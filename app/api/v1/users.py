from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import DB, AuthContext, get_auth
from app.core.errors import AppError
from app.core.utils import clean_str
from app.models.user import User
from app.schemas.common import Page
from app.schemas.listing import ListingOut
from app.schemas.user import UserMe, UserUpdate
from app.services import listing_service
from app.services.serializers import listing_out, user_me

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMe)
async def get_me(auth: AuthContext = Depends(get_auth)) -> UserMe:
    return user_me(auth.user)


@router.patch("/me", response_model=UserMe)
async def update_me(
    data: UserUpdate,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> UserMe:
    user = auth.user
    values = data.model_dump(exclude_unset=True)
    if "first_name" in values:
        user.first_name = clean_str(values["first_name"], max_len=128)
    if "last_name" in values:
        user.last_name = clean_str(values["last_name"], max_len=128)
    if "email" in values:
        email = clean_str(values["email"], max_len=255)
        if email:
            email = email.lower()
            existing = await db.scalar(
                select(User.id).where(User.email == email, User.id != user.id)
            )
            if existing:
                raise AppError("Email уже используется", status_code=409, code="email_taken")
        if email != user.email:
            user.email_verified_at = None
        user.email = email
    if "notification_settings" in values and values["notification_settings"] is not None:
        settings = dict(user.notification_settings or {})
        settings.update(values["notification_settings"])
        user.notification_settings = settings
    await db.commit()
    return user_me(user)


@router.get("/me/favorites", response_model=Page[ListingOut])
async def my_favorites(
    page: int = 1,
    per_page: int = 20,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> Page[ListingOut]:
    page = max(1, page)
    per_page = min(100, max(1, per_page))
    listings, total = await listing_service.list_favorites(
        db, auth.user, page=page, per_page=per_page
    )
    items = [
        listing_out(item, contacts_visible=True, is_favorite=True) for item in listings
    ]
    return Page.build(items, total, page, per_page)
