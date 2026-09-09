const pptxgen = require("pptxgenjs");
const path = require("path");

const DARK = "2D3142";
const PAPER = "F5F5F5";
const WHITE = "FFFFFF";
const INK = "2D3142";
const MUTED = "4F5D75";
const SOFT = "7A8399";
const ACCENT = "EB6C36";
const TINT = "FBE7DC";
const RULE = "E3E1DC";
const LIGHT = "D8DAE3";

const TITLE_FONT = "Cambria";
const BODY = "Calibri";
const W = 13.333;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "Team BOT BABY";
pres.company = "Manakula Vinayagar Institute of Technology";
pres.title = "EvidenceHire - PS02";

function chip(s, n) {
  s.addShape("roundRect", { x: 0.55, y: 0.45, w: 0.55, h: 0.55, rectRadius: 0.07,
    fill: { color: ACCENT }, line: { type: "none" } });
  s.addText(String(n).padStart(2, "0"), { x: 0.55, y: 0.45, w: 0.55, h: 0.55,
    isTextBox: true, margin: 0, align: "center", valign: "middle",
    fontFace: BODY, fontSize: 14, bold: true, color: WHITE });
}

function title(s, text, sub) {
  s.addText(text, { x: 1.35, y: 0.38, w: 11.4, h: 0.6, isTextBox: true, margin: 0,
    fontFace: TITLE_FONT, fontSize: 30, bold: true, color: INK, valign: "middle" });
  if (sub) {
    s.addText(sub, { x: 1.35, y: 0.94, w: 11.4, h: 0.4, isTextBox: true, margin: 0,
      fontFace: BODY, fontSize: 13, color: MUTED, valign: "middle" });
  }
}

function row(s, x, y, w, num, head, body) {
  s.addShape("ellipse", { x, y, w: 0.5, h: 0.5, fill: { color: TINT },
    line: { color: ACCENT, width: 1.25 } });
  s.addText(String(num), { x, y, w: 0.5, h: 0.5, isTextBox: true, margin: 0,
    align: "center", valign: "middle", fontFace: BODY, fontSize: 13, bold: true, color: ACCENT });
  s.addText(head, { x: x + 0.7, y: y - 0.05, w: w - 0.7, h: 0.35, isTextBox: true,
    margin: 0, fontFace: BODY, fontSize: 15, bold: true, color: INK });
  s.addText(body, { x: x + 0.7, y: y + 0.32, w: w - 0.7, h: 0.62, isTextBox: true,
    margin: 0, fontFace: BODY, fontSize: 11.5, color: MUTED, valign: "top",
    lineSpacingMultiple: 1.12 });
}

function card(s, x, y, w, h, head, body, accentHead) {
  s.addShape("roundRect", { x, y, w, h, rectRadius: 0.08, fill: { color: WHITE },
    line: { color: RULE, width: 1 } });
  s.addShape("roundRect", { x: x + 0.28, y: y + 0.28, w: 0.4, h: 0.14, rectRadius: 0.03,
    fill: { color: ACCENT }, line: { type: "none" } });
  s.addText(head, { x: x + 0.28, y: y + 0.52, w: w - 0.56, h: 0.5, isTextBox: true,
    margin: 0, fontFace: BODY, fontSize: 14, bold: true,
    color: accentHead ? ACCENT : INK, valign: "top" });
  s.addText(body, { x: x + 0.28, y: y + 1.04, w: w - 0.56, h: h - 1.3, isTextBox: true,
    margin: 0, fontFace: BODY, fontSize: 10.5, color: MUTED, valign: "top",
    lineSpacingMultiple: 1.15 });
}

