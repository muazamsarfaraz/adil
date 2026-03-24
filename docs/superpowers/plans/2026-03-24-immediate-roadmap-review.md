# Plan Review: 2026-03-24 Immediate Roadmap

**Reviewer:** Senior Code Reviewer (Claude Opus 4.6)
**Date:** 2026-03-24
**Plan:** `E:/dev/mcbx/adil/docs/superpowers/plans/2026-03-24-immediate-roadmap.md`
**Verdict:** Mostly sound. 3 critical issues, 5 important issues, 6 suggestions.

---

## What Was Done Well

- Clear TDD flow: tests written before implementation in Tasks 3-5
- Jurisdiction-aware solicitor directory is a thoughtful design
- Prompt engineering for report generation is well-structured with explicit format constraints
- Section parser regex is robust for the expected format
- Proper use of existing patterns: `Security(verify_api_key)`, `@limiter.limit()`, fire-and-forget logging
- `.gitignore` is comprehensive and project-specific
- Ruff rule selection (E/W/F/I/B/UP) is sensible; B008 ignore for FastAPI `Depends` is correct

---

## Critical Issues (Must Fix)

### C1: `tests/` directory does not exist and no `__init__.py` is planned

The plan creates files in `adil-rag-api/tests/test_report_generator.py` and `adil-rag-api/tests/test_image_endpoint.py`, but the `tests/` directory does not currently exist. The plan never includes a step to `mkdir -p adil-rag-api/tests` or create `adil-rag-api/tests/__init__.py`.

Without `__init__.py`, pytest may fail to import modules from the parent directory, especially since the existing `test_backend.py` lives at the root of `adil-rag-api/` (not in a `tests/` subdirectory). The new tests under `tests/` will need either a `conftest.py` with `sys.path` manipulation or an `__init__.py` file.

**Fix:** Add a step before Task 3 Step 1:
```bash
mkdir -p adil-rag-api/tests
touch adil-rag-api/tests/__init__.py
```

Or add a `conftest.py` in `adil-rag-api/tests/` with:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
```

### C2: `log_conversation()` called with unexpected keyword arguments in the endpoint

In Task 5 Step 4, the `generate_report` endpoint calls:
```python
asyncio.create_task(log_conversation(
    endpoint="generate_report",
    query_text="",
    report_type=body.report_type.value,
    jurisdiction=body.jurisdiction,
))
```

But the actual `log_conversation()` signature in `conversation_log.py` (line 99) is:
```python
async def log_conversation(
    endpoint: str,
    query_text: str = "",
    conversation_history=None,
    has_urls: bool = False,
    has_images: bool = False,
    viability_requested: bool = False,
    report_submitted: bool = False,
    report_target=None,
    report_success=None,
    response_time_ms=None,
    model_used=None,
    token_count=None,
):
```

There are **no** `report_type` or `jurisdiction` parameters. This will raise a `TypeError` at runtime. The fire-and-forget `create_task` pattern means the error will be silently swallowed (logged but not returned to client), so the endpoint will still return 200 -- but metadata logging will be broken.

**Fix:** Change the log call to use existing parameters:
```python
asyncio.create_task(log_conversation(
    endpoint="generate_report",
    query_text=f"[report:{body.report_type.value}]",
))
```
Or extend `log_conversation()` to accept `report_type` and `jurisdiction` parameters.

### C3: `test_generate_report_requires_auth` will PASS even without the endpoint

In Task 5 Step 1, the test `test_generate_report_requires_auth` sends a POST without an API key and asserts `status_code in (401, 403)`. However, if `ADIL_API_KEY` is not set in the test environment, the `verify_api_key` function returns `"open"` (line 239-240 of app.py), meaning auth is **disabled**. In that case:
- If the endpoint doesn't exist yet, it returns 404 (test fails -- good)
- If the endpoint exists but no API key is configured, it returns 200 or 500 (test fails -- bad, it should test auth)

The test at Step 2 expects it to fail with 404 because the endpoint doesn't exist, which is fine for TDD. But once implemented, the test will only work correctly if `ADIL_API_KEY` is set in the test environment. The `api_key` fixture reads from `os.environ.get("ADIL_API_KEY", "test-key")` but nothing in the plan sets this environment variable.

**Fix:** The test should explicitly set `ADIL_API_KEY` to ensure auth is enforced:
```python
@pytest.fixture(autouse=True)
def _set_api_key(self, monkeypatch):
    monkeypatch.setenv("ADIL_API_KEY", "test-key-12345")
