const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "AskAdil / MCB";
pres.title = "AskAdil Solicitor Directory — Executive Brief";

// Brand colours
const C = {
  green900: "0D3B1E",
  green800: "14532D",
  green700: "166534",
  green600: "16A34A",
  green100: "DCFCE7",
  gold500: "D4A843",
  gold400: "E5C76B",
  gold700: "8B6914",
  slate800: "1E293B",
  slate600: "475569",
  slate500: "64748B",
  slate300: "CBD5E1",
  slate200: "E2E8F0",
  slate100: "F1F5F9",
  white: "FFFFFF",
  bg: "FAFAF8",
  red600: "DC2626",
};

const shadow = () => ({ type: "outer", color: "000000", blur: 6, offset: 2, angle: 135, opacity: 0.1 });

// ═══════════════════════════════════════════════════
// SLIDE 1 — Title
// ═══════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.green900 };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: C.gold500 } });

  s.addText("askadil.org", {
    x: 0.7, y: 0.4, w: 3, h: 0.4,
    fontSize: 14, fontFace: "Georgia", color: C.gold400, bold: true, margin: 0,
  });

  s.addText("Solicitor Directory", {
    x: 0.7, y: 1.5, w: 8, h: 1.0,
    fontSize: 44, fontFace: "Georgia", color: C.white, bold: true, margin: 0,
  });

  s.addText("Executive Brief for MCB Leadership", {
    x: 0.7, y: 2.6, w: 7, h: 0.5,
    fontSize: 20, fontFace: "Calibri", color: C.gold400, margin: 0,
  });

  s.addText("March 2026", {
    x: 0.7, y: 3.4, w: 3, h: 0.4,
    fontSize: 14, fontFace: "Calibri", color: C.slate300, margin: 0,
  });

  s.addText("An initiative in association with the Muslim Council of Britain", {
    x: 0.7, y: 4.9, w: 6, h: 0.4,
    fontSize: 11, fontFace: "Calibri", color: C.slate500, margin: 0,
  });
}

// ═══════════════════════════════════════════════════
// SLIDE 2 — The Problem
// ═══════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  s.addText("THE PROBLEM", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700, bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("British Muslims cannot find\nMuslim-friendly legal help.", {
    x: 0.7, y: 0.9, w: 8.5, h: 1.0,
    fontSize: 30, fontFace: "Georgia", color: C.green900, bold: true, margin: 0,
  });

  const stats = [
    { num: "377%", label: "surge in Islamophobia\nincidents (2023-24)" },
    { num: "45%", label: "of all religious hate\ncrimes target Muslims" },
    { num: "~12,000", label: "Muslim solicitors in\nEngland & Wales" },
    { num: "0", label: "public searchable\ndirectories exist" },
  ];

  stats.forEach((st, i) => {
    const x = 0.5 + i * 2.3;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 2.3, w: 2.05, h: 1.8, fill: { color: C.white }, shadow: shadow() });
    s.addShape(pres.shapes.RECTANGLE, { x, y: 2.3, w: 2.05, h: 0.05, fill: { color: i < 2 ? C.red600 : C.green700 } });
    s.addText(st.num, {
      x, y: 2.5, w: 2.05, h: 0.7,
      fontSize: 32, fontFace: "Georgia", color: i < 2 ? C.red600 : C.green700, bold: true, align: "center", margin: 0,
    });
    s.addText(st.label, {
      x, y: 3.2, w: 2.05, h: 0.7,
      fontSize: 11, fontFace: "Calibri", color: C.slate600, align: "center", margin: 0,
    });
  });

  s.addText("Existing resources (muslimlawyer.co.uk, SolicitorConnect) are either dormant since 2019 or ineffective.", {
    x: 0.7, y: 4.5, w: 8.5, h: 0.4,
    fontSize: 12, fontFace: "Calibri", color: C.slate500, italic: true, margin: 0,
  });
}