// ---------- 1. Title ----------
{
  const s = pres.addSlide();
  s.background = { color: DARK };
  s.addText("X'O CODE 2026   ·   PS02   ·   AUTONOMOUS TALENT-ACQUISITION SCREENING", {
    x: 0.9, y: 1.0, w: 11.6, h: 0.4, isTextBox: true, margin: 0,
    fontFace: BODY, fontSize: 11.5, bold: true, color: LIGHT, charSpacing: 2 });
  s.addText("EvidenceHire", { x: 0.85, y: 2.3, w: 11.6, h: 1.6, isTextBox: true,
    margin: 0, fontFace: TITLE_FONT, fontSize: 72, bold: true, color: WHITE });
  s.addText("Don't just read what candidates claim.\nVerify what the evidence supports.", {
    x: 0.9, y: 3.95, w: 11, h: 1.0, isTextBox: true, margin: 0,
    fontFace: TITLE_FONT, italic: true, fontSize: 22, color: ACCENT,
    lineSpacingMultiple: 1.2 });
  s.addText("Team BOT BABY  ·  XO01", { x: 0.9, y: 6.3, w: 8, h: 0.45, isTextBox: true,
    margin: 0, fontFace: BODY, fontSize: 16, bold: true, color: WHITE });
  s.addText("Manakula Vinayagar Institute of Technology", { x: 0.9, y: 6.75, w: 8, h: 0.35,
    isTextBox: true, margin: 0, fontFace: BODY, fontSize: 11.5, color: LIGHT });
  s.addNotes("EvidenceHire, PS02 Autonomous Talent-Acquisition Screening Agent. Team BOT BABY, Team ID XO01.");
}

// ---------- 2. Team ----------
{
  const s = pres.addSlide();
  s.background = { color: PAPER };
  chip(s, 2);
  title(s, "The Team", "Team BOT BABY  ·  XO01  ·  Manakula Vinayagar Institute of Technology");

  const y = 1.9, w = 3.75, h = 4.2, gap = 0.35;
  const people = [
    ["MM", "Madanraj M", "23TRL004", "Team Lead",
      "Coordination, integration, GitHub checkpoints and final submission."],
    ["GS", "Ganisetti Veera Venkata\nSatyanarayana", "23TRL001", "Screening Engine",
      "Claim extraction, terminology equivalence, evidence grading, requirement assessment."],
    ["SN", "Santhosh N", "24TR0028", "Console & Demo",
      "Recruiter console, dataset authoring, demo scenario and documentation."],
  ];

  people.forEach((p, i) => {
    const x = 0.7 + i * (w + gap);
    s.addShape("roundRect", { x, y, w, h, rectRadius: 0.08, fill: { color: WHITE },
      line: { color: RULE, width: 1 } });
    s.addShape("ellipse", { x: x + 0.35, y: y + 0.35, w: 0.9, h: 0.9,
      fill: { color: TINT }, line: { color: ACCENT, width: 1.25 } });
    s.addText(p[0], { x: x + 0.35, y: y + 0.35, w: 0.9, h: 0.9, isTextBox: true,
      margin: 0, align: "center", valign: "middle", fontFace: TITLE_FONT,
      fontSize: 22, bold: true, color: ACCENT });
    s.addText(p[1], { x: x + 0.35, y: y + 1.4, w: w - 0.7, h: 0.6, isTextBox: true,
      margin: 0, fontFace: BODY, fontSize: 14.5, bold: true, color: INK, valign: "top" });
    s.addText("Reg. No. " + p[2], { x: x + 0.35, y: y + 2.0, w: w - 0.7, h: 0.3,
      isTextBox: true, margin: 0, fontFace: BODY, fontSize: 10.5, color: SOFT });
    s.addText(p[3], { x: x + 0.35, y: y + 2.34, w: w - 0.7, h: 0.3, isTextBox: true,
      margin: 0, fontFace: BODY, fontSize: 11.5, bold: true, color: ACCENT });
    s.addText(p[4], { x: x + 0.35, y: y + 2.7, w: w - 0.7, h: 1.2, isTextBox: true,
      margin: 0, fontFace: BODY, fontSize: 10, color: MUTED, valign: "top",
      lineSpacingMultiple: 1.15 });
  });
  s.addNotes("Three members, one clear layer each, so any of us can be questioned on our own area.");
}

