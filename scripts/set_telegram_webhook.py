"""Register the Telegram webhook.

Usage::

    python -m scripts.set_telegram_webhook https://api.example.com/api/v1/telegram/webhook

Requires ``TELEGRAM_BOT_TOKEN`` and, optionally, ``TELEGRAM_WEBHOOK_SECRET``.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from app.core.config import settings
from app.core.telegram import telegram_bot

logger = logging.getLogger(__name__)


async def main(url: str) -> None:
    if not telegram_bot.configured:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not configured")
    payload: dict[str, object] = {
        "url": url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": False,
    }
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret
    result = await telegram_bot.call("setWebhook", payload)
    if result is None:
        raise SystemExit("Telegram API request failed")
    logger.info("Webhook response: %s", result)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python -m scripts.set_telegram_webhook <https://host/api/v1/telegram/webhook>"
        )
    asyncio.run(main(sys.argv[1]))
