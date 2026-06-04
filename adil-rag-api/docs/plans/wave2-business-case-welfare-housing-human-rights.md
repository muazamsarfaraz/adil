# AskAdil Wave 2 Business Case — Welfare, Housing & Human Rights

**Classification:** CONFIDENTIAL — MCB Internal
**Prepared for:** MCB Executive Team
**Prepared by:** AskAdil Team, MCB Digital
**Date:** May 2026
**Origin:** Practice-area expansion plan (LegalScraper `EXPANSION_PLAN.md`).
Parent / Wave 1 task: `869defau3`. This paper: ClickUp `869depba3`. Wave 3 filed separately.

---

## 1. Recommendation

**GO — approve Wave 2 in principle.**

Broaden the AskAdil solicitor directory beyond Wave 0/1 (Islamophobia, Family, Employment,
Immigration, Wills & Probate) to add three further bread-and-butter community legal areas:
**Welfare / Benefits**, **Landlord / Tenant (Housing)**, and **Human Rights**.

The data already exists, the directory filters are **already built and tested** (see §4), and the
outreach reuses Wave 1 infrastructure. The only genuinely new decisions for MCB are commercial and
editorial, not technical: authorise the ~250-email send, nominate an outreach owner, and confirm the
editorial stance on Prevent / Human Rights cases before that subset launches.

---

## 2. Why these three areas

All three are recurring legal needs where Muslim households are over-represented and under-served by
mainstream advice services:

- **Welfare / Benefits** — Universal Credit appeals, PIP refusals, housing-benefit disputes.
  Low-income communities and language barriers are over-represented; strong overlap with the
  demographic AskAdil already serves.
- **Landlord / Tenant (Housing)** — disrepair, illegal evictions, deposit disputes. Renters in
  Muslim-majority postcodes face the same housing stress as the wider population. Pairs naturally
  with welfare (same client, same week).
- **Human Rights** — Prevent referrals, citizenship deprivation, religious-freedom cases, Schedule 7
  stops. **The most distinctly Muslim-community-need area in the dataset outside Immigration.**

---

## 3. Dataset coverage — no new ingestion required

The records already live in `LegalScraper/data/directory.db` and the bundled
`adil-rag-api/docs/legalscraper_landing.json` export. No further scraping budget needed.

| Area | Total UK solicitors | Likely-Muslim | Muslim with email |
|---|--:|--:|--:|
| Welfare / Benefits | 186 | 30 | 28 |
| Landlord / Tenant – residential | 1,685 | 160 | 144 |
| Human Rights | 471 | 86 | 76 |
| **Wave 2 combined** | **2,342** | **276** | **248** |

*Source: LegalScraper directory.db, 2026-05-26.*

---

## 4. Engineering readiness — already wired

The three Wave 2 filters are **already implemented and merged** in `adil-rag-api`, so Item 1 of the
asks below ("wire the three new practice-area filters") carries **zero remaining build cost**.

- `solicitor_directory.py` → `PRACTICE_AREA_GROUPS` carries all three as `wave: 2` groups:
  **Welfare & Benefits**, **Housing**, **Human Rights**.
- Each group rolls up LegalScraper's fragmented raw SRA strings (e.g. *Housing* →
  `Landlord and tenant - residential` + `Landlord and tenant - commercial`; *Welfare & Benefits* →
  `Benefits and allowances`). This matters because a bare `area="housing"` substring search returns
  **zero** results — the raw data never uses the word "housing".
- `GET /api/v1/solicitors/search?area=<group label>` expands the label to its matchers.
- `GET /api/v1/solicitors/facets` returns the groups as wave-tagged `area_groups`, so the
  find-a-solicitor UI can render Wave 2 filter tiles the moment MCB approves surfacing them.

Live counts verified against the bundled export on 2026-05-26:

| Wave 2 group | Solicitors in directory |
|---|--:|
| Welfare & Benefits | 40 |
| Housing | 239 |
| Human Rights | 114 |

Covered by unit tests in `tests/test_solicitor_directory.py`
(`test_wave2_groups_present_and_searchable`, `test_housing_group_rolls_up_landlord_tenant`).

**What "approval" unlocks:** surfacing the Wave 2 tiles in the public find-a-solicitor UI and
authorising the outreach send. The backend is ready; this is a product/comms decision, not a sprint.

---

## 5. Outreach cost & plan

- ~250 emails for the narrow Muslim-only Wave 2 send (248 with verified email addresses).
- Same two-question template as Wave 1: free directory listing + sponsorship interest.
- Fits in a single 2-week window with no new infrastructure (reuses the Wave 1 outreach engine,
  consent schema, and landing-page export script).

---

## 6. Why MCB should say yes

1. **Zero data cost** — the dataset already exists; no further scraping budget needed.
2. **Zero build cost** — the directory filters are already wired and tested (§4).
3. **Shared infrastructure** — same outreach template, consent schema, and export script as Wave 1.
4. **Compounds the AskAdil brand** — moving from "Muslim family law + Islamophobia" to "broad
   community legal needs" repositions AskAdil as the default Muslim legal directory in the UK, not a
   narrow vertical.
5. **Synergy with existing referrals** — a Family Law user often also has a Housing or Welfare issue.
   Cross-referral within one trusted service beats three siloed services.

---

## 7. Sensitivity flags

- **Human Rights / Prevent is politically charged.** Outreach to those solicitors should include a
  sentence on AskAdil's editorial stance — e.g. *"we surface options, we don't take political
  positions on Prevent itself."* This subset warrants a short editorial review **before** launch.
- **Welfare and Housing carry no sensitivity flags** — pure consumer legal-aid territory; safe to
  launch alongside Wave 1.

---

## 8. Decisions required of MCB

```
[  ]  1. APPROVE Wave 2 in principle (the directory filters are already built —
         this authorises surfacing them in the public UI).

[  ]  2. APPROVE the ~250-email Muslim-only outreach send (public-register
         solicitors; same template as Wave 1; no PR/comms risk).

[  ]  3. NOMINATE an outreach owner:
         [  ] Same owner as Wave 1     [  ] Split per area

[  ]  4. CONFIRM the editorial position on Prevent / Human Rights cases before
         that subset launches (Welfare + Housing may launch without this).
```

Approved by: ______________________________   Date: ______________

---

*Backend wiring complete and tested. Welfare + Housing have no sensitivity flags and can launch on
approval; the Human Rights subset is gated on the editorial confirmation in Decision 4.*
