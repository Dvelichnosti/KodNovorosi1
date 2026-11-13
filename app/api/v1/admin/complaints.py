from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from app.api.deps import DB, AuthContext, require_platform_permission
from app.core.audit import write_audit
from app.core.errors import AppError
from app.core.utils import client_ip, utcnow
from app.models.enums import ComplaintStatus
from app.models.listing import Complaint
from app.schemas.admin import ResolveComplaintIn
from app.schemas.common import Page
from app.schemas.listing import ComplaintOut
from app.services.serializers import complaint_out

router = APIRouter(prefix="/complaints", tags=["admin: complaints"])


@router.get("", response_model=Page[ComplaintOut])
async def list_complaints(
    status_filter: ComplaintStatus | None = Query(default=None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_platform_permission("complaints.handle")),
    db: DB = None,
) -> Page[ComplaintOut]:
    query = select(Complaint)
    if status_filter:
        query = query.where(Complaint.status == status_filter)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    result = await db.execute(
        query.order_by(Complaint.created_at.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    items = [complaint_out(item) for item in result.scalars().unique().all()]
    return Page.build(items, int(total), page, per_page)


@router.post("/{complaint_id}/take", response_model=ComplaintOut)
async def take_complaint(
    complaint_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("complaints.handle")),
    db: DB = None,
) -> ComplaintOut:
    complaint = await db.get(Complaint, complaint_id)
    if complaint is None:
        raise AppError("Жалоба не найдена", status_code=404, code="complaint_not_found")
    complaint.status = ComplaintStatus.IN_REVIEW
    complaint.handled_by = auth.user.id
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="complaint.take",
        entity_type="complaint",
        entity_id=complaint.id,
        ip=client_ip(request),
    )
    await db.commit()
    fresh = await db.scalar(select(Complaint).where(Complaint.id == complaint.id))
    return complaint_out(fresh)


@router.post("/{complaint_id}/resolve", response_model=ComplaintOut)
async def resolve_complaint(
    complaint_id: uuid.UUID,
    data: ResolveComplaintIn,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("complaints.handle")),
    db: DB = None,
) -> ComplaintOut:
    complaint = await db.get(Complaint, complaint_id)
    if complaint is None:
        raise AppError("Жалоба не найдена", status_code=404, code="complaint_not_found")
    complaint.status = ComplaintStatus(data.status)
    complaint.resolution = data.resolution
    complaint.handled_by = auth.user.id
    complaint.handled_at = utcnow()
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="complaint.resolve",
        entity_type="complaint",
        entity_id=complaint.id,
        payload={"status": data.status, "resolution": data.resolution},
        ip=client_ip(request),
    )
    await db.commit()
    fresh = await db.scalar(select(Complaint).where(Complaint.id == complaint.id))
    return complaint_out(fresh)