// ═══════════════════════════════════════════════════
// SLIDE 3 — The Opportunity
// ═══════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.green900 };

  s.addText("THE OPPORTUNITY", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold400, bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("AskAdil is uniquely positioned\nto build what no one else can.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.9,
    fontSize: 28, fontFace: "Georgia", color: C.white, bold: true, margin: 0,
  });

  const props = [
    { title: "MCB Trust Signal", desc: "Association with the Muslim Council of Britain provides credibility no other platform can replicate." },
    { title: "AskAdil Chatbot", desc: "Users already describe their legal issue to AskAdil. We can match them to the right solicitor automatically." },
    { title: "First-Mover Advantage", desc: "Zero competitors in this space. No public Muslim lawyer directory exists anywhere in the UK." },
    { title: "Community Reach", desc: "500+ MCB-affiliated mosques and organisations as a distribution network for promoting the directory." },
  ];

  props.forEach((p, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.5 + col * 4.6;
    const y = 2.2 + row * 1.5;
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 4.3, h: 1.25, fill: { color: C.green800 } });
    s.addText(p.title, {
      x: x + 0.2, y: y + 0.1, w: 3.9, h: 0.35,
      fontSize: 14, fontFace: "Calibri", color: C.gold400, bold: true, margin: 0,
    });
    s.addText(p.desc, {
      x: x + 0.2, y: y + 0.5, w: 3.9, h: 0.65,
      fontSize: 11, fontFace: "Calibri", color: C.slate300, margin: 0,
    });
  });
}

// ═══════════════════════════════════════════════════
// SLIDE 4 — What We've Built
// ═══════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  s.addText("WHAT WE'VE BUILT", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700, bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("Research, technology, and documentation\nare complete and ready to execute.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.9,
    fontSize: 26, fontFace: "Georgia", color: C.green900, bold: true, margin: 0,
  });

  const items = [
    {
      title: "Research", accent: C.green700,
      lines: [
        "50 solicitor firms audited with verified contact details",
        "43 Islamophobia legal resources mapped",
        "Geographic coverage across all major Muslim population centres",
      ],
    },
    {
      title: "Technology", accent: C.green800,
      lines: [
        "AI outreach engine: researches firms, writes personalised emails",
        "Live on Railway: API + worker + database + Redis",
        "222 automated tests passing, real email delivery verified",
      ],
    },
    {
      title: "Documentation", accent: C.gold700,
      lines: [
        "Monetisation strategy (freemium, self-sustaining at maturity)",
        "SRA compliance framework reviewed",
        "Outreach plan with templates, cadence, tracking",
      ],
    },
  ];

  items.forEach((item, i) => {
    const x = 0.4 + i * 3.15;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 2.1, w: 2.95, h: 3.0, fill: { color: C.white }, shadow: shadow() });
    s.addShape(pres.shapes.RECTANGLE, { x, y: 2.1, w: 2.95, h: 0.05, fill: { color: item.accent } });
    s.addText(item.title, {
      x: x + 0.15, y: 2.25, w: 2.65, h: 0.4,
      fontSize: 16, fontFace: "Calibri", color: item.accent, bold: true, margin: 0,
    });
    s.addText(item.lines.map(l => ({ text: l, options: { bullet: true, breakLine: true } })), {
      x: x + 0.15, y: 2.75, w: 2.65, h: 2.2,
      fontSize: 11, fontFace: "Calibri", color: C.slate600, paraSpaceAfter: 6,
    });
  });
}

