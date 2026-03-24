# Design Review: adil-report-bridge

**Reviewer:** Senior Code Reviewer (Claude Opus 4.6)
**Date:** 2026-03-22
**Spec:** `E:\dev\mcbx\adil\docs\superpowers\specs\2026-03-22-report-bridge-design.md`

---

## Overall Assessment

The spec is well-structured, clearly written, and demonstrates strong architectural thinking. The separation of concerns (bridge as isolated service), the target-agnostic config pattern, and the graceful fallback strategy are all sound decisions. The PII pass-through model is the right call given the project's constraints.

The issues below are ordered by severity.

---

## Critical Issues (Must Fix)

### C1. No authentication between RAG API and Bridge (Line 329)

The spec says the bridge has "no public domain" and relies on Railway private networking for security. This is necessary but not sufficient. Any other Railway service in the same project (or environment) can reach the bridge. There is no shared secret, mTLS, or API key between the two services.

**Recommendation:** Add a `BRIDGE_API_KEY` environment variable shared between RAG API and bridge. The bridge should reject requests missing a valid key. This mirrors the existing `ADIL_API_KEY` pattern in the RAG API (`adil-rag-api/app.py`, line 164).

### C2. Base64 screenshot in JSON response is a bandwidth and memory risk (Line 95)

A full-page confirmation screenshot encoded as base64 in a JSON response can easily be 1-5MB. This payload travels: Bridge -> RAG API -> Frontend -> User's browser. For mobile/Telegram users on slow connections, this is problematic. It also means the entire screenshot lives in Python memory across three services simultaneously.

**Recommendation:** Either (a) compress/resize the screenshot to a thumbnail (max 200KB) before base64 encoding, or (b) upload the screenshot to a temporary signed URL (e.g., Railway volume, S3, or Cloudflare R2) and return only the URL. Option (a) is simpler for MVP. Specify a maximum size in the spec.

### C3. PII in memory is still PII in crash dumps and swap (Line 53, 331)

The spec correctly avoids persisting PII to disk or database. However, Python process crash dumps, Railway deploy logs, and OS swap files can still capture in-memory PII. The spec should address:

- Explicitly zeroing/overwriting PII variables after use (Python makes this hard but not impossible with `ctypes` or mutable bytearrays)
- Ensuring Railway's container restart policy does not capture core dumps
- Setting `PYTHONDONTWRITEBYTECODE=1` and disabling core dumps in the Dockerfile

**Recommendation:** Add a "PII Lifecycle" section specifying: (1) PII arrives in request, (2) passed to browser-use, (3) explicitly dereferenced after submission, (4) garbage collected. Acknowledge the limitations.

---

## Important Issues (Should Fix)

### I1. No request timeout specified for the RAG API -> Bridge call (Line 222)

The spec says "Timeout (>60s)" in the failure table (line 345) but does not specify the timeout for the RAG API's `httpx` call to the bridge. The existing frontend already uses `timeout=120.0` for RAG API calls (`adil-frontend/app.py`, line 108). If the bridge takes 60s and the RAG API has its own processing overhead, the frontend's 120s timeout could be exceeded.

**Recommendation:** Specify explicit timeouts: Bridge browser automation = 60s, RAG API -> Bridge httpx call = 70s (60 + 10s buffer), Frontend -> RAG API = 120s (already set). Document this timeout chain in the spec.

### I2. API contract inconsistency: `/submit` vs `/api/v1/submit-report` field shapes (Lines 67-87 vs 196-217)

The RAG API public endpoint uses a structured nested format (`reporter.first_name`, `incident.details`), but the bridge uses a flat format (`data.first_name`, `data.incident_details`). This means the RAG API must transform the nested structure into the flat one before calling the bridge. This transformation logic is not specified anywhere.

**Recommendation:** Either (a) document the field mapping/transformation logic explicitly, or (b) make the bridge accept the same nested structure as the public API to eliminate the mapping layer.

### I3. Health endpoint inconsistency: `/health` vs `/health/targets` (Lines 116 and 351)

Line 116 shows `GET /health` returning target reachability. Line 351 references `GET /health/targets` for periodic target checks. These appear to be the same thing described with two different paths.

**Recommendation:** Pick one path. Suggest `GET /health` for basic liveness (fast, no external calls) and `GET /targets` (already defined at line 129) for target reachability. Do not combine liveness probes with external dependency checks -- Railway health probes should be fast and deterministic.

### I4. No concurrency controls on browser sessions (Lines 29-33)

Browser-use + Playwright consumes significant memory per session (~150-300MB for Chromium). If two submit requests arrive simultaneously, two Chromium instances launch. On Railway's typical 512MB-2GB containers, this could OOM the service.

