# AskAdil Reporting Integration Roadmap & PRD

**Date:** 2026-03-07
**Author:** AskAdil Development Team
**Status:** Draft for Discussion
**Audience:** MCB Leadership, IRU, Partner Organisations

---

## Executive Summary

AskAdil currently educates users about their legal rights and directs them to reporting organisations via links. This document proposes a phased approach to **integrate directly with UK reporting portals**, reducing friction for users who want to take action after receiving legal guidance.

The vision: a user tells AskAdil about a hate incident, receives legal education, and can then **generate a pre-filled report** ready to submit to the appropriate organisation — reducing the reporting journey from 30+ minutes to under 5.

**Key finding:** Most reporting forms collect information that AskAdil already gathers during its intake conversation. The primary barrier is not technical — it is establishing data-sharing partnerships with each organisation.

**Key distinction:** Not all paths are self-service. Hate crime reporting (Tell MAMA, IRU, Police) can be done directly by users, but workplace discrimination claims (ACAS, ET1) and compensation claims should go through a solicitor. AskAdil must route users to the right path — and help them find a Muslim solicitor when needed.

---

## Self-Service vs Solicitor Paths

AskAdil handles two fundamentally different user journeys. The integration approach differs for each.

### Self-Service Path (AskAdil helps directly)

User can report/act independently. AskAdil generates summaries, guides form completion, and (in later tiers) submits on their behalf.

| Scenario | Organisations | AskAdil Role |
|----------|--------------|--------------|
| Hate crime / Islamophobia | Tell MAMA, IRU, Police Scotland, True Vision | Generate report summary, guide form completion |
| Online hate speech | Tell MAMA, platform reporting tools | Analyse content, generate report |
| General discrimination enquiry | EASS (phone/email/chat) | Brief user on what to ask |
| Information gathering | Citizens Advice | Direct to local bureau |

### Solicitor Path (AskAdil prepares and refers)

User needs professional legal representation. AskAdil educates on rights, prepares a case summary for the solicitor, and helps find a Muslim solicitor.

| Scenario | Process | AskAdil Role |
|----------|---------|--------------|
| Workplace discrimination | Solicitor -> ACAS EC -> ET1 | Explain process, generate case summary, find solicitor |
| Service discrimination (county court) | Solicitor -> county court claim | Explain rights, generate case summary, find solicitor |
| Compensation claims | Solicitor required | Explain Vento bands, generate case summary, find solicitor |
| Complex / multi-issue cases | Solicitor required | Triage, generate case summary, find solicitor |
| Appeals | Solicitor strongly recommended | Explain process, find solicitor |

**Key principle:** For solicitor-path cases, AskAdil's value is in (1) educating the user so they understand what the solicitor will do, (2) generating a structured case summary the user can bring to their first consultation, and (3) helping them find a Muslim solicitor who understands their community context.

---

## Find a Muslim Solicitor

### The Problem

The Law Society's "Find a Solicitor" tool (solicitors.lawsociety.org.uk) lets users search by legal specialism and location, but not by cultural background or community understanding. For British Muslims facing discrimination — especially around hijab, prayer, Islamophobia — having a solicitor who understands the community context can significantly improve the experience and outcome.

### Existing Directories

| Directory | URL | Coverage | Searchable? | Notes |
|-----------|-----|----------|-------------|-------|
| **Muslim Lawyer UK** | muslimlawyer.co.uk | London (primarily) | By area | Partner lawyers network, covers employment/family/immigration |
| **Muslim Solicitors** | muslimsolicitors.co.uk | England & Wales | Limited | Multi-language, employment/family/immigration |
| **Association of Muslim Lawyers (AML)** | No public directory | National | No | Est. 1993, professional body for Muslim lawyers. No searchable member list. Contact: amlevents@mail.com |
| **Muslim Lawyers Action Group (MLAG)** | Inner Temple network | National | No | Network of Muslim solicitors, barristers, academics at the Inner Temple |
| **Ascentim Legal** | ascentimlegal.com | National | No | Firm specialising in Sharia-related issues under UK law |

**Gap:** No single, comprehensive, searchable directory of Muslim solicitors by specialism (discrimination, employment, hate crime) and location exists.

### Seed Database

A research database of 24 firms and 2 professional bodies has been compiled:

**See:** `docs/plans/muslim-solicitors-seed-database.json`

