const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "AskAdil / MCB";
pres.title = "AskAdil Solicitor Directory - Pitch Deck";

// ── Brand colours ──
const C = {
  green900: "0D3B1E",
  green800: "14532D",
  green700: "166534",
  green600: "16A34A",
  green100: "DCFCE7",
  green50: "F0FDF4",
  gold700: "8B6914",
  gold600: "B8860B",
  gold500: "D4A843",
  gold400: "E5C76B",
  gold100: "FEF9E7",
  slate900: "0F172A",
  slate800: "1E293B",
  slate700: "334155",
  slate600: "475569",
  slate500: "64748B",
  slate300: "CBD5E1",
  slate200: "E2E8F0",
  slate100: "F1F5F9",
  white: "FFFFFF",
  bg: "FAFAF8",
};

const imgDir = path.resolve(__dirname, "../../../adil-landing/images");
const heroWorkplace = path.join(imgDir, "hero-concept-1-workplace.jpeg");
const heroCommunity = path.join(imgDir, "hero-concept-2-community.jpeg");
const heroPhone = path.join(imgDir, "hero-concept-3-phone.jpeg");

// Helper: fresh shadow each time (pptxgenjs mutates objects)
const cardShadow = () => ({
  type: "outer", color: "000000", blur: 6, offset: 2, angle: 135, opacity: 0.1,
});

