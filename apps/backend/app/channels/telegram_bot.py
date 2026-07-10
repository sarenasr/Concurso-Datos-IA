"""Telegram delivery channel.

Webhook mode for Railway. Set TELEGRAM_BOT_TOKEN, deploy, then hit the running
service once with `curl <app-url>/setwebhook` to register the webhook.

Local polling mode for quick testing:
    uv run python -m app.channels.telegram_bot
"""
from __future__ import annotations

import logging

from app.config import settings

log = logging.getLogger("datia.telegram")


def _application():
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters

    app = Application.builder().token(settings.telegram_bot_token).build()

    async def start(update: Update, context):
        await update.message.reply_text(
            "Hola, soy DATIA. Preguntame sobre datos abiertos de Colombia 🇨🇴"
        )

    async def on_text(update: Update, context):
        from app.agents.graph import run_agent

        text = update.message.text
        try:
            result = run_agent(text)
            reply = result.get("answer") or "Sin respuesta."
            await update.message.reply_text(reply[:4000])
        except Exception as exc:  # noqa: BLE001
            log.exception("agent failed")
            await update.message.reply_text(f"Error: {exc}")

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def run_polling() -> None:
    """Run the bot in long-polling mode (local dev)."""
    app = _application()
    app.run_polling()


async def telegram_webhook(update_dict: dict) -> dict | None:
    """Handle a single Telegram update dict (called by FastAPI webhook endpoint)."""
    from telegram import Update

    update = Update.de_json(update_dict, _application().bot)
    await _application().process_update(update)
    return {"ok": True}


async def set_webhook(base_url: str) -> dict:
    """Register the webhook URL with Telegram. Hit GET /setwebhook once deployed."""
    app = _application()
    url = f"{base_url.rstrip('/')}/telegram/webhook"
    ok = await app.bot.set_webhook(url=url)
    return {"webhook_url": url, "ok": ok}


if __name__ == "__main__":
    run_polling()
