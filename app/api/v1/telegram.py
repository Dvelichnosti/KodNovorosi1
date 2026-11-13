from __future__ import annotations

import logging

from fastapi import APIRouter, Header, Request

from app.api.deps import DB
from app.core.config import settings
from app.core.errors import AppError
from app.services import telegram_bot

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def webhook(
    request: Request,
    db: DB = None,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise AppError("Неверный секрет вебхука", status_code=403, code="invalid_webhook_secret")
    try:
        update = await request.json()
    except Exception as exc:
        raise AppError("Некорректный JSON", status_code=400, code="invalid_json") from exc
    try:
        await telegram_bot.handle_update(db, update)
    except Exception:
        logger.exception("Telegram update processing failed")
    return {"ok": True}