// ════════════════════════════════════════════════════════════════
// SLIDE 1 — Title
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.green900 };

  // Subtle pattern overlay
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625,
    fill: { color: C.green800, transparency: 70 },
  });

  // Gold accent bar top
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.06,
    fill: { color: C.gold500 },
  });

  // Logo text
  s.addText("askadil.org", {
    x: 0.7, y: 0.4, w: 3, h: 0.4,
    fontSize: 14, fontFace: "Georgia", color: C.gold400,
    bold: true, margin: 0,
  });

  // Main title
  s.addText("Solicitor Directory", {
    x: 0.7, y: 1.4, w: 8, h: 1.2,
    fontSize: 44, fontFace: "Georgia", color: C.white,
    bold: true, margin: 0,
  });

  // Subtitle
  s.addText("Building the UK's first searchable directory\nof Muslim & Islamic-specialist solicitors", {
    x: 0.7, y: 2.7, w: 7, h: 0.9,
    fontSize: 18, fontFace: "Calibri", color: C.gold400,
    margin: 0,
  });

  // Tagline
  s.addText("Educate First, Litigate Second.", {
    x: 0.7, y: 3.9, w: 5, h: 0.5,
    fontSize: 14, fontFace: "Georgia", color: C.slate300,
    italic: true, margin: 0,
  });

  // Footer
  s.addText("An initiative in association with the Muslim Council of Britain", {
    x: 0.7, y: 4.9, w: 6, h: 0.4,
    fontSize: 10, fontFace: "Calibri", color: C.slate500,
    margin: 0,
  });

  // Date
  s.addText("March 2026", {
    x: 7.5, y: 4.9, w: 2, h: 0.4,
    fontSize: 10, fontFace: "Calibri", color: C.slate500,
    align: "right", margin: 0,
  });

  // Hero image on right
  s.addImage({
    path: heroWorkplace,
    x: 6.2, y: 0.8, w: 3.4, h: 2.3,
    rounding: true,
    transparency: 15,
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 2 — The Problem
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  // Section label
  s.addText("THE PROBLEM", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("No public, searchable Muslim\nlawyer directory exists in the UK.", {
    x: 0.7, y: 0.9, w: 8.5, h: 1.1,
    fontSize: 32, fontFace: "Georgia", color: C.green900,
    bold: true, margin: 0,
  });

  // Problem cards - row 1
  const problems = [
    { title: "Dormant sites", desc: "muslimlawyer.co.uk & muslimsolicitors.co.uk are the same entity — no named lawyers, no updates since 2019." },
    { title: "No public directories", desc: "AML, MLAG, and Muslim Lawyers' Hub are networks for lawyers, not directories for the public." },
    { title: "Matching platforms fail", desc: "SolicitorConnect claims 500+ specialists but only 11 firms are visible. Enquiry-based, not browsable." },
  ];

  problems.forEach((p, i) => {
    const x = 0.7 + i * 3.0;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.4, w: 2.7, h: 2.2,
      fill: { color: C.white },
      shadow: cardShadow(),
    });
    // Green top accent
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.4, w: 2.7, h: 0.05,
      fill: { color: C.green700 },
    });
    s.addText(p.title, {
      x: x + 0.2, y: 2.6, w: 2.3, h: 0.4,
      fontSize: 15, fontFace: "Calibri", color: C.green800,
      bold: true, margin: 0,
    });
    s.addText(p.desc, {
      x: x + 0.2, y: 3.1, w: 2.3, h: 1.3,
      fontSize: 11, fontFace: "Calibri", color: C.slate600,
      margin: 0,
    });
  });

  // Bottom stat
  s.addText("~12,000 Muslim solicitors practise in England & Wales (6% of profession) — but the public has no way to find them.", {
    x: 0.7, y: 4.9, w: 8.5, h: 0.4,
    fontSize: 11, fontFace: "Calibri", color: C.slate500,
    italic: true, margin: 0,
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 3 — The Opportunity (Big Stats)
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.green900 };

  s.addText("THE OPPORTUNITY", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold400,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("A first-mover advantage in an\nunserved market.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.9,
    fontSize: 28, fontFace: "Georgia", color: C.white,
    bold: true, margin: 0,
  });

  // Big stat cards
  const stats = [
    { num: "~12,000", label: "Muslim solicitors\nin England & Wales" },
    { num: "361", label: "Barristers\nself-identified as Muslim" },
    { num: "0", label: "Public searchable\ndirectories" },
    { num: "1st", label: "AskAdil would be\nfirst of its kind" },
  ];

  stats.forEach((st, i) => {
    const x = 0.7 + i * 2.3;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.2, w: 2.05, h: 2.0,
      fill: { color: C.green800 },
      shadow: cardShadow(),
    });
    s.addText(st.num, {
      x, y: 2.4, w: 2.05, h: 0.8,
      fontSize: 36, fontFace: "Georgia", color: C.gold400,
      bold: true, align: "center", margin: 0,
    });
    s.addText(st.label, {
      x, y: 3.2, w: 2.05, h: 0.8,
      fontSize: 12, fontFace: "Calibri", color: C.slate300,
      align: "center", margin: 0,
    });
  });

  s.addText("Sources: Law Society diversity data, Bar Council, CILEX", {
    x: 0.7, y: 4.9, w: 8, h: 0.3,
    fontSize: 9, fontFace: "Calibri", color: C.slate500,
    margin: 0,
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 4 — What We Audited
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  s.addText("RESEARCH AUDIT", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("We audited every Muslim lawyer\nresource in the UK.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.9,
    fontSize: 28, fontFace: "Georgia", color: C.green900,
    bold: true, margin: 0,
  });

  // Table of audit results
  const headerRow = [
    { text: "Resource", options: { fill: { color: C.green800 }, color: C.white, bold: true, fontSize: 11, fontFace: "Calibri" } },
    { text: "Type", options: { fill: { color: C.green800 }, color: C.white, bold: true, fontSize: 11, fontFace: "Calibri" } },
    { text: "Named Lawyers?", options: { fill: { color: C.green800 }, color: C.white, bold: true, fontSize: 11, fontFace: "Calibri" } },
    { text: "Status", options: { fill: { color: C.green800 }, color: C.white, bold: true, fontSize: 11, fontFace: "Calibri" } },
  ];

  const rowStyle = { fontSize: 10, fontFace: "Calibri", color: C.slate700 };
  const altFill = { fill: { color: C.slate100 } };
  const tableData = [
    headerRow,
    [
      { text: "Muslim Lawyer UK", options: rowStyle },
      { text: "Referral service", options: rowStyle },
      { text: "None", options: { ...rowStyle, color: "DC2626" } },
      { text: "Dormant (2019)", options: { ...rowStyle, color: "DC2626" } },
    ],
    [
      { text: "SolicitorConnect", options: { ...rowStyle, ...altFill } },
      { text: "Matching platform", options: { ...rowStyle, ...altFill } },
      { text: "11 firms only", options: { ...rowStyle, ...altFill, color: "D97706" } },
      { text: "Early-stage", options: { ...rowStyle, ...altFill, color: "D97706" } },
    ],
    [
      { text: "AML / MLAG / Hub", options: rowStyle },
      { text: "Professional networks", options: rowStyle },
      { text: "No public directory", options: { ...rowStyle, color: "DC2626" } },
      { text: "Active (networking)", options: rowStyle },
    ],
    [
      { text: "Duncan Lewis", options: { ...rowStyle, ...altFill } },
      { text: "Law firm dept", options: { ...rowStyle, ...altFill } },
      { text: "2 (may have left)", options: { ...rowStyle, ...altFill, color: "D97706" } },
      { text: "Page outdated", options: { ...rowStyle, ...altFill, color: "D97706" } },
    ],
    [
      { text: "Legal 500", options: rowStyle },
      { text: "Rankings", options: rowStyle },
      { text: "Finance only", options: { ...rowStyle, color: "D97706" } },
      { text: "Active (limited)", options: rowStyle },
    ],
  ];

  s.addTable(tableData, {
    x: 0.7, y: 2.0, w: 8.6,
    colW: [2.4, 2.0, 2.1, 2.1],
    border: { pt: 0.5, color: C.slate200 },
    rowH: [0.35, 0.35, 0.35, 0.35, 0.35, 0.35],
  });

  s.addText("Conclusion: The market is wide open. No competitor offers what AskAdil can build.", {
    x: 0.7, y: 4.5, w: 8.5, h: 0.4,
    fontSize: 13, fontFace: "Calibri", color: C.green800,
    bold: true, italic: true, margin: 0,
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 5 — What We've Compiled
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  s.addText("COMPILED DIRECTORY", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("38 firms with verified contact details.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.6,
    fontSize: 28, fontFace: "Georgia", color: C.green900,
    bold: true, margin: 0,
  });

  // Category cards
  const cats = [
    { num: "15", label: "Islamic Family\nLaw / Divorce", color: C.green800 },
    { num: "12", label: "Islamic Wills &\nInheritance", color: C.green700 },
    { num: "14", label: "Islamic Finance\n& Conveyancing", color: C.green600 },
    { num: "8", label: "Employment\nDiscrimination", color: C.gold700 },
    { num: "8", label: "Multi-service\nIslamic Law", color: C.gold600 },
  ];

  cats.forEach((c, i) => {
    const x = 0.5 + i * 1.85;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.8, w: 1.65, h: 1.8,
      fill: { color: C.white },
      shadow: cardShadow(),
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.8, w: 1.65, h: 0.05,
      fill: { color: c.color },
    });
    s.addText(c.num, {
      x, y: 2.0, w: 1.65, h: 0.7,
      fontSize: 32, fontFace: "Georgia", color: c.color,
      bold: true, align: "center", margin: 0,
    });
    s.addText(c.label, {
      x, y: 2.7, w: 1.65, h: 0.7,
      fontSize: 11, fontFace: "Calibri", color: C.slate600,
      align: "center", margin: 0,
    });
  });

  // Standout firms
  s.addText("Priority firms for outreach:", {
    x: 0.7, y: 3.9, w: 8, h: 0.35,
    fontSize: 13, fontFace: "Calibri", color: C.green800,
    bold: true, margin: 0,
  });

  s.addText([
    { text: "I Will Solicitors", options: { bold: true, breakLine: false } },
    { text: " (Islamic Wills leader)  |  ", options: { breakLine: false } },
    { text: "Aramas Family Law", options: { bold: true, breakLine: false } },
    { text: " (Chambers-ranked)  |  ", options: { breakLine: false } },
    { text: "White Horse Solicitors", options: { bold: true, breakLine: false } },
    { text: " (Islamic Finance)  |  ", options: { breakLine: false } },
    { text: "Kuddus Solicitors", options: { bold: true, breakLine: false } },
    { text: " (All HPP panels)  |  ", options: { breakLine: false } },
    { text: "Rahman Lowe", options: { bold: true, breakLine: false } },
    { text: " (Legal 500, discrimination)", options: {} },
  ], {
    x: 0.7, y: 4.3, w: 8.6, h: 0.6,
    fontSize: 11, fontFace: "Calibri", color: C.slate600,
    margin: 0,
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 6 — Geographic Coverage
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  s.addText("GEOGRAPHIC COVERAGE", {
    x: 0.7, y: 0.4, w: 4, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("Firms across every major\nMuslim population centre.", {
    x: 0.7, y: 0.9, w: 5, h: 0.9,
    fontSize: 28, fontFace: "Georgia", color: C.green900,
    bold: true, margin: 0,
  });

  // Region list — left column
  const regions = [
    { region: "London", count: "9 firms", firms: "Ascentim, White Horse, Kuddus, Duncan Lewis, Farani Taylor, Rahman Lowe" },
    { region: "Birmingham", count: "5 firms", firms: "I Will Solicitors, Aman, Touchwood, Witan, Duncan Lewis" },
    { region: "Manchester", count: "6 firms", firms: "Aramas, MWG, O'Donnell, ASL, Myerson, Reeds" },
    { region: "Yorkshire", count: "5 firms", firms: "Batley Law, Makin Dixon (10 offices), YHM, Slater Heelis" },
    { region: "Lancashire", count: "3 firms", firms: "Blakewater (Blackburn), Curtis Law, AFG Law (Bolton)" },
    { region: "Nationwide", count: "6 firms", firms: "Stowe, Irwin Mitchell, Reeds (22 offices), Taylor Rose, I Will" },
  ];

  regions.forEach((r, i) => {
    const y = 2.1 + i * 0.55;
    // Region tag
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.7, y, w: 1.5, h: 0.4,
      fill: { color: C.green800 },
    });
    s.addText(r.region, {
      x: 0.7, y, w: 1.5, h: 0.4,
      fontSize: 11, fontFace: "Calibri", color: C.white,
      bold: true, align: "center", valign: "middle", margin: 0,
    });
    // Count
    s.addText(r.count, {
      x: 2.4, y, w: 0.9, h: 0.4,
      fontSize: 11, fontFace: "Calibri", color: C.green700,
      bold: true, valign: "middle", margin: 0,
    });
    // Firms
    s.addText(r.firms, {
      x: 3.3, y, w: 6.2, h: 0.4,
      fontSize: 10, fontFace: "Calibri", color: C.slate600,
      valign: "middle", margin: 0,
    });
  });

  // Community image
  s.addImage({
    path: heroCommunity,
    x: 7.0, y: 0.5, w: 2.6, h: 1.5,
    rounding: true,
    transparency: 10,
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 7 — Islamophobia Legal Support
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.green900 };

  // Subtle pattern overlay
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625,
    fill: { color: C.green800, transparency: 70 },
  });

  // Gold accent bar top
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.06,
    fill: { color: C.gold500 },
  });

  s.addText("ISLAMOPHOBIA SUPPORT", {
    x: 0.7, y: 0.4, w: 4, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold400,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("Dedicated resources for\nanti-Muslim discrimination.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.9,
    fontSize: 28, fontFace: "Georgia", color: C.white,
    bold: true, margin: 0,
  });

  // Column 1 — First Contact
  const col1x = 0.5;
  s.addShape(pres.shapes.RECTANGLE, {
    x: col1x, y: 2.0, w: 2.9, h: 2.6,
    fill: { color: C.green800 },
    shadow: cardShadow(),
  });
  s.addText("First Contact", {
    x: col1x + 0.2, y: 2.15, w: 2.5, h: 0.35,
    fontSize: 14, fontFace: "Calibri", color: C.gold400,
    bold: true, margin: 0,
  });
  s.addText(
    "Tell MAMA: 0800 456 1226\nIRU: 020 3904 6555\nMuslim Safety Net: 0303 330 0288",
    {
      x: col1x + 0.2, y: 2.6, w: 2.5, h: 1.8,
      fontSize: 11, fontFace: "Calibri", color: C.slate300,
      margin: 0,
    }
  );

  // Column 2 — Specialist Solicitors
  const col2x = 3.6;
  s.addShape(pres.shapes.RECTANGLE, {
    x: col2x, y: 2.0, w: 2.9, h: 2.6,
    fill: { color: C.green800 },
    shadow: cardShadow(),
  });
  s.addText("Specialist Solicitors", {
    x: col2x + 0.2, y: 2.15, w: 2.5, h: 0.35,
    fontSize: 14, fontFace: "Calibri", color: C.gold400,
    bold: true, margin: 0,
  });
  s.addText(
    "Bindmans LLP (Prevent, hijab)\nRahman Lowe (Legal 500)\nKesar & Co (Legal Aid)\nMishcon de Reya (Tell MAMA lawyers)",
    {
      x: col2x + 0.2, y: 2.6, w: 2.5, h: 1.8,
      fontSize: 11, fontFace: "Calibri", color: C.slate300,
      margin: 0,
    }
  );

  // Column 3 — Key Barristers
  const col3x = 6.7;
  s.addShape(pres.shapes.RECTANGLE, {
    x: col3x, y: 2.0, w: 2.9, h: 2.6,
    fill: { color: C.green800 },
    shadow: cardShadow(),
  });
  s.addText("Key Barristers", {
    x: col3x + 0.2, y: 2.15, w: 2.5, h: 0.35,
    fontSize: 14, fontFace: "Calibri", color: C.gold400,
    bold: true, margin: 0,
  });
  s.addText(
    "Karon Monaghan KC (Matrix)\nImran Khan KC (Nexus)\nSchona Jolly KC (Matrix)",
    {
      x: col3x + 0.2, y: 2.6, w: 2.5, h: 1.8,
      fontSize: 11, fontFace: "Calibri", color: C.slate300,
      margin: 0,
    }
  );

  // Bottom stat bar
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 4.85, w: 10, h: 0.5,
    fill: { color: C.green800 },
  });
  s.addText(
    "377% surge in Islamophobia incidents (2023-24)  |  45% of all religious hate crimes target Muslims  |  Avg tribunal settlement: \u00A343,234",
    {
      x: 0.5, y: 4.85, w: 9.0, h: 0.5,
      fontSize: 10, fontFace: "Calibri", color: C.gold400,
      align: "center", valign: "middle", margin: 0,
    }
  );
}

