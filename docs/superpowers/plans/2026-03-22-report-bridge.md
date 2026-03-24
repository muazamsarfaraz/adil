# Report Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `adil-report-bridge` microservice — an AI-powered browser automation service that submits hate crime reports to police.uk on behalf of AskAdil users.

**Architecture:** Standalone FastAPI service using browser-use + Gemini Flash + Playwright to fill multi-step web forms. Called internally by the RAG API via Railway private networking. Fails gracefully with a copy-paste fallback report.

**Tech Stack:** Python 3.11, FastAPI, browser-use, Playwright, Gemini Flash (via langchain-google-genai ChatGoogleGenerativeAI), Pydantic v2, httpx, Pillow (screenshot resize)

**Spec:** `docs/superpowers/specs/2026-03-22-report-bridge-design.md`

---

## File Structure

```
adil-report-bridge/           # NEW service (all files created)
├── app.py                    # FastAPI app: /submit, /health, /health/targets, /targets
├── browser_agent.py          # browser-use Agent wrapper, runs form submission
├── targets.py                # TARGETS config dict (police-uk)
├── models.py                 # Pydantic request/response models
├── screenshot.py             # Screenshot capture + resize/compress
├── Dockerfile                # Python 3.11 + Playwright + Chromium
├── requirements.txt          # Dependencies
├── railway.toml              # Railway deployment config
├── .env.example              # Env var documentation
└── tests/
    ├── test_models.py        # Model validation tests
    ├── test_targets.py       # Target config validation
    ├── test_app.py           # API endpoint tests (mocked browser)
    └── __init__.py           # Package marker

adil-rag-api/                 # EXISTING service (files modified)
├── models.py                 # Add SubmitReportRequest/Response models
├── app.py                    # Add /api/v1/submit-report, /api/v1/report-targets endpoints
└── tests/
    └── test_backend.py       # Add submit-report endpoint tests

adil-frontend/                # EXISTING service (files modified)
└── app.py                    # Add report submission flow in chat
```

---

### Task 1: Scaffold the bridge service

**Files:**
- Create: `adil-report-bridge/requirements.txt`
- Create: `adil-report-bridge/.env.example`
- Create: `adil-report-bridge/railway.toml`
- Create: `adil-report-bridge/Dockerfile`

- [ ] **Step 1: Create requirements.txt**

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
browser-use>=0.2.0
playwright>=1.40.0
langchain-google-genai>=2.0.0
python-dotenv>=1.0.0
pydantic>=2.5.0
httpx>=0.25.0
Pillow>=10.0.0
```

- [ ] **Step 2: Create .env.example**

```
# Required
GOOGLE_API_KEY=your-google-api-key
BRIDGE_API_KEY=your-shared-secret

# Optional
GEMINI_MODEL=gemini-2.5-flash
PORT=8000
```

- [ ] **Step 3: Create railway.toml**

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

- [ ] **Step 4: Create Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Playwright system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxdamage1 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    libxshmfence1 libx11-xcb1 libxcomposite1 libxfixes3 libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .

# Security: run as non-root user
RUN useradd -m appuser
USER appuser

ENV PORT=8000 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 5: Commit**

```bash
git add adil-report-bridge/requirements.txt adil-report-bridge/.env.example adil-report-bridge/railway.toml adil-report-bridge/Dockerfile
git commit -m "feat(bridge): scaffold adil-report-bridge service"
```

---

### Task 2: Bridge Pydantic models

**Files:**
- Create: `adil-report-bridge/models.py`
- Create: `adil-report-bridge/tests/test_models.py`

- [ ] **Step 1: Write failing tests**

Create `adil-report-bridge/tests/test_models.py`:

```python
"""Tests for bridge Pydantic models."""
import pytest
from models import SubmitRequest, SubmitResponse, DOB


def test_submit_request_valid():
    req = SubmitRequest(
        target="police-uk",
        data={
            "first_name": "Ahmad",
            "surname": "Hassan",
            "dob": {"day": "15", "month": "06", "year": "1990"},
            "gender": "male",
            "email": "ahmad@example.com",
            "incident_details": "Hate incident occurred outside station",
            "location": "London E1",
            "date_time": "10 March 2026, 5:30pm",
        },
    )
    assert req.target == "police-uk"
    assert req.data["first_name"] == "Ahmad"


def test_submit_request_missing_target():
    with pytest.raises(Exception):
        SubmitRequest(data={"first_name": "Test"})


def test_submit_response_success():
    resp = SubmitResponse(
        success=True,
        target="police-uk",
        reference_number="HC-2026-12345",
        confirmation_screenshot="base64data",
        confirmation_text="Report submitted.",
    )
    assert resp.success is True
    assert resp.reference_number == "HC-2026-12345"


def test_submit_response_failure():
    resp = SubmitResponse(
        success=False,
        target="police-uk",
        error="Site unreachable",
        fallback_report="--- INCIDENT REPORT ---",
        target_url="https://www.police.uk/ro/report/hate-crime/forms/v1/hate-crime-online2/",
    )
    assert resp.success is False
    assert resp.error == "Site unreachable"


def test_dob_model():
    dob = DOB(day="15", month="06", year="1990")
    assert dob.day == "15"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd adil-report-bridge && python -m pytest tests/test_models.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'models')

- [ ] **Step 3: Write models.py**