| Category | Count | Examples |
|----------|-------|---------|
| Muslim community focus | 8 firms | Rahman Lowe, Duncan Lewis, Kesar & Co, Sharma Solicitors |
| Discrimination specialists | 8 firms | Didlaw, Farore Law, Slater + Gordon, Bindmans, Redmans |
| Scotland | 5 firms | Lindsays, Jackson Boyd, Thompsons Scotland |
| Northern Ireland | 3 firms | P.A. Duffy & Co, Paul Doran Law |
| Professional bodies | 2 | Association of Muslim Lawyers (AML), Muslim Lawyers Action Group (MLAG) |

**Status:** All firms marked `outreach_status: "not_contacted"`. None have consented to be listed.

### Outreach Plan

**Phase 1 — Introductory contact (MCB to lead):**

Template email/letter to each firm:

> *Dear [Firm],*
>
> *The Muslim Council of Britain is developing AskAdil (askadil.org), a free AI legal education tool that helps British Muslims understand their rights under UK discrimination law.*
>
> *We are building a "Find a Muslim Solicitor" feature to connect users who need professional legal representation with solicitors experienced in discrimination cases.*
>
> *Would your firm be interested in being listed? Listing is free and includes your firm name, location, specialisms, and contact details. Users who need legal representation would be directed to you with a structured case summary (with their consent) so you have context before the first consultation.*
>
> *We would value a brief call to discuss this. Please reply to [contact] or call [number].*

**Phase 2 — Data collection from consenting firms:**
- Confirm: firm name, locations, specialisms, contact URL/email/phone
- Ask: languages spoken, free initial consultation available, no-win-no-fee available, Legal Aid accepted
- Ask: preferred referral method (email, phone, web form)
- Get: written consent to list on AskAdil

**Phase 3 — Professional body partnerships:**
- Contact AML (amlevents@mail.com) to discuss member directory sharing
- Contact MLAG at Inner Temple for barrister referral partnership

### Recommended Approach (Phased)

**Immediate:** Generic solicitor-finding links only (already in system prompt):
- "Find any discrimination solicitor at solicitors.lawsociety.org.uk"
- "For Scotland: lawscot.org.uk / For NI: lawsoc-ni.org"

**After outreach (Tier 2):** Build curated "AskAdil Recommended Solicitors" directory:
- Only list firms that have consented
- Searchable by jurisdiction, specialism, and location
- Display in AskAdil responses: "We recommend these solicitors in your area who have experience with discrimination cases"
- New endpoint: `GET /api/v1/solicitors?jurisdiction=england&specialism=employment_discrimination&location=london`

**Long-term (Tier 3):** AskAdil Solicitor Referral Service:
- User completes AskAdil conversation about a solicitor-path case
- AskAdil generates a structured case summary (solicitor consultation pack)
- User clicks "Find a Solicitor" and selects from consented directory
- Case summary is sent to the solicitor (with user consent) as a referral
- Solicitor contacts user for a free initial consultation
- Track referral outcomes (with consent) to improve recommendations

### Partnership Opportunities

**Association of Muslim Lawyers (AML):**
1. Would AML share or publish a searchable member directory (by specialism and region)?
2. Would AML members accept referrals from AskAdil with structured case summaries?
3. Could AML endorse AskAdil as a pre-consultation tool? ("Before your appointment, use AskAdil to understand your rights")
4. Would AML co-brand a "Find a Muslim Discrimination Solicitor" feature?
5. Can AML help identify members who offer free initial consultations?

**Muslim Lawyer UK / Muslim Solicitors:**
- Would these directories accept referral traffic from AskAdil?
- Can we get structured data (solicitor name, specialism, location, contact) for integration?
- Interest in a co-branded "AskAdil recommends" listing?

**Individual firms:**
- Each firm in the seed database is a potential partner
- Priority outreach to the 8 Muslim-community-focus firms first
- Secondary outreach to discrimination specialists with proven Muslim case track records (Redmans, Didlaw)

---

## Current State

AskAdil's conversation flow already collects:
- **Jurisdiction** (England/Wales, Scotland, NI)
- **Incident type** (workplace, hate crime, service discrimination, online)
- **Date/time** of incident
- **Location** (general area)
- **Incident description** (detailed narrative)
- **Whether police were contacted**
- **Severity assessment** (via viability scoring)

After intake, responses include a "What You Can Do Now" section with 3-5 relevant organisation links selected by topic and jurisdiction.

**Gap:** Users must then navigate to each organisation's website, find the form, and re-enter all the information they already provided to AskAdil.

---