// ════════════════════════════════════════════════════════════════
// SLIDE 8 — Islamophobia Referral Pathways
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  s.addText("REFERRAL PATHWAYS", {
    x: 0.7, y: 0.4, w: 4, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("Matching victims to the right support.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.6,
    fontSize: 28, fontFace: "Georgia", color: C.green900,
    bold: true, margin: 0,
  });

  // 6 referral cards in 2 rows of 3
  const referrals = [
    { scenario: "Hate Crime / Attack", referral: "Tell MAMA + Police + Saunders Law" },
    { scenario: "Workplace Discrimination", referral: "IRU + ACAS + Landau Law (no-win-no-fee)" },
    { scenario: "School / Hijab Issue", referral: "IRU + Mishcon de Reya" },
    { scenario: "Housing Discrimination", referral: "Shelter + Hodge Jones & Allen" },
    { scenario: "Police / State", referral: "Bhatt Murphy + DPG Law + EHRC" },
    { scenario: "Prevent / Counter-terror", referral: "CAGE + Bindmans + IHRC" },
  ];

  referrals.forEach((r, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.5 + col * 3.1;
    const y = 1.8 + row * 1.7;

    // Card background
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 2.85, h: 1.45,
      fill: { color: C.white },
      shadow: cardShadow(),
    });
    // Green top accent
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 2.85, h: 0.05,
      fill: { color: C.green700 },
    });
    // Scenario title
    s.addText(r.scenario, {
      x: x + 0.15, y: y + 0.15, w: 2.55, h: 0.4,
      fontSize: 13, fontFace: "Calibri", color: C.green800,
      bold: true, margin: 0,
    });
    // Arrow
    s.addText("\u2192", {
      x: x + 0.15, y: y + 0.55, w: 0.3, h: 0.3,
      fontSize: 14, fontFace: "Calibri", color: C.green600,
      margin: 0,
    });
    // Referral text
    s.addText(r.referral, {
      x: x + 0.45, y: y + 0.55, w: 2.25, h: 0.7,
      fontSize: 11, fontFace: "Calibri", color: C.slate600,
      margin: 0,
    });
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 9 — How It Works (Chat Flow)
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.green900 };

  s.addText("HOW IT WORKS", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold400,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("AI-powered referral through\nthe AskAdil chatbot.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.9,
    fontSize: 28, fontFace: "Georgia", color: C.white,
    bold: true, margin: 0,
  });

  // Flow steps
  const steps = [
    { step: "1", title: "User asks", desc: "\"I need help with\nIslamic divorce\nin Manchester\"" },
    { step: "2", title: "AskAdil matches", desc: "Specialism + Location\n+ Language\n+ Availability" },
    { step: "3", title: "Referral", desc: "Top 2-3 matched\nsolicitors with contact\ndetails & context" },
    { step: "4", title: "Follow-up", desc: "Track referral quality,\ncollect feedback,\nimprove matching" },
  ];

  steps.forEach((st, i) => {
    const x = 0.5 + i * 2.4;
    // Step number circle
    s.addShape(pres.shapes.OVAL, {
      x: x + 0.65, y: 2.1, w: 0.5, h: 0.5,
      fill: { color: C.gold500 },
    });
    s.addText(st.step, {
      x: x + 0.65, y: 2.1, w: 0.5, h: 0.5,
      fontSize: 18, fontFace: "Georgia", color: C.green900,
      bold: true, align: "center", valign: "middle", margin: 0,
    });
    // Title
    s.addText(st.title, {
      x, y: 2.8, w: 2.1, h: 0.4,
      fontSize: 15, fontFace: "Calibri", color: C.gold400,
      bold: true, align: "center", margin: 0,
    });
    // Description
    s.addText(st.desc, {
      x, y: 3.2, w: 2.1, h: 1.0,
      fontSize: 11, fontFace: "Calibri", color: C.slate300,
      align: "center", margin: 0,
    });

    // Arrow between steps
    if (i < 3) {
      s.addShape(pres.shapes.LINE, {
        x: x + 2.1, y: 2.35, w: 0.3, h: 0,
        line: { color: C.gold500, width: 2 },
      });
    }
  });

  // Phone image
  s.addImage({
    path: heroPhone,
    x: 6.8, y: 0.4, w: 2.8, h: 1.6,
    rounding: true,
    transparency: 20,
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 10 — Roadmap
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  s.addText("ROADMAP", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("Four phases to a comprehensive platform.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.6,
    fontSize: 28, fontFace: "Georgia", color: C.green900,
    bold: true, margin: 0,
  });

  const phases = [
    {
      phase: "Phase 1", period: "Now", title: "Manual Referral",
      items: "Embed 38 firms in RAG\nChat-based referrals\nDisclaimer copy",
      accent: C.green600,
    },
    {
      phase: "Phase 2", period: "Apr-Jun 2026", title: "Outreach & Consent",
      items: "Contact priority firms\nVerify details & consent\nEngage AML/MLAG/Hub",
      accent: C.green700,
    },
    {
      phase: "Phase 3", period: "Jun-Sep 2026", title: "Self-Registration & SRA",
      items: "\"List your practice\" portal\nSRA API integration\nName-matching outreach",
      accent: C.green800,
    },
    {
      phase: "Phase 4", period: "Sep 2026+", title: "Full Platform",
      items: "Search & filter UI\nReviews & ratings\nBarristers extension",
      accent: C.green900,
    },
  ];

  // Timeline line
  s.addShape(pres.shapes.LINE, {
    x: 0.7, y: 1.95, w: 8.6, h: 0,
    line: { color: C.slate300, width: 2 },
  });

  phases.forEach((p, i) => {
    const x = 0.5 + i * 2.3;

    // Timeline dot
    s.addShape(pres.shapes.OVAL, {
      x: x + 0.85, y: 1.82, w: 0.26, h: 0.26,
      fill: { color: p.accent },
    });

    // Card
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.3, w: 2.1, h: 2.8,
      fill: { color: C.white },
      shadow: cardShadow(),
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.3, w: 2.1, h: 0.05,
      fill: { color: p.accent },
    });

    // Phase label
    s.addText(p.phase, {
      x: x + 0.15, y: 2.45, w: 1.0, h: 0.3,
      fontSize: 10, fontFace: "Calibri", color: p.accent,
      bold: true, margin: 0,
    });
    s.addText(p.period, {
      x: x + 1.0, y: 2.45, w: 1.0, h: 0.3,
      fontSize: 9, fontFace: "Calibri", color: C.slate500,
      align: "right", margin: 0,
    });

    // Title
    s.addText(p.title, {
      x: x + 0.15, y: 2.8, w: 1.8, h: 0.4,
      fontSize: 13, fontFace: "Calibri", color: C.green900,
      bold: true, margin: 0,
    });

    // Items
    s.addText(p.items, {
      x: x + 0.15, y: 3.3, w: 1.8, h: 1.5,
      fontSize: 10, fontFace: "Calibri", color: C.slate600,
      margin: 0,
    });
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 11 — Monetisation Model
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  s.addText("MONETISATION", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("Freemium directory with\nmultiple revenue streams.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.9,
    fontSize: 28, fontFace: "Georgia", color: C.green900,
    bold: true, margin: 0,
  });

  // Free vs Premium comparison
  // Free card
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 2.1, w: 4.0, h: 3.0,
    fill: { color: C.white },
    shadow: cardShadow(),
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 2.1, w: 4.0, h: 0.5,
    fill: { color: C.slate700 },
  });
  s.addText("Free Tier", {
    x: 0.7, y: 2.1, w: 4.0, h: 0.5,
    fontSize: 16, fontFace: "Calibri", color: C.white,
    bold: true, align: "center", valign: "middle", margin: 0,
  });
  s.addText([
    { text: "Basic listing (name, address, phone)", options: { bullet: true, breakLine: true } },
    { text: "Practice areas shown", options: { bullet: true, breakLine: true } },
    { text: "Link to firm website", options: { bullet: true, breakLine: true } },
    { text: "Included in chat referrals", options: { bullet: true, breakLine: true } },
    { text: "Standard placement", options: { bullet: true } },
  ], {
    x: 1.0, y: 2.8, w: 3.4, h: 2.0,
    fontSize: 12, fontFace: "Calibri", color: C.slate700,
    paraSpaceAfter: 6,
  });

  // Premium card
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.3, y: 2.1, w: 4.0, h: 3.0,
    fill: { color: C.white },
    shadow: cardShadow(),
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.3, y: 2.1, w: 4.0, h: 0.5,
    fill: { color: C.green800 },
  });
  s.addText("Premium  £49-149/mo", {
    x: 5.3, y: 2.1, w: 4.0, h: 0.5,
    fontSize: 16, fontFace: "Calibri", color: C.gold400,
    bold: true, align: "center", valign: "middle", margin: 0,
  });
  s.addText([
    { text: "Enhanced profile (photo, bio, cases)", options: { bullet: true, breakLine: true } },
    { text: "Priority \"Featured\" placement", options: { bullet: true, breakLine: true } },
    { text: "Direct enquiry form (leads to email)", options: { bullet: true, breakLine: true } },
    { text: "Analytics dashboard (views, clicks)", options: { bullet: true, breakLine: true } },
    { text: "\"MCB Verified\" trust badge", options: { bullet: true, breakLine: true } },
    { text: "Review management tools", options: { bullet: true } },
  ], {
    x: 5.6, y: 2.8, w: 3.4, h: 2.0,
    fontSize: 12, fontFace: "Calibri", color: C.slate700,
    paraSpaceAfter: 4,
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 12 — Revenue Projections (Chart)
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  s.addText("REVENUE PROJECTIONS", {
    x: 0.7, y: 0.4, w: 4, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("Conservative growth to £237K annual revenue.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.6,
    fontSize: 28, fontFace: "Georgia", color: C.green900,
    bold: true, margin: 0,
  });

  // Bar chart — annual revenue by phase
  s.addChart(pres.charts.BAR, [
    {
      name: "Annual Revenue (£)",
      labels: ["Phase 2\n(Mid 2026)", "Phase 3\n(Late 2026)", "Phase 4\n(2027)", "Mature\n(2028+)"],
      values: [4500, 23460, 91200, 237600],
    },
  ], {
    x: 0.7, y: 1.7, w: 5.5, h: 3.5,
    barDir: "col",
    chartColors: [C.green700],
    chartArea: { fill: { color: C.white }, roundedCorners: true },
    catAxisLabelColor: C.slate600,
    catAxisLabelFontSize: 9,
    valAxisLabelColor: C.slate500,
    valAxisLabelFontSize: 9,
    valGridLine: { color: C.slate200, size: 0.5 },
    catGridLine: { style: "none" },
    showValue: true,
    dataLabelPosition: "outEnd",
    dataLabelColor: C.green900,
    dataLabelFontSize: 10,
    showLegend: false,
    valAxisNumFmt: "£#,##0",
  });

  // Key assumptions on right
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.6, y: 1.7, w: 3.0, h: 3.5,
    fill: { color: C.white },
    shadow: cardShadow(),
  });
  s.addText("Key Assumptions", {
    x: 6.8, y: 1.85, w: 2.6, h: 0.35,
    fontSize: 13, fontFace: "Calibri", color: C.green800,
    bold: true, margin: 0,
  });
  s.addText([
    { text: "20% paid conversion at maturity", options: { bullet: true, breakLine: true } },
    { text: "1,000 listed firms (of ~12K Muslim solicitors)", options: { bullet: true, breakLine: true } },
    { text: "£99/mo average premium fee", options: { bullet: true, breakLine: true } },
    { text: "Subscriptions only (excl. lead gen, events, data)", options: { bullet: true, breakLine: true } },
    { text: "Total addressable: £350K/yr with all streams", options: { bullet: true } },
  ], {
    x: 6.8, y: 2.3, w: 2.6, h: 2.5,
    fontSize: 10, fontFace: "Calibri", color: C.slate600,
    paraSpaceAfter: 6,
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 13 — Revenue Mix at Maturity (Pie)
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  s.addText("REVENUE MIX AT MATURITY", {
    x: 0.7, y: 0.4, w: 5, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("Target: £250-350K annual revenue (2028+)", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.6,
    fontSize: 28, fontFace: "Georgia", color: C.green900,
    bold: true, margin: 0,
  });

  // Pie chart
  s.addChart(pres.charts.DOUGHNUT, [
    {
      name: "Revenue",
      labels: ["Premium Subscriptions", "Lead Generation", "Sponsored Content", "Events & Conferences", "Data & API"],
      values: [45, 25, 15, 10, 5],
    },
  ], {
    x: 0.5, y: 1.6, w: 4.5, h: 3.5,
    chartColors: [C.green800, C.green600, C.gold600, C.gold400, C.slate500],
    showPercent: true,
    showLegend: true,
    legendPos: "b",
    legendFontSize: 10,
    legendColor: C.slate700,
    dataLabelColor: C.white,
    dataLabelFontSize: 11,
  });

  // Revenue stream details on right
  const streams = [
    { name: "Premium Subscriptions", pct: "45%", amt: "~£113K", desc: "£49-149/mo enhanced profiles" },
    { name: "Lead Generation", pct: "25%", amt: "~£63K", desc: "£5-25 per qualified enquiry" },
    { name: "Sponsored Content", pct: "15%", amt: "~£38K", desc: "Articles, newsletters, guides" },
    { name: "Events", pct: "10%", amt: "~£25K", desc: "Webinars, roadshows, conference" },
    { name: "Data & API", pct: "5%", amt: "~£13K", desc: "Market reports, API licensing" },
  ];

  streams.forEach((st, i) => {
    const y = 1.7 + i * 0.7;
    s.addText(st.pct, {
      x: 5.5, y, w: 0.6, h: 0.3,
      fontSize: 14, fontFace: "Georgia", color: C.green800,
      bold: true, margin: 0,
    });
    s.addText(st.name, {
      x: 6.2, y, w: 2.5, h: 0.3,
      fontSize: 12, fontFace: "Calibri", color: C.slate800,
      bold: true, margin: 0,
    });
    s.addText(st.amt + "  —  " + st.desc, {
      x: 6.2, y: y + 0.28, w: 3.3, h: 0.3,
      fontSize: 10, fontFace: "Calibri", color: C.slate500,
      margin: 0,
    });
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 14 — Why Firms Will Pay
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.green900 };

  s.addText("VALUE PROPOSITION", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold400,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("Why solicitors will pay to be\non AskAdil.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.9,
    fontSize: 28, fontFace: "Georgia", color: C.white,
    bold: true, margin: 0,
  });

  const props = [
    { title: "Unique Audience", desc: "The only directory specifically serving British Muslims via AI chatbot. No competitor exists." },
    { title: "Pre-qualified Leads", desc: "Users have already described their legal issue. Firms get warm, contextual enquiries — not cold clicks." },
    { title: "MCB Trust Signal", desc: "Association with the Muslim Council of Britain provides credibility no generic directory can match." },
    { title: "Community Reach", desc: "Access to MCB's network of 500+ affiliated mosques and community organisations." },
    { title: "10x Cheaper than Google", desc: "Google Ads cost £5-15 per click (£500-1,500/mo). AskAdil Premium is £99/mo for unlimited visibility." },
    { title: "Growing Market", desc: "Muslim solicitors grew from 5% to 6% of profession. Community demand for culturally-aware legal help is rising." },
  ];

  props.forEach((p, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.5 + col * 3.1;
    const y = 2.1 + row * 1.6;

    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 2.85, h: 1.35,
      fill: { color: C.green800 },
    });
    s.addText(p.title, {
      x: x + 0.15, y: y + 0.1, w: 2.55, h: 0.35,
      fontSize: 13, fontFace: "Calibri", color: C.gold400,
      bold: true, margin: 0,
    });
    s.addText(p.desc, {
      x: x + 0.15, y: y + 0.5, w: 2.55, h: 0.75,
      fontSize: 10, fontFace: "Calibri", color: C.slate300,
      margin: 0,
    });
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 15 — SRA Compliance
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  s.addText("SRA COMPLIANCE", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("Regulatory framework ensures\ncompliance from day one.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.9,
    fontSize: 28, fontFace: "Georgia", color: C.green900,
    bold: true, margin: 0,
  });

  // Permitted vs Prohibited
  // Permitted
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 2.1, w: 4.0, h: 2.8,
    fill: { color: C.green100 },
  });
  s.addText("Permitted", {
    x: 0.7, y: 2.1, w: 4.0, h: 0.45,
    fontSize: 15, fontFace: "Calibri", color: C.green800,
    bold: true, align: "center", valign: "middle", margin: 0,
  });
  s.addText([
    { text: "Charge for enhanced profiles / advertising", options: { bullet: true, breakLine: true } },
    { text: "Charge per lead (non-PI areas)", options: { bullet: true, breakLine: true } },
    { text: "Charge for sponsored content", options: { bullet: true, breakLine: true } },
    { text: "Charge for events / sponsorship", options: { bullet: true, breakLine: true } },
    { text: "All require: written agreements + client disclosure", options: { bullet: true } },
  ], {
    x: 0.9, y: 2.65, w: 3.6, h: 2.0,
    fontSize: 11, fontFace: "Calibri", color: C.green800,
    paraSpaceAfter: 6,
  });

  // Prohibited
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.3, y: 2.1, w: 4.0, h: 2.8,
    fill: { color: "FEE2E2" },
  });
  s.addText("Prohibited", {
    x: 5.3, y: 2.1, w: 4.0, h: 0.45,
    fontSize: 15, fontFace: "Calibri", color: "DC2626",
    bold: true, align: "center", valign: "middle", margin: 0,
  });
  s.addText([
    { text: "Referral fees for personal injury (LASPO ban)", options: { bullet: true, breakLine: true } },
    { text: "Payment influencing chat recommendations", options: { bullet: true, breakLine: true } },
    { text: "Unlabelled sponsored content", options: { bullet: true, breakLine: true } },
    { text: "Undisclosed commercial arrangements", options: { bullet: true } },
  ], {
    x: 5.5, y: 2.65, w: 3.6, h: 2.0,
    fontSize: 11, fontFace: "Calibri", color: "991B1B",
    paraSpaceAfter: 6,
  });

  s.addText("Editorial independence: AskAdil chat recommends based on best-fit (specialism, location, language) — never payment status.", {
    x: 0.7, y: 5.05, w: 8.6, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.slate600,
    italic: true, margin: 0,
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 16 — Data Sources for Growth
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  s.addText("GROWTH STRATEGY", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("Multiple channels to scale\nfrom 38 to 1,000+ firms.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.9,
    fontSize: 28, fontFace: "Georgia", color: C.green900,
    bold: true, margin: 0,
  });

  const channels = [
    { title: "SRA API", desc: "Query 200K+ solicitors by name/location.\nMatch against Muslim surnames.\nInvite to opt in.", priority: "High" },
    { title: "MCB Network", desc: "500+ affiliated mosques.\nCommunity recommendations.\nWarm introductions.", priority: "High" },
    { title: "Self-Registration", desc: "\"List your practice\" portal.\nPromote via AML, MLAG, Hub.\nLawyers opt in directly.", priority: "High" },
    { title: "LinkedIn Mining", desc: "Search AML/MLAG followers.\nIdentify self-identified\nMuslim legal professionals.", priority: "Medium" },
    { title: "Islamic Banks", desc: "Al Rayan, Gatehouse etc.\nmaintain solicitor panels.\nPre-vetted for competence.", priority: "Medium" },
    { title: "Law Society FOI", desc: "Anonymised diversity data\nby religion + practice area\n+ region. Market sizing.", priority: "Low" },
  ];

  channels.forEach((ch, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.5 + col * 3.1;
    const y = 2.0 + row * 1.65;

    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 2.85, h: 1.45,
      fill: { color: C.white },
      shadow: cardShadow(),
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 2.85, h: 0.04,
      fill: { color: ch.priority === "High" ? C.green700 : ch.priority === "Medium" ? C.gold600 : C.slate400 },
    });
    s.addText(ch.title, {
      x: x + 0.15, y: y + 0.12, w: 1.7, h: 0.3,
      fontSize: 13, fontFace: "Calibri", color: C.green800,
      bold: true, margin: 0,
    });
    s.addText(ch.priority, {
      x: x + 1.85, y: y + 0.12, w: 0.85, h: 0.3,
      fontSize: 9, fontFace: "Calibri",
      color: ch.priority === "High" ? C.green700 : ch.priority === "Medium" ? C.gold700 : C.slate500,
      bold: true, align: "right", margin: 0,
    });
    s.addText(ch.desc, {
      x: x + 0.15, y: y + 0.5, w: 2.55, h: 0.85,
      fontSize: 10, fontFace: "Calibri", color: C.slate600,
      margin: 0,
    });
  });
}

