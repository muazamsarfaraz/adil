const docx = require("docx");
const fs = require("fs");
const path = require("path");

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  WidthType, AlignmentType, HeadingLevel, BorderStyle, TableOfContents,
  PageNumber, Header, Footer, ShadingType, VerticalAlign,
  PageBreak, Tab, TabStopPosition, TabStopType, convertInchesToTwip,
  LevelFormat, NumberFormat
} = docx;

const MCB_GREEN = "14532D";
const MCB_GREEN_LIGHT = "1E7A3F";
const WHITE = "FFFFFF";
const LIGHT_GREY = "F2F2F2";
const FONT = "Arial";

// Helper: create a styled paragraph
function p(text, options = {}) {
  const {
    bold = false, size = 22, heading, alignment, spacing, color,
    italic = false, font = FONT, pageBreak = false, bullet
  } = options;

  const config = {
    children: [
      new TextRun({
        text,
        bold,
        size,
        font,
        color: color || undefined,
        italics: italic,
      }),
    ],
    alignment: alignment || AlignmentType.LEFT,
    spacing: spacing || { after: 120 },
  };

  if (heading) config.heading = heading;
  if (pageBreak) config.pageBreakBefore = true;
  if (bullet) {
    config.bullet = { level: 0 };
  }

  return new Paragraph(config);
}

// Multi-run paragraph
function pMulti(runs, options = {}) {
  const { heading, alignment, spacing, pageBreak, bullet } = options;
  const config = {
    children: runs.map(r => new TextRun({
      text: r.text,
      bold: r.bold || false,
      size: r.size || 22,
      font: r.font || FONT,
      color: r.color || undefined,
      italics: r.italic || false,
      break: r.break ? 1 : undefined,
    })),
    alignment: alignment || AlignmentType.LEFT,
    spacing: spacing || { after: 120 },
  };
  if (heading) config.heading = heading;
  if (pageBreak) config.pageBreakBefore = true;
  if (bullet) config.bullet = { level: 0 };
  return new Paragraph(config);
}

// Bullet point
function bullet(text, level = 0) {
  return new Paragraph({
    children: [new TextRun({ text, size: 22, font: FONT })],
    bullet: { level },
    spacing: { after: 60 },
  });
}

// Empty paragraph
function empty() {
  return new Paragraph({ children: [], spacing: { after: 60 } });
}

// Table cell with text
function cell(text, options = {}) {
  const {
    bold = false, shading, width, color, size = 20, alignment,
    vAlign, colspan, rowspan, borders
  } = options;

  const config = {
    children: [
      new Paragraph({
        children: [new TextRun({ text, bold, size, font: FONT, color: color || undefined })],
        alignment: alignment || AlignmentType.LEFT,
        spacing: { before: 40, after: 40 },
      }),
    ],
    verticalAlign: vAlign || VerticalAlign.CENTER,
  };

  if (shading) {
    config.shading = { fill: shading, type: ShadingType.CLEAR };
  }
  if (width) {
    config.width = { size: width, type: WidthType.PERCENTAGE };
  }
  if (colspan) config.columnSpan = colspan;
  if (rowspan) config.rowSpan = rowspan;

  return new TableCell(config);
}

// Header row for tables
function headerRow(texts, widths) {
  return new TableRow({
    children: texts.map((t, i) =>
      cell(t, {
        bold: true,
        shading: MCB_GREEN,
        color: WHITE,
        width: widths ? widths[i] : undefined,
        alignment: AlignmentType.LEFT,
      })
    ),
    tableHeader: true,
  });
}

// Data row (alternating)
function dataRow(texts, index, widths) {
  const bg = index % 2 === 1 ? LIGHT_GREY : undefined;
  return new TableRow({
    children: texts.map((t, i) =>
      cell(t, {
        shading: bg,
        width: widths ? widths[i] : undefined,
      })
    ),
  });
}

