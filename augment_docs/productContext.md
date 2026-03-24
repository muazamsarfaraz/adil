# Product Context — Project Ad'l (UK)

## Executive Summary

Project Ad'l is a legal-tech platform tailored to the British Muslim experience, inspired by the ADL model and grounded in the **British Muslim Manifesto: Vision 2050**. It prioritises educational empowerment and internal resolution ("Educate First") before utilising a high-resource litigation network ("Litigate Second") to challenge Islamophobia and uphold the Rule of Law.

## Problems Solved

- British Muslims facing discrimination (employment, public services, online hate) lack accessible, culturally-sensitive legal guidance.
- Existing legal resources are generic, expensive, or litigation-first — discouraging early resolution.
- Community members often don't know their rights under UK equality and hate-crime legislation.
- No unified platform bridges digital self-help → community advocacy → professional litigation.

## User Personas

| Persona | Description | Primary Need |
|---------|-------------|--------------|
| **Employed Muslim** | Faces workplace discrimination (Ramadan, hijab, prayer breaks) | Know Your Rights brief + internal grievance template |
| **Online Abuse Victim** | Targeted by Islamophobic hate speech on social media | Online Safety Act guidance + evidence gathering checklist |
| **Community Advocate** | Mosque/community leader supporting members | Referral pathways, mediation guidance, hub booking |
| **Complex Case Claimant** | High-viability discrimination case needing legal representation | Viability assessment + solicitor matching (Find a Muslim Solicitor) |

## Strategic Pillars (Vision 2050 Alignment)

1. **Wafa bil 'Ahd (Rule of Law):** Framing justice as a service to the common good of the UK "shared home."
2. **Ilm (Knowledge & Evidence):** A high-integrity triage system that values verifiable evidence over blind following or hearsay.
3. **Pedagogical Triage:** Using the legal system as a tool for community mentorship rather than just a litigious hammer.

## The "Educate First" Workflow (Pedagogical Modules)

### Tier 1: Digital Empowerment (Immediate)
- **Tailored Info-Packets:** AI generates "Know Your Rights" briefs specific to the incident (e.g., "Rights of Muslim Employees during Ramadan", "The Online Safety Act and Social Media Abuse").
- **Self-Help Templates:** Automated "Internal Grievance Letters" or "Formal Requests for Evidence" (SARs) the user can send to their employer/service provider.

### Tier 2: Community Navigation (Human-in-the-Loop)
- **Advocacy Referral:** AI refers to community advocacy groups or local Citizens Advice Bureau (CAB) partners for systemic but not yet "litigation ready" issues.
- **Mediation Support:** Guidance on requesting a facilitated "Roundtable" or mediation session (Shura).

### Tier 3: In-Person "Ad'l Hubs" (Physical Support)
- **Local In-Person Chats:** Booking for "Safe Space Chat" with trained community advocate or pro bono solicitor at partner mosque/community centre.
- **"Sacred Spaces" Integration:** Mosques as "Beacons of Service" (Diyafa commitment) for physical support and moral accompaniment.

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| **FR1** | System MUST NOT recommend litigation as the first step. Must provide at least one educational/alternative resolution path before "Lawyer Matchmaker." | **Mandatory** |
| **FR2** | Managed RAG (Gemini FST) grounding sources must include Vento Guidelines (2025/26 update). | **Mandatory** |
| **FR3** | If evidence is insufficient, AI must provide a "Checklist for Success" advising what documentation to gather (Ilm Threshold). | **Mandatory** |
| **FR4** | System MUST be jurisdiction-aware across all four UK legal jurisdictions (England & Wales, Scotland, Northern Ireland, Wales-specific duties). | **Mandatory** |
| **FR5** | System MUST provide structured triage/escalation to human solicitors when case viability is high or user needs exceed educational scope. | **Mandatory** |
| **FR6** | System MUST maintain conversation context (multi-turn memory) within a session so users don't repeat themselves. | **Mandatory** |
| **FR7** | System MUST suggest contextual follow-up questions after each response to guide users through their rights. | **High** |

