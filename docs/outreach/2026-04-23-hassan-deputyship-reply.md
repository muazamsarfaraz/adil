# Reply to br Hassan — Deputyship / Guardianship for Adults with Learning Disabilities

**Date:** 2026-04-23
**Context:** Hassan is asking MCB/Muazam to connect families with a Muslim family-law solicitor for an awareness resource on deputyship and guardianship for young adults with learning disabilities. He specifically mentions **MLegal** and **Shabina Begum at Goodman Ray** (https://www.goodmanray.com/our-team/partners/shabina-begum/).

This is not discrimination law — it's **Court of Protection** work under the **Mental Capacity Act 2005** (welfare deputyship + property & affairs deputyship). A new area of need that AskAdil does not currently cover.

---

## Suggested reply (ready to copy)

> Wa alaikum salaam br Hassan, hope you're well.
>
> This is an important gap — the Mental Capacity Act 2005 and Court of Protection route is complex, and I don't think there's a plain-English Muslim-community resource on it anywhere. Happy to help.
>
> On solicitor connections: **Shabina Begum at Goodman Ray** is a strong lead — she's a partner, does Court of Protection and welfare deputyship work, and has a solid reputation for vulnerable-client cases. Goodman Ray overall is known for children's law and mental capacity work, so they'd be a good fit. I'd approach her directly via the contact form on their site; happy to draft an introduction if useful.
>
> I'm less sure **MLegal** is the right firm for this specific need — their public profile is more family/divorce/Islamic finance than Court of Protection. I'd reach out but not depend on them.
>
> Two more I'd add to the shortlist:
>
> 1. **I Will Solicitors** (https://www.iwillsolicitors.com/) — they explicitly list deputyship and powers of attorney alongside Islamic wills, so they can handle the property & affairs side with cultural competence. Less clear on welfare deputyship.
> 2. **Duncan Lewis Solicitors** (https://www.duncanlewis.co.uk/) — large firm with a Court of Protection department and Islamic family law specialists; more likely to do pro-bono / fixed-fee community work at scale.
>
> On the resource: if it helps, I can put together a one-pager covering the practical side — *when do you need a deputyship order vs an LPA, the Court of Protection process, who pays, timelines, and what to do differently when learning disabilities mean the young adult can't grant an LPA themselves*. I can pair that with a plain-English explainer of the Mental Capacity Act's five principles. Happy to circulate a draft for your team to review.
>
> On AskAdil: this would be a natural extension for the platform. We currently cover discrimination and hate crime; we don't cover Court of Protection yet. If there's appetite, I'd scope adding a **Mental Capacity Act / deputyship** track — same question-and-citations interface, pointing families to the right form (COP1 / COP1A / COP3) and to vetted solicitors. Let me know if that's of interest and I'll put together a short proposal.
>
> Walaikum salaam,
> Muazam

---

## What I can do (if you want me to follow up)

### Immediate (this session or next)
1. **Add 1 firm to the solicitor directory** — Goodman Ray (Shabina Begum) with specialisms `court_of_protection`, `welfare_deputyship`, `mental_capacity`, `vulnerable_adults`. Needs 2 new specialism tags in the vocabulary.
2. **Flag I Will Solicitors** in the reply as the existing-directory option (only firm with `deputyship` + `powers_of_attorney` already listed).
3. **Draft an introduction email** to Shabina Begum — 1 paragraph, explains MCB + the resource purpose.

### Short-term (1–2 weeks)
4. **Create the plain-English resource** — one-page PDF covering:
   - Difference between LPA (capacity at time of signing required) and deputyship (for those who never had capacity)
   - Welfare deputyship vs property & affairs deputyship
   - The COP1 application process, timelines, fees, supervision
   - Five MCA principles
   - Islamic considerations (whether `wali` or Islamic guardianship concepts map onto legal deputyship — usually not, but worth addressing)
   - Who to contact (solicitor, Office of the Public Guardian, Court of Protection)
5. **Reach out to Shabina Begum** for a 30-min call to review the draft before publication; offer co-authorship.

### Medium-term (new AskAdil track)
5. **Alternative data sources for comprehensive directory** — the research flagged that no comprehensive "all Muslim lawyers" list is publicly obtainable. Alternatives to pursue:
   - **Law Society's "Find a Solicitor" directory** (solicitors.lawsociety.org.uk) — searchable but not filterable by religion/community; would need manual curation to extract Muslim partners
   - **LinkedIn** (filter by law firm + Muslim-community signals e.g. bar associations, alumni networks, verified practice areas) — requires either a data scraping workflow respecting LinkedIn ToS, or manual/semi-manual research
   - **Muslim community publications** (Muslim News, 5Pillars, The Muslim Vibe) — features & interviews often name Muslim solicitors in specific practice areas; ingest article archives + extract named professionals
   - Each of the above yields partial data only; the research concluded **no automated path produces a comprehensive list** — human-in-the-loop curation + direct outreach to umbrella networks (step 7 below) remains the most reliable approach
6. **Expand AskAdil's legal scope** to include Mental Capacity Act + Court of Protection.
   - Upload the MCA 2005, Code of Practice, relevant case law (Re D, Re MN, Cheshire West) to the Gemini FST store via `adil-document-uploader`
   - Add a new search domain: `mental_capacity_deputyship` → EWCOP (Court of Protection) court code on TNA
   - Add new intake-flow branch: if user mentions "learning disability" / "can't make decisions" / "deputyship" / "guardianship", route to MCA-aware system prompt section
   - Update the RAG system prompt with MCA fundamentals (five principles, best interests test, advance decisions)
7. **Add Court-of-Protection-specific solicitor filter** so users searching for this specialism get the right firms.

---

## Proposed email to Shabina Begum (if approved)

> Subject: Muslim Council of Britain — deputyship awareness resource
>
> Dear Ms Begum,
>
> I'm writing on behalf of the Muslim Council of Britain's digital legal tech initiative ("AskAdil", askadil.org — an AI legal education tool for British Muslims).
>
> We've been approached by community members with a concrete need: families with young adults who have learning disabilities are unaware of the Court of Protection deputyship process and the practical differences between LPAs, welfare deputyship, and property & affairs deputyship. There is no Muslim-community-facing plain-English resource on this.
>
> We'd like to produce one and would value your input. Specifically:
>
> 1. A 30-minute call to scope the content and review our draft for accuracy.
> 2. Optional: listing you / Goodman Ray on our solicitor directory as a Court of Protection referral.
> 3. Optional: co-authorship or acknowledgement on the final resource.
>
> No funding attached, but the resource will reach the MCB's network (mosques, community organisations, ~1,000+ monthly AskAdil users) with a clear solicitor-referral path.
>
> Is there a good week for a brief call?
>
> Walaikum salaam / Kind regards,
> Muazam Sarfaraz
> Lead Developer, AskAdil (MCB)
> muazam.sarfaraz@gmail.com
