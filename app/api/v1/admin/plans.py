from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.api.deps import DB, AuthContext, require_platform_permission
from app.core.audit import write_audit
from app.core.errors import AppError
from app.core.utils import client_ip
from app.models.billing import Plan
from app.models.organization import Organization
from app.schemas.admin import PlanCreateIn, PlanUpdateIn
from app.schemas.common import Message
from app.schemas.organization import PlanOut
from app.services.serializers import plan_out

router = APIRouter(prefix="/plans", tags=["admin: plans"])


@router.get("", response_model=list[PlanOut])
async def list_plans(
    auth: AuthContext = Depends(require_platform_permission("plans.manage")),
    db: DB = None,
) -> list[PlanOut]:
    result = await db.execute(select(Plan).order_by(Plan.sort_order, Plan.price))
    return [plan_out(item) for item in result.scalars().all()]


@router.post("", response_model=PlanOut, status_code=201)
async def create_plan(
    data: PlanCreateIn,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("plans.manage")),
    db: DB = None,
) -> PlanOut:
    existing = await db.scalar(select(Plan.id).where(Plan.code == data.code))
    if existing:
        raise AppError("Тариф с таким кодом уже существует", status_code=409, code="plan_exists")
    plan = Plan(
        code=data.code,
        name=data.name.strip(),
        max_active_listings=data.max_active_listings,
        price=Decimal(str(data.price)),
        currency=data.currency,
        features=data.features,
        description=data.description,
        is_active=data.is_active,
        sort_order=data.sort_order,
    )
    db.add(plan)
    await db.flush()
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="plan.create",
        entity_type="plan",
        entity_id=plan.id,
        payload={"code": plan.code},
        ip=client_ip(request),
    )
    await db.commit()
    await db.refresh(plan)
    return plan_out(plan)


@router.patch("/{plan_id}", response_model=PlanOut)
async def update_plan(
    plan_id: uuid.UUID,
    data: PlanUpdateIn,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("plans.manage")),
    db: DB = None,
) -> PlanOut:
    plan = await db.get(Plan, plan_id)
    if plan is None:
        raise AppError("Тариф не найден", status_code=404, code="plan_not_found")
    values = data.model_dump(exclude_unset=True)
    for field in ("name", "max_active_listings", "currency", "features", "description", "is_active", "sort_order"):
        if field in values and values[field] is not None:
            setattr(plan, field, values[field])
    if "price" in values and values["price"] is not None:
        plan.price = Decimal(str(values["price"]))
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="plan.update",
        entity_type="plan",
        entity_id=plan.id,
        payload=values,
        ip=client_ip(request),
    )
    await db.commit()
    await db.refresh(plan)
    return plan_out(plan)


@router.delete("/{plan_id}", response_model=Message)
async def delete_plan(
    plan_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("plans.manage")),
    db: DB = None,
) -> Message:
    plan = await db.get(Plan, plan_id)
    if plan is None:
        raise AppError("Тариф не найден", status_code=404, code="plan_not_found")
    assigned = await db.scalar(
        select(func.count(Organization.id)).where(Organization.plan_id == plan.id)
    )
    if assigned:
        raise AppError(
            "Тариф назначен организациям. Сначала смените им тариф.",
            status_code=409,
            code="plan_in_use",
            details={"organizations_count": int(assigned)},
        )
    await db.delete(plan)
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="plan.delete",
        entity_type="plan",
        entity_id=plan_id,
        payload={"code": plan.code},
        ip=client_ip(request),
    )
    await db.commit()
    return Message(message="Тариф удалён")