// ---------- 3. Problem ----------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  chip(s, 3);
  title(s, "The Problem");

  s.addText("A keyword matcher cannot tell\na proven skill from\na padded one.", {
    x: 0.7, y: 1.9, w: 5.5, h: 2.6, isTextBox: true, margin: 0,
    fontFace: TITLE_FONT, italic: true, fontSize: 27, color: ACCENT,
    valign: "top", lineSpacingMultiple: 1.18 });

  s.addText("If the resume says \"Python\" and the requisition says \"Python\", conventional screening counts it as a hit - whether the candidate shipped production systems or simply typed the word.", {
    x: 0.7, y: 4.7, w: 5.5, h: 1.6, isTextBox: true, margin: 0,
    fontFace: BODY, fontSize: 12, color: MUTED, valign: "top", lineSpacingMultiple: 1.2 });

  const rx = 6.9, rw = 5.7;
  row(s, rx, 2.0, rw, 1, "It rewards resume padding",
    "A bare \"expert in distributed systems\" scores the same as someone who actually built one.");
  row(s, rx, 3.2, rw, 2, "It punishes honest phrasing",
    "\"Built ROS 2 navigation packages\" may never use the requisition's exact keyword.");
  row(s, rx, 4.4, rw, 3, "It hides broken requisitions",
    "5+ years demanded on a junior role produces a weak pool - and blames the applicants.");
  row(s, rx, 5.6, rw, 4, "It gives no basis for a trade-off",
    "One opaque percentage cannot say where a candidate is strong and where they are not.");
  s.addNotes("The failure is not that matching is inaccurate. It is that a mention and a demonstration are treated as the same thing.");
}

// ---------- 4. Proposed solution ----------
{
  const s = pres.addSlide();
  s.background = { color: PAPER };
  chip(s, 4);
  title(s, "Our Solution - EvidenceHire",
    "The question is not \"does the resume contain the keyword?\" but \"how well-supported is this claim before we trust it?\"");

  row(s, 0.9, 2.15, 11.2, 1, "An evidence ladder, E0 to E4",
    "Every claim is graded by where its support actually sits. A cover note carries zero weight - a candidate vouching for themselves is the claim, not evidence for it. Skills lists and coursework are weak; projects moderate; professional work strong.");
  row(s, 0.9, 3.55, 11.2, 2, "Terminology equivalence that can also refuse",
    "\"Robot Operating System 2\" is accepted as ROS 2 - no penalty for phrasing. Arduino is refused for ROS 2, with the reason stated. Four outcomes: exact, equivalent, related, none.");
  row(s, 0.9, 4.95, 11.2, 3, "Named gaps instead of one opaque score",
    "Fit is reported per requirement. \"Unaddressed\" is kept distinct from \"addressed but not demonstrated\", and every unmet required area is named in the summary.");

  s.addShape("roundRect", { x: 0.9, y: 6.25, w: 11.2, h: 0.8, rectRadius: 0.08,
    fill: { color: TINT }, line: { type: "none" } });
  s.addText("Every assessment states its chain in the same order:   claim  >  evidence  >  assessment  >  confidence", {
    x: 1.2, y: 6.25, w: 10.6, h: 0.8, isTextBox: true, margin: 0,
    fontFace: BODY, italic: true, fontSize: 12.5, color: INK, valign: "middle" });
  s.addNotes("Claim strength and evidence strength are modelled as separate things. That single decision is what the whole system rests on.");
}

// ---------- 5. Architecture ----------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  chip(s, 5);
  title(s, "How It Works");
  const imgH = 4.9, imgW = imgH * (2464 / 1540);
  s.addImage({ path: path.join(__dirname, "docs", "architecture.png"),
    x: (W - imgW) / 2, y: 1.55, w: imgW, h: imgH });
  s.addNotes("Three parsers feed one grader. Nothing downstream is allowed to treat a claim as proven until the grader has placed its evidence on the ladder.");
}

