"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-13

Baseline migration. The schema is generated from the SQLAlchemy metadata so
that a fresh database always matches the models. Subsequent migrations should
be created with ``alembic revision --autogenerate``.
"""
from __future__ import annotations

from collections.abc import Sequence

import app.models  # noqa: F401  (register all ORM models)
from alembic import op
from app.core.database import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_listings_fts "
            "ON listings USING gin (to_tsvector('russian', title || ' ' || description))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_listings_fts")
    Base.metadata.drop_all(bind=bind)
