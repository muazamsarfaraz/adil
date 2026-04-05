# BAILII Programmatic Access Research

**Date:** 2026-04-01  
**Purpose:** Evaluate BAILII and alternatives for building a UK discrimination/equality case law integration

---

## 1. Does BAILII have an API?

**No.** BAILII explicitly states in their FAQ:

> "BAILII's Terms of Service prohibit the bulk downloading of data, therefore BAILII does not have an API."

They direct anyone interested in bulk data to **The National Archives (TNA) Find Case Law** service at https://caselaw.nationalarchives.gov.uk/

## 2. BAILII URL Structure

Cases are organized in a predictable hierarchy:

```
https://www.bailii.org/{jurisdiction}/cases/{court_code}/{year}/{number}.html
```

**Examples:**
| Court | URL Pattern |
|---|---|
| Employment Tribunal (ET) | `/uk/cases/UKET/{year}/{number}.html` |
| Employment Appeal Tribunal (EAT) | `/uk/cases/UKEAT/{year}/{number}.html` |
| Court of Appeal (Civil) | `/ew/cases/EWCA/Civ/{year}/{number}.html` |
| Court of Appeal (Criminal) | `/ew/cases/EWCA/Crim/{year}/{number}.html` |
| UK Supreme Court | `/uk/cases/UKSC/{year}/{number}.html` |
| ECHR | `/eu/cases/ECHR/{year}/{number}.html` |
| High Court (Admin) | `/ew/cases/EWHC/Admin/{year}/{number}.html` |

**Browsing structure:**
- Court index: `/uk/cases/UKEAT/` (lists years + A-Z title browse)
- Year listing: `/uk/cases/UKEAT/2024/` (lists all cases for that year by month)
- A-Z title: `/uk/cases/UKEAT/toc-A.html`

**Search endpoints:**
- Case law search: `/form/search_cases.html`
- Find by citation: `/cgi-bin/find_by_citation.cgi`
- Multidatabase search: `/form/search_multidatabase.html`

## 3. Case Organization

Cases are organized by:
- **Jurisdiction** (UK-wide, England & Wales, Scotland, Northern Ireland, Ireland, Europe)
- **Court/Tribunal** (each has its own code, e.g. UKEAT, UKET, EWCA)
- **Year** within each court
- **A-Z title index** within each court

BAILII OpenLaw also provides **curated topic lists** of leading cases:
- `/openlaw/employment.html` - Employment law leading cases
- `/openlaw/human_rights_echr.html` - Human Rights (ECHR) leading cases

## 4. Relevant Courts for Discrimination/Equality Law

| Court | BAILII Code | Path | Coverage |
|---|---|---|---|
| Employment Tribunal | UKET | `/uk/cases/UKET/` | 2011-2026 |
| Employment Appeal Tribunal | UKEAT | `/uk/cases/UKEAT/` | 1976-2026 |
| Court of Appeal (Civil) | EWCA/Civ | `/ew/cases/EWCA/Civ/` | Extensive |
| UK Supreme Court | UKSC | `/uk/cases/UKSC/` | 2009+ |
| House of Lords | UKHL | `/uk/cases/UKHL/` | Historical |
| ECHR | ECHR | `/eu/cases/ECHR/` | Extensive |
| High Court (Admin) | EWHC/Admin | `/ew/cases/EWHC/Admin/` | Relevant for JR of tribunal decisions |

**Note:** EAT cases on BAILII often include subject tags in parentheses, e.g.:
- `(DISABILITY DISCRIMINATION)`
- `(RACE DISCRIMINATION)`
- `(AGE DISCRIMINATION)`
- `(EQUAL PAY)`
- `(SEX DISCRIMINATION)`

This is useful for filtering discrimination cases from the year listings.

## 5. Judgment Format

- **HTML pages** with embedded styling (MS Word-converted HTML with MsoNormal classes)
- Each judgment page includes: neutral citation, court, date, parties, judge names, full text
- **PDF versions** also available at the same path with `.pdf` extension
- The HTML is messy (Word-to-HTML conversion) but the text content is extractable
- Citation metadata is in the page header breadcrumb area
- Individual case URLs are stable and cite-able

