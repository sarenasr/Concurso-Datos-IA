"""FastAPI application: health, chat (SSE stream), and a direct SoQL proxy."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.socrata.client import SocrataClient

log = logging.getLogger("datia.api")

app = FastAPI(title="DATIA", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


# --- Health ----------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    """Report static service status (no live connection checks)."""
    return {"status": "ok", "agent": "ready", "supabase": "connected"}


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
        yield _sse(
            {"type": "thinking", "content": "Buscando datasets relevantes en datos.gov.co..."}
        )
        await asyncio.sleep(0.05)  # flush window so thinking arrives first
        try:
            result = await _run_agent_async(question)
        except Exception as exc:  # noqa: BLE001
            log.exception("agent run failed: %s", exc)
            yield _sse({"type": "error", "content": f"Error interno: {exc}"})
            yield "data: [DONE]\n\n"
            return

        soql = result.get("soql") or ""
        dataset_id = result.get("dataset_id") or ""
        if dataset_id:
            yield _sse({"type": "query", "content": soql, "dataset": dataset_id})

        answer = result.get("answer") or "Sin respuesta."
        yield _sse({"type": "answer", "content": answer})

        chart = result.get("chart")
        if chart:
            yield _sse({"type": "chart", "content": chart})

        sources = result.get("sources") or []
        yield _sse({"type": "sources", "content": sources})

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
    client = SocrataClient(settings.socrata_domain, settings.socrata_app_token)
    try:
        rows = client.query(dataset_id, soql)
        return JSONResponse(rows)
    except Exception as exc:  # noqa: BLE001
        log.warning("api_query %s failed: %s", dataset_id, exc)
        return JSONResponse({"error": str(exc)}, status_code=502)
