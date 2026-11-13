from fastapi import APIRouter

from app.api.v1.admin import (
    audit,
    catalog,
    complaints,
    listings,
    organizations,
    plans,
    roles,
    settings,
    stats,
    users,
)

router = APIRouter(prefix="/admin")
router.include_router(users.router)
router.include_router(roles.router)
router.include_router(organizations.router)
router.include_router(listings.router)
router.include_router(complaints.router)
router.include_router(catalog.router)
router.include_router(plans.router)
router.include_router(audit.router)
router.include_router(settings.router)
router.include_router(stats.router)
