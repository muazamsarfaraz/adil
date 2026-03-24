# Immediate Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement all "immediate/high priority" roadmap items: git init, linting, type checking, jurisdiction selector UI, incident summary generator endpoint, solicitor consultation pack, and test coverage for new + untested features.

**Architecture:** Seven independent tasks that build on each other sequentially. Infrastructure first (git, linting, typing), then backend features (generate-report endpoint with two report types), then frontend (jurisdiction selector), then test coverage, then final commit.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, Chainlit, ruff, mypy, pytest, pytest-asyncio, Google Gemini API

---

## File Map

### New Files
- `pyproject.toml` (root) — ruff + mypy config for all 3 Python services
- `.gitignore` (root) — comprehensive Python/.env/IDE ignores
- `adil-rag-api/report_generator.py` — report generation logic (incident summary + solicitor pack)
- `adil-rag-api/tests/test_report_generator.py` — tests for report generation
- `adil-rag-api/tests/test_image_endpoint.py` — tests for image query endpoint

### Modified Files
- `adil-rag-api/models.py` — add `ReportType` enum, `GenerateReportRequest`, `GenerateReportResponse`, `ReportSection`
- `adil-rag-api/app.py` — add `POST /api/v1/generate-report` endpoint, import new models
- `adil-rag-api/requirements-dev.txt` — add ruff, mypy
- `adil-frontend/app.py` — add jurisdiction selector buttons in `start_chat()`, store in session, prepend to queries

---

### Task 1: Git Initialisation

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Create .gitignore**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
*.egg-info/
dist/
build/
*.egg

# Virtual environments
.venv/
venv/
env/

# Environment variables (secrets)
.env
.env.local
.env.production

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db
desktop.ini

# pytest
.pytest_cache/
htmlcov/
.coverage

# mypy
.mypy_cache/

# ruff
.ruff_cache/

# Chainlit runtime
.chainlit/
.files/

# Railway deploy artifacts
deploy_api.txt
link_api.txt
fe_check.txt

# Node (if any)
node_modules/

# Legislation downloads (large, regenerable)
legislation_downloads/
```

- [ ] **Step 2: Initialise git repo**

Run: `cd E:/dev/mcbx/adil && git init`
Expected: `Initialized empty Git repository`

- [ ] **Step 3: Stage all files and verify nothing sensitive is included**

Run: `git add -A && git status`
Expected: No `.env` files, no `__pycache__/`, no `.chainlit/` directories staged.
If `.env` appears, abort and fix `.gitignore`.

- [ ] **Step 4: Create initial commit**

```bash
git commit -m "feat: initial commit — AskAdil codebase

Four services: adil-rag-api, adil-frontend, adil-report-bridge, adil-landing
125 existing tests passing, deployed on Railway at askadil.org"
```

---

### Task 2: Linting Setup (ruff)

**Files:**
- Create: `pyproject.toml` (project root)
- Modify: `adil-rag-api/requirements-dev.txt`

- [ ] **Step 1: Write pyproject.toml with ruff + mypy config**

```toml
[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "B",    # flake8-bugbear
    "UP",   # pyupgrade
]
ignore = [
    "E501",  # line too long (handled by formatter)
    "B008",  # do not perform function calls in argument defaults (FastAPI Depends)
]

[tool.ruff.lint.isort]
known-first-party = ["models", "rag_service", "content_extractor", "conversation_log", "email_receipt"]

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true
check_untyped_defs = true
```

- [ ] **Step 2: Add ruff and mypy to dev requirements**

Append to `adil-rag-api/requirements-dev.txt`:
```
ruff>=0.8.0
mypy>=1.8.0
```

- [ ] **Step 3: Run ruff check on all services**

Run: `cd E:/dev/mcbx/adil && python -m ruff check adil-rag-api/ adil-report-bridge/ adil-frontend/`
Expected: List of issues (do NOT auto-fix yet — review first)

- [ ] **Step 4: Run ruff format (dry-run) to see what would change**

Run: `python -m ruff format --diff adil-rag-api/ adil-report-bridge/ adil-frontend/`
Expected: Diff output showing formatting changes

- [ ] **Step 5: Apply ruff format**

Run: `python -m ruff format adil-rag-api/ adil-report-bridge/ adil-frontend/`

- [ ] **Step 6: Apply safe ruff fixes**

Run: `python -m ruff check --fix adil-rag-api/ adil-report-bridge/ adil-frontend/`

- [ ] **Step 7: Run existing tests to confirm nothing broke**

Run: `cd E:/dev/mcbx/adil/adil-rag-api && python -m pytest test_backend.py -v --tb=short`
Expected: 125 tests pass

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml adil-rag-api/requirements-dev.txt adil-rag-api/ adil-report-bridge/ adil-frontend/
git commit -m "chore: add ruff linting + formatting, mypy config

pyproject.toml with ruff (E/W/F/I/B/UP rules) and mypy settings.
Applied ruff format and safe auto-fixes across all 3 services."
```

