"""LangGraph agent: triage -> search -> schema -> generate_soql -> exhaust_self_correct -> answer.

State machine nodes: triage, chitchat_answer, search, schema, generate_soql,
execute_query, check_result, answer. ``triage`` asks a small LLM to classify the
incoming question and, for meta/greeting/capability questions, to draft the
Spanish reply in the same call; that pair short-circuits straight to
``chitchat_answer`` (falling back to the canned ``CHITCHAT_ANSWER`` if the LLM
left the answer blank) with no DB/chart work, while genuine data questions
proceed into the usual pipeline starting at ``search``. On a SoQL error the
agent regenerates the query up to ``MAX_RETRIES``
times, feeding the error message back into the LLM prompt so the next attempt can
fix the broken clause. The final answer is generated in Spanish by a separate LLM
call, paired with citations and (when tabular) a Vega-Lite chart.

The LLM call is isolated in :func:`llm_complete` so the wiring stays real even if
you swap providers via LiteLLM. When ``LITELLM_API_BASE`` is set the model name is
prefixed with ``openai/`` so LiteLLM routes through the OpenAI-compatible endpoint
(e.g. OpenCode Go / glm-5.2).
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import TypedDict
from urllib.parse import parse_qsl

import yaml
from langgraph.graph import END, StateGraph

from app.agents import few_shots
from app.agents import tools as T
from app.agents.llm import llm_complete, llm_complete_small
from app.agents.tools import _coerce_number
from app.config import settings

log = logging.getLogger("manglar.agent")

MAX_RETRIES = 2
_SOQL_HARD_LIMIT = 50000

# search_catalog() scores are fused RRF + priority-boost values on a SMALL
# scale — a strong/relevant top match is only ~0.045-0.05, and typical scores
# range ~0.02-0.05. They are NOT 0-1 similarity scores; never gate on 0.5.
_PRIORITY_OVERRIDE_MAX_SCORE = 0.03  # only override when the top hit is genuinely weak
_MIN_CONFIDENT_SCORE = 0.02  # below this, refuse to commit so answer_node's honest fallback fires

_HERO_YAML = Path(__file__).resolve().parent.parent.parent / "data" / "hero_questions.yaml"


# --- Prompts ---------------------------------------------------------------

SOQL_SYSTEM_PROMPT = (
    "Eres un generador de consultas SoQL para Socrata (datos.gov.co).\n"
    "Recibes una pregunta en español y el esquema de un dataset.\n"
    "Generas SÓLO la consulta SoQL (la parte después de ? en la URL del recurso).\n"
    "No agregues explicaciones, solo el SoQL.\n\n"
    "Reglas importantes:\n"
    "- Usa field_name (snake_case) no el name de columna\n"
    "- Fechas en formato ISO: '2025-01-01T00:00:00.000'\n"
    "- Los valores de texto NO son consistentes entre datasets: unos guardan 'Medellín',\n"
    "  otros 'MEDELLIN' (mayúsculas, sin tilde). Por eso, para filtrar por texto usa SIEMPRE\n"
    "  coincidencia insensible a mayúsculas/tildes con upper(): p. ej.\n"
    "  $where=upper(ciudad)=upper('Medellín')  o  $where=upper(departamento) like upper('%antioquia%').\n"
    "  NUNCA asumas Title Case con un '=' exacto.\n"
    "- $limit por defecto 1000, máximo 50000\n"
    "- Cada fragmento debe tener forma $parametro=valor y separarse con &: "
    "$select=...&$where=... Nunca escribas SQL plano ni predicados fuera de $where.\n"
    "- Usa upper(campo) like upper('%texto%'); ILIKE no está soportado.\n"
    "- No uses subconsultas.\n"
    "- Agregaciones: $select=campo, count(*)&$group=campo\n"
    "- Top N: $order=campo DESC&$limit=N"
)

ANSWER_SYSTEM_PROMPT = (
    "Eres Manglar, un asistente que explica datos de Colombia en español claro y simple.\n"
    "Recibes una pregunta, el resultado de una consulta SoQL, y los metadatos del dataset.\n"
    "Respondes en español, en máximo 3 párrafos, con el dato principal primero.\n"
    "Menciona el dataset por nombre e incluye el número exacto si aplica.\n"
    "REGLA CRÍTICA: si el dataset NO trata sobre el tema exacto de la pregunta "
    "(por ejemplo, te dan datos de COVID-19 pero preguntan por dengue), NO reportes "
    "ninguna cifra de ese dataset. En su lugar responde exactamente que no encontraste "
    "un dataset preciso para esa pregunta y sugiere consultar la fuente oficial. "
    "Nunca presentes un número de un tema distinto como si respondiera la pregunta.\n"
    "Cuando compares periodos o reportes un promedio, total o variación, incluye SIEMPRE "
    "los valores numéricos exactos en la respuesta (no describas solo la tendencia)."
)

JOIN_ANSWER_SYSTEM_PROMPT = (
    "Eres Manglar, un asistente que explica datos de Colombia en español claro y simple.\n"
    "Recibes una pregunta, el resultado de una consulta que cruza DOS datasets, y los "
    "metadatos de ambos.\n"
    "El resultado filtra el dataset SECUNDARIO a las llaves (NIT/documento) presentes en "
    "el PRIMARIO.\n"
    "Respondes en español, en máximo 3 párrafos, con el dato principal primero.\n"
    "Menciona AMBOS datasets por nombre en la respuesta (primario y secundario).\n"
    "Si el campo 'partial' es true, indica que el resultado es parcial y que los números "
    "pueden estar subestimados."
)

RELEVANCE_GATE_SYSTEM_PROMPT = (
    "Eres un verificador de relevancia para un asistente de datos abiertos de Colombia.\n"
    "Recibes una pregunta del usuario y los metadatos (nombre + columnas) de UN dataset "
    "candidato que un buscador eligió.\n"
    "Tu única tarea: decidir si ese dataset REALMENTE contiene los datos necesarios para "
    "responder la pregunta, sobre el MISMO tema.\n"
    "Un dataset de un tema distinto NO sirve aunque se parezca (p. ej. preguntan por dengue "
    "y el dataset es de COVID-19; preguntan por hurtos y el dataset es de homicidios).\n"
    'Responde SOLO con JSON válido, sin markdown: {"relevant": true|false, "reason": "..."}.\n'
    "Sé conservador: si hay duda razonable de que el dataset SÍ cubre el tema, responde "
    "true. Responde false solo cuando el dataset trate claramente de otro tema."
)

JOIN_SYSTEM_PROMPT = (
    "Eres un generador de consultas SoQL para Socrata (datos.gov.co) que produce UN JOIN "
    "entre dos datasets.\n"
    "Recibes una pregunta en español, y los esquemas de DOS datasets (primario y secundario).\n"
    "Devuelves un único JSON con las claves:\n"
    '  "primary_soql": SoQL para el dataset PRIMARIO. SOLO $select la columna llave '
    "(join_key_primary). Fija $limit=50000. No incluyas otras columnas ni filtros.\n"
    '  "partner_soql": SoQL para el dataset SECUNDARIO (filtrado a lo que la pregunta pide, '
    "incluye la columna join_key_partner y las columnas relevantes para responder). "
    "NO incluyas $limit (el sistema lo añade).\n"
    '  "join_key_primary": el field_name de la columna del PRIMARIO que sirve de llave '
    "(ej: documento_contratista)\n"
    '  "join_key_partner": el field_name de la columna del SECUNDARIO que sirve de llave '
    "(ej: documento_proveedor)\n"
    "Reglas SoQL: Fechas ISO. Usa field_name no name. Cada consulta debe usar parámetros "
    "$select=...&$where=...; nunca SQL plano ni predicados sueltos. Usa "
    "upper(campo) like upper('%texto%'), nunca ILIKE. No uses subconsultas. "
    "Devuelve SOLO el JSON, sin explicación."
)


# --- State -----------------------------------------------------------------


class AgentState(TypedDict):
    """Mutable state passed between graph nodes."""

    question: str
    datasets: list[dict]
    dataset_id: str | None
    schema: dict | None
    soql: str | None
    query_result: dict | None
    retry_count: int
    answer: str | None
    chart: dict | None
    sources: list[dict]
    step: str
    is_join_question: bool
    join_partner_id: str | None
    join_key_primary: str | None
    join_key_partner: str | None
    partner_schema: dict | None
    partner_soql: str | None
    partner_query_result: dict | None
    is_chitchat: bool
    chitchat_answer_text: str
    needs_clarification: bool
    clarification_question: str


# --- Helpers ---------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_hero_questions() -> list[dict]:
    """Load and cache the hero questions list from YAML.

    Returns a list of dicts with keys: id, question, datasets, pattern.
    """
    if not _HERO_YAML.exists():
        return []
    data = yaml.safe_load(_HERO_YAML.read_text(encoding="utf-8")) or {}
    return data.get("hero_questions", [])


def _column_brief(schema: dict | None, max_cols: int = 30) -> str:
    """Build a compact `field_name (datatype): name` listing for the LLM.

    Limited to *max_cols* columns (default 30) to keep the prompt small for
    datasets with many columns.  Column descriptions are truncated to 50 chars.
    """
    if not schema:
        return ""
    cols = schema.get("columns", []) or []
    lines = []
    for c in cols[:max_cols]:
        name = c.get("name", "")
        if len(name) > 50:
            name = name[:47] + "..."
        lines.append(f"- {c.get('field_name', '')} ({c.get('datatype', '')}): {name}")
    if len(cols) > max_cols:
        lines.append(f"... ({len(cols) - max_cols} more columns omitted)")
    return "\n".join(lines)


def _few_shots_text(question: str = "", max_patterns: int = 6) -> str:
    """Return a compact few-shot block, ranked by token overlap with *question*."""
    patterns = few_shots.load_patterns()
    if question:
        q_tokens = set(re.findall(r"\w+", question.lower()))

        def _overlap(p: dict) -> int:
            p_tokens = set(re.findall(r"\w+", str(p.get("user_question", "")).lower()))
            return len(q_tokens & p_tokens)

        patterns = sorted(patterns, key=_overlap, reverse=True)
    patterns = patterns[:max_patterns]
    return "\n".join(f"- Q: {p['user_question']}\n  SoQL: {p['soql']}" for p in patterns)


def _clean_soql(raw: str) -> str:
    """Strip markdown fences / leading labels from an LLM SoQL response."""
    soql = raw.strip().strip("`")
    if soql.lower().startswith("soql"):
        soql = soql.split("\n", 1)[-1].strip()
    if soql.startswith("```"):
        soql = "\n".join(soql.splitlines()[1:])
        soql = soql.rsplit("```", 1)[0]
    return soql.strip().strip("`").strip()


_ALLOWED_SOQL_PARAMS = {
    "$select",
    "$where",
    "$group",
    "$order",
    "$limit",
    "$offset",
    "$q",
    "$having",
    "$query",
}


def _validate_soql(soql: str) -> str | None:
    """Return a concise structural validation error, or ``None`` when valid."""
    if not soql or not soql.strip():
        return "consulta vacía"
    if re.search(r"\bilike\b", soql, re.IGNORECASE):
        return "ILIKE no está soportado; usa upper(campo) like upper('%texto%')"

    pairs = parse_qsl(soql.lstrip("?"), keep_blank_values=True)
    if not pairs:
        return "no contiene parámetros SoQL"

    seen: set[str] = set()
    for raw_key, value in pairs:
        key = raw_key.lower().strip()
        if key not in _ALLOWED_SOQL_PARAMS:
            return f"parámetro SoQL inválido: {raw_key!r}"
        if key in seen:
            return f"parámetro SoQL duplicado: {raw_key}"
        seen.add(key)
        if not value.strip():
            return f"valor vacío para {raw_key}"
        if key in {"$limit", "$offset"}:
            try:
                number = int(value)
            except ValueError:
                return f"{raw_key} debe ser un entero"
            if number < 0 or (key == "$limit" and number > _SOQL_HARD_LIMIT):
                return f"{raw_key} fuera del rango permitido"

    return None


def _looks_like_soql(soql: str) -> bool:
    """Backward-compatible boolean wrapper around :func:`_validate_soql`."""
    return _validate_soql(soql) is None


_JOIN_QUESTION_RE = re.compile(
    r"que\s+ad[eé]m[aá]s"
    r"|que\s+ambi[eé]n"
    r"|que\s+cuentan\s+con"
    r"|sancionad[aá]s?.*(?:contrat|salud)"
    r"|contrat.*sancionad",
    re.IGNORECASE,
)


def _detect_join_question(question: str) -> bool:
    """Return True if the question looks like a cross-dataset join request.

    Pure function — regex match on Spanish cues that signal the user wants
    results from two datasets intersected by a shared key.
    """
    return _JOIN_QUESTION_RE.search(question) is not None


def _resolve_secop_pair(question: str) -> tuple[str, str] | None:
    """Detect the SECOP-Sancionados + SECOP-II-Contratos pair from a question.

    Returns ``(sancionados_id, contratos_id)`` when both concepts are present,
    else ``None``.  Uses the priority YAML so the IDs stay in one place.
    """
    from app.rag.catalog import _load_priority_datasets

    q = question.lower()
    sancionados_id: str | None = None
    contratos_id: str | None = None
    for ds in _load_priority_datasets():
        hint = (ds.get("search_hint") or "").lower()
        did = ds.get("id")
        if not did:
            continue
        if "sancionad" in hint and sancionados_id is None:
            sancionados_id = did
        elif ("secop2 contratos" in hint or "secop ii contratos" in hint) and contratos_id is None:
            contratos_id = did
    if sancionados_id is None or contratos_id is None:
        return None
    if "sancionad" not in q:
        return None
    if "contrat" not in q and "secop" not in q:
        return None
    return (sancionados_id, contratos_id)


def _find_join_neighbor(primary_id: str, label_hint: str = "") -> str | None:
    """Pick a neighbor of ``primary_id`` from the dataset graph.

    When ``label_hint`` is non-empty, prefer a neighbor whose label contains
    the hint as a substring.  Otherwise return the highest-confidence neighbor.
    Returns ``None`` when the graph has no neighbors for the primary dataset.
    """
    neighbors = T.graph_neighbors(primary_id)
    if not neighbors:
        return None
    if label_hint:
        hint = label_hint.lower()
        for n in neighbors:
            if hint in (n.get("label") or "").lower():
                return n["dataset_id"]
    return neighbors[0]["dataset_id"]


# --- Chitchat / triage ------------------------------------------------------

TRIAGE_SYSTEM_PROMPT = (
    "Eres el enrutador de Manglar, un asistente de datos abiertos de Colombia "
    "(datos.gov.co). Decide si el mensaje del usuario requiere CONSULTAR datos "
    "públicos (cifras, estadísticas, datasets, contratos, salud, contratación, "
    "etc.) o si es conversación general, un saludo, o una pregunta sobre quién "
    "eres / qué puedes hacer. Responde SOLO con JSON válido, sin markdown, con "
    'la forma {"needs_data": true|false, "answer": "..."}. Si needs_data es '
    "false, en 'answer' escribe una respuesta breve, amable y útil en español "
    "(si preguntan por tus capacidades, explica brevemente qué haces y da 2-3 "
    "ejemplos de preguntas). Si needs_data es true, deja 'answer' como cadena "
    "vacía."
)


CHITCHAT_ANSWER = (
    "¡Hola! Soy Manglar, un asistente que te ayuda a explorar los datos abiertos de "
    "Colombia publicados en datos.gov.co. Busco los datasets relevantes, genero "
    "consultas automáticamente y te respondo con cifras exactas, fuentes citadas y, "
    "cuando aplica, un gráfico.\n\n"
    "Algunas preguntas que puedes hacerme:\n"
    "- ¿Cuántos contratos públicos firmó Medellín en 2025 y cuáles son las top 5 empresas?\n"
    "- ¿Qué datos abiertos existen sobre vacunación?\n"
    "- ¿Cuál fue la TRM promedio del último mes comparada con el año anterior?\n"
    "- ¿Cuántos beneficiarios de Familias en Acción hay por municipio en Antioquia?\n\n"
    "¡Pregúntame lo que quieras saber sobre los datos públicos de Colombia!"
)


# --- Nodes ---------------------------------------------------------------


_MISSING_LOCATION_RE = re.compile(
    r"\bmi\s+(municipio|ciudad|departamento)\b",
    re.IGNORECASE,
)


def _location_clarification(question: str) -> str | None:
    """Return a clarification prompt when a possessive location has no context."""
    match = _MISSING_LOCATION_RE.search(question)
    if not match:
        return None
    location_type = match.group(1).lower()
    return f"¿Cuál es tu {location_type}? Incluye el departamento si puede haber ambigüedad."


def triage_node(state: AgentState) -> AgentState:
    """Classify the question as chitchat/meta vs. a genuine data question.

    Uses a single small-model LLM call that both classifies the message and
    (for non-data messages) drafts the Spanish reply, so there is no
    regex/keyword list to keep in sync with real usage. The safe default on
    any exception, timeout, or unparsable response is the DATA path — we
    never want to wrongly refuse a genuine data question.
    """
    clarification = _location_clarification(state["question"])
    if clarification:
        state["needs_clarification"] = True
        state["clarification_question"] = clarification
        state["is_chitchat"] = False
        state["chitchat_answer_text"] = ""
        state["step"] = "triage"
        return state

    state["needs_clarification"] = False
    state["clarification_question"] = ""
    messages = [
        {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
        {"role": "user", "content": state["question"]},
    ]
    try:
        raw = llm_complete_small(messages, temperature=0)
        parsed = _parse_join_llm_response(raw)
    except Exception as exc:  # noqa: BLE001
        log.warning("triage LLM call failed, defaulting to data path: %s", exc)
        parsed = None

    if not parsed or "needs_data" not in parsed:
        if parsed is not None:
            log.warning("triage LLM parse failed, defaulting to data path: raw=%r", raw)
        state["is_chitchat"] = False
        state["chitchat_answer_text"] = ""
    elif not parsed["needs_data"]:
        state["is_chitchat"] = True
        state["chitchat_answer_text"] = parsed.get("answer") or ""
    else:
        state["is_chitchat"] = False
        state["chitchat_answer_text"] = ""

    state["step"] = "triage"
    return state


def chitchat_answer_node(state: AgentState) -> AgentState:
    """Instant Spanish answer for meta questions — no DB/LLM/chart.

    Prefers the answer the triage LLM already drafted; falls back to the
    canned ``CHITCHAT_ANSWER`` when the LLM left it empty (e.g. safe-default
    path where triage wasn't actually the chitchat branch, or an LLM answer
    that came back blank).
    """
    state["answer"] = state.get("chitchat_answer_text") or CHITCHAT_ANSWER
    state["sources"] = []
    state["chart"] = None
    state["step"] = "answer"
    return state


def clarification_answer_node(state: AgentState) -> AgentState:
    """Ask for required context without catalog, Socrata, or another LLM call."""
    state["answer"] = state.get("clarification_question") or (
        "Necesito un poco más de contexto para consultar los datos."
    )
    state["sources"] = []
    state["chart"] = None
    state["step"] = "answer"
    return state


def search_node(state: AgentState) -> AgentState:
    """Find candidate datasets via catalog RAG and pick the best one.

    Selection order:
    1. **Priority override** — if the top result's score is below
       ``_PRIORITY_OVERRIDE_MAX_SCORE`` AND the question keyword-matches a
       priority dataset, override with that match.
    2. **Low-confidence fallback** — if there was no priority override and the
       top score is below ``_MIN_CONFIDENT_SCORE`` (and this isn't a join
       question), leave ``dataset_id`` unset so ``answer_node`` gives an
       honest "no relevant dataset found" answer instead of querying a weak
       match.
    3. **Default** — otherwise pick the highest-scored result from RAG.

    When the question looks like a cross-dataset join, the node also resolves
    the partner dataset (SECOP pair via priority YAML, or graph neighbors).
    """
    results = T.search_catalog(state["question"])
    state["datasets"] = results
    state["step"] = "search"

    if not results:
        return state

    # Default: pick the highest-scored result
    best = results[0]
    chosen_id = best.get("id")
    chosen_score = float(best.get("score", 0.0))

    # Priority override: if top score is low, check keyword matches
    priority_match = None
    if chosen_score < _PRIORITY_OVERRIDE_MAX_SCORE:
        priority_match = _find_priority_keyword_override(state["question"], results)
        if priority_match:
            log.info(
                "Priority override: %s -> %s (top score was %.3f)",
                chosen_id,
                priority_match,
                chosen_score,
            )
            chosen_id = priority_match

    # Join detection — computed before the low-confidence check below so a
    # weak-scoring join question never gets its dataset_id cleared here (the
    # join path resolves/consumes dataset_id independently, further down).
    state["is_join_question"] = _detect_join_question(state["question"])

    if not state.get("dataset_id"):
        if (
            priority_match is None
            and chosen_score < _MIN_CONFIDENT_SCORE
            and not state["is_join_question"]
        ):
            # Honest low-confidence fallback: refuse to commit to a weak match.
            # answer_node's `dataset_id is None` branch will suggest alternatives
            # from `state["datasets"]` instead of querying an irrelevant dataset.
            state["dataset_id"] = None
        else:
            state["dataset_id"] = chosen_id

    if state["is_join_question"]:
        pair = _resolve_secop_pair(state["question"])
        if pair:
            state["dataset_id"] = pair[0]
            state["join_partner_id"] = pair[1]
        else:
            primary = state.get("dataset_id")
            if primary:
                state["join_partner_id"] = _find_join_neighbor(primary)
            else:
                state["join_partner_id"] = None

    return state


def _find_priority_keyword_override(question: str, results: list[dict]) -> str | None:
    """Check if the question keyword-matches a priority dataset not already chosen.

    Returns the dataset ID to override with, or None if no override is needed.
    """
    from app.rag.catalog import _priority_ids, _priority_keyword_match

    pids = _priority_ids()
    matches = _priority_keyword_match(question)
    if not matches:
        return None

    # Find the best keyword match that is a priority dataset
    for m in matches:
        mid = m.get("id")
        if mid in pids:
            # Check if it's already in the results with a decent score
            in_results = any(
                r.get("id") == mid and float(r.get("score", 0.0)) >= 0.5 for r in results
            )
            if not in_results:
                return mid
    return None


def schema_node(state: AgentState) -> AgentState:
    """Pull the schema for the chosen dataset from the registry."""
    did = state.get("dataset_id")
    state["schema"] = T.get_schema(did) if did else None
    state["step"] = "schema"
    return state


def relevance_gate_node(state: AgentState) -> AgentState:
    """Reject a chosen dataset whose subject doesn't match the question.

    The score-based selection in ``search_node`` catches "nothing is even
    weakly similar", but not "the top match is about a *different subject*
    than asked" — a topically-adjacent dataset (COVID for a dengue question,
    homicidios for a hurtos question) sails past the score floor. This node
    asks a small LLM whether the chosen dataset actually contains data for the
    question's subject; on a confident "no" it clears ``dataset_id`` so the
    downstream honest fallback fires instead of reporting a cross-topic number.

    Conservative by design: any LLM/parse failure, or genuine doubt, leaves the
    dataset in place — we never want to wrongly refuse a valid data question.
    """
    did = state.get("dataset_id")
    schema = state.get("schema")
    state["step"] = "relevance_gate"
    if not did or not schema:
        return state

    col_text = _column_brief(schema, max_cols=15)
    user_content = (
        f"Pregunta: {state['question']}\n"
        f"Dataset candidato: {schema.get('name', did)}\n"
        f"Columnas:\n{col_text}"
    )
    messages = [
        {"role": "system", "content": RELEVANCE_GATE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        parsed = _parse_join_llm_response(llm_complete_small(messages, temperature=0))
    except Exception as exc:  # noqa: BLE001
        log.warning("relevance_gate LLM call failed, keeping dataset: %s", exc)
        return state

    if parsed and parsed.get("relevant") is False:
        log.info(
            "Relevance gate rejected %s for question %r: %s",
            did,
            state["question"][:80],
            parsed.get("reason", ""),
        )
        state["dataset_id"] = None
    return state


def _build_soql_messages(state: AgentState, *, correction: str | None = None) -> list[dict]:
    """Compose the messages asking the LLM to write (or fix) a SoQL query."""
    did = state.get("dataset_id")
    schema = state.get("schema") or {}
    col_text = _column_brief(schema)
    few_shots_text = _few_shots_text(state["question"])
    messages: list[dict] = [
        {"role": "system", "content": SOQL_SYSTEM_PROMPT},
        {"role": "system", "content": f"Ejemplos SoQL:\n{few_shots_text}"},
        {
            "role": "user",
            "content": (
                f"Pregunta: {state['question']}\nDataset id: {did}\nColumnas:\n{col_text}"
                if col_text
                else f"Pregunta: {state['question']}"
            ),
        },
    ]
    if correction:
        messages.append({"role": "assistant", "content": state.get("soql", "")})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Esa consulta falló con este error: {correction}\n"
                    "Corregila. Devuelve SOLO el SoQL corregido."
                ),
            }
        )
    return messages


def generate_soql_node(state: AgentState) -> AgentState:
    """Ask the LLM to write (or fix) a SoQL query for the current dataset.

    On a retry the previous error message is fed back into the prompt so the LLM
    can repair the broken clause. If no dataset was chosen the node produces an
    empty SoQL string; ``execute_query_node`` will mark a synthetic error and the
    routing logic will jump straight to ``answer``.
    """
    did = state.get("dataset_id")
    if not did:
        state["soql"] = ""
        state["step"] = "generate_soql"
        return state

    # If the previous attempt produced an empty query (LLM failed OR returned
    # garbage) without an actionable correction error, don't burn another LLM
    # call — bump the retry counter past the budget so routing goes to answer.
    prev_result = state.get("query_result") or {}
    prev_error = prev_result.get("error")
    prev_soql = state.get("soql") or ""
    if (
        prev_error
        and not prev_soql
        and prev_error == "no_se_pudo_generar_la_consulta_o_no_hay_dataset"
    ):
        state["retry_count"] = MAX_RETRIES + 1
        state["step"] = "generate_soql"
        return state

    correction = None
    result = state.get("query_result")
    if result and result.get("error") and state.get("soql"):
        correction = result.get("error")

    messages = _build_soql_messages(state, correction=correction)
    try:
        soql = _clean_soql(llm_complete_small(messages, temperature=0))
    except Exception as exc:  # noqa: BLE001
        log.exception("generate_soql LLM call failed: %s", exc)
        soql = ""

    validation_error = _validate_soql(soql)
    if validation_error:
        log.warning("generate_soql produced invalid SoQL: %s", validation_error)
    state["soql"] = soql
    state["step"] = "generate_soql"
    return state


def execute_query_node(state: AgentState) -> AgentState:
    """Run the SoQL query against the Socrata resource."""
    did = state.get("dataset_id")
    soql = state.get("soql") or ""
    if not did or not soql:
        state["query_result"] = {
            "rows": [],
            "count": 0,
            "error": "no_se_pudo_generar_la_consulta_o_no_hay_dataset",
        }
        state["step"] = "execute_query"
        return state
    validation_error = _validate_soql(soql)
    if validation_error:
        state["query_result"] = {
            "rows": [],
            "count": 0,
            "error": f"invalid_soql: {validation_error}",
        }
        state["step"] = "execute_query"
        return state
    state["query_result"] = T.query_dataset(did, soql)
    state["step"] = "execute_query"
    return state


def check_result_node(state: AgentState) -> AgentState:
    """Evaluate the query result; bump ``retry_count`` on a fixable error.

    The increment happens unconditionally on error so the routing function can use
    ``retry_count <= MAX_RETRIES`` as the post-increment retry guard — this gives
    exactly ``MAX_RETRIES`` regeneration rounds without an infinite loop.
    """
    result = state.get("query_result") or {}
    if result.get("error"):
        state["retry_count"] = state.get("retry_count", 0) + 1
    state["step"] = "check_result"
    return state


def answer_node(state: AgentState) -> AgentState:
    """Generate the Spanish answer, citations, and optional Vega-Lite chart."""
    did = state.get("dataset_id")
    schema = state.get("schema") or {}
    datasets = state.get("datasets") or []
    result = state.get("query_result") or {}
    rows = result.get("rows") or []
    soql = state.get("soql") or ""
    error = result.get("error")

    domain = settings.socrata_domain
    permalink = schema.get("permalink") or next(
        (r.get("permalink") for r in datasets if r.get("id") == did),
        f"https://{domain}/d/{did}" if did else None,
    )

    sources: list[dict] = [
        {"name": schema.get("name", did or ""), "permalink": permalink, "soql": soql}
    ]
    if state.get("is_join_question"):
        partner_schema = state.get("partner_schema") or {}
        partner_id = state.get("join_partner_id")
        if partner_schema or partner_id:
            partner_permalink = partner_schema.get("permalink") or next(
                (r.get("permalink") for r in datasets if r.get("id") == partner_id),
                f"https://{domain}/d/{partner_id}" if partner_id else None,
            )
            sources.append(
                {
                    "name": partner_schema.get("name", partner_id or ""),
                    "permalink": partner_permalink,
                    "soql": state.get("partner_soql") or "",
                }
            )
    state["sources"] = sources

    if error and not rows:
        if not did:
            suggestions = datasets[:3]
            names = ", ".join(s.get("name", "") for s in suggestions if s.get("name"))
            state["answer"] = (
                "No encontré un dataset claramente relevante para tu pregunta en "
                "el catálogo de datos.gov.co."
            )
            if names:
                state["answer"] += f" Tal vez te refieras a: {names}."
            state["chart"] = None
            state["step"] = "answer"
            return state
        retries = state.get("retry_count", 0)
        state["answer"] = (
            f"No pude completar la consulta tras {retries} intentos de corrección. "
            f"Error final: {error}"
        )
        state["chart"] = None
        state["step"] = "answer"
        return state

    summary_ctx = json.dumps(rows[:20], ensure_ascii=False, default=str)
    is_join = state.get("is_join_question")
    system_prompt = JOIN_ANSWER_SYSTEM_PROMPT if is_join else ANSWER_SYSTEM_PROMPT

    total_rows = len(rows)
    # For single-row aggregate results (count/sum/avg), extract the exact numeric
    # values so the LLM echoes them verbatim instead of recomputing from a slice.
    exact_values = None
    if total_rows == 1 and rows[0]:
        scalars = {k: v for k, v in rows[0].items() if _coerce_number(v) is not None}
        if scalars:
            exact_values = scalars

    if is_join:
        partner_schema = state.get("partner_schema") or {}
        partner_id = state.get("join_partner_id")
        user_content = (
            f"Pregunta: {state['question']}\n"
            f"Resultados (máx 20 filas): {summary_ctx}\n"
            f"Dataset primario: {schema.get('name', did)}\n"
            f"Dataset secundario: {partner_schema.get('name', partner_id)}\n"
            f"Filas encontradas: {len(rows)}\n"
            f"partial: {result.get('partial', False)}\n"
            f"Total de filas: {total_rows}\n"
        )
        if exact_values is not None:
            user_content += (
                f"VALORES EXACTOS calculados desde el resultado completo "
                f"(cópialos textualmente, NO los recalcules): "
                f"{json.dumps(exact_values, ensure_ascii=False, default=str)}\n"
            )
    else:
        user_content = (
            f"Pregunta: {state['question']}\n"
            f"Resultados (máx 20 filas): {summary_ctx}\n"
            f"Dataset: {schema.get('name', did)}\n"
            f"Total de filas: {total_rows}\n"
        )
        if exact_values is not None:
            user_content += (
                f"VALORES EXACTOS calculados desde el resultado completo "
                f"(cópialos textualmente, NO los recalcules): "
                f"{json.dumps(exact_values, ensure_ascii=False, default=str)}\n"
            )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    try:
        answer = llm_complete(messages)
    except Exception as exc:  # noqa: BLE001
        log.exception("answer LLM call failed: %s", exc)
        answer = f"Encontré {len(rows)} filas pero no pude redactar la respuesta. (detalle: {exc})"

    if result.get("partial"):
        answer = (
            f"⚠️ Resultado parcial: basado en las primeras {len(rows)} filas. "
            "La consulta completa excede el límite operativo; "
            "los números pueden estar subestimados.\n\n"
        ) + answer

    state["answer"] = answer

    if rows and len(rows[0]) >= 2 and any(_coerce_number(v) is not None for v in rows[0].values()):
        state["chart"] = T.make_chart(rows[:50], title=schema.get("name", ""))
    else:
        state["chart"] = None
    state["step"] = "answer"
    return state


def _normalize_key(value: object) -> str:
    """Lowercase + strip a join-key value for case-insensitive comparison."""
    if value is None:
        return ""
    s = str(value).strip().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def _parse_join_llm_response(raw: str) -> dict | None:
    """Extract the JSON block from the LLM join response.

    Tries to parse the whole response first, then falls back to extracting the
    first ``{...}`` block.  Returns ``None`` on failure.
    """
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _strip_limit_offset(soql: str) -> str:
    """Remove ``$limit`` and ``$offset`` parameters from a SoQL string."""
    parts = soql.split("&")
    filtered = [p for p in parts if not re.match(r"\s*\$(limit|offset)\s*=", p.strip())]
    return "&".join(filtered)


def _extract_where(soql: str) -> tuple[str, str]:
    """Split a SoQL into (remaining_without_where_or_pagination, where_expression).

    ``$limit`` / ``$offset`` are always stripped.  All ``$where`` fragments are
    collected and joined with ``AND`` so the caller can append additional filters.
    """
    parts = soql.split("&")
    where_exprs: list[str] = []
    remaining: list[str] = []
    for p in parts:
        stripped = p.strip()
        if stripped.startswith("$where="):
            where_exprs.append(stripped[len("$where=") :])
        elif not re.match(r"\s*\$(limit|offset)\s*=", stripped):
            remaining.append(p)
    return "&".join(remaining), " AND ".join(where_exprs)


def _ensure_selected_field(soql: str, field: str) -> str:
    """Ensure a simple field is present in ``$select`` without changing filters."""
    parts = soql.split("&")
    for index, part in enumerate(parts):
        if part.strip().lower().startswith("$select="):
            prefix, value = part.split("=", 1)
            selected = {item.strip() for item in value.split(",")}
            if field not in selected:
                parts[index] = f"{prefix}={value},{field}"
            return "&".join(parts)
    return f"$select={field}&{soql}" if soql else f"$select={field}"


def _build_join_messages(state: AgentState, *, correction: str | None = None) -> list[dict]:
    """Compose the messages asking the LLM to write (or fix) a join plan."""
    primary_id = state.get("dataset_id")
    partner_id = state.get("join_partner_id")
    primary_schema = state.get("schema") or {}
    partner_schema = state.get("partner_schema") or {}
    primary_col_text = _column_brief(primary_schema)
    partner_col_text = _column_brief(partner_schema)
    messages: list[dict] = [
        {"role": "system", "content": JOIN_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Pregunta: {state['question']}\n\n"
                f"Dataset PRIMARIO ({primary_id}):\n{primary_col_text}\n\n"
                f"Dataset SECUNDARIO ({partner_id}):\n{partner_col_text}"
            ),
        },
    ]
    if correction:
        messages.append(
            {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "primary_soql": state.get("soql", ""),
                        "partner_soql": state.get("partner_soql", ""),
                        "join_key_primary": state.get("join_key_primary", ""),
                        "join_key_partner": state.get("join_key_partner", ""),
                    }
                ),
            }
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Esa consulta falló con este error: {correction}\n"
                    "Corregila. Devuelve SOLO el JSON corregido."
                ),
            }
        )
    return messages


def join_generate_node(state: AgentState) -> AgentState:
    """LLM call only: produce the two SoQLs and join-key column names.

    On retry the previous error is fed back into the prompt so the LLM can
    repair the broken clause.  Does NOT execute any query — that is the job of
    ``join_execute_node``.
    """
    primary_id = state.get("dataset_id")
    partner_id = state.get("join_partner_id")
    if not primary_id or not partner_id:
        state["query_result"] = {
            "rows": [],
            "count": 0,
            "error": "join_missing_dataset_ids",
            "partial": False,
        }
        state["step"] = "join_generate"
        return state

    primary_schema = T.get_schema(primary_id)
    partner_schema = T.get_schema(partner_id)
    state["schema"] = primary_schema
    state["partner_schema"] = partner_schema

    correction = None
    prev_result = state.get("query_result") or {}
    if prev_result.get("error") and state.get("soql"):
        correction = prev_result["error"]

    messages = _build_join_messages(state, correction=correction)
    raw = ""
    try:
        raw = llm_complete_small(messages, temperature=0)
        parsed = _parse_join_llm_response(raw)
    except Exception as exc:  # noqa: BLE001
        log.exception("join_generate LLM call failed: %s", exc)
        parsed = None

    if not parsed or not all(
        k in parsed
        for k in ("primary_soql", "partner_soql", "join_key_primary", "join_key_partner")
    ):
        log.warning("join_generate LLM parse failed, raw=%r", raw)
        state["query_result"] = {
            "rows": [],
            "count": 0,
            "error": "join_llm_parse_failed",
            "partial": False,
        }
        state["partner_query_result"] = {
            "rows": [],
            "count": 0,
            "error": "join_llm_parse_failed",
        }
        state["step"] = "join_generate"
        return state

    join_key_primary = str(parsed["join_key_primary"]).strip()
    join_key_partner = str(parsed["join_key_partner"]).strip()
    primary_fields = {
        str(c.get("field_name", "")) for c in (primary_schema or {}).get("columns", [])
    }
    partner_fields = {
        str(c.get("field_name", "")) for c in (partner_schema or {}).get("columns", [])
    }
    identifier_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    validation_error = None
    if not primary_schema or not partner_schema:
        validation_error = "no se pudo cargar uno de los esquemas"
    elif not identifier_re.fullmatch(join_key_primary) or join_key_primary not in primary_fields:
        validation_error = f"llave primaria desconocida: {join_key_primary!r}"
    elif not identifier_re.fullmatch(join_key_partner) or join_key_partner not in partner_fields:
        validation_error = f"llave secundaria desconocida: {join_key_partner!r}"

    partner_soql = _clean_soql(str(parsed["partner_soql"]))
    partner_validation_error = _validate_soql(partner_soql)
    if validation_error is None and partner_validation_error:
        validation_error = f"consulta secundaria inválida: {partner_validation_error}"
    if validation_error is None:
        partner_soql = _ensure_selected_field(partner_soql, join_key_partner)

    # The primary side only needs the join key. Compose it deterministically so
    # plain SQL or extra filters from the LLM can never trigger a network retry.
    primary_soql = (
        f"$select={join_key_primary}&$where={join_key_primary} is not null&$limit=50000"
        if identifier_re.fullmatch(join_key_primary)
        else ""
    )

    state["soql"] = primary_soql
    state["partner_soql"] = partner_soql
    state["join_key_primary"] = join_key_primary
    state["join_key_partner"] = join_key_partner
    if validation_error:
        state["query_result"] = {
            "rows": [],
            "count": 0,
            "error": f"join_validation_error: {validation_error}",
            "partial": False,
        }
        state["partner_query_result"] = {
            "rows": [],
            "count": 0,
            "error": f"join_validation_error: {validation_error}",
        }
        state["step"] = "join_generate"
        return state

    state["query_result"] = None
    state["step"] = "join_generate"
    return state


def join_execute_node(state: AgentState) -> AgentState:
    """Paginate the primary dataset, then batch-filter the partner server-side.

    Primary pagination uses ``$limit=50000`` / ``$offset`` and stops at the first
    page that returns fewer rows (or at the 50 000-row hard cap, whichever comes
    first).  The partner dataset is queried in batches of 100 primary keys via a
    pushdown ``$where=<key> in (...)`` filter so the merge becomes "all partner
    rows collected across batches" — no client-side intersection needed.
    """
    primary_id = state.get("dataset_id")
    partner_id = state.get("join_partner_id")
    primary_soql = state.get("soql") or ""
    partner_soql = state.get("partner_soql") or ""
    join_key_primary = state.get("join_key_primary") or ""
    join_key_partner = state.get("join_key_partner") or ""

    existing_error = (state.get("query_result") or {}).get("error")
    if existing_error and str(existing_error).startswith("join_validation_error:"):
        state["step"] = "join_execute"
        return state

    if (
        not primary_id
        or not partner_id
        or not primary_soql
        or not join_key_primary
        or not join_key_partner
    ):
        state["query_result"] = {
            "rows": [],
            "count": 0,
            "error": "join_missing_query_params",
            "partial": False,
        }
        state["step"] = "join_execute"
        return state

    base_primary_soql = _strip_limit_offset(primary_soql)

    primary_rows: list[dict] = []
    partial = False
    offset = 0

    while len(primary_rows) < _SOQL_HARD_LIMIT:
        page_soql = (
            f"{base_primary_soql}&$limit={_SOQL_HARD_LIMIT}&$offset={offset}"
            if base_primary_soql
            else f"$limit={_SOQL_HARD_LIMIT}&$offset={offset}"
        )
        try:
            page_result = T.query_dataset(primary_id, page_soql)
        except Exception as exc:  # noqa: BLE001
            state["query_result"] = {
                "rows": [],
                "count": 0,
                "error": f"join_primary_error: {exc}",
                "partial": False,
            }
            state["step"] = "join_execute"
            return state

        if page_result.get("error"):
            state["query_result"] = {
                "rows": [],
                "count": 0,
                "error": f"join_primary_error: {page_result['error']}",
                "partial": False,
            }
            state["step"] = "join_execute"
            return state

        page_rows = page_result.get("rows") or []
        primary_rows.extend(page_rows)

        if len(page_rows) < _SOQL_HARD_LIMIT:
            break

        offset += _SOQL_HARD_LIMIT
        if len(primary_rows) >= _SOQL_HARD_LIMIT:
            partial = True
            break

    primary_rows = primary_rows[:_SOQL_HARD_LIMIT]

    seen_keys: set[str] = set()
    query_keys: list[str] = []
    seen_query_keys: set[str] = set()
    for row in primary_rows:
        raw_key = str(row.get(join_key_primary) or "").strip()
        normalized_key = _normalize_key(raw_key)
        if not normalized_key:
            continue
        seen_keys.add(normalized_key)
        # Query both representations. Otherwise a punctuated primary NIT could
        # miss an unpunctuated partner NIT (or vice versa) before client filtering.
        for candidate in (raw_key, normalized_key):
            if candidate and candidate not in seen_query_keys:
                seen_query_keys.add(candidate)
                query_keys.append(candidate)

    if not query_keys:
        state["query_result"] = {
            "rows": [],
            "count": 0,
            "error": None,
            "partial": partial,
        }
        state["partner_query_result"] = {"rows": [], "count": 0, "error": None}
        state["step"] = "join_execute"
        return state

    base_partner_soql, existing_where = _extract_where(partner_soql)
    partner_rows: list[dict] = []
    batch_size = 50

    for i in range(0, len(query_keys), batch_size):
        batch_keys = query_keys[i : i + batch_size]
        keys_literal = ",".join(f"'{k.replace(chr(39), chr(39) * 2)}'" for k in batch_keys)
        key_filter = f"{join_key_partner} in ({keys_literal})"
        combined_where = f"({existing_where}) AND ({key_filter})" if existing_where else key_filter
        if base_partner_soql:
            batch_soql = f"{base_partner_soql}&$where={combined_where}&$limit={_SOQL_HARD_LIMIT}"
        else:
            batch_soql = f"$where={combined_where}&$limit={_SOQL_HARD_LIMIT}"

        try:
            batch_result = T.query_dataset(partner_id, batch_soql)
        except Exception as exc:  # noqa: BLE001
            state["query_result"] = {
                "rows": [],
                "count": 0,
                "error": f"join_partner_error: {exc}",
                "partial": partial,
            }
            state["step"] = "join_execute"
            return state

        if batch_result.get("error"):
            state["query_result"] = {
                "rows": [],
                "count": 0,
                "error": f"join_partner_error: {batch_result['error']}",
                "partial": partial,
            }
            state["step"] = "join_execute"
            return state

        batch_rows = batch_result.get("rows") or []
        partner_rows.extend(batch_rows)

        if len(batch_rows) >= _SOQL_HARD_LIMIT:
            partial = True

    # Authoritative client-side re-filter: the server-side `in (...)` pushdown is
    # a coarse filter; NIT/document formatting differs across datasets, so the
    # real membership check must run on normalized keys.
    partner_rows = [r for r in partner_rows if _normalize_key(r.get(join_key_partner)) in seen_keys]

    state["partner_query_result"] = {
        "rows": partner_rows,
        "count": len(partner_rows),
        "error": None,
    }
    state["query_result"] = {
        "rows": partner_rows,
        "count": len(partner_rows),
        "error": None,
        "partial": partial,
    }
    state["step"] = "join_execute"
    return state


def join_check_node(state: AgentState) -> AgentState:
    """Bump ``retry_count`` when the join pipeline produced a fixable error."""
    result = state.get("query_result") or {}
    if result.get("error"):
        state["retry_count"] = state.get("retry_count", 0) + 1
    state["step"] = "join_check"
    return state


def join_query_node(state: AgentState) -> AgentState:
    """Backward-compatible wrapper: generate + execute in one call.

    Kept so existing callers (and tests) that invoke ``join_query_node`` directly
    still work.  The graph itself uses the split nodes.
    """
    state = join_generate_node(state)
    qr = state.get("query_result") or {}
    if qr.get("error"):
        return state
    state = join_execute_node(state)
    return state


# --- Routing ---------------------------------------------------------------


def route_after_triage(state: AgentState) -> str:
    """Route chitchat/meta questions to the canned answer, else into search."""
    if state.get("needs_clarification"):
        return "clarification_answer"
    if state.get("is_chitchat"):
        return "chitchat_answer"
    return "search"


def route_after_search(state: AgentState) -> str:
    """Route to ``join_generate`` for cross-dataset joins, else ``schema``."""
    if state.get("is_join_question") and state.get("join_partner_id"):
        return "join_generate"
    return "schema"


def route_after_check(state: AgentState) -> str:
    """On a fixable SoQL error (within retry budget) go to generate_soql; else answer.

    If no dataset was chosen there is nothing to correct, so we go straight to the
    answer node. ``retry_count`` was incremented in ``check_result_node`` and the
    guard ``retry_count <= MAX_RETRIES`` admits exactly ``MAX_RETRIES`` regenerations.
    """
    if not state.get("dataset_id"):
        return "answer"
    result = state.get("query_result") or {}
    error = result.get("error")
    retry = state.get("retry_count", 0)
    if error and retry <= MAX_RETRIES:
        return "generate_soql"
    return "answer"


def route_after_join_check(state: AgentState) -> str:
    """On a fixable join error (within retry budget) retry ``join_generate``; else answer."""
    if not state.get("dataset_id"):
        return "answer"
    result = state.get("query_result") or {}
    error = result.get("error")
    retry = state.get("retry_count", 0)
    if error and retry <= MAX_RETRIES:
        return "join_generate"
    return "answer"


# --- Question cache ---------------------------------------------------------

# Simple in-memory cache: question -> final AgentState.
# Bounded to _CACHE_MAX entries (FIFO eviction).
_CACHE_MAX = 100
_question_cache: dict[str, AgentState] = {}


# --- Build the graph -------------------------------------------------------


@lru_cache(maxsize=1)
def build_agent():
    """Construct and compile the LangGraph agent state graph (cached)."""
    g = StateGraph(AgentState)
    g.add_node("triage", triage_node)
    g.add_node("chitchat_answer", chitchat_answer_node)
    g.add_node("clarification_answer", clarification_answer_node)
    g.add_node("search", search_node)
    g.add_node("schema", schema_node)
    g.add_node("relevance_gate", relevance_gate_node)
    g.add_node("generate_soql", generate_soql_node)
    g.add_node("execute_query", execute_query_node)
    g.add_node("check_result", check_result_node)
    g.add_node("join_generate", join_generate_node)
    g.add_node("join_execute", join_execute_node)
    g.add_node("join_check", join_check_node)
    g.add_node("answer", answer_node)

    g.set_entry_point("triage")
    g.add_conditional_edges(
        "triage",
        route_after_triage,
        {
            "clarification_answer": "clarification_answer",
            "chitchat_answer": "chitchat_answer",
            "search": "search",
        },
    )
    g.add_edge("chitchat_answer", END)
    g.add_edge("clarification_answer", END)
    g.add_conditional_edges(
        "search",
        route_after_search,
        {"schema": "schema", "join_generate": "join_generate"},
    )
    g.add_edge("schema", "relevance_gate")
    g.add_edge("relevance_gate", "generate_soql")
    g.add_edge("generate_soql", "execute_query")
    g.add_edge("execute_query", "check_result")
    g.add_conditional_edges(
        "check_result",
        route_after_check,
        {"generate_soql": "generate_soql", "answer": "answer"},
    )
    g.add_edge("join_generate", "join_execute")
    g.add_edge("join_execute", "join_check")
    g.add_conditional_edges(
        "join_check",
        route_after_join_check,
        {"join_generate": "join_generate", "answer": "answer"},
    )
    g.add_edge("answer", END)
    return g.compile()


def run_agent(question: str) -> AgentState:
    """Run the full agent on a user question and return the final state.

    Returns the full AgentState dict: answer, chart, sources, soql, dataset_id,
    datasets, retry_count, and step.

    Results are cached in memory: if the exact same question was asked before,
    the cached state is returned instantly without re-running the agent.
    """
    # Check cache first
    cached = _question_cache.get(question)
    if cached is not None:
        log.info("Cache hit for question: %s", question[:60])
        return cached

    agent = build_agent()
    initial_state: AgentState = {
        "question": question,
        "datasets": [],
        "dataset_id": None,
        "schema": None,
        "soql": None,
        "query_result": None,
        "retry_count": 0,
        "answer": None,
        "chart": None,
        "sources": [],
        "step": "search",
        "is_join_question": False,
        "join_partner_id": None,
        "join_key_primary": None,
        "join_key_partner": None,
        "partner_schema": None,
        "partner_soql": None,
        "partner_query_result": None,
        "is_chitchat": False,
        "chitchat_answer_text": "",
        "needs_clarification": False,
        "clarification_question": "",
    }
    result = agent.invoke(initial_state)

    # Store in cache (FIFO eviction when full)
    if len(_question_cache) >= _CACHE_MAX:
        oldest_key = next(iter(_question_cache))
        del _question_cache[oldest_key]
    _question_cache[question] = result  # type: ignore[assignment]

    return result  # type: ignore[return-value]
