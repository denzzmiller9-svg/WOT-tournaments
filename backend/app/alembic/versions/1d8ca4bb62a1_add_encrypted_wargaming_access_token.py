"""add encrypted Wargaming access token

Revision ID: 1d8ca4bb62a1
Revises: eaf5de8bef0b
Create Date: 2026-10-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1d8ca4bb62a1"
down_revision: Union[str, Sequence[str], None] = "eaf5de8bef0b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("wg_access_token_encrypted", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("wg_access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "wg_access_token_expires_at")
    op.drop_column("users", "wg_access_token_encrypted")