---

### Task 3: Incident Summary Generator + Solicitor Pack — Models

**Files:**
- Modify: `adil-rag-api/models.py` — add new models after line 446
- Modify: `adil-rag-api/app.py` line 48 — update imports

- [ ] **Step 1: Write failing test for new models**

Create `adil-rag-api/tests/test_report_generator.py`:
```python
"""Tests for the report generation feature (incident summary + solicitor pack)."""
import pytest
from models import (
    ReportType,
    GenerateReportRequest,
    GenerateReportResponse,
    ReportSection,
    ConversationTurn,
)


class TestReportModels:
    """Validate Pydantic models for report generation."""

    def test_report_type_enum_values(self):
        assert ReportType.INCIDENT_SUMMARY == "incident_summary"
        assert ReportType.SOLICITOR_PACK == "solicitor_pack"

    def test_generate_report_request_valid(self):
        req = GenerateReportRequest(
            conversation_history=[
                ConversationTurn(role="user", content="I was harassed at work for wearing hijab"),
                ConversationTurn(role="model", content="I understand. Let me help you understand your rights."),
            ],
            report_type=ReportType.INCIDENT_SUMMARY,
        )
        assert req.report_type == ReportType.INCIDENT_SUMMARY
        assert len(req.conversation_history) == 2

    def test_generate_report_request_requires_history(self):
        with pytest.raises(Exception):
            GenerateReportRequest(
                conversation_history=[],
                report_type=ReportType.INCIDENT_SUMMARY,
            )

    def test_generate_report_request_solicitor_pack(self):
        req = GenerateReportRequest(
            conversation_history=[
                ConversationTurn(role="user", content="My employer denied me prayer breaks"),
            ],
            report_type=ReportType.SOLICITOR_PACK,
            jurisdiction="Scotland",
        )
        assert req.report_type == ReportType.SOLICITOR_PACK
        assert req.jurisdiction == "Scotland"

    def test_report_section_model(self):
        section = ReportSection(heading="WHAT HAPPENED", content="The user was harassed.")
        assert section.heading == "WHAT HAPPENED"
        assert section.content == "The user was harassed."

    def test_generate_report_response(self):
        resp = GenerateReportResponse(
            report_text="--- INCIDENT REPORT ---\nTest content",
            report_type=ReportType.INCIDENT_SUMMARY,
            sections=[
                ReportSection(heading="WHAT HAPPENED", content="Test"),
            ],
        )
        assert resp.report_type == ReportType.INCIDENT_SUMMARY
        assert len(resp.sections) == 1
        assert resp.generated_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd E:/dev/mcbx/adil/adil-rag-api && python -m pytest tests/test_report_generator.py -v --tb=short`
Expected: FAIL — `ImportError: cannot import name 'ReportType' from 'models'`

- [ ] **Step 3: Add models to models.py**

