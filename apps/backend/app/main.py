"""FastAPI application: health, chat (SSE stream), and a direct SoQL proxy."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.socrata.client import SocrataClient

# Wire root logger from LOG_LEVEL env var (falls back to settings.log_level).
# Only configure if no handlers exist yet (avoids overriding uvicorn's config).
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", settings.log_level).upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

log = logging.getLogger("manglar.api")

_STEP_LABELS = {
    "search": "Buscando datasets relevantes en datos.gov.co...",
    "schema": "Analizando el esquema del dataset seleccionado...",
    "generate_soql": "Generando la consulta SoQL...",
    "execute_query": "Ejecutando la consulta en datos.gov.co...",
    "check_result": "Validando el resultado de la consulta...",
    "answer": "Redactando la respuesta final...",
}

app = FastAPI(title="Manglar", version="0.1.0")

_cors_origins = settings.cors_origins_list
if not _cors_origins:
    log.warning("CORS_ORIGINS is empty — allowing all origins WITHOUT credentials (demo mode)")
    _cors_origins = ["*"]
else:
    log.info("CORS allow-list: %s", _cors_origins)

_cors_allow_credentials: bool = bool(_cors_origins and _cors_origins != ["*"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request models ---------------------------------------------------------


class ChatMessage(BaseModel):
    """A single chat message in the OpenAI-style role/content schema."""

    role: str = "user"
    content: str = ""


class ChatRequest(BaseModel):
    """Payload accepted by POST /chat."""

    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = True


# --- Helpers ----------------------------------------------------------------


def _sse(event: dict) -> str:
    """Serialize one SSE data line (``data: {json}\\n\\n``)."""
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def _extract_question(body: dict) -> str:
    """Pull the content of the last user message out of the raw request body."""
    messages = body.get("messages", [])
    if not messages:
        return ""
    last = messages[-1]
    if isinstance(last, dict):
        return last.get("content", "")
    return str(last)


async def _run_agent_async(question: str) -> dict:
    """Run the sync agent in a worker thread so the event loop stays free."""
    from app.agents.graph import run_agent

    return await asyncio.to_thread(run_agent, question)


@lru_cache(maxsize=1)
def _proxy_socrata() -> SocrataClient:
    """Shared SocrataClient singleton for the /api/query proxy."""
    return SocrataClient(settings.socrata_domain, settings.socrata_app_token)


def _emit_result_events(state: dict) -> list[str]:
    """Yield SSE events for query/answer/chart/sources from final state."""
    events: list[str] = []
    soql = state.get("soql") or ""
    dataset_id = state.get("dataset_id") or ""
    if dataset_id:
        events.append(_sse({"type": "query", "content": soql, "dataset": dataset_id}))
    answer = state.get("answer") or "Sin respuesta."
    events.append(_sse({"type": "answer", "content": answer}))
    chart = state.get("chart")
    if chart:
        events.append(_sse({"type": "chart", "content": chart}))
    sources = state.get("sources") or []
    events.append(_sse({"type": "sources", "content": sources}))
    return events


# --- Health ----------------------------------------------------------------

_START_TIME = time.time()
_HEALTH_CACHE_TTL = 10  # seconds
_health_cache: tuple[float, dict] = (0, {})


def _supabase_health() -> str:
    """Ping Supabase with a minimal query. Returns 'ok', 'fail', or 'timeout'."""
    if not settings.supabase_url or not settings.supabase_key_resolved:
        return "fail"
    try:
        from supabase import create_client

        sb = create_client(settings.supabase_url, settings.supabase_key_resolved)
        sb.table("catalog").select("id").limit(1).execute()
        return "ok"
    except TimeoutError:
        return "timeout"
    except Exception:
        return "fail"


def _compute_health() -> dict:
    """Run live checks and return the health envelope."""
    sb_status = _supabase_health()
    overall = "ok" if sb_status == "ok" else "degraded"
    return {
        "status": overall,
        "checks": {"supabase": sb_status},
        "uptime_s": int(time.time() - _START_TIME),
    }


@app.get("/health")
def health() -> dict:
    """Liveness + readiness probe. Always returns HTTP 200.

    Caches the result for 10 seconds to avoid hammering Supabase on every probe.
    ``status`` is ``"ok"`` only if Supabase is reachable; ``"degraded"`` otherwise.
    """
    global _health_cache
    now = time.time()
    cached_at, cached_body = _health_cache
    if now - cached_at < _HEALTH_CACHE_TTL and cached_body:
        return cached_body
    body = _compute_health()
    _health_cache = (now, body)
    return body


# --- Chat (SSE) -------------------------------------------------------------


@app.post("/chat", response_model=None)
async def chat(request: Request) -> StreamingResponse | JSONResponse:
    """Accept ``{messages, stream?}`` and return an SSE stream or JSON body.

    SSE event types (each line ``data: {json}\\n\\n``):
      - ``thinking``  status/progress updates
      - ``query``     the SoQL the agent ran + dataset id
      - ``answer``    the final Spanish answer text
      - ``chart``     a Vega-Lite spec (omitted if none)
      - ``sources``   list of {name, permalink, soql}
      - ``[DONE]``    terminal marker

    When ``stream`` is ``false`` a single JSON object with the same fields is
    returned instead of a text/event-stream response.
    """
    body = await request.json()
    question = _extract_question(body)
    stream = bool(body.get("stream", True))

    if not question:
        err = {"type": "error", "content": "No se recibió ninguna pregunta."}
        if stream:
            return StreamingResponse(
                iter((_sse(err), "data: [DONE]\n\n")),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        return JSONResponse({"error": err["content"]}, status_code=400)

    if not stream:
        try:
            result = await _run_agent_async(question)
        except Exception as exc:  # noqa: BLE001
            log.exception("agent run failed: %s", exc)
            return JSONResponse({"error": f"Error interno: {exc}"}, status_code=500)
        return JSONResponse(_build_json_result(result))

    async def event_stream():
        from queue import Queue

        from app.agents.graph import _CACHE_MAX, _question_cache, build_agent

        yield _sse({"type": "thinking", "content": _STEP_LABELS["search"]})
        await asyncio.sleep(0.05)

        seen: set[str] = {"search"}  # search label already emitted above

        # Cache: replay instantly
        cached = _question_cache.get(question)
        if cached is not None:
            log.info("Cache hit for question: %s", question[:60])
            for ev in _emit_result_events(cached):
                yield ev
            yield "data: [DONE]\n\n"
            return

        agent = build_agent()
        initial_state: dict = {
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
        }

        import threading

        q: Queue = Queue()
        _SENTINEL = object()

        def worker():
            try:
                for chunk in agent.stream(initial_state, stream_mode="updates"):
                    q.put(chunk)
            except Exception as exc:  # noqa: BLE001
                q.put(exc)
            q.put(_SENTINEL)

        threading.Thread(target=worker, daemon=True).start()
        loop = asyncio.get_event_loop()
        final_state = None
        while True:
            item = await loop.run_in_executor(None, q.get)
            if item is _SENTINEL:
                break
            if isinstance(item, Exception):
                log.exception("agent stream failed: %s", item)
                yield _sse({"type": "error", "content": f"Error interno: {item}"})
                yield "data: [DONE]\n\n"
                return
            # chunk is {node_name: state}
            for node_name, state in item.items():
                if node_name in seen:
                    continue
                seen.add(node_name)
                label = _STEP_LABELS.get(node_name)
                if label:
                    yield _sse({"type": "thinking", "content": label})
                if node_name in ("answer", "chitchat_answer"):
                    final_state = state
            await asyncio.sleep(0)  # yield to event loop so SSE flushes

        if final_state is None:
            yield _sse({"type": "error", "content": "El agente no completó el flujo."})
            yield "data: [DONE]\n\n"
            return

        # Cache and emit results
        if len(_question_cache) >= _CACHE_MAX:
            oldest = next(iter(_question_cache))
            del _question_cache[oldest]
        _question_cache[question] = final_state
        for ev in _emit_result_events(final_state):
            yield ev
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _build_json_result(result: dict) -> dict:
    """Shape the agent state dict into the non-streaming JSON response."""
    return {
        "query": result.get("soql") or "",
        "dataset": result.get("dataset_id") or "",
        "answer": result.get("answer") or "Sin respuesta.",
        "chart": result.get("chart") or None,
        "sources": result.get("sources") or [],
    }


# --- Direct SoQL proxy -----------------------------------------------------


@app.get("/api/query")
def api_query(
    dataset_id: str = Query(..., alias="dataset_id"),
    soql: str = Query("", alias="soql"),
) -> Any:
    """Direct SoQL proxy for the "Ver consulta" button / debugging.

    Returns the raw JSON row array from Socrata (or a 502 error envelope).
    """
    client = _proxy_socrata()
    try:
        rows = client.query(dataset_id, soql)
        return JSONResponse(rows)
    except Exception as exc:  # noqa: BLE001
        log.exception("api_query %s failed: %s", dataset_id, exc)
        return JSONResponse({"error": str(exc)}, status_code=502)
