"""Automatic dataset knowledge-graph builder.

This is the rigor/innovation centerpiece of DATIA. We discover relationships between
the ~30 priority datasets so the agent can answer cross-sector questions
("empresas sancionadas que además tienen contratos en salud en Antioquia") by
following graph edges instead of guessing.

Pipeline (`build_graph(dataset_ids)`):

  1. For each dataset, fetch `/api/views/{id}.json` and normalize every column name
     via `synonyms.normalize_column` (e.g. `nit_entidad` -> `nit`).
  2. Classify each normalized column into one of
     {entity_id, geo, time, measure, descriptor, id_internal} using a single batched
     LiteLLM call with a strict JSON-schema prompt.
  3. Propose edges:
       - JOINABLE_ON: two datasets sharing an `entity_id` column with the same
         normalized concept (e.g. both have `nit`).
       - LOCATED_IN: a dataset with a `geo` municipio/departamento column.
       - SAME_TOPIC: dataset pairs in the same `domain_category` whose catalog
         embeddings have cosine similarity > 0.82.
  4. Validate each JOINABLE_ON edge by sampling distinct values from both datasets
     (SocrataClient.distinct_values) and keeping the edge only if the Jaccard
     overlap of the value sets exceeds 0.1. This avoids spurious joins on columns
     that merely share a name but hold different domains.
  5. Upsert `graph_nodes` (one per dataset, plus concept nodes) and `graph_edges`
     into Supabase.

The graph is intentionally conservative: false-positive joins are more dangerous
than missing edges, so join validation is a hard gate.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from app.config import settings
from app.graph.synonyms import normalize_column
from app.socrata.client import SocrataClient

# --- types -----------------------------------------------------------------

CLASSIFY_SYSTEM = (
    "You are a data catalog classifier. Given a list of dataset columns, classify each "
    "into exactly one of:\n"
    "  entity_id   - a unique identifier of a real-world entity (NIT, DANE code, drug id)\n"
    "  geo         - a geographic place (municipio, departamento, region)\n"
    "  time        - a date / timestamp column\n"
    "  measure     - a numeric measure / quantity to aggregate\n"
    "  descriptor  - a free-text / categorical descriptor\n"
    "  id_internal - an internal row id with no join value\n"
    "Respond with ONLY a JSON object mapping each column name to its label."
)

SAME_TOPIC_THRESHOLD = 0.82
JOIN_JACCARD_THRESHOLD = 0.1


def _supabase():
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_service_key)


def _llm_complete(system: str, user: str) -> str:
    """Single LLM completion via LiteLLM (provider-agnostic)."""
    import litellm

    model = settings.litellm_model
    kwargs: dict[str, Any] = {}
    if settings.litellm_api_base:
        kwargs["api_base"] = settings.litellm_api_base
    key = settings.litellm_api_key_resolved
    if key:
        kwargs["api_key"] = key
    resp = litellm.completion(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0,
        **kwargs,
    )
    return resp["choices"][0]["message"]["content"]  # type: ignore[index]


def _classify_columns(dataset_id: str, columns: list[str]) -> dict[str, str]:
    """Ask the LLM to label every column. Returns {column_name: label}."""
    if not columns:
        return {}
    user = json.dumps({"dataset": dataset_id, "columns": columns}, ensure_ascii=False)
    raw = _llm_complete(CLASSIFY_SYSTEM, user)
    # tolerate markdown fences
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _get_normalized_schema(client: SocrataClient, dataset_id: str) -> list[dict]:
    """Fetch view metadata and return columns with raw + normalized names + datatype."""
    view = client.get_views(dataset_id)
    cols = view.get("columns") or []
    out = []
    for c in cols:
        raw = c.get("name") or c.get("fieldName") or ""
        field = c.get("fieldName") or raw
        out.append(
            {
                "raw_name": raw,
                "field_name": field,
                "normalized": normalize_column(raw),
                "datatype": c.get("dataTypeName") or c.get("renderTypeName"),
            }
        )
    return out


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _same_topic_pairs(sb, dataset_ids: list[str]) -> list[tuple[str, str, float]]:
    """Find SAME_TOPIC pairs by cosine similarity of catalog embeddings (>0.82)."""
    import numpy as np

    rows = (
        sb.table("catalog_embeddings")
        .select("dataset_id, embedding")
        .in_("dataset_id", dataset_ids)
        .execute()
        .data
    )
    cats = sb.table("catalog").select("id, domain_category").in_("id", dataset_ids).execute().data
    cat_of = {r["id"]: r.get("domain_category") for r in cats}
    emb_of = {r["dataset_id"]: np.asarray(r["embedding"], dtype=float) for r in rows if r.get("embedding")}
    pairs = []
    ids = [d for d in dataset_ids if d in emb_of]
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            # only within same domain_category (if both have one)
            ca, cb = cat_of.get(a), cat_of.get(b)
            if ca and cb and ca != cb:
                continue
            va, vb = emb_of[a], emb_of[b]
            sim = float(va @ vb / ((np.linalg.norm(va) * np.linalg.norm(vb)) + 1e-9))
            if sim >= SAME_TOPIC_THRESHOLD:
                pairs.append((a, b, sim))
    return pairs


def build_graph(dataset_ids: list[str]) -> dict:
    """Run the full graph-build pipeline for the given dataset ids.

    Returns a small report dict: counts of nodes/edges produced.
    """
    sb = _supabase()
    client = SocrataClient(settings.socrata_domain, settings.socrata_app_token)

    # ---- Step 1+2: schemas + classification -------------------------------
    schemas: dict[str, list[dict]] = {}
    classified: dict[str, dict[str, str]] = {}
    for did in dataset_ids:
        try:
            schema = _get_normalized_schema(client, did)
        except Exception as exc:  # noqa: BLE001
            print(f"[build_graph] schema fetch failed for {did}: {exc}")
            continue
        schemas[did] = schema
        raw_names = [c["raw_name"] for c in schema]
        classified[did] = _classify_columns(did, raw_names)

    # ---- Step 3a: JOINABLE_ON proposals ----------------------------------
    # group datasets by normalized column concept, for columns classified as entity_id
    concept_to_datasets: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for did, schema in schemas.items():
        labels = classified.get(did, {})
        for col in schema:
            if labels.get(col["raw_name"]) == "entity_id":
                concept_to_datasets[col["normalized"]].append((did, col["raw_name"]))

    join_proposals: list[tuple[str, str, str, str, str]] = []  # a, b, concept, colA, colB
    for concept, members in concept_to_datasets.items():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, colA = members[i]
                b, colB = members[j]
                if a == b:
                    continue
                join_proposals.append((a, b, concept, colA, colB))

    # ---- Step 4: validate joins via Jaccard of distinct values -----------
    value_cache: dict[tuple[str, str], set] = {}

    def distinct(did: str, field: str) -> set:
        key = (did, field)
        if key not in value_cache:
            try:
                vals = client.distinct_values(did, field, limit=50)
                value_cache[key] = {str(v) for v in vals}
            except Exception:  # noqa: BLE001
                value_cache[key] = set()
        return value_cache[key]

    validated_edges: list[dict] = []
    for a, b, concept, colA, colB in join_proposals:
        va, vb = distinct(a, colA), distinct(b, colB)
        j = _jaccard(va, vb)
        if j > JOIN_JACCARD_THRESHOLD:
            validated_edges.append(
                {
                    "src": a,
                    "dst": b,
                    "type": "JOINABLE_ON",
                    "confidence": j,
                    "extra": {"concept": concept, "col_a": colA, "col_b": colB},
                }
            )

    # ---- Step 3b: SAME_TOPIC edges ---------------------------------------
    for a, b, sim in _same_topic_pairs(sb, list(schemas.keys())):
        validated_edges.append({"src": a, "dst": b, "type": "SAME_TOPIC", "confidence": sim, "extra": {}})

    # ---- Step 3c: LOCATED_IN (dataset -> geo concept) --------------------
    located_edges: list[dict] = []
    for did, schema in schemas.items():
        labels = classified.get(did, {})
        for col in schema:
            if labels.get(col["raw_name"]) == "geo":
                located_edges.append(
                    {
                        "src": did,
                        "dst": f"geo:{col['normalized']}",
                        "type": "LOCATED_IN",
                        "confidence": 1.0,
                        "extra": {"column": col["raw_name"]},
                    }
                )

    # ---- Step 5: upsert nodes + edges to Supabase -----------------------
    nodes: list[dict] = []
    for did, schema in schemas.items():
        nodes.append(
            {
                "id": did,
                "type": "dataset",
                "label": did,
                "dataset_id": did,
                "extra": {"n_columns": len(schema)},
            }
        )
    # concept/geo nodes
    concept_nodes: set = set()
    for e in validated_edges + located_edges:
        if e["type"] in ("LOCATED_IN",):
            concept_nodes.add(e["dst"])
    for cn in concept_nodes:
        nodes.append({"id": cn, "type": "concept", "label": cn, "dataset_id": None, "extra": {}})

    if nodes:
        sb.table("graph_nodes").upsert(nodes, on_conflict="id").execute()
    all_edges = validated_edges + located_edges
    if all_edges:
        # drop serial id; let DB assign
        sb.table("graph_edges").upsert(
            [{"src": e["src"], "dst": e["dst"], "type": e["type"], "confidence": e["confidence"], "extra": e["extra"]}
             for e in all_edges]
        ).execute()

    return {
        "datasets": len(schemas),
        "nodes": len(nodes),
        "edges": len(all_edges),
        "join_edges": len(validated_edges),
    }
