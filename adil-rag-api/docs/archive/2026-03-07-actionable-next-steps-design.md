# Actionable Next Steps — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Every post-intake response includes a "What You Can Do Now" section with 3-5 relevant organizations, helplines, and reporting links chosen by the AI based on the user's jurisdiction and topic.

**Architecture:** Single-file change to the system prompt in `rag_service.py`. The AI selects resources from a directory embedded in the prompt. No API/model/frontend changes needed.

**Tech Stack:** Python, Gemini system prompt, pytest

---

### Task 1: Write test verifying resource directory exists in system prompt

**Files:**
- Modify: `test_backend.py` (append new test class at end of file)

**Step 1: Write the failing test**

Add this test class at the end of `test_backend.py`:

```python
# ---------------------------------------------------------------------------
# 9. System Prompt — Actionable Next Steps Resource Directory
# ---------------------------------------------------------------------------
from rag_service import SYSTEM_INSTRUCTION


class TestSystemPromptResourceDirectory:
    """Verify the system prompt contains the actionable next steps resource directory."""

    def test_contains_resource_directory_section(self):
        assert "ACTIONABLE NEXT STEPS" in SYSTEM_INSTRUCTION or "What You Can Do Now" in SYSTEM_INSTRUCTION

    def test_contains_tell_mama(self):
        assert "tellmamauk.org" in SYSTEM_INSTRUCTION

    def test_contains_iru(self):
        assert "theiru.org.uk" in SYSTEM_INSTRUCTION

    def test_contains_true_vision(self):
        assert "report-it.org.uk" in SYSTEM_INSTRUCTION

    def test_contains_stop_hate_uk(self):
        assert "stophateuk.org" in SYSTEM_INSTRUCTION

    def test_contains_eass(self):
        assert "equalityadvisoryservice.com" in SYSTEM_INSTRUCTION

    def test_contains_citizens_advice(self):
        assert "citizensadvice.org.uk" in SYSTEM_INSTRUCTION

    def test_contains_acas(self):
        assert "acas.org.uk" in SYSTEM_INSTRUCTION

    def test_contains_law_society(self):
        assert "solicitors.lawsociety.org.uk" in SYSTEM_INSTRUCTION

    def test_contains_legal_aid(self):
        assert "find-legal-advice.justice.gov.uk" in SYSTEM_INSTRUCTION

    def test_contains_employment_tribunal(self):
        assert "gov.uk/employment-tribunals" in SYSTEM_INSTRUCTION

    def test_contains_scotland_resources(self):
        assert "lawscot.org.uk" in SYSTEM_INSTRUCTION
        assert "slab.org.uk" in SYSTEM_INSTRUCTION

    def test_contains_ni_resources(self):
        assert "equalityni.org" in SYSTEM_INSTRUCTION
        assert "lawsoc-ni.org" in SYSTEM_INSTRUCTION

    def test_contains_selection_guidance(self):
        """AI must be told to select 3-5 relevant resources per response."""
        assert "3-5" in SYSTEM_INSTRUCTION or "three to five" in SYSTEM_INSTRUCTION
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest test_backend.py::TestSystemPromptResourceDirectory -v`
Expected: Multiple FAILs (resource URLs not yet in system prompt)

**Step 3: Commit**

```bash
git add test_backend.py
git commit -m "test: add tests for actionable next steps resource directory in system prompt"
```

---

### Task 2: Add resource directory and section 10 to system prompt

**Files:**
- Modify: `rag_service.py:384-412` (insert new section 10 before Response Format, update Response Format)

**Step 1: Insert the resource directory and instructions after section 9 (line 392) and before Response Format (line 394)**

In `rag_service.py`, find this text:

```
These must be specific to the user's situation and help them explore their rights further.
During the intake phase, these should help the user provide the information you need.

## Response Format
```

Replace with:

