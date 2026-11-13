from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.api.deps import DB, AuthContext, get_auth
from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.core.storage import save_upload
from app.models.system import UploadedFile
from app.schemas.upload import UploadOut

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    kind: str = Form(default="image"),
    file: UploadFile = File(...),
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> UploadOut:
    await enforce_rate_limit(
        f"upload:{auth.user.id}",
        settings.upload_rate_limit,
        settings.upload_rate_window,
    )
    saved = await save_upload(file, owner_id=auth.user.id, kind=kind)
    uploaded = UploadedFile(
        owner_id=auth.user.id,
        kind=saved["kind"],
        filename=saved["filename"],
        original_name=saved["original_name"],
        content_type=saved["content_type"],
        size=saved["size"],
        path=saved["path"],
        url=saved["url"],
        is_public=saved["is_public"],
    )
    db.add(uploaded)
    await db.commit()
    await db.refresh(uploaded)
    return UploadOut(
        id=uploaded.id,
        kind=uploaded.kind,
        filename=uploaded.filename,
        original_name=uploaded.original_name,
        content_type=uploaded.content_type,
        size=uploaded.size,
        url=uploaded.url,
        is_public=uploaded.is_public,
        created_at=uploaded.created_at,
    )