// Create a professional table
function createTable(headers, rows, widths) {
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    rows: [
      headerRow(headers, widths),
      ...rows.map((r, i) => dataRow(r, i, widths)),
    ],
    borders: {
      top: { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" },
      bottom: { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" },
      left: { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" },
      right: { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" },
      insideVertical: { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" },
    },
  });
}

// Checkbox item
function checkbox(text, checked = false) {
  const mark = checked ? "[X]" : "[  ]";
  return new Paragraph({
    children: [
      new TextRun({ text: `${mark}  `, bold: true, size: 24, font: "Courier New" }),
      new TextRun({ text, size: 22, font: FONT }),
    ],
    spacing: { after: 120 },
    indent: { left: convertInchesToTwip(0.5) },
  });
}

// Signature line
function signatureLine(label) {
  return new Paragraph({
    children: [
      new TextRun({ text: `${label}: `, size: 22, font: FONT }),
      new TextRun({ text: "________________________________________", size: 22, font: FONT }),
      new TextRun({ text: "    Date: ", size: 22, font: FONT }),
      new TextRun({ text: "________________", size: 22, font: FONT }),
    ],
    spacing: { before: 240, after: 120 },
  });
}

// ============================================================
// BUILD DOCUMENT
// ============================================================

const doc = new Document({
  styles: {
    default: {
      document: {
        run: { font: FONT, size: 22 },
      },
      heading1: {
        run: { font: FONT, size: 32, bold: true, color: MCB_GREEN },
        paragraph: { spacing: { before: 360, after: 120 } },
      },
      heading2: {
        run: { font: FONT, size: 26, bold: true, color: MCB_GREEN },
        paragraph: { spacing: { before: 240, after: 120 } },
      },
      heading3: {
        run: { font: FONT, size: 24, bold: true, color: "333333" },
        paragraph: { spacing: { before: 200, after: 80 } },
      },
    },
  },
  features: {
    updateFields: true,
  },
  sections: [
    // ========== COVER PAGE ==========
    {
      properties: {
        page: {
          size: { width: convertInchesToTwip(8.5), height: convertInchesToTwip(11) },
          margin: {
            top: convertInchesToTwip(1),
            bottom: convertInchesToTwip(1),
            left: convertInchesToTwip(1),
            right: convertInchesToTwip(1),
          },
        },
      },
      headers: {
        default: new Header({
          children: [
            new Paragraph({
              children: [new TextRun({ text: "CONFIDENTIAL \u2014 MCB Internal", size: 16, font: FONT, color: "999999", italics: true })],
              alignment: AlignmentType.RIGHT,
            }),
          ],
        }),
      },
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              children: [
                new TextRun({ text: "AskAdil Solicitor Directory \u2014 Business Case  |  Page ", size: 16, font: FONT, color: "999999" }),
                new TextRun({ children: [PageNumber.CURRENT], size: 16, font: FONT, color: "999999" }),
                new TextRun({ text: " of ", size: 16, font: FONT, color: "999999" }),
                new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, font: FONT, color: "999999" }),
              ],
              alignment: AlignmentType.CENTER,
            }),
          ],
        }),
      },
      children: [
        empty(), empty(), empty(), empty(), empty(),
        // MCB branding
        new Paragraph({
          children: [new TextRun({ text: "Muslim Council of Britain", size: 36, font: FONT, bold: true, color: MCB_GREEN })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 60 },
        }),
        new Paragraph({
          children: [new TextRun({ text: "\u2501".repeat(40), size: 20, color: MCB_GREEN })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 400 },
        }),
        empty(), empty(),
        // Title
        new Paragraph({
          children: [new TextRun({ text: "AskAdil Solicitor Directory", size: 56, font: FONT, bold: true, color: MCB_GREEN })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 120 },
        }),
        new Paragraph({
          children: [new TextRun({ text: "Business Case & Decision Paper", size: 40, font: FONT, color: "333333" })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 240 },
        }),
        new Paragraph({
          children: [new TextRun({ text: "\u2501".repeat(30), size: 20, color: MCB_GREEN })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 240 },
        }),
        // Subtitle
        new Paragraph({
          children: [new TextRun({ text: "Decision Paper for MCB Executive Team", size: 28, font: FONT, italic: true, color: "555555" })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 600 },
        }),
        empty(), empty(), empty(),
        // Meta info
        new Paragraph({
          children: [
            new TextRun({ text: "Date: ", bold: true, size: 22, font: FONT }),
            new TextRun({ text: "March 2026", size: 22, font: FONT }),
          ],
          alignment: AlignmentType.CENTER,
          spacing: { after: 80 },
        }),
        new Paragraph({
          children: [
            new TextRun({ text: "Classification: ", bold: true, size: 22, font: FONT }),
            new TextRun({ text: "CONFIDENTIAL \u2014 MCB Internal", size: 22, font: FONT, color: "CC0000" }),
          ],
          alignment: AlignmentType.CENTER,
          spacing: { after: 80 },
        }),
        new Paragraph({
          children: [
            new TextRun({ text: "Prepared by: ", bold: true, size: 22, font: FONT }),
            new TextRun({ text: "AskAdil Team, MCB Digital", size: 22, font: FONT }),
          ],
          alignment: AlignmentType.CENTER,
          spacing: { after: 80 },
        }),
      ],
    },

    // ========== TABLE OF CONTENTS ==========
    {
      properties: {
        page: {
          size: { width: convertInchesToTwip(8.5), height: convertInchesToTwip(11) },
          margin: {
            top: convertInchesToTwip(1), bottom: convertInchesToTwip(1),
            left: convertInchesToTwip(1), right: convertInchesToTwip(1),
          },
        },
      },
      children: [
        p("Table of Contents", { heading: HeadingLevel.HEADING_1, size: 32, bold: true, color: MCB_GREEN }),
        new TableOfContents("Table of Contents", {
          hyperlink: true,
          headingStyleRange: "1-3",
        }),
        empty(),
        new Paragraph({
          children: [new TextRun({ text: "(Update this field in Word: right-click \u2192 Update Field \u2192 Update Entire Table)", size: 18, font: FONT, italics: true, color: "999999" })],
          spacing: { after: 120 },
        }),
      ],
    },

    // ========== MAIN CONTENT ==========
    {
      properties: {
        page: {
          size: { width: convertInchesToTwip(8.5), height: convertInchesToTwip(11) },
          margin: {
            top: convertInchesToTwip(1), bottom: convertInchesToTwip(1),
            left: convertInchesToTwip(1), right: convertInchesToTwip(1),
          },
        },
      },
      children: [
        // ========== 1. EXECUTIVE SUMMARY ==========
        p("1. Executive Summary", { heading: HeadingLevel.HEADING_1 }),
        new Paragraph({
          children: [new TextRun({
            text: "British Muslims currently have no reliable, centralised way to find Muslim-friendly legal help. This paper proposes that MCB launches the UK\u2019s first searchable directory of Muslim solicitors and legal professionals through its AskAdil platform, leveraging MCB\u2019s trusted brand and extensive community reach. The AskAdil team has already researched over 50 firms across key practice areas, built the core technology platform, and deployed the supporting infrastructure. We are now seeking executive sign-off to begin formal outreach to solicitors on behalf of MCB. The investment required is minimal \u2014 the technology is built, infrastructure is live, and the primary cost is staff time for email review. At maturity, the directory has the potential to generate \u00A3250\u2013350K per year in revenue while providing an essential community service that addresses a genuine, unmet need.",
            size: 22, font: FONT,
          })],
          spacing: { after: 200 },
        }),

        // ========== 2. BACKGROUND & PROBLEM STATEMENT ==========
        p("2. Background & Problem Statement", { heading: HeadingLevel.HEADING_1 }),
        p("The need for a dedicated Muslim solicitor directory is driven by several converging factors:", { spacing: { after: 160 } }),
        bullet("377% surge in Islamophobic hate crimes recorded between 2023 and 2024, creating unprecedented demand for legal support in the Muslim community."),
        bullet("45% of all religious hate crimes in the UK target Muslims, making them the most disproportionately affected faith group."),
        bullet("An estimated 12,000 Muslim solicitors practise in England and Wales, yet there is no dedicated directory or discovery mechanism to connect them with the community they serve."),
        bullet("Existing resources such as the Muslim Lawyers Directory and similar initiatives are dormant, outdated, or ineffective, leaving a significant gap."),
        bullet("Community members frequently ask AskAdil questions such as \u201CHow do I find a Muslim solicitor?\u201D or \u201CCan you recommend a lawyer who understands Islamic law?\u201D \u2014 demonstrating clear, organic demand."),
        bullet("Legal needs span multiple specialisms: Islamic family law (including Sharia divorce), Islamic wills and inheritance, halal conveyancing and Islamic finance, and discrimination/Islamophobia cases."),
        empty(),
        p("Without a centralised, trusted platform, Muslim individuals and families are left navigating a fragmented landscape at precisely the moment they need reliable legal support the most.", { italic: true, color: "555555" }),

        // ========== 3. PROPOSED SOLUTION ==========
        p("3. Proposed Solution", { heading: HeadingLevel.HEADING_1, pageBreak: true }),
        p("AskAdil will build and maintain the UK\u2019s first curated, searchable directory of Muslim solicitors and legal professionals, integrated directly into the AskAdil AI chatbot platform.", { spacing: { after: 160 } }),
        empty(),
        p("3.1 Core Features", { heading: HeadingLevel.HEADING_2 }),
        bullet("Curated directory of verified Muslim solicitors, searchable by specialism, location, and language."),
        bullet("AI-powered matching: AskAdil\u2019s chatbot intelligently matches users to the most relevant solicitors based on their legal need, geographic area, and language preference."),
        bullet("Consent-based onboarding: All solicitors are contacted via a professional outreach campaign and must explicitly opt in to be listed."),
        bullet("MCB ownership: MCB\u2019s direct ownership provides inherent trust and credibility that no third-party platform could replicate."),
        empty(),
        p("3.2 How It Works", { heading: HeadingLevel.HEADING_2 }),
        bullet("User asks AskAdil a legal question (e.g., \u201CI need help with an Islamic will\u201D)."),
        bullet("AskAdil provides general legal information and guidance from its knowledge base."),
        bullet("AskAdil recommends relevant solicitors from the directory, with profile summaries."),
        bullet("User contacts the solicitor directly (AskAdil facilitates the connection, not the legal advice)."),
        empty(),
        p("3.3 Outreach Approach", { heading: HeadingLevel.HEADING_2 }),
        bullet("AI-generated, human-reviewed personalised outreach emails sent via SendGrid."),
        bullet("Each email is tailored to the firm\u2019s specialism and explains MCB\u2019s AskAdil initiative."),
        bullet("Dry-run tested and validated \u2014 the outreach engine is built and ready for deployment."),
        bullet("Follow-up sequences for non-responders (max 2 follow-ups per firm)."),

        // ========== 4. REVENUE MODEL ==========
        p("4. Revenue Model & Financial Projections", { heading: HeadingLevel.HEADING_1, pageBreak: true }),
        p("The directory follows a phased monetisation strategy designed to build scale before introducing revenue streams.", { spacing: { after: 160 } }),
        empty(),
        p("4.1 Phased Growth Plan", { heading: HeadingLevel.HEADING_2 }),
        createTable(
          ["Phase", "Timeline", "Listed Firms", "Revenue", "Strategy"],
          [
            ["Free", "Now \u2013 Q3 2026", "25\u201350", "\u00A30", "Build scale and trust"],
            ["Freemium", "Q3 2026 \u2013 Q1 2027", "50\u2013150", "\u00A323K/yr", "Premium listings \u00A349\u2013149/mo"],
            ["Growth", "Q1 2027 \u2013 Q3 2027", "150\u2013400", "\u00A391K/yr", "Subscriptions + lead gen"],
            ["Maturity", "2028+", "1,000+", "\u00A3250\u2013350K/yr", "All revenue streams"],
          ],
          [15, 20, 15, 15, 35]
        ),
        empty(), empty(),
        p("4.2 Revenue Streams Breakdown (at Maturity)", { heading: HeadingLevel.HEADING_2 }),
        createTable(
          ["Revenue Stream", "% of Revenue", "Description"],
          [
            ["Premium Subscriptions", "45%", "Enhanced profiles, analytics dashboard, MCB Verified badge, priority placement"],
            ["Lead Generation", "25%", "\u00A35\u201325 per qualified enquiry passed to solicitors (excluding cases with a PI element \u2014 see section 7.1)"],
            ["Sponsored Content", "15%", "Sponsored articles, newsletter placements, featured practice area guides"],
            ["Events", "10%", "Webinars, community roadshows, annual Muslim Lawyers Conference"],
            ["Data & API", "5%", "Market intelligence reports, API licensing for third-party platforms"],
          ],
          [25, 15, 60]
        ),
        empty(),
        p("4.3 Revenue Scenarios (Sensitivity Analysis)", { heading: HeadingLevel.HEADING_2 }),
        p("The maturity-phase projection above represents the optimistic case. The following table presents three scenarios to give a more realistic range of outcomes.", { spacing: { after: 160 } }),
        createTable(
          ["Scenario", "Firms at Maturity", "Paid Conversion", "Annual Revenue"],
          [
            ["Conservative", "200 firms", "10% paying (20)", "\u00A324K/yr"],
            ["Base case", "500 firms", "15% paying (75)", "\u00A390K/yr"],
            ["Optimistic", "1,000 firms", "20% paying (200)", "\u00A3238K/yr"],
          ],
          [25, 25, 25, 25]
        ),
        empty(),
        p("Important context: The 12,000 Muslim solicitors are distributed across a much smaller number of firms. The total addressable market of firms with dedicated Islamic law desks is narrower than the headline number suggests. Not all 12,000 solicitors run independent practices, and many work in firms that would subscribe once, not per-solicitor.", { italic: true, color: "555555" }),
        empty(),
        p("Even the conservative case (\u00A324K/yr) covers operational costs. The base case (\u00A390K/yr) is self-sustaining and would fund further product development. The optimistic case remains achievable but depends on significant market penetration and successful monetisation of multiple revenue streams.", { italic: true, color: "555555" }),

        // ========== 5. KNOWN SOLICITORS ==========
        p("5. Known Solicitors & Legal Professionals", { heading: HeadingLevel.HEADING_1, pageBreak: true }),
        p("Our research has identified 50+ firms and organisations across four key practice areas, plus six support organisations. The following tables summarise the directory as currently researched.", { spacing: { after: 160 } }),
        empty(),

        // Islamic Family Law
        p("5.1 Islamic Family Law (15 firms)", { heading: HeadingLevel.HEADING_2 }),
        createTable(
          ["Firm Name", "Location", "Key Specialism", "Contact"],
          [
            ["Aramas Family Law", "Manchester", "Islamic divorce, custody", "Available"],
            ["Duncan Lewis", "London (national)", "Sharia divorce, family mediation", "Available"],
            ["gunnercooke (Siddique Patel)", "Manchester", "Islamic family law, arbitration", "Available"],
            ["Slater Heelis", "Manchester / Sale", "Family law, Islamic divorce", "Available"],
            ["Curtis Law", "Bradford", "Islamic family law, children matters", "Available"],
            ["O\u2019Donnell Solicitors", "London", "Sharia divorce, financial settlements", "Available"],
            ["Stowe Family Law", "National (multiple offices)", "High-net-worth Islamic divorce", "Available"],
            ["Irwin Mitchell", "National", "Family law, Islamic prenuptials", "Available"],
            ["Reeds Solicitors", "London", "Family law, forced marriage", "Available"],
            ["Witan Solicitors", "London / Midlands", "Islamic family law, custody", "Available"],
            ["Makin Dixon", "Birmingham", "Family law, Islamic divorce", "Available"],
            ["Fitz Solicitors", "London", "Family law, Sharia councils", "Available"],
            ["Paradigm Family Law", "National", "Islamic divorce, co-parenting", "Available"],
            ["Woolley & Co", "National (remote)", "Islamic family law", "Available"],
            ["Anthony Gold", "London", "Family law, cultural sensitivity", "Available"],
          ],
          [25, 25, 30, 20]
        ),
        empty(),

        // Islamic Wills & Inheritance
        p("5.2 Islamic Wills & Inheritance (12 firms)", { heading: HeadingLevel.HEADING_2, pageBreak: true }),
        createTable(
          ["Firm Name", "Location", "Key Specialism", "Contact"],
          [
            ["I Will Solicitors", "Birmingham", "Islamic wills, Sharia-compliant estates", "Available"],
            ["MWG Solicitors", "London", "Islamic wills, probate", "Available"],
            ["AM Law", "London", "Islamic inheritance, trust structures", "Available"],
            ["Aman Solicitors", "London / Birmingham", "Islamic wills, estate planning", "Available"],
            ["Farani Taylor", "London", "Islamic wills, immigration-linked estates", "Available"],
            ["Greystone Solicitors", "London", "Sharia-compliant wills, trusts", "Available"],
            ["YHM Solicitors", "Birmingham", "Islamic wills, probate", "Available"],
            ["Myerson Solicitors", "Manchester / Altrincham", "Private client, Islamic estate planning", "Available"],
            ["Oasis Legal", "London", "Islamic wills, Wasiyyah", "Available"],
            ["Greengate Solicitors", "Manchester", "Islamic wills, succession planning", "Available"],
            ["SA Law", "Hertfordshire", "Wills, trusts, Islamic compliance", "Available"],
            ["Nelsons Solicitors", "East Midlands", "Islamic wills, probate disputes", "Available"],
          ],
          [25, 25, 30, 20]
        ),
        empty(),

        // Islamic Finance & Conveyancing
        p("5.3 Islamic Finance & Conveyancing (14 firms)", { heading: HeadingLevel.HEADING_2, pageBreak: true }),
        createTable(
          ["Firm Name", "Location", "Key Specialism", "Contact"],
          [
            ["White Horse Solicitors", "London", "Islamic mortgages, halal conveyancing", "Available"],
            ["Batley Law", "West Yorkshire", "Islamic finance, conveyancing", "Available"],
            ["ASL Solicitors", "Birmingham", "Halal conveyancing, property", "Available"],
            ["Blakewater Certus", "Lancashire", "Islamic mortgage conveyancing", "Available"],
            ["AFG Law", "Bolton / Manchester", "Islamic finance, commercial property", "Available"],
            ["Kuddus Solicitors", "London", "Islamic mortgage, residential conveyancing", "Available"],
            ["Taylor Rose", "National", "Conveyancing, Islamic finance products", "Available"],
            ["Shakespeare Martineau", "National", "Islamic finance, Sukuk, commercial", "Available"],
            ["Touchwood Solicitors", "London", "Islamic conveyancing, buy-to-let", "Available"],
            ["Mullis & Peake", "Essex", "Conveyancing, Islamic mortgage products", "Available"],
            ["Foot Anstey", "South West / London", "Islamic finance, commercial property", "Available"],
            ["Charles Russell Speechlys", "London", "Islamic finance, Sukuk, Sharia advisory", "Available"],
            ["Trowers & Hamlins", "London / Middle East", "Islamic finance, real estate", "Available"],
            ["Dentons", "Global", "Islamic finance, capital markets", "Available"],
          ],
          [25, 25, 30, 20]
        ),
        empty(),

        // Discrimination & Islamophobia
        p("5.4 Discrimination & Islamophobia (12 firms)", { heading: HeadingLevel.HEADING_2, pageBreak: true }),
        createTable(
          ["Firm Name", "Location", "Key Specialism", "Contact"],
          [
            ["Rahman Lowe", "London", "Employment discrimination, Islamophobia", "Available"],
            ["Kesar & Co", "London", "Discrimination, hate crime", "Available"],
            ["Sharma Solicitors", "London", "Employment law, discrimination", "Available"],
            ["Gulbenkian Andonian", "London", "Human rights, discrimination", "Available"],
            ["Didlaw", "National (remote)", "Discrimination, whistleblowing", "Available"],
            ["Bindmans LLP", "London", "Human rights, civil liberties", "Available"],
            ["Mishcon de Reya", "London", "High-profile discrimination, human rights", "Available"],
            ["Bhatt Murphy", "London", "Civil liberties, police misconduct", "Available"],
            ["Landau Law", "London", "Employment discrimination, settlement", "Available"],
            ["Toner Legal", "National", "Hate crime, religious discrimination", "Available"],
            ["Slater + Gordon", "National", "Employment discrimination, group actions", "Available"],
            ["Leigh Day", "London", "Human rights, group litigation", "Available"],
          ],
          [25, 25, 30, 20]
        ),
        empty(),

        // Support Organisations
        p("5.5 Support Organisations (6)", { heading: HeadingLevel.HEADING_2 }),
        createTable(
          ["Organisation", "Focus Area", "Role in Directory", "Contact"],
          [
            ["Tell MAMA", "Anti-Muslim hate crime reporting", "Referral partner, case data", "Available"],
            ["Islamic Relief UK (IRU)", "Humanitarian, community welfare", "Community reach, promotion", "Available"],
            ["CAGE", "Due process, rule of law", "Legal rights advocacy", "Available"],
            ["Islamic Human Rights Commission (IHRC)", "Human rights, Islamophobia", "Research partner, referrals", "Available"],
            ["Muslim Safety Net", "Community safety, legal support", "Grassroots referral network", "Available"],
            ["Liberty", "Civil liberties, human rights", "Legal expertise, test cases", "Available"],
          ],
          [25, 25, 30, 20]
        ),

        // ========== 6. INVESTMENT REQUIRED ==========
        p("6. Investment Required", { heading: HeadingLevel.HEADING_1, pageBreak: true }),
        p("The core technology has been built and is operational. However, an honest assessment of total costs must include staff time, legal review, and ongoing management \u2014 not just infrastructure.", { spacing: { after: 160 } }),
        empty(),
        createTable(
          ["Item", "Cost", "Status"],
          [
            ["Technology (outreach engine)", "\u00A30", "Built and deployed"],
            ["Infrastructure (Railway hosting)", "~\u00A330/mo (~\u00A3360/yr)", "Live"],
            ["SendGrid (email)", "Free tier \u2192 \u00A315/mo at scale", "Configured"],
            ["LLM APIs (Gemini/Claude)", "~\u00A310\u201330/mo", "Configured"],
            ["External SRA legal review", "\u00A33,000\u20135,000 (one-off)", "Required before monetisation"],
            ["Staff time (6-week outreach)", "~\u00A31,500 (est. 3hrs/wk @ \u00A380/hr)", "Internal cost"],
            ["Ongoing management", "~\u00A32,400/yr (est. 2hrs/wk @ \u00A325/hr)", "GDPR, complaints, updates"],
            ["Total Year 1", "~\u00A37,000\u20139,000", ""],
            ["Ongoing (Year 2+)", "~\u00A33,500/yr", ""],
          ],
          [45, 30, 25]
        ),
        empty(),
        p("The \u00A3100 figure in the original estimate only covered raw infrastructure. The true Year 1 cost including SRA legal review and staff time is \u00A37,000\u20139,000. This is still minimal relative to the revenue potential and community impact. Even the conservative revenue scenario (\u00A324K/yr) comfortably exceeds ongoing costs from Year 2 onwards.", { italic: true }),

        // ========== 7. REGULATORY & LEGAL COMPLIANCE ==========
        p("7. Regulatory & Legal Compliance", { heading: HeadingLevel.HEADING_1, pageBreak: true }),
        p("The directory must comply with several regulatory frameworks. We have identified the key compliance requirements and proposed mitigations. This section is deliberately candid about risks \u2014 it is better to address them now than be surprised later.", { spacing: { after: 160 } }),
        empty(),
        p("7.1 SRA Referral Fee and Introducer Rules", { heading: HeadingLevel.HEADING_2 }),
        p("LASPO and PI Referral Fees:", { bold: true, spacing: { after: 80 } }),
        bullet("The Legal Aid, Sentencing and Punishment of Offenders Act 2012 (LASPO) prohibits referral fees in personal injury cases."),
        bullet("Our model does not charge referral fees for PI cases \u2014 lead generation fees apply only to non-PI practice areas."),
        empty(),
        p("SRA Codes of Conduct \u2014 Principles 3 & 7 (Introducer Obligations):", { bold: true, spacing: { after: 80 } }),
        bullet("ALL referral and lead-generation fees are regulated under SRA rules, not just Personal Injury. Principle 7 (legal and regulatory obligations) and Principle 3 (public trust) impose broad duties on solicitors receiving introductions."),
        bullet("Solicitors using AskAdil must inform their clients specifically about any financial arrangement with AskAdil as an introducer. This is a mandatory disclosure obligation under the SRA Standards and Regulations."),
        bullet("The \u00A35\u201325 lead generation fee must be disclosed to the end user, not simply labelled as a \u2018paid listing\u2019. Transparency is non-negotiable \u2014 the directory must make clear to users that some solicitors pay for referrals."),
        bullet("All solicitor listings will clearly disclose whether the listing is free or paid (premium), and the nature of any financial arrangement."),
        empty(),
        p("PI/Discrimination Boundary Risk:", { bold: true, spacing: { after: 80 } }),
        bullet("Hate crime and discrimination cases (a core AskAdil practice area) frequently involve claims for psychological injury. This blurs into Personal Injury, potentially triggering the LASPO referral fee ban."),
        bullet("The boundary between a \u2018discrimination case\u2019 and a \u2018personal injury case\u2019 is not always clear-cut. A claim for compensation for anxiety or PTSD arising from Islamophobic harassment could be classified as PI."),
        bullet("Mitigation: exclude ALL cases with any personal injury element from lead generation fees entirely. For discrimination-specialist firms, charge only for subscription/advertising \u2014 never per-lead."),
        bullet("Alternative approach: use a flat subscription model for discrimination firms, removing any per-referral fee and thereby avoiding the LASPO boundary question entirely."),
        p("This boundary risk is the single most important legal issue to resolve before monetisation. The external SRA legal review (budgeted at \u00A33,000\u20135,000 in section 6) must specifically address this question.", { italic: true, color: "555555", spacing: { after: 160 } }),
        empty(),
        p("7.2 GDPR Compliance", { heading: HeadingLevel.HEADING_2 }),
        bullet("All outreach is consent-based: solicitors must opt in to be listed."),
        bullet("Right to removal: any solicitor can request delisting at any time."),
        bullet("Privacy policy and data processing terms will be provided to all listed solicitors."),
        bullet("User data (enquiries) is processed in accordance with AskAdil\u2019s existing privacy policy."),
        empty(),
        p("7.3 Editorial Independence", { heading: HeadingLevel.HEADING_2 }),
        bullet("Payment for premium listings does not influence AI recommendations \u2014 matching is based on specialism, location, and user need."),
        bullet("Premium listings receive enhanced profiles and visibility, but do not receive preferential ranking in AI-generated recommendations."),
        bullet("Clear disclaimers state that AskAdil does not endorse, guarantee, or take responsibility for the quality of legal advice provided by listed solicitors."),

        // ========== 8. RISK ANALYSIS ==========
        p("8. Risk Analysis", { heading: HeadingLevel.HEADING_1, pageBreak: true }),
        createTable(
          ["Risk", "Likelihood", "Impact", "Mitigation"],
          [
            ["Low response rate from solicitors", "Medium", "Medium", "Outreach on MCB letterhead, AI-personalised emails, up to 2 follow-ups per firm"],
            ["Regulatory action (SRA)", "Low", "High", "External SRA legal review before monetisation; no PI referral fees; full disclosure per SRA Principles 3 & 7; mandatory client disclosure of introducer fees"],
            ["PI/Discrimination boundary", "Medium", "High", "Exclude cases with PI element from lead gen fees. Charge subscriptions only for discrimination firms. Seek specific SRA guidance on boundary cases."],
            ["Reputational damage to MCB", "Low", "High", "MCB oversight of all outreach communications; every email is human-reviewed before sending; dry-run tested; professional tone"],
            ["Data protection breach", "Low", "Medium", "GDPR-compliant architecture; consent-based listing; right to removal; encrypted data storage"],
            ["Competitor enters market", "Low", "Medium", "First-mover advantage; MCB\u2019s direct involvement provides unique trust signal; established community reach"],
            ["Revenue below projections", "Medium", "Low", "Free tier ensures community value regardless of commercial performance; low operating costs"],
          ],
          [22, 12, 12, 54]
        ),

        // ========== 9. STRATEGIC MODEL — HYBRID APPROACH ==========
        p("9. Strategic Model: Why a Hybrid Approach, Not Hate-Crime Only", { heading: HeadingLevel.HEADING_1, pageBreak: true }),
        p("A legitimate question for the executive team: should the directory focus exclusively on hate-crime and Islamophobia cases, given MCB\u2019s community mandate? This section explains why a hate-crime-only model would be counterproductive, and recommends a hybrid approach that serves victims while ensuring financial sustainability."),
        empty(),

        p("Why Hate-Crime Only Would Fail", { heading: HeadingLevel.HEADING_2 }),
        empty(),
        pMulti([
          { text: "1. It kills the revenue model. ", bold: true },
          { text: "Hate-crime victims typically lack funds for private fees \u2014 cases are handled via Legal Aid, pro bono, or No-Win-No-Fee. Law firms will pay \u00A325 for a lead on a high-value Islamic divorce or estate plan. They will not pay for distressed hate-crime enquiries. Restricting to hate-crime drops projected revenue to near zero." },
        ], { spacing: { after: 160 } }),
        pMulti([
          { text: "2. It maximises regulatory danger. ", bold: true },
          { text: "Hate-crime assaults frequently involve psychological trauma or physical injury claims, blurring into Personal Injury territory. Charging lead-generation fees on cases with a PI element risks regulatory breach under LASPO. By contrast, Islamic Wills and Halal Conveyancing leads are entirely legal and low-risk." },
        ], { spacing: { after: 160 } }),
        pMulti([
          { text: "3. It duplicates existing charity work. ", bold: true },
          { text: "Tell MAMA, the IRU, CAGE, and IHRC already handle hate-crime reporting, victim support, and legal referrals. A hate-crime-only directory would compete with MCB\u2019s own community partners rather than complement them. AskAdil\u2019s genuine first-mover advantage lies in everyday legal services." },
        ], { spacing: { after: 160 } }),
        pMulti([
          { text: "4. It ignores organic demand. ", bold: true },
          { text: "Community members ask AskAdil questions like \u201CHow do I find a Muslim solicitor?\u201D and \u201CCan you recommend a lawyer who understands Islamic law?\u201D The bulk of demand is for Islamic family law, wills, and finance \u2014 the intersection of British law and Sharia. Cutting these means ignoring what users actually need." },
        ], { spacing: { after: 240 } }),

        p("Recommended: Hybrid/Subsidised Model", { heading: HeadingLevel.HEADING_2 }),
        empty(),
        createTable(
          ["Commercial Tier (Revenue-Generating)", "Community Tier (Free Public Service)"],
          [
            ["Islamic Family Law & Divorce", "Discrimination & Hate Crime"],
            ["Islamic Wills & Inheritance", "Islamophobia cases"],
            ["Islamic Finance & Conveyancing", "Actions against police"],
            ["Employment Law", "Prevent programme cases"],
            ["Immigration", "Pro bono & Legal Aid referrals"],
            ["Monetised: Premium listings, lead gen fees, sponsored content", "Never monetised: No lead gen fees, no premium required"],
            ["Generates \u00A390\u2013238K/yr revenue", "Funded by commercial tier"],
          ],
          [50, 50]
        ),
        empty(),
        p("This model ensures MCB\u2019s directory serves both community need and financial sustainability. The hybrid approach neutralises the SRA/LASPO regulatory risk entirely, ensures the directory serves the community\u2019s actual day-to-day legal needs, and generates the revenue needed to sustain the service long-term. The commercial tier funds the community tier \u2014 a model proven by organisations like Citizens Advice and many Law Centres."),
        empty(),

        // ========== 10. RECOMMENDATION ==========
        p("10. Recommendation", { heading: HeadingLevel.HEADING_1, pageBreak: true }),
        empty(),
        pMulti([
          { text: "Recommendation: ", bold: true, size: 28, color: MCB_GREEN },
          { text: "GO", bold: true, size: 28, color: MCB_GREEN },
        ], { spacing: { after: 240 } }),
        p("We recommend proceeding with the AskAdil Solicitor Directory, subject to the following conditions:", { spacing: { after: 160 } }),
        empty(),
        pMulti([
          { text: "Condition 1: ", bold: true },
          { text: "All outreach emails are human-reviewed and approved before sending. No automated mass-emailing without oversight." },
        ], { spacing: { after: 120 } }),
        pMulti([
          { text: "Condition 2: ", bold: true },
          { text: "SRA compliance is reviewed by an external solicitor before the monetisation phase begins (prior to Q3 2026)." },
        ], { spacing: { after: 120 } }),
        pMulti([
          { text: "Condition 3: ", bold: true },
          { text: "Quarterly progress reports are provided to the MCB executive team, covering: directory growth, user engagement, solicitor feedback, and revenue progress." },
        ], { spacing: { after: 240 } }),
        empty(),
        p("The rationale for this recommendation is clear:", { bold: true, spacing: { after: 120 } }),
        bullet("The technology is built and tested \u2014 no further development investment is required."),
        bullet("The community need is demonstrable and urgent."),
        bullet("The financial risk is low (\u00A37,000\u20139,000 Year 1 including SRA legal review, ~\u00A33,500/yr ongoing)."),
        bullet("The revenue potential is significant (\u00A324K\u2013238K/year depending on scenario; base case \u00A390K/yr is self-sustaining)."),
        bullet("MCB is uniquely positioned to succeed where others have failed, due to its trust and reach."),
        bullet("Delay risks ceding first-mover advantage to commercial or less community-aligned competitors."),

        // ========== 11. DECISION REQUIRED ==========
        p("11. Decision Required", { heading: HeadingLevel.HEADING_1, pageBreak: true }),
        p("The MCB Executive Team is asked to approve the following two decisions:", { spacing: { after: 240 } }),
        empty(),

        p("Decision 1: Approve Outreach", { heading: HeadingLevel.HEADING_2 }),
        p("Authorise the AskAdil team to begin contacting 50 solicitor firms on behalf of MCB, using human-reviewed, personalised outreach emails.", { spacing: { after: 120 } }),
        empty(),
        checkbox("APPROVED \u2014 Authorise outreach to 50 solicitor firms on behalf of MCB"),
        empty(),
        checkbox("APPROVED WITH CONDITIONS \u2014 Proceed with the following modifications:"),
        new Paragraph({
          children: [new TextRun({ text: "Conditions: ___________________________________________________________________", size: 22, font: FONT, color: "999999" })],
          spacing: { after: 60 },
          indent: { left: convertInchesToTwip(0.7) },
        }),
        new Paragraph({
          children: [new TextRun({ text: "_____________________________________________________________________________", size: 22, font: FONT, color: "999999" })],
          spacing: { after: 120 },
          indent: { left: convertInchesToTwip(0.7) },
        }),
        empty(),
        checkbox("DEFERRED \u2014 Revisit at the next executive meeting"),
        empty(),
        checkbox("DECLINED \u2014 Do not proceed"),
        empty(), empty(),

        p("Decision 2: Promote via MCB Channels (Phase 2)", { heading: HeadingLevel.HEADING_2 }),
        p("Once 25+ firms are listed in the directory, share the directory with mosques and MCB newsletter subscribers to drive community adoption.", { spacing: { after: 120 } }),
        empty(),
        checkbox("APPROVED \u2014 Promote via MCB channels once 25+ firms are listed"),
        empty(),
        checkbox("APPROVED WITH CONDITIONS \u2014 Proceed with the following modifications:"),
        new Paragraph({
          children: [new TextRun({ text: "Conditions: ___________________________________________________________________", size: 22, font: FONT, color: "999999" })],
          spacing: { after: 60 },
          indent: { left: convertInchesToTwip(0.7) },
        }),
        new Paragraph({
          children: [new TextRun({ text: "_____________________________________________________________________________", size: 22, font: FONT, color: "999999" })],
          spacing: { after: 120 },
          indent: { left: convertInchesToTwip(0.7) },
        }),
        empty(),
        checkbox("DEFERRED \u2014 Revisit at the next executive meeting"),
        empty(),
        checkbox("DECLINED \u2014 Do not proceed"),
        empty(), empty(),
        // Signature lines
        new Paragraph({
          children: [new TextRun({ text: "\u2501".repeat(50), size: 16, color: "CCCCCC" })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 240 },
        }),
        signatureLine("Approved by"),
        signatureLine("Name & Title"),
        empty(), empty(),

        // ========== APPENDICES ==========
        p("Appendices", { heading: HeadingLevel.HEADING_1, pageBreak: true }),
        p("The following appendices are available as separate documents and can be provided upon request:", { spacing: { after: 200 } }),
        empty(),
        pMulti([
          { text: "Appendix A: ", bold: true },
          { text: "Full Solicitor Directory \u2014 solicitor-directory-comprehensive.json (machine-readable database of all researched firms, with full contact details, specialisms, and metadata)" },
        ], { spacing: { after: 120 } }),
        pMulti([
          { text: "Appendix B: ", bold: true },
          { text: "Monetisation Strategy Document \u2014 Detailed revenue model, pricing tiers, competitive analysis, and financial projections" },
        ], { spacing: { after: 120 } }),
        pMulti([
          { text: "Appendix C: ", bold: true },
          { text: "Outreach Email Templates \u2014 Sample personalised emails for each practice area, follow-up sequences, and response handling procedures" },
        ], { spacing: { after: 120 } }),
        pMulti([
          { text: "Appendix D: ", bold: true },
          { text: "Technical Architecture \u2014 Outreach engine design specification, API documentation, infrastructure diagram, and security architecture" },
        ], { spacing: { after: 120 } }),
        empty(), empty(),
        new Paragraph({
          children: [new TextRun({ text: "\u2501".repeat(50), size: 16, color: "CCCCCC" })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 120 },
        }),
        new Paragraph({
          children: [new TextRun({ text: "End of Document", size: 20, font: FONT, italics: true, color: "999999" })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 60 },
        }),
        new Paragraph({
          children: [new TextRun({ text: "CONFIDENTIAL \u2014 MCB Internal  |  AskAdil Solicitor Directory Business Case  |  March 2026", size: 16, font: FONT, color: "999999" })],
          alignment: AlignmentType.CENTER,
        }),
      ],
    },
  ],
});

// Generate the document
const outputPath = path.join(__dirname, "AskAdil-Solicitor-Directory-Business-Case.docx");
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outputPath, buffer);
  console.log(`Document generated successfully: ${outputPath}`);
  console.log(`File size: ${(buffer.length / 1024).toFixed(1)} KB`);
}).catch((err) => {
  console.error("Error generating document:", err);
  process.exit(1);
});
