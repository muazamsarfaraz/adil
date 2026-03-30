"""Tests for graph assembly — compilation, routing, and full path integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from langgraph.graph import END

from app.agents.graph import (
    build_outreach_graph,
    classify_router,
    close_node,
    compile_outreach_graph,
    convert_node,
    gate_node,
    gate_router,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(**overrides) -> dict:
    """Create a minimal OutreachState dict for testing."""
    base = {
        "contact_id": "c-123",
        "campaign_id": "camp-456",
        "contact": {
            "name": "Jane Smith",
            "email": "jane@smithlaw.co.uk",
            "firm_name": "Smith & Partners",
            "website": "https://smithlaw.co.uk",
            "current_cadence_step": 0,
            "metadata": {"location": "Manchester"},
        },
        "campaign": {
            "auto_send": True,
            "llm_config": {
                "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
                "compose": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
                "classify": {"provider": "gemini", "model": "gemini-2.5-flash"},
            },
            "research_instructions": "Research this solicitor.",
            "compose_instructions": "Write a professional email.",
            "classify_instructions": "Classify the reply.",
            "templates": {
                "initial": {
                    "subject": "Intro from AskAdil",
                    "body": "Hello {{contact_name}},\n\n{{personalised_intro}}\n\nBest",
                },
                "follow_up_1": {
                    "subject": "Following up — AskAdil",
                    "body": "Hi {{contact_name}},\n\nJust following up.\n\nBest",
                },
            },
            "cadence": [
                {"step": 0, "wait_days": 0},
                {"step": 1, "wait_days": 3},
                {"step": 2, "wait_days": 7},
            ],
        },
        "research_data": {},
        "draft_subject": "",
        "draft_body": "",
        "reply_text": "",
        "classification": "",
        "current_step": "",
        "error": "",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Graph compilation tests
# ---------------------------------------------------------------------------


class TestGraphCompilation:
    """Test that the graph builds and compiles without errors."""

    def test_build_outreach_graph_returns_state_graph(self):
        """build_outreach_graph returns an uncompiled StateGraph."""
        from langgraph.graph import StateGraph

        graph = build_outreach_graph()
        assert isinstance(graph, StateGraph)

    def test_compile_outreach_graph_returns_compiled_graph(self):
        """compile_outreach_graph returns a compiled graph that can be invoked."""
        compiled = compile_outreach_graph()
        assert compiled is not None
        assert hasattr(compiled, "invoke")
        assert hasattr(compiled, "ainvoke")

    def test_graph_has_all_expected_nodes(self):
        """The graph contains all expected nodes."""
        graph = build_outreach_graph()
        node_names = set(graph.nodes.keys())
        expected = {"research", "compose", "gate", "send", "evaluate", "classify", "convert", "close"}
        assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"


# ---------------------------------------------------------------------------
# Gate node tests
# ---------------------------------------------------------------------------


class TestGateNode:
    """Tests for the gate_node function."""

    async def test_gate_approves_when_auto_send_true(self):
        """gate_node returns gate_approved when campaign.auto_send is True."""
        state = _make_state()
        state["campaign"]["auto_send"] = True
        result = await gate_node(state)
        assert result["current_step"] == "gate_approved"

    async def test_gate_pending_when_auto_send_false(self):
        """gate_node returns gate_pending when campaign.auto_send is False."""
        state = _make_state()
        state["campaign"]["auto_send"] = False
        result = await gate_node(state)
        assert result["current_step"] == "gate_pending"

    async def test_gate_pending_when_auto_send_missing(self):
        """gate_node defaults to gate_pending when auto_send is not set."""
        state = _make_state()
        state["campaign"].pop("auto_send", None)
        result = await gate_node(state)
        assert result["current_step"] == "gate_pending"


# ---------------------------------------------------------------------------
# Gate router tests
# ---------------------------------------------------------------------------


class TestGateRouter:
    """Tests for the gate_router function."""

    def test_routes_to_send_when_approved(self):
        state = {"current_step": "gate_approved"}
        assert gate_router(state) == "send"

    def test_routes_to_end_when_pending(self):
        state = {"current_step": "gate_pending"}
        assert gate_router(state) == END

    def test_routes_to_end_when_unknown(self):
        state = {"current_step": "something_else"}
        assert gate_router(state) == END


# ---------------------------------------------------------------------------
# Classify router tests
# ---------------------------------------------------------------------------


class TestClassifyRouter:
    """Tests for the classify_router function."""

    def test_routes_to_convert_on_interested(self):
        state = {"classification": "interested"}
        assert classify_router(state) == "convert"

    def test_routes_to_close_on_declined(self):
        state = {"classification": "declined"}
        assert classify_router(state) == "close"

    def test_routes_to_compose_on_question(self):
        state = {"classification": "question"}
        assert classify_router(state) == "compose"

    def test_routes_to_close_on_out_of_office(self):
        state = {"classification": "out_of_office"}
        assert classify_router(state) == "close"

    def test_routes_to_close_on_bounce(self):
        state = {"classification": "bounce"}
        assert classify_router(state) == "close"

    def test_routes_to_close_on_unknown(self):
        state = {"classification": "something_weird"}
        assert classify_router(state) == "close"

    def test_routes_to_compose_when_no_classification(self):
        """Defaults to 'question' -> compose when classification is missing."""
        state = {}
        assert classify_router(state) == "compose"


# ---------------------------------------------------------------------------
# Terminal node tests
# ---------------------------------------------------------------------------


class TestTerminalNodes:
    """Tests for convert_node and close_node."""

    async def test_convert_node_returns_current_step(self):
        state = _make_state()
        result = await convert_node(state)
        assert result["current_step"] == "convert"

    async def test_close_node_returns_current_step(self):
        state = _make_state()
        result = await close_node(state)
        assert result["current_step"] == "close"


# ---------------------------------------------------------------------------
# Full graph path integration tests (mocked LLM calls)
#
# Strategy: patch node functions at the module level BEFORE building the graph
# so that add_node captures the mock. Use ainvoke for async nodes.
# ---------------------------------------------------------------------------


class TestFullGraphPaths:
    """Integration tests for full graph paths with mocked node functions."""

    @patch("app.agents.graph.research_node", new_callable=AsyncMock)
    @patch("app.agents.graph.compose_node", new_callable=AsyncMock)
    @patch("app.agents.graph.send_node", new_callable=AsyncMock)
    async def test_initial_outreach_auto_send(self, mock_send, mock_compose, mock_research):
        """Initial outreach with auto_send=True: research -> compose -> gate -> send -> END."""
        mock_research.return_value = {
            "research_data": {"personalisation_hooks": ["Award winner"]},
            "current_step": "research",
        }
        mock_compose.return_value = {
            "draft_subject": "Hello Jane",
            "draft_body": "Great email body",
            "current_step": "compose",
        }
        mock_send.return_value = {"current_step": "send"}

        # Build graph AFTER patching so mocks are captured by add_node
        compiled = compile_outreach_graph()
        state = _make_state()
        state["campaign"]["auto_send"] = True

        result = await compiled.ainvoke(state)

        mock_research.assert_called_once()
        mock_compose.assert_called_once()
        mock_send.assert_called_once()
        assert result["current_step"] == "send"

    @patch("app.agents.graph.research_node", new_callable=AsyncMock)
    @patch("app.agents.graph.compose_node", new_callable=AsyncMock)
    async def test_initial_outreach_gate_interrupt(self, mock_compose, mock_research):
        """Initial outreach with auto_send=False: research -> compose -> gate -> END (interrupt)."""
        mock_research.return_value = {
            "research_data": {"personalisation_hooks": ["Award winner"]},
            "current_step": "research",
        }
        mock_compose.return_value = {
            "draft_subject": "Hello Jane",
            "draft_body": "Great email body",
            "current_step": "compose",
        }

        compiled = compile_outreach_graph()
        state = _make_state()
        state["campaign"]["auto_send"] = False

        result = await compiled.ainvoke(state)

        mock_research.assert_called_once()
        mock_compose.assert_called_once()
        # Gate should have interrupted — send should NOT have been called
        assert result["current_step"] == "gate_pending"

    @patch("app.agents.graph.classify_node", new_callable=AsyncMock)
    @patch("app.agents.graph.evaluate_node", new_callable=AsyncMock)
    async def test_evaluate_reply_interested_converts(self, mock_evaluate, mock_classify):
        """evaluate (reply) -> classify (interested) -> convert -> END."""
        mock_evaluate.return_value = {
            "current_step": "evaluate",
            "has_reply": True,
        }
        mock_classify.return_value = {
            "classification": "interested",
            "current_step": "classify",
        }

        # Build graph AFTER patching, then override entry point
        compiled = compile_outreach_graph(entry_point="evaluate")

        state = _make_state(reply_text="Yes, I'm interested!")
        result = await compiled.ainvoke(state)

        mock_evaluate.assert_called_once()
        mock_classify.assert_called_once()
        assert result["current_step"] == "convert"
        assert result["classification"] == "interested"

    @patch("app.agents.graph.classify_node", new_callable=AsyncMock)
    @patch("app.agents.graph.evaluate_node", new_callable=AsyncMock)
    async def test_evaluate_reply_declined_closes(self, mock_evaluate, mock_classify):
        """evaluate (reply) -> classify (declined) -> close -> END."""
        mock_evaluate.return_value = {
            "current_step": "evaluate",
            "has_reply": True,
        }
        mock_classify.return_value = {
            "classification": "declined",
            "current_step": "classify",
        }

        compiled = compile_outreach_graph(entry_point="evaluate")

        state = _make_state(reply_text="No thanks, not interested.")
        result = await compiled.ainvoke(state)

        mock_evaluate.assert_called_once()
        mock_classify.assert_called_once()
        assert result["current_step"] == "close"

    @patch("app.agents.graph.send_node", new_callable=AsyncMock)
    @patch("app.agents.graph.compose_node", new_callable=AsyncMock)
    @patch("app.agents.graph.classify_node", new_callable=AsyncMock)
    @patch("app.agents.graph.evaluate_node", new_callable=AsyncMock)
    async def test_evaluate_reply_question_composes_reply(self, mock_evaluate, mock_classify, mock_compose, mock_send):
        """evaluate (reply) -> classify (question) -> compose -> gate -> send -> END."""
        mock_evaluate.return_value = {
            "current_step": "evaluate",
            "has_reply": True,
        }
        mock_classify.return_value = {
            "classification": "question",
            "current_step": "classify",
        }
        mock_compose.return_value = {
            "draft_subject": "Re: Your question",
            "draft_body": "Great question — here's the answer.",
            "current_step": "compose",
        }
        mock_send.return_value = {"current_step": "send"}

        compiled = compile_outreach_graph(entry_point="evaluate")

        state = _make_state(reply_text="Can you tell me more?")
        state["campaign"]["auto_send"] = True
        result = await compiled.ainvoke(state)

        mock_evaluate.assert_called_once()
        mock_classify.assert_called_once()
        mock_compose.assert_called_once()
        mock_send.assert_called_once()
        assert result["current_step"] == "send"

    @patch("app.agents.graph.send_node", new_callable=AsyncMock)
    @patch("app.agents.graph.compose_node", new_callable=AsyncMock)
    @patch("app.agents.graph.evaluate_node", new_callable=AsyncMock)
    async def test_evaluate_no_reply_follow_up(self, mock_evaluate, mock_compose, mock_send):
        """evaluate (no reply, cadence remaining) -> compose -> gate -> send -> END."""
        mock_evaluate.return_value = {
            "current_step": "evaluate",
            "has_reply": False,
            "action": "follow_up",
        }
        mock_compose.return_value = {
            "draft_subject": "Following up",
            "draft_body": "Just wanted to follow up.",
            "current_step": "compose",
        }
        mock_send.return_value = {"current_step": "send"}

        compiled = compile_outreach_graph(entry_point="evaluate")

        state = _make_state()
        state["campaign"]["auto_send"] = True
        result = await compiled.ainvoke(state)

        mock_evaluate.assert_called_once()
        mock_compose.assert_called_once()
        mock_send.assert_called_once()
        assert result["current_step"] == "send"

    @patch("app.agents.graph.evaluate_node", new_callable=AsyncMock)
    async def test_evaluate_no_reply_cadence_exhausted_closes(self, mock_evaluate):
        """evaluate (no reply, cadence exhausted) -> close -> END."""
        mock_evaluate.return_value = {
            "current_step": "evaluate",
            "has_reply": False,
            "action": "close",
        }

        compiled = compile_outreach_graph(entry_point="evaluate")

        state = _make_state()
        result = await compiled.ainvoke(state)

        mock_evaluate.assert_called_once()
        assert result["current_step"] == "close"