**Recommendation:** Add a concurrency limit (semaphore) to the bridge -- e.g., `asyncio.Semaphore(1)` for MVP, with a 429 response when the semaphore is full. Specify the expected Railway container memory (recommend >= 2GB). Document that submissions are serialized in MVP.

### I5. No idempotency or duplicate submission protection (Line 59)

If the RAG API retries after a timeout, or the user double-clicks, the same report could be submitted twice to police.uk. Since there is no database, traditional idempotency keys are not available.

**Recommendation:** For MVP, the simplest approach is: (a) the RAG API should never retry (already implied by "no retry queue"), and (b) the frontend should disable the submit button after first click and show a spinner. Document both explicitly. Post-MVP, consider a short-lived in-memory dedup cache keyed on hash(reporter_email + incident_details).

### I6. `conversation_history` field in RAG API submit request is unused (Line 215)

The public endpoint accepts `conversation_history` but the spec never explains what it is used for. The bridge does not receive it. The only stated use is "if bridge fails, use Gemini to generate a Tier 1 incident summary from conversation history" (line 224), but the fallback generation logic is not specified.

**Recommendation:** Clarify that conversation_history is used exclusively for fallback report generation when the bridge fails. Specify that it is NOT forwarded to the bridge.

---

## Suggestions (Nice to Have)

### S1. Specify browser-use agent model and version explicitly

The spec says "Gemini Flash" but does not pin a model version. The existing RAG API uses `gemini-2.5-flash` (`adil-rag-api/models.py`, line 237). The browser-use library may need specific model compatibility.

**Recommendation:** Pin to `gemini-2.5-flash` or whichever version browser-use supports. Add this to the target config or as a top-level setting.

### S2. Add a `dry_run` mode for testing

Testing against the real police.uk form risks creating false reports. The spec mentions `tests/test_targets.py` (line 368) but only for config validation.

**Recommendation:** Add a `dry_run: true` parameter to the `/submit` endpoint that runs the full browser automation but stops before clicking the final submit button. Capture a screenshot of the review page as proof the form was filled correctly.

### S3. Specify logging standards explicitly

The spec says "PII excluded from logs" (line 331) but does not specify what IS logged. The existing RAG API uses Python `logging` with a standard format (`adil-rag-api/app.py`, line 59-62).

**Recommendation:** Specify a log format and what fields are logged per submission: `{timestamp, target, success, reference_number, duration_ms, error_type}`. Add a structured logging library (e.g., `structlog`) to ensure PII cannot accidentally leak into log messages.

### S4. Consider adding a `role` field validation

The `role` field appears in both optional_fields (target config, line 173) and required in the incident section of the RAG API request (line 212). The spec should clarify whether `role` is required or optional, and what the valid values are (`victim`, `witness`, `third_party`).

### S5. Dockerfile should run as non-root

The Dockerfile sketch (lines 297-318) does not add a non-root user. Playwright/Chromium running as root in a container is a security concern, especially when navigating to external websites.

**Recommendation:** Add `RUN useradd -m appuser` and `USER appuser` before the CMD.

### S6. Evidence file uploads are not addressed

The police.uk form (Step 5, line 415) supports file uploads, but the bridge API only accepts `evidence_urls` (strings). If a user has local evidence files (photos, documents), there is no mechanism to upload them through the bridge.

**Recommendation:** Acknowledge this as a known MVP limitation or add a `evidence_files` field accepting base64-encoded attachments. Given the base64 screenshot concern (C2), this needs careful size management.

---

## What Was Done Well

- **Graceful degradation**: The fallback-to-manual-report pattern is excellent. Users always get something useful even when automation fails.
- **Target-agnostic design**: The configuration-driven approach for adding new portals is the right abstraction level. The natural language instructions to the AI agent are pragmatic.
- **Deployment isolation**: Separating the bridge from the RAG API is the correct call. Playwright/Chromium is heavy and crash-prone; it should not share a process with the query API.
- **Explicit ToS assessment**: Documenting the robots.txt and ToS analysis (lines 419-424) shows due diligence.
- **API design philosophy**: Returning 200 with `success: false` for external failures vs 4xx/5xx for bridge failures (line 113) is a thoughtful distinction.

---

## Summary

| Category | Count |
|----------|-------|
| Critical (must fix) | 3 |
| Important (should fix) | 6 |
| Suggestions (nice to have) | 6 |

The spec is strong enough to begin implementation after addressing the three critical items. The most important fix is C1 (bridge authentication) -- without it, the PII security model has a gap. C2 (screenshot size) and C3 (PII in memory) should be addressed before production deployment.
