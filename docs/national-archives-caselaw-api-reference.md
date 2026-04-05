# National Archives Case Law API Reference

> Source: https://caselaw.nationalarchives.gov.uk/
> OpenAPI Spec: https://raw.githubusercontent.com/nationalarchives/ds-find-caselaw-docs/refs/heads/main/doc/openapi/public_api.yml
> API Docs: https://nationalarchives.github.io/ds-find-caselaw-docs/public
> Version: 0.5.1

## 1. Base URL & Endpoints

**Base URL:** `https://caselaw.nationalarchives.gov.uk`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/atom.xml` | Atom feed of documents (primary search/list endpoint) |
| GET | `/{court}/{subdivision}/{year}/atom.xml` | Court-scoped feed (DEPRECATED, redirects) |
| GET | `/{document_uri}/data.xml` | Get full document XML (Akoma Ntoso) |

There is **no JSON REST API**. The API is Atom/XML-based. The Atom feed at `/atom.xml` is the primary programmatic interface for searching and listing cases.

## 2. Searching for Cases by Topic

Use the `query` parameter on the Atom feed endpoint for full-text search:

```
GET /atom.xml?query=discrimination
GET /atom.xml?query="religious+discrimination"
GET /atom.xml?query=equality+hate+crime
```

- Quoted phrases (`"religious discrimination"`) match exact word order.
- Multiple space-separated words match documents containing ALL words.
- The same parameters work on the web search at `/judgments/search`.

### Example: discrimination cases in EAT
```
GET /atom.xml?query=discrimination&court=eat
```

### Example: religious discrimination across multiple courts
```
GET /atom.xml?query="religious+discrimination"&court=eat&court=ewca/civ
```

## 3. Document Formats

Each document is available in **three formats**:

| Format | Access | Content-Type |
|--------|--------|--------------|
| **XML (Akoma Ntoso)** | `/{document_uri}/data.xml` | `application/akn+xml` |
| **PDF** | `https://assets.caselaw.nationalarchives.gov.uk/{uri}/{uri}.pdf` | `application/pdf` |
| **HTML** | `/{document_uri}` (web page) | `text/html` |

The XML uses the [Akoma Ntoso](https://www.oasis-open.org/standard/akn-v1-0/) standard — a structured legal document XML format. This is the richest format for programmatic processing.

The Atom feed entries include links to all three formats via `<link>` elements:
- `<link rel="alternate"/>` — HTML page
- `<link rel="alternate" type="application/akn+xml"/>` — XML
- `<link rel="alternate" type="application/pdf"/>` — PDF

## 4. Authentication & Rate Limits

- **No authentication required.** The API is fully public, no API key needed.
- **Rate limit:** 1,000 requests per rolling 5-minute window per IP address.
- Exceeding the limit returns `HTTP 429 Too Many Requests`.
- Contact caselaw@nationalarchives.gov.uk if you need higher limits.

## 5. Court/Tribunal Filter Codes

Use the `court` or `tribunal` parameter (they are aliases). Multiple values supported via repeated params.

### Courts relevant to AskAdil

| Court | Code | Coverage |
|-------|------|----------|
| **Employment Appeal Tribunal** | `eat` | 2021–present |
| **Court of Appeal (Civil)** | `ewca/civ` | 2001–present |
| **Court of Appeal (Criminal)** | `ewca/crim` | 2003–present |
| **UK Supreme Court** | `uksc` | 2009–present |
| **High Court (Admin)** | `ewhc/admin` | 2003–present |
| **High Court (KB)** | `ewhc/kb` | 2003–present |
| **High Court (Chancery)** | `ewhc/ch` | 2003–present |
| **High Court (Family)** | `ewhc/fam` | 2003–present |
| **County Court** | `ukcc` | 2019–present |

### Note on Employment Tribunal (first instance)
The Employment Tribunal (ET) is **NOT available** on Find Case Law. ET decisions are published via https://www.gov.uk/employment-tribunal-decisions (gov.uk) and historically on BAILII. Find Case Law only has the **Employment Appeal Tribunal (EAT)** from 2021 onwards.

### Tribunal codes

| Tribunal | Code | Coverage |
|----------|------|----------|
| Employment Appeal Tribunal | `eat` | 2021–present |
| Upper Tribunal (AAC) | `ukut/aac` | 2005–present |
| Upper Tribunal (IAC) | `ukut/iac` | 2007–present |
| First-tier Tribunal (GRC) | `ukftt/grc` | 2009–present |

Two code formats are accepted: URL-style (`ewhc/fam`) or XML-style (`EWHC-Family`).

## 6. Pagination

The Atom feed supports pagination via the `page` query parameter:

```
GET /atom.xml?query=discrimination&court=eat&page=1
GET /atom.xml?query=discrimination&court=eat&page=2
```

The feed includes standard Atom pagination links:
- `<link rel="first" href="...?page=1"/>`
- `<link rel="last" href="...?page=7326"/>`
- `<link rel="next" href="...?page=2"/>`

Total collection is ~7,326 pages as of April 2026.

## 7. Additional Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | string | Full-text search (quoted for exact phrase) |
| `court` | string[] | Court/tribunal code filter (repeatable) |
| `tribunal` | string[] | Alias for `court` |
| `party` | string | Match word in party name |
| `judge` | string | Match word in judge name |
| `order` | string | Sort order: `relevance`, `-date`, `date`, `-transformation` |
| `page` | int | Page number for pagination |

Date filtering parameters exist but are noted as `todo` in the OpenAPI spec — they appear to use `from_date_0`, `from_date_1`, `from_date_2` (day, month, year) based on the web form. These work on the web search URL:
```
/search?query=discrimination&court=eat&from_date_2=2023&to_date_2=2025
```
And equivalently on the atom feed.

## 8. Licensing Warning

**The Open Justice Licence does NOT permit computational analysis.** Bulk programmatic searching to identify, extract, or enrich content requires a separate (free) application:
https://caselaw.nationalarchives.gov.uk/re-use-find-case-law-records/licence-application-process

For an AskAdil integration that searches on behalf of individual users (not bulk indexing), the standard Open Justice Licence should suffice — but review the terms.

## 9. Example Integration Flow

```python
import httpx

BASE = "https://caselaw.nationalarchives.gov.uk"

# 1. Search for discrimination cases in EAT
resp = httpx.get(f"{BASE}/atom.xml", params={
    "query": "religious discrimination",
    "court": ["eat", "ewca/civ"],
    "order": "-date",
    "page": 1,
})
# resp.text is Atom XML — parse with lxml or feedparser

# 2. Get full judgment XML for a specific case
doc_uri = "eat/2024/123"  # or "d-f11e093f-8a53-4e43-8dd8-1531b5d8f018"
resp = httpx.get(f"{BASE}/{doc_uri}/data.xml")
# resp.text is Akoma Ntoso XML
```

## 10. Key GitHub Repositories

- **Public UI:** https://github.com/nationalarchives/ds-caselaw-public-ui (Django frontend)
- **API Client:** https://github.com/nationalarchives/ds-caselaw-custom-api-client (Python, MarkLogic backend)
- **API Docs:** https://github.com/nationalarchives/ds-find-caselaw-docs (OpenAPI spec, documentation)
