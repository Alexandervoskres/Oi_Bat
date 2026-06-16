"""initial schema

Creates the full current schema (users, import_batches, products,
product_snapshots, stock_movements, audit_logs) from the SQLAlchemy models so
the baseline stays in lockstep with create_all. Future schema changes ship as
their own revisions with explicit op.add_column / op.create_table calls.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-16

"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _metadata():
    from backend.app.database import Base
    import backend.app.models  # noqa: F401  (populate metadata)

    return Base.metadata


def upgrade() -> None:
    # checkfirst=True keeps this safe on databases that already have some tables
    # (e.g. an existing dev.db created by the previous create_all bootstrap).
    _metadata().create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    _metadata().drop_all(bind=op.get_bind())
