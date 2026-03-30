"""add dry_run column to campaigns and email_dry_run enum value

Revision ID: add_dry_run_001
Revises: add_enum_values_001
Create Date: 2026-03-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "add_dry_run_001"
down_revision: Union[str, Sequence[str]] = "add_enum_values_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add dry_run column to campaigns table
    op.add_column(
        "campaigns",
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # Add email_dry_run to event_type enum
    op.execute("ALTER TYPE event_type ADD VALUE IF NOT EXISTS 'email_dry_run'")


def downgrade() -> None:
    # Remove dry_run column
    op.drop_column("campaigns", "dry_run")

    # PostgreSQL does not support removing enum values
