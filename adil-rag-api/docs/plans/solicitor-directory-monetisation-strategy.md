# AskAdil Solicitor Directory: Monetisation Strategy

**Date:** 25 March 2026
**Status:** Draft — for discussion
**Related:** `2026-03-25-solicitor-directory-research-and-roadmap.md`

---

## 1. Context & Constraints

### What we're monetising
A curated directory of Muslim/Islamic-specialist solicitors, embedded within AskAdil's AI legal guidance chatbot. Users ask questions, get legal information, and are referred to appropriate solicitors when they need professional help.

### Regulatory constraints

**Referral fee ban (LASPO 2012, Sections 56-60):**
- [LASPO](https://www.sra.org.uk/solicitors/guidance/prohibition-of-referral-fees-in-laspo-56-60/) prohibits paying or receiving referral fees for personal injury and death claims
- For all other practice areas, referral arrangements are permitted but must be:
  - In writing
  - Disclosed to the client
  - Not detrimental to client interests
- The burden of proof falls on the regulated person to show a payment was not a referral fee

**What this means for AskAdil:**
- We **cannot** charge per-referral fees for personal injury work
- We **can** charge for advertising, enhanced listings, lead generation, and subscriptions in non-PI areas — provided arrangements are transparent and disclosed
- Any commercial arrangement must not influence which solicitors AskAdil recommends (editorial independence)
- All commercial relationships must be clearly labelled to users

### Community positioning
AskAdil is an MCB-affiliated community service. Monetisation must:
- Feel appropriate for a community/charity context
- Not compromise trust or perceived independence
- Prioritise user outcomes over revenue
- Be transparent about any commercial relationships

---

## 2. Market Benchmarks

### How legal directories make money

| Directory | Model | Revenue Indicators |
|-----------|-------|-------------------|
| **[Chambers & Partners](https://chambers.com/)** | Free rankings + paid enhanced profiles + advertising. Rankings are editorial; paid profiles are separate. | Sold for £400M to Abry Partners (2023) |
| **[Legal 500](https://www.legal500.com/)** | Free rankings + paid full profiles in directory. Non-paying firms shown in grey (de-emphasised). | Major revenue from profile upsells |
| **[Avvo](https://www.avvo.com/)** (US) | Freemium. Basic profile free. Revenue from sponsored listings on other lawyers' pages + "Avvo Pro" (blocks competitor ads on your page). | Traffic declining since 2018 (~500K/mo) |
| **[Justia](https://www.justia.com/)** (US) | Freemium. Gold/Platinum subscriptions for premium placement, competitor ad removal, enhanced features. | 4M+ monthly visitors |
| **[ReviewSolicitors](https://www.reviewsolicitors.co.uk/)** | Free listing + paid premium profiles + review management tools. | UK-specific, growing |
| **[SolicitorConnect](https://www.solicitorconnect.co.uk/)** | Enquiry-matching platform. Firms pay for leads. | Early-stage, low traction |

### Key lessons
1. **Free basic listings** are table stakes — firms expect free inclusion
2. **Enhanced profiles** are the primary revenue driver (not referral fees)
3. **Editorial independence** must be visibly separate from commercial relationships
4. **Traffic/audience** is the prerequisite — monetisation follows scale
5. **Community trust** is the moat — once lost, the directory dies

---

## 3. Monetisation Models

### Model A: Freemium Directory (Recommended)

```
FREE TIER                          PREMIUM TIER (£49-149/month)
─────────────────────────────      ─────────────────────────────
✓ Basic listing                    ✓ Everything in Free, plus:
  - Firm name                      ✓ Enhanced profile (photo, bio,
  - Address                          case studies, awards)
  - Phone number                   ✓ Priority placement in search
  - Practice areas                   results (labelled "Featured")
  - Link to website                ✓ Direct enquiry form (leads
                                     sent to firm's email)
                                   ✓ Analytics dashboard (views,
                                     clicks, enquiries)
                                   ✓ "MCB Verified" badge
                                   ✓ Review management tools
                                   ✓ Multilingual profile
                                   ✓ Firm logo display
```

**Why this model:**
- Low barrier to entry (free) builds directory scale quickly
- Premium is genuinely valuable (leads, visibility, trust signals)
- Clear separation between editorial (AskAdil chat recommendations based on fit) and commercial (enhanced visibility)
- SRA-compliant: payment is for advertising/profile services, not referrals

**Pricing tiers:**

| Tier | Price | Target |
|------|-------|--------|
| **Basic** | Free | All firms — builds scale |
| **Professional** | £49/month (£499/year) | Solo practitioners, boutique firms |
| **Premium** | £99/month (£999/year) | Mid-size firms wanting leads |
| **Enterprise** | £149/month (£1,499/year) | Multi-office firms, national coverage |

**Revenue projection (conservative):**

| Phase | Listed Firms | Paid Conversion | Avg Monthly Fee | Monthly Revenue | Annual Revenue |
|-------|-------------|-----------------|-----------------|-----------------|----------------|
| Phase 2 (mid-2026) | 50 | 10% (5 firms) | £75 | £375 | £4,500 |
| Phase 3 (late 2026) | 150 | 15% (23 firms) | £85 | £1,955 | £23,460 |
| Phase 4 (2027) | 400 | 20% (80 firms) | £95 | £7,600 | £91,200 |
| Mature (2028+) | 1,000 | 20% (200 firms) | £99 | £19,800 | £237,600 |

### Model B: Lead Generation

Firms pay per qualified enquiry routed through AskAdil.

```
User asks AskAdil about Islamic divorce in Manchester
→ AskAdil provides legal information
→ User says "Can you connect me with a solicitor?"
→ AskAdil sends enquiry to 2-3 matched firms
→ Firm pays £5-25 per enquiry received
```

**Pricing by practice area:**

| Practice Area | Price Per Lead | Rationale |
|---------------|---------------|-----------|
| Islamic Wills | £5-10 | Lower average case value |
| Islamic Finance/Conveyancing | £10-20 | Higher case value, competitive |
| Islamic Family Law/Divorce | £15-25 | High case value, urgent need |
| Employment Discrimination | £15-25 | High case value |
| Immigration | £10-15 | Medium case value |
| Personal Injury | **PROHIBITED** | LASPO ban on PI referral fees |

**Important:** This model requires:
- Written agreements with each firm
- Clear disclosure to users ("AskAdil may receive a fee from firms we connect you with")
- No influence on which firms are recommended (best-fit matching only)
- Exclusion of personal injury entirely

**Revenue projection:**

| Phase | Monthly Enquiries | Avg Fee | Monthly Revenue | Annual Revenue |
|-------|------------------|---------|-----------------|----------------|
| Phase 2 | 50 | £12 | £600 | £7,200 |
| Phase 3 | 200 | £15 | £3,000 | £36,000 |
| Phase 4 | 500 | £15 | £7,500 | £90,000 |
| Mature | 1,500 | £18 | £27,000 | £324,000 |

### Model C: Sponsored Content & Events

| Revenue Stream | Description | Estimated Revenue |
|----------------|-------------|-------------------|
| **Sponsored articles** | Firms sponsor educational content on AskAdil ("Understanding Mahr claims" sponsored by Aramas Family Law) | £200-500/article |
| **Webinars/CPD events** | AskAdil hosts online legal education events; firms sponsor or present | £500-2,000/event |
| **Mosque/community roadshows** | In-person legal clinics at MCB affiliates; firms pay to participate | £300-1,000/event |
| **Newsletter sponsorship** | Firms sponsor AskAdil's community newsletter | £100-300/edition |
| **Annual conference** | "Muslim Legal Services Summit" — firms exhibit, network, CPD | £5,000-15,000/event |

### Model D: Data & Insights (Future)

| Product | Description | Price |
|---------|-------------|-------|
| **Market reports** | "Islamic Legal Services in the UK 2027" — anonymised demand data, trends, geographic analysis | £500-2,000/report |
| **Firm analytics** | Detailed analytics for listed firms: what users search for, demand by area, competitor benchmarking | Included in Premium tier |
| **API access** | Other platforms (Islamic banks, mortgage brokers, estate agents) embed AskAdil solicitor search | £500-5,000/year |

---

## 4. Recommended Strategy: Phased Approach

### Phase 1: Free Only (Now — Q3 2026)
**Revenue: £0 — Focus on scale and trust**

- All listings free
- No commercial arrangements
- Build directory to 100+ firms
- Prove the referral model works (track enquiry volume, user satisfaction)
- Establish editorial credibility
- Gather data on which practice areas drive most demand

**Rationale:** Monetising too early kills community trust. The directory's value proposition to firms is "we send you clients" — prove that first.

### Phase 2: Freemium Launch (Q3 2026 — Q1 2027)
**Target revenue: £2,000-5,000/month**

- Introduce Premium tier (£49-99/month)
- Enhanced profiles, analytics dashboard, MCB Verified badge
- "Featured" placement clearly labelled
- AskAdil chat continues to recommend on best-fit, not payment
- Start sponsored content programme

**Key milestones before launching paid tier:**
- [ ] 100+ listed firms
- [ ] 200+ monthly referral enquiries
- [ ] At least 3 firms asking "how do we get more visibility?"
- [ ] User satisfaction >4/5 on referral quality

### Phase 3: Lead Generation + Events (Q1 2027 — Q3 2027)
**Target revenue: £5,000-10,000/month**

- Introduce pay-per-lead alongside subscriptions (firms choose model)
- Written agreements with SRA disclosure requirements
- Launch quarterly webinars / community events
- Begin mosque roadshow programme with MCB affiliates
- Pilot API access for Islamic finance institutions

### Phase 4: Full Platform (Q3 2027+)
**Target revenue: £15,000-25,000/month**

- All revenue streams active
- Data & insights products
- Annual conference
- API licensing
- Possible white-label for other community organisations

---

## 5. Revenue Mix at Maturity

```
Target: £250,000 - £350,000 annual revenue (2028+)

┌─────────────────────────────────────────────────────┐
│                                                      │
│  Premium Subscriptions    45%  ████████████████████   │
│  Lead Generation          25%  ███████████            │
│  Sponsored Content        15%  ██████                 │
│  Events & Conferences     10%  ████                   │
│  Data & API                5%  ██                     │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## 6. Pricing Rationale

### Why firms will pay

| Value Proposition | Detail |
|-------------------|--------|
| **Unique audience** | Only directory specifically serving the Muslim community via AI chatbot. No competitor exists. |
| **Qualified leads** | Users have already described their legal issue to AskAdil — firms receive pre-qualified enquiries, not cold traffic |
| **Trust signal** | MCB affiliation provides credibility that generic directories lack |
| **Community reach** | Access to MCB's network of 500+ affiliated mosques and organisations |
| **Low cost vs alternatives** | Google Ads for "Islamic divorce solicitor" costs £5-15/click. £99/month for unlimited visibility is compelling. |

### Competitive pricing comparison

| Platform | Cost to Law Firm | What They Get |
|----------|-----------------|---------------|
| Google Ads | £5-15 per click (£500-1,500/month typical) | Traffic, no pre-qualification |
| Legal 500 enhanced profile | ~£2,000-5,000/year | Prestige, no direct leads |
| ReviewSolicitors premium | ~£50-150/month | Reviews, some leads |
| SolicitorConnect | Per-lead fee | Very low volume currently |
| **AskAdil Professional** | **£49/month** | **Pre-qualified leads, MCB trust, unique audience** |
| **AskAdil Premium** | **£99/month** | **All above + analytics, badge, priority** |

---

## 7. SRA Compliance Framework

### What we can do

| Activity | SRA Status | Requirements |
|----------|-----------|--------------|
| Charge for enhanced profiles/advertising | Permitted | Clearly label paid content |
| Charge per lead (non-PI areas) | Permitted | Written agreement, client disclosure |
| Charge for sponsored content | Permitted | Label as sponsored |
| Charge for events/sponsorship | Permitted | Standard commercial terms |
| Accept referral fees for PI claims | **PROHIBITED** | LASPO ban — no exceptions |

### Compliance checklist

- [ ] All commercial arrangements in writing
- [ ] Client-facing disclosure: "Some solicitors listed on AskAdil have paid for enhanced visibility. This does not affect our recommendations, which are based on your needs."
- [ ] AskAdil chat recommendations based on best-fit matching (specialism, location, language), never payment status
- [ ] "Featured" or "Sponsored" labels on all paid placements
- [ ] PI leads never monetised
- [ ] Annual compliance review
- [ ] Legal review of all commercial terms before launch

### Separation of editorial and commercial

```
EDITORIAL (AskAdil chat)              COMMERCIAL (directory listings)
──────────────────────────            ──────────────────────────────
Recommends based on:                  Enhanced by payment:
• Practice area match                 • Profile completeness
• Geographic proximity                • "Featured" placement
• Language match                      • MCB Verified badge
• Free consultation availability      • Analytics access
• Legal aid availability              • Lead routing

NEVER influenced by payment.          Always labelled as paid.
```

---

## 8. Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Monetisation erodes community trust | Medium | High | Free tier always available. Editorial independence. Transparent labelling. Community advisory board. |
| SRA enforcement action | Low | High | Legal review before launch. Written agreements. PI exclusion. Annual compliance audit. |
| Low firm conversion to paid | Medium | Medium | Prove lead volume first. Start with very low pricing. Offer free trial periods. |
| Competitor enters market | Low | Medium | First-mover advantage. MCB affiliation is hard to replicate. Build network effects. |
| Firms game the system (fake reviews, etc.) | Medium | Medium | Moderation. Verified reviews only. Manual review of flagged content. |
| Revenue concentration (few large payers) | Medium | Low | Diverse revenue streams. Pricing accessible to solo practitioners. |

---

## 9. Alternative Considered: Fully Free / Donation-Based

**Option:** Keep the directory entirely free and fund via MCB grants, community donations, or zakat.

| Pros | Cons |
|------|------|
| Maximum trust | Not sustainable long-term |
| No SRA compliance complexity | Dependent on donor goodwill |
| Aligns with charitable mission | Cannot invest in growth/features |
| Simple to operate | No incentive for firms to keep profiles updated |

**Verdict:** A hybrid approach is better. The free tier preserves community trust while premium services create sustainable revenue. Many Islamic organisations successfully combine community service with commercial operations (e.g. Islamic banks, halal certification bodies).

---

## 10. Implementation Dependencies

| Dependency | Required For | Status |
|------------|-------------|--------|
| Directory reaches 100+ firms | Phase 2 (paid launch) | In progress (38 firms compiled) |
| 200+ monthly referral enquiries | Phase 2 (proves value to firms) | Not yet — need Phase 1 chat integration |
| Payment processing | Phase 2 | Stripe / GoCardless setup needed |
| Firm dashboard (profile management, analytics) | Phase 2 | To be built |
| SRA compliance legal review | Phase 2 | Needs external legal counsel |
| Lead routing infrastructure | Phase 3 | To be built |
| CRM for firm relationships | Phase 2 | To be selected |
| MCB endorsement of commercial model | Phase 2 | Needs MCB board discussion |

---

## 11. Key Decisions Needed

1. **MCB position on commercial directory:** Is MCB comfortable with AskAdil generating revenue from solicitor listings? What governance is needed?
2. **Pricing validation:** Should we survey the 38 compiled firms to test willingness to pay before setting prices?
3. **PI exclusion:** Confirm we will never monetise personal injury referrals (LASPO compliance)
4. **Editorial independence policy:** Formal written policy separating chat recommendations from commercial relationships
5. **Legal review:** Engage external solicitor to review the monetisation model against SRA rules before launch
6. **Charity vs commercial entity:** Does the directory operate under MCB's charitable status or as a separate commercial entity?

---

## Sources

- [SRA Referral Fees Guidance (LASPO)](https://www.sra.org.uk/solicitors/guidance/referral-fees-laspo-sra-principles/)
- [LASPO Sections 56-60 — Prohibition of Referral Fees](https://www.sra.org.uk/solicitors/guidance/prohibition-of-referral-fees-in-laspo-56-60/)
- [Chambers Revenue Model (Bloomberg Law)](https://news.bloomberglaw.com/business-and-practice/chambers-revenue-model-tests-law-firms-appetite-for-exposure)
- [Legal 500 FAQs](https://www.legal500.com/faqs/)
- [Avvo Business Model (Wikipedia)](https://en.wikipedia.org/wiki/Avvo)
- [Justia Directory Review 2026](https://growlaw.co/blog/justia-lawyer-directory)
- [UK Legal Services Market Report 2025 (PwC)](https://www.strategyand.pwc.com/uk/en/reports/uk-legal-services-market-report-2025.pdf)
- [SRA Code of Conduct for Solicitors](https://rules.sra.org.uk/solicitors/standards-regulations/code-conduct-solicitors/)