// ════════════════════════════════════════════════════════════════
// SLIDE 17 — Next Steps / CTA
// ════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.green900 };

  // Gold accent bar top
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.06,
    fill: { color: C.gold500 },
  });

  s.addText("NEXT STEPS", {
    x: 0.7, y: 0.5, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold400,
    bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("From research to referrals.", {
    x: 0.7, y: 1.0, w: 8.5, h: 0.6,
    fontSize: 32, fontFace: "Georgia", color: C.white,
    bold: true, margin: 0,
  });

  const nextSteps = [
    { num: "1", text: "Embed the 38-firm directory into AskAdil's RAG knowledge base for immediate chat referrals" },
    { num: "2", text: "Begin outreach to Tier A firms — I Will Solicitors, Aramas, White Horse, Kuddus, Rahman Lowe" },
    { num: "3", text: "Engage AML, MLAG, and Muslim Lawyers' Hub as distribution partners" },
    { num: "4", text: "Register for SRA API access and prototype name-matching pipeline" },
    { num: "5", text: "MCB board discussion: governance model for commercial directory operations" },
  ];

  nextSteps.forEach((ns, i) => {
    const y = 1.9 + i * 0.6;
    s.addShape(pres.shapes.OVAL, {
      x: 0.7, y: y + 0.05, w: 0.35, h: 0.35,
      fill: { color: C.gold500 },
    });
    s.addText(ns.num, {
      x: 0.7, y: y + 0.05, w: 0.35, h: 0.35,
      fontSize: 14, fontFace: "Georgia", color: C.green900,
      bold: true, align: "center", valign: "middle", margin: 0,
    });
    s.addText(ns.text, {
      x: 1.3, y, w: 7.5, h: 0.45,
      fontSize: 14, fontFace: "Calibri", color: C.white,
      valign: "middle", margin: 0,
    });
  });

  // Contact
  s.addText("askadil.org", {
    x: 0.7, y: 4.7, w: 3, h: 0.4,
    fontSize: 18, fontFace: "Georgia", color: C.gold400,
    bold: true, margin: 0,
  });
  s.addText("An initiative in association with the Muslim Council of Britain", {
    x: 0.7, y: 5.05, w: 6, h: 0.3,
    fontSize: 10, fontFace: "Calibri", color: C.slate500,
    margin: 0,
  });
}

// ── Write file ──
const outPath = path.join(__dirname, "AskAdil-Solicitor-Directory-Pitch-Deck.pptx");
pres.writeFile({ fileName: outPath }).then(() => {
  console.log("Pitch deck created: " + outPath);
}).catch(err => {
  console.error("Error:", err);
});
