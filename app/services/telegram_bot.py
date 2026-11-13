from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_token
from app.core.telegram import telegram_bot
from app.models.auth import LoginSession
from app.models.enums import InvitationStatus, LoginStatus
from app.models.organization import Invitation
from app.models.user import User
from app.services import auth_service, org_service

logger = logging.getLogger(__name__)


async def _find_session_by_chat(db: AsyncSession, chat_id: int) -> LoginSession | None:
    return await db.scalar(
        select(LoginSession)
        .where(
            LoginSession.chat_id == chat_id,
            LoginSession.status == LoginStatus.PENDING,
        )
        .order_by(LoginSession.created_at.desc())
    )


async def _handle_start(db: AsyncSession, message: dict[str, Any], payload: str) -> None:
    chat_id = message["chat"]["id"]
    from_user = message.get("from") or {}
    telegram_id = from_user.get("id")
    if not telegram_id:
        return

    if payload.startswith("login_"):
        token = payload[len("login_") :]
        session = await db.scalar(
            select(LoginSession).where(LoginSession.token_hash == hash_token(token))
        )
        if session is None:
            await telegram_bot.send_message(chat_id, "Ссылка входа не найдена или устарела.")
            return
        if session.status == LoginStatus.CONSUMED:
            await telegram_bot.send_message(chat_id, "Эта ссылка уже использована.")
            return
        session.chat_id = chat_id
        await db.commit()
        await telegram_bot.request_contact(
            chat_id,
            "Чтобы войти в BizBoard, поделитесь номером телефона. Это подтвердит ваш номер без СМС.",
        )
        return

    if payload.startswith("invite_"):
        token = payload[len("invite_") :]
        invitation = await db.scalar(
            select(Invitation).where(Invitation.token_hash == hash_token(token))
        )
        if invitation is None or invitation.status != InvitationStatus.PENDING:
            await telegram_bot.send_message(chat_id, "Приглашение не найдено или уже использовано.")
            return
        invitation.telegram_id = telegram_id
        await db.commit()
        user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is not None:
            try:
                await org_service.accept_pending_invites(db, user)
                await telegram_bot.send_message(
                    chat_id,
                    "Приглашение принято. Откройте кабинет BizBoard, чтобы увидеть организацию.",
                )
            except Exception:
                logger.exception("Failed to accept invitation")
                await telegram_bot.send_message(chat_id, "Не удалось принять приглашение.")
            return
        # New user: start a login session in the same chat, then the invitation is
        # accepted automatically after the contact is confirmed.
        session, _ = await auth_service.start_telegram_login(db, ip=None, user_agent="telegram-invite")
        session.chat_id = chat_id
        await db.commit()
        await telegram_bot.request_contact(
            chat_id,
            "Чтобы принять приглашение, войдите в BizBoard и поделитесь номером телефона.",
        )
        return

    await telegram_bot.send_message(
        chat_id,
        "Добро пожаловать в BizBoard — платформу B2B-объявлений для малого и среднего бизнеса.\n"
        "Войти можно на сайте по ссылке из приложения.",
    )


async def _handle_contact(db: AsyncSession, message: dict[str, Any]) -> None:
    chat_id = message["chat"]["id"]
    from_user = message.get("from") or {}
    contact = message.get("contact") or {}
    telegram_id = from_user.get("id")
    phone = contact.get("phone_number")
    if not telegram_id or not phone:
        return
    if contact.get("user_id") and int(contact["user_id"]) != int(telegram_id):
        await telegram_bot.send_message(chat_id, "Поделитесь, пожалуйста, своим контактом.")
        return
    session = await _find_session_by_chat(db, chat_id)
    if session is None:
        await telegram_bot.send_message(
            chat_id,
            "Сессия входа не найдена. Вернитесь в приложение и начните вход заново.",
        )
        return
    try:
        await auth_service.confirm_login_session(
            db,
            session,
            telegram_id=int(telegram_id),
            phone=phone,
            first_name=from_user.get("first_name"),
            last_name=from_user.get("last_name"),
            username=from_user.get("username"),
            chat_id=chat_id,
        )
        await telegram_bot.remove_keyboard(
            chat_id,
            "Готово. Вернитесь в приложение — вход подтверждён.",
        )
    except Exception as exc:
        logger.exception("Telegram contact confirmation failed")
        await telegram_bot.send_message(chat_id, f"Не удалось войти: {exc}")


async def handle_update(db: AsyncSession, update: dict[str, Any]) -> None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    if message.get("contact"):
        await _handle_contact(db, message)
        return
    text = (message.get("text") or "").strip()
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        payload = parts[1].strip() if len(parts) > 1 else ""
        await _handle_start(db, message, payload)
        return
    if text.startswith("/help"):
        await telegram_bot.send_message(
            message["chat"]["id"],
            "BizBoard: вход по ссылке из приложения. Подтвердите телефон кнопкой ниже.",
        )
