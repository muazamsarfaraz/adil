# Wave 3 Business Case — Criminal Defence + Hate-Crime Victim Support

**Status:** 🔴 **AWAITING MCB SIGN-OFF** — do not begin outreach until the decisions below are recorded.
**Requested by:** `LegalScraper` (sibling project), 2026-05-26
**Owner:** AskAdil product + MCB executive
**Parent plan:** `EXPANSION_PLAN.md` (practice-area expansion) — ClickUp `869defau3`
**Wave tasks:** Wave 1 → `869defau3` · Wave 2 → filed alongside · **Wave 3 → `869depbaw` (this doc)**
**Sensitivity:** **Highest of the three waves.** Read in full before greenlighting.

---

## TL;DR / Recommendation

AskAdil should extend its solicitor directory to two genuine, under-served community needs:
**(1) Muslim defendants in criminal proceedings** and **(2) Muslim victims of Islamophobic hate
crime.** The data already supports it (the Wave-3 "Criminal Defence" directory group is live), the
incremental cost is ~£0 plus ~166 outreach emails, and the community need is well-evidenced
(Tell MAMA, CST).

**But Wave 3 carries reputational and editorial risk that Waves 1–2 do not** — chiefly around
listing solicitors who defend terrorism-related charges. This is a **strategic MCB decision, not an
operational one.** We recommend: **approve in principle, gate behind explicit editorial sign-off and
community-advisory framing review, and ship it last** — only after Wave 1 and Wave 2 have landed and
returned positive feedback.

---

## 1. Two distinct user funnels — both genuine community needs

### Funnel A — Muslim defendants in criminal proceedings
- Stop-and-search disputes
- Terrorism-related charges (TPIMs, control orders, Schedule 7 detentions)
- Pre-trial bail support, court representation

**Why distinct:** Muslim defendants statistically face higher stop-and-search rates and more
aggressive prosecution under terrorism legislation. They need a directory that surfaces solicitors
comfortable with those specific case types.

### Funnel B — Muslim victims of Islamophobic hate crime
- Reporting and pursuing prosecution
- Compensation claims (Criminal Injuries Compensation Authority)
- Civil claims against perpetrators where the criminal route fails

**Why distinct:** Tell MAMA UK and CST data both show hate-crime victims drop out of the justice
process at high rates because they don't know how to navigate it. A trusted directory helps them
stay in the process.

---

## 2. Coverage in the dataset

Source-of-truth cohort (LegalScraper SRA dataset):

| | Total UK | Likely-Muslim | Muslim with email |
|---|--:|--:|--:|
| Crime – general (covers **both** funnels) | 1,598 | 201 | **166** |

**Directory cross-check (AskAdil's bundled `legalscraper_landing.json`, 1,477 per-solicitor
records):** 294 records carry a `Crime - *` practice area and 183 carry a Criminal Litigation
accreditation — so the criminal cohort is already present and filterable in the live directory data.

**Important data reality — there is no distinct "hate crime" tag.** The SRA practice-area taxonomy
labels this work as `Crime - general`, `Crime - fraud`, `Crime - domestic violence`, etc., plus
`Criminal Litigation Accredited`. A search of the bundled index returns **0** solicitors with a raw
"hate crime" or "terror" area string. **This confirms the business-case framing:** hate-crime victim
support is *not* a separable specialism — it is served by the general criminal cohort, **cross-listed**
against:
- **Personal Injury** (340 records) — for civil compensation claims, and
- **Human Rights / Civil Liberties** (Wave 2 cohort) — for police-conduct complaints.

**Product consequence:** we should *not* manufacture a standalone "Hate Crime Support" filter tile —
it would be a permanently zero-count phantom. Instead the directory surfaces the criminal cohort and
**signposts** the PI / Human-Rights cross-listing in the hate-crime landing copy. (See §6.)

---

## 3. Why this needs MCB-level sign-off — not just product approval

Wave 3 raises questions Waves 1 and 2 do not:

- **Editorial position on terrorism legislation.** Does AskAdil list solicitors who routinely defend
  terrorism-related charges? Most major Muslim civil-society organisations say yes — legal defence
  is a right — but the *framing* in outreach and on the landing page matters enormously.
- **Press exposure risk.** A tabloid headline along the lines of *"Muslim charity refers terror
  suspects to lawyers"* is a real risk if framing is loose. Conversely, **not** offering the service
  signals that AskAdil treats Muslim defendants as second-class users. Both directions carry risk;
  doing nothing is not neutral.
- **Community-advisory input recommended.** Before any Wave 3 outreach goes out, MCB should consult
  2–3 community lawyers and 1–2 senior community representatives on framing.

---

## 4. Outreach plan (only if approved — currently HELD)

Same two-question template as Wave 1, with adapted framing:

> *"AskAdil is helping UK Muslims connect with criminal-defence and hate-crime-support solicitors.
> We've identified you from the SRA register as a criminal-law solicitor at [Firm]."*

- **Scope: ~166 emails** — the narrow Muslim-only Wave 3 send (the "Muslim with email" cohort).
- **Do NOT broaden** to all 1,598 UK criminal solicitors. An unfocused mass send multiplies PR-risk
  surface for no benefit.
- **Send is gated** behind every decision in §5 *and* behind Wave 1 + Wave 2 having landed with
  positive feedback (§7).

---

