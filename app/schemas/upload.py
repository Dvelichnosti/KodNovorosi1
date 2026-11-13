from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class UploadOut(BaseModel):
    id: uuid.UUID
    kind: str
    filename: str
    original_name: str | None = None
    content_type: str
    size: int
    url: str
    is_public: bool
    created_at: datetime