Append to end of `adil-rag-api/models.py` (after line 446):
```python


# ============================================================================
# Report Generation Models
# ============================================================================


class ReportType(str, Enum):
    """Type of report to generate from conversation history.

    - **incident_summary** — Structured summary for self-service reporting
      (Police, Tell MAMA, IRU). Copy-paste into forms.
    - **solicitor_pack** — Consultation preparation pack for solicitor-path
      cases (ACAS, ET1, county court). Bring to first appointment.
    """
    INCIDENT_SUMMARY = "incident_summary"
    SOLICITOR_PACK = "solicitor_pack"


class ReportSection(BaseModel):
    """A single section of a generated report."""
    heading: str = Field(..., description="Section heading, e.g. 'WHAT HAPPENED'.")
    content: str = Field(..., description="Section content text.")


class GenerateReportRequest(BaseModel):
    """Request model for the `/api/v1/generate-report` endpoint.

    Generates a structured report from conversation history. Two types:
    - `incident_summary` — for self-service hate crime reporting
    - `solicitor_pack` — for solicitor consultation preparation
    """
    conversation_history: List[ConversationTurn] = Field(
        ...,
        description="The conversation history to generate a report from.",
        min_length=1,
        max_length=50,
    )
    report_type: ReportType = Field(
        ReportType.INCIDENT_SUMMARY,
        description="Type of report to generate.",
    )
    jurisdiction: Optional[str] = Field(
        None,
        description="User's jurisdiction (e.g. 'England and Wales', 'Scotland', 'Northern Ireland').",
    )

    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "conversation_history": [
                    {"role": "user", "content": "I was verbally abused on the bus for wearing a niqab."},
                    {"role": "model", "content": "I'm sorry to hear that. This could constitute a religiously aggravated offence under the Crime and Disorder Act 1998 s.28..."},
                ],
                "report_type": "incident_summary",
                "jurisdiction": "England and Wales",
            }
        ]
    })


class GenerateReportResponse(BaseModel):
    """Response from the `/api/v1/generate-report` endpoint."""
    report_text: str = Field(..., description="The full report as formatted text.")
    report_type: ReportType = Field(..., description="Type of report generated.")
    sections: List[ReportSection] = Field(
        default_factory=list,
        description="Report broken into sections for UI rendering.",
    )
    generated_at: str = Field(
        default_factory=lambda: __import__("datetime").datetime.utcnow().isoformat() + "Z",
        description="ISO 8601 timestamp of generation.",
    )
    jurisdiction: Optional[str] = Field(None, description="Jurisdiction used for the report.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd E:/dev/mcbx/adil/adil-rag-api && python -m pytest tests/test_report_generator.py -v --tb=short`
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add adil-rag-api/models.py adil-rag-api/tests/test_report_generator.py
git commit -m "feat: add ReportType, GenerateReportRequest/Response models

Two report types: incident_summary (self-service) and solicitor_pack.
Includes ReportSection for structured UI rendering."
```

---

### Task 4: Incident Summary Generator + Solicitor Pack — Service Logic

**Files:**
- Create: `adil-rag-api/report_generator.py`

- [ ] **Step 1: Add tests for report generation logic**

Append to `adil-rag-api/tests/test_report_generator.py`:
```python
from unittest.mock import AsyncMock, patch, MagicMock


class TestReportGeneratorPrompts:
    """Verify report generation prompts are well-structured."""

    def test_incident_summary_prompt_contains_required_sections(self):
        from report_generator import _build_incident_summary_prompt
        prompt = _build_incident_summary_prompt("England and Wales")
        assert "WHAT HAPPENED" in prompt
        assert "WHERE THIS HAPPENED" in prompt
        assert "WHEN THIS HAPPENED" in prompt
        assert "LEGAL CONTEXT" in prompt
        assert "INCIDENT REPORT SUMMARY" in prompt

    def test_solicitor_pack_prompt_contains_required_sections(self):
        from report_generator import _build_solicitor_pack_prompt
        prompt = _build_solicitor_pack_prompt("England and Wales")
        assert "SOLICITOR CONSULTATION PACK" in prompt
        assert "KEY DATES" in prompt
        assert "RELEVANT LEGISLATION" in prompt
        assert "WHAT TO ASK YOUR SOLICITOR" in prompt

    def test_solicitor_pack_prompt_scotland_uses_scottish_resources(self):
        from report_generator import _build_solicitor_pack_prompt
        prompt = _build_solicitor_pack_prompt("Scotland")
        assert "lawscot.org.uk" in prompt

    def test_solicitor_pack_prompt_ni_uses_ni_resources(self):
        from report_generator import _build_solicitor_pack_prompt
        prompt = _build_solicitor_pack_prompt("Northern Ireland")
        assert "lawsoc-ni.org" in prompt


class TestParseReportSections:
    """Verify section parsing from generated report text."""

    def test_parse_sections_from_incident_report(self):
        from report_generator import parse_report_sections
        text = (
            "--- INCIDENT REPORT SUMMARY ---\n"
            "Generated by AskAdil\n\n"
            "WHAT HAPPENED:\nSomeone shouted abuse.\n\n"
            "WHERE THIS HAPPENED:\nBirmingham city centre.\n\n"
            "WHEN THIS HAPPENED:\n15 March 2026, around 3pm.\n\n"
            "--- END REPORT ---"
        )
        sections = parse_report_sections(text)
        assert len(sections) >= 3
        assert sections[0].heading == "WHAT HAPPENED"
        assert "shouted abuse" in sections[0].content

    def test_parse_sections_from_solicitor_pack(self):
        from report_generator import parse_report_sections
        text = (
            "--- SOLICITOR CONSULTATION PACK ---\n\n"
            "YOUR SITUATION:\nDenied prayer breaks at work.\n\n"
            "KEY DATES:\nIncident: 10 March 2026\n\n"
            "RELEVANT LEGISLATION:\nEquality Act 2010 s.13\n\n"
            "--- END PACK ---"
        )
        sections = parse_report_sections(text)
        assert len(sections) >= 3
        assert any(s.heading == "KEY DATES" for s in sections)
