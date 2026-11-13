import uuid
from typing import Any

from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import enum_type as enum_type  # re-export


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


def json_default() -> dict[str, Any]:
    return {}