// ---------- 6. Live proof ----------
{
  const s = pres.addSlide();
  s.background = { color: DARK };
  s.addText("REAL OUTPUT - NOT A MOCKUP", { x: 0.9, y: 0.6, w: 10, h: 0.35,
    isTextBox: true, margin: 0, fontFace: BODY, fontSize: 11, bold: true,
    color: LIGHT, charSpacing: 2 });
  s.addText("The same candidate, judged two opposite ways", { x: 0.85, y: 1.05, w: 11.6,
    h: 0.7, isTextBox: true, margin: 0, fontFace: TITLE_FONT, fontSize: 28,
    bold: true, color: WHITE });

  s.addShape("roundRect", { x: 0.9, y: 2.1, w: 11.2, h: 2.35, rectRadius: 0.08,
    fill: { color: "3A3F55" }, line: { type: "none" } });
  s.addText([
    { text: "A-07  Priya Raman\n", options: { color: WHITE, bold: true, fontSize: 14 } },
    { text: "Cloud Deployment    claimed = expert        E1  ", options: { color: LIGHT, fontSize: 13 } },
    { text: "OVERCLAIMED\n", options: { color: ACCENT, bold: true, fontSize: 13 } },
    { text: "ROS 2               claimed = proficient    E4  ", options: { color: LIGHT, fontSize: 13 } },
    { text: "Strong", options: { color: "9BD4A8", bold: true, fontSize: 13 } },
  ], { x: 1.25, y: 2.3, w: 10.5, h: 1.9, isTextBox: true, margin: 0,
    fontFace: "Courier New", valign: "top", lineSpacingMultiple: 1.5 });

  s.addText("Claim strength runs opposite to evidence strength. She overclaims cloud and underclaims robotics - a keyword matcher scores both as hits.", {
    x: 0.9, y: 4.65, w: 11.2, h: 0.7, isTextBox: true, margin: 0,
    fontFace: BODY, italic: true, fontSize: 13, color: LIGHT, valign: "top" });

  s.addText("Summary produced by the system:", { x: 0.9, y: 5.5, w: 11.2, h: 0.3,
    isTextBox: true, margin: 0, fontFace: BODY, fontSize: 11, color: SOFT });
  s.addText("\"4 of 5 required areas strong; 1 below bar (Cloud Deployment); 1 unsupported claim flagged\"", {
    x: 0.9, y: 5.85, w: 11.2, h: 0.6, isTextBox: true, margin: 0,
    fontFace: BODY, fontSize: 14, bold: true, color: WHITE, valign: "top" });
  s.addText("42 automated tests cover this behaviour, including the negative cases.", {
    x: 0.9, y: 6.6, w: 11.2, h: 0.35, isTextBox: true, margin: 0,
    fontFace: BODY, fontSize: 11, color: LIGHT });
  s.addNotes("This is genuine output from the engine, reproducible by running the test suite.");
}

// ---------- 7. Feasibility ----------
{
  const s = pres.addSlide();
  s.background = { color: PAPER };
  chip(s, 7);
  title(s, "Feasibility", "Every choice was made so the demo cannot fail on the day.");

  const y = 2.05, w = 3.6, h = 3.1, gap = 0.35;
  card(s, 0.7, y, w, h, "Runs fully offline",
    "The engine is deterministic and rules-first. No network call, no API quota, nothing that venue Wi-Fi can break. The LLM layer is optional and cached.");
  card(s, 0.7 + w + gap, y, w, h, "Already working, not planned",
    "5 engine modules built and 42 tests passing. Requisition conflict detection, claim extraction, equivalence, evidence grading and requirement assessment all run today.");
  card(s, 0.7 + 2 * (w + gap), y, w, h, "No blocking dependencies",
    "No model training, no OAuth approval wait, no paid infrastructure, no database to provision. Python and Streamlit only.");

  s.addText("Each engine decision traces to a rule and a quoted source span - which is what makes the output auditable rather than a black box, and what lets any team member explain any part of it.", {
    x: 0.7, y: 5.5, w: 11.2, h: 0.8, isTextBox: true, margin: 0,
    fontFace: BODY, italic: true, fontSize: 12, color: MUTED, valign: "top" });
  s.addNotes("42 tests passing is verifiable on the spot. The negative cases are the interesting ones: Arduino must not satisfy ROS 2.");
}