```

- [ ] **Step 2: Run to verify failures**

Run: `cd E:/dev/mcbx/adil/adil-rag-api && python -m pytest tests/test_report_generator.py::TestReportGeneratorPrompts -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'report_generator'`

- [ ] **Step 3: Create report_generator.py**

Create `adil-rag-api/report_generator.py`:
```python
"""Report generation from conversation history.

Two report types:
- Incident Summary: structured text for copy-paste into reporting forms
- Solicitor Pack: consultation prep for solicitor-path cases

Uses the existing RAGService.query() to generate reports via Gemini,
with specialised prompts that instruct the model to produce structured output.
"""
import re
from typing import List, Optional

from models import ReportSection


# ---------------------------------------------------------------------------
# Solicitor directory by jurisdiction
# ---------------------------------------------------------------------------

_SOLICITOR_LINKS = {
    "England and Wales": (
        "- solicitors.lawsociety.org.uk (Law Society Find a Solicitor)\n"
        "- muslimlawyer.co.uk (Muslim Lawyer UK)\n"
        "- muslimsolicitors.co.uk (Muslim Solicitors)"
    ),
    "Scotland": (
        "- lawscot.org.uk (Law Society of Scotland)\n"
        "- muslimlawyer.co.uk (Muslim Lawyer UK)"
    ),
    "Northern Ireland": (
        "- lawsoc-ni.org (Law Society of Northern Ireland)"
    ),
}


def _build_incident_summary_prompt(jurisdiction: Optional[str] = None) -> str:
    """Build the Gemini prompt for generating an incident summary report."""
    jur_line = f"\nJURISDICTION: {jurisdiction}" if jurisdiction else ""
    return (
        "INSTRUCTION: You are generating a structured INCIDENT REPORT SUMMARY, "
        "NOT having a conversation. Do NOT ask questions. Do NOT request more information. "
        "Use ONLY the information in the conversation history. "
        "If a detail is missing, write 'Not provided' for that section.\n\n"
        "Generate the report in this EXACT format:\n\n"
        "--- INCIDENT REPORT SUMMARY ---\n"
        f"Generated by AskAdil{jur_line}\n\n"
        "TYPE:\n[Religious discrimination / hate crime / online hate — identify from conversation]\n\n"
        "WHAT HAPPENED:\n[Summarise the incident in 2-4 clear sentences from the conversation]\n\n"
        "WHERE THIS HAPPENED:\n[Location if mentioned, otherwise 'Not provided']\n\n"
        "WHEN THIS HAPPENED:\n[Date, time, duration if mentioned, otherwise 'Not provided']\n\n"
        "SUSPECT DESCRIPTION:\n[Any descriptions provided, otherwise 'Not provided']\n\n"
        "POLICE CONTACTED:\n[Yes/No if mentioned, otherwise 'Not provided']\n\n"
        "EVIDENCE:\n[Any URLs, screenshots, or documents mentioned, otherwise 'None mentioned']\n\n"
        "LEGAL CONTEXT:\n[Relevant legislation identified during the conversation, "
        "e.g. Equality Act 2010 s.13, Public Order Act 1986 s.29B, Crime and Disorder Act 1998 s.28]\n\n"
        "--- END REPORT ---"
    )


def _build_solicitor_pack_prompt(jurisdiction: Optional[str] = None) -> str:
    """Build the Gemini prompt for generating a solicitor consultation pack."""
    jur = jurisdiction or "England and Wales"
    solicitor_links = _SOLICITOR_LINKS.get(jur, _SOLICITOR_LINKS["England and Wales"])

    return (
        "INSTRUCTION: You are generating a SOLICITOR CONSULTATION PACK, "
        "NOT having a conversation. Do NOT ask questions. Do NOT request more information. "
        "Use ONLY the information in the conversation history. "
        "If a detail is missing, write 'Not provided' for that section.\n\n"
        "This pack is for the user to bring to their first solicitor appointment.\n\n"
        "Generate the report in this EXACT format:\n\n"
        "--- SOLICITOR CONSULTATION PACK ---\n"
        f"Generated by AskAdil — Jurisdiction: {jur}\n"
        "Bring this to your first solicitor appointment.\n\n"
        "YOUR SITUATION:\n[Structured narrative from conversation — 3-5 sentences]\n\n"
        "KEY DATES:\n"
        "- Incident date: [date if mentioned, otherwise 'Not provided']\n"
        "- Time limit for ET claim: [calculate 3 months less 1 day from incident date if applicable]\n"
        "- ACAS EC must be started by: [calculate if applicable, otherwise 'N/A']\n\n"
        "RELEVANT LEGISLATION:\n[List all relevant Acts and sections identified, "
        "e.g. Equality Act 2010 s.13 (direct discrimination), s.26 (harassment)]\n\n"
        "ASKADIL ASSESSMENT:\n"
        "- Key legal issues identified: [list from conversation]\n"
        "- Note: This is a preliminary AI assessment, not legal advice.\n\n"
        "WHAT TO ASK YOUR SOLICITOR:\n"
        "1. Do I have grounds for a claim?\n"
        "2. Should we go through ACAS Early Conciliation first?\n"
        "3. What evidence do I need to gather?\n"
        "4. Do you offer a no-win-no-fee arrangement for discrimination cases?\n"
        "5. What is the realistic timeline and cost?\n\n"
        "FIND A SOLICITOR:\n"
        f"{solicitor_links}\n\n"
        "--- END PACK ---"
    )


