from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import DB, AuthContext, require_any_platform_permission
from app.models.enums import (
    ComplaintStatus,
    DocumentStatus,
    ListingStatus,
    OrgStatus,
    UserStatus,
    VerificationLevel,
)
from app.models.listing import Complaint, Listing
from app.models.organization import Organization, VerificationDocument
from app.models.user import User
from app.schemas.admin import AdminStatsOut

router = APIRouter(prefix="/stats", tags=["admin: stats"])


@router.get("", response_model=AdminStatsOut)
async def admin_stats(
    auth: AuthContext = Depends(
        require_any_platform_permission(
            ["users.view", "orgs.verify", "listings.moderate", "complaints.handle"]
        )
    ),
    db: DB = None,
) -> AdminStatsOut:
    async def count(model, *conditions) -> int:
        query = select(func.count()).select_from(model)
        if conditions:
            query = query.where(*conditions)
        return int(await db.scalar(query) or 0)

    return AdminStatsOut(
        users_total=await count(User),
        users_blocked=await count(User, User.status == UserStatus.BLOCKED),
        organizations_total=await count(Organization, Organization.status == OrgStatus.ACTIVE),
        organizations_pending_verification=await count(
            Organization,
            Organization.status == OrgStatus.ACTIVE,
            Organization.verification_level != VerificationLevel.MODERATOR,
        ),
        listings_total=await count(Listing, Listing.deleted_at.is_(None)),
        listings_pending=await count(
            Listing,
            Listing.status == ListingStatus.PENDING,
            Listing.deleted_at.is_(None),
        ),
        listings_active=await count(
            Listing,
            Listing.status == ListingStatus.ACTIVE,
            Listing.deleted_at.is_(None),
        ),
        complaints_new=await count(Complaint, Complaint.status == ComplaintStatus.NEW),
        documents_pending=await count(
            VerificationDocument, VerificationDocument.status == DocumentStatus.PENDING
        ),
    )