// ═══════════════════════════════════════════════════
// SLIDE 5 — The Ask
// ═══════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  s.addText("WHAT WE NEED", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700, bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("Three decisions to move forward.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.6,
    fontSize: 28, fontFace: "Georgia", color: C.green900, bold: true, margin: 0,
  });

  const decisions = [
    {
      num: "1", title: "Approve Outreach", priority: "Required",
      desc: "Authorise contacting 50 solicitor firms to invite them to the directory (free listing). Each email is AI-personalised and human-reviewed before sending.",
    },
    {
      num: "2", title: "MCB Endorsement Letter", priority: "Required",
      desc: "Provide a brief endorsement paragraph for outreach emails and the directory landing page. This is the #1 trust signal for solicitor response rates.",
    },
    {
      num: "3", title: "Promote via MCB Channels", priority: "Phase 2",
      desc: "Share the directory with MCB's network once 25+ firms are listed. Newsletter, social media, affiliate mosque networks.",
    },
  ];

  decisions.forEach((d, i) => {
    const y = 1.7 + i * 1.2;
    s.addShape(pres.shapes.OVAL, {
      x: 0.7, y: y + 0.15, w: 0.45, h: 0.45,
      fill: { color: C.green800 },
    });
    s.addText(d.num, {
      x: 0.7, y: y + 0.15, w: 0.45, h: 0.45,
      fontSize: 18, fontFace: "Georgia", color: C.white, bold: true, align: "center", valign: "middle", margin: 0,
    });
    s.addText(d.title, {
      x: 1.4, y, w: 4, h: 0.4,
      fontSize: 16, fontFace: "Calibri", color: C.green800, bold: true, margin: 0,
    });
    s.addText(d.priority, {
      x: 8.0, y, w: 1.5, h: 0.35,
      fontSize: 10, fontFace: "Calibri", color: d.priority === "Required" ? C.green700 : C.slate500,
      bold: true, align: "right", margin: 0,
    });
    s.addText(d.desc, {
      x: 1.4, y: y + 0.4, w: 7.5, h: 0.65,
      fontSize: 11, fontFace: "Calibri", color: C.slate600, margin: 0,
    });
  });
}

// ═══════════════════════════════════════════════════
// SLIDE 6 — Phased Approach
// ═══════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };

  s.addText("PHASED APPROACH", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold700, bold: true, charSpacing: 3, margin: 0,
  });

  s.addText("From outreach to revenue in four phases.", {
    x: 0.7, y: 0.9, w: 8.5, h: 0.6,
    fontSize: 28, fontFace: "Georgia", color: C.green900, bold: true, margin: 0,
  });

  // Timeline
  s.addShape(pres.shapes.LINE, { x: 0.7, y: 1.95, w: 8.6, h: 0, line: { color: C.slate300, width: 2 } });

  const phases = [
    { phase: "Phase 1", period: "Wk 1-6", title: "Outreach", outcome: "25+ firms consent", accent: C.green600 },
    { phase: "Phase 2", period: "Week 8", title: "Launch", outcome: "Directory live in chat", accent: C.green700 },
    { phase: "Phase 3", period: "Week 10", title: "Promote", outcome: "Community awareness", accent: C.green800 },
    { phase: "Phase 4", period: "Q3 2026", title: "Scale", outcome: "200+ firms, revenue", accent: C.green900 },
  ];

  phases.forEach((p, i) => {
    const x = 0.5 + i * 2.3;
    s.addShape(pres.shapes.OVAL, { x: x + 0.85, y: 1.82, w: 0.26, h: 0.26, fill: { color: p.accent } });
    s.addShape(pres.shapes.RECTANGLE, { x, y: 2.3, w: 2.1, h: 2.3, fill: { color: C.white }, shadow: shadow() });
    s.addShape(pres.shapes.RECTANGLE, { x, y: 2.3, w: 2.1, h: 0.05, fill: { color: p.accent } });
    s.addText(p.phase, {
      x: x + 0.15, y: 2.45, w: 1.0, h: 0.3,
      fontSize: 10, fontFace: "Calibri", color: p.accent, bold: true, margin: 0,
    });
    s.addText(p.period, {
      x: x + 1.0, y: 2.45, w: 1.0, h: 0.3,
      fontSize: 9, fontFace: "Calibri", color: C.slate500, align: "right", margin: 0,
    });
    s.addText(p.title, {
      x: x + 0.15, y: 2.8, w: 1.8, h: 0.4,
      fontSize: 15, fontFace: "Calibri", color: C.green900, bold: true, margin: 0,
    });
    s.addText(p.outcome, {
      x: x + 0.15, y: 3.3, w: 1.8, h: 0.4,
      fontSize: 11, fontFace: "Calibri", color: C.slate600, margin: 0,
    });
  });

  // Revenue bar
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 4.8, w: 9.0, h: 0.5, fill: { color: C.green100 } });
  s.addText("Revenue potential at maturity: £250-350K/year (self-sustaining via freemium subscriptions + lead generation)", {
    x: 0.7, y: 4.8, w: 8.6, h: 0.5,
    fontSize: 11, fontFace: "Calibri", color: C.green800, bold: true, valign: "middle", margin: 0,
  });
}

