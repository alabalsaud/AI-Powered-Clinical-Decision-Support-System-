import { jsPDF } from 'jspdf';

// ─── Dietary & lifestyle recommendations per diagnosis keyword ─────────────────
const DIETARY_RULES = [
  {
    keywords: ['diabetes', 'diabetic', 'hyperglycemi', 'hba1c', 'insulin'],
    title: 'Type 2 Diabetes / Hyperglycaemia',
    avoid: [
      'Sugary drinks (soda, fruit juice, energy drinks)',
      'White rice, white bread, and refined carbohydrates',
      'Sweets, cakes, pastries, and processed snacks',
      'Deep-fried foods and trans fats',
      'High-glycaemic fruits in excess (dates, watermelon, ripe banana)',
    ],
    recommend: [
      'Whole grains (brown rice, oats, whole-wheat bread)',
      'Non-starchy vegetables (leafy greens, broccoli, tomatoes)',
      'Lean protein (grilled chicken, fish, legumes)',
      'Low-fat dairy or plant-based alternatives',
      'Regular small meals — avoid long fasting periods',
    ],
  },
  {
    keywords: ['hypertension', 'blood pressure', 'hypertensive', 'cardiovascular'],
    title: 'Hypertension / Cardiovascular Disease',
    avoid: [
      'High-sodium foods: table salt, pickles, processed meats, canned soups',
      'Fast food, chips, and heavily salted snacks',
      'Alcohol (more than 1 drink/day for women, 2 for men)',
      'Full-fat dairy, fatty red meat, and saturated fats',
      'Caffeine in excess (>3 cups of coffee/day)',
    ],
    recommend: [
      'DASH diet: fruits, vegetables, whole grains, low-fat dairy',
      'Potassium-rich foods: bananas, sweet potatoes, spinach',
      'Fatty fish (salmon, tuna) twice a week — Omega-3 benefits',
      'Limit sodium to <2,300 mg/day (ideally <1,500 mg)',
      'Maintain healthy weight; regular aerobic exercise',
    ],
  },
  {
    keywords: ['heart failure', 'cardiac failure', 'ejection fraction', 'bnp'],
    title: 'Heart Failure',
    avoid: [
      'Excess fluid (limit to 1.5–2 L/day unless advised otherwise)',
      'High-sodium foods — sodium causes fluid retention',
      'Alcohol — worsens cardiac function',
      'Processed foods, deli meats, and canned goods',
    ],
    recommend: [
      'Weigh yourself daily — report sudden gain >2 kg in 2 days',
      'Small, frequent meals to reduce strain on the heart',
      'Low-sodium diet (<2,000 mg/day)',
      'Adequate lean protein to prevent muscle wasting',
    ],
  },
  {
    keywords: ['kidney', 'renal', 'ckd', 'aki', 'nephropathy', 'creatinine'],
    title: 'Kidney Disease (CKD / AKI)',
    avoid: [
      'High-potassium foods (bananas, oranges, potatoes, tomatoes) if K⁺ elevated',
      'High-phosphorus foods (dairy, nuts, seeds, dark colas) if phosphorus elevated',
      'Excess protein — increases kidney workload',
      'Salt substitutes (often contain potassium chloride)',
      'NSAIDs and herbal supplements without physician approval',
    ],
    recommend: [
      'Follow nephrologist-guided fluid and electrolyte restrictions',
      'Low-sodium diet to control blood pressure',
      'Moderate, controlled protein intake',
      'Regular monitoring of potassium, phosphorus, and creatinine levels',
    ],
  },
  {
    keywords: ['pneumonia', 'respiratory', 'copd', 'asthma', 'lung', 'pulmonary'],
    title: 'Respiratory / Pulmonary Conditions',
    avoid: [
      'Dairy products if they worsen mucus production',
      'Gas-producing foods (beans, cabbage) that cause bloating and diaphragm pressure',
      'Processed foods and excessive sugar (weaken immune system)',
      'Cold beverages if they trigger bronchospasm',
    ],
    recommend: [
      'Stay well-hydrated — fluids help thin secretions',
      'Antioxidant-rich foods: berries, citrus, bell peppers (vitamin C)',
      'Omega-3 fatty acids (salmon, flaxseed) — anti-inflammatory',
      'Small frequent meals to avoid a full stomach pressing on diaphragm',
    ],
  },
  {
    keywords: ['sepsis', 'infection', 'bacteremia', 'fever'],
    title: 'Sepsis / Systemic Infection',
    avoid: [
      'Raw or undercooked meat, fish, eggs during recovery',
      'Foods that weaken immunity: excessive alcohol, high-sugar foods',
      'Unpasteurised dairy and juices',
    ],
    recommend: [
      'Protein-rich foods to support tissue repair (eggs, lean meat, legumes)',
      'Zinc and vitamin C sources for immune function',
      'Sufficient caloric intake to meet increased metabolic demands',
      'Stay well-hydrated to support kidney clearance of toxins',
    ],
  },
  {
    keywords: ['gerd', 'reflux', 'esophageal', 'gastric', 'peptic ulcer', 'gastritis'],
    title: 'GERD / Gastric / Peptic Ulcer',
    avoid: [
      'Spicy foods, chilli, black pepper',
      'Citrus fruits and juices (orange, lemon, tomato)',
      'Coffee, tea, alcohol, and carbonated drinks',
      'Chocolate, mint, and fatty or fried foods',
      'Eating within 2–3 hours of lying down',
    ],
    recommend: [
      'Small, frequent meals rather than large portions',
      'Eat slowly and chew thoroughly',
      'Elevate head of bed by 15–20 cm if symptoms occur at night',
      'Maintain healthy weight — obesity worsens reflux',
    ],
  },
  {
    keywords: ['anemia', 'iron deficiency', 'hemoglobin', 'haemoglobin'],
    title: 'Anaemia / Iron Deficiency',
    avoid: [
      'Tea, coffee, and calcium-rich foods immediately WITH iron-rich meals (inhibit absorption)',
      'Excessive fibre supplements that bind iron',
    ],
    recommend: [
      'Iron-rich foods: red meat, liver, lentils, spinach, fortified cereals',
      'Vitamin C alongside iron sources (orange juice, tomatoes) to enhance absorption',
      'Folate-rich foods: leafy greens, legumes, fortified bread',
      'Vitamin B12 sources: meat, fish, dairy, eggs',
    ],
  },
];

