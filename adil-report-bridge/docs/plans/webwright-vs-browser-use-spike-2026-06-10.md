# Webwright vs. browser-use — driver spike

**Date:** 2026-06-10
**Owner:** AskAdil platform
**Status:** Draft for review
**Scope:** Choose the browser-automation driver for `adil-report-bridge` going forward.

---

## 1. Context

`adil-report-bridge` is an internal FastAPI microservice that files hate-crime
and discrimination incident reports to external UK reporting portals on behalf
of AskAdil users. It exposes `POST /submit { target, data }` behind an
`X-Bridge-Key` header and dispatches each submission via one of two adapter
types:

- **browser** — drives a real Chromium session through the portal's web form.
- **email** — sends a structured email to the portal address via SendGrid
  (used for portals that publish no machine-fileable web form).

`BRIDGE_DRY_RUN=true` is set in production today, so the agent walks the
entire form but never clicks the final Submit button. No real reports have
landed in any portal yet from production.

### Portal targets

`targets.py` defines **10** portals (the CLAUDE.md says "11" — that is stale;
the actual dict has 10 entries). Of those, **7 are browser targets** and
**3 are email targets**:

| ID | Adapter | URL | Notes |
|---|---|---|---|
| `police-uk` | browser | police.uk hate-crime form | Multi-step gov.uk form. National. ToS unverified — flag as open question. |
| `tell-mama` | browser | tellmamauk.org/submit-a-report-to-us | Single-page form. May require account/login in future; today no auth, but a known pain point in the brief. |
| `police-scotland` | browser | scotland.police.uk secureform C3 | Multi-page secure form, likely server-side validation; bot-checking unknown. |
| `iru` | browser | theiru.org.uk/report-islamophobia | NGO portal, single page. |
| `islamophobia-uk` | browser | islamophobiauk.co.uk | NGO portal, single page. |
| `british-muslim-trust` | browser | britishmuslimtrust.co.uk/report-hate | NGO portal, single page. |
| `muslim-safety-net` | browser | muslimsafetynet.org.uk/report | **Has CAPTCHA** at the bottom (explicit in instructions). |
| `prevent-watch` | email | preventwatch.org/get-support | Email-only; not in scope for this spike. |
| `eass` | email | equalityadvisoryservice.com | Email-only; not in scope. |
| `stop-hate-uk` | email | stophateuk.org/report-hate-crime | Email-only; not in scope. |

So the **browser-driver decision affects 7 portals** today. The 3 email
targets ride a separate SendGrid adapter (`email_adapter.py`) and are
untouched by this spike.

---

## 2. Current state

### What the bridge uses today

`browser_agent.py` imports:

```python
from browser_use import Agent, Browser, ChatAnthropic
```

So the **current driver is `browser-use` >= 0.5.0** wrapping Playwright
Chromium, with `ChatAnthropic` (Claude Sonnet) as the reasoning model.
Migrated off Gemini Flash on 2026-06-04 as part of the AskAdil one-vendor
consolidation. Each portal target has free-text `instructions` and an
`required_fields` / `optional_fields` list; the agent reads the instructions
plus a flat `DATA TO FILL IN THE FORM:` block and figures out selectors at
runtime by reading the rendered DOM + (for `browser-use`) screenshots.

### Submission flow

1. Client calls `POST /submit { target, data }` with `X-Bridge-Key`.
2. `app.py` validates `data` against `target.required_fields`.
3. Email targets → `email_adapter.send_email_report`.
4. Browser targets → `browser_agent.submit_report`:
   - Acquires `asyncio.Semaphore(1)` (30s timeout → 503).
   - Builds task prompt from `instructions + data`.
   - Runs `Agent(...).run(max_steps=50)` with a **60-second wall-clock
     timeout** on the entire run.
   - Captures one screenshot of the final page via `page.screenshot(full_page=False)`.
   - Returns `{ success, reference_number, confirmation_screenshot, confirmation_text, dry_run }`.

### Known pain points (from code + brief)

- **Single-screenshot evidence.** Only the final page is captured. If
  submission fails partway, the operator gets a description from the agent's
  `final_result` text but no per-step screenshot trail. Bad for legal-evidence
  audit.
- **60-second hard timeout** for a multi-page form (e.g. police-uk,
  police-scotland) is tight; the agent has burned ~30s of that on selector
  exploration on slow portals.