// ═══════════════════════════════════════════════════
// SLIDE 7 — Risk & Next Step
// ═══════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.green900 };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: C.gold500 } });

  s.addText("RISK & NEXT STEP", {
    x: 0.7, y: 0.4, w: 3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.gold400, bold: true, charSpacing: 3, margin: 0,
  });

  // Risk table
  s.addText("Risks are minimal and mitigated:", {
    x: 0.7, y: 1.0, w: 8, h: 0.4,
    fontSize: 16, fontFace: "Calibri", color: C.white, bold: true, margin: 0,
  });

  const risks = [
    ["Low response rate", "MCB endorsement + AI personalisation + follow-up cadence"],
    ["Regulatory (SRA)", "No PI referral fees. Disclosure compliant. Legal review planned."],
    ["Reputational", "Every email human-reviewed. Dry-run tested. Professional tone verified."],
    ["Data protection", "GDPR compliant. Public data only. Consent required. Right to removal."],
  ];

  const headerRow = [
    { text: "Risk", options: { fill: { color: C.green800 }, color: C.white, bold: true, fontSize: 11, fontFace: "Calibri" } },
    { text: "Mitigation", options: { fill: { color: C.green800 }, color: C.white, bold: true, fontSize: 11, fontFace: "Calibri" } },
  ];

  const tableData = [headerRow, ...risks.map(r => [
    { text: r[0], options: { fontSize: 11, fontFace: "Calibri", color: C.slate300 } },
    { text: r[1], options: { fontSize: 11, fontFace: "Calibri", color: C.slate300 } },
  ])];

  s.addTable(tableData, {
    x: 0.7, y: 1.5, w: 8.6,
    colW: [2.5, 6.1],
    border: { pt: 0.5, color: C.green800 },
    rowH: [0.35, 0.35, 0.35, 0.35, 0.35],
  });

  // CTA
  s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y: 3.8, w: 8.6, h: 1.2, fill: { color: C.green800 } });

  s.addText("One decision needed:", {
    x: 1.0, y: 3.9, w: 8, h: 0.35,
    fontSize: 14, fontFace: "Calibri", color: C.gold400, bold: true, margin: 0,
  });

  s.addText("Approve outreach with MCB endorsement.\nEverything else is built, tested, and ready to execute.", {
    x: 1.0, y: 4.3, w: 8, h: 0.6,
    fontSize: 18, fontFace: "Georgia", color: C.white, bold: true, margin: 0,
  });

  s.addText("askadil.org", {
    x: 0.7, y: 5.1, w: 3, h: 0.3,
    fontSize: 12, fontFace: "Georgia", color: C.gold400, bold: true, margin: 0,
  });
}

// Write
const outPath = path.join(__dirname, "AskAdil-MCB-Exec-Brief.pptx");
pres.writeFile({ fileName: outPath }).then(() => {
  console.log("Created: " + outPath);
}).catch(err => console.error(err));
