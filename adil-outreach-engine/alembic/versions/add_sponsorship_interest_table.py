"""add sponsorship_interest table

Captures Wave-1 Q2-YES (sponsorship) signals extracted by the reply
classifier. Idempotent on (contact_id, raw_reply_event_id).

Revision ID: add_sponsor_001
Revises: add_dry_run_001
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "add_sponsor_001"
down_revision: str | Sequence[str] = "add_dry_run_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sponsorship_status = sa.Enum(
        "new",
        "contacted",
        "sponsoring",
        "declined",
        name="sponsorship_interest_status",
    )
    sponsorship_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "sponsorship_interests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "raw_reply_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outreach_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sponsorship_status,
            nullable=False,
            server_default="new",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "contact_id",
            "raw_reply_event_id",
            name="uq_sponsorship_contact_reply",
        ),
    )
    op.create_index(
        "ix_sponsorship_interests_contact_id",
        "sponsorship_interests",
        ["contact_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sponsorship_interests_contact_id", table_name="sponsorship_interests")
    op.drop_table("sponsorship_interests")
    sa.Enum(name="sponsorship_interest_status").drop(op.get_bind(), checkfirst=True)
