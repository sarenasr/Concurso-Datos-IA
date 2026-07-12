"""Telegram polling bot for DATIA.

Run locally:
    uv run python -m app.channels.telegram_bot

On each text message the agent runs and the ``answer`` field is replied. Long
answers are split into <=4096-char chunks to respect the Telegram limit.
"""

from __future__ import annotations

import logging

from app.config import settings

log = logging.getLogger("datia.telegram")

TELEGRAM_MAX_LEN = 4096


def _split(text: str, limit: int = TELEGRAM_MAX_LEN) -> list[str]:
    """Split ``text`` into chunks no longer than ``limit`` (line-aware)."""
    chunks: list[str] = []
    for line in text.splitlines(keepends=True):
        if not chunks or len(chunks[-1]) + len(line) > limit:
            chunks.append(line)
        else:
            chunks[-1] += line
    return [c for c in chunks if c]


async def _on_text(update, context) -> None:  # noqa: ANN001
    """Handle an inbound text message: run the agent, reply with the answer."""
    from app.agents.graph import run_agent

    text = update.message.text
    try:
        result = run_agent(text)
        reply = result.get("answer") or "Sin respuesta."
    except Exception as exc:  # noqa: BLE001
        log.exception("agent failed")
        reply = f"Lo siento, hubo un error: {exc}"

    for chunk in _split(reply):
        await update.message.reply_text(chunk)


def _build_app():
    """Build a configured python-telegram-bot Application."""
    from telegram.ext import Application, CommandHandler, MessageHandler, filters

    app = Application.builder().token(settings.telegram_bot_token).build()

    async def _start(update, context):  # noqa: ANN001
        await update.message.reply_text(
            "Hola, soy DATIA. Preguntame sobre los datos abiertos de Colombia."
        )

    app.add_handler(CommandHandler("start", _start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text))
    return app


def start_bot() -> None:
    """Start the Telegram bot in long-polling mode."""
    app = _build_app()
    app.run_polling()


if __name__ == "__main__":
    start_bot()