## Portal Analysis

### 1. IRU (Islamophobia Response Unit)

**URL:** theiru.org.uk/report-islamophobia/
**Form type:** Multi-step web form (15+ fields)

| Field | Required | AskAdil Can Map? | Notes |
|-------|----------|-----------------|-------|
| Full Name | Yes | No | PII — user must provide |
| Email | Yes | No | PII |
| Phone | Yes | No | PII |
| Gender | Yes | No | Not collected |
| Ethnicity | Yes | No | Not collected |
| Country of Residence | Yes | Partial | Jurisdiction known (UK) but not specific country |
| Age | Yes | No | Not collected |
| Victim / Reporting on behalf | Yes | Yes | Conversation context |
| Date of Incident | Yes | Yes | Collected during intake |
| Location of Incident | Yes | Yes | Collected during intake |
| Incident Details | Yes | Yes | Core conversation content |
| Police Report Status | Yes | Yes | Often discussed |
| CCTV Awareness | No | No | Not typically discussed |
| Referral Source | No | Yes | "AskAdil / MCB" |
| Court Dates | No | Partial | If discussed |
| Consent | Yes | No | Must be explicit |

**Mappability:** ~5 of 15 fields (33%) auto-fillable from conversation
**Recommended approach:** Generate a structured incident summary that users can copy-paste into the form's free-text fields. Medium-term: discuss API/referral partnership with IRU.

---

### 2. Tell MAMA

**URL:** tellmamauk.org/submit-a-report-to-us/
**Form type:** Web form with file upload support

| Field | Required | AskAdil Can Map? | Notes |
|-------|----------|-----------------|-------|
| Name | Yes | No | PII |
| Email | Yes | No | PII |
| Phone | Yes | No | PII |
| Incident Type | Yes | Yes | Mapped from conversation topic |
| Description | Yes | Yes | Core conversation content |
| Location | Yes | Yes | Collected during intake |
| Victim / Witness | Yes | Yes | Conversation context |
| Date/Time | No | Yes | Collected during intake |
| Photos/Evidence | No | No | Not collected (URLs may be relevant) |
| Demographics | No | No | Not collected |

**Mappability:** ~5 of 10 fields (50%) auto-fillable
**Recommended approach:** Tell MAMA is a key MCB partner. Explore a **referral API** where AskAdil sends a structured case summary with user consent. Tell MAMA already works with third-party reporting centres — AskAdil could become a digital reporting centre.

---

### 3. Police Scotland — Hate Crime Reporting Form

**URL:** scotland.police.uk/secureforms/c3/
**Form type:** Single-page web form with conditional panels

| Field | Required | AskAdil Can Map? | Notes |
|-------|----------|-----------------|-------|
| Emergency? (Yes/No) | Yes | Yes | AskAdil assesses severity |
| Incident Type | Yes | Yes | Dropdown: "Hate Related Incident - Religion" |
| Self / 3rd Party | Yes | Yes | Conversation context |
| Anonymous? | Yes | No | User choice |
| Name | Yes | No | PII |
| Address | Yes | No | PII |
| Town | Yes | Partial | General area from conversation |
| Postcode | No | No | PII |
| Phone | Yes | No | PII |
| Email | Yes | No | PII |
| Date of Birth | No | No | Not collected |
| Contact Preference | Yes | No | User choice |
| Special Requirements | No | No | Not typically discussed |
| What happened (2000 char) | Yes | Yes | Core conversation content |
| Where did this happen (2000 char) | Yes | Yes | Collected during intake |
| When did this happen (2000 char) | Yes | Yes | Collected during intake |
| Perpetrator description (2000 char) | Yes | Partial | If discussed |
| Additional info (2000 char) | Yes | Yes | Legal context from AskAdil |
| Disclaimer checkbox | Yes | No | Must be explicit |

**Mappability:** ~7 of 19 fields (37%) auto-fillable — but the critical narrative fields (what/where/when) are all mappable
**Recommended approach:** Generate a structured report matching the form's 5 narrative sections. User copies into the form alongside their personal details.

---

### 4. Met Police (England & Wales) — Online Hate Crime Reporting

**URL:** met.police.uk/ro/report/hate-crime/
**Form type:** Multi-step JavaScript form (varies by police force)

**Challenge:** Each of the 43 police forces in England & Wales has a different online reporting system. The Met Police form requires JavaScript and is a multi-step wizard. Form fields could not be fully captured but follow a similar pattern to Police Scotland.