```
These must be specific to the user's situation and help them explore their rights further.
During the intake phase, these should help the user provide the information you need.

### 10. ACTIONABLE NEXT STEPS (MANDATORY in post-intake responses)
After every post-intake response (i.e. after the user has answered your clarifying questions), include a **"What You Can Do Now"** section with 3-5 concrete resources selected from the directory below. Choose the MOST RELEVANT resources based on the user's jurisdiction, topic, and severity.

**Selection rules:**
- **Hate crime / online hate:** Include Tell MAMA + True Vision or Police + Stop Hate UK
- **Workplace discrimination:** Include ACAS + Employment Tribunal + Law Society
- **General discrimination / services:** Include EASS + Citizens Advice + Law Society
- **Scotland:** Replace England/Wales resources with Scottish equivalents where available
- **Northern Ireland:** Replace with NI equivalents (Equality Commission NI, Law Society NI, Advice NI)
- **High severity / urgent:** Lead with Police (999) and solicitor referral
- **Always include at least one solicitor-finding resource** (Law Society, Legal Aid, or jurisdiction equivalent)

**Format each resource as a markdown link with the phone number or key detail:**
- **[Tell MAMA](https://tellmamauk.org/submit-a-report-to-us/)** — Report anti-Muslim hate incidents online
- **[IRU](https://theiru.org.uk/report-islamophobia/)** — Islamophobia Response Unit, phone 020 3904 6555
- etc.

#### Resource Directory

**Report Islamophobia / Anti-Muslim Hate:**
- **Tell MAMA** — tellmamauk.org/submit-a-report-to-us/ — Report anti-Muslim hate incidents (online form)
- **IRU (Islamophobia Response Unit)** — theiru.org.uk/report-islamophobia/ — Phone: 020 3904 6555, Email: info@theiru.org.uk
- **MEND (Muslim Engagement & Development)** — mend.org.uk — Advocacy and policy campaigns

**Report Hate Crime (General):**
- **True Vision** — report-it.org.uk — Online hate crime reporting (forwarded to local police)
- **Stop Hate UK** — stophateuk.org — 24/7 helpline: 0800 138 1625, text: 07717 989 025
- **Police** — 101 (non-emergency), 999 (emergency, immediate danger)

**Legal Advice & Discrimination Support:**
- **EASS (Equality Advisory Support Service)** — equalityadvisoryservice.com — Phone: 0808 800 0082 (Mon-Fri 9am-7pm, Sat 10am-2pm)
- **Citizens Advice** — citizensadvice.org.uk — Free legal guidance, local bureau network
- **ACAS** — acas.org.uk — Workplace disputes, early conciliation (mandatory before ET claim)
- **Law Society — Find a Solicitor** — solicitors.lawsociety.org.uk — Search for discrimination/employment solicitors
- **Legal Aid Finder** — find-legal-advice.justice.gov.uk — Check eligibility for means-tested legal aid

**Employment Tribunal:**
- **GOV.UK ET1** — gov.uk/employment-tribunals/make-a-claim — Submit employment tribunal claim online

**Regulatory:**
- **EHRC** — equalityhumanrights.com — Equality & Human Rights Commission (strategic enforcement)

**Scotland-Specific:**
- **Police Scotland Hate Crime** — scotland.police.uk/contact-us/reporting-hate-crime/ — Online reporting
- **Law Society of Scotland** — lawscot.org.uk — Find a Scottish solicitor
- **Scottish Legal Aid Board** — slab.org.uk — Legal aid in Scotland

**Northern Ireland-Specific:**
- **Equality Commission NI** — equalityni.org — NI discrimination complaints
- **Law Society NI** — lawsoc-ni.org — Find a NI solicitor
- **Advice NI** — adviceni.net — Free advice services across Northern Ireland

## Response Format
```

**Step 2: Update the Response Format for subsequent messages to include the new section**

Find this block in the Response Format:

```
### Subsequent messages (after intake):
1. **Direct answer** to the question
2. **Legal basis** with statute/case citations
3. **Practical next steps** (educate first)
4. **When to seek legal advice** (if applicable)
5. **Suggested next steps** (3 follow-up questions)
```

Replace with:

```
### Subsequent messages (after intake):
1. **Direct answer** to the question
2. **Legal basis** with statute/case citations
3. **Practical next steps** (educate first)
4. **When to seek legal advice** (if applicable)
5. **What You Can Do Now** (3-5 actionable resources from the directory, selected by topic/jurisdiction)
6. **Suggested next steps** (3 follow-up questions)
```

**Step 3: Run tests to verify they pass**

Run: `python -m pytest test_backend.py::TestSystemPromptResourceDirectory -v`
Expected: All 14 tests PASS

**Step 4: Run full test suite to check for regressions**

Run: `python -m pytest test_backend.py -v`
Expected: All 71 tests PASS (57 existing + 14 new)

**Step 5: Commit**

```bash
git add rag_service.py
git commit -m "feat: add actionable next steps resource directory to system prompt

Every post-intake response now includes a 'What You Can Do Now' section
with 3-5 relevant organizations selected by topic and jurisdiction.
Includes Tell MAMA, IRU, True Vision, Stop Hate UK, EASS, ACAS,
Citizens Advice, Law Society, Employment Tribunal, plus Scotland
and Northern Ireland equivalents."
```

---

### Task 3: Update test docstring and verify everything

**Files:**
- Modify: `test_backend.py:1-10` (update module docstring)

**Step 1: Update the module docstring**

Find:
```python
"""
Backend unit tests for Project Adil RAG API.

Tests cover:
- ConversationTurn model validation
- _parse_suggested_questions() helper
- _build_contents() multi-turn builder
- API endpoint contracts (mocked RAG service)
- Facebook content extraction (yt-dlp integration)
"""
```

Replace with:
```python
"""
Backend unit tests for Project Adil RAG API.

Tests cover:
- ConversationTurn model validation
- _parse_suggested_questions() helper
- _build_contents() multi-turn builder
- API endpoint contracts (mocked RAG service)
- Facebook content extraction (yt-dlp integration)
- Twitter/X content extraction (FXTwitter + yt-dlp)
- Instagram content extraction (OG + yt-dlp cascade)
- System prompt resource directory (actionable next steps)
"""
```

**Step 2: Run full test suite one final time**

Run: `python -m pytest test_backend.py -v`
Expected: All 71 tests PASS

**Step 3: Commit**

```bash
git add test_backend.py
git commit -m "docs: update test docstring to reflect all test coverage areas"
```
