from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, AuthContext, require_platform_permission
from app.core.audit import write_audit
from app.core.errors import AppError
from app.core.utils import client_ip, utcnow
from app.models.billing import Plan
from app.models.enums import OrgStatus, VerificationLevel
from app.models.organization import (
    Organization,
    OrganizationCapability,
    VerificationDocument,
)
from app.schemas.common import Page
from app.schemas.organization import (
    AssignPlanIn,
    DocumentOut,
    DocumentReviewIn,
    OrgOut,
    VerifyOrgIn,
)
from app.services import org_service
from app.services.serializers import document_out

router = APIRouter(prefix="/organizations", tags=["admin: organizations"])


@router.get("", response_model=Page[OrgOut])
async def list_organizations(
    q: str | None = Query(default=None, max_length=200),
    status_filter: OrgStatus | None = Query(default=None, alias="status"),
    verification_level: VerificationLevel | None = Query(default=None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_platform_permission("orgs.verify")),
    db: DB = None,
) -> Page[OrgOut]:
    query = select(Organization)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                Organization.name.ilike(pattern),
                Organization.inn.ilike(pattern),
                Organization.slug.ilike(pattern),
            )
        )
    if status_filter:
        query = query.where(Organization.status == status_filter)
    if verification_level:
        query = query.where(Organization.verification_level == verification_level)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    result = await db.execute(
        query.options(
            selectinload(Organization.capabilities).selectinload(
                OrganizationCapability.capability
            )
        )
        .order_by(Organization.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    orgs = list(result.scalars().unique().all())
    items = [await org_service.get_org_out(db, org) for org in orgs]
    return Page.build(items, int(total), page, per_page)


@router.get("/{org_id}", response_model=OrgOut)
async def get_organization(
    org_id: uuid.UUID,
    auth: AuthContext = Depends(require_platform_permission("orgs.verify")),
    db: DB = None,
) -> OrgOut:
    org = await org_service.get_org(db, org_id)
    return await org_service.get_org_out(db, org)


@router.post("/{org_id}/verify", response_model=OrgOut)
async def verify_organization(
    org_id: uuid.UUID,
    data: VerifyOrgIn,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("orgs.verify")),
    db: DB = None,
) -> OrgOut:
    org = await org_service.get_org(db, org_id)
    if data.decision == "approve":
        org.moderator_verified_at = utcnow()
        org.verified_by = auth.user.id
        org.rejection_reason = None
        org.verification_level = VerificationLevel.MODERATOR
    else:
        if not data.comment:
            raise AppError(
                "Укажите причину отказа",
                status_code=422,
                code="rejection_reason_required",
            )
        org.rejection_reason = data.comment
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="organization.verify",
        entity_type="organization",
        entity_id=org.id,
        payload={"decision": data.decision, "comment": data.comment},
        ip=client_ip(request),
    )
    await db.commit()
    org = await org_service.get_org(db, org.id)
    return await org_service.get_org_out(db, org)


@router.get("/{org_id}/documents", response_model=list[DocumentOut])
async def list_documents(
    org_id: uuid.UUID,
    auth: AuthContext = Depends(require_platform_permission("orgs.verify")),
    db: DB = None,
) -> list[DocumentOut]:
    await org_service.get_org(db, org_id)
    result = await db.execute(
        select(VerificationDocument)
        .where(VerificationDocument.organization_id == org_id)
        .order_by(VerificationDocument.created_at.desc())
    )
    return [document_out(item) for item in result.scalars().all()]


@router.post("/{org_id}/documents/{document_id}/review", response_model=DocumentOut)
async def review_document(
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    data: DocumentReviewIn,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("orgs.verify")),
    db: DB = None,
) -> DocumentOut:
    document = await db.get(VerificationDocument, document_id)
    if document is None or document.organization_id != org_id:
        raise AppError("Документ не найден", status_code=404, code="document_not_found")
    result = await org_service.review_verification_document(
        db,
        auth.user,
        document_id,
        decision=data.decision,
        comment=data.comment,
    )
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="organization.document_review",
        entity_type="verification_document",
        entity_id=document_id,
        payload={"decision": data.decision, "comment": data.comment},
        ip=client_ip(request),
    )
    await db.commit()
    return result


@router.post("/{org_id}/plan", response_model=OrgOut)
async def assign_plan(
    org_id: uuid.UUID,
    data: AssignPlanIn,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("plans.manage")),
    db: DB = None,
) -> OrgOut:
    org = await org_service.get_org(db, org_id)
    if data.plan_id is not None:
        plan = await db.get(Plan, data.plan_id)
        if plan is None:
            raise AppError("Тариф не найден", status_code=404, code="plan_not_found")
        org.plan_id = plan.id
    else:
        org.plan_id = None
    org.plan_expires_at = data.expires_at
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="organization.assign_plan",
        entity_type="organization",
        entity_id=org.id,
        payload={"plan_id": str(data.plan_id) if data.plan_id else None},
        ip=client_ip(request),
    )
    await db.commit()
    org = await org_service.get_org(db, org.id)
    return await org_service.get_org_out(db, org)