// ─── Medicine guidance per drug keyword ───────────────────────────────────────
const DRUG_NOTES = {
  metformin:    'Take with food to reduce GI side effects. Monitor for lactic acidosis (rare). Avoid alcohol.',
  aspirin:      'Take with food or milk to protect the stomach. Avoid if allergic to NSAIDs. Can increase bleeding risk.',
  warfarin:     'Maintain consistent vitamin K intake (leafy greens). Regular INR monitoring required. Avoid NSAIDs.',
  lisinopril:   'Monitor potassium and renal function. Avoid potassium supplements unless prescribed. Stop if angioedema occurs.',
  amlodipine:   'May cause ankle swelling. Avoid grapefruit juice. Take at the same time daily.',
  atorvastatin: 'Avoid grapefruit juice. Report muscle pain/weakness immediately. Take at bedtime.',
  simvastatin:  'Avoid grapefruit juice. Report muscle pain. Take in the evening.',
  omeprazole:   'Take 30 minutes before meals. Long-term use may reduce magnesium/B12 — monitor periodically.',
  pantoprazole: 'Take before meals. Long-term use may affect magnesium levels.',
  amoxicillin:  'Complete the full course even if feeling better. Take with food if upset stomach occurs.',
  azithromycin: 'Complete full course. Avoid antacids within 2 hours. May prolong QT — report palpitations.',
  ciprofloxacin:'Avoid calcium-containing foods/antacids within 2 hours. Drink plenty of water. Avoid sun exposure.',
  prednisone:   'Take with food. Avoid live vaccines. Taper dose slowly — do not stop abruptly.',
  insulin:      'Store in refrigerator. Rotate injection sites. Monitor glucose regularly. Carry fast sugar for hypoglycaemia.',
  furosemide:   'Monitor potassium — eat potassium-rich foods or take supplements if prescribed. Weigh daily.',
  spironolactone:'Avoid potassium supplements and high-potassium foods. Monitor renal function.',
  clopidogrel:  'Avoid unnecessary NSAIDs. Report unusual bleeding. Take with or without food.',
  enoxaparin:   'Subcutaneous injection — rotate sites. Report unusual bruising or bleeding.',
  paracetamol:  'Do not exceed 4 g/day. Avoid alcohol. Check other medicines for hidden paracetamol.',
  acetaminophen:'Same as paracetamol — max 4 g/day, avoid alcohol.',
  ibuprofen:    'Take with food. Avoid if renal impairment or history of peptic ulcer. Monitor blood pressure.',
  salbutamol:   'Rinse mouth after inhaled use. Report worsening breathlessness. Use reliever inhaler before exercise.',
  fluticasone:  'Rinse mouth/gargle after each use to prevent oral candidiasis.',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function patientDisplayName(p) {
  if (!p) return 'Unknown';
  return (
    p.full_name ||
    p.name ||
    `${p.first_name || ''} ${p.last_name || ''}`.trim() ||
    'Unknown'
  );
}

function safeFilename(s) {
  return String(s).replace(/[^a-zA-Z0-9-_]+/g, '_').slice(0, 60) || 'patient';
}

function getDietaryRecommendations(diagnoses) {
  const names = (diagnoses || []).map(
    (d) => (d.condition || d.diagnosis_name || d.name || '').toLowerCase()
  );
  const matched = [];
  for (const rule of DIETARY_RULES) {
    if (rule.keywords.some((kw) => names.some((n) => n.includes(kw)))) {
      matched.push(rule);
    }
  }
  return matched;
}

function getDrugNote(drugName) {
  if (!drugName) return null;
  const lower = drugName.toLowerCase();
  for (const [key, note] of Object.entries(DRUG_NOTES)) {
    if (lower.includes(key)) return note;
  }
  return null;
}

// ─── PDF Builder ──────────────────────────────────────────────────────────────

export function downloadClinicalReportPdf({
  patient,
  reportType,
  dateFrom,
  dateTo,
  diagnoses,
  prescriptions,
  conditions,
  allergies,
}) {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' });
  const pageW = doc.internal.pageSize.getWidth();
  const margin = 14;
  const maxW = pageW - margin * 2;
  let y = 18;

  // ── Layout helpers ──────────────────────────────────────────────────────────
  function checkPage(needed = 12) {
    if (y + needed > 285) {
      doc.addPage();
      y = 18;
    }
  }

  function addText(size, text, gap = 4, color = [30, 41, 59]) {
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(size);
    doc.setTextColor(...color);
    const lines = doc.splitTextToSize(String(text), maxW);
    checkPage(lines.length * size * 0.42 + gap);
    doc.text(lines, margin, y);
    y += lines.length * (size * 0.42) + gap;
  }

  function addHeading(text, color = [15, 23, 42]) {
    checkPage(14);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12);
    doc.setTextColor(...color);
    doc.text(text, margin, y);
    y += 7;
    // underline rule
    doc.setDrawColor(...color);
    doc.setLineWidth(0.4);
    doc.line(margin, y - 2, pageW - margin, y - 2);
    y += 3;
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(30, 41, 59);
  }

  function addSubheading(text) {
    checkPage(10);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(10);
    doc.setTextColor(30, 41, 59);
    doc.text(text, margin, y);
    y += 6;
    doc.setFont('helvetica', 'normal');
  }

  function addBullet(text, indent = 4) {
    const bulletX = margin + indent;
    const textX = margin + indent + 5;
    const textMaxW = maxW - indent - 5;
    doc.setFontSize(9);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(30, 41, 59);
    const lines = doc.splitTextToSize(String(text), textMaxW);
    checkPage(lines.length * 4 + 3);
    doc.text('•', bulletX, y);
    doc.text(lines, textX, y);
    y += lines.length * 4 + 2;
  }

  function addHRule(gapBefore = 3, gapAfter = 5) {
    y += gapBefore;
    checkPage(6);
    doc.setDrawColor(200, 210, 225);
    doc.setLineWidth(0.2);
    doc.line(margin, y, pageW - margin, y);
    y += gapAfter;
  }

  // ── Cover / Header ──────────────────────────────────────────────────────────
  doc.setFillColor(15, 23, 42);
  doc.rect(0, 0, pageW, 28, 'F');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(15);
  doc.setTextColor(255, 255, 255);
  doc.text('AI-CDSS — Clinical Report', margin, 12);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(180, 200, 230);
  doc.text(`${reportType}  ·  ${new Date().toLocaleString()}`, margin, 20);
  if (dateFrom || dateTo) {
    doc.text(`Date range: ${dateFrom || '—'} to ${dateTo || '—'}`, margin, 25);
  }
  y = 36;

  // ── Patient Information ─────────────────────────────────────────────────────
  addHeading('Patient Information');
  const nm = patientDisplayName(patient);
  const patRows = [
    ['Name', nm],
    ['MRN', patient?.mrn ?? '—'],
    ['Patient ID', patient?.id ?? '—'],
    ['Gender', patient?.gender ?? '—'],
    ['Date of Birth', patient?.date_of_birth ?? '—'],
    ['Blood Type', patient?.blood_type ?? '—'],
    ['Age', patient?.age != null ? `${patient.age} years` : '—'],
    ['Phone', patient?.phone ?? '—'],
  ];
  const colW = maxW / 2;
  for (let i = 0; i < patRows.length; i += 2) {
    const [l1, v1] = patRows[i];
    const [l2, v2] = patRows[i + 1] || ['', ''];
    checkPage(8);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9);
    doc.setTextColor(100, 116, 139);
    doc.text(l1, margin, y);
    if (l2) doc.text(l2, margin + colW, y);
    y += 4;
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(15, 23, 42);
    doc.text(String(v1), margin, y);
    if (v2) doc.text(String(v2), margin + colW, y);
    y += 6;
  }

  // ── Known Conditions ────────────────────────────────────────────────────────
  const condList = Array.isArray(conditions) ? conditions : [];
  if (condList.length > 0 && reportType !== 'Prescription History') {
    addHRule();
    addHeading('Known Medical Conditions');
    condList.forEach((c) => {
      const name = c.condition || String(c);
      const icd  = c.icd_code ? `  [${c.icd_code}]` : '';
      addBullet(name + icd);
    });
  }

  // ── Allergies ───────────────────────────────────────────────────────────────
  const allergyList = Array.isArray(allergies) ? allergies : [];
  if (allergyList.length > 0) {
    addHRule();
    addHeading('Allergies', [185, 28, 28]);
    allergyList.forEach((a) => {
      const allergen  = a.allergen || String(a);
      const severity  = a.severity ? `Severity: ${a.severity}` : '';
      const reaction  = a.reaction ? `Reaction: ${a.reaction}` : '';
      const detail    = [severity, reaction].filter(Boolean).join(' · ');
      addBullet(`${allergen}${detail ? ' — ' + detail : ''}`);
    });
  }

  // ── Diagnoses ───────────────────────────────────────────────────────────────
  const dxList = Array.isArray(diagnoses) ? diagnoses : [];
  if (reportType !== 'Prescription History' && dxList.length > 0) {
    addHRule();
    addHeading('Diagnoses');
    dxList.forEach((d, idx) => {
      checkPage(18);
      const name = d.condition || d.diagnosis_name || '—';
      const icd  = d.icd || d.diagnosis_code || '—';
      const conf = d.confidence ?? d.confidence_score;
      const dt   = d.date || (d.diagnosed_at && String(d.diagnosed_at).split('T')[0]) || '—';
      const src  = d.source || '—';
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(10);
      doc.setTextColor(15, 23, 42);
      const lines = doc.splitTextToSize(`${idx + 1}. ${name}`, maxW);
      doc.text(lines, margin, y);
      y += lines.length * 5 + 1;
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(9);
      doc.setTextColor(100, 116, 139);
      doc.text(`ICD-10: ${icd}  ·  Confidence: ${conf != null ? conf + '%' : '—'}  ·  Date: ${dt}  ·  Source: ${src}`, margin + 4, y);
      y += 6;
    });
  }

  // ── Prescriptions & Medication Details ─────────────────────────────────────
  const rxList = Array.isArray(prescriptions) ? prescriptions : [];
  if (reportType !== 'Diagnostic Report' && rxList.length > 0) {
    addHRule();
    addHeading('Prescriptions & Medications');
    rxList.forEach((r, idx) => {
      checkPage(24);
      const drug  = r.drug_name || r.drug || '—';
      const dose  = r.dose ?? '—';
      const freq  = r.frequency || r.freq || '—';
      const dur   = r.duration ?? '—';
      const route = r.route ?? '—';
      const dt    = r.date || (r.prescribed_at && String(r.prescribed_at).split('T')[0]) || '—';
      const status = r.status || r.safety_status || 'Active';

      doc.setFont('helvetica', 'bold');
      doc.setFontSize(10);
      doc.setTextColor(15, 23, 42);
      doc.text(`${idx + 1}. ${drug}`, margin, y);
      y += 5;

      doc.setFont('helvetica', 'normal');
      doc.setFontSize(9);
      doc.setTextColor(100, 116, 139);
      doc.text(`Dose: ${dose}  ·  Frequency: ${freq}  ·  Duration: ${dur}  ·  Route: ${route}  ·  Date: ${dt}  ·  Status: ${status}`, margin + 4, y);
      y += 5;

      // Drug-specific guidance
      const note = getDrugNote(drug);
      if (note) {
        doc.setTextColor(30, 80, 160);
        const noteLines = doc.splitTextToSize(`ℹ  ${note}`, maxW - 8);
        checkPage(noteLines.length * 4 + 4);
        doc.text(noteLines, margin + 4, y);
        y += noteLines.length * 4 + 2;
      }

      if (r.notes) {
        doc.setTextColor(60, 80, 60);
        const nlines = doc.splitTextToSize(`Notes: ${r.notes}`, maxW - 8);
        checkPage(nlines.length * 4 + 2);
        doc.text(nlines, margin + 4, y);
        y += nlines.length * 4 + 2;
      }
      y += 2;
    });
  }

  // ── Dietary Recommendations ─────────────────────────────────────────────────
  const allDx = [...dxList, ...condList.map(c => ({ condition: c.condition || String(c) }))];
  const dietRules = getDietaryRecommendations(allDx);

  if (dietRules.length > 0 && reportType !== 'Prescription History') {
    addHRule();
    addHeading('Dietary & Lifestyle Recommendations', [14, 100, 60]);

    dietRules.forEach((rule) => {
      addSubheading(`${rule.title}`);

      doc.setFont('helvetica', 'bold');
      doc.setFontSize(9);
      doc.setTextColor(185, 28, 28);
      checkPage(6);
      doc.text('Foods / Substances to AVOID:', margin + 2, y);
      y += 5;
      rule.avoid.forEach((item) => addBullet(item));

      y += 2;
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(9);
      doc.setTextColor(14, 100, 60);
      checkPage(6);
      doc.text('Recommended:', margin + 2, y);
      y += 5;
      rule.recommend.forEach((item) => addBullet(item));
      y += 4;
    });
  }

  // ── Fallback if truly empty ─────────────────────────────────────────────────
  if (dxList.length === 0 && rxList.length === 0 && condList.length === 0) {
    addHRule();
    addHeading('Clinical Data');
    addText(9, 'No diagnoses, prescriptions, or conditions recorded for this patient in the database.');
  }

  // ── Footer ──────────────────────────────────────────────────────────────────
  addHRule(6, 4);
  doc.setFont('helvetica', 'italic');
  doc.setFontSize(8);
  doc.setTextColor(148, 163, 184);
  const footer =
    'This report is generated by the AI-CDSS demo for educational purposes only. ' +
    'It does not replace professional medical judgment, documentation, or signed clinical records. ' +
    `Generated: ${new Date().toLocaleString()}`;
  const fLines = doc.splitTextToSize(footer, maxW);
  checkPage(fLines.length * 4 + 6);
  doc.text(fLines, margin, y);

  const fn = `CDSS_${safeFilename(nm)}_${new Date().toISOString().slice(0, 10)}.pdf`;
  doc.save(fn);
}