- **No cookie / session persistence.** Each submission spins a fresh
  Chromium. Fine today (no logins yet) but Tell MAMA may move behind an
  account; we'd have nowhere to put cached sessions.
- **CAPTCHA on muslim-safety-net** is currently delegated to "the agent
  figures it out" — `browser-use` has no built-in solver. In dry-run mode
  this is fine; in real mode it will fail silently and we'll see
  `success=False` with an opaque LLM result string.
- **Failure-mode visibility.** The operator sees `confirmation_text` (last
  500 chars of agent output) and one screenshot. No DOM dump, no step trace,
  no network HAR.
- **LLM cost.** Every form fill is paid Claude Sonnet inference at runtime.
  No per-portal cached "recipe" — we re-derive the selector strategy each call.
- **Bot detection.** Current setup is vanilla Chromium with no fingerprint
  shaping. None of the portals have explicitly blocked us *yet* (we are in
  dry-run), but police.uk and police-scotland are likely to have WAF / bot
  rules we'd discover only in production.

---

## 3. Comparison matrix

`browser-use (current)` is the column for what's in `browser_agent.py` today.
The two candidates are **Webwright** (the skill at
`C:\Users\muaza\.claude\skills\webwright\SKILL.md`, a code-as-action
Playwright pattern) and **browser-use** (continued; the option of going
deeper into the same framework rather than swapping).

| Capability | Webwright | browser-use | Current (browser-use) |
|---|---|---|---|
| **Stealth / anti-bot (CDP fingerprint)** | None built-in. Launches Firefox headless via plain Playwright. Anti-bot is whatever you hand-code (`playwright-stealth`, residential proxy, etc.). | Ships with CDP-level fingerprint shaping and anti-detection patches; supports residential-proxy URLs natively. | None. Vanilla Chromium, no proxy. **Gap vs. either candidate.** |
| **CAPTCHA handling** | None built-in. You'd plug in 2Captcha / Anti-Captcha manually as a Playwright step. Vision verification possible because Claude reads the PNG. | No built-in solver, but vision+DOM hybrid lets the LLM at least *see* the CAPTCHA. Has community recipes for hCaptcha / reCaptcha via solver APIs. | None. Will silently fail muslim-safety-net in real mode. |
| **Cookie / session persistence (Tell MAMA login)** | DIY — write cookies to disk in the workspace, reload next run. Fits the workspace contract naturally (`outputs/<task_id>/cookies.json`). | Built-in `BrowserContext` with `storage_state` + recovery. One-liner. Supports multi-portal session pool. | Not used. Each call fresh. |
| **Form-fill reliability under DOM volatility** | **Lower auto-adaptation**: the script is fixed Playwright code authored once. When the portal changes selectors, the script breaks until a human (or the skill re-run) re-authors it. Stable runs, brittle to portal redesigns. | **Higher auto-adaptation**: LLM re-derives selectors each call from current DOM + screenshot. Survives most portal redesigns. Pays for it in tokens and latency. | Same as browser-use column. Already adapts. |
| **Screenshot + structured audit-trail (legal evidence)** | **Strong out of the box.** Workspace contract requires `final_runs/run_<id>/screenshots/final_execution_<step>_<action>.png` + `final_script_log.txt` with a `step <n> action: ...` line per constraint. This is exactly the audit trail legal evidence wants. | One final screenshot today; the framework supports more but you wire it. History object has step-by-step actions, but not as a labelled per-CP screenshot folder. | Single final-page JPEG (compressed to 500KB), plus 500-char text. Weak. |
| **Vision-input support** | Yes via Claude reading PNGs natively. Verification only — not in the action loop. | Yes — vision is in the action loop (LLM sees screenshots between steps). Better for visual CAPTCHAs and visual-only validation states. | Yes (browser-use uses it). |
| **Dev velocity for adding the 12th/13th portal** | **Slow per portal**: each new portal is a fresh `WORKSPACE_DIR`, explore phase, authored `final_script.py`. Engineering hours per portal, but result is durable + fast. | **Fast per portal**: add a dict entry to `targets.py` with `instructions` + field list. Already proven — 7 portals stood up this way. Hours not days. | Same as browser-use. This is the framework's biggest win today. |
| **Cost per submission (LLM tokens + infra)** | **Near-zero per submission once authored.** `final_script.py` runs Playwright directly; no LLM in the hot path. LLM cost is one-time authoring + maintenance. Infra: a Playwright worker (already have one). | **~$0.02–0.10 per submission** (Claude Sonnet @ ~10-30k tokens per multi-page form). Linear in volume. Plus Chromium memory pressure (already at semaphore=1). | Same as browser-use column. At low volume (dry-run only) cost is negligible; at hate-crime-incident scale (10s–100s/day) it becomes real. |
| **Failure-mode visibility (what the operator sees)** | Per-step screenshot + per-step log line + a final datum. If step 7 of 12 breaks, you can see the exact PNG and the action log says what selector failed. **Excellent.** | Agent history object + one final screenshot + LLM `final_result` describing what it thinks went wrong. Often vague ("could not find the submit button"). Adequate, not great. | One screenshot + 500-char string. **Poor.** Operator can't diagnose mid-flow failures. |

