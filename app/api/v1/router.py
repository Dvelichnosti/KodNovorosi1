from fastapi import APIRouter

from app.api.v1 import (
    auth,
    catalog,
    invitations,
    listings,
    meta,
    organizations,
    public,
    telegram,
    uploads,
    users,
)
from app.api.v1.admin.router import router as admin_router

router = APIRouter()
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(organizations.router)
router.include_router(invitations.router)
router.include_router(catalog.router)
router.include_router(listings.router)
router.include_router(uploads.router)
router.include_router(public.router)
router.include_router(meta.router)
router.include_router(telegram.router)
router.include_router(admin_router)