Create `adil-report-bridge/models.py`:

```python
"""Pydantic models for the report bridge service."""
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class DOB(BaseModel):
    day: str = Field(..., min_length=1, max_length=2)
    month: str = Field(..., min_length=1, max_length=2)
    year: str = Field(..., min_length=4, max_length=4)


class SubmitRequest(BaseModel):
    """Request to submit a report to a target form."""
    target: str = Field(..., description="Target form identifier, e.g. 'police-uk'.")
    data: Dict[str, Any] = Field(..., description="Flat dict of form field values.")


class SubmitResponse(BaseModel):
    """Response from a report submission attempt."""
    success: bool
    target: str
    reference_number: Optional[str] = None
    confirmation_screenshot: Optional[str] = None
    confirmation_text: Optional[str] = None
    submitted_at: Optional[datetime] = None
    error: Optional[str] = None
    fallback_report: Optional[str] = None
    target_url: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str


class TargetInfo(BaseModel):
    name: str
    url: str
    required_fields: List[str]
    optional_fields: List[str]
    coverage: str


class TargetHealthInfo(BaseModel):
    reachable: bool
    last_checked: Optional[datetime] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd adil-report-bridge && python -m pytest tests/test_models.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add adil-report-bridge/models.py adil-report-bridge/tests/test_models.py
git commit -m "feat(bridge): add Pydantic request/response models"
```

---

### Task 3: Target configuration

**Files:**
- Create: `adil-report-bridge/targets.py`
- Create: `adil-report-bridge/tests/test_targets.py`

- [ ] **Step 1: Write failing tests**

Create `adil-report-bridge/tests/test_targets.py`:

```python
"""Tests for target configuration."""
import pytest
from targets import TARGETS, get_target, validate_data_for_target


def test_police_uk_target_exists():
    assert "police-uk" in TARGETS


def test_police_uk_has_required_keys():
    t = TARGETS["police-uk"]
    assert "name" in t
    assert "url" in t
    assert "instructions" in t
    assert "required_fields" in t
    assert "optional_fields" in t
    assert "coverage" in t


def test_police_uk_url():
    t = TARGETS["police-uk"]
    assert "police.uk" in t["url"]


def test_get_target_valid():
    t = get_target("police-uk")
    assert t["name"] == "Police UK — National Hate Crime Report"


def test_get_target_invalid():
    assert get_target("nonexistent") is None


def test_validate_data_all_required_present():
    data = {
        "first_name": "Ahmad",
        "surname": "Hassan",
        "dob": {"day": "15", "month": "06", "year": "1990"},
        "gender": "male",
        "email": "ahmad@example.com",
        "incident_details": "Something happened",
        "location": "London",
        "date_time": "10 March 2026",
    }
    missing = validate_data_for_target("police-uk", data)
    assert missing == []


def test_validate_data_missing_fields():
    data = {"first_name": "Ahmad"}
    missing = validate_data_for_target("police-uk", data)
    assert "surname" in missing
    assert "email" in missing
    assert "incident_details" in missing
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd adil-report-bridge && python -m pytest tests/test_targets.py -v`
Expected: FAIL

- [ ] **Step 3: Write targets.py**

Create `adil-report-bridge/targets.py`:

```python
"""Target form configurations for the report bridge.

Each target defines a reporting portal with its URL, AI agent instructions,
and required/optional field lists. Adding a new target = adding a dict entry.
"""
from typing import Optional, Dict, List, Any

TARGETS: Dict[str, Dict[str, Any]] = {
    "police-uk": {
        "name": "Police UK — National Hate Crime Report",
        "url": "https://www.police.uk/ro/report/hate-crime/forms/v1/hate-crime-online2/",
        "instructions": (
            "Fill the multi-step hate crime reporting form with the provided data. "
            "Step 1: Enter personal details (first name, surname, date of birth, gender). "
            "Step 2: Enter contact details (email, phone, address). "
            "Step 3: Select role (victim, witness, or third party). "
            "Step 4: Enter incident details (what happened, where, when). "
            "Step 5: Add any evidence or URLs. "
            "Step 6: Enter suspect description if provided. "
            "Step 7: Review all details and submit. "
            "Always add 'Submitted via AskAdil (askadil.org) on behalf of the reporter' "
            "in the additional information field. "
            "After submission, capture the confirmation page including any reference number."
        ),
        "required_fields": [
            "first_name", "surname", "dob", "gender", "email",
            "incident_details", "location", "date_time",
        ],
        "optional_fields": [
            "phone", "address", "role", "suspect_description",
            "additional_info", "evidence_urls",
        ],
        "coverage": "England & Wales",
    },
}


def get_target(target_id: str) -> Optional[Dict[str, Any]]:
    """Return target config or None if not found."""
    return TARGETS.get(target_id)


def validate_data_for_target(target_id: str, data: Dict[str, Any]) -> List[str]:
    """Return list of missing required fields for the given target."""
    target = get_target(target_id)
    if not target:
        return [f"Unknown target: {target_id}"]
    return [f for f in target["required_fields"] if f not in data or not data[f]]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd adil-report-bridge && python -m pytest tests/test_targets.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add adil-report-bridge/targets.py adil-report-bridge/tests/test_targets.py
git commit -m "feat(bridge): add police-uk target configuration"
```

---

### Task 4: Screenshot utility