### Reading the matrix

There are two genuine axes the candidates split on:

1. **Velocity vs. evidence.** browser-use is dramatically faster to add a
   portal but produces weaker audit trails. Webwright is slower to author
   but produces a legally-defensible per-step record by construction.
2. **Cost shape.** browser-use is variable cost (tokens per submission).
   Webwright is fixed cost (engineering hours, then near-zero per run).
   The breakeven depends on submission volume.

It is **not** a wash — these are real trade-offs — but neither is
strictly dominant.

---

## 4. Recommendation

**Stay on `browser-use` as the live driver, but adopt the Webwright workspace
contract for two things: (a) authoring the per-portal "happy path" reference
script and (b) producing the audit-trail folder layout.**

Concretely:

- Keep `browser_agent.py`'s `browser-use` Agent as the **runtime** driver
  for the 7 browser portals. Don't rip it out — it's working in dry-run,
  the team understands it, and the per-portal dict-entry velocity is the
  framework's biggest win.
- For each browser portal, run a one-off Webwright session against the
  portal's dry-run form and **commit the resulting `final_script.py` +
  screenshot trail** into `adil-report-bridge/portal_scripts/<target_id>/`.
  This gives us:
  - A **deterministic fallback** path per portal that doesn't need an LLM
    at runtime, usable when the LLM agent gets stuck or when we want to
    drop submission cost to zero.
  - A **reference for the operator** — when `browser-use` reports a
    failure, we have the canonical screenshot-trail of what the form
    *should* look like at each step, to diagnose what changed.
- Bring the **audit-trail layout** (`final_runs/run_<id>/screenshots/...`
  + step log) into `browser_agent.py` even when the runtime is still
  `browser-use`: per submission, write each `browser-use` step + a PNG to
  a per-request folder, and include that folder reference in the
  `SubmitResponse`. This is the single biggest evidence-quality win and
  doesn't depend on swapping drivers.
- Add **CDP fingerprint shaping + cookie persistence** (browser-use supports
  both natively) before flipping `BRIDGE_DRY_RUN=false`. This is non-optional
  for police.uk / police-scotland.

**Why not pure Webwright?** Because we'd lose the per-portal velocity that's
already proven across 7 targets, and police.uk / police-scotland multi-page
forms with server-side validation are exactly the case where LLM
auto-adaptation pays for itself.

**Why not pure browser-use as-is?** Because the audit trail is genuinely
not good enough for an evidence-grade legal-reporting pipeline, and we are
about to flip dry-run off.

### Trade-offs accepted

- Authoring + maintaining the Webwright reference scripts is real
  engineering cost (~0.5–1 day per portal initially, ~0.25 day per portal
  per portal-redesign). Budget for this.
- We carry two patterns (LLM agent + deterministic script) instead of one.
  The cognitive overhead is small because the workspace contract is
  documented in `~/.claude/skills/webwright/SKILL.md`.
- If `browser-use` upstream lands a richer audit-trail story before we do,
  we should revisit and possibly drop the Webwright workspace for that part.

---

## 5. Spike plan

Goal: prove the recommendation against 3 portals before committing to
roll-out across all 7.

