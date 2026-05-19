"""add acts/act_sections/act_subsections tables

Revision ID: b8d1c2e4f3a1
Revises: a3c9e1f70b22
Create Date: 2026-05-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8d1c2e4f3a1"
down_revision: str | None = "a3c9e1f70b22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "acts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("leg_type", sa.String(20), nullable=False),
        sa.Column("leg_number", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("raw_xml", sa.Text(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("leg_type", "year", "leg_number", name="uq_acts_legref"),
    )

    op.create_table(
        "act_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("act_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.String(20), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("ordering", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["act_id"], ["acts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("act_id", "number", name="uq_act_sections_number"),
    )
    op.create_index("ix_act_sections_act_id", "act_sections", ["act_id"])

    op.create_table(
        "act_subsections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("ordering", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["section_id"], ["act_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("section_id", "number", name="uq_act_subsections_number"),
    )
    op.create_index("ix_act_subsections_section_id", "act_subsections", ["section_id"])


def downgrade() -> None:
    op.drop_index("ix_act_subsections_section_id", "act_subsections")
    op.drop_table("act_subsections")
    op.drop_index("ix_act_sections_act_id", "act_sections")
    op.drop_table("act_sections")
    op.drop_table("acts")
