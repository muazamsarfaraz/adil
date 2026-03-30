"""add missing enum values to event_type and contact_status

Revision ID: add_enum_values_001
Revises: e94bb186bea8
Create Date: 2026-03-28
"""

from typing import Sequence, Union
from alembic import op

revision: str = "add_enum_values_001"
down_revision: Union[str, Sequence[str]] = "e94bb186bea8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing event_type enum values
    new_event_types = [
        "email_failed",
        "research_completed",
        "research_failed",
        "compose_failed",
        "evaluate_result",
        "marked_unresponsive",
        "webhook_sent",
        "webhook_failed",
        "email_delivered",
        "email_bounced",
        "reopened",
    ]
    for val in new_event_types:
        op.execute(f"ALTER TYPE event_type ADD VALUE IF NOT EXISTS '{val}'")

    # Add missing contact_status enum value
    op.execute("ALTER TYPE contact_status ADD VALUE IF NOT EXISTS 'bounced'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values
    pass
