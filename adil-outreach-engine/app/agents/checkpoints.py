"""Checkpoint persistence — save/load/deactivate LangGraph state to agent_checkpoints table."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_checkpoint import AgentCheckpoint

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom JSON encoder for non-serialisable types
# ---------------------------------------------------------------------------


class _StateEncoder(json.JSONEncoder):
    """Handle UUID, datetime, and other non-serialisable types in state dicts."""

    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        return super().default(obj)


def _serialise_state(state: dict) -> dict:
    """Round-trip state through JSON to ensure it's serialisable for JSONB storage."""
    return json.loads(json.dumps(state, cls=_StateEncoder))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def save_checkpoint(
    db_session: AsyncSession,
    contact_id: str,
    run_id: str,
    graph_name: str,
    state: dict,
    current_node: str,
) -> str:
    """
    Save a LangGraph state checkpoint to the database.

    Serialises state to JSON and upserts the agent_checkpoints row
    for the active run.

    Returns the checkpoint ID (as string).
    """
    contact_uuid = uuid.UUID(contact_id) if isinstance(contact_id, str) else contact_id
    run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
    serialised = _serialise_state(state)

    # Look for existing active checkpoint for this contact
    stmt = select(AgentCheckpoint).where(
        AgentCheckpoint.contact_id == contact_uuid,
        AgentCheckpoint.is_active.is_(True),
    )
    result = await db_session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Update existing checkpoint
        existing.state = serialised
        existing.current_node = current_node
        existing.run_id = run_uuid
        existing.graph_name = graph_name
        existing.updated_at = datetime.now(timezone.utc)
        await db_session.flush()
        checkpoint_id = str(existing.id)
        logger.info("Updated checkpoint %s for contact %s at node '%s'", checkpoint_id, contact_id, current_node)
    else:
        # Insert new checkpoint
        checkpoint = AgentCheckpoint(
            contact_id=contact_uuid,
            run_id=run_uuid,
            graph_name=graph_name,
            state=serialised,
            current_node=current_node,
            is_active=True,
        )
        db_session.add(checkpoint)
        await db_session.flush()
        checkpoint_id = str(checkpoint.id)
        logger.info("Created checkpoint %s for contact %s at node '%s'", checkpoint_id, contact_id, current_node)

    await db_session.commit()
    return checkpoint_id


async def load_checkpoint(
    db_session: AsyncSession,
    contact_id: str,
    run_id: str | None = None,
) -> dict | None:
    """
    Load the active LangGraph checkpoint for a contact.

    If run_id is provided, load that specific run.
    Otherwise, load the active checkpoint.

    Returns the deserialised state dict, or None if no checkpoint exists.
    """
    contact_uuid = uuid.UUID(contact_id) if isinstance(contact_id, str) else contact_id

    if run_id is not None:
        run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
        stmt = select(AgentCheckpoint).where(
            AgentCheckpoint.contact_id == contact_uuid,
            AgentCheckpoint.run_id == run_uuid,
        )
    else:
        stmt = select(AgentCheckpoint).where(
            AgentCheckpoint.contact_id == contact_uuid,
            AgentCheckpoint.is_active.is_(True),
        )

    result = await db_session.execute(stmt)
    checkpoint = result.scalar_one_or_none()

    if checkpoint is None:
        logger.debug("No checkpoint found for contact %s", contact_id)
        return None

    logger.info(
        "Loaded checkpoint %s for contact %s at node '%s'",
        checkpoint.id,
        contact_id,
        checkpoint.current_node,
    )
    return {
        "id": str(checkpoint.id),
        "contact_id": str(checkpoint.contact_id),
        "run_id": str(checkpoint.run_id),
        "graph_name": checkpoint.graph_name,
        "state": checkpoint.state,
        "current_node": checkpoint.current_node,
        "is_active": checkpoint.is_active,
    }


async def deactivate_checkpoint(
    db_session: AsyncSession,
    contact_id: str,
) -> None:
    """
    Mark the active checkpoint for a contact as inactive.
    Called before starting a new run (retry).
    """
    contact_uuid = uuid.UUID(contact_id) if isinstance(contact_id, str) else contact_id

    stmt = (
        update(AgentCheckpoint)
        .where(
            AgentCheckpoint.contact_id == contact_uuid,
            AgentCheckpoint.is_active.is_(True),
        )
        .values(is_active=False, updated_at=datetime.now(timezone.utc))
    )
    await db_session.execute(stmt)
    await db_session.commit()
    logger.info("Deactivated checkpoint for contact %s", contact_id)


async def cleanup_expired_checkpoints(
    db_session: AsyncSession,
    days: int = 30,
) -> int:
    """
    Delete checkpoints older than `days` that are inactive.
    Returns the number of deleted rows.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = delete(AgentCheckpoint).where(
        AgentCheckpoint.is_active.is_(False),
        AgentCheckpoint.updated_at < cutoff,
    )
    result = await db_session.execute(stmt)
    await db_session.commit()
    deleted = result.rowcount
    logger.info("Cleaned up %d expired checkpoints (older than %d days)", deleted, days)
    return deleted