**Recommended approach:** Focus on Police Scotland first (single, accessible form). For England/Wales, generate a narrative summary users can take to any reporting channel (online, 101, or in person).

---

### 4a. Police UK — National Online Hate Crime Reporting

**URL:** police.uk/ro/report/hate-crime/forms/v1/hate-crime-online2/
**Form type:** Multi-step JavaScript wizard

This is the **national police.uk reporting form** covering England & Wales. Unlike individual force forms, this is a single entry point that routes reports to the relevant local force.

| Field | Required | AskAdil Can Map? | Notes |
|-------|----------|-----------------|-------|
| First name | Yes | No | PII — user must provide |
| Surname | Yes | No | PII |
| Date of birth (Day/Month/Year) | Yes | No | PII |
| Gender (Female/Male/Self-describe) | Yes | No | Not collected |
| Incident narrative | Yes | Yes | Core conversation content |
| Location of incident | Yes | Yes | Collected during intake |
| Date/time of incident | Yes | Yes | Collected during intake |

**Mappability:** Narrative fields (incident details, location, timing) are mappable from AskAdil conversation; personal details require user input.
**Recommended approach:** Include in Tier 2 Smart Form Guides alongside Police Scotland. Generate pre-filled narrative text users can copy into the form. This is the preferred England & Wales reporting form as it works nationally.

---

### 5. True Vision (report-it.org.uk)

**URL:** report-it.org.uk
**Form type:** Unknown — site certificate expired at time of research

**Note:** True Vision is the national online hate crime reporting portal. Reports are forwarded to local police forces. When the site is accessible, it likely collects similar fields to Police Scotland.

**Recommended approach:** Revisit when certificate is renewed. True Vision may be the best England/Wales equivalent to Police Scotland's form.

---

### 6. ACAS Early Conciliation (SOLICITOR PATH)

**URL:** acas.org.uk/notify/start
**Form type:** Multi-step wizard
**Path:** Solicitor-assisted (recommended)

| Field | Required | AskAdil Can Map? | Notes |
|-------|----------|-----------------|-------|
| Claimant Name | Yes | No | PII |
| Claimant Address | Yes | No | PII |
| Claimant Contact | Yes | No | PII |
| Respondent Name (employer) | Yes | Partial | If discussed |
| Respondent Address | Yes | No | Rarely provided |
| Nature of Dispute | Yes | Yes | Conversation topic |
| Employment dates | Likely | Partial | If discussed |

**Mappability:** Low (~2 of 7 core fields)
**Why solicitor path:** ACAS Early Conciliation is a mandatory prerequisite before Employment Tribunal claims. While users *can* self-notify, having a solicitor manage this process significantly improves outcomes — the solicitor handles negotiation during the conciliation window and ensures deadlines are met.
**Recommended approach:** AskAdil educates the user on the ACAS EC process, generates a case summary for the solicitor, and helps find a Muslim solicitor (see "Find a Muslim Solicitor" section). Also generates a checklist of information the user needs to gather before their solicitor appointment.

---

### 7. ET1 Employment Tribunal Claim (SOLICITOR PATH)

**URL:** gov.uk/employment-tribunals/make-a-claim
**Form type:** GOV.UK multi-step form (requires ACAS certificate number)
**Path:** Solicitor-assisted (strongly recommended)

**Prerequisite:** User must have completed ACAS Early Conciliation first and received a certificate with a unique reference number. This number is mandatory on the ET1 form.

**Why solicitor path:** The ET1 form requires detailed legal grounds, correct respondent identification, and precise claim articulation. Errors can result in claims being struck out. The 3-month-less-1-day time limit (from date of the act complained of) makes professional guidance critical.
**Recommended approach:** AskAdil explains the sequential process (find solicitor -> ACAS EC -> ET1), generates a structured case summary the user brings to their first solicitor consultation, and helps find a Muslim solicitor. AskAdil should never encourage users to file ET1 claims without legal advice.

---

### 8. EASS (Equality Advisory Support Service)

**URL:** equalityadvisoryservice.com
**Form type:** No complaint form — advisory service via phone, email, live chat

**Recommended approach:** No form integration possible. AskAdil already provides the contact details and can brief users on what to ask when they call.

---

### 9. EHRC (Equality and Human Rights Commission)

**URL:** equalityhumanrights.com
**Form type:** No public complaint form for individuals

