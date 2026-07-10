"""LangGraph agent: search -> schema -> query -> self-correct -> answer.

State machine nodes: plan, search, schema, query, error_correct, answer.
On a SoQL error we feed the error back into the planner and retry up to 2 times.
The final answer carries citations (dataset name + permalink + SoQL) and, when the
result is tabular, a Vega-Lite chart.

The LLM call is isolated in `llm_complete(messages)` so the wiring is real even if
you swap providers via LiteLLM.
"""
from __future__ import annotations

import json
from typing import Any

from langgraph.graph import StateGraph, END

from app.agents.few_shots import load_patterns
from app.agents import tools as T
from app.config import settings

MAX_RETRIES = 2

# --- LLM helper -----------------------------------------------------------


def llm_complete(messages: list[dict], *, temperature: float = 0.2, json_mode: bool = False) -> str:
    """Provider-agnostic completion via LiteLLM.

    All provider routing is controlled by LITELLM_MODEL / LITELLM_API_BASE in config.
    Returns the assistant message content as a string.
    """
    import litellm

    kwargs: dict[str, Any] = {"model": settings.litellm_model, "messages": messages, "temperature": temperature}
    if settings.litellm_api_base:
        kwargs["api_base"] = settings.litellm_api_base
    key = settings.litellm_api_key_resolved
    if key:
        kwargs["api_key"] = key
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = litellm.completion(**kwargs)
    return resp["choices"][0]["message"]["content"]  # type: ignore[index]


def _assistant(content: str) -> dict:
    return {"role": "assistant", "content": content}


# --- State -----------------------------------------------------------------

class AgentState(dict):  # type: ignore[misc]
    """Mutable state passed between graph nodes.

    Keys: question, plan, dataset_id, schema, soql, rows, error, retries,
    answer, citations, chart.
    """


# --- Nodes ----------------------------------------------------------------

SYSTEM_PROMPT = (
    "Sos DATIA, un asistente de datos abiertos de Colombia (datos.gov.co). "
    "Respondes en español. Para responder una pregunta: 1) encontrá el dataset "
    "correcto con search_catalog, 2) mirá su esquema con get_schema, 3) escribí "
    "una consulta SoQL y ejecutala con query_dataset, 4) si hay error, corregí "
    "la consulta (máximo 2 intentos), 5) respondé con la cifra, una cita "
    "(nombre del dataset + permalink + SoQL) y, si es tabular, un chart."
)


def plan_node(state: AgentState) -> AgentState:
    """Decide which dataset(s) to use and what to look up."""
    few_shots = "\n".join(
        f"- Q: {p['user_question']}\n  SoQL: {p['soql']}" for p in load_patterns()
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Ejemplos SoQL:\n{few_shots}"},
        {"role": "user", "content": state["question"]},
        {"role": "user", "content": "Devuelve SOLO JSON: {\"search_query\": str, \"sector\": str|null}."},
    ]
    raw = llm_complete(messages, json_mode=True)
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError:
        plan = {"search_query": state["question"], "sector": None}
    state["plan"] = plan
    state.setdefault("retries", 0)
    return state


def search_node(state: AgentState) -> AgentState:
    """Find candidate datasets via catalog RAG."""
    plan = state.get("plan") or {}
    results = T.search_catalog_tool(plan.get("search_query", state["question"]), sector=plan.get("sector"))
    state["search_results"] = results
    if results and not state.get("dataset_id"):
        state["dataset_id"] = results[0]["id"]
    return state


def schema_node(state: AgentState) -> AgentState:
    """Pull the schema for the chosen dataset."""
    did = state.get("dataset_id")
    if not did:
        return state
    schema = T.get_schema(did)
    state["schema"] = schema
    return state


def query_node(state: AgentState) -> AgentState:
    """Ask the LLM to write a SoQL query for the current dataset, then run it."""
    did = state.get("dataset_id")
    schema = state.get("schema") or {}
    cols = schema.get("columns", [])
    col_text = ", ".join(f"{c.get('field_name','')}: {c.get('datatype','')}" for c in cols)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Dataset id: {did}\nColumnas: {col_text}\nPregunta: {state['question']}"},
        {"role": "user", "content": "Escribí SOLO el SoQL (sin explicar). Empezá con $. Ej: $select=count(*)"},
    ]
    soql = llm_complete(messages, temperature=0.0).strip().strip("`")
    if soql.startswith("SoQL"):
        soql = soql.split("\n", 1)[-1].strip()
    state["soql"] = soql
    try:
        rows = T.query_dataset(did, soql)
        state["rows"] = rows
        state["error"] = None
    except Exception as exc:  # noqa: BLE001
        state["rows"] = []
        state["error"] = str(exc)
    return state