## Jurisdiction Handling (FR4)

The UK has four distinct legal jurisdictions. While core legislation (Equality Act 2010) applies across Great Britain, significant differences exist:

| Jurisdiction | Key Differences |
|-------------|----------------|
| **England & Wales** | Default jurisdiction. Equality Act 2010, Public Order Act 1986, Employment Tribunals. |
| **Scotland** | Separate court system (Court of Session, Sheriff Court). Employment law is UK-wide but civil remedies and procedures differ. Different hate crime legislation (Hate Crime and Public Order (Scotland) Act 2021). |
| **Northern Ireland** | Separate equality legislation in some areas. Fair Employment and Treatment (NI) Order 1998 provides additional religion/belief protections in employment. Different public order legislation. |
| **Wales** | Shares England & Wales jurisdiction but has different specific duties for public bodies under the Equality Act 2010 (Welsh-specific PSED regulations, Welsh Language Standards, Socio-economic Duty commenced in Wales). |

### Jurisdiction UX Flow
1. **Session start:** User selects jurisdiction via clickable buttons (🏴󠁧󠁢󠁥󠁮󠁧󠁿 England / 🏴󠁧󠁢󠁷󠁬󠁳󠁿 Wales / 🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland / 🇬🇧 Northern Ireland)
2. **Stored in session:** Jurisdiction persists for the entire conversation
3. **Prepended to queries:** Every API call includes jurisdiction context
4. **AI adjusts guidance:** Cites jurisdiction-specific legislation, courts, and procedures
5. **Honest limitations:** If RAG corpus lacks jurisdiction-specific sources, AI flags this transparently

### Knowledge Base Limitation
The current Gemini FST corpus is primarily England & Wales legislation and case law. For Scotland and NI, the AI provides correct general guidance (employment law is UK-wide) but may lack jurisdiction-specific case law. This should be flagged to users and addressed by expanding the FST corpus over time.

## Triage & Escalation Architecture (FR5)

### The Pedagogical Funnel (3-Tier Escalation)

AskAdil follows "Educate First, Litigate Second" through a structured triage:

#### Tier 1 — Self-Help (Digital Empowerment) ✅ *Current default*
- AI explains legal rights and relevant legislation
- Provides "Know Your Rights" briefs specific to the incident
- Generates self-help templates (grievance letters, SARs)
- Suggests alternative resolution (mediation, ACAS, formal complaints)

#### Tier 2 — Guided Escalation 🔧 *Next to implement*
When the AI detects a potentially viable case (viability scoring), it provides:
- **Viability Assessment:** Structured score (0-100) with Vento band estimation
- **Evidence Checklist:** What documentation to gather (FR3)
- **Escalation Card** with actionable links:
  - 📞 **ACAS Early Conciliation** — link + deadline warning (3 months minus 1 day)
  - 🔍 **Law Society Find a Solicitor** — filtered by discrimination law + user's jurisdiction
  - 🏛️ **Citizens Advice** — local bureau finder
  - 📋 **Template letters** — Letter Before Action, formal complaint templates

#### Tier 3 — Human Referral 📋 *Future — requires MCB infrastructure*
- **"Request Legal Review" button** — creates a case summary from the conversation
- Sends structured referral to MCB's legal partner network
- Requires: partner solicitor database, intake form, case management system
- Could integrate with existing MCB community support infrastructure

#### Reporting Integration (see roadmap PRD)
- **Self-service path:** Hate crime/Islamophobia reporting to Tell MAMA, IRU, Police Scotland, True Vision. AskAdil generates incident summary for copy-paste or (later) submits directly.
- **Solicitor path:** Workplace discrimination, compensation claims. AskAdil generates Solicitor Consultation Pack and helps find a Muslim solicitor.
- **Find a Muslim Solicitor:** Seed database of 24 firms researched (8 Muslim-community-focus). Outreach required before listing. Key partnership target: Association of Muslim Lawyers (AML).
- **4-tier roadmap:** Tier 1 (incident summary, no partnership), Tier 2 (form guides + solicitor directory), Tier 3 (referral partnerships), Tier 4 (Third Party Reporting Centre status).

