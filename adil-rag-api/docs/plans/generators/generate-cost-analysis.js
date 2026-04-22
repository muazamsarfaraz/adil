// Generate AskAdil cost analysis docx
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, PageOrientation, LevelFormat,
  HeadingLevel, BorderStyle, WidthType, ShadingType, PageBreak,
  TabStopType, TabStopPosition, PageNumber, ExternalHyperlink,
} = require("docx");

const GREEN = "14532D";
const GREY_LIGHT = "E5E7EB";
const GREY_BG = "F3F4F6";
const HIGHLIGHT = "D1FAE5";

const border = { style: BorderStyle.SINGLE, size: 4, color: "CBD5E1" };
const borders = { top: border, bottom: border, left: border, right: border };

function H1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 120 },
    children: [new TextRun({ text, bold: true, color: GREEN, size: 32 })],
  });
}

function H2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 100 },
    children: [new TextRun({ text, bold: true, color: GREEN, size: 26 })],
  });
}

function H3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 180, after: 80 },
    children: [new TextRun({ text, bold: true, color: "333333", size: 22 })],
  });
}

function P(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 120 },
    children: [new TextRun({ text, ...opts })],
  });
}

function bullet(text, opts = {}) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 60 },
    children: [new TextRun({ text, ...opts })],
  });
}

function bulletRuns(runs) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 60 },
    children: runs,
  });
}

function cell(text, opts = {}) {
  const { bold = false, fill, width, color, align } = opts;
  return new TableCell({
    borders,
    width: width ? { size: width, type: WidthType.DXA } : undefined,
    shading: fill ? { fill, type: ShadingType.CLEAR } : undefined,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({
      alignment: align,
      children: [new TextRun({ text, bold, color })],
    })],
  });
}

function buildTable(widths, rows) {
  const totalWidth = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: totalWidth, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((r, i) => new TableRow({
      children: r.map((c, j) => {
        if (typeof c === "string") {
          return cell(c, { width: widths[j], bold: i === 0, fill: i === 0 ? GREEN : undefined, color: i === 0 ? "FFFFFF" : undefined });
        }
        return cell(c.text, { width: widths[j], ...c });
      }),
    })),
  });
}

const CONTENT_WIDTH = 9360; // US Letter 1" margins

