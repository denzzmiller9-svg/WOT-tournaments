"""add participant statistics snapshot

Revision ID: 8f47a31c6d2e
Revises: 3c0556168a16
Create Date: 2026-10-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "8f47a31c6d2e"
down_revision: Union[str, Sequence[str], None] = "3c0556168a16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tournament_participants",
        sa.Column("statistics_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tournament_participants", "statistics_snapshot")
