import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self) -> None:
        self.token = settings.telegram_bot_token
        self.username = settings.telegram_bot_username

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def login_link(self, token: str) -> str:
        bot = self.username.lstrip("@") or "BizBoardBot"
        return f"https://t.me/{bot}?start=login_{token}"

    def invite_link(self, token: str) -> str:
        bot = self.username.lstrip("@") or "BizBoardBot"
        return f"https://t.me/{bot}?start=invite_{token}"

    async def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.configured:
            logger.info("Telegram bot is not configured, skip %s", method)
            return None
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as exc:  # pragma: no cover - external service
            logger.warning("Telegram API error on %s: %s", method, exc)
            return None

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        await self.call("sendMessage", payload)

    async def request_contact(self, chat_id: int, text: str) -> None:
        await self.send_message(
            chat_id,
            text,
            reply_markup={
                "keyboard": [[{"text": "📱 Поделиться контактом", "request_contact": True}]],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            },
        )

    async def remove_keyboard(self, chat_id: int, text: str) -> None:
        await self.send_message(
            chat_id,
            text,
            reply_markup={"remove_keyboard": True},
        )


telegram_bot = TelegramBot()
