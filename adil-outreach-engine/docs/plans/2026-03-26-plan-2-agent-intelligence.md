# Plan 2: Agent Intelligence (LangGraph)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the LangGraph agent graph that powers intelligent outreach — research targets, compose personalised emails, classify responses, and decide next actions.

**Architecture:** LangGraph StateGraph with configurable LLM per node. Agents use tools for web scraping, SRA register lookup, and web search. State checkpointed to PostgreSQL for crash recovery.

**Tech Stack:** LangGraph, langchain-google-genai, langchain-anthropic, langchain-openai, httpx, BeautifulSoup4

**Depends on:** Plan 1 (models and schemas must exist) — `Campaign`, `Contact`, `OutreachEvent`, `AgentCheckpoint` SQLAlchemy models and Pydantic schemas.

---

## Task 1: OutreachState TypedDict

**File:** `app/agents/state.py`

Define the LangGraph state schema that flows through every node in the graph.

- [ ] Create `app/agents/__init__.py` (empty)
- [ ] Create `app/agents/state.py` with the `OutreachState` TypedDict:

```python
from typing import TypedDict, Optional

class OutreachState(TypedDict):
    # Identifiers
    contact_id: str
    campaign_id: str

    # Full records (loaded at graph start)
    contact: dict              # contact record from DB
    campaign: dict             # campaign config from DB

    # Research output
    research_data: dict        # populated by research node — personalisation hooks, SRA status, key info

    # Compose output
    draft_subject: str         # populated by compose node
    draft_body: str            # populated by compose node

    # Reply handling
    reply_text: str            # populated when reply received (from inbound webhook)
    classification: str        # populated by classify node — one of: interested, declined, question, out_of_office, bounce

    # Graph state tracking
    current_step: str          # current node name in the graph
    error: str                 # last error message if any
```

- [ ] Verify the state matches Section 5.1 of the design spec exactly

**Acceptance:** `OutreachState` is importable from `app.agents.state` and all fields match the spec.

---

## Task 2: LLM Provider Abstraction

**File:** `app/agents/llm.py`

Create a factory function that returns a LangChain `BaseChatModel` for any supported provider, driven by campaign-level `llm_config`.

- [ ] Create `app/agents/llm.py`
- [ ] Implement `get_llm()` function per Section 5.4 of the spec:

```python
from langchain_core.language_models.chat_models import BaseChatModel

def get_llm(config: dict, **kwargs) -> BaseChatModel:
    """
    Instantiate a LangChain chat model from campaign llm_config.

    Args:
        config: Dict with "provider" and "model" keys.
                e.g. {"provider": "gemini", "model": "gemini-2.5-flash"}
        **kwargs: Passed through to the model constructor (temperature, max_tokens, etc.)

    Returns:
        BaseChatModel instance.

    Raises:
        ValueError: If provider is not supported.
    """
    provider = config["provider"]
    model = config["model"]

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, **kwargs)
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, **kwargs)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, **kwargs)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
```

- [ ] Add `get_default_llm_config()` helper that returns sensible defaults:

```python
DEFAULT_LLM_CONFIG = {
    "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "compose": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    "classify": {"provider": "gemini", "model": "gemini-2.5-flash"},
}

def get_default_llm_config() -> dict:
    return DEFAULT_LLM_CONFIG.copy()
```

- [ ] Ensure environment variable names follow convention: `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (these are auto-read by the langchain provider packages)

**Acceptance:** `get_llm({"provider": "gemini", "model": "gemini-2.5-flash"})` returns a `ChatGoogleGenerativeAI` instance. Same for anthropic and openai. Unknown provider raises `ValueError`.

---

## Task 3: Scraper Tool

**File:** `app/agents/tools/scraper.py`

Async website scraping tool for the research agent. Uses httpx for HTTP and BeautifulSoup for HTML parsing.

- [ ] Create `app/agents/tools/__init__.py` (empty)
- [ ] Create `app/agents/tools/scraper.py`
- [ ] Implement `scrape_website` as a LangChain `@tool`:

```python
from langchain_core.tools import tool

