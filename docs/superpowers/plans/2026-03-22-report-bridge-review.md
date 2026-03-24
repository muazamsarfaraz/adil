# Report Bridge Plan Review

**Reviewer:** Code Review Agent
**Date:** 2026-03-22
**Verdict:** NOT APPROVED -- 4 Critical issues, 3 Important issues, 4 Suggestions

---

## Critical Issues (must fix before implementation)

### C1. Wrong LLM import -- `ChatGoogle` does not exist

**Plan (browser_agent.py, line 503):**
```python
from browser_use import Agent, Browser, ChatGoogle
```

**Reality:** browser-use 0.1.48 does NOT export `ChatGoogle`. The correct class is `ChatGoogleGenerativeAI` from `langchain_google_genai`:
```python
from browser_use import Agent, Browser
from langchain_google_genai import ChatGoogleGenerativeAI
```

And the constructor is `ChatGoogleGenerativeAI(model=model)`, not `ChatGoogle(model=model)`.

Additionally, `langchain-google-genai` (not `google-genai`) must be in `requirements.txt`. The plan lists `google-genai>=0.4.0` but the actual dependency is `langchain-google-genai`.

**Impact:** The bridge service will crash on startup.

### C2. Wrong env var name for Google API key

**Plan:** Uses `GEMINI_API_KEY` throughout (`.env.example`, deployment instructions, spec).

**Reality:** browser-use checks for `GOOGLE_API_KEY` (see `REQUIRED_LLM_API_ENV_VARS` in `browser_use/agent/views.py` line 33: `'ChatGoogleGenerativeAI': ['GOOGLE_API_KEY']`). The `ChatGoogleGenerativeAI` class from langchain also uses `GOOGLE_API_KEY` by default.

**Fix:** Either rename the env var to `GOOGLE_API_KEY` everywhere, or pass `google_api_key=os.getenv("GEMINI_API_KEY")` explicitly to the constructor. The former is cleaner.

### C3. Wrong `initial_actions` action name

**Plan (browser_agent.py, line 591-593):**
```python
initial_actions=[
    {"open_url": target_config["url"]},
]
```

**Reality:** The action is `go_to_url`, not `open_url`. The parameter structure is:
```python
initial_actions=[
    {"go_to_url": {"url": target_config["url"]}},
]
```

See `browser_use/controller/service.py` line 94 and `browser_use/controller/views.py` line 9 (`GoToUrlAction` with a `url` field).

**Impact:** The agent will fail to navigate to the target form.

### C4. `browser.get_context()` does not exist

**Plan (browser_agent.py, lines 611-614):**
```python
context = await browser.get_context()
pages = context.pages
```

**Reality:** `Browser` has no `get_context()` method. The agent stores its context as `agent.browser_context` (a `BrowserContext` instance). To get the current page:
```python
page = await agent.browser_context.get_current_page()
png_bytes = await asyncio.wait_for(
    page.screenshot(full_page=False), timeout=10
)
```

But note: the `agent` variable must be in scope for this. Since `agent` is a local variable in `submit_report`, this is straightforward to fix.

**Impact:** Screenshot capture will crash with `AttributeError`.

---

## Important Issues (should fix)

### I1. `Browser(headless=True)` is wrong constructor

**Plan (browser_agent.py, line 588):**
```python
browser = Browser(headless=True)
```

**Reality:** `Browser.__init__` takes a `BrowserConfig` object, not keyword args. The `headless` field is on `BrowserConfig`:
```python
from browser_use import Browser, BrowserConfig
browser = Browser(config=BrowserConfig(headless=True))
```

### I2. `requirements.txt` lists wrong dependency

**Plan:** `google-genai>=0.4.0`
**Should be:** `langchain-google-genai>=2.0.0` (the langchain wrapper that browser-use actually uses, per its dependencies list).

The plan's spec also lists `google-genai>=0.4.0` in the dependencies section. Both need updating.

### I3. Plan says "after line 392" for RAG API models -- actual last line is 393