**Key finding:** The EHRC does not handle individual complaints. They:
- Route all individual enquiries to EASS
- Accept whistleblowing reports (via online form or email)
- Accept discrimination claim notifications from courts (not individuals)
- Have a Legal Helpline for legal professionals only

**Recommended approach:** No direct integration. AskAdil correctly routes users to EASS for individual help and can explain the EHRC's strategic enforcement role.

---

## Integration Tiers

### Tier 1: Incident Summary Generator (Immediate — No Partnership Required)

**Timeline:** 2-4 weeks
**Dependencies:** None — purely client-side

After the intake conversation, AskAdil generates a **structured incident summary** formatted for easy copy-paste into reporting forms:

```
--- INCIDENT REPORT SUMMARY ---
Generated by AskAdil on [date]

TYPE: Religious discrimination / hate crime
DATE: [extracted from conversation]
LOCATION: [extracted from conversation]
JURISDICTION: [England/Wales/Scotland/NI]

WHAT HAPPENED:
[AI-generated structured narrative from conversation]

WHEN THIS HAPPENED:
[Date, time, duration details]

WHERE THIS HAPPENED:
[Location details]

PERPETRATOR (if known):
[Any descriptions provided]

POLICE CONTACTED: [Yes/No]
EVIDENCE: [URLs analysed, if any]

LEGAL CONTEXT (from AskAdil analysis):
- Relevant legislation: [e.g., Equality Act 2010 s.13, Public Order Act 1986 s.29B]
- Potential classification: [e.g., religiously aggravated harassment]
- Time limits: [e.g., 3 months less 1 day for ET claim]

--- END SUMMARY ---
```

**User flow:**
1. User has conversation with AskAdil
2. User clicks "Generate Report Summary" button
3. AskAdil produces structured text
4. User copies relevant sections into the reporting form of their choice

**Value:** Reduces cognitive load; users don't have to re-articulate their story. The legal context section adds value that no reporting form currently provides.

**Solicitor path variant:** For workplace/compensation cases, generate a **solicitor consultation pack** instead:

```
--- SOLICITOR CONSULTATION PACK ---
Generated by AskAdil on [date]
Bring this to your first solicitor appointment.

YOUR SITUATION:
[Structured narrative from conversation]

KEY DATES:
- Incident date: [date]
- Time limit for ET claim: [calculated deadline]
- ACAS EC must be started by: [calculated date]

RELEVANT LEGISLATION:
- [e.g., Equality Act 2010 s.13 (direct discrimination), s.26 (harassment)]

ASKADIL ASSESSMENT:
- Viability: [score]/100
- Vento band estimate: [band] ([range])
- Note: This is a preliminary AI assessment, not legal advice.

WHAT TO ASK YOUR SOLICITOR:
1. Do I have grounds for a claim?
2. Should we go through ACAS first?
3. What evidence do I need to gather?
4. Do you offer a no-win-no-fee arrangement?
5. What is the realistic timeline?

FIND A MUSLIM SOLICITOR:
- muslimlawyer.co.uk (London & surrounding)
- muslimsolicitors.co.uk (England & Wales)
- solicitors.lawsociety.org.uk (all solicitors by specialism)

--- END PACK ---
```

---

### Tier 2: Smart Form Guides (3-6 months — No Partnership Required)

**Timeline:** 3-6 months
**Dependencies:** None

Extend the incident summary with **form-specific guides** that map AskAdil's output to each organisation's form fields:

**Example for Police Scotland:**
```
POLICE SCOTLAND HATE CRIME FORM GUIDE
(scotland.police.uk/secureforms/c3/)

Step 1: Select "No" for emergency (unless ongoing)
Step 2: Select "Hate Related Incident - Religion"
Step 3: Select "No - This is about me" (or "Yes" if reporting for someone)
Step 4: Fill in your personal details (name, address, phone, email)
Step 5: Copy into "What happened": [pre-filled text]
Step 6: Copy into "Where did this happen": [pre-filled text]
Step 7: Copy into "When did this happen": [pre-filled text]
Step 8: Copy into "Description of person": [pre-filled text or "Unknown"]
Step 9: Copy into "Additional info": [pre-filled legal context]
Step 10: Tick the disclaimer and submit
```

**Value:** Removes the "what do I put in each field?" friction. Especially valuable for users unfamiliar with formal reporting.

---

### Tier 3: Referral Partnerships (6-12 months — Requires Partnerships)

**Timeline:** 6-12 months
**Dependencies:** Data sharing agreements, API access, GDPR compliance

Establish formal referral partnerships where AskAdil can send structured case data directly to partner organisations with user consent.

**Priority partners:**

| Organisation | Why | Integration Type | Path | Complexity |
|-------------|-----|-----------------|------|------------|
| **Tell MAMA** | MCB relationship, existing 3rd party reporting model | Referral API or email submission | Self-service | Medium |
| **IRU** | MCB relationship, direct Islamophobia focus | Referral API or structured email | Self-service | Medium |
| **AML** | Muslim solicitor directory for solicitor-path cases | Referral list / member directory | Solicitor | Medium |
| **Police Scotland** | Single form, structured fields, public submission | Automated form submission | Self-service | High |

**Technical approach:**
1. User completes AskAdil conversation
2. User clicks "Report to [Organisation]"
3. AskAdil shows a consent screen: "We will share the following information with [Organisation]: [list]. Do you consent?"
4. User provides any missing required fields (name, email, phone)
5. AskAdil submits via API/structured email
6. User receives confirmation

**GDPR considerations:**
- Explicit consent required before any data sharing
- Data minimisation — only share fields required by the receiving organisation
- Right to withdraw — user can request deletion
- Privacy notice must explain each partner and what data is shared
- MCB as data controller, partners as independent controllers
- Data Processing Agreements required with each partner

---

### Tier 2.5: AI Browser Bridge (IMPLEMENTED)

**Timeline:** Implemented 2026-03-23
**Dependencies:** None — browser-use + Gemini Flash

AskAdil's **adil-report-bridge** microservice uses AI-powered browser automation to fill and submit reporting forms on behalf of users. The AI agent reads form labels semantically, adapting to UI changes without hard-coded selectors.

**Live bridge targets:**

| Target | Form URL | PII Required? | Coverage |
|--------|----------|--------------|----------|
| **Police UK** | police.uk/ro/report/hate-crime/... | Yes | England & Wales |
| **Tell MAMA** | tellmamauk.org/submit-a-report-to-us/ | Yes | UK-wide |
| **Police Scotland** | scotland.police.uk/secureforms/c3/ | Yes | Scotland |
| **IRU** | theiru.org.uk/report-islamophobia/ | Yes | UK-wide |
| **Islamophobia UK** | islamophobiauk.co.uk/ | No (anonymous) | UK-wide |

**User flow:** User types "report" → selects target → provides PII (if required) → reviews consent → bridge fills and submits form → user gets confirmation + reference number. If bridge fails, a structured fallback report is generated for manual submission.

**Architecture:** See `docs/superpowers/specs/2026-03-22-report-bridge-design.md`

---

### Tier 2.6: Email Adapter (Roadmap)

**Timeline:** Next sprint
**Dependencies:** SendGrid API key, MCB approval for sender domain

For organisations that accept reports via email but have no web form, add an **email adapter** to the bridge service alongside the browser adapter. Uses SendGrid to send a structured incident report email.

**Email adapter candidates:**

| Organisation | Email | Viable? |
|-------------|-------|---------|
| **EASS** | Via equalityadvisoryservice.com contact form or email | Yes — structured enquiry email |
| **Muslim Safety Net** | Via muslimsafetynet.org.uk | Partial — primary channel is WhatsApp |
| **Stop Hate UK** | Via stophateuk.org | Partial — primary channel is phone |

**Not viable for email adapter:**
- BTP (text 61016 — police text line, cannot accept programmatic SMS)
- Prevent Watch (phone only)
- British Muslim Trust (phone only)

**Implementation:**
- Add `adapter_type: "email"` field to target config (currently all are `"browser"`)
- New `email_adapter.py` in bridge service using SendGrid
- Structured email template with incident summary, legal context, and AskAdil attribution
- Same consent flow as browser adapter
- Requires: SendGrid API key, verified sender domain (e.g. reports@askadil.org)

---

### Tier 4: Deep Integration (12-24 months — Requires Significant Partnership)

**Timeline:** 12-24 months
**Dependencies:** Formal MoUs, technical integration, regulatory approval

**AskAdil as a Third-Party Reporting Centre:**
- Tell MAMA and Police Scotland both support Third Party Reporting Centres (TPRCs)
- AskAdil (via MCB) could apply to become a recognised digital TPRC
- This would give AskAdil formal authority to submit reports on behalf of users
- Police Scotland lists TPRCs publicly — MCB/AskAdil would appear in this list

**AskAdil as an ACAS Digital Gateway:**
- Explore whether ACAS would accept structured notifications from AskAdil
- Users would still need to provide their own details and consent
- AskAdil could pre-populate the notification with case details

---

## Technical Architecture (Tier 1)

Tier 1 requires minimal changes:

```
User conversation --> AskAdil RAG API
                          |
                    [Existing intake flow]
                          |
                    [New: /api/v1/generate-report endpoint]
                          |
                    Gemini generates structured summary
                    from conversation history
                          |
                    Returns formatted text to frontend
                          |
                    Frontend displays with copy buttons
```

**Backend changes:**
- New endpoint: `POST /api/v1/generate-report`
- Input: conversation_history, report_type (general/police/tell-mama/iru)
- Output: structured text formatted for the target form
- System prompt addition: report generation instructions

**Frontend changes:**
- New button in post-intake responses: "Generate Report Summary"
- Display formatted text with per-section copy buttons
- Organisation-specific formatting options

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Users treat AI-generated reports as complete | Reports may lack critical details | Clear disclaimer: "Review and edit before submitting" |
| Inaccurate incident summaries | Could harm user's case | AI generates from user's own words; user reviews before use |
| PII handling | GDPR liability | Tier 1-2 keep all data client-side; Tier 3+ requires DPAs |
| Organisation form changes | Guides become outdated | Version form guides, check quarterly |
| Users skip professional legal advice | Harm to case | Maintain "consult a solicitor" messaging throughout |
| Partner organisations reject integration | Wasted development effort | Start with Tier 1-2 (no partnership needed) |
| Users file ET1/ACAS without solicitor | Weak claims, missed deadlines | Solicitor-path cases always recommend solicitor first; never show ACAS/ET1 as self-service |
| Solicitor directory becomes outdated | Bad referrals | Partner with AML for maintained list; quarterly review |
| Liability for solicitor referrals | MCB liability if solicitor underperforms | Clear disclaimer: "AskAdil does not endorse or guarantee any solicitor" |

---

## Discussion Points for IRU Meeting

1. **Referral source field:** IRU form has a "Referral Source" field — can we agree that "AskAdil / Muslim Council of Britain" is an accepted referral source?

2. **Structured submission:** Would IRU accept structured incident reports via email (e.g., to a dedicated inbox) as an alternative to form submission?

3. **API access:** Does IRU have or plan to develop an API for receiving reports from third-party platforms?

4. **Data sharing:** What data does IRU need vs. want? Can we agree on a minimal data set for referrals?

5. **Case tracking:** If AskAdil refers a user to IRU, can the user receive a reference number for follow-up?

6. **Volume expectations:** Based on AskAdil usage, what report volume should IRU expect?

---

## Discussion Points for Other Partners

**Tell MAMA:**
- AskAdil as a digital Third Party Reporting Centre — is this possible?
- Structured email submissions vs. API integration
- Tell MAMA already accepts reports from partner organisations — what's the process?

**Police Scotland:**
- Can MCB/AskAdil apply to become a Third Party Reporting Centre?
- Would Police Scotland accept structured reports from a digital TPRC?

**Association of Muslim Lawyers (AML):**
- Would AML publish or share a searchable member directory by specialism and region?
- Would AML members accept referrals from AskAdil with structured case summaries?
- Could AML endorse AskAdil as a pre-consultation educational tool?
- Would AML co-brand a "Find a Muslim Discrimination Solicitor" feature?
- Can AML identify members who offer free initial consultations for discrimination cases?

**Muslim Lawyer UK / Muslim Solicitors:**
- Would these directories accept referral traffic from AskAdil?
- Can we get structured data (solicitor name, specialism, location, contact) for integration?
- Interest in a co-branded "AskAdil recommends" listing?

---

## GDPR & Data Protection Compliance

**Status:** Privacy notice drafted (`docs/privacy-notice.md`). Consent flow implemented in frontend. Outstanding actions below require MCB legal/DPO involvement.

### Current Technical Safeguards (Implemented)

| Safeguard | Status |
|-----------|--------|
| PII pass-through only (never persisted to disk/DB/logs) | Done |
| Explicit consent screen before report submission | Done |
| Cancel at any point during PII collection | Done |
| Data minimisation (only collect what police.uk requires) | Done |
| PII excluded from application logs | Done |
| Privacy notice drafted | Done (`docs/privacy-notice.md`) |
| Attribution on submissions ("Submitted via AskAdil") | Done |

### Outstanding Actions (MCB Legal/DPO Required)

| Action | Owner | Priority | Notes |
|--------|-------|----------|-------|
| **Review and publish privacy notice** | MCB Legal | Critical | Draft at `docs/privacy-notice.md`. Needs legal review, MCB contact details, and publication on askadil.org |
| **Data Protection Impact Assessment (DPIA)** | MCB DPO | Critical | Required because AskAdil processes special category data (religion) and hate crime reports. Template: ICO DPIA guidance at ico.org.uk |
| **Sign Railway DPA** | MCB Legal | High | Railway (hosting provider) is a data processor. Standard DPA available at railway.com/legal. MCB must sign as data controller. |
| **Register with ICO** | MCB DPO | High | If MCB is not already registered with the ICO as a data controller, this must be done. Fee applies. |
| **Data breach response plan** | MCB DPO | High | Document: who is notified, within 72 hours (ICO), affected users informed. Template at ico.org.uk |
| **Google Gemini DPA** | MCB Legal | Medium | User messages are sent to Google Gemini for AI processing. Review Google's data processing terms. |
| **Add privacy notice link to Chainlit UI** | Dev team | Medium | Link to published privacy notice in welcome message and consent screen |
| **Cookie notice** | MCB Legal | Low | AskAdil uses essential cookies only. Simple notice sufficient. |
| **Age verification consideration** | MCB Legal | Low | Privacy notice states not for under-13s. Consider whether a gate is needed. |

### Lawful Basis Summary

| Processing activity | Lawful basis | Special category basis |
|--------------------|--------------|-----------------------|
| Conversation (legal education) | Legitimate interest (Art 6.1.f) | Not applicable (no PII required) |
| Report submission (PII collection) | Explicit consent (Art 6.1.a) | Explicit consent (Art 9.2.a) + Substantial public interest (Art 9.2.g) |
| Image analysis | Legitimate interest (Art 6.1.f) | Explicit consent if images contain special category data |
| URL/content analysis | Legitimate interest (Art 6.1.f) | Not applicable |

### Image Evidence Relay (Roadmap)

When image upload to police forms is implemented, additional consent wording is required: *"Any images you shared in this conversation will be included as evidence in the report."* This must be added to the consent screen before image relay goes live.

---

## Recommended Next Steps

1. **Immediate (this sprint):** Implement Tier 1 — Incident Summary Generator (self-service path) + Solicitor Consultation Pack (solicitor path)
2. **Immediate:** Add Muslim solicitor directory links to the system prompt resource directory (muslimlawyer.co.uk, muslimsolicitors.co.uk)
3. **Immediate:** MCB Legal to review privacy notice (`docs/privacy-notice.md`) and publish on askadil.org
4. **Immediate:** MCB DPO to begin DPIA for hate crime report submission feature
5. **This sprint:** Sign Railway DPA and review Google Gemini data processing terms
6. **Next sprint:** Implement Tier 2 — Smart Form Guides for Police Scotland and Tell MAMA
7. **This quarter:** Schedule meetings with IRU, Tell MAMA, and AML to discuss Tier 3 partnerships
8. **Q3 2026:** Apply for TPRC status with Police Scotland and Tell MAMA
9. **Q3 2026:** Launch curated Muslim solicitor directory (with AML partnership)
10. **Q4 2026:** Begin Tier 3 implementation with first confirmed partner

---

## Appendix: Form Field Comparison Matrix

| Field | IRU | Tell MAMA | Police Scotland | ACAS | ET1 |
|-------|-----|-----------|----------------|------|-----|
| Name | Req | Req | Req | Req | Req |
| Email | Req | Req | Req | Req | Req |
| Phone | Req | Req | Req | Req | Opt |
| Address | - | - | Req | Req | Req |
| Incident Type | - | Req | Req (dropdown) | Req | Req |
| Description | Req | Req | Req (2000 char) | Req | Req |
| Date | Req | Opt | Req (free text) | - | Req |
| Location | Req | Req | Req (2000 char) | - | - |
| Victim/Witness | Req | Req | Req | - | - |
| Perpetrator Info | - | - | Req (2000 char) | - | Req |
| Police Contacted | Req | - | - | - | - |
| ACAS Certificate | - | - | - | - | Req |
| Demographics | Req | Opt | Opt (DOB) | - | - |
| Evidence/Files | - | Opt (5 files) | - | - | Opt |
| Consent | Req | - | Req (disclaimer) | - | - |

**Legend:** Req = Required, Opt = Optional, - = Not collected
