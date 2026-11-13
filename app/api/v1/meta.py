from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB
from app.core.permissions import ORG_PERMISSIONS, PLATFORM_PERMISSIONS
from app.core.reference import (
    ATTRIBUTE_TYPES,
    COMPLAINT_REASONS,
    COMPLAINT_STATUSES,
    LISTING_STATUSES,
    LISTING_TYPES,
    ORG_TYPES,
    REGIONS,
    VERIFICATION_LEVELS,
)
from app.models.billing import Plan
from app.schemas.organization import PlanOut
from app.services.serializers import plan_out

router = APIRouter(tags=["meta"])


@router.get("/meta")
async def meta() -> dict:
    return {
        "regions": REGIONS,
        "org_types": ORG_TYPES,
        "verification_levels": VERIFICATION_LEVELS,
        "listing_types": LISTING_TYPES,
        "listing_statuses": LISTING_STATUSES,
        "complaint_reasons": COMPLAINT_REASONS,
        "complaint_statuses": COMPLAINT_STATUSES,
        "attribute_types": ATTRIBUTE_TYPES,
        "org_permissions": ORG_PERMISSIONS,
        "platform_permissions": PLATFORM_PERMISSIONS,
    }


@router.get("/plans", response_model=list[PlanOut])
async def public_plans(db: DB = None) -> list[PlanOut]:
    result = await db.execute(
        select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order, Plan.price)
    )
    return [plan_out(item) for item in result.scalars().all()]