### Triage Signals (When to Escalate)

| Signal | Detection Method | Escalation Level |
|--------|-----------------|-----------------|
| User explicitly asks about suing/compensation | Keyword matching | Tier 2 |
| Case has strong legal merit | AI viability scoring (structured output) | Tier 2 |
| Time limit approaching (3-month ET deadline) | AI detects dates in conversation | Tier 2 (urgent) |
| Multiple protected characteristics involved | AI analysis | Tier 2 |
| User requests human help | Explicit request | Tier 3 |
| Conversation depth > N exchanges on same topic | Session tracking | Tier 2 (suggest) |

### Viability Scoring (Ilm Threshold)

The AI evaluates three litigation ingredients:
1. **Statutory Footing** — Is there a clear legal basis? (e.g., s.13 EA 2010)
2. **Case Law Precedent** — Does supporting case law exist?
3. **Quantum Potential** — Are recoverable damages likely?

Score → Vento Band mapping:
- **0-30:** Low viability → Tier 1 (education + self-help)
- **31-60:** Medium viability → Tier 2 (guided escalation + evidence checklist)
- **61-100:** High viability → Tier 2 (strong escalation card) + flag for Tier 3

---

## Strategic Analysis: The "Ad'l" Philosophy

The alignment with **Vision 2050** shifts the focus from "victimhood" to "agency." By prioritising *Ilm* (Knowledge), Ad'l isn't just solving a legal problem — it is building a more legally literate community.

### Key Strengths of the Workflow

- **The Vento Grounding:** Referencing the **Vento Guidelines (2025/26)** ensures that if a case *does* move to litigation, the user has a realistic expectation of potential "Injury to Feelings" awards.
- **The "Shura" Mediation:** Introducing mediation as a "Tier 2" intervention aligns perfectly with the UK's **Pre-Action Protocols**, which encourage ADR (Alternative Dispute Resolution) before court proceedings.
- **Human-in-the-Loop:** Using mosques as "Ad'l Hubs" solves the "digital divide" and provides the moral support AI cannot offer.

## Recommended Enhancements

### Privacy & "Amanah" (Trust)
Since the platform handles sensitive legal data (Special Category Data under UK GDPR), the backend should utilise **End-to-End Encryption** for the "Evidence Vault" where users upload their documents.

### The "Vento Calculator"
A micro-feature within the Insight Portal that helps users estimate potential claim values based on current 2026 inflation-adjusted Vento bands.

### Language Support
While the focus is British Muslim, incorporating **Urdu, Arabic, and Bengali** LLM prompts for Tier 1 info-packets would increase accessibility for older generations or new arrivals.

## Technical Decision: No LangChain

The project deliberately uses the `google-genai` SDK directly rather than LangChain. Rationale:

1. **Gemini File Search Tool (FST):** The core RAG uses Gemini's native FST grounding — a proprietary feature that LangChain's wrappers don't natively support. Using LangChain would mean bypassing its abstractions anyway.
2. **Simple architecture:** The entire flow is one API call with system prompt + conversation history + file search tool. No multi-step chains, no agent routing, no tool orchestration.
3. **Smaller attack surface:** Fewer dependencies = less CVE exposure. Critical for a legal platform handling sensitive queries.
4. **Stability:** Direct SDK avoids LangChain's frequent breaking API changes between versions.
5. **Jurisdiction + triage + multi-turn:** All implementable with session state + prompt engineering + structured output — none require an orchestration framework.

**Reassess if:** The project needs multi-step agent reasoning, multiple LLM providers, or complex tool-calling chains. At that point, LangGraph (not LangChain) would be the appropriate choice.

---
*Updated: 2026-03-07 | Source: Project Ad'l PRD (2026-01-22) + Strategic Analysis + Reporting Integration Roadmap | Live: https://askadil.org*

