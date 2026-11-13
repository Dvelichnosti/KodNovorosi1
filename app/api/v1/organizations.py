from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.api.deps import DB, AuthContext, get_auth
from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.core.storage import save_upload
from app.models.enums import DocumentKind
from app.models.system import UploadedFile
from app.schemas.common import Message
from app.schemas.organization import (
    CapabilitiesUpdate,
    DocumentOut,
    InnVerifyIn,
    InvitationCreated,
    InvitationOut,
    InviteIn,
    MemberOut,
    MemberUpdate,
    OrgCreate,
    OrgOut,
    OrgUpdate,
    OwnerTransferIn,
    RoleCreate,
    RoleOut,
    RoleUpdate,
)
from app.services import org_service

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrgOut, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrgCreate,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> OrgOut:
    org = await org_service.create_organization(db, auth.user, data)
    return await org_service.get_org_out(db, org)


@router.get("/mine", response_model=list[OrgOut])
async def my_organizations(
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> list[OrgOut]:
    return await org_service.list_my_organizations(db, auth.user)


@router.get("/{org_id}", response_model=OrgOut)
async def get_organization(
    org_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> OrgOut:
    org, _ = await org_service.require_member(db, auth.user, org_id)
    return await org_service.get_org_out(db, org)


@router.patch("/{org_id}", response_model=OrgOut)
async def update_organization(
    org_id: uuid.UUID,
    data: OrgUpdate,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> OrgOut:
    org = await org_service.update_organization(db, auth.user, org_id, data)
    return await org_service.get_org_out(db, org)


@router.put("/{org_id}/capabilities", response_model=OrgOut)
async def update_capabilities(
    org_id: uuid.UUID,
    data: CapabilitiesUpdate,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> OrgOut:
    org = await org_service.set_capabilities(db, auth.user, org_id, data)
    return await org_service.get_org_out(db, org)


@router.post("/{org_id}/verification/inn", response_model=OrgOut)
async def verify_inn(
    org_id: uuid.UUID,
    data: InnVerifyIn,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> OrgOut:
    org = await org_service.verify_inn(db, auth.user, org_id, data.inn)
    return await org_service.get_org_out(db, org)


@router.post(
    "/{org_id}/verification/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_verification_document(
    org_id: uuid.UUID,
    kind: DocumentKind = Form(...),
    file: UploadFile = File(...),
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> DocumentOut:
    await enforce_rate_limit(
        f"upload:{auth.user.id}",
        settings.upload_rate_limit,
        settings.upload_rate_window,
    )
    await org_service.require_member(db, auth.user, org_id)
    saved = await save_upload(file, owner_id=auth.user.id, kind="document")
    uploaded = UploadedFile(
        owner_id=auth.user.id,
        kind="document",
        filename=saved["filename"],
        original_name=saved["original_name"],
        content_type=saved["content_type"],
        size=saved["size"],
        path=saved["path"],
        url=saved["url"],
        is_public=False,
    )
    db.add(uploaded)
    await db.flush()
    document = await org_service.add_verification_document(
        db,
        auth.user,
        org_id,
        kind=kind,
        file_url=saved["url"],
        original_name=saved["original_name"],
    )
    return document


@router.get("/{org_id}/verification/documents", response_model=list[DocumentOut])
async def list_verification_documents(
    org_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> list[DocumentOut]:
    return await org_service.list_verification_documents(db, auth.user, org_id)


@router.get("/{org_id}/members", response_model=list[MemberOut])
async def list_members(
    org_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> list[MemberOut]:
    return await org_service.list_members(db, auth.user, org_id)


@router.post(
    "/{org_id}/invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    org_id: uuid.UUID,
    data: InviteIn,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> InvitationCreated:
    return await org_service.invite_member(
        db,
        auth.user,
        org_id,
        role_id=data.role_id,
        telegram_id=data.telegram_id,
    )


@router.get("/{org_id}/invitations", response_model=list[InvitationOut])
async def list_invitations(
    org_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> list[InvitationOut]:
    return await org_service.list_invitations(db, auth.user, org_id)


@router.delete("/{org_id}/invitations/{invitation_id}", response_model=Message)
async def revoke_invitation(
    org_id: uuid.UUID,
    invitation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> Message:
    await org_service.revoke_invitation(db, auth.user, org_id, invitation_id)
    return Message(message="Приглашение отозвано")


@router.patch("/{org_id}/members/{user_id}", response_model=MemberOut)
async def update_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    data: MemberUpdate,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> MemberOut:
    return await org_service.update_member_role(
        db, auth.user, org_id, user_id, data.role_id
    )


@router.delete("/{org_id}/members/{user_id}", response_model=Message)
async def remove_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> Message:
    await org_service.remove_member(db, auth.user, org_id, user_id)
    return Message(message="Сотрудник удалён")


@router.post("/{org_id}/transfer-owner", response_model=OrgOut)
async def transfer_owner(
    org_id: uuid.UUID,
    data: OwnerTransferIn,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> OrgOut:
    return await org_service.transfer_owner(db, auth.user, org_id, data.user_id)


@router.get("/{org_id}/roles", response_model=list[RoleOut])
async def list_roles(
    org_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> list[RoleOut]:
    return await org_service.list_roles(db, auth.user, org_id)


@router.post("/{org_id}/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
async def create_role(
    org_id: uuid.UUID,
    data: RoleCreate,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> RoleOut:
    return await org_service.create_role(db, auth.user, org_id, data)


@router.patch("/{org_id}/roles/{role_id}", response_model=RoleOut)
async def update_role(
    org_id: uuid.UUID,
    role_id: uuid.UUID,
    data: RoleUpdate,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> RoleOut:
    return await org_service.update_role(db, auth.user, org_id, role_id, data)


@router.delete("/{org_id}/roles/{role_id}", response_model=Message)
async def delete_role(
    org_id: uuid.UUID,
    role_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> Message:
    await org_service.delete_role(db, auth.user, org_id, role_id)
    return Message(message="Роль удалена")