**Files:**
- Create: `adil-report-bridge/screenshot.py`

- [ ] **Step 1: Write screenshot.py**

Create `adil-report-bridge/screenshot.py`:

```python
"""Screenshot capture and compression utility.

Resizes screenshots to max 1024px wide and compresses to JPEG
to keep the base64 payload under 500KB.
"""
import base64
import io
from PIL import Image


MAX_WIDTH = 1024
MAX_SIZE_BYTES = 500_000  # 500KB


def compress_screenshot(png_bytes: bytes) -> str:
    """Compress a PNG screenshot to JPEG, resize, and return base64.

    Args:
        png_bytes: Raw PNG screenshot bytes from Playwright.

    Returns:
        Base64-encoded JPEG string, max 500KB.
    """
    img = Image.open(io.BytesIO(png_bytes))

    # Resize if wider than MAX_WIDTH
    if img.width > MAX_WIDTH:
        ratio = MAX_WIDTH / img.width
        new_height = int(img.height * ratio)
        img = img.resize((MAX_WIDTH, new_height), Image.LANCZOS)

    # Convert to RGB (JPEG doesn't support alpha)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Compress with decreasing quality until under size limit
    for quality in (85, 70, 50, 30):
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality)
        if buffer.tell() <= MAX_SIZE_BYTES:
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
        buffer.seek(0)

    # Last resort: return whatever we have
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
```

- [ ] **Step 2: Commit**

```bash
git add adil-report-bridge/screenshot.py
git commit -m "feat(bridge): add screenshot compression utility"
```

---

### Task 5: Browser agent wrapper

**Files:**
- Create: `adil-report-bridge/browser_agent.py`

This is the core of the bridge — it wraps browser-use to fill and submit forms.

- [ ] **Step 1: Write browser_agent.py**

Create `adil-report-bridge/browser_agent.py`:

```python
"""Browser automation agent for form submission.

Uses browser-use with Gemini Flash to fill multi-step web forms.
The AI agent reads form labels semantically, adapting to UI changes.
"""
import os
import logging
import asyncio
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from browser_use import Agent, Browser, BrowserConfig
from langchain_google_genai import ChatGoogleGenerativeAI

from targets import get_target
from screenshot import compress_screenshot

logger = logging.getLogger(__name__)

# Concurrency: max 1 Chromium session to avoid OOM
_semaphore = asyncio.Semaphore(1)
SEMAPHORE_TIMEOUT = 30  # seconds to wait before returning 503


def _build_task_prompt(target_config: Dict[str, Any], data: Dict[str, Any]) -> str:
    """Build the agent task prompt from target instructions and user data.

    Formats the data as key-value pairs the AI agent can reference
    while filling the form.
    """
    instructions = target_config["instructions"]

    # Format data for the agent, excluding None/empty values
    data_lines = []
    for key, value in data.items():
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, dict):
            # Handle DOB: {"day": "15", "month": "06", "year": "1990"}
            formatted = ", ".join(f"{k}: {v}" for k, v in value.items())
            data_lines.append(f"- {key}: {formatted}")
        elif isinstance(value, list):
            data_lines.append(f"- {key}: {', '.join(str(v) for v in value)}")
        else:
            data_lines.append(f"- {key}: {value}")

    data_block = "\n".join(data_lines)

    return (
        f"{instructions}\n\n"
        f"DATA TO FILL IN THE FORM:\n{data_block}\n\n"
        f"IMPORTANT:\n"
        f"- If a field is not in the data above, leave it blank or skip it.\n"
        f"- For 'additional_info' or free-text fields, include: "
        f"'Submitted via AskAdil (askadil.org) on behalf of the reporter.'\n"
        f"- After submitting, DO NOT close the page. Stay on the confirmation page.\n"
        f"- Report the confirmation text and any reference number you see."
    )


async def submit_report(
    target_id: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Submit a report using AI browser automation.

    Args:
        target_id: Target form identifier (e.g. "police-uk").
        data: Flat dict of form field values.

    Returns:
        Dict with success, reference_number, confirmation_screenshot, etc.
    """
    target_config = get_target(target_id)
    if not target_config:
        return {
            "success": False,
            "error": f"Unknown target: {target_id}",
            "target": target_id,
        }

    # Acquire semaphore with timeout
    try:
        await asyncio.wait_for(_semaphore.acquire(), timeout=SEMAPHORE_TIMEOUT)
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Service busy — another submission is in progress. Please try again shortly.",
            "target": target_id,
        }

    browser = None
    try:
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        llm = ChatGoogleGenerativeAI(model=model)

        browser = Browser(config=BrowserConfig(headless=True))
        task_prompt = _build_task_prompt(target_config, data)

        agent = Agent(
            task=task_prompt,
            llm=llm,
            browser=browser,
            initial_actions=[
                {"go_to_url": {"url": target_config["url"]}},
            ],
        )

        logger.info("Starting form submission for target=%s", target_id)
        history = await asyncio.wait_for(agent.run(max_steps=50), timeout=60)

        # Extract result
        final_result = history.final_result() or ""
        is_successful = history.is_successful()

        # Take screenshot of final page
        screenshot_b64 = None
        try:
            page = await agent.browser_context.get_current_page()
            if page:
                png_bytes = await asyncio.wait_for(
                    page.screenshot(full_page=False), timeout=10
                )
                screenshot_b64 = compress_screenshot(png_bytes)
        except Exception as e:
            logger.warning("Screenshot capture failed: %s", e)

        if is_successful:
            # Try to extract reference number from the result
            reference = _extract_reference(final_result)
            return {
                "success": True,
                "target": target_id,
                "reference_number": reference,
                "confirmation_screenshot": screenshot_b64,
                "confirmation_text": final_result[:500],
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            return {
                "success": False,
                "target": target_id,
                "error": f"Form submission did not complete successfully. Agent result: {final_result[:200]}",
                "confirmation_screenshot": screenshot_b64,
                "target_url": target_config["url"],
            }

    except asyncio.TimeoutError:
        logger.error("Form submission timed out for target=%s", target_id)
        return {
            "success": False,
            "target": target_id,
            "error": "Form submission timed out after 60 seconds.",
            "target_url": target_config["url"],
        }
    except Exception as e:
        logger.error("Form submission error for target=%s: %s", target_id, e)
        return {
            "success": False,
            "target": target_id,
            "error": f"Form submission failed: {str(e)}",
            "target_url": target_config["url"],
        }
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        _semaphore.release()
        # Explicit PII cleanup
        del data


def _extract_reference(text: str) -> Optional[str]:
    """Try to extract a reference number from the agent's final result text."""
    import re
    # Common patterns: HC-2026-12345, REF: 12345, Reference: ABC123
    patterns = [
        r"(?:ref(?:erence)?[\s:]*#?\s*)([A-Z0-9-]{5,})",
        r"(HC-\d{4}-\d+)",
        r"(?:number[\s:]*#?\s*)([A-Z0-9-]{5,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None
```