@tool
async def scrape_website(url: str) -> str:
    """Scrape a website and extract text content, contact details, and key information.

    Args:
        url: The URL to scrape.

    Returns:
        Extracted text content with contact details and key information.
    """
```

- [ ] Implementation details:
  - Use `httpx.AsyncClient` with a 15-second timeout and browser-like `User-Agent` header
  - Parse HTML with `BeautifulSoup(html, "html.parser")`
  - Extract: page title, meta description, main text content (strip nav/footer/script/style tags)
  - Extract contact details: emails (regex), phone numbers (regex), addresses
  - Truncate output to 4000 characters to stay within LLM context limits
  - Return structured text: `"Title: ...\nDescription: ...\nContact: ...\nContent: ..."`
  - Handle errors gracefully: connection errors, timeouts, non-200 status codes all return descriptive error strings (never raise — the LLM agent needs the error message)
- [ ] Add rate limiting awareness: respect `robots.txt` is optional for v1 but add a `# TODO: robots.txt` comment

**Acceptance:** `await scrape_website.ainvoke({"url": "https://example.com"})` returns extracted text content. Timeouts and errors return error strings, not exceptions.

---

## Task 4: SRA Register Tool

**File:** `app/agents/tools/sra.py`

Query the Solicitors Regulation Authority (SRA) API to verify solicitor registration status.

- [ ] Create `app/agents/tools/sra.py`
- [ ] Implement `search_sra_register` as a LangChain `@tool`:

```python
@tool
async def search_sra_register(name: str, firm: str = "") -> str:
    """Search the SRA (Solicitors Regulation Authority) register for a solicitor or firm.

    Args:
        name: The solicitor or firm name to search for.
        firm: Optional firm name to narrow results.

    Returns:
        SRA registration details including SRA number and regulatory status.
    """
```

- [ ] Implementation details:
  - SRA API endpoint: `https://www.sra.org.uk/consumers/register/search/` (or their JSON API if available)
  - Use `httpx.AsyncClient` with 10-second timeout
  - Query parameters: `name`, `firm` (if provided)
  - Parse response to extract: SRA number, status (active/inactive/suspended), firm name, address
  - Return structured text: `"SRA Number: ...\nStatus: ...\nFirm: ...\nAddress: ..."`
  - If no results: return `"No SRA registration found for {name}"`
  - Handle API errors gracefully (return error string)
- [ ] Add fallback: if the SRA API is unavailable, return a message saying the lookup failed and the agent should proceed without it

**Acceptance:** `await search_sra_register.ainvoke({"name": "John Smith", "firm": "Smith & Co"})` returns SRA details or a "not found" message. Never raises exceptions to the caller.

---

## Task 5: Web Search Tool

**File:** `app/agents/tools/web_search.py`

Web search tool for the research agent to find recent news, awards, and other relevant information about a contact or firm.

- [ ] Create `app/agents/tools/web_search.py`
- [ ] Implement `search_web` as a LangChain `@tool`:

```python
@tool
async def search_web(query: str) -> str:
    """Search the web for recent news, awards, and information about a person or firm.

    Args:
        query: The search query string.

    Returns:
        Search results with titles, snippets, and URLs.
    """
```

- [ ] Implementation details:
  - Use a configurable search backend via `SEARCH_PROVIDER` env var (default: `"serper"`)
  - **Serper (default):** POST to `https://google.serper.dev/search` with `SERPER_API_KEY`
  - **Fallback (no API key):** Return a message saying web search is unavailable and to proceed without it
  - Parse results: extract top 5 results with title, snippet, URL
  - Format as readable text for the LLM
  - Truncate total output to 3000 characters
- [ ] Handle errors gracefully (return error string, never raise)

**Acceptance:** `await search_web.ainvoke({"query": "Aramas Family Law Manchester"})` returns formatted search results or a graceful fallback message.

---

## Task 6: Research Node

**File:** `app/agents/nodes/research.py`

The research agent node enriches contact data using the three tools (scraper, SRA, web search).

- [ ] Create `app/agents/nodes/__init__.py` (empty)
- [ ] Create `app/agents/nodes/research.py`
- [ ] Implement the `research_node` function:

```python
async def research_node(state: OutreachState) -> dict:
    """
    Research agent node. Uses tools to enrich contact data.

    Reads: state["contact"], state["campaign"]
    Writes: state["research_data"], state["current_step"]
    """
```

- [ ] Implementation details:
  - Extract LLM config: `campaign["llm_config"]["research"]` (fall back to `DEFAULT_LLM_CONFIG["research"]`)
  - Instantiate LLM via `get_llm(config)`
  - Bind tools: `[scrape_website, search_sra_register, search_web]`
  - Build system prompt from `campaign["research_instructions"]` with context:
    ```
    You are a research agent. Your job is to research the following contact and gather
    personalisation hooks for an outreach email.

    Contact: {contact name, email, firm, website}

    Instructions from campaign manager:
    {campaign.research_instructions}

    Use the available tools to:
    1. Scrape the firm's website (if provided) for key information
    2. Check the SRA register for regulatory status
    3. Search the web for recent news, awards, or notable mentions

    Return a JSON object with:
    - "personalisation_hooks": list of 2-4 specific hooks for email personalisation
    - "firm_description": brief description of the firm
    - "sra_status": SRA registration details (or "not checked")
    - "key_people": any key people identified
    - "recent_news": any recent news or awards
    - "best_contact_email": the best email to reach the contact (from website if different)
    ```
  - Use `llm.bind_tools(tools).ainvoke(messages)` in a ReAct-style loop (or use LangGraph's built-in `create_react_agent` for tool calling)
  - Parse the LLM's final response as JSON into `research_data`
  - Return `{"research_data": parsed_data, "current_step": "research"}`
- [ ] Error handling: if research fails, set `research_data` to `{"error": str(e), "personalisation_hooks": []}` and continue (don't block the pipeline)

**Acceptance:** Given a state with a contact that has a website, the research node calls scrape_website, optionally calls SRA and web search, and returns enriched `research_data`.

---

## Task 7: Compose Node

**File:** `app/agents/nodes/compose.py`

Generates a personalised email from the campaign template plus research data. No tools — pure LLM generation.

- [ ] Create `app/agents/nodes/compose.py`
- [ ] Implement the `compose_node` function:

```python
async def compose_node(state: OutreachState) -> dict:
    """
    Compose agent node. Generates personalised email from template + research data.

    Reads: state["contact"], state["campaign"], state["research_data"]
    Writes: state["draft_subject"], state["draft_body"], state["current_step"]
    """
```

- [ ] Implementation details:
  - Extract LLM config: `campaign["llm_config"]["compose"]` (fall back to `DEFAULT_LLM_CONFIG["compose"]`)
  - Instantiate LLM via `get_llm(config)`
  - Determine which template to use based on `contact["current_cadence_step"]`:
    - Step 0 → `campaign["templates"]["initial"]`
    - Step N → `campaign["templates"]["follow_up_N"]`
  - Build system prompt from `campaign["compose_instructions"]`:
    ```
    You are an email composition agent. Write a personalised email using the template
    and research data provided.

    Instructions from campaign manager:
    {campaign.compose_instructions}

    Template:
    Subject: {template.subject}
    Body: {template.body}

    Research data:
    {research_data as formatted text}

    Contact details:
    Name: {contact.name}
    Firm: {contact.firm_name}
    Location: {contact.metadata.location if present}

    Outreach history:
    {previous outreach events if any, for follow-ups}

    Rules:
    - Replace all {{variable}} placeholders with appropriate content
    - {{personalised_intro}} should be 1-2 sentences referencing specific research findings
    - Keep the email warm, professional, and concise
    - Do not invent facts not present in the research data
    - Return ONLY the email in this format:
      SUBJECT: <subject line>
      BODY: <email body>
    ```
  - Parse LLM response to extract subject and body
  - Return `{"draft_subject": subject, "draft_body": body, "current_step": "compose"}`
- [ ] No tools bound — pure generation task
- [ ] Error handling: if compose fails, set `error` in state and return

**Acceptance:** Given state with contact, campaign templates, and research_data, the compose node returns a personalised `draft_subject` and `draft_body`.

---

## Task 8: Classify Node

**File:** `app/agents/nodes/classify.py`

Classifies reply text into categories. No tools — pure classification.

- [ ] Create `app/agents/nodes/classify.py`
- [ ] Implement the `classify_node` function:

```python
async def classify_node(state: OutreachState) -> dict:
    """
    Classify agent node. Classifies reply text into categories.

    Reads: state["reply_text"], state["campaign"]
    Writes: state["classification"], state["current_step"]
    """
```

- [ ] Implementation details:
  - Extract LLM config: `campaign["llm_config"]["classify"]` (fall back to `DEFAULT_LLM_CONFIG["classify"]`)
  - Instantiate LLM via `get_llm(config)`
  - Build system prompt from `campaign["classify_instructions"]`:
    ```
    You are an email reply classification agent.

    Instructions from campaign manager:
    {campaign.classify_instructions}

    Classify the following reply into exactly one of these categories:
    - interested: The contact is interested and wants to proceed
    - declined: The contact explicitly declines or opts out
    - question: The contact has questions and needs more information
    - out_of_office: Auto-reply / out of office message
    - bounce: Delivery failure / invalid email

    Reply text:
    {reply_text}

    Previous outreach context:
    {outreach history summary}

    Return a JSON object:
    {
      "category": "<one of the categories above>",
      "confidence": <0.0-1.0>,
      "extracted_data": {<any relevant extracted info like return date for OOO, specific questions, etc.>}
    }
    ```
  - Parse LLM response as JSON
  - Return `{"classification": parsed["category"], "current_step": "classify"}`
- [ ] If JSON parsing fails, fall back to string matching on the response to extract the category
- [ ] Error handling: default classification to `"question"` if all parsing fails (safest default — routes to human review)

**Acceptance:** Given state with `reply_text`, the classify node returns a `classification` string that is one of: `interested`, `declined`, `question`, `out_of_office`, `bounce`.

---

## Task 9: Send Node (Placeholder)

**File:** `app/agents/nodes/send.py`

Placeholder for the send node. Actual SendGrid integration is in Plan 3.

- [ ] Create `app/agents/nodes/send.py`
- [ ] Implement `send_node` as a placeholder:

```python
async def send_node(state: OutreachState) -> dict:
    """
    Send node (placeholder). Actual SendGrid integration in Plan 3.

    In production, this node:
    1. Calls SendGrid API to send the email
    2. Logs an outreach_event (email_sent)
    3. Updates contact status to "emailed"
    4. Schedules the first evaluate task via arq

    For now, logs the draft and returns.

    Reads: state["draft_subject"], state["draft_body"], state["contact"]
    Writes: state["current_step"]
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.info(
        f"[SEND PLACEHOLDER] Would send email to {state['contact'].get('email', 'unknown')}: "
        f"Subject: {state.get('draft_subject', 'N/A')}"
    )

    return {"current_step": "send"}
```

**Acceptance:** `send_node` is callable, logs intent, and returns updated state. No actual email is sent.

---

## Task 10: Evaluate Node

**File:** `app/agents/nodes/evaluate.py`

Checks for replies, decides whether to follow up or close the contact. This is triggered by deferred arq tasks based on the campaign cadence.

- [ ] Create `app/agents/nodes/evaluate.py`
- [ ] Implement the `evaluate_node` function:

```python
async def evaluate_node(state: OutreachState) -> dict:
    """
    Evaluate node. Checks for replies and decides next action.

    This node is the decision point after the "wait" period.
    It determines routing via the return value which conditional edges read.

    Reads: state["contact"], state["campaign"], state["reply_text"]
    Writes: state["current_step"]
    """
```

- [ ] Implementation details:
  - Check if `state["reply_text"]` is populated (meaning a reply was received during the wait period)
  - If reply exists → return `{"current_step": "evaluate", "has_reply": True}`
  - If no reply:
    - Check `contact["current_cadence_step"]` against `campaign["cadence"]`
    - If more cadence steps remain → return `{"current_step": "evaluate", "has_reply": False, "action": "follow_up"}`
    - If cadence exhausted → return `{"current_step": "evaluate", "has_reply": False, "action": "close"}`
- [ ] Implement the routing function used by conditional edges:

```python
def evaluate_router(state: OutreachState) -> str:
    """Route from evaluate node based on reply status and cadence."""
    if state.get("has_reply"):
        return "classify"
    elif state.get("action") == "follow_up":
        return "compose"  # loops back to compose with follow-up template
    else:
        return "close"
```

**Acceptance:** `evaluate_node` correctly routes to `classify` when reply exists, `compose` for follow-ups, and `close` when cadence is exhausted.

---

## Task 11: Main Graph Assembly

**File:** `app/agents/graph.py`

Wire all nodes together into a LangGraph `StateGraph` with conditional edges and the human-approval gate.

- [ ] Create `app/agents/graph.py`
- [ ] Implement the graph builder:

```python
from langgraph.graph import StateGraph, END
from app.agents.state import OutreachState

def build_outreach_graph() -> StateGraph:
    """
    Build the outreach LangGraph StateGraph.

    Graph flow (from Section 5.1 of design spec):

    START --> research --> compose --> gate --> send --> END (wait for arq)
                                                        |
                           evaluate <--- (arq deferred task)
                              |
                     +--------+--------+
                     |                 |
                reply_exists      no_reply
                     |                 |
                  classify      follow_up_or_close
                     |                 |
              +------+------+    (compose or close)
              |      |      |
          interested declined question/ooo
              |      |      |
           convert  close  compose (reply)
    """
```

- [ ] Define all nodes:

```python
graph = StateGraph(OutreachState)

# Add nodes
graph.add_node("research", research_node)
graph.add_node("compose", compose_node)
graph.add_node("gate", gate_node)
graph.add_node("send", send_node)
graph.add_node("evaluate", evaluate_node)
graph.add_node("classify", classify_node)
graph.add_node("convert", convert_node)
graph.add_node("close", close_node)
```

- [ ] Implement the `gate_node` function:

```python
async def gate_node(state: OutreachState) -> dict:
    """
    Human approval gate.
    If campaign.auto_send is True, passes through immediately.
    If False, interrupts the graph for human approval via /approve-draft endpoint.
    """
    campaign = state["campaign"]
    if campaign.get("auto_send", False):
        return {"current_step": "gate_approved"}
    else:
        # This will be handled by LangGraph's interrupt mechanism
        return {"current_step": "gate_pending"}
```

- [ ] Define the gate routing function:

```python
def gate_router(state: OutreachState) -> str:
    """Route from gate node. Auto-send or wait for approval."""
    if state.get("current_step") == "gate_approved":
        return "send"
    else:
        return "__interrupt__"  # LangGraph interrupt — resumes when /approve-draft called
```

- [ ] Define the classify routing function:

```python
def classify_router(state: OutreachState) -> str:
    """Route from classify node based on classification result."""
    classification = state.get("classification", "question")
    if classification == "interested":
        return "convert"
    elif classification == "declined":
        return "close"
    elif classification == "question":
        return "compose"  # compose a reply to the question
    elif classification == "out_of_office":
        return "close"  # will be rescheduled by arq
    elif classification == "bounce":
        return "close"
    else:
        return "close"  # safe default
```

- [ ] Wire edges:

```python
# Linear flow: START -> research -> compose -> gate
graph.set_entry_point("research")
graph.add_edge("research", "compose")
graph.add_edge("compose", "gate")

# Conditional: gate -> send or interrupt
graph.add_conditional_edges("gate", gate_router, {
    "send": "send",
    "__interrupt__": END,  # paused for human approval
})

# send -> END (wait period handled by arq, not the graph)
graph.add_edge("send", END)

# Evaluate is entry point for the follow-up graph (separate invocation)
# Conditional: evaluate -> classify or compose or close
graph.add_conditional_edges("evaluate", evaluate_router, {
    "classify": "classify",
    "compose": "compose",
    "close": "close",
})

# Conditional: classify -> convert or close or compose
graph.add_conditional_edges("classify", classify_router, {
    "convert": "convert",
    "close": "close",
    "compose": "compose",
})

# Terminal nodes
graph.add_edge("convert", END)
graph.add_edge("close", END)
```

- [ ] Implement simple `convert_node` and `close_node`:

```python
async def convert_node(state: OutreachState) -> dict:
    """Mark contact as converted. Actual conversion handling in Plan 3."""
    return {"current_step": "convert"}

async def close_node(state: OutreachState) -> dict:
    """Mark contact as closed (declined/unresponsive). Cleanup in Plan 3."""
    return {"current_step": "close"}
```

- [ ] Compile the graph: `compiled = graph.compile()`
- [ ] Export `build_outreach_graph` and `compile_outreach_graph` (returns compiled version)

**Acceptance:** `compile_outreach_graph()` returns a compiled LangGraph that can be invoked with an `OutreachState` dict. The graph flows correctly through research -> compose -> gate -> send for the initial outreach path, and evaluate -> classify -> convert/close for the follow-up path.

---

## Task 12: Checkpoint Persistence

**File:** `app/agents/checkpoints.py`

Save and load LangGraph state to/from the `agent_checkpoints` database table for crash recovery.

- [ ] Create `app/agents/checkpoints.py`
- [ ] Implement `save_checkpoint`:

```python
import uuid
import json
from datetime import datetime

async def save_checkpoint(
    db_session,
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

    Returns the checkpoint ID.
    """
```

- [ ] Implementation details:
  - Query for existing active checkpoint: `WHERE contact_id = ? AND is_active = true`
  - If exists, update `state`, `current_node`, `updated_at`
  - If not exists, insert new row with `is_active = true`
  - Serialise `state` dict to JSON (handle non-serialisable types with a custom encoder)

- [ ] Implement `load_checkpoint`:

```python
async def load_checkpoint(
    db_session,
    contact_id: str,
    run_id: str = None,
) -> dict | None:
    """
    Load the active LangGraph checkpoint for a contact.

    If run_id is provided, load that specific run.
    Otherwise, load the active checkpoint.

    Returns the deserialised state dict, or None if no checkpoint exists.
    """
```

- [ ] Implement `deactivate_checkpoint`:

```python
async def deactivate_checkpoint(
    db_session,
    contact_id: str,
) -> None:
    """
    Mark the active checkpoint for a contact as inactive.
    Called before starting a new run (retry).
    """
```

- [ ] Implement `cleanup_expired_checkpoints`:

```python
async def cleanup_expired_checkpoints(
    db_session,
    days: int = 30,
) -> int:
    """
    Delete checkpoints older than `days` for completed campaigns.
    Returns the number of deleted rows.
    """
```

- [ ] Add a LangGraph-compatible checkpointer class if needed:

```python
from langgraph.checkpoint.base import BaseCheckpointSaver

class PostgresCheckpointer(BaseCheckpointSaver):
    """
    Custom LangGraph checkpointer that persists to PostgreSQL
    via the agent_checkpoints table.
    """
```

**Acceptance:** Checkpoints can be saved after each node, loaded on resume, and deactivated on retry. The `PostgresCheckpointer` integrates with LangGraph's built-in checkpoint system.

---

## Task 13: Tests

**Directory:** `tests/agents/`

Unit tests for each node and integration test for the full graph.

- [ ] Create `tests/agents/__init__.py`
- [ ] Create `tests/agents/test_state.py`:
  - [ ] Test that `OutreachState` can be instantiated with all fields
  - [ ] Test that `OutreachState` works as a TypedDict (type checking, key access)

- [ ] Create `tests/agents/test_llm.py`:
  - [ ] Test `get_llm` with `provider="gemini"` returns `ChatGoogleGenerativeAI` (mock the import)
  - [ ] Test `get_llm` with `provider="anthropic"` returns `ChatAnthropic` (mock the import)
  - [ ] Test `get_llm` with `provider="openai"` returns `ChatOpenAI` (mock the import)
  - [ ] Test `get_llm` with unknown provider raises `ValueError`
  - [ ] Test `kwargs` passthrough (temperature, max_tokens)

- [ ] Create `tests/agents/test_tools.py`:
  - [ ] Test `scrape_website` with mocked httpx response returns extracted content
  - [ ] Test `scrape_website` with timeout returns error string (not exception)
  - [ ] Test `scrape_website` with non-200 status returns error string
  - [ ] Test `search_sra_register` with mocked response returns SRA details
  - [ ] Test `search_sra_register` with no results returns "not found" message
  - [ ] Test `search_web` with mocked Serper response returns formatted results
  - [ ] Test `search_web` with no API key returns fallback message

- [ ] Create `tests/agents/test_nodes.py`:
  - [ ] Test `research_node` with mocked LLM and tools returns enriched `research_data`
  - [ ] Test `compose_node` with mocked LLM returns `draft_subject` and `draft_body`
  - [ ] Test `classify_node` with mocked LLM returns valid classification category
  - [ ] Test `classify_node` fallback when JSON parsing fails
  - [ ] Test `send_node` placeholder returns updated state
  - [ ] Test `evaluate_node` routes to `classify` when reply exists
  - [ ] Test `evaluate_node` routes to `compose` when follow-up needed
  - [ ] Test `evaluate_node` routes to `close` when cadence exhausted

- [ ] Create `tests/agents/test_graph.py`:
  - [ ] Test full graph compilation succeeds
  - [ ] Test initial outreach path: research -> compose -> gate (auto_send=true) -> send -> END
  - [ ] Test gate interrupt path: research -> compose -> gate (auto_send=false) -> interrupt
  - [ ] Test follow-up path: evaluate (no reply, cadence remaining) -> compose -> gate -> send
  - [ ] Test reply path: evaluate (reply exists) -> classify (interested) -> convert -> END
  - [ ] Test decline path: evaluate (reply exists) -> classify (declined) -> close -> END
  - [ ] Test question path: evaluate (reply exists) -> classify (question) -> compose -> gate -> send
  - [ ] Test close path: evaluate (no reply, cadence exhausted) -> close -> END

- [ ] Create `tests/agents/test_checkpoints.py`:
  - [ ] Test `save_checkpoint` creates new checkpoint
  - [ ] Test `save_checkpoint` updates existing active checkpoint
  - [ ] Test `load_checkpoint` returns active checkpoint state
  - [ ] Test `load_checkpoint` returns None when no checkpoint exists
  - [ ] Test `deactivate_checkpoint` marks checkpoint inactive
  - [ ] Test `cleanup_expired_checkpoints` deletes old checkpoints

- [ ] All tests use `pytest` and `pytest-asyncio`
- [ ] LLM calls are mocked (never call real APIs in tests)
- [ ] httpx calls are mocked with `respx` or `pytest-httpx`

**Acceptance:** All tests pass with `pytest tests/agents/ -v`. No real API calls are made. Coverage for all nodes, tools, routing logic, and checkpoints.

---

## File Structure Summary

After Plan 2 is complete, the following files will exist:

```
app/
  agents/
    __init__.py
    state.py              # Task 1: OutreachState TypedDict
    llm.py                # Task 2: LLM provider abstraction
    graph.py              # Task 11: Main graph assembly
    checkpoints.py        # Task 12: Checkpoint persistence
    tools/
      __init__.py
      scraper.py           # Task 3: Website scraper
      sra.py               # Task 4: SRA register lookup
      web_search.py        # Task 5: Web search
    nodes/
      __init__.py
      research.py          # Task 6: Research agent node
      compose.py           # Task 7: Compose agent node
      classify.py          # Task 8: Classify agent node
      send.py              # Task 9: Send node (placeholder)
      evaluate.py          # Task 10: Evaluate node
tests/
  agents/
    __init__.py
    test_state.py          # Task 13
    test_llm.py            # Task 13
    test_tools.py          # Task 13
    test_nodes.py          # Task 13
    test_graph.py          # Task 13
    test_checkpoints.py    # Task 13
```

## Dependencies to Add (pyproject.toml / requirements.txt)

```
langgraph>=0.2.0
langchain-core>=0.3.0
langchain-google-genai>=2.0.0
langchain-anthropic>=0.3.0
langchain-openai>=0.3.0
httpx>=0.27.0
beautifulsoup4>=4.12.0
```

**Dev dependencies:**
```
pytest-asyncio>=0.24.0
respx>=0.22.0  # or pytest-httpx
```