## 6. Terms of Service / Scraping Restrictions

**BAILII explicitly prohibits scraping.** Their Terms of Service (https://www.bailii.org/bailii/copyright.html) state:

**Prohibited Uses include:**
- (a) incorporating search results or HTML versions of judgments into another website or computer program
- (b) storing search results or HTML versions of judgments
- (c) external indexing by web robots/spiders not authorized by robots.txt
- (d) abusive use via automated mechanisms, particularly bulk downloading

**robots.txt** blocks ALL case law directories for all user agents:
```
User-agent: *
Disallow: /eu
Disallow: /ew
Disallow: /ie
Disallow: /uk
Disallow: /wales
...
User-agent: GPTBot
Disallow: /
```

**BAILII actively monitors and blocks** domains using automated access without authorization.

**Copyright:** HTML markup copyright belongs to BAILII. Judgment text is Crown Copyright (freely reproducible if attributed). Third-party publisher copyright may apply to some content.

**Conclusion: Do NOT scrape BAILII.** They will block you and it violates their ToS.

## 7. Recommended Alternative: The National Archives Find Case Law

BAILII themselves recommend TNA for bulk/programmatic access.

### TNA Public API

**Atom Feed endpoint:** `https://caselaw.nationalarchives.gov.uk/atom.xml`

- Returns paginated Atom XML feed of documents
- Parameters mirror the advanced search at `/judgments/search`
- Can filter by court, date range, and keywords
- Supports ordering by `-transformation` (most recently changed first) or handed-down date
- Each entry includes links to:
  - HTML version (on the FCL website)
  - XML version (LegalDocML / Akoma Ntoso format)
  - PDF version

**Document formats available:**
- **XML (LegalDocML):** Structured markup with neutral citation, court, date, case name, party names, judge names
- **HTML:** Auto-converted from XML
- **PDF:** Available for download

### TNA Court Coverage (relevant courts)

| Court | Date Range |
|---|---|
| UK Supreme Court | 2009-2026 |
| Court of Appeal (Civil) | 2001-2026 |
| Court of Appeal (Criminal) | 2003-2026 |
| High Court (Administrative) | 2003-2026 |
| Employment Appeal Tribunal | Received regularly |
| Upper Tribunals | Received regularly |

**Note:** TNA receives EAT cases directly. First-tier Employment Tribunal coverage may be limited compared to BAILII.

### TNA Licensing

- **Open Justice Licence v2.0** covers most uses freely, including commercial use
- **Computational analysis requires a separate licence** (free to apply, no charges)
  - This includes: text mining, NLP, bulk extraction, ML/AI training, statistical analysis
  - Apply via: https://caselaw.nationalarchives.gov.uk/what-you-need-to-apply-for-a-licence
  - Contact: caselawlicence@nationalarchives.gov.uk
- You MUST apply before doing any programmatic bulk access

### TNA GitHub

Open source service: https://github.com/nationalarchives/ds-find-caselaw-docs

---

## Recommendation for AskAdil

1. **Use The National Archives Find Case Law API** as the primary data source
2. **Apply for a computational analysis licence** (free) before building any scraper/integration
3. **Use the Atom feed** (`/atom.xml`) to query and paginate through cases filtered by court (EAT, EWCA/Civ, UKSC)
4. **Consume XML (LegalDocML)** format for structured metadata extraction
5. **Supplement with BAILII OpenLaw** topic pages (manually curated, small number of leading cases) via manual review only
6. **For Employment Tribunal (ET) first-instance decisions:** these may require BAILII or gov.uk ET decisions page (https://www.gov.uk/employment-tribunal-decisions) as TNA coverage of ET is limited
7. **For ECHR cases:** consider HUDOC (https://hudoc.echr.coe.int/) which has its own API

### Priority courts for discrimination/equality:
1. EAT (UKEAT) - primary source of discrimination case law
2. Court of Appeal Civil (EWCA/Civ) - appellate discrimination law
3. UK Supreme Court (UKSC) - landmark equality decisions
4. High Court Admin (EWHC/Admin) - judicial review of tribunal decisions
5. ECHR - European human rights dimension
