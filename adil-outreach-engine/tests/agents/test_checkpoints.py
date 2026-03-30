"""Tests for checkpoint persistence — save, load, deactivate, cleanup."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.agents.checkpoints import (
    cleanup_expired_checkpoints,
    deactivate_checkpoint,
    load_checkpoint,
    save_checkpoint,
)
from app.models.agent_checkpoint import AgentCheckpoint
from app.models.campaign import Campaign
from app.models.contact import Contact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_campaign_and_contact(db_session) -> tuple[str, str]:
    """Insert a campaign and contact so FK constraints are satisfied."""
    campaign_id = uuid.uuid4()
    contact_id = uuid.uuid4()

    campaign = Campaign(
        id=campaign_id,
        name="Test Campaign",
        slug=f"test-campaign-{campaign_id.hex[:8]}",
        goal="signup",
        templates={"initial": {"subject": "Hello", "body": "Hi there"}},
        cadence=[{"step": 0, "wait_days": 0}],
    )
    db_session.add(campaign)
    await db_session.flush()

    contact = Contact(
        id=contact_id,
        campaign_id=campaign_id,
        name="Test Contact",
        email="test@example.com",
    )
    db_session.add(contact)
    await db_session.flush()

    return str(campaign_id), str(contact_id)


# ---------------------------------------------------------------------------
# save_checkpoint tests
# ---------------------------------------------------------------------------


class TestSaveCheckpoint:
    """Tests for save_checkpoint."""

    async def test_creates_new_checkpoint(self, db_session):
        """save_checkpoint creates a new checkpoint row."""
        _, contact_id = await _seed_campaign_and_contact(db_session)
        run_id = str(uuid.uuid4())

        state = {"contact_id": contact_id, "current_step": "research", "research_data": {"hooks": ["award"]}}

        checkpoint_id = await save_checkpoint(
            db_session,
            contact_id=contact_id,
            run_id=run_id,
            graph_name="outreach",
            state=state,
            current_node="research",
        )

        assert checkpoint_id is not None
        # Verify in DB
        result = await db_session.execute(select(AgentCheckpoint).where(AgentCheckpoint.id == uuid.UUID(checkpoint_id)))
        row = result.scalar_one()
        assert row.graph_name == "outreach"
        assert row.current_node == "research"
        assert row.is_active is True
        assert row.state["current_step"] == "research"

    async def test_updates_existing_active_checkpoint(self, db_session):
        """save_checkpoint updates an existing active checkpoint for the same contact."""
        _, contact_id = await _seed_campaign_and_contact(db_session)
        run_id = str(uuid.uuid4())

        # First save
        state1 = {"current_step": "research"}
        id1 = await save_checkpoint(db_session, contact_id, run_id, "outreach", state1, "research")

        # Second save — should update, not insert
        state2 = {"current_step": "compose"}
        id2 = await save_checkpoint(db_session, contact_id, run_id, "outreach", state2, "compose")

        assert id1 == id2  # Same row was updated

        # Verify updated state
        result = await db_session.execute(select(AgentCheckpoint).where(AgentCheckpoint.id == uuid.UUID(id1)))
        row = result.scalar_one()
        assert row.current_node == "compose"
        assert row.state["current_step"] == "compose"

    async def test_handles_uuid_in_state(self, db_session):
        """save_checkpoint serialises UUIDs in state without error."""
        _, contact_id = await _seed_campaign_and_contact(db_session)
        run_id = str(uuid.uuid4())

        state = {"contact_id": str(uuid.uuid4()), "some_uuid": uuid.uuid4()}

        checkpoint_id = await save_checkpoint(db_session, contact_id, run_id, "outreach", state, "research")
        assert checkpoint_id is not None


# ---------------------------------------------------------------------------
# load_checkpoint tests
# ---------------------------------------------------------------------------


class TestLoadCheckpoint:
    """Tests for load_checkpoint."""

    async def test_loads_active_checkpoint(self, db_session):
        """load_checkpoint returns the active checkpoint state."""
        _, contact_id = await _seed_campaign_and_contact(db_session)
        run_id = str(uuid.uuid4())

        state = {"current_step": "compose", "draft_subject": "Hello"}
        await save_checkpoint(db_session, contact_id, run_id, "outreach", state, "compose")

        loaded = await load_checkpoint(db_session, contact_id)

        assert loaded is not None
        assert loaded["current_node"] == "compose"
        assert loaded["state"]["current_step"] == "compose"
        assert loaded["state"]["draft_subject"] == "Hello"
        assert loaded["is_active"] is True

    async def test_loads_by_run_id(self, db_session):
        """load_checkpoint with run_id loads that specific run."""
        _, contact_id = await _seed_campaign_and_contact(db_session)
        run_id = str(uuid.uuid4())

        state = {"current_step": "send"}
        await save_checkpoint(db_session, contact_id, run_id, "outreach", state, "send")

        loaded = await load_checkpoint(db_session, contact_id, run_id=run_id)

        assert loaded is not None
        assert loaded["run_id"] == run_id

    async def test_returns_none_when_no_checkpoint(self, db_session):
        """load_checkpoint returns None when no checkpoint exists for the contact."""
        # Use a random contact_id that doesn't exist in DB
        result = await load_checkpoint(db_session, str(uuid.uuid4()))
        assert result is None


# ---------------------------------------------------------------------------
# deactivate_checkpoint tests
# ---------------------------------------------------------------------------


class TestDeactivateCheckpoint:
    """Tests for deactivate_checkpoint."""

    async def test_deactivates_active_checkpoint(self, db_session):
        """deactivate_checkpoint marks the active checkpoint as inactive."""
        _, contact_id = await _seed_campaign_and_contact(db_session)
        run_id = str(uuid.uuid4())

        state = {"current_step": "gate_pending"}
        await save_checkpoint(db_session, contact_id, run_id, "outreach", state, "gate")

        await deactivate_checkpoint(db_session, contact_id)

        # Verify it's inactive
        loaded = await load_checkpoint(db_session, contact_id)
        assert loaded is None  # No active checkpoint

    async def test_deactivate_is_idempotent(self, db_session):
        """deactivate_checkpoint does not error when no active checkpoint exists."""
        _, contact_id = await _seed_campaign_and_contact(db_session)
        # No checkpoint exists — should not raise
        await deactivate_checkpoint(db_session, contact_id)


# ---------------------------------------------------------------------------
# cleanup_expired_checkpoints tests
# ---------------------------------------------------------------------------


class TestCleanupExpiredCheckpoints:
    """Tests for cleanup_expired_checkpoints."""

    async def test_deletes_old_inactive_checkpoints(self, db_session):
        """cleanup_expired_checkpoints removes inactive checkpoints older than the threshold."""
        _, contact_id = await _seed_campaign_and_contact(db_session)
        run_id = str(uuid.uuid4())
        contact_uuid = uuid.UUID(contact_id)

        # Create a checkpoint and deactivate it
        checkpoint = AgentCheckpoint(
            contact_id=contact_uuid,
            run_id=uuid.UUID(run_id),
            graph_name="outreach",
            state={"current_step": "close"},
            current_node="close",
            is_active=False,
        )
        db_session.add(checkpoint)
        await db_session.flush()

        # Manually backdate the updated_at
        checkpoint.updated_at = datetime.now(timezone.utc) - timedelta(days=60)
        await db_session.flush()
        await db_session.commit()

        deleted = await cleanup_expired_checkpoints(db_session, days=30)
        assert deleted == 1

    async def test_does_not_delete_recent_inactive_checkpoints(self, db_session):
        """cleanup_expired_checkpoints keeps recent inactive checkpoints."""
        _, contact_id = await _seed_campaign_and_contact(db_session)
        run_id = str(uuid.uuid4())

        state = {"current_step": "close"}
        await save_checkpoint(db_session, contact_id, run_id, "outreach", state, "close")
        await deactivate_checkpoint(db_session, contact_id)

        deleted = await cleanup_expired_checkpoints(db_session, days=30)
        assert deleted == 0

    async def test_does_not_delete_active_checkpoints(self, db_session):
        """cleanup_expired_checkpoints never deletes active checkpoints."""
        _, contact_id = await _seed_campaign_and_contact(db_session)
        run_id = str(uuid.uuid4())

        state = {"current_step": "gate_pending"}
        await save_checkpoint(db_session, contact_id, run_id, "outreach", state, "gate")

        deleted = await cleanup_expired_checkpoints(db_session, days=0)
        assert deleted == 0
