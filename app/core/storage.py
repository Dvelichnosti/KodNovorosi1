import uuid
from pathlib import Path

import aiofiles
from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import AppError
from app.core.utils import slugify_text

IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
DOCUMENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

ALLOWED_TYPES = {
    "logo": IMAGE_TYPES,
    "image": IMAGE_TYPES,
    "document": DOCUMENT_TYPES,
}

PUBLIC_KINDS = {"logo", "image"}


async def save_upload(file: UploadFile, *, owner_id: uuid.UUID, kind: str) -> dict:
    kind = kind.lower().strip()
    if kind not in ALLOWED_TYPES:
        raise AppError(
            "Недопустимый тип загрузки",
            status_code=422,
            code="invalid_upload_kind",
            details={"allowed": sorted(ALLOWED_TYPES)},
        )
    content_type = (file.content_type or "").lower()
    allowed = ALLOWED_TYPES[kind]
    if content_type not in allowed:
        raise AppError(
            "Недопустимый формат файла",
            status_code=422,
            code="invalid_file_type",
            details={"allowed": sorted(allowed)},
        )

    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise AppError(
            f"Файл больше {settings.max_upload_mb} МБ",
            status_code=413,
            code="file_too_large",
        )
    if not data:
        raise AppError("Пустой файл", status_code=422, code="empty_file")

    ext = allowed[content_type]
    filename = f"{uuid.uuid4().hex}{ext}"
    folder = settings.media_path / kind / str(owner_id)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    async with aiofiles.open(target, "wb") as handle:
        await handle.write(data)

    relative = Path(kind) / str(owner_id) / filename
    return {
        "filename": filename,
        "original_name": file.filename or filename,
        "content_type": content_type,
        "size": len(data),
        "path": str(target),
        "relative_path": str(relative).replace("\\", "/"),
        "url": f"{settings.media_url.rstrip('/')}/{str(relative).replace(chr(92), '/')}",
        "is_public": kind in PUBLIC_KINDS,
        "kind": kind,
    }


def safe_name(value: str) -> str:
    return slugify_text(value, fallback="file")
