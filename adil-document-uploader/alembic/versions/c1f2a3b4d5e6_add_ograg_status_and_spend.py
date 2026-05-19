"""add judgments.ograg_status + extraction_spend_usd table

Revision ID: c1f2a3b4d5e6
Revises: b8d1c2e4f3a1
Create Date: 2026-05-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1f2a3b4d5e6"
down_revision: str | None = "b8d1c2e4f3a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "judgments",
        sa.Column(
            "ograg_status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
    )
    op.create_index("ix_judgments_ograg_status", "judgments", ["ograg_status"])

    op.create_table(
        "extraction_spend_usd",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("judgment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pass_name", sa.String(32), nullable=False),
        sa.Column("usd_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_extraction_spend_judgment_id",
        "extraction_spend_usd",
        ["judgment_id"],
    )
    op.create_index(
        "ix_extraction_spend_created_at",
        "extraction_spend_usd",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_extraction_spend_created_at", "extraction_spend_usd")
    op.drop_index("ix_extraction_spend_judgment_id", "extraction_spend_usd")
    op.drop_table("extraction_spend_usd")
    op.drop_index("ix_judgments_ograg_status", "judgments")
    op.drop_column("judgments", "ograg_status")
