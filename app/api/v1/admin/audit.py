from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import DB, AuthContext, require_platform_permission
from app.models.system import AuditLog
from app.schemas.admin import AuditOut
from app.schemas.common import Page
from app.services.serializers import audit_out

router = APIRouter(prefix="/audit", tags=["admin: audit"])


@router.get("", response_model=Page[AuditOut])
async def list_audit(
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None, max_length=128),
    entity_type: str | None = Query(default=None, max_length=64),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_platform_permission("audit.view")),
    db: DB = None,
) -> Page[AuditOut]:
    query = select(AuditLog)
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
    if action:
        query = query.where(AuditLog.action == action)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    result = await db.execute(
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    items = [audit_out(item) for item in result.scalars().all()]
    return Page.build(items, int(total), page, per_page)