```

This pattern is likely used in `test_backend.py` already -- verify and replicate.

---

## Important Issues (Should Fix)

### I1: `generated_at` default_factory uses deprecated `datetime.utcnow()`

In Task 3 Step 3, the `GenerateReportResponse.generated_at` field uses:
```python
default_factory=lambda: __import__("datetime").datetime.utcnow().isoformat() + "Z",
```

`datetime.utcnow()` has been deprecated since Python 3.12. Since the project targets Python 3.11+, this works but will emit deprecation warnings on 3.12+.

**Fix:** Use `datetime.now(datetime.timezone.utc)`:
```python
default_factory=lambda: __import__("datetime").datetime.now(
    __import__("datetime").timezone.utc
).isoformat(),
```

Or more cleanly, import at the top of models.py and use:
```python
from datetime import datetime, timezone

# In the field:
default_factory=lambda: datetime.now(timezone.utc).isoformat(),
```

### I2: `_send_query` jurisdiction prepend not applied to analyze and image endpoints

Task 6 Step 2 says to use `query_with_context` instead of `user_text` in the payload's `query` field. However, looking at the frontend's `_send_query()` (lines 108-142), there are THREE different API call branches:
1. **Images** endpoint (`/api/v1/query/image`) -- uses `user_text or None` in the `query` field
2. **Analyze** endpoint (`/api/v1/analyze`) -- uses `user_text` in the `content` field (not `query`)
3. **Query** endpoint (`/api/v1/query`) -- uses `user_text` in the `query` field

The plan only mentions replacing `user_text` with `query_with_context` in the `query` field. But the analyze endpoint uses `content`, not `query`. The plan needs to clarify: should jurisdiction context be prepended to the `content` field for analyze requests too? And for image requests?

**Fix:** Make the plan explicit about which fields get jurisdiction context in each branch. Likely all three should get it.

### I3: `test_image_endpoint_rejects_invalid_mime` test name is misleading

In Task 7 Step 1, the test `test_image_endpoint_rejects_invalid_mime` actually sends a **valid** MIME type (`image/png`) with valid base64 data (`dGVzdA==`). The comment says "The endpoint validates base64 and MIME -- invalid base64 for a real image will fail at the Gemini level (500) or validation (400)." This doesn't test invalid MIME rejection at all.

**Fix:** Either rename to `test_image_endpoint_accepts_valid_mime_but_fake_image` or add a real invalid-MIME test:
```python
def test_image_endpoint_rejects_invalid_mime(self, client, api_key):
    resp = client.post(
        "/api/v1/query/image",
        json={"images": [{"mime_type": "image/svg+xml", "data": "dGVzdA=="}]},
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 400
```

### I4: `sys.path` manipulation inconsistency between test files

In Task 7 (`test_image_endpoint.py`), `sys.path` is set at module level (lines 933-934):
```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
```

But in Task 5 (`test_report_generator.py`), the `sys.path` insert is inside a **fixture** in `TestGenerateReportEndpoint` (line 622):
```python
@pytest.fixture
def client(self):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from app import app
    return TestClient(app)
```

The model tests in `TestReportModels` (Task 3) do `from models import ...` at the module level with NO `sys.path` manipulation. This will fail because the test file is in `tests/` and `models.py` is in the parent directory.

**Fix:** Add `sys.path.insert(0, ...)` at the module level of `test_report_generator.py`, or use a shared `conftest.py`.

### I5: The `test_generate_report_accepts_valid_request` test asserts 200 or 500

This test (Task 5, line 661-674) accepts both 200 and 500 as valid. While the comment explains this is because Gemini may not be configured in CI, a 500 response means the test passes even if the implementation is completely broken. The endpoint could raise any arbitrary exception and the test would pass.

**Fix:** Add a mock for `rag_service.query` to guarantee a 200 response path is tested:
```python
def test_generate_report_returns_report(self, client, api_key):
    with patch("app.rag_service") as mock_rag:
        mock_rag.query = AsyncMock(return_value=(
            "--- INCIDENT REPORT SUMMARY ---\nWHAT HAPPENED:\nTest\n--- END REPORT ---",
            [], mock_usage, mock_metadata,
        ))
        resp = client.post(...)
        assert resp.status_code == 200
        assert "INCIDENT REPORT" in resp.json()["report_text"]
```

---

## Suggestions (Nice to Have)

### S1: Consider adding `[tool.pytest.ini_options]` to `pyproject.toml`

Since the project is adding a root `pyproject.toml` for ruff/mypy, this is a good opportunity to centralize pytest config too:
```toml
[tool.pytest.ini_options]
testpaths = ["adil-rag-api", "adil-report-bridge"]
asyncio_mode = "auto"
```

### S2: The `parse_report_sections` regex may miss headings with numbers

The regex `r'^([A-Z][A-Z\s/()]+):'` requires headings to be ALL CAPS letters, spaces, slashes, and parens. This would miss headings like `"STEP 1"` or `"ACAS EC"`. The solicitor pack prompt includes "ACAS EC must be started by" as inline content, not a heading, so this is fine for now -- but worth noting for future prompt changes.

### S3: `.gitignore` could include `*.log` files

Railway and local dev may generate log files. Consider adding `*.log` to the gitignore.

### S4: Task 1 Step 3 uses `git add -A`

The plan says "Run: `git add -A && git status`" and then "If `.env` appears, abort and fix `.gitignore`." This is fine as a safety check, but it's better practice to use `git add .` (which respects `.gitignore`) and then review. `git add -A` also stages deletions, which is usually what you want for an initial commit but is worth noting.

### S5: `report_generator.py` could benefit from a `__all__` export list

For clarity about the public API surface:
```python
__all__ = ["get_report_prompt", "parse_report_sections"]
```

### S6: Jurisdiction selector doesn't have a "skip" option

The `start_chat()` replacement in Task 6 shows 3 jurisdiction buttons but no way to skip or say "I don't know." If a user doesn't click a button and just types a message, `jurisdiction` will remain `None`. The plan handles this gracefully (`query_with_context = user_text` when jurisdiction is None), but it's a UX consideration -- users may not realise they should click a button first.

**Suggestion:** Add a fourth action:
```python
cl.Action(
    name="select_jurisdiction",
    payload={"jurisdiction": None},
    label="I'm not sure / Outside UK",
),
```

---

## File Path Verification

| Plan Reference | Actual Path | Status |
|---|---|---|
| `adil-rag-api/models.py` (446 lines) | Exists, 446 lines | Correct |
| `adil-rag-api/app.py` (1139 lines) | Exists, 1139 lines | Correct |
| `adil-frontend/app.py` (620 lines) | Exists | Correct |
| `adil-rag-api/rag_service.py` | Exists | Correct |
| `adil-rag-api/conversation_log.py` | Exists | Correct |
| `adil-rag-api/test_backend.py` | Exists (root level, not in tests/) | Correct |
| `adil-rag-api/requirements-dev.txt` | Exists (3 deps) | Correct |
| `adil-rag-api/tests/` | Does NOT exist | **Missing step** |
| `pyproject.toml` (root) | Does NOT exist | Correct (to be created) |
| `.gitignore` (root) | To be created | Correct |

---

## Import Verification

| Import in Plan | Actual Source | Status |
|---|---|---|
| `from models import ReportType, GenerateReportRequest, ...` | To be added to models.py | OK |
| `from report_generator import get_report_prompt, parse_report_sections` | To be created | OK |
| `from rag_service import RAGService` | Exists in app.py line 54 | OK |
| `rag_service.query(query_text=..., max_sources=0, ...)` | Signature: `query(self, query_text, max_sources=10, include_viability=False, conversation_history=None)` | OK -- `max_sources=0` is valid |
| Return value: `answer, _, usage, metadata` | Returns `Tuple[str, List[Source], TokenUsage, QueryMetadata]` | OK |

---

## Summary

The plan is well-structured and follows good engineering practices (TDD, incremental commits, infrastructure-first ordering). The three critical issues should be resolved before implementation begins:

1. **Create `tests/` directory with `__init__.py` or `conftest.py`** -- without this, all new tests will fail on import
2. **Fix `log_conversation()` kwargs** -- the plan passes parameters that don't exist in the function signature
3. **Ensure test auth is deterministic** -- tests relying on auth behavior need `ADIL_API_KEY` set in the environment

The five important issues should be addressed during implementation but won't block progress. The suggestions are quality-of-life improvements that can be deferred.
