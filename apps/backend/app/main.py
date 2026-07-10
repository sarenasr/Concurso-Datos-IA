"""FastAPI application: health, chat (SSE stream), and a direct SoQL proxy."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from app.config import settings
from app.socrata.client import SocrataClient

app = FastAPI(title="DATIA", version="0.1.0")

# CORS open for the frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "datia"}


@app.post("/chat")
async def chat(request: Request) -> StreamingResponse:
    """Accept {messages, stream?} and return an SSE stream.

    For now this streams a stub while wiring the real agent in `run_agent`.
    Each SSE event is `data: {json}\n\n`; the final event has `event: done`.
    """
    body = await request.json()
    messages = body.get("messages", [])
    question = ""
    if messages:
        last = messages[-1]
        question = last.get("content", "") if isinstance(last, dict) else str(last)

    async def event_stream():
        # Stream placeholder tokens so the frontend can wire up immediately.
        yield f"data: {json.dumps({'delta': 'Pensando... '}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.1)
        try:
            from app.agents.graph import run_agent

            result = run_agent(question)
            payload = {
                "answer": result.get("answer") or "Sin respuesta.",
                "citations": result.get("citations", []),
                "chart": result.get("chart"),
                "soql": result.get("soql"),
                "dataset_id": result.get("dataset_id"),
            }
            yield f"data: {json.dumps({'delta': payload['answer']}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'final': payload}, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/query")
def api_query(
    dataset_id: str = Query(..., alias="dataset_id"),
    soql: str = Query("", alias="soql"),
) -> Any:
    """Direct SoQL proxy for the "Ver consulta" button / debugging."""
    client = SocrataClient(settings.socrata_domain, settings.socrata_app_token)
    try:
        rows = client.query(dataset_id, soql)
        return JSONResponse(rows)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=502)


@app.get("/setwebhook")
async def set_webhook(request: Request) -> dict:
    """Register the Telegram webhook with Telegram once deployed."""
    base = str(request.base_url)
    from app.channels.telegram_bot import set_webhook as tg_set_webhook

    return await tg_set_webhook(base)


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict:
    """Inbound Telegram webhook."""
    from app.channels.telegram_bot import telegram_webhook as tg_handle

    update = await request.json()
    return await tg_handle(update)
