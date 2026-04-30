"""add solicitor_firms table

Revision ID: a3c9e1f70b22
Revises: f2b5ff000b4e
Create Date: 2026-04-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c9e1f70b22"
down_revision: str | None = "f2b5ff000b4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "solicitor_firms",
        sa.Column("sra_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("also_known_as", sa.Text(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("legal_aid", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("firm_type", sa.Text(), nullable=True),
        sa.Column("sra_url", sa.String(500), nullable=True),
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("sra_number"),
    )
    op.create_index("ix_solicitor_firms_city", "solicitor_firms", ["city"])
    op.create_index("ix_solicitor_firms_legal_aid", "solicitor_firms", ["legal_aid"])


def downgrade() -> None:
    op.drop_index("ix_solicitor_firms_legal_aid", "solicitor_firms")
    op.drop_index("ix_solicitor_firms_city", "solicitor_firms")
    op.drop_table("solicitor_firms")