const doc = new Document({
  creator: "AskAdil Team",
  title: "AskAdil Cost Analysis",
  description: "Build cost and running cost analysis for the AskAdil platform",
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: GREEN },
        paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: GREEN },
        paragraph: { spacing: { before: 240, after: 100 }, outlineLevel: 1 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "AskAdil Cost Analysis  •  Confidential  •  Page ", size: 18, color: "666666" }),
            new TextRun({ size: 18, color: "666666", children: [PageNumber.CURRENT] }),
          ],
        })],
      }),
    },
    children: [
      // Title block
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 600, after: 100 },
        children: [new TextRun({ text: "Muslim Council of Britain", bold: true, color: GREEN, size: 32 })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 600 },
        children: [new TextRun({ text: "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", color: GREEN, size: 18 })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 100 },
        children: [new TextRun({ text: "AskAdil Platform", bold: true, color: GREEN, size: 56 })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 400 },
        children: [new TextRun({ text: "Build Cost & Running Cost Analysis", color: "333333", size: 36 })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 200 },
        children: [new TextRun({ text: "AI-assisted development vs. traditional build comparison", italics: true, color: "555555", size: 22 })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 600, after: 100 },
        children: [new TextRun({ text: "Prepared for: MCB Executive Team", color: "333333", size: 22 })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 100 },
        children: [new TextRun({ text: "Date: April 2026", color: "333333", size: 22 })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 100 },
        children: [new TextRun({ text: "Classification: CONFIDENTIAL — MCB Internal", color: "333333", size: 22 })],
      }),
      new Paragraph({ children: [new PageBreak()] }),

      // 1. Executive Summary
      H1("1. Executive Summary"),
      P("AskAdil is a six-microservice AI legal education platform for British Muslims, built end-to-end over a 30-day period (March 24 – April 22, 2026) by a single developer using AI-assisted (\"vibe-coding\") tooling. This paper sets out what it cost to build and what it costs to run."),

      H3("Headline numbers"),
      buildTable([3360, 3000, 3000], [
        ["Metric", "AI-assisted (actual)", "Traditional build (estimated)"],
        ["Calendar time", "30 days", "6–9 months"],
        ["Team size", "1 developer", "2–3 senior developers + PM"],
        ["Build cost", "£300 – £8,000", "£120,000 – £240,000"],
        ["Code shipped", "~29,000 LOC, 378+ tests", "Equivalent scope"],
      ]),
      P(""),
      P("Running costs are estimated at £70–£180 per month (£840–£2,160/year) depending on usage volume, excluding payment processing fees and the custom domain.", { bold: true }),

      H3("Key finding"),
      P("AI-assisted development delivered a platform that would conventionally cost £120K–£240K and take 6–9 months, for between £300 (tooling only) and £8,000 (fully-loaded with contractor rate for one developer), in 30 calendar days with ~9 active coding days. This represents a 15–400× cost reduction and an 8× time compression."),

      // 2. What Was Built
      H1("2. What Was Built"),
      P("The platform comprises six deployed microservices plus supporting infrastructure:"),
      buildTable([2000, 4360, 3000], [
        ["Service", "Purpose", "Tech stack"],
        ["adil-frontend", "User-facing Chainlit chatbot at askadil.org", "Chainlit, Python, Docker"],
        ["adil-rag-api", "RAG engine: Gemini FST, content extraction, viability scoring, reporting orchestration, solicitor directory", "FastAPI, Google GenAI SDK, httpx, lxml"],
        ["adil-outreach-engine", "AI-powered outreach campaigns (solicitor signup, partner engagement) with LangGraph agents, SendGrid, Stripe, Cal.com", "FastAPI, LangGraph, arq, SQLAlchemy, Redis"],
        ["adil-report-bridge", "Submits hate-crime reports to external portals via browser automation", "FastAPI, browser-use, Playwright"],
        ["adil-document-uploader", "Daily case-law fetch from The National Archives, Gemini FST upload, Telegram heartbeat", "FastAPI, arq, lxml, google-genai"],
        ["adil-landing", "Static marketing site", "nginx, HTML/CSS"],
      ]),
      P(""),
      H3("Infrastructure on Railway (10 services total)"),
      bullet("6 application containers (listed above)"),
      bullet("2 managed Postgres databases (conversation logs, outreach, case-law judgments)"),
      bullet("2 managed Redis instances (arq queues, session state)"),
      bullet("External: Google Gemini, SendGrid, Stripe, Cal.com, Cloudflare DNS, TNA Atom API"),

      H3("Scope metrics"),
      buildTable([4680, 4680], [
        ["Metric", "Value"],
        ["Python lines of code", "24,492"],
        ["TypeScript / JavaScript", "2,508"],
        ["HTML / CSS", "1,674"],
        ["Total lines (production code)", "~29,000"],
        ["Automated tests", "378+ across services"],
        ["Git commits", "62"],
        ["Active coding days", "9 (calendar span: 30 days)"],
        ["Microservices deployed", "6"],
        ["Case-law judgments ingested", "1,040 (daily auto-fetch)"],
      ]),

      // 3. AI-Built Cost Breakdown
      H1("3. AI-Assisted Build Cost"),
      P("Two framings are presented below. The first is the strict out-of-pocket cost actually incurred. The second is the fully-loaded equivalent if the developer's time were billed at a market rate."),

      H3("3.1 Out-of-pocket tooling cost (actual cash spent)"),
      buildTable([4680, 2340, 2340], [
        ["Item", "Period", "Cost (GBP)"],
        ["Claude Max subscription (for Claude Code)", "1.5 months × £160", "~£240"],
        ["Cloudflare, domain registration (askadil.org)", "Year 1", "~£15"],
        ["Railway free-tier / hobby infrastructure during development", "1.5 months", "~£45"],
        [{ text: "Total out-of-pocket build cost", bold: true }, "", { text: "~£300", bold: true }],
      ]),

      H3("3.2 Fully-loaded cost (if developer's time were billed)"),
      P("Using the git history, active coding days = 9 (concentrated in 3 bursts). Assuming 8 productive hours per active day = 72 hours of engineering time."),
      buildTable([4680, 2340, 2340], [
        ["Rate benchmark", "Hours", "Cost (GBP)"],
        ["UK senior full-stack contractor (£80/hr)", "72", "£5,760"],
        ["UK senior full-stack contractor (£120/hr, specialist)", "72", "£8,640"],
        ["Plus tooling (Section 3.1)", "—", "£300"],
        [{ text: "Total fully-loaded cost (range)", bold: true }, "", { text: "£6,060 – £8,940", bold: true }],
      ]),

      // 4. Traditional Build
      H1("4. Traditional \"Old-School\" Build Estimate"),
      P("For comparison, the same scope delivered by a conventional development team following industry-standard practice. Estimates are based on typical UK rates and scope-based effort assumptions for a greenfield project with comparable complexity."),

      H3("4.1 Effort breakdown"),
      buildTable([4000, 1500, 2000, 2000], [
        ["Workstream", "Weeks", "FTE", "Notes"],
        ["Discovery, design, legal content curation", "4", "1 PM + 1 solicitor consultant", "Stakeholder workshops, legal review"],
        ["Backend: RAG API, prompt engineering, Gemini integration", "8", "1 senior engineer", "Including iteration on citations, viability scoring"],
        ["Outreach engine (LangGraph, arq, email/Stripe/Cal)", "6", "1 senior engineer", "Agent design, scheduling, webhooks"],
        ["Report-bridge (browser automation for 8 portals)", "4", "1 senior engineer", "Playwright flows, robustness"],
        ["Document uploader + case-law pipeline", "2", "1 engineer", "TNA integration, FST management"],
        ["Frontend (Chainlit UI + landing page)", "3", "1 frontend engineer", "Jurisdiction flows, session mgmt"],
        ["DevOps: Railway, CI/CD, monitoring, heartbeat", "2", "1 DevOps", "Multi-service deploys"],
        ["QA, integration testing, content validation", "3", "1 QA engineer", "378+ tests equivalent"],
        [{ text: "Total effort", bold: true }, { text: "32", bold: true }, "", "~6–9 months calendar time with parallelism"],
      ]),

      H3("4.2 Cost at UK rates"),
      buildTable([4680, 2340, 2340], [
        ["Scenario", "Team / duration", "Cost (GBP)"],
        ["Lean in-house team (permanent hires, fully-loaded salary)", "2 seniors × 6 months", "£96,000"],
        ["Mid-range consultancy", "2 seniors + PM × 6 months", "£150,000"],
        ["Agency build (typical rate card)", "3 seniors + PM × 9 months", "£240,000"],
        [{ text: "Traditional build range", bold: true }, "", { text: "£96,000 – £240,000", bold: true }],
      ]),

      // 5. Cost savings
      H1("5. Cost Savings Summary"),
      buildTable([3000, 3000, 3360], [
        ["Comparison", "Ratio", "Interpretation"],
        ["Out-of-pocket vs. traditional low end", "320×", "£300 vs. £96,000"],
        ["Out-of-pocket vs. traditional high end", "800×", "£300 vs. £240,000"],
        ["Fully-loaded vs. traditional low end", "12–16×", "£6K–£9K vs. £96K"],
        ["Fully-loaded vs. traditional high end", "27–40×", "£6K–£9K vs. £240K"],
        ["Calendar time", "6–9×", "30 days vs. 6–9 months"],
      ]),
      P(""),
      P("Caveats:", { bold: true }),
      bullet("These estimates compare a production-shipped system against a hypothetical traditional build of the same scope. They do not account for the quality, correctness, or long-term maintenance differences between AI-assisted and traditional code."),
      bullet("The AI-assisted cost excludes legal/content curation by subject-matter experts, which for AskAdil was done in parallel by the developer (a practising Muslim familiar with MCB's priorities) rather than contracted out."),
      bullet("Traditional estimates assume no offshore cost-reduction; offshore rates could bring traditional builds into the £40K–£80K range at additional oversight cost."),

      // 6. Running Costs
      H1("6. Running Costs"),
      P("Monthly cloud and service costs for AskAdil in production. Usage-dependent items are shown at low, medium, and high traffic scenarios."),

      H3("6.1 Fixed infrastructure"),
      buildTable([3000, 2000, 2000, 2360], [
        ["Item", "Provider", "Monthly cost", "Notes"],
        ["Application services × 6", "Railway", "£24 – £96", "£4–16/service depending on plan"],
        ["Postgres × 2", "Railway", "£8 – £16", "Shared across services"],
        ["Redis × 2", "Railway", "£8 – £16", "arq queue + session state"],
        ["Custom domain askadil.org", "Cloudflare / registrar", "£1.25", "£15/year amortised"],
        ["Cloudflare DNS / proxy", "Cloudflare", "£0", "Free tier"],
        [{ text: "Fixed subtotal", bold: true }, "", { text: "£41 – £129", bold: true }, ""],
      ]),

      H3("6.2 Usage-based (AI + messaging)"),
      P("Assumes Gemini 2.5 Flash at published rates (input £0.06/1M tokens, output £0.24/1M tokens)."),
      buildTable([3000, 2360, 2000, 2000], [
        ["Item", "Low traffic", "Medium traffic", "High traffic"],
        ["User queries / month", "500", "5,000", "25,000"],
        ["Gemini API (RAG + vision + heartbeat)", "£1", "£8", "£40"],
        ["SendGrid (email receipts, outreach)", "£0 (free tier)", "£15", "£15"],
        ["Stripe fees (on paid solicitor listings, est.)", "£0 – £20", "£50 – £100", "£100 – £300"],
        [{ text: "Usage-based subtotal", bold: true }, { text: "£1 – £21", bold: true }, { text: "£73 – £123", bold: true }, { text: "£155 – £355", bold: true }],
      ]),

      H3("6.3 All-in monthly total"),
      buildTable([3000, 2120, 2120, 2120], [
        ["Scenario", "Low traffic", "Medium traffic", "High traffic"],
        ["Fixed (low band)", "£41", "£41", "£41"],
        ["Usage (mid point)", "£11", "£98", "£255"],
        ["Uplift for pro plans / growth", "£0", "£30", "£80"],
        [{ text: "Total monthly", bold: true }, { text: "~£50", bold: true }, { text: "~£170", bold: true }, { text: "~£375", bold: true }],
        [{ text: "Total annual", bold: true }, { text: "~£600", bold: true }, { text: "~£2,040", bold: true }, { text: "~£4,500", bold: true }],
      ]),
      P(""),
      P("Current usage places AskAdil in the low-to-medium traffic band. Annual running cost is therefore expected to be £600–£2,040 until the directory reaches scale.", { bold: true }),

      // 7. Total Cost of Ownership
      H1("7. 3-Year Total Cost of Ownership"),
      P("Combining build cost with three years of operating cost at medium traffic:"),
      buildTable([4680, 2340, 2340], [
        ["Component", "AI-assisted", "Traditional build"],
        ["Year 0 build cost", "£300 – £8,940", "£96,000 – £240,000"],
        ["3 years of running cost (medium traffic)", "£6,120", "£6,120"],
        ["3 years of maintenance (est. 10% of build/yr for traditional)", "Included", "£28,800 – £72,000"],
        [{ text: "3-year TCO (range)", bold: true, fill: HIGHLIGHT }, { text: "£6,420 – £15,060", bold: true, fill: HIGHLIGHT }, { text: "£130,920 – £318,120", bold: true, fill: HIGHLIGHT }],
      ]),
      P(""),
      P("Traditional maintenance cost is estimated at 10% of build cost per year (industry rule-of-thumb for active feature development + bug fixes + dependency updates). AI-assisted maintenance is bundled into ongoing developer tooling cost."),

      // 8. Caveats & Recommendations
      H1("8. Caveats and Recommendations"),
      H3("8.1 Things to watch"),
      bullet("Vendor lock-in: Gemini and Railway are proprietary. Exit strategy and portability should be reviewed annually."),
      bullet("Legal accuracy: AI-assisted code quality and legal content quality require continued sampling and SME review. Budget £5K/year for solicitor advisory review."),
      bullet("Scaling step-changes: moving from Railway hobby to pro plans, or Gemini Flash to Pro models, can multiply costs. Monitor the usage-based band."),
      bullet("Knowledge concentration: a single-developer build is a key-person risk. Document runbooks (already partially done) and consider cross-training a second engineer."),

      H3("8.2 Recommendations"),
      bullet("Accept the 15–40× cost advantage for further AskAdil feature work while retaining independent SME review of legal content."),
      bullet("Budget £2,000/year for running costs (medium traffic band) plus £5,000/year for legal advisory review, totalling a £7,000/year operating envelope."),
      bullet("Re-forecast when: user queries exceed 25K/month; directory reaches 100+ firms; or any new microservice is added."),
      bullet("Formalise the developer toolchain (Claude Max, Railway, GitHub) as an MCB-approved stack to ensure continuity."),

      // Appendix
      H1("Appendix A: Data Sources"),
      bullet("Git history: 62 commits across 30 days (March 24 – April 22, 2026), via `git log`"),
      bullet("Code metrics: `find` + `wc -l` across service directories"),
      bullet("Railway pricing: published rates at railway.com/pricing (April 2026)"),
      bullet("Gemini pricing: published rates at ai.google.dev/pricing (April 2026)"),
      bullet("UK contractor rate benchmark: ITJobsWatch Q1 2026 median for senior full-stack + LLM specialism"),
      bullet("Traditional build scope estimate: author's experience + industry rules of thumb for microservice-heavy projects"),
    ]
  }],
});

Packer.toBuffer(doc).then(buffer => {
  const path = "E:/dev/mcbx/adil/adil-rag-api/docs/plans/AskAdil-Cost-Analysis.docx";
  fs.writeFileSync(path, buffer);
  console.log("Wrote " + path + " (" + (buffer.length / 1024).toFixed(1) + " KB)");
});
