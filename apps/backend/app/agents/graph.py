"""LangGraph agent: search -> schema -> generate_soql -> exhaust_self_correct -> answer.

State machine nodes: search, schema, generate_soql, execute_query, check_result,
answer. On a SoQL error the agent regenerates the query up to ``MAX_RETRIES``
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
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.agents import few_shots
from app.agents import tools as T
from app.config import settings

log = logging.getLogger("datia.agent")

MAX_RETRIES = 2


# --- LLM helper -----------------------------------------------------------


def llm_complete(messages: list[dict], temperature: float = 0) -> str:
    """Provider-agnostic completion via LiteLLM.

    Returns the assistant message content as a string.
    """
    import litellm

    model = settings.litellm_model
    kwargs: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "timeout": 30,
    }
    if settings.litellm_api_base:
        if not model.startswith("openai/"):
            model = f"openai/{model}"
        kwargs["api_base"] = settings.litellm_api_base
    key = settings.litellm_api_key_resolved
    if key:
        kwargs["api_key"] = key
    resp = litellm.completion(model=model, **kwargs)
    return resp["choices"][0]["message"]["content"]  # type: ignore[index]


# --- Prompts ---------------------------------------------------------------

SOQL_SYSTEM_PROMPT = (
    "Eres un generador de consultas SoQL para Socrata (datos.gov.co).\n"
    "Recibes una pregunta en español y el esquema de un dataset.\n"
    "Generas SÓLO la consulta SoQL (la parte después de ? en la URL del recurso).\n"
    "No agregues explicaciones, solo el SoQL.\n\n"
    "Reglas importantes:\n"
    "- Usa field_name (snake_case) no el name de columna\n"
    "- Fechas en formato ISO: '2025-01-01T00:00:00.000'\n"
    "- Texto es case-sensitive: usa like 'MAYÚSCULAS' o in ('valor1','valor2')\n"
    "- $limit por defecto 1000, máximo 50000\n"
    "- Agregaciones: $select=campo, count(*)&$group=campo\n"
    "- Top N: $order=campo DESC&$limit=N"
)

ANSWER_SYSTEM_PROMPT = (
    "Eres DATIA, un asistente que explica datos de Colombia en español claro y simple.\n"
    "Recibes una pregunta, el resultado de una consulta SoQL, y los metadatos del dataset.\n"
    "Respondes en español, en máximo 3 párrafos, con el dato principal primero.\n"
    "Menciona el dataset por nombre e incluye el número exacto si aplica."
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


# --- Helpers ---------------------------------------------------------------


def _column_brief(schema: dict | None) -> str:
    """Build a compact `field_name (datatype): name` listing for the LLM."""
    if not schema:
        return ""
    cols = schema.get("columns", []) or []
    return "\n".join(
        f"- {c.get('field_name', '')} ({c.get('datatype', '')}): {c.get('name', '')}" for c in cols
    )


def _few_shots_text() -> str:
    return "\n".join(
        f"- Q: {p['user_question']}\n  SoQL: {p['soql']}" for p in few_shots.load_patterns()
    )


def _clean_soql(raw: str) -> str:
    """Strip markdown fences / leading labels from an LLM SoQL response."""
    soql = raw.strip().strip("`")
    if soql.lower().startswith("soql"):
        soql = soql.split("\n", 1)[-1].strip()
    if soql.startswith("```"):
        soql = "\n".join(soql.splitlines()[1:])
        soql = soql.rsplit("```", 1)[0]
    return soql.strip().strip("`").strip()


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# --- Nodes ---------------------------------------------------------------


def search_node(state: AgentState) -> AgentState:
    """Find candidate datasets via catalog RAG and pick the best one."""
    results = T.search_catalog(state["question"])
    state["datasets"] = results
    state["step"] = "search"
    if results and not state.get("dataset_id"):
        state["dataset_id"] = results[0].get("id")
    return state


def schema_node(state: AgentState) -> AgentState:
    """Pull the schema for the chosen dataset from the registry."""
    did = state.get("dataset_id")
    state["schema"] = T.get_schema(did) if did else None
    state["step"] = "schema"
    return state


def _build_soql_messages(state: AgentState, *, correction: str | None = None) -> list[dict]:
    """Compose the messages asking the LLM to write (or fix) a SoQL query."""
    did = state.get("dataset_id")
    schema = state.get("schema") or {}
    col_text = _column_brief(schema)
    few_shots_text = _few_shots_text()
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

    correction = None
    result = state.get("query_result")
    if result and result.get("error") and state.get("soql"):
        correction = result.get("error")

    messages = _build_soql_messages(state, correction=correction)
    try:
        soql = _clean_soql(llm_complete(messages, temperature=0))
    except Exception as exc:  # noqa: BLE001
        log.exception("generate_soql LLM call failed: %s", exc)
        soql = ""
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
    state["sources"] = [
        {"name": schema.get("name", did or ""), "permalink": permalink, "soql": soql}
    ]

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
    messages: list[dict] = [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Pregunta: {state['question']}\n"
                f"Resultados (máx 20 filas): {summary_ctx}\n"
                f"Dataset: {schema.get('name', did)}"
            ),
        },
    ]
    try:
        answer = llm_complete(messages)
    except Exception as exc:  # noqa: BLE001
        log.exception("answer LLM call failed: %s", exc)
        answer = f"Encontré {len(rows)} filas pero no pude redactar la respuesta. (detalle: {exc})"
    state["answer"] = answer

    if rows and len(rows[0]) >= 2 and any(_is_number(v) for v in rows[0].values()):
        state["chart"] = T.make_chart(rows[:50], title=schema.get("name", ""))
    else:
        state["chart"] = None
    state["step"] = "answer"
    return state


# --- Routing ---------------------------------------------------------------


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


# --- Build the graph -------------------------------------------------------


def build_agent():
    """Construct and compile the LangGraph agent state graph."""
    g = StateGraph(AgentState)
    g.add_node("search", search_node)
    g.add_node("schema", schema_node)
    g.add_node("generate_soql", generate_soql_node)
    g.add_node("execute_query", execute_query_node)
    g.add_node("check_result", check_result_node)
    g.add_node("answer", answer_node)

    g.set_entry_point("search")
    g.add_edge("search", "schema")
    g.add_edge("schema", "generate_soql")
    g.add_edge("generate_soql", "execute_query")
    g.add_edge("execute_query", "check_result")
    g.add_conditional_edges(
        "check_result",
        route_after_check,
        {"generate_soql": "generate_soql", "answer": "answer"},
    )
    g.add_edge("answer", END)
    return g.compile()


def run_agent(question: str) -> AgentState:
    """Run the full agent on a user question and return the final state.

    Returns the full AgentState dict: answer, chart, sources, soql, dataset_id,
    datasets, retry_count, and step.
    """
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
    }
    result = agent.invoke(initial_state)
    return result  # type: ignore[return-value]
