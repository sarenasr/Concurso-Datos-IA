"""Telegram polling bot for DATIA.

Run locally:
    uv run python -m app.channels.telegram_bot

On each text message the agent runs and the ``answer`` field is replied. Long
answers are split into <=4096-char chunks to respect the Telegram limit.
"""

from __future__ import annotations

import asyncio
import html
import logging

from app.config import settings

log = logging.getLogger("datia.telegram")

TELEGRAM_MAX_LEN = 4096
TYPING_INTERVAL = 4


def _split(text: str, limit: int = TELEGRAM_MAX_LEN) -> list[str]:
    """Split ``text`` into chunks no longer than ``limit`` (line-aware)."""
    chunks: list[str] = []
    for line in text.splitlines(keepends=True):
        if not chunks or len(chunks[-1]) + len(line) > limit:
            chunks.append(line)
        else:
            chunks[-1] += line
    return [c for c in chunks if c]


def _format_sources(sources: list[dict]) -> str:
    """Format source citations for Telegram display (HTML)."""
    if not sources:
        return ""
    lines = ["\n<b>Fuentes:</b>"]
    for src in sources:
        name = html.escape(src.get("name", "Dataset"))
        permalink = src.get("permalink", "")
        if permalink:
            lines.append(f'• <a href="{permalink}">{name}</a>')
        else:
            lines.append(f"• {name}")
    return "\n".join(lines)


def _format_chart_info(chart: dict | None) -> str:
    """Provide a text note when a chart was generated (HTML)."""
    if not chart:
        return ""
    return "\n<i>Se generó un gráfico con los datos. Consúltalo en la versión web de DATIA.</i>"


async def _send_typing_loop(context, chat_id: int, stop_event: asyncio.Event) -> None:
    """Send typing action periodically until stopped."""
    from telegram.constants import ChatAction

    while not stop_event.is_set():
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:  # noqa: BLE001
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TYPING_INTERVAL)
        except asyncio.TimeoutError:
            pass


async def _on_text(update, context) -> None:  # noqa: ANN001
    """Handle an inbound text message: run the agent, reply with the answer."""
    from app.agents.graph import run_agent

    text = update.message.text
    chat_id = update.effective_chat.id

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_send_typing_loop(context, chat_id, stop_typing))

    try:
        result = await asyncio.to_thread(run_agent, text)
        answer = result.get("answer") or "Sin respuesta."
        sources = result.get("sources") or []
        chart = result.get("chart")

        reply = html.escape(answer)
        chart_note = _format_chart_info(chart)
        if chart_note:
            reply += chart_note
        sources_text = _format_sources(sources)
        if sources_text:
            reply += sources_text
    except Exception as exc:  # noqa: BLE001
        log.exception("agent failed")
        reply = f"Lo siento, hubo un error: {html.escape(str(exc))}"
    finally:
        stop_typing.set()
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    for chunk in _split(reply):
        await update.message.reply_text(chunk, parse_mode="HTML")


def _build_app():
    """Build a configured python-telegram-bot Application."""
    from telegram.ext import Application, CommandHandler, MessageHandler, filters

    app = Application.builder().token(settings.telegram_bot_token).build()

    async def _start(update, context):  # noqa: ANN001
        await update.message.reply_text(
            "Hola, soy DATIA. Preguntame sobre los datos abiertos de Colombia.\n\n"
            "Escribe tu pregunta en lenguaje natural y buscaré los datos relevantes "
            "en datos.gov.co para responder.\n\n"
            "Usa /help para ver ejemplos."
        )

    async def _help(update, context):  # noqa: ANN001
        await update.message.reply_text(
            "<b>Ejemplos de preguntas:</b>\n\n"
            "• ¿Cuántos habitantes tiene Medellín?\n"
            "• ¿Cuál es el presupuesto del Ministerio de Educación?\n"
            "• ¿Cuántos casos de COVID hay en Bogotá?\n"
            "• ¿Cuántas instituciones educativas hay en Cali?\n\n"
            "Puedes preguntar sobre cualquier dato abierto disponible en datos.gov.co.",
            parse_mode="HTML",
        )

    app.add_handler(CommandHandler("start", _start))
    app.add_handler(CommandHandler("help", _help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text))
    return app


def start_bot() -> None:
    """Start the Telegram bot in long-polling mode."""
    app = _build_app()
    app.run_polling()


if __name__ == "__main__":
    start_bot()
