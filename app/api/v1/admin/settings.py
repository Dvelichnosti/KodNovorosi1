from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.deps import DB, AuthContext, require_platform_permission
from app.core.audit import write_audit
from app.core.utils import client_ip, utcnow
from app.models.system import PlatformSetting
from app.schemas.admin import SettingOut, SettingUpdateIn

router = APIRouter(prefix="/settings", tags=["admin: settings"])


@router.get("", response_model=list[SettingOut])
async def list_settings(
    auth: AuthContext = Depends(require_platform_permission("settings.manage")),
    db: DB = None,
) -> list[SettingOut]:
    result = await db.execute(select(PlatformSetting).order_by(PlatformSetting.key))
    return [
        SettingOut(
            key=item.key,
            value=item.value or {},
            description=item.description,
            updated_at=item.updated_at,
        )
        for item in result.scalars().all()
    ]


@router.put("/{key}", response_model=SettingOut)
async def upsert_setting(
    key: str,
    data: SettingUpdateIn,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("settings.manage")),
    db: DB = None,
) -> SettingOut:
    setting = await db.get(PlatformSetting, key)
    if setting is None:
        setting = PlatformSetting(key=key, value=data.value)
        db.add(setting)
    setting.value = data.value
    if data.description is not None:
        setting.description = data.description
    setting.updated_by = auth.user.id
    setting.updated_at = utcnow()
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="settings.update",
        entity_type="platform_setting",
        entity_id=key,
        payload={"value": data.value},
        ip=client_ip(request),
    )
    await db.commit()
    await db.refresh(setting)
    return SettingOut(
        key=setting.key,
        value=setting.value or {},
        description=setting.description,
        updated_at=setting.updated_at,
    )
