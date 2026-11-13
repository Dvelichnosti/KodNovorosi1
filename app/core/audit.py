import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import AuditLog


async def write_audit(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    ip: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        payload=payload or {},
        ip=ip,
    )
    db.add(entry)
    return entry