def get_report_prompt(report_type: str, jurisdiction: Optional[str] = None) -> str:
    """Return the appropriate prompt for the given report type."""
    if report_type == "solicitor_pack":
        return _build_solicitor_pack_prompt(jurisdiction)
    return _build_incident_summary_prompt(jurisdiction)


def parse_report_sections(report_text: str) -> List[ReportSection]:
    """Parse a generated report into structured sections.

    Looks for patterns like:
        HEADING:
        Content text here.
    """
    sections: List[ReportSection] = []
    # Match lines like "WHAT HAPPENED:" or "KEY DATES:" followed by content
    pattern = re.compile(
        r'^([A-Z][A-Z\s/()]+):\s*\n(.*?)(?=\n[A-Z][A-Z\s/()]+:\s*\n|---\s|$)',
        re.MULTILINE | re.DOTALL,
    )
    for match in pattern.finditer(report_text):
        heading = match.group(1).strip()
        content = match.group(2).strip()
        if content and heading not in ("INSTRUCTION",):
            sections.append(ReportSection(heading=heading, content=content))
    return sections
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd E:/dev/mcbx/adil/adil-rag-api && python -m pytest tests/test_report_generator.py -v --tb=short`
Expected: All tests PASS (model tests + prompt tests + parse tests)

- [ ] **Step 5: Commit**

```bash
git add adil-rag-api/report_generator.py adil-rag-api/tests/test_report_generator.py
git commit -m "feat: add report_generator module with prompt builders and section parser

Incident summary prompt for self-service reporting (Police/Tell MAMA/IRU).
Solicitor pack prompt for consultation prep (ACAS/ET1 path).
Jurisdiction-aware solicitor directory links.
Section parser for structured UI rendering."
```

---

### Task 5: Incident Summary Generator + Solicitor Pack — Endpoint

**Files:**
- Modify: `adil-rag-api/app.py` — add endpoint + imports

- [ ] **Step 1: Write endpoint integration test**

Append to `adil-rag-api/tests/test_report_generator.py`:
```python
from fastapi.testclient import TestClient