Acceptance: **9 dry-run submissions (3 portals × 3 runs each)** complete
end-to-end via the dual-mode pipeline, each producing a
`final_runs/run_<id>/` folder with one PNG per critical point (≥4 PNGs per
run) plus a structured `final_script_log.txt`. At least 1 of the 3 portals
is multi-page (police-uk or police-scotland). Failure-mode visibility
verified by deliberately breaking a selector and confirming the operator
can identify the failing step from the screenshot folder alone.

1. **(0.5d)** Pick the 3 spike portals: `tell-mama` (single page,
   easiest), `muslim-safety-net` (CAPTCHA, hardest single-page),
   `police-uk` (multi-page, gov form). Confirm portal ToS / dry-run
   acceptability before any live calls — see open questions.
2. **(0.5d)** Add `portal_scripts/` directory and a tiny loader in
   `browser_agent.py` that checks `portal_scripts/<target_id>/final_script.py`
   exists. If yes, runtime can use it as a **deterministic-mode** flag
   (`USE_SCRIPTED_PORTAL=true`); else fall back to browser-use Agent.
3. **(1d per portal × 3 = 3d)** Run the Webwright workflow (plan →
   explore → final → self-verify) against each spike portal's *dry-run*
   form, with synthetic user data. Commit `final_script.py` + the
   reference `final_runs/run_1/screenshots/` to the repo as the canonical
   per-portal evidence template.
4. **(0.5d)** Wire per-submission audit-trail layout into the live
   `browser-use` path: write each step's PNG to
   `/tmp/submissions/<request_id>/screenshots/` and a step log; return the
   request id in `SubmitResponse.audit_trail_id`. Upload trail to S3 (or
   the existing screenshot store) on completion.
5. **(0.25d)** Add `BrowserContext storage_state` cookie persistence per
   portal so Tell MAMA login (when it lands) has a place to live.
6. **(0.25d)** Add `playwright-stealth` + a residential proxy env var
   (`BRIDGE_PROXY_URL`) — disabled by default. Smoke-test against
   police.uk and confirm no obvious block.
7. **(0.5d)** Break a selector on the `tell-mama` deterministic script
   deliberately, run a submission, and verify the operator can identify
   the failed step from the screenshot folder alone within 60 seconds.
   Repeat for the `browser-use` runtime path to confirm the new audit
   trail is also legible.
8. **(0.25d)** Document the dual-mode pattern in `CLAUDE.md`: when to
   author a deterministic script, when to leave a portal on LLM-only.

**Total spike effort: ~5.75 days.** Conservatively budget 7 days to
accommodate selector exploration friction on police.uk.

---

## 6. Open questions

These are blockers for the spike — flag, don't decide.

- **Does police.uk's ToS forbid programmatic submission?** The form is a
  national gov.uk endpoint. Even with the user's explicit consent (we are
  filing on their behalf, not impersonating), we need a clear policy line.
  Spike step 1 cannot proceed against police.uk live until this is
  answered. Tell MAMA + muslim-safety-net are NGO portals and likely
  permissive but should still be confirmed.
- **Will Tell MAMA require login in the next 6 months?** The brief flagged
  this. If yes, the cookie-persistence work in spike step 5 needs a real
  account; if no, it can stay synthetic.
- **What's the legal-evidence acceptance bar for the audit trail?**
  Per-step PNGs + a step log is what Webwright produces — but does the
  user-facing AskAdil legal team want anything more (e.g. signed
  timestamps, content hashes, network HAR)? If yes, factor into spike
  step 4 before locking the layout.
- **Submission volume forecast.** The breakeven between fixed-cost
  Webwright scripts and variable-cost browser-use depends on this. If
  we're at 10s of submissions per day, browser-use cost stays trivial
  and the deterministic scripts are evidence-only. If we're at 1000s
  per day post-launch, the cost calc flips and deterministic scripts
  earn their keep on cost alone. Need a number before doing the full
  7-portal roll-out beyond the spike.
- **Does the existing screenshot upload store (where compressed JPEGs go
  today) scale to per-step folders?** Multiply current storage by ~8x
  per submission. Confirm with infra before step 4.
- **Captcha solver provider choice.** 2Captcha vs. Anti-Captcha vs.
  CapSolver — not a hard blocker for the spike (muslim-safety-net dry-run
  can be solved manually), but needs a decision before real submissions.

---

*End of doc.*