// ---------- 8. Scalability ----------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  chip(s, 8);
  title(s, "Scalability");

  row(s, 0.9, 2.0, 11.2, 1, "New skills are data, not code",
    "The equivalence map is a curated data structure. Supporting a new domain means adding entries, not rewriting matching logic.");
  row(s, 0.9, 3.2, 11.2, 2, "New evidence sources plug into one layer",
    "Grading reads section-weighted evidence. Adding external sources - repositories, portfolios, publications - extends the evidence set without touching assessment or reporting.");
  row(s, 0.9, 4.4, 11.2, 3, "Pool analysis scales with the pool",
    "Gap detection and trade-off ranking are aggregate reads over per-candidate assessments, so 12 applications and 1,200 use the same path.");

  s.addShape("roundRect", { x: 0.9, y: 5.75, w: 11.2, h: 1.05, rectRadius: 0.08,
    fill: { color: "F3F1EE" }, line: { color: RULE, width: 1 } });
  s.addText("Honest limit: today it is single-user and in-memory, sized for the hackathon. Production would need durable storage and per-organisation evidence weighting - named as future work, not claimed as done.", {
    x: 1.2, y: 5.75, w: 10.6, h: 1.05, isTextBox: true, margin: 0,
    fontFace: BODY, italic: true, fontSize: 12, color: MUTED, valign: "middle" });
  s.addNotes("We would rather state the limit than have a judge find it.");
}

// ---------- 9. Scope & closing ----------
{
  const s = pres.addSlide();
  s.background = { color: DARK };
  s.addText("SCOPE", { x: 0.9, y: 0.62, w: 10, h: 0.35, isTextBox: true, margin: 0,
    fontFace: BODY, fontSize: 11, bold: true, color: LIGHT, charSpacing: 2 });
  s.addText("What we build, and what we refuse to", { x: 0.85, y: 1.05, w: 11.6, h: 0.7,
    isTextBox: true, margin: 0, fontFace: TITLE_FONT, fontSize: 28, bold: true, color: WHITE });

  const y = 2.15, w = 3.6, h = 3.3, gap = 0.35;
  const cols = [
    ["IN SCOPE NOW", WHITE,
      "Evidence grading E0-E4\nTerminology equivalence\nRequirement assessment\nRequisition conflict detection\nRecruiter console"],
    ["NEXT", ACCENT,
      "Trade-off shortlisting\nTalent-pool gap detection\nWithin-document timeline checks\nCandidate comparison view"],
    ["DELIBERATELY NOT", LIGHT,
      "No AI-authorship detection\nNo protected-trait inference\nNo fabricated evidence\nNo accusations - only\n\"requires verification\"\nNo automated hiring decision"],
  ];

  cols.forEach((c, i) => {
    const x = 0.9 + i * (w + gap);
    s.addShape("roundRect", { x, y, w, h, rectRadius: 0.08, fill: { color: "3A3F55" },
      line: { type: "none" } });
    s.addText(c[0], { x: x + 0.3, y: y + 0.3, w: w - 0.6, h: 0.4, isTextBox: true,
      margin: 0, fontFace: BODY, fontSize: 12, bold: true, color: c[1], charSpacing: 1.5 });
    s.addText(c[2], { x: x + 0.3, y: y + 0.85, w: w - 0.6, h: h - 1.15, isTextBox: true,
      margin: 0, fontFace: BODY, fontSize: 11.5, color: LIGHT, valign: "top",
      lineSpacingMultiple: 1.45 });
  });

  s.addText("The last column is a design position, not a missing feature. A screening system that cannot be held to account should not be trusted with a hiring decision - so ours does not make one.", {
    x: 0.9, y: 5.75, w: 11.2, h: 0.8, isTextBox: true, margin: 0,
    fontFace: BODY, italic: true, fontSize: 12.5, color: LIGHT, valign: "top" });
  s.addText("Thank you.   Team BOT BABY  -  EvidenceHire", { x: 0.9, y: 6.65, w: 11,
    h: 0.5, isTextBox: true, margin: 0, fontFace: TITLE_FONT, italic: true,
    fontSize: 20, color: ACCENT });
  s.addNotes("Close on the refusals. Most teams will not have thought about what their system should decline to infer.");
}

pres.writeFile({ fileName: path.join(__dirname, "EvidenceHire-PS02-BOTBABY.pptx") })
  .then(() => console.log("written"));