- [ ] **Step 2: Commit**

```bash
git add adil-report-bridge/browser_agent.py
git commit -m "feat(bridge): add browser-use agent wrapper for form submission"
```

---

### Task 6: Bridge FastAPI app

**Files:**
- Create: `adil-report-bridge/app.py`
- Create: `adil-report-bridge/tests/test_app.py`

- [ ] **Step 1: Write failing tests**

Create `adil-report-bridge/tests/test_app.py`:

```python
"""Tests for the bridge FastAPI app."""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

# Set env vars before importing app
import os
os.environ["BRIDGE_API_KEY"] = "test-bridge-key"
os.environ["GOOGLE_API_KEY"] = "test-google-key"

from app import app

client = TestClient(app)
HEADERS = {"X-Bridge-Key": "test-bridge-key"}


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


def test_targets():
    resp = client.get("/targets", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "police-uk" in data


def test_submit_no_auth():
    resp = client.post("/submit", json={"target": "police-uk", "data": {}})
    assert resp.status_code == 403


def test_submit_invalid_target():
    resp = client.post(
        "/submit",
        headers=HEADERS,
        json={"target": "nonexistent", "data": {}},
    )
    assert resp.status_code == 400


def test_submit_missing_fields():
    resp = client.post(
        "/submit",
        headers=HEADERS,
        json={"target": "police-uk", "data": {"first_name": "Ahmad"}},
    )
    assert resp.status_code == 422


@patch("app.submit_report", new_callable=AsyncMock)
def test_submit_success(mock_submit):
    mock_submit.return_value = {
        "success": True,
        "target": "police-uk",
        "reference_number": "HC-2026-99999",
        "confirmation_screenshot": "base64data",
        "confirmation_text": "Your report has been submitted.",
        "submitted_at": "2026-03-22T19:30:00Z",
    }
    resp = client.post(
        "/submit",
        headers=HEADERS,
        json={
            "target": "police-uk",
            "data": {
                "first_name": "Ahmad",
                "surname": "Hassan",
                "dob": {"day": "15", "month": "06", "year": "1990"},
                "gender": "male",
                "email": "ahmad@example.com",
                "incident_details": "Hate incident occurred",
                "location": "London E1",
                "date_time": "10 March 2026",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["reference_number"] == "HC-2026-99999"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd adil-report-bridge && python -m pytest tests/test_app.py -v`
Expected: FAIL

- [ ] **Step 3: Write app.py**

Create `adil-report-bridge/app.py`:

```python
"""
adil-report-bridge — AI-Powered Form Submission Service

Internal microservice that uses browser-use + Gemini Flash to submit
hate crime reports to external reporting portals on behalf of AskAdil users.

Endpoints:
    POST /submit          - Submit a report to a target form
    GET  /health          - Liveness probe
    GET  /health/targets  - Target form reachability (cached 5 min)
    GET  /targets         - Available targets and required fields
"""
import os
import time
import secrets
import logging
from typing import Dict

from fastapi import FastAPI, HTTPException, Security, Request
from fastapi.security import APIKeyHeader
from dotenv import load_dotenv

from models import (
    SubmitRequest, SubmitResponse, HealthResponse,
    TargetInfo, TargetHealthInfo,
)
from targets import TARGETS, get_target, validate_data_for_target
from browser_agent import submit_report

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

VERSION = "0.1.0"

# --- Authentication ---
BRIDGE_API_KEY = os.getenv("BRIDGE_API_KEY")
api_key_header = APIKeyHeader(name="X-Bridge-Key", auto_error=False)


async def verify_bridge_key(api_key: str = Security(api_key_header)) -> str:
    if not BRIDGE_API_KEY:
        logger.warning("BRIDGE_API_KEY not set — running in OPEN mode")
        return "open"
    if not api_key:
        raise HTTPException(status_code=403, detail="Missing X-Bridge-Key header.")
    if not secrets.compare_digest(api_key, BRIDGE_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid bridge key.")
    return api_key


# --- App ---
app = FastAPI(
    title="adil-report-bridge",
    description="AI-powered form submission service for AskAdil.",
    version=VERSION,
    docs_url=None,   # Internal service, no public docs
    redoc_url=None,
)


# --- Health (no auth — used by Railway health check) ---
@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy", version=VERSION)


# --- Target health (auth required) ---
_target_health_cache: Dict[str, TargetHealthInfo] = {}
_target_health_ts: float = 0
TARGET_HEALTH_TTL = 300  # 5 minutes


@app.get("/health/targets")
async def health_targets(_key: str = Security(verify_bridge_key)):
    global _target_health_cache, _target_health_ts
    now = time.time()

    if now - _target_health_ts < TARGET_HEALTH_TTL and _target_health_cache:
        return {"targets": _target_health_cache}

    import httpx
    results = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        for tid, tcfg in TARGETS.items():
            try:
                resp = await client.head(tcfg["url"])
                results[tid] = {
                    "reachable": resp.status_code < 500,
                    "last_checked": time.time(),
                }
            except Exception:
                results[tid] = {"reachable": False, "last_checked": time.time()}

    _target_health_cache = results
    _target_health_ts = now
    return {"targets": results}


# --- Targets list (auth required) ---
@app.get("/targets")
async def list_targets(_key: str = Security(verify_bridge_key)):
    return {
        tid: TargetInfo(
            name=tcfg["name"],
            url=tcfg["url"],
            required_fields=tcfg["required_fields"],
            optional_fields=tcfg["optional_fields"],
            coverage=tcfg["coverage"],
        )
        for tid, tcfg in TARGETS.items()
    }


# --- Submit (auth required) ---
@app.post("/submit", response_model=SubmitResponse)
async def submit(body: SubmitRequest, _key: str = Security(verify_bridge_key)):
    # Validate target exists
    target = get_target(body.target)
    if not target:
        raise HTTPException(status_code=400, detail=f"Unknown target: {body.target}")

    # Validate required fields
    missing = validate_data_for_target(body.target, body.data)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required fields for {body.target}: {', '.join(missing)}",
        )

    # Log submission attempt (NO PII)
    logger.info("Submission attempt: target=%s", body.target)

    # Run browser agent
    result = await submit_report(body.target, body.data)

    # Log result (NO PII)
    logger.info(
        "Submission result: target=%s success=%s ref=%s",
        body.target,
        result.get("success"),
        result.get("reference_number", "none"),
    )

    return SubmitResponse(**result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd adil-report-bridge && python -m pytest tests/test_app.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add adil-report-bridge/app.py adil-report-bridge/tests/test_app.py
git commit -m "feat(bridge): add FastAPI app with /submit, /health, /targets endpoints"
```

---

### Task 7: RAG API — models for submit-report

**Files:**
- Modify: `adil-rag-api/models.py`

- [ ] **Step 1: Add new models to the bottom of `adil-rag-api/models.py`**

Append after the `AnalyzeContentResponse` class (after line 392):

```python
# ============================================================================
# Report Submission Models
# ============================================================================


class ReporterInfo(BaseModel):
    """Personal details of the person filing the report.
    WARNING: PII — never log, never persist."""
    first_name: str = Field(..., min_length=1, max_length=100)
    surname: str = Field(..., min_length=1, max_length=100)
    dob: dict = Field(..., description="Date of birth: {day, month, year}.")
    gender: str = Field(..., min_length=1, max_length=50)
    email: str = Field(..., min_length=5, max_length=200)
    phone: Optional[str] = Field(None, max_length=30)
    address: Optional[str] = Field(None, max_length=500)


class IncidentInfo(BaseModel):
    """Incident details extracted from the AskAdil conversation."""
    details: str = Field(..., min_length=10, max_length=50000)
    location: str = Field(..., min_length=1, max_length=1000)
    date_time: str = Field(..., min_length=1, max_length=500)
    suspect_description: Optional[str] = Field(None, max_length=5000)
    role: str = Field("victim", description="victim, witness, or third_party.")


class SubmitReportRequest(BaseModel):
    """Request to submit a hate crime report via the bridge service."""
    target: str = Field(..., description="Target form ID, e.g. 'police-uk'.")
    reporter: ReporterInfo
    incident: IncidentInfo
    evidence_urls: Optional[List[str]] = Field(default_factory=list)
    conversation_history: Optional[List[ConversationTurn]] = Field(
        None,
        description="Used ONLY for fallback report generation if bridge fails. Not sent to bridge.",
        max_length=50,
    )


class SubmitReportResponse(BaseModel):
    """Response from report submission."""
    success: bool
    target: str
    reference_number: Optional[str] = None
    confirmation_screenshot: Optional[str] = None
    message: Optional[str] = None
    submitted_at: Optional[str] = None
    error: Optional[str] = None
    fallback_report: Optional[str] = None
    target_url: Optional[str] = None
    form_guide: Optional[str] = None
```

- [ ] **Step 2: Add new models to the imports in `adil-rag-api/app.py`**

