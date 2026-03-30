"""Tests for agent nodes: research, compose, classify, send, evaluate."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


from app.agents.nodes.classify import classify_node, _parse_classification
from app.agents.nodes.compose import compose_node, _parse_email_response, _resolve_template
from app.agents.nodes.evaluate import evaluate_node, evaluate_router
from app.agents.nodes.research import research_node, _parse_research_json
from app.agents.nodes.send import send_node


# ---------------------------------------------------------------------------
# Helpers — reusable state fixtures
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
            "llm_config": {
                "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
                "compose": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
                "classify": {"provider": "gemini", "model": "gemini-2.5-flash"},
            },
            "research_instructions": "Research this solicitor thoroughly.",
            "compose_instructions": "Write a warm, professional email.",
            "classify_instructions": "Classify the reply accurately.",
            "templates": {
                "initial": {
                    "subject": "Introduction from AskAdil",
                    "body": "Hello {{contact_name}},\n\n{{personalised_intro}}\n\nBest regards",
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


def _mock_llm_response(content: str):
    """Create a mock LLM response with .content and no tool_calls."""
    resp = MagicMock()
    resp.content = content
    resp.tool_calls = []
    return resp


# ---------------------------------------------------------------------------
# Research node tests
# ---------------------------------------------------------------------------


class TestResearchNode:
    """Tests for the research_node function."""

    @patch("app.agents.nodes.research.get_llm")
    async def test_research_returns_enriched_data(self, mock_get_llm):
        """research_node returns research_data with personalisation hooks."""
        mock_response = _mock_llm_response(
            '{"personalisation_hooks": ["Award-winning family law firm", '
            '"Recently expanded Manchester office"], '
            '"firm_description": "Leading family law practice", '
            '"sra_status": "Active - SRA 123456", '
            '"key_people": ["Jane Smith"], '
            '"recent_news": "Won Legal 500 award 2025", '
            '"best_contact_email": "jane@smithlaw.co.uk"}'
        )
        # Use MagicMock for bind_tools (sync), AsyncMock for ainvoke (async)
        mock_llm_with_tools = MagicMock()
        mock_llm_with_tools.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm_with_tools)
        mock_get_llm.return_value = mock_llm

        state = _make_state()
        result = await research_node(state)

        assert result["current_step"] == "research"
        assert "research_data" in result
        assert len(result["research_data"]["personalisation_hooks"]) == 2
        assert result["research_data"]["firm_description"] == "Leading family law practice"

    @patch("app.agents.nodes.research.get_llm")
    async def test_research_handles_tool_calls(self, mock_get_llm):
        """research_node processes tool calls in ReAct loop."""
        # First response has a tool call
        tool_call_response = MagicMock()
        tool_call_response.content = ""
        tool_call_response.tool_calls = [
            {"name": "scrape_website", "args": {"url": "https://smithlaw.co.uk"}, "id": "tc-1"}
        ]

        # Second response is the final answer (no tool calls)
        final_response = _mock_llm_response(
            '{"personalisation_hooks": ["Great website"], '
            '"firm_description": "A law firm", '
            '"sra_status": "not checked", '
            '"key_people": [], '
            '"recent_news": "", '
            '"best_contact_email": "jane@smithlaw.co.uk"}'
        )

        # Use MagicMock for bind_tools (sync), AsyncMock for ainvoke (async)
        mock_llm_with_tools = MagicMock()
        mock_llm_with_tools.ainvoke = AsyncMock(side_effect=[tool_call_response, final_response])
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm_with_tools)
        mock_get_llm.return_value = mock_llm

        with patch("app.agents.nodes.research.scrape_website") as mock_scraper:
            mock_scraper.name = "scrape_website"
            mock_scraper.ainvoke = AsyncMock(return_value="Title: Smith Law\nContent: Great firm")

            # Patch _TOOLS to use our mock
            with patch("app.agents.nodes.research._TOOLS", [mock_scraper]):
                state = _make_state()
                result = await research_node(state)

        assert result["current_step"] == "research"
        assert "research_data" in result
        mock_scraper.ainvoke.assert_called_once()

    @patch("app.agents.nodes.research.get_llm")
    async def test_research_error_returns_fallback(self, mock_get_llm):
        """research_node returns fallback data on error instead of crashing."""
        mock_get_llm.side_effect = Exception("LLM unavailable")

        state = _make_state()
        result = await research_node(state)

        assert result["current_step"] == "research"
        assert "error" in result["research_data"]
        assert result["research_data"]["personalisation_hooks"] == []

    @patch("app.agents.nodes.research.get_llm")
    async def test_research_continues_after_tool_error(self, mock_get_llm):
        """research_node continues with remaining tools when one tool fails."""
        # First response: two tool calls (scraper fails, SRA succeeds)
        tool_call_response = MagicMock()
        tool_call_response.content = ""
        tool_call_response.tool_calls = [
            {"name": "scrape_website", "args": {"url": "https://smithlaw.co.uk"}, "id": "tc-1"},
            {"name": "search_sra_register", "args": {"name": "Jane Smith"}, "id": "tc-2"},
        ]

        # Final response after tool results
        final_response = _mock_llm_response(
            '{"personalisation_hooks": ["SRA registered solicitor"], '
            '"firm_description": "Gathered from SRA data", '
            '"sra_status": "Active", '
            '"key_people": ["Jane Smith"], '
            '"recent_news": "", '
            '"best_contact_email": "jane@smithlaw.co.uk"}'
        )

        mock_llm_with_tools = MagicMock()
        mock_llm_with_tools.ainvoke = AsyncMock(side_effect=[tool_call_response, final_response])
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm_with_tools)
        mock_get_llm.return_value = mock_llm

        mock_scraper = MagicMock()
        mock_scraper.name = "scrape_website"
        mock_scraper.ainvoke = AsyncMock(side_effect=TypeError("expected string or bytes-like object, got 'list'"))

        mock_sra = MagicMock()
        mock_sra.name = "search_sra_register"
        mock_sra.ainvoke = AsyncMock(return_value="SRA Status: Active - Jane Smith - ID 123456")

        with patch("app.agents.nodes.research._TOOLS", [mock_scraper, mock_sra]):
            state = _make_state()
            result = await research_node(state)

        # Should succeed with partial data, not return error
        assert result["current_step"] == "research"
        assert "error" not in result.get("research_data", {})
        assert len(result["research_data"]["personalisation_hooks"]) >= 1
        # Both tools should have been called
        mock_scraper.ainvoke.assert_called_once()
        mock_sra.ainvoke.assert_called_once()

    @patch("app.agents.nodes.research.get_llm")
    async def test_research_uses_campaign_llm_config(self, mock_get_llm):
        """research_node uses the LLM config from campaign."""
        mock_response = _mock_llm_response('{"personalisation_hooks": [], "firm_description": ""}')
        mock_llm_with_tools = MagicMock()
        mock_llm_with_tools.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm_with_tools)
        mock_get_llm.return_value = mock_llm

        state = _make_state()
        await research_node(state)

        mock_get_llm.assert_called_once_with(
            {"provider": "gemini", "model": "gemini-2.5-flash"},
            temperature=0.2,
        )


class TestParseResearchJson:
    """Tests for _parse_research_json helper."""

    def test_parses_valid_json(self):
        result = _parse_research_json('{"personalisation_hooks": ["hook1"], "firm_description": "A firm"}')
        assert result["personalisation_hooks"] == ["hook1"]

    def test_parses_json_in_code_block(self):
        text = '```json\n{"personalisation_hooks": ["hook1"]}\n```'
        result = _parse_research_json(text)
        assert result["personalisation_hooks"] == ["hook1"]

    def test_parses_json_embedded_in_text(self):
        text = 'Here is the data:\n{"personalisation_hooks": ["hook1"]}\nDone.'
        result = _parse_research_json(text)
        assert result["personalisation_hooks"] == ["hook1"]

    def test_fallback_on_invalid_json(self):
        result = _parse_research_json("This is not JSON at all")
        assert result["personalisation_hooks"] == []
        assert "raw_response" in result


# ---------------------------------------------------------------------------
# Compose node tests
# ---------------------------------------------------------------------------


class TestComposeNode:
    """Tests for the compose_node function."""

    @patch("app.agents.nodes.compose.get_llm")
    async def test_compose_returns_subject_and_body(self, mock_get_llm):
        """compose_node returns draft_subject and draft_body."""
        mock_llm = AsyncMock()
        mock_response = _mock_llm_response(
            "SUBJECT: Introduction from AskAdil — Legal Tech for Smith & Partners\n"
            "BODY: Dear Jane,\n\n"
            "I noticed Smith & Partners recently won a Legal 500 award — congratulations!\n\n"
            "Best regards,\nAskAdil Team"
        )
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        state = _make_state(
            research_data={
                "personalisation_hooks": ["Won Legal 500 award"],
                "firm_description": "Family law firm",
            }
        )
        result = await compose_node(state)

        assert result["current_step"] == "compose"
        assert "AskAdil" in result["draft_subject"]
        assert "Jane" in result["draft_body"]
        assert "Legal 500" in result["draft_body"]

    @patch("app.agents.nodes.compose.get_llm")
    async def test_compose_error_returns_empty_drafts(self, mock_get_llm):
        """compose_node returns empty drafts on error instead of crashing."""
        mock_get_llm.side_effect = Exception("LLM unavailable")

        state = _make_state()
        result = await compose_node(state)

        assert result["current_step"] == "compose"
        assert result["draft_subject"] == ""
        assert result["draft_body"] == ""
        assert "error" in result

    @patch("app.agents.nodes.compose.get_llm")
    async def test_compose_uses_campaign_llm_config(self, mock_get_llm):
        """compose_node uses the compose LLM config from campaign."""
        mock_llm = AsyncMock()
        mock_response = _mock_llm_response("SUBJECT: Test\nBODY: Hello")
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        state = _make_state()
        await compose_node(state)

        mock_get_llm.assert_called_once_with(
            {"provider": "anthropic", "model": "claude-sonnet-4-6"},
            temperature=0.7,
        )

    @patch("app.agents.nodes.compose.get_llm")
    async def test_compose_includes_sender_name_in_prompt(self, mock_get_llm):
        """compose_node passes sender_name from campaign to LLM prompt, avoiding placeholders."""
        mock_llm = AsyncMock()
        mock_response = _mock_llm_response(
            "SUBJECT: Introduction from AskAdil\n" "BODY: Dear Jane,\n\nGreat firm!\n\nBest regards,\nMuazam Ali"
        )
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        state = _make_state()
        state["campaign"]["sender_name"] = "Muazam Ali"
        _result = await compose_node(state)

        # Verify sender_name was passed in the system prompt
        call_args = mock_llm.ainvoke.call_args[0][0]
        system_content = call_args[0].content
        assert "Muazam Ali" in system_content
        assert "never use placeholders" in system_content.lower() or "Never use placeholders" in system_content

    @patch("app.agents.nodes.compose.get_llm")
    async def test_compose_falls_back_to_campaign_name_when_no_sender_name(self, mock_get_llm):
        """compose_node uses campaign name as fallback when sender_name is not set."""
        mock_llm = AsyncMock()
        mock_response = _mock_llm_response("SUBJECT: Test\nBODY: Hello")
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        state = _make_state()
        state["campaign"]["name"] = "AskAdil Outreach"
        # No sender_name key
        state["campaign"].pop("sender_name", None)
        _result = await compose_node(state)

        call_args = mock_llm.ainvoke.call_args[0][0]
        system_content = call_args[0].content
        assert "AskAdil Outreach" in system_content


class TestResolveTemplate:
    """Tests for _resolve_template helper."""

    def test_selects_initial_template_for_step_0(self):
        campaign = {
            "templates": {
                "initial": {"subject": "Hello", "body": "Initial body"},
                "follow_up_1": {"subject": "Follow up", "body": "FU body"},
            }
        }
        contact = {"current_cadence_step": 0}
        subject, body = _resolve_template(campaign, contact)
        assert subject == "Hello"
        assert body == "Initial body"

    def test_selects_follow_up_template_for_step_1(self):
        campaign = {
            "templates": {
                "initial": {"subject": "Hello", "body": "Initial body"},
                "follow_up_1": {"subject": "Follow up", "body": "FU body"},
            }
        }
        contact = {"current_cadence_step": 1}
        subject, body = _resolve_template(campaign, contact)
        assert subject == "Follow up"
        assert body == "FU body"

    def test_falls_back_to_defaults_when_no_templates(self):
        campaign = {"templates": {}}
        contact = {"current_cadence_step": 0}
        subject, body = _resolve_template(campaign, contact)
        assert "sender_name" in subject  # default template
        assert "contact_name" in body


class TestParseEmailResponse:
    """Tests for _parse_email_response helper."""

    def test_parses_standard_format(self):
        text = "SUBJECT: Test Subject\nBODY: Hello there,\n\nThis is the body."
        subject, body = _parse_email_response(text)
        assert subject == "Test Subject"
        assert "Hello there" in body

    def test_fallback_on_unparseable_response(self):
        text = "Just some random text without format markers."
        subject, body = _parse_email_response(text)
        # Should still return something (first line as subject)
        assert subject != ""


# ---------------------------------------------------------------------------
# Classify node tests
# ---------------------------------------------------------------------------


class TestClassifyNode:
    """Tests for the classify_node function."""

    @patch("app.agents.nodes.classify.get_llm")
    async def test_classify_returns_valid_category(self, mock_get_llm):
        """classify_node returns a valid classification category."""
        mock_llm = AsyncMock()
        mock_response = _mock_llm_response(
            '{"category": "interested", "confidence": 0.95, ' '"extracted_data": {"next_step": "schedule call"}}'
        )
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        state = _make_state(reply_text="Yes, I'd love to learn more about AskAdil!")
        result = await classify_node(state)

        assert result["current_step"] == "classify"
        assert result["classification"] == "interested"

    @patch("app.agents.nodes.classify.get_llm")
    async def test_classify_declined(self, mock_get_llm):
        """classify_node correctly identifies a declined reply."""
        mock_llm = AsyncMock()
        mock_response = _mock_llm_response('{"category": "declined", "confidence": 0.9, "extracted_data": {}}')
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        state = _make_state(reply_text="No thank you, not interested.")
        result = await classify_node(state)

        assert result["classification"] == "declined"

    @patch("app.agents.nodes.classify.get_llm")
    async def test_classify_out_of_office(self, mock_get_llm):
        """classify_node correctly identifies an out-of-office reply."""
        mock_llm = AsyncMock()
        mock_response = _mock_llm_response(
            '{"category": "out_of_office", "confidence": 0.99, ' '"extracted_data": {"return_date": "2026-04-05"}}'
        )
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        state = _make_state(reply_text="I am out of the office until 5th April. I will respond on my return.")
        result = await classify_node(state)

        assert result["classification"] == "out_of_office"

    @patch("app.agents.nodes.classify.get_llm")
    async def test_classify_fallback_on_json_parse_failure(self, mock_get_llm):
        """classify_node falls back to string matching when JSON parse fails."""
        mock_llm = AsyncMock()
        # LLM returns non-JSON response with category keyword
        mock_response = _mock_llm_response("Based on analysis, this reply is clearly a bounce notification.")
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        state = _make_state(reply_text="Delivery failed: address not found")
        result = await classify_node(state)

        assert result["classification"] == "bounce"

    @patch("app.agents.nodes.classify.get_llm")
    async def test_classify_ultimate_fallback_is_question(self, mock_get_llm):
        """classify_node defaults to 'question' when all parsing fails."""
        mock_llm = AsyncMock()
        # LLM returns completely unparseable response
        mock_response = _mock_llm_response("I cannot determine the category.")
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        state = _make_state(reply_text="Some ambiguous reply")
        result = await classify_node(state)

        assert result["classification"] == "question"

    @patch("app.agents.nodes.classify.get_llm")
    async def test_classify_error_defaults_to_question(self, mock_get_llm):
        """classify_node defaults to 'question' on error."""
        mock_get_llm.side_effect = Exception("LLM unavailable")

        state = _make_state(reply_text="Some reply text")
        result = await classify_node(state)

        assert result["classification"] == "question"
        assert "error" in result

    async def test_classify_empty_reply_returns_question(self):
        """classify_node returns 'question' for empty reply_text."""
        state = _make_state(reply_text="")
        result = await classify_node(state)

        assert result["classification"] == "question"


class TestParseClassification:
    """Tests for _parse_classification helper."""

    def test_parses_valid_json(self):
        result = _parse_classification('{"category": "interested", "confidence": 0.9, "extracted_data": {}}')
        assert result["category"] == "interested"
        assert result["confidence"] == 0.9

    def test_parses_json_in_code_block(self):
        text = '```json\n{"category": "declined", "confidence": 0.8, "extracted_data": {}}\n```'
        result = _parse_classification(text)
        assert result["category"] == "declined"

    def test_string_match_fallback(self):
        result = _parse_classification("This is clearly an out_of_office auto-reply.")
        assert result["category"] == "out_of_office"
        assert result["confidence"] == 0.5

    def test_ultimate_fallback_is_question(self):
        result = _parse_classification("Completely unrelated text with no keywords.")
        assert result["category"] == "question"
        assert result["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Send node tests
# ---------------------------------------------------------------------------


class TestSendNode:
    """Tests for the send_node placeholder function."""

    async def test_send_returns_updated_state(self):
        """send_node returns current_step='send'."""
        state = _make_state(
            draft_subject="Test Subject",
            draft_body="Test body content",
        )
        result = await send_node(state)

        assert result == {"current_step": "send"}

    async def test_send_handles_missing_email(self):
        """send_node works even when contact email is missing."""
        state = _make_state()
        state["contact"] = {"name": "Test"}  # no email key
        result = await send_node(state)

        assert result == {"current_step": "send"}


# ---------------------------------------------------------------------------
# Evaluate node tests
# ---------------------------------------------------------------------------


class TestEvaluateNode:
    """Tests for the evaluate_node function."""

    async def test_evaluate_routes_to_classify_when_reply_exists(self):
        """evaluate_node returns has_reply=True when reply_text is populated."""
        state = _make_state(reply_text="Yes, tell me more!")
        result = await evaluate_node(state)

        assert result["current_step"] == "evaluate"
        assert result["has_reply"] is True

    async def test_evaluate_routes_to_follow_up_when_cadence_remaining(self):
        """evaluate_node returns action='follow_up' when cadence steps remain."""
        state = _make_state(reply_text="")
        state["contact"]["current_cadence_step"] = 0  # step 0 of 3 steps
        result = await evaluate_node(state)

        assert result["current_step"] == "evaluate"
        assert result["has_reply"] is False
        assert result["action"] == "follow_up"

    async def test_evaluate_routes_to_close_when_cadence_exhausted(self):
        """evaluate_node returns action='close' when all cadence steps done."""
        state = _make_state(reply_text="")
        state["contact"]["current_cadence_step"] = 2  # last step (index 2 of 3)
        result = await evaluate_node(state)

        assert result["current_step"] == "evaluate"
        assert result["has_reply"] is False
        assert result["action"] == "close"

    async def test_evaluate_routes_to_close_when_no_cadence(self):
        """evaluate_node routes to close when campaign has no cadence defined."""
        state = _make_state(reply_text="")
        state["campaign"]["cadence"] = []
        result = await evaluate_node(state)

        assert result["has_reply"] is False
        assert result["action"] == "close"


class TestEvaluateRouter:
    """Tests for the evaluate_router function."""

    def test_routes_to_classify_on_reply(self):
        state = {"has_reply": True}
        assert evaluate_router(state) == "classify"

    def test_routes_to_compose_on_follow_up(self):
        state = {"has_reply": False, "action": "follow_up"}
        assert evaluate_router(state) == "compose"

    def test_routes_to_close_on_exhausted(self):
        state = {"has_reply": False, "action": "close"}
        assert evaluate_router(state) == "close"

    def test_routes_to_close_by_default(self):
        state = {"has_reply": False}
        assert evaluate_router(state) == "close"

    def test_routes_to_close_on_empty_state(self):
        state = {}
        assert evaluate_router(state) == "close"