def error_correct_node(state: AgentState) -> AgentState:
    """Feed the SoQL error back and ask for a corrected query (bounded retries)."""
    state["retries"] = state.get("retries", 0) + 1
    if state["retries"] > MAX_RETRIES:
        state["error"] = state.get("error") or "demasiados intentos"
        return state
    did = state.get("dataset_id")
    schema = state.get("schema") or {}
    col_text = ", ".join(c.get("field_name", "") for c in schema.get("columns", []))
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Dataset id: {did}\nColumnas: {col_text}\nPregunta: {state['question']}"},
        {"role": "assistant", "content": state.get("soql", "")},
        {"role": "user", "content": f"Esa consulta falló con: {state['error']}\nCorregila. Devolvé SOLO el SoQL."},
    ]
    soql = llm_complete(messages, temperature=0.0).strip().strip("`")
    state["soql"] = soql
    try:
        rows = T.query_dataset(did, soql)
        state["rows"] = rows
        state["error"] = None
    except Exception as exc:  # noqa: BLE001
        state["rows"] = []
        state["error"] = str(exc)
    return state


def answer_node(state: AgentState) -> AgentState:
    """Compose the final answer with citations + optional Vega-Lite chart."""
    did = state.get("dataset_id")
    rows = state.get("rows") or []
    soql = state.get("soql", "")
    schema = state.get("schema") or {}

    # citations
    permalink = schema.get("permalink") or f"https://{settings.socrata_domain}/d/{did}"
    state["citations"] = [
        {"dataset": schema.get("name", did), "permalink": permalink, "soql": soql}
    ]

    if state.get("error"):
        state["answer"] = f"No pude completar la consulta tras varios intentos. Error: {state['error']}"
        return state

    summary_ctx = json.dumps(rows[:20], ensure_ascii=False)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Pregunta: {state['question']}\nResultados (máx 20 filas): {summary_ctx}"},
        {"role": "user", "content": "Respondé en español de forma concisa con la cifra o hallazgo principal."},
    ]
    state["answer"] = llm_complete(messages)

    # Vega-Lite chart when the result looks tabular (>=2 cols, at least one numeric)
    if rows and len(rows[0]) >= 2:
        first = rows[0]
        numeric_field = next(
            (k for k, v in first.items() if isinstance(v, (int, float))), None
        )
        if numeric_field:
            x_field = next((k for k in first if k != numeric_field), None)
            if x_field:
                state["chart"] = T.make_chart(rows[:50], x=x_field, y=numeric_field)
    return state


# --- Routing ---------------------------------------------------------------

def route_after_query(state: AgentState) -> str:
    """Go to error-correct on failure, else to answer."""
    if state.get("error") and state.get("retries", 0) < MAX_RETRIES:
        return "error_correct"
    return "answer"


# --- Build the graph -------------------------------------------------------

def build_agent_graph():
    """Construct and compile the LangGraph agent."""
    g = StateGraph(AgentState)
    g.add_node("plan", plan_node)
    g.add_node("search", search_node)
    g.add_node("schema", schema_node)
    g.add_node("query", query_node)
    g.add_node("error_correct", error_correct_node)
    g.add_node("answer", answer_node)

    g.set_entry_point("plan")
    g.add_edge("plan", "search")
    g.add_edge("search", "schema")
    g.add_edge("schema", "query")
    g.add_conditional_edges(
        "query",
        route_after_query,
        {"error_correct": "error_correct", "answer": "answer"},
    )
    g.add_edge("error_correct", "answer")
    g.add_edge("answer", END)
    return g.compile()


def run_agent(question: str) -> dict:
    """Run the full agent on a user question and return the final state."""
    graph = build_agent_graph()
    result = graph.invoke(AgentState(question=question))
    return {
        "answer": result.get("answer"),
        "citations": result.get("citations", []),
        "chart": result.get("chart"),
        "soql": result.get("soql"),
        "dataset_id": result.get("dataset_id"),
    }