Update the imports from `models` (line 45-49 of `adil-rag-api/app.py`) to include:

```python
from models import (
    QueryRequest, QueryResponse, HealthResponse, StatsResponse,
    AnalyzeContentRequest, AnalyzeContentResponse, ExtractedContent, ContentType,
    ImageQueryRequest, ImageData, ALLOWED_IMAGE_MIMES,
    SubmitReportRequest, SubmitReportResponse,
)
```

- [ ] **Step 3: Commit**

```bash
git add adil-rag-api/models.py adil-rag-api/app.py
git commit -m "feat(api): add SubmitReport request/response models"
```

---

### Task 8: RAG API — submit-report and report-targets endpoints

**Files:**
- Modify: `adil-rag-api/app.py`

- [ ] **Step 1: Add env vars and bridge client setup**

After the CORS configuration section (~line 336 after the validation error handler), add:

```python
# --- Report Bridge Configuration ---
REPORT_BRIDGE_URL = os.getenv("REPORT_BRIDGE_URL")
BRIDGE_API_KEY = os.getenv("BRIDGE_API_KEY")
```

- [ ] **Step 2: Add the /api/v1/report-targets endpoint**

Add before the `if __name__` block at the bottom of `adil-rag-api/app.py`:

```python
# =============================================================================
# REPORT SUBMISSION ENDPOINTS
# =============================================================================

@app.get("/api/v1/report-targets", tags=["Report Submission"])
@limiter.limit(RATE_LIMIT_GENERAL)
async def report_targets(request: Request, _api_key: str = Security(verify_api_key)):
    """Return available reporting targets with required fields."""
    if not REPORT_BRIDGE_URL:
        raise HTTPException(status_code=503, detail="Report bridge not configured.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{REPORT_BRIDGE_URL}/targets",
                headers={"X-Bridge-Key": BRIDGE_API_KEY or ""},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch report targets: {e}")
            raise HTTPException(status_code=503, detail="Report bridge unavailable.")
```

- [ ] **Step 3: Add the /api/v1/submit-report endpoint**

Add after the report-targets endpoint:

```python
@app.post(
    "/api/v1/submit-report",
    response_model=SubmitReportResponse,
    tags=["Report Submission"],
    summary="Submit a hate crime report via automated form filling",
)
@limiter.limit(RATE_LIMIT_QUERY)
async def submit_report(
    request: Request,
    body: SubmitReportRequest,
    _api_key: str = Security(verify_api_key),
):
    """Submit a hate crime report to an external reporting portal.

    The bridge service fills and submits the form using AI browser automation.
    If submission fails, a fallback report is generated for manual submission.

    WARNING: This endpoint handles PII. Data is passed through to the bridge
    and never persisted. Do NOT retry on failure — treat as final.
    """
    if not REPORT_BRIDGE_URL:
        raise HTTPException(status_code=503, detail="Report bridge not configured.")

    # Transform nested public format → flat bridge format
    bridge_data = {
        "first_name": body.reporter.first_name,
        "surname": body.reporter.surname,
        "dob": body.reporter.dob,
        "gender": body.reporter.gender,
        "email": body.reporter.email,
        "phone": body.reporter.phone,
        "address": body.reporter.address,
        "role": body.incident.role,
        "incident_details": body.incident.details,
        "location": body.incident.location,
        "date_time": body.incident.date_time,
        "suspect_description": body.incident.suspect_description,
        "evidence_urls": body.evidence_urls or [],
        "additional_info": "Submitted via AskAdil (askadil.org) on behalf of the reporter.",
    }

    # Remove None values
    bridge_data = {k: v for k, v in bridge_data.items() if v is not None}

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{REPORT_BRIDGE_URL}/submit",
                headers={"X-Bridge-Key": BRIDGE_API_KEY or ""},
                json={"target": body.target, "data": bridge_data},
            )
            resp.raise_for_status()
            result = resp.json()
    except httpx.TimeoutException:
        logger.error("Bridge timeout for target=%s", body.target)
        result = {"success": False}
    except Exception as e:
        logger.error("Bridge call failed for target=%s: %s", body.target, e)
        result = {"success": False}

    # Clean up PII from local scope
    del bridge_data

    if result.get("success"):
        ref = result.get("reference_number", "N/A")
        return SubmitReportResponse(
            success=True,
            target=body.target,
            reference_number=result.get("reference_number"),
            confirmation_screenshot=result.get("confirmation_screenshot"),
            message=(
                f"Your hate crime report has been submitted to "
                f"{body.target.replace('-', ' ').title()}. "
                f"Please save reference number {ref}."
            ),
            submitted_at=result.get("submitted_at"),
        )
    else:
        # Generate fallback report from conversation history
        fallback = None
        form_guide = None
        if rag_service and body.conversation_history:
            try:
                history_dicts = [
                    {"role": t.role, "content": t.content}
                    for t in body.conversation_history
                ]
                fallback_answer, _, _, _ = await rag_service.query(
                    query_text=(
                        "Generate a structured incident report summary from this conversation "
                        "that the user can copy-paste into a hate crime reporting form. "
                        "Include sections: WHAT HAPPENED, WHERE, WHEN, SUSPECT DESCRIPTION. "
                        "Do NOT include any personal information like names or contact details."
                    ),
                    max_sources=0,
                    include_viability=False,
                    conversation_history=history_dicts,
                )
                fallback = fallback_answer
            except Exception as e:
                logger.error(f"Fallback report generation failed: {e}")

        return SubmitReportResponse(
            success=False,
            target=body.target,
            error=result.get("error", "Automated submission failed. Please submit manually using the report below."),
            fallback_report=fallback,
            target_url=result.get("target_url"),
            form_guide=form_guide,
        )
```

