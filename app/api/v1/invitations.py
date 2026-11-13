from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import DB, AuthContext, get_auth
from app.schemas.organization import OrgOut
from app.services import org_service

router = APIRouter(prefix="/invitations", tags=["organizations"])


@router.post("/{token}/accept", response_model=OrgOut)
async def accept_invitation(
    token: str,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> OrgOut:
    return await org_service.accept_invitation(db, auth.user, token)