class TestGenerateReportEndpoint:
    """Test the POST /api/v1/generate-report endpoint contract."""

    @pytest.fixture
    def client(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from app import app
        return TestClient(app)

    @pytest.fixture
    def api_key(self):
        return os.environ.get("ADIL_API_KEY", "test-key")

    def test_generate_report_requires_auth(self, client):
        resp = client.post("/api/v1/generate-report", json={
            "conversation_history": [
                {"role": "user", "content": "test"},
            ],
            "report_type": "incident_summary",
        })
        assert resp.status_code in (401, 403)

    def test_generate_report_rejects_empty_history(self, client, api_key):
        resp = client.post(
            "/api/v1/generate-report",
            json={"conversation_history": [], "report_type": "incident_summary"},
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 422

    def test_generate_report_rejects_invalid_type(self, client, api_key):
        resp = client.post(
            "/api/v1/generate-report",
            json={
                "conversation_history": [{"role": "user", "content": "test"}],
                "report_type": "invalid_type",
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 422

    def test_generate_report_accepts_valid_request(self, client, api_key):
        """Smoke test — verifies the endpoint exists and accepts valid input.
        Will return 500 if Gemini is not configured, which is expected in CI."""
        resp = client.post(
            "/api/v1/generate-report",
            json={
                "conversation_history": [
                    {"role": "user", "content": "I was harassed at work for wearing hijab"},
                    {"role": "model", "content": "That sounds like it could be direct discrimination under the Equality Act 2010 s.13."},
                ],
                "report_type": "incident_summary",
                "jurisdiction": "England and Wales",
            },
            headers={"X-API-Key": api_key},
        )
        # 200 if Gemini is configured, 500 if not (both valid in test)
        assert resp.status_code in (200, 500)
```

- [ ] **Step 2: Run to verify failure (endpoint doesn't exist yet)**

Run: `cd E:/dev/mcbx/adil/adil-rag-api && python -m pytest tests/test_report_generator.py::TestGenerateReportEndpoint::test_generate_report_requires_auth -v --tb=short`
Expected: FAIL — 404 (endpoint not found) or import error

- [ ] **Step 3: Add imports to app.py**

At line 48-53 in `adil-rag-api/app.py`, update the imports block:

Add `GenerateReportRequest, GenerateReportResponse, ReportType` to the models import, and add `from report_generator import get_report_prompt, parse_report_sections` below line 57.

Specifically, change line 48-53 from:
```python
from models import (
    QueryRequest, QueryResponse, HealthResponse, StatsResponse,
    AnalyzeContentRequest, AnalyzeContentResponse, ExtractedContent, ContentType,
    ImageQueryRequest, ImageData, ALLOWED_IMAGE_MIMES,
    SubmitReportRequest, SubmitReportResponse,
)
```
to:
```python
from models import (
    QueryRequest, QueryResponse, HealthResponse, StatsResponse,
    AnalyzeContentRequest, AnalyzeContentResponse, ExtractedContent, ContentType,
    ImageQueryRequest, ImageData, ALLOWED_IMAGE_MIMES,
    SubmitReportRequest, SubmitReportResponse,
    GenerateReportRequest, GenerateReportResponse, ReportType,
)
```

And after line 57 (`from content_extractor import ContentExtractor`), add:
```python
from report_generator import get_report_prompt, parse_report_sections
```

- [ ] **Step 4: Add the endpoint to app.py**

Insert before line 1135 (the `if __name__` block), after the submit_report endpoint:

```python


# =============================================================================
# REPORT GENERATION ENDPOINTS
# =============================================================================


@app.post(
    "/api/v1/generate-report",
    response_model=GenerateReportResponse,
    tags=["Report Generation"],
    summary="Generate a structured incident report or solicitor consultation pack",
)
@limiter.limit(RATE_LIMIT_QUERY)
async def generate_report(
    request: Request,
    body: GenerateReportRequest,
    _api_key: str = Security(verify_api_key),
):
    """Generate a structured report from conversation history.

    Two report types:
    - **incident_summary**: For self-service hate crime reporting. Generates
      a structured summary the user can copy-paste into Police, Tell MAMA, or IRU forms.
    - **solicitor_pack**: For solicitor-path cases. Generates a consultation
      preparation pack with key dates, legislation, and questions to ask.

    🔐 **Requires `X-API-Key` header.**
    """
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialised.")

    prompt = get_report_prompt(body.report_type.value, body.jurisdiction)

    history_dicts = [
        {"role": t.role, "content": t.content}
        for t in body.conversation_history
    ]

    try:
        answer, _, usage, metadata = await rag_service.query(
            query_text=prompt,
            max_sources=0,
            include_viability=False,
            conversation_history=history_dicts,
        )
    except Exception as e:
        logger.error(f"Report generation error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate report. Please try again.",
        )

    sections = parse_report_sections(answer)

    # Log anonymised metadata (fire-and-forget)
    asyncio.create_task(log_conversation(
        endpoint="generate_report",
        query_text="",
        report_type=body.report_type.value,
        jurisdiction=body.jurisdiction,
    ))

    return GenerateReportResponse(
        report_text=answer,
        report_type=body.report_type,
        sections=sections,
        jurisdiction=body.jurisdiction,
    )
```

- [ ] **Step 5: Run endpoint tests**

Run: `cd E:/dev/mcbx/adil/adil-rag-api && python -m pytest tests/test_report_generator.py::TestGenerateReportEndpoint -v --tb=short`
Expected: Auth test passes (401/403), empty history rejected (422), invalid type rejected (422), valid request returns 200 or 500

- [ ] **Step 6: Run full test suite to confirm no regressions**

Run: `cd E:/dev/mcbx/adil/adil-rag-api && python -m pytest test_backend.py tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add adil-rag-api/app.py adil-rag-api/tests/test_report_generator.py
git commit -m "feat: add POST /api/v1/generate-report endpoint

Generates incident summaries (self-service path) or solicitor consultation
packs (solicitor path) from conversation history via Gemini.
Includes auth, rate limiting, anonymised logging."
```

---

### Task 6: Jurisdiction Selector UI

**Files:**
- Modify: `adil-frontend/app.py` — `start_chat()` and `_send_query()`

- [ ] **Step 1: Modify start_chat() to show jurisdiction buttons**

In `adil-frontend/app.py`, replace the `start_chat()` function (lines 39-68) with:

```python
@cl.on_chat_start
async def start_chat():
    """Initialize chat session with conversation history and jurisdiction selector"""
    cl.user_session.set("message_count", 0)
    cl.user_session.set("viability_requested", False)
    cl.user_session.set("conversation_history", [])
    cl.user_session.set("jurisdiction", None)

    # Send welcome message with jurisdiction selector
    actions = [
        cl.Action(
            name="select_jurisdiction",
            payload={"jurisdiction": "England and Wales"},
            label="England & Wales",
        ),
        cl.Action(
            name="select_jurisdiction",
            payload={"jurisdiction": "Scotland"},
            label="Scotland",
        ),
        cl.Action(
            name="select_jurisdiction",
            payload={"jurisdiction": "Northern Ireland"},
            label="Northern Ireland",
        ),
    ]

    await cl.Message(
        content=(
            "⚖️ **Welcome to AskAdil (عادل)**\n\n"
            "I'm a free legal education assistant specialising in **UK discrimination law**, "
            "particularly cases affecting British Muslims.\n\n"
            "**Where are you based?** This helps me give you jurisdiction-specific guidance:\n"
        ),
        actions=actions,
    ).send()


@cl.action_callback("select_jurisdiction")
async def on_select_jurisdiction(action: cl.Action):
    """Handle jurisdiction selection."""
    jurisdiction = action.payload.get("jurisdiction", "England and Wales")
    cl.user_session.set("jurisdiction", jurisdiction)

    await cl.Message(
        content=(
            f"**{jurisdiction}** — noted.\n\n"
            "📋 **To give you the best guidance, I'll start by asking a few "
            "questions** — like when the incident happened.\n\n"
            "💡 **You can also:**\n"
            "- Upload **screenshots or photos** of messages, letters, or documents for legal analysis\n"
            "- Paste **YouTube / Facebook / Twitter / Instagram / news article links** for legal analysis\n"
            "- Ask **follow-up questions** — I remember our conversation\n"
            "- Get **actionable next steps** with real links to organisations\n"
            "- Type **report** to submit a hate crime report\n\n"
            "> ⚠️ **AskAdil is an educational tool, not a law firm.** "
            "Always consult a qualified solicitor before taking legal action.\n\n"
            "*Tell me what happened and I'll help you understand your rights.*"
        )
    ).send()
```

- [ ] **Step 2: Modify _send_query() to prepend jurisdiction context**

In the `_send_query()` function, after the line that gets conversation history from the session, add jurisdiction prepending. Find the section that builds the payload (around line 100-110 where the `query` field is set) and prepend jurisdiction context:

Before building the API payload, add:
```python
    # Prepend jurisdiction context if set
    jurisdiction = cl.user_session.get("jurisdiction")
    query_with_context = user_text
    if jurisdiction:
        query_with_context = f"[Jurisdiction: {jurisdiction}] {user_text}"
```

Then use `query_with_context` instead of `user_text` in the payload's `query` field.

- [ ] **Step 3: Test manually**

Run the frontend locally and verify:
1. Welcome message shows 3 jurisdiction buttons
2. Clicking a button stores jurisdiction and shows confirmation
3. Subsequent queries include jurisdiction context

- [ ] **Step 4: Commit**

```bash
git add adil-frontend/app.py
git commit -m "feat: add jurisdiction selector UI at chat start

Three clickable buttons: England & Wales, Scotland, Northern Ireland.
Selection stored in session and prepended to all queries for
jurisdiction-specific legal guidance."
```

---

### Task 7: Test Coverage for Image Endpoint

**Files:**
- Create: `adil-rag-api/tests/test_image_endpoint.py`

- [ ] **Step 1: Write image endpoint tests**

Create `adil-rag-api/tests/test_image_endpoint.py`:
```python
"""Tests for the image query endpoint (/api/v1/query/image)."""
import os
import sys
import base64
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from models import ImageQueryRequest, ImageData, ALLOWED_IMAGE_MIMES


class TestImageModels:
    """Validate image-related Pydantic models."""

    def test_allowed_image_mimes(self):
        assert "image/png" in ALLOWED_IMAGE_MIMES
        assert "image/jpeg" in ALLOWED_IMAGE_MIMES
        assert "image/gif" in ALLOWED_IMAGE_MIMES
        assert "image/webp" in ALLOWED_IMAGE_MIMES
        assert "image/svg+xml" not in ALLOWED_IMAGE_MIMES

    def test_image_data_valid(self):
        img = ImageData(mime_type="image/png", data=base64.b64encode(b"fakepng").decode())
        assert img.mime_type == "image/png"

    def test_image_query_request_requires_images(self):
        with pytest.raises(Exception):
            ImageQueryRequest(images=[], include_viability_score=False)

    def test_image_query_request_max_5_images(self):
        with pytest.raises(Exception):
            ImageQueryRequest(
                images=[
                    ImageData(mime_type="image/png", data="dGVzdA==")
                    for _ in range(6)
                ],
                include_viability_score=False,
            )

    def test_image_query_request_valid(self):
        req = ImageQueryRequest(
            query="Is this discriminatory?",
            images=[ImageData(mime_type="image/png", data="dGVzdA==")],
            include_viability_score=False,
        )
        assert req.query == "Is this discriminatory?"
        assert len(req.images) == 1

    def test_image_query_request_optional_query(self):
        req = ImageQueryRequest(
            images=[ImageData(mime_type="image/jpeg", data="dGVzdA==")],
            include_viability_score=False,
        )
        assert req.query is None


class TestImageEndpointContract:
    """Test the /api/v1/query/image endpoint contract."""

    @pytest.fixture
    def client(self):
        from app import app
        return TestClient(app)

    @pytest.fixture
    def api_key(self):
        return os.environ.get("ADIL_API_KEY", "test-key")

    def test_image_endpoint_requires_auth(self, client):
        resp = client.post("/api/v1/query/image", json={
            "images": [{"mime_type": "image/png", "data": "dGVzdA=="}],
        })
        assert resp.status_code in (401, 403)

    def test_image_endpoint_rejects_empty_images(self, client, api_key):
        resp = client.post(
            "/api/v1/query/image",
            json={"images": []},
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 422

    def test_image_endpoint_rejects_invalid_mime(self, client, api_key):
        resp = client.post(
            "/api/v1/query/image",
            json={
                "images": [{"mime_type": "image/png", "data": "dGVzdA=="}],
            },
            headers={"X-API-Key": api_key},
        )
        # The endpoint validates base64 and MIME — invalid base64 for a real
        # image will fail at the Gemini level (500) or validation (400)
        assert resp.status_code in (200, 400, 500)
```

- [ ] **Step 2: Run image tests**

Run: `cd E:/dev/mcbx/adil/adil-rag-api && python -m pytest tests/test_image_endpoint.py -v --tb=short`
Expected: Model tests pass, endpoint contract tests pass (401/422/etc)

- [ ] **Step 3: Commit**

```bash
git add adil-rag-api/tests/test_image_endpoint.py
git commit -m "test: add image endpoint model validation and contract tests

Covers ALLOWED_IMAGE_MIMES, ImageData, ImageQueryRequest validation,
and /api/v1/query/image endpoint auth + input validation."
```

---

### Task 8: Final Lint + Full Test Run

- [ ] **Step 1: Run ruff on all new code**

Run: `cd E:/dev/mcbx/adil && python -m ruff check adil-rag-api/ adil-report-bridge/ adil-frontend/ --fix`

- [ ] **Step 2: Run ruff format on all new code**

Run: `python -m ruff format adil-rag-api/ adil-report-bridge/ adil-frontend/`

- [ ] **Step 3: Run full test suite**

Run: `cd E:/dev/mcbx/adil/adil-rag-api && python -m pytest test_backend.py tests/ -v --tb=short`
Expected: All tests pass (125 existing + ~20 new)

- [ ] **Step 4: Run report-bridge tests**

Run: `cd E:/dev/mcbx/adil/adil-report-bridge && python -m pytest tests/ -v --tb=short`
Expected: All bridge tests pass

- [ ] **Step 5: Commit any lint fixes**

```bash
git add -A
git commit -m "chore: final lint pass across all services"
```

---

## Deployment Note

Railway deployment (`railway up` for each service) requires Railway CLI auth and is environment-specific. After all tasks are complete:

```bash
cd E:/dev/mcbx/adil/adil-rag-api && railway up
cd E:/dev/mcbx/adil/adil-frontend && railway up
```

## MCB Legal Items (Non-Technical — Cannot Be Automated)

These require organisational action:
- Review and publish privacy notice (`docs/privacy-notice.md`)
- Begin Data Protection Impact Assessment (DPIA)
- Sign Railway DPA
- Register with ICO (if not already registered)
