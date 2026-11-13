from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DB
from app.schemas.common import Page
from app.schemas.organization import OrgPublic
from app.services import org_service

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/organizations", response_model=Page[OrgPublic])
async def search_organizations(
    q: str | None = Query(default=None, max_length=200),
    region: str | None = Query(default=None),
    type: str | None = Query(default=None),
    capability: str | None = Query(default=None),
    verification_level: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: DB = None,
) -> Page[OrgPublic]:
    items, total = await org_service.search_organizations(
        db,
        q=q,
        region=region,
        org_type=type,
        capability=capability,
        verification_level=verification_level,
        page=page,
        per_page=per_page,
    )
    return Page.build(items, total, page, per_page)


@router.get("/organizations/{slug}", response_model=OrgPublic)
async def get_organization(slug: str, db: DB = None) -> OrgPublic:
    return await org_service.get_public_org(db, slug)