- [ ] **Step 4: Commit**

```bash
git add adil-rag-api/app.py
git commit -m "feat(api): add /api/v1/submit-report and /api/v1/report-targets endpoints"
```

---

### Task 9: Frontend — report submission flow

**Files:**
- Modify: `adil-frontend/app.py`

- [ ] **Step 1: Add report submission action button handler**

Add after the `on_suggested_question` callback at the end of `adil-frontend/app.py` (before any `if __name__` block), add the following:

```python
# --- Report Submission Flow ---

REPORT_PII_FIELDS = [
    ("first_name", "What is your **first name**?", True),
    ("surname", "What is your **surname**?", True),
    ("dob_str", "What is your **date of birth**? (DD/MM/YYYY)", True),
    ("gender", "What is your **gender**? (Male / Female / Self-describe)", True),
    ("email", "What is your **email address**?", True),
    ("phone", "What is your **phone number**? (optional — press Enter to skip)", False),
]


@cl.action_callback("start_report")
async def on_start_report(action: cl.Action):
    """Handle clicks on 'Report to Police' action button."""
    target = action.payload.get("target", "police-uk")
    cl.user_session.set("report_target", target)
    cl.user_session.set("report_data", {})
    cl.user_session.set("report_field_index", 0)
    cl.user_session.set("collecting_report_pii", True)

    # Ask first field
    field_name, prompt, required = REPORT_PII_FIELDS[0]
    await cl.Message(content=f"📋 **Report Submission — Police UK**\n\nI'll need a few details to submit the report on your behalf.\n\n{prompt}").send()


async def _handle_report_pii(message_text: str):
    """Process PII collection during report flow. Returns True if still collecting."""
    if not cl.user_session.get("collecting_report_pii"):
        return False

    idx = cl.user_session.get("report_field_index", 0)
    data = cl.user_session.get("report_data", {})
    field_name, prompt, required = REPORT_PII_FIELDS[idx]

    value = message_text.strip()

    # Allow skip for optional fields
    if not value and not required:
        value = None
    elif not value and required:
        await cl.Message(content=f"This field is required. {prompt}").send()
        return True

    data[field_name] = value
    cl.user_session.set("report_data", data)

    # Move to next field
    next_idx = idx + 1
    if next_idx < len(REPORT_PII_FIELDS):
        cl.user_session.set("report_field_index", next_idx)
        _, next_prompt, _ = REPORT_PII_FIELDS[next_idx]
        await cl.Message(content=next_prompt).send()
        return True

    # All fields collected — show consent summary
    cl.user_session.set("collecting_report_pii", False)
    cl.user_session.set("awaiting_report_consent", True)

    history = cl.user_session.get("conversation_history") or []

    # Build consent summary (show what will be submitted)
    consent_msg = (
        "📋 **Please review the information below before I submit your report.**\n\n"
        f"**Name:** {data.get('first_name')} {data.get('surname')}\n"
        f"**Date of Birth:** {data.get('dob_str')}\n"
        f"**Gender:** {data.get('gender')}\n"
        f"**Email:** {data.get('email')}\n"
    )
    if data.get("phone"):
        consent_msg += f"**Phone:** {data.get('phone')}\n"

    consent_msg += (
        "\n**Incident details** will be taken from our conversation.\n\n"
        "⚠️ **By confirming, a hate crime report will be submitted to Police UK on your behalf.**\n\n"
        "Do you confirm? (yes / no)"
    )
    await cl.Message(content=consent_msg).send()
    return True


async def _handle_report_consent(message_text: str):
    """Handle the consent confirmation for report submission."""
    if not cl.user_session.get("awaiting_report_consent"):
        return False

    cl.user_session.set("awaiting_report_consent", False)
    response = message_text.strip().lower()

    if response not in ("yes", "y", "confirm"):
        await cl.Message(content="Report submission cancelled. Your information has been discarded.").send()
        cl.user_session.set("report_data", {})
        return True

    data = cl.user_session.get("report_data", {})
    target = cl.user_session.get("report_target", "police-uk")
    history = cl.user_session.get("conversation_history") or []

    # Parse DOB
    dob_parts = data.get("dob_str", "01/01/1990").split("/")
    dob = {"day": dob_parts[0], "month": dob_parts[1], "year": dob_parts[2]} if len(dob_parts) == 3 else {"day": "01", "month": "01", "year": "1990"}

    # Build incident details from conversation history
    incident_text = "\n".join(
        turn["content"] for turn in history if turn["role"] == "user"
    )

    # Build request payload
    payload = {
        "target": target,
        "reporter": {
            "first_name": data.get("first_name"),
            "surname": data.get("surname"),
            "dob": dob,
            "gender": data.get("gender"),
            "email": data.get("email"),
            "phone": data.get("phone"),
        },
        "incident": {
            "details": incident_text or "Hate crime incident reported via AskAdil.",
            "location": "Provided in conversation",
            "date_time": "Provided in conversation",
            "role": "victim",
        },
        "evidence_urls": [],
        "conversation_history": [
            {"role": t["role"], "content": t["content"]} for t in history
        ] if history else None,
    }

    msg = cl.Message(content="*⏳ Submitting your report to Police UK...*")
    await msg.send()

    try:
        api_headers = {"X-API-Key": ADIL_API_KEY} if ADIL_API_KEY else {}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{RAG_API_URL}/api/v1/submit-report",
                headers=api_headers,
                json=payload,
            )
            resp.raise_for_status()
            result = resp.json()
    except Exception as e:
        await msg.stream_token(f"\n\n❌ Failed to connect to the reporting service: {str(e)}")
        await msg.update()
        cl.user_session.set("report_data", {})
        return True

    # Clear PII immediately
    cl.user_session.set("report_data", {})

    if result.get("success"):
        ref = result.get("reference_number", "N/A")
        response_text = (
            f"✅ **Report submitted successfully!**\n\n"
            f"**Reference Number:** `{ref}`\n\n"
        )
        if result.get("message"):
            response_text += f"{result['message']}\n\n"
        response_text += (
            "⚠️ **Please save this reference number now.** "
            "AskAdil does not store your personal information after submission.\n\n"
            "Police may contact you at the email/phone you provided. "
            "If you don't hear back within 7 days, call **101** and quote your reference number."
        )

        # Show confirmation screenshot if available
        if result.get("confirmation_screenshot"):
            response_text += "\n\n📸 **Confirmation screenshot saved below.**"

        msg.content = response_text
        await msg.update()
    else:
        error_text = f"❌ **Automated submission was not successful.**\n\n"
        if result.get("error"):
            error_text += f"{result['error']}\n\n"

        if result.get("fallback_report"):
            error_text += (
                "📋 **Here is your incident report — you can submit it manually:**\n\n"
                f"```\n{result['fallback_report']}\n```\n\n"
            )

        if result.get("target_url"):
            error_text += f"🔗 **Submit manually here:** [{result['target_url']}]({result['target_url']})\n"

        msg.content = error_text
        await msg.update()

    return True
```