## 5. Asks of MCB — decisions to record

> Record each decision (Approved / Rejected / Amended) with a date and initials. Outreach cannot
> start until all five are resolved.

### Decision 1 — Editorial sign-off: list defence solicitors for terrorism-related cases
**Ask:** Yes / No. Strategic call. Does AskAdil list solicitors who defend terrorism-related
charges (TPIMs, control orders, Schedule 7)?
**Decision:** ☐ Approved ☐ Rejected ☐ Amended — _________________  (date / initials)

### Decision 2 — Approve the hate-crime victim-support angle
**Ask:** Confirm the hate-crime victim-support funnel (Funnel B). Almost-certainly low-controversy;
flag if MCB wants different framing.
**Decision:** ☐ Approved ☐ Rejected ☐ Amended — _________________  (date / initials)

### Decision 3 — Nominate community-advisory consultees
**Ask:** Name 2–3 community lawyers + 1–2 senior community representatives to review framing before
the send.
**Consultees:** ___________________________________________  (date / initials)

### Decision 4 — Confirm the editorial line for the landing page
**Ask:** Confirm the disclaimer that **listing ≠ endorsement** of any specific case or client, and
approve the hate-crime signposting copy (§6).
**Decision:** ☐ Approved ☐ Rejected ☐ Amended — _________________  (date / initials)

### Decision 5 — Confirm sequencing (hold Wave 3 last)
**Ask:** Confirm Wave 3 outreach is held until Wave 1 + Wave 2 are landed and positive feedback is
in. Don't lead with the most-sensitive area.
**Decision:** ☐ Confirmed ☐ Override — _________________  (date / initials)

---

## 6. Framing & landing-page guidance (for Decision 4)

The directory already returns this disclaimer with every response
(`DISCLAIMER` in `solicitor_directory.py`):

> *"AskAdil does not endorse or guarantee any solicitor. All firms listed are pending outreach —
> none have consented to be listed yet. Contact details are from publicly available sources only.
> Firm data includes information supplied by the Solicitors Regulation Authority."*

**Recommended Wave-3 additions to the landing copy (subject to MCB editorial sign-off):**

1. **Defence framing (Funnel A):** *"Everyone is entitled to legal representation. AskAdil lists
   criminal-defence solicitors as a public-information service. Listing a solicitor is not an
   endorsement of any client, charge, or outcome."*
2. **Hate-crime framing (Funnel B):** *"If you have experienced Islamophobic hate crime, these
   solicitors can help you report it, pursue prosecution, or claim compensation. For civil
   compensation see also Personal Injury; for police-conduct complaints see also Human Rights."*
   (This is the cross-listing signpost — there is no separate hate-crime filter; see §2.)
3. Keep the two funnels visually and editorially **separate** so defence framing never bleeds into
   victim-support framing.

---

## 7. Sequencing — why Wave 3 ships last

| Wave | Practice areas | Sensitivity | Gate |
|------|----------------|-------------|------|
| 1 | Immigration & Asylum; Wills, Probate & Inheritance | Low | landed first |
| 2 | Welfare & Benefits; Housing; Human Rights | Low–medium | after Wave 1 |
| **3** | **Criminal Defence; (+ hate-crime victim support)** | **High** | **after 1 + 2, + all §5 decisions** |

Leading with the most-sensitive area would put the riskiest framing in front of press and community
before the directory has an established, uncontroversial track record. Sequencing is a deliberate
risk-management choice.

---

## 8. Cost

- **Data:** £0 (cohort already in the dataset; directory group already shipped).
- **Outreach:** ~166 emails (existing outreach engine; marginal cost ≈ £0).
- **Community-advisory time:** ~4 hours for framing review (Decision 3 consultees).
- **Editorial / comms time:** landing-page copy for the two funnels (Decision 4 framing).

---

## 9. Implementation status & technical notes

**Already shipped (no action needed):**
- `PRACTICE_AREA_GROUPS` in `adil-rag-api/solicitor_directory.py` already contains
  `{"group": "Criminal Defence", "wave": 3, "matchers": ("crime", "criminal")}` plus the Wave-3
  `Personal Injury` group used for hate-crime civil-claim cross-listing.
- `/api/v1/solicitors/facets` already returns this group (with `wave` + `count`); the directory
  search already expands the `Criminal Defence` label to its raw SRA strings.

**Deliberately NOT done (respecting the sign-off gate):**
- **No standalone "Hate Crime Support" group** — it would be a zero-count phantom (§2). Hate-crime
  support is delivered via the criminal cohort + PI/Human-Rights cross-listing + landing copy.
- **No outreach campaign seeded.** When Decisions 1–5 are recorded, the ~166-contact Muslim-only
  criminal cohort is seeded through the existing outreach engine
  (`adil-outreach-engine/scripts/seed_solicitor_campaign.py` pattern), filtered to the
  `Crime - *` cohort with Muslim flag + email present. **Do not run before sign-off.**

---

## 10. Recommendation

**Approve in principle; gate on the five decisions in §5; ship last.** The community need is real and
the cost is negligible. The only material risk is editorial framing around terrorism defence — which
is exactly why this is an MCB decision and why we route it through community-advisory review before a
single email is sent.

---

*From LegalScraper, 2026-05-26. Companion to Wave 1 (`869defau3`) and Wave 2. Wave 3 is intentionally
the last to ship.*