**Plan (Task 7, Step 1):** "Append after the `AnalyzeContentResponse` class (after line 392)"
**Reality:** `AnalyzeContentResponse` ends at line 392 with the closing field, and line 393 is a blank line. The file ends at line 393. This is a minor off-by-one but the instruction "append after AnalyzeContentResponse" is clear enough. However, the new models reference `ConversationTurn` (line 1008) which exists at line 56. The import `from typing import List, Optional` at line 18 already covers `List` and `Optional`. No additional imports are needed, but the plan doesn't explicitly call this out -- the implementer should verify.

---

## Suggestions (nice to have)

### S1. Task 4 (screenshot.py) has no tests -- breaks TDD pattern

Tasks 2, 3, and 6 follow TDD (write failing tests first). Task 4 (screenshot utility) and Task 5 (browser_agent.py) skip tests entirely. The `compress_screenshot` function is pure and easy to test. Consider adding `test_screenshot.py` with tests for resize and compression logic.

### S2. Frontend `_send_query` action button placement (Task 9, Step 3)

The plan says to add the report button "after the suggested question actions are built (~line 215)". Looking at the actual code, line 215 is the end of the `for` loop, and lines 216-217 check `if actions: msg.actions = actions`. The report button append should go between line 215 and line 216 (before the `if actions` check). The plan's instruction is vague ("~line 215") and could lead to the button being added after `msg.actions` is already set.

### S3. `form_guide` is always `None` in the RAG API fallback path

In Task 8 (line 1180), `form_guide = None` is initialized and never populated. The spec's failure response includes `form_guide` with step-by-step instructions, but no code generates it. Consider generating it from the target config's `instructions` field, or remove it from the response model.

### S4. No `tests/__init__.py` file

The plan creates test files in `adil-report-bridge/tests/` but never creates `tests/__init__.py`. While pytest can work without it, the test imports (`from models import ...`) will fail unless either (a) the tests directory has an `__init__.py`, or (b) a `conftest.py` adds the parent to `sys.path`, or (c) the project is installed as a package. The plan should create `adil-report-bridge/tests/__init__.py` or a `conftest.py` with path setup.

---

## Spec Coverage Checklist

| Spec Requirement | Plan Coverage | Status |
|---|---|---|
| POST /submit endpoint | Task 6 | Covered |
| GET /health endpoint | Task 6 | Covered |
| GET /health/targets (cached 5 min) | Task 6 | Covered |
| GET /targets endpoint | Task 6 | Covered |
| X-Bridge-Key authentication | Task 6 | Covered |
| Semaphore (max 1 concurrent) | Task 5 | Covered |
| Screenshot resize/compress to 500KB | Task 4 | Covered |
| Target-agnostic config | Task 3 | Covered |
| RAG API POST /api/v1/submit-report | Task 8 | Covered |
| RAG API GET /api/v1/report-targets | Task 8 | Covered |
| RAG API data transformation | Task 8 | Covered |
| RAG API fallback report generation | Task 8 | Covered |
| RAG API no-retry policy | Task 8 | Covered (single httpx call) |
| Frontend PII collection | Task 9 | Covered |
| Frontend consent screen | Task 9 | Covered |
| Frontend success/failure display | Task 9 | Covered |
| PII cleanup after use | Tasks 5, 8, 9 | Covered |
| Dockerfile with non-root user | Task 1 | Covered |
| Railway deployment | Task 10 | Covered |
| No PII in logs | Tasks 5, 6 | Covered |

---

## File Path Consistency

All file paths are consistent between spec and plan. The plan adds three files not in the spec (`tests/test_models.py`, `tests/test_app.py`, `.env.example`) which are beneficial additions.

---

## Commit Granularity

Commits are well-scoped: one per logical unit (scaffold, models, targets, screenshot, agent, app, RAG models, RAG endpoints, frontend, deploy). This is good.

---

## Summary

The plan is well-structured and covers all spec requirements. However, the browser-use API usage has 4 critical errors that will prevent the bridge from functioning. These stem from incorrect assumptions about the browser-use library's API surface. All are straightforward to fix. After fixing C1-C4 and I1-I2, the plan should be re-reviewed and approved.