- [ ] **Step 2: Update the main message handler to intercept PII collection**

Modify the `main` function in `adil-frontend/app.py` to check for report PII collection before processing as a normal query. Add at the top of the `main` function, before the image handling:

```python
@cl.on_message
async def main(message: cl.Message):
    """Handle incoming messages with URL, image, conversation memory, and report support"""
    # Check if we're collecting PII for a report
    if await _handle_report_pii(message.content):
        return
    if await _handle_report_consent(message.content):
        return

    # ... rest of existing main function unchanged ...
```

- [ ] **Step 3: Add report action button to post-intake responses**

In the `_send_query` function, after the suggested question actions are built (~line 215), add a report action button:

```python
        # Add "Report to Police" action button
        actions.append(
            cl.Action(
                name="start_report",
                payload={"target": "police-uk"},
                label="📋 Report to Police UK",
            )
        )
```

- [ ] **Step 4: Commit**

```bash
git add adil-frontend/app.py
git commit -m "feat(frontend): add police report submission flow with PII collection and consent"
```

---

### Task 10: Deploy bridge service to Railway

**Files:** No code changes — deployment only.

- [ ] **Step 1: Create the bridge service on Railway**

```bash
cd adil-report-bridge
railway service create adil-report-bridge
railway link
# Select: project-adil → production → adil-report-bridge
```

- [ ] **Step 2: Set environment variables in Railway dashboard**

Set these in the Railway dashboard for `adil-report-bridge`:
- `GOOGLE_API_KEY` — your Google API key (same key used for Gemini in RAG API)
- `BRIDGE_API_KEY` — generate a new secret (e.g. `openssl rand -hex 32`)
- `GEMINI_MODEL` — `gemini-2.5-flash`

Set these in Railway dashboard for `adil-rag-api`:
- `REPORT_BRIDGE_URL` — the internal Railway URL of the bridge service (e.g. `http://adil-report-bridge.railway.internal:8080`)
- `BRIDGE_API_KEY` — same secret as above

- [ ] **Step 3: Deploy bridge**

```bash
cd adil-report-bridge
railway up
```

- [ ] **Step 4: Deploy updated RAG API**

```bash
cd adil-rag-api
railway service adil-rag-api
railway up
```

- [ ] **Step 5: Deploy updated frontend**

```bash
cd adil-frontend
railway service adil-frontend
railway up
```

- [ ] **Step 6: Verify health**

```bash
# Check bridge health (via RAG API, since bridge is internal)
curl -H "X-API-Key: $ADIL_API_KEY" https://adil-rag-api-production.up.railway.app/api/v1/report-targets
```

- [ ] **Step 7: Commit any deployment config changes**

```bash
git add -A
git commit -m "chore: deploy report bridge service to Railway"
```

---

## Verification Checklist

After all tasks are complete, verify end-to-end:

- [ ] Bridge `/health` returns 200
- [ ] RAG API `/api/v1/report-targets` returns police-uk target
- [ ] Frontend shows "Report to Police UK" button after a query
- [ ] Clicking the button starts PII collection flow
- [ ] Consent screen shows all collected information
- [ ] Confirming triggers the bridge submission
- [ ] Success shows reference number + screenshot + save warning
- [ ] Failure shows fallback report + manual link
