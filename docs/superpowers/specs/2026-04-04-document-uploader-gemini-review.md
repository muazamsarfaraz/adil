# Gemini Review (document)

**Model:** `gemini-3.1-pro-preview`
**Date:** 2026-04-05 00:07:52
**Review type:** document

**Files reviewed:**
- `E:\dev\mcbx\adil\docs\superpowers\specs\2026-04-04-document-uploader-design.md`

---

Overall, this is an excellent, highly practical design specification. It is concise, well-structured, and gives an engineering team exactly the information they need to understand the *why*, *what*, and *how* of the microservice. 

However, there are a few technical inaccuracies, missing edge-case handlings, and stylistic inconsistencies that should be addressed before it is finalized.

Here is a detailed review with actionable suggestions for improvement.

---

### 1. Completeness and Accuracy (Technical Flaws)
*   **Math Error in Rate Limiting:** Under **Data Flow > Fetch cycle (Step 6)**, the document states: *"max 200 req/min (well under 1,000/5min)"*. 
    *   *Issue:* 200 requests/minute × 5 minutes = 1,000 requests. This is exactly the limit, not "well under," which risks triggering HTTP 429 (Too Many Requests) errors.
    *   *Action:* Change this to *"max 150 req/min"* (or 100) to ensure a safe buffer.
*   **Missing Error Logging in Database Schema:** Under the **Upload cycle (Step 5)**, the document mentions: *"On failure: set status `failed`, log error..."* 
    *   *Issue:* If a background worker fails, searching through container logs is tedious. 
    *   *Action:* Add an `error_message` or `last_error` (TEXT) column to the `judgments` table to store the stack trace or HTTP error reason for failed fetches/uploads. 
*   **Package Management:** The project structure includes `pyproject.toml`, but no lock file is shown (e.g., `poetry.lock`, `uv.lock`, or `requirements.txt`). 
    *   *Action:* Add the appropriate lock file to the directory tree to clarify which dependency manager the project uses.

### 2. Clarity and Readability
*   **Expand Acronyms on First Use:** While the target audience (engineers) might know some of these, expanding them improves readability for new hires or adjacent teams.
    *   *Action:* 
        *   Define **FST** (File Search Tool) in the Purpose section.
        *   Define **ET** (Employment Tribunal) in the Constraints section.
        *   Define **ECHR** (European Convention on Human Rights / Court of Human Rights) in the Search Domains section.
*   **Clarify "Clean Text":** Under **Data Flow**, Step 4 mentions extracting "clean text." 
    *   *Action:* Briefly specify what this means (e.g., "strip XML tags, remove footnotes, preserve paragraph breaks") so the developer writing `xml_parser.py` knows the exact requirement.
*   **Data Flow Diagram:** The ASCII diagram is slightly confusing because the arrows don't clearly map to the text below it. 
    *   *Action:* Update the ASCII art to clearly denote the two distinct asynchronous processes (Fetch vs. Upload):
    ```text
    [TNA Atom API] 
         │ (Fetch via arq worker)
         ▼
    [Postgres (dedup on neutral_citation)]
         │ (Upload via arq worker)
         ▼
    [Gemini FST Store]
    ```

### 3. Logical Flow and Structure
*   **Numbering Typo:** Under **Data Flow > Fetch cycle**, the numbering repeats the number 3: (1, 2, 3, **3**, 4, 5, 6).
    *   *Action:* Correct the numbering sequence to 1 through 7.
*   **Upload Cycle Trigger:** The fetch cycle mentions it runs daily via "arq cron". The upload cycle says it "runs after fetch".
    *   *Action:* Clarify *how* it runs after the fetch. Does the fetch task enqueue the upload task? Is it a separate cron job? Add a brief sentence: *(e.g., "Triggered automatically by the worker upon completion of the fetch cycle").*

### 4. Grammar and Style Consistency
*   **Tone and Abbreviations:** Avoid overly casual shorthand in formal design specs.
    *   *Action:* Change "dedup" to "deduplication" in the Purpose section.
*   **Capitalization Consistency:** 
    *   *Action:* Ensure consistent casing for database statuses. In the text, they are lowercase (`pending`), but in specs, it is often clearer to use uppercase for ENUMs (e.g., `PENDING`, `UPLOADED`, `FAILED`). Whichever you choose, ensure the Python implementation matches the spec.
*   **Date Sanity Check:** The document date is `2026-04-04`. 
    *   *Action:* Verify if this is intentional (e.g., a future-dated project) or a typo for `2024` or `2025`.

### 5. Audience Appropriateness
The document is excellently tailored for a backend engineering team. The inclusion of Railway deployment details, specific FastAPI/arq architectural choices, and explicit mentions of existing patterns (e.g., "same pattern as `adil-outreach-engine`") provides fantastic context that reduces developer friction. 

### Suggested Rewrite for the "Data Flow" Section
Here is how you might apply the feedback to the Data Flow section to make it perfect:

```markdown
### Data Flow

```text
[TNA Atom API] 
     │ (1. Fetch via arq cron)
     ▼
[Postgres Database] (Deduplication via neutral_citation)
     │ (2. Upload via arq worker)
     ▼
[Gemini FST Store]
```

**Fetch cycle** (daily 03:00 UTC via arq cron):
1. Worker iterates predefined search queries against `GET https://caselaw.nationalarchives.gov.uk/atom.xml`.
2. Follow `rel="next"` pagination links until results are exhausted or the rate limit is approached.
3. For each Atom entry, check if `neutral_citation` exists in Postgres.
4. If new: fetch full judgment via `GET /{tna_uri}/data.xml`.
5. Parse Akoma Ntoso XML → extract clean plain text (stripping XML tags while preserving paragraph structure), parties, date, and court.
6. Insert into DB with status `pending`.
7. Rate limiting: Implement a simple async semaphore, max 150 req/min (ensuring a safe buffer under the 1,000/5min Open Justice Licence limit).

**Upload cycle** (Enqueued automatically after fetch cycle completes):
1. Query judgments with status `pending`.
2. Prepend a metadata header to the clean text to improve LLM context:
   ```text
   CITATION: [2023] EAT 45
   CASE: Smith v Employer Ltd
   COURT: Employment Appeal Tribunal
   DATE: 2023-06-15
   SOURCE: https://caselaw.nationalarchives.gov.uk/eat/2023/45
   ---
   [judgment text]
   ```
3. Upload to Gemini FST Store via `genai.Client.files.upload()` and associate the file with the store.
4. On success: update status to `uploaded` and store the `gemini_file_id`.
5. On failure: update status to `failed`, store the reason in `error_message`, and retry on the next cycle.
```