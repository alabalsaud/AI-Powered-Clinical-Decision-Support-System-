import { useState, useEffect } from 'react';
import { Steps, ConfBar } from '../components/UI.jsx';
import AiDiagnosisLogo from '../components/AiDiagnosisLogo.jsx';
import { diagnoses as diagnosesApi } from '../api.js';
import { diagnosePatient, runClinicalPipeline } from '../api/cdssApi.js';
import { patientMatchesSearch } from '../utils/patientSearch.js';

/** Rule engine: avoid false ACS from phrases like "No shortness of breath" (substring "shortness"). */
function likelyCardiacSymptoms(symptoms, troponin) {
  if ((parseFloat(troponin) || 0) > 0) return true;
  const raw = symptoms || '';
  const s = raw.toLowerCase();
  const deniesSob =
    /\bno\s+shortness\s+of\s+breath\b|\bno\s+dyspnea\b|denies\s+(?:any\s+)?(?:shortness|dyspnea|sob)\b|without\s+(?:any\s+)?(?:shortness|dyspnea)\b/i.test(
      raw
    );
  const hasSob =
    !deniesSob &&
    (/\bshortness\s+of\s+breath\b/.test(s) ||
      /\bdyspnea\b/.test(s) ||
      /\bdifficulty\s+breathing\b/.test(s) ||
      (/\bsob\b/i.test(raw) && !/\bno\s+sob\b/i.test(raw)));
  const deniesChest =
    /\bno\s+chest\s+pain\b|denies\s+chest\s+pain|without\s+chest\s+pain|non[-\s]?cardiac\s+chest/i.test(raw);
  const hasChest =
    !deniesChest &&
    (/\bchest\s+pain\b/.test(s) ||
      /\bangina\b/.test(s) ||
      /\bsubsternal\b/.test(s) ||
      /\bpressing\s+chest\b/.test(s));
  return hasChest || hasSob;
}

function buildDxResults(symptoms, lab) {
  const s = (symptoms || '').toLowerCase();
  const glucose = parseFloat(lab.glucose) || 0;
  const hba1c = parseFloat(lab.hba1c) || 0;
  const troponin = parseFloat(lab.troponin) || 0;

  if (
    s.includes('thirst') ||
    s.includes('urin') ||
    s.includes('fatigue') ||
    glucose > 140 ||
    hba1c > 6.5
  ) {
    return [
      {
        rank: 1,
        name: 'Type 2 Diabetes Mellitus',
        icd: 'E11.9',
        confidence: 92,
        evidence:
          'Elevated blood glucose, polydipsia, polyuria, fatigue. HbA1c ≥6.5% is diagnostic per ADA 2024.',
        factors: [
          { n: 'Blood Glucose', v: 88 },
          { n: 'HbA1c', v: 92 },
          { n: 'Symptoms', v: 85 },
          { n: 'BMI', v: 61 },
          { n: 'Family Hx', v: 70 },
        ],
      },
      {
        rank: 2,
        name: 'Metabolic Syndrome',
        icd: 'E88.81',
        confidence: 71,
        evidence:
          'Concurrent hypertension and elevated glucose suggest metabolic syndrome.',
        factors: [
          { n: 'Glucose', v: 75 },
          { n: 'BP', v: 68 },
          { n: 'Waist Circ.', v: 55 },
        ],
      },
      {
        rank: 3,
        name: 'Prediabetes / IGT',
        icd: 'R73.09',
        confidence: 48,
        evidence:
          'Borderline values possible but HbA1c is diagnostic for overt DM.',
        factors: [
          { n: 'HbA1c', v: 45 },
          { n: 'FPG', v: 50 },
        ],
      },
      {
        rank: 4,
        name: 'Type 1 Diabetes Mellitus',
        icd: 'E10.9',
        confidence: 34,
        evidence:
          'Autoimmune etiology less likely given gradual onset and age.',
        factors: [
          { n: 'Autoimmune markers', v: 20 },
          { n: 'Age at onset', v: 18 },
        ],
      },
      {
        rank: 5,
        name: 'Cushing Syndrome',
        icd: 'E24.9',
        confidence: 12,
        evidence:
          'Secondary cause of hyperglycaemia — low probability without other features.',
        factors: [{ n: 'Cortisol', v: 15 }],
      },
    ];
  }

  if (likelyCardiacSymptoms(symptoms, troponin)) {
    return [
      {
        rank: 1,
        name: 'Acute Coronary Syndrome',
        icd: 'I24.9',
        confidence: 78,
        evidence:
          'Chest pain, ECG changes, elevated troponin. Requires urgent cardiology review (ACC/AHA 2021).',
        factors: [
          { n: 'Troponin', v: 85 },
          { n: 'ECG changes', v: 80 },
          { n: 'Pain character', v: 72 },
          { n: 'Risk factors', v: 68 },
        ],
      },
      {
        rank: 2,
        name: 'Stable Angina',
        icd: 'I20.9',
        confidence: 65,
        evidence:
          'Exertional chest pain pattern consistent with stable coronary disease.',
        factors: [
          { n: 'Exercise-related', v: 70 },
          { n: 'Duration', v: 60 },
        ],
      },
      {
        rank: 3,
        name: 'GERD',
        icd: 'K21.0',
        confidence: 30,
        evidence: 'Atypical discomfort — less likely given risk profile.',
        factors: [{ n: 'Burning quality', v: 35 }],
      },
    ];
  }

  return [
    {
      rank: 1,
      name: 'Viral Upper Respiratory Infection',
      icd: 'J06.9',
      confidence: 74,
      evidence:
        'Symptoms consistent with viral URI. No alarming features identified.',
      factors: [
        { n: 'Symptom pattern', v: 80 },
        { n: 'Duration', v: 65 },
        { n: 'Fever', v: 55 },
      ],
    },
    {
      rank: 2,
      name: 'Bacterial Sinusitis',
      icd: 'J01.90',
      confidence: 52,
      evidence:
        'Purulent discharge and facial pain may suggest bacterial sinusitis.',
      factors: [
        { n: 'Nasal discharge', v: 60 },
        { n: 'Duration >7d', v: 50 },
      ],
    },
    {
      rank: 3,
      name: 'Allergic Rhinitis',
      icd: 'J30.9',
      confidence: 45,
      evidence: 'Allergic history increases probability.',
      factors: [
        { n: 'Allergy history', v: 50 },
        { n: 'Triggers', v: 40 },
      ],
    },
  ];
}

// ── XAI Horizontal Bar Chart ─────────────────────────────────────────────────
// Renders each SHAP/LIME factor as a horizontal bar.
// Bars are colour-coded: green ≥70, amber 40–69, red <40.
function XAIBarChart({ factors }) {
  if (!Array.isArray(factors) || factors.length === 0) return null;

  // Sort descending so the most influential factor is on top
  const sorted = [...factors].sort((a, b) => b.v - a.v);
  const maxVal  = Math.max(...sorted.map((f) => f.v), 1);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {sorted.map((f, i) => {
        const pct     = Math.round((f.v / maxVal) * 100);   // bar width relative to max
        const barColor =
          f.v >= 70 ? 'var(--success, #22c55e)'
          : f.v >= 40 ? 'var(--warning, #f59e0b)'
          : 'var(--danger, #ef4444)';

        return (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {/* label */}
            <div
              style={{
                width: 110,
                minWidth: 110,
                fontSize: 11,
                color: 'var(--text2, #94a3b8)',
                textAlign: 'right',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
              title={f.n}
            >
              {f.n}
            </div>

            {/* bar track */}
            <div
              style={{
                flex: 1,
                height: 14,
                borderRadius: 7,
                background: 'var(--surface3, rgba(255,255,255,0.06))',
                overflow: 'hidden',
                position: 'relative',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${pct}%`,
                  borderRadius: 7,
                  background: barColor,
                  transition: 'width 0.5s ease',
                }}
              />
            </div>

            {/* value label */}
            <div
              style={{
                width: 34,
                minWidth: 34,
                fontSize: 11,
                fontFamily: 'var(--font-mono, monospace)',
                fontWeight: 700,
                color: barColor,
                textAlign: 'right',
              }}
            >
              {f.v}%
            </div>
          </div>
        );
      })}
    </div>
  );
}

const STEP_LABELS = [
  'Select Patient',
  'Clinical Data',
  'AI Analysis',
  'Review & Confirm',
];

// ── Pipeline Results Panels ───────────────────────────────────────────────────

// ── Drug reason lookup — plain English explanation for common medicines ────────
const DRUG_REASONS = {
  // Cardiac
  'aspirin':       'Aspirin prevents blood clots from forming inside arteries, reducing the risk of another heart attack or stroke.',
  'atenolol':      'Atenolol is a beta-blocker that slows the heart rate and lowers blood pressure, giving the heart less work to do after a heart attack.',
  'metoprolol':    'Metoprolol slows the heart rate and reduces blood pressure, protecting the heart muscle from further damage.',
  'carvedilol':    'Carvedilol helps the heart beat more efficiently and reduces strain on the heart muscle.',
  'lisinopril':    'Lisinopril relaxes blood vessels so the heart does not have to pump as hard. It also protects the kidneys in diabetic patients.',
  'ramipril':      'Ramipril relaxes blood vessels, lowers blood pressure, and helps the heart recover after injury.',
  'enalapril':     'Enalapril lowers blood pressure and reduces the workload on the heart.',
  'amlodipine':    'Amlodipine relaxes and widens blood vessels, making it easier for the heart to pump and lowering blood pressure.',
  'atorvastatin':  'Atorvastatin lowers bad cholesterol (LDL) in the blood, which reduces the buildup of fatty plaques in arteries and lowers heart attack risk.',
  'rosuvastatin':  'Rosuvastatin reduces bad cholesterol and helps keep arteries clear and healthy.',
  'simvastatin':   'Simvastatin lowers cholesterol levels to reduce the risk of blocked arteries and heart attack.',
  'clopidogrel':   'Clopidogrel prevents blood clots by stopping platelets from sticking together inside blood vessels.',
  'warfarin':      'Warfarin is a blood thinner that prevents dangerous clots from forming or growing larger.',
  'heparin':       'Heparin is an injectable blood thinner used to quickly stop dangerous clot formation.',
  'nitroglycerin': 'Nitroglycerin quickly widens blood vessels to relieve chest pain by improving blood flow to the heart.',
  'furosemide':    'Furosemide is a water tablet (diuretic) that removes excess fluid from the body, reducing swelling and easing the heart\'s workload.',
  'spironolactone':'Spironolactone removes excess fluid and salt from the body, and also protects the heart after a heart attack.',
  'digoxin':       'Digoxin helps the heart beat more slowly and with more force, improving blood flow in heart failure.',

  // Diabetes
  'metformin':     'Metformin is the first-choice medicine for type 2 diabetes. It lowers blood sugar by reducing sugar production in the liver.',
  'insulin':       'Insulin is a hormone that moves sugar from the blood into body cells where it is used for energy.',
  'glipizide':     'Glipizide stimulates the pancreas to release more insulin, helping to lower blood sugar levels.',
  'gliclazide':    'Gliclazide helps the pancreas produce more insulin to control blood sugar levels.',
  'sitagliptin':   'Sitagliptin helps the body produce more insulin after meals and lowers the amount of sugar the liver releases.',
  'empagliflozin': 'Empagliflozin removes excess sugar from the body through the urine. It also protects the heart and kidneys.',
  'dapagliflozin': 'Dapagliflozin helps the kidneys remove excess sugar from the blood through urine.',
  'liraglutide':   'Liraglutide helps control blood sugar, reduces appetite, and protects the heart in people with diabetes.',

  // Thyroid
  'levothyroxine': 'Levothyroxine replaces the thyroid hormone that the thyroid gland is not making enough of. It is taken for life in hypothyroidism.',
  'carbimazole':   'Carbimazole slows down an overactive thyroid gland, preventing it from making too much thyroid hormone.',

  // Mental health
  'sertraline':    'Sertraline (an SSRI) balances chemicals in the brain that affect mood, helping to relieve depression and anxiety.',
  'fluoxetine':    'Fluoxetine balances serotonin in the brain, improving mood, sleep, and energy in depression.',
  'escitalopram':  'Escitalopram improves mood by increasing serotonin levels in the brain. It is used for depression and anxiety.',
  'amitriptyline': 'Amitriptyline improves mood by balancing brain chemicals. It is also used for nerve pain and sleep problems.',
  'quetiapine':    'Quetiapine balances brain chemicals to treat severe mood disorders, bipolar disorder, and schizophrenia.',

  // Antibiotics
  'amoxicillin':   'Amoxicillin is an antibiotic that kills the bacteria causing the infection.',
  'azithromycin':  'Azithromycin is an antibiotic used for chest infections, ear infections, and some sexually transmitted infections.',
  'ciprofloxacin': 'Ciprofloxacin is a broad antibiotic that kills a wide range of harmful bacteria.',
  'doxycycline':   'Doxycycline is an antibiotic used for chest infections, skin infections, and some tick-borne diseases.',

  // Pain / Inflammation
  'ibuprofen':     'Ibuprofen reduces pain, fever, and swelling by blocking chemicals that cause inflammation.',
  'paracetamol':   'Paracetamol relieves mild to moderate pain and reduces fever. It is safe for most people.',
  'naproxen':      'Naproxen is an anti-inflammatory medicine that relieves pain and swelling.',
  'prednisolone':  'Prednisolone is a steroid that reduces severe inflammation and calms overactive immune reactions.',

  // Respiratory
  'salbutamol':    'Salbutamol quickly opens the airways during an asthma attack or breathing difficulty.',
  'montelukast':   'Montelukast reduces airway inflammation and prevents asthma symptoms and allergic reactions.',
  'tiotropium':    'Tiotropium opens the airways and helps people with COPD breathe more easily.',

  // GI
  'omeprazole':    'Omeprazole reduces stomach acid, which helps heal ulcers and prevents acid reflux damage.',
  'pantoprazole':  'Pantoprazole lowers stomach acid to treat acid reflux, ulcers, and stomach damage from other medicines.',
  'ondansetron':   'Ondansetron stops nausea and vomiting by blocking signals in the brain that trigger the feeling of sickness.',
};

function getDrugReason(drugName) {
  if (!drugName) return null;
  const key = drugName.toLowerCase().replace(/\s+\d.*/, '').trim();
  for (const [k, v] of Object.entries(DRUG_REASONS)) {
    if (key.includes(k)) return v;
  }
  return null;
}

// ── Layman-friendly pipeline results ─────────────────────────────────────────
function PipelineResultPanels({ result }) {
  const meds  = result.medication_groups || [];
  const score = result.qa_scores || {};
  const overall = result.overall_score ?? 0;

  // Plain-English verdict based on overall score
  const verdict =
    overall >= 80 ? { label: 'Highly Reliable', color: '#34d399', bg: 'rgba(52,211,153,0.10)', border: 'rgba(52,211,153,0.30)', icon: '✅', desc: 'The AI is very confident. A doctor can review and confirm this with high trust.' }
    : overall >= 60 ? { label: 'Moderately Reliable', color: '#fbbf24', bg: 'rgba(251,191,36,0.10)', border: 'rgba(251,191,36,0.30)', icon: '⚠️', desc: 'The AI gave a reasonable result but a doctor should carefully review before deciding.' }
    : { label: 'Needs Doctor Review', color: '#f87171', bg: 'rgba(248,113,113,0.10)', border: 'rgba(248,113,113,0.30)', icon: '🔴', desc: 'The result is uncertain. Please consult a doctor before taking any action.' };

  const urgencyColor = result.urgency === 'critical' ? '#f87171' : result.urgency === 'urgent' ? '#fbbf24' : '#34d399';
  const urgencyLabel = result.urgency === 'critical' ? 'Urgent — See a doctor immediately' : result.urgency === 'urgent' ? 'See a doctor today' : 'Routine — Book an appointment';

  const checks = [
    { label: 'How sure is the AI about this diagnosis?', value: score.diagnosis_confidence ?? 0, hint: 'Higher = AI is more confident in the suggested diagnosis' },
    { label: 'How well do the symptoms match?',          value: score.symptom_coverage ?? 0,    hint: 'Higher = more of the patient\'s symptoms are explained by this diagnosis' },
    { label: 'Are the medicines safe to prescribe?',     value: score.medication_safety ?? 0,   hint: 'Higher = the suggested medicines were checked and are safe for this patient' },
    { label: 'Are the medical codes correct?',           value: score.icd_validity ?? 0,        hint: 'Higher = all diagnosis codes are valid and recognized internationally' },
    { label: 'No medicine conflicts with allergies?',    value: score.allergy_safety ?? 0,      hint: 'Higher = no suggested medicine will trigger the patient\'s known allergies' },
  ];

  return (
    <div className="pipe-panel">

      {/* ── Gradient header card: verdict + urgency + score ─── */}
      <div className="pipe-hero" style={{
        background: `linear-gradient(135deg, ${verdict.color}22 0%, ${verdict.color}08 100%)`,
        borderColor: verdict.color + '44',
      }}>
        <div className="pipe-hero-left">
          <div className="pipe-hero-icon">{verdict.icon}</div>
          <div>
            <div className="pipe-hero-label">AI Analysis Result</div>
            <div className="pipe-hero-verdict" style={{ color: verdict.color }}>{verdict.label}</div>
            <div className="pipe-hero-desc">{verdict.desc}</div>
            <div className="pipe-hero-urgency" style={{ color: urgencyColor, borderColor: urgencyColor + '55', background: urgencyColor + '14' }}>
              <svg viewBox="0 0 24 24" fill="none" stroke={urgencyColor} strokeWidth="2.5" width="13" height="13"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              {urgencyLabel}
            </div>
          </div>
        </div>
        <div className="pipe-hero-scores">
          <div className="pipe-hero-score-item">
            <div className="pipe-hero-score-num" style={{ color: verdict.color }}>{overall}%</div>
            <div className="pipe-hero-score-lbl">Overall</div>
          </div>
          <div className="pipe-hero-score-divider" />
          <div className="pipe-hero-score-item">
            <div className="pipe-hero-score-num" style={{ color: '#a78bfa' }}>{score.diagnosis_confidence ?? 0}%</div>
            <div className="pipe-hero-score-lbl">AI Confidence</div>
          </div>
        </div>
      </div>

      {/* ── Compact 5-check grid ─────────────────────────────── */}
      <div className="pipe-grid-card">
        <div className="pipe-grid-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="13" height="13"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
          Safety Checks
        </div>
        <div className="pipe-grid">
          {checks.map((c, i) => {
            const color = c.value >= 80 ? '#34d399' : c.value >= 50 ? '#fbbf24' : '#f87171';
            const StatusIcon = c.value >= 80
              ? () => <svg viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg>
              : c.value >= 50
              ? () => <svg viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" width="14" height="14"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
              : () => <svg viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" width="14" height="14"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>;
            return (
              <div key={i} className="pipe-grid-item" style={{ borderColor: color + '30', background: color + '0a' }}>
                <div className="pipe-grid-item-top">
                  <StatusIcon />
                  <span className="pipe-grid-pct" style={{ color }}>{c.value}%</span>
                </div>
                <div className="pipe-grid-item-label">{c.label}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Medicines section ───────────────────────────────── */}
      {meds.length > 0 && (
        <div className="pipe-meds-card">
          <div className="pipe-meds-header">
            <div className="pipe-meds-header-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="18" height="18"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>
            </div>
            <div>
              <div className="pipe-meds-header-title">Recommended Medicines</div>
              <div className="pipe-meds-header-sub">Checked against patient allergies and medical history</div>
            </div>
          </div>

          <div className="pipe-meds-inner">
          {/* Summary pills */}
          <div className="pipe-med-summary">
            <span className="pipe-med-pill pipe-med-pill--safe">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" width="11" height="11"><polyline points="20 6 9 17 4 12"/></svg>
              {result.total_safe_drugs ?? 0} Safe
            </span>
            {(result.total_warned_drugs ?? 0) > 0 && (
              <span className="pipe-med-pill pipe-med-pill--warn">⚠ {result.total_warned_drugs} Use with Caution</span>
            )}
            {(result.total_blocked_drugs ?? 0) > 0 && (
              <span className="pipe-med-pill pipe-med-pill--blocked">🚫 {result.total_blocked_drugs} Cannot Use (Allergy)</span>
            )}
          </div>

          {meds.map((grp, gi) => (
            <div key={gi} className="pipe-med-group">
              <div className="pipe-med-group-name">{grp.matched_on}</div>
              <div className="pipe-med-group-reason">{grp.rationale}</div>

              {(grp.drugs_safe || []).map((d, di) => {
                const reason = d.reason || d.rationale || getDrugReason(d.name);
                return (
                  <div key={di} className="pipe-drug pipe-drug--safe">
                    <div className="pipe-drug-top">
                      <span className="pipe-drug-name">{d.name}</span>
                      <span className="pipe-drug-badge pipe-drug-badge--safe">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" width="10" height="10"><polyline points="20 6 9 17 4 12"/></svg>
                        Safe to use
                      </span>
                    </div>
                    <div className="pipe-drug-dosing">
                      <span className="pipe-drug-dosing-item">💊 {d.dose}</span>
                      <span className="pipe-drug-dosing-item">🕐 {d.frequency}</span>
                      <span className="pipe-drug-dosing-item">📋 {d.route}</span>
                      <span className="pipe-drug-line">{d.line === 'first' ? '1st choice' : '2nd choice'}</span>
                    </div>
                    {reason && (
                      <div className="pipe-drug-reason">
                        <span className="pipe-drug-reason-icon">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="12" height="12"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                        </span>
                        <span><b>Why this medicine?</b> {reason}</span>
                      </div>
                    )}
                  </div>
                );
              })}
              {(grp.drugs_warned || []).map((d, di) => {
                const reason = d.reason || d.rationale || getDrugReason(d.name);
                return (
                  <div key={`w${di}`} className="pipe-drug pipe-drug--warn">
                    <div className="pipe-drug-top">
                      <span className="pipe-drug-name">{d.name}</span>
                      <span className="pipe-drug-badge pipe-drug-badge--warn">⚠ Use with caution</span>
                    </div>
                    <div className="pipe-drug-dosing">
                      <span className="pipe-drug-dosing-item">💊 {d.dose}</span>
                      <span className="pipe-drug-dosing-item">🕐 {d.frequency}</span>
                    </div>
                    {reason && (
                      <div className="pipe-drug-reason pipe-drug-reason--warn">
                        <span className="pipe-drug-reason-icon">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="12" height="12"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                        </span>
                        <span><b>Why this medicine?</b> {reason}</span>
                      </div>
                    )}
                    <div className="pipe-drug-warn-note">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="12" height="12"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                      <b>Caution:</b> {(d.warn_reasons || []).join('; ')}
                    </div>
                  </div>
                );
              })}
              {(grp.drugs_blocked || []).map((d, di) => (
                <div key={`b${di}`} className="pipe-drug pipe-drug--blocked">
                  <div className="pipe-drug-top">
                    <span className="pipe-drug-name" style={{ textDecoration: 'line-through', opacity: 0.6 }}>{d.name}</span>
                    <span className="pipe-drug-badge pipe-drug-badge--blocked">🚫 Cannot use — Allergy</span>
                  </div>
                  <div className="pipe-drug-blocked-note">
                    This medicine was <b>automatically blocked</b> because it conflicts with the patient's known allergies. The doctor must <b>not prescribe</b> this.
                    {(d.block_reasons || []).length > 0 && (
                      <span> Reason: {d.block_reasons.join('; ')}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ))}
          </div>{/* end pipe-meds-inner */}
        </div>
      )}

      {/* ── Verification notes ──────────────────────────────── */}
      {(result.verification_notes || []).length > 0 && (
        <div className="pipe-notes-card">
          <div className="pipe-checks-title" style={{ marginBottom: 8 }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            Doctor Notes
          </div>
          {result.verification_notes.map((n, i) => (
            <div key={i} className="pipe-note-item">• {n}</div>
          ))}
        </div>
      )}
    </div>
  );
}

function normalizePatient(p) {
  const fullName =
    p?.name ||
    p?.full_name ||
    `${p?.first_name || ''} ${p?.last_name || ''}`.trim() ||
    'Unknown Patient';

  const age =
    p?.age ??
    (p?.date_of_birth
      ? new Date().getFullYear() - new Date(p.date_of_birth).getFullYear()
      : 'N/A');

  const conditions = Array.isArray(p?.conditions)
    ? p.conditions
    : Array.isArray(p?.medical_histories)
      ? p.medical_histories.map((c) => c.condition).filter(Boolean)
      : [];

  const allergies = Array.isArray(p?.allergies)
    ? p.allergies
        .map((a) => (typeof a === 'string' ? a : a?.allergen))
        .filter(Boolean)
    : [];

  return {
    ...p,
    name: fullName,
    age,
    gender: p?.gender || 'N/A',
    conditions,
    allergies,
  };
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function termsFromText(text) {
  return String(text || '')
    .split(/[\n,;]+|(?:\s+and\s+)|(?:\s+or\s+)/i)
    .map((term) => term.trim())
    .filter((term) => term.length > 2);
}

function cleanClinicalNotes(notes, symptoms, conditions = []) {
  if (!notes?.trim()) return notes || '';

  const terms = new Set();
  termsFromText(symptoms).forEach((term) => terms.add(term));

  if (Array.isArray(conditions)) {
    conditions
      .map((c) => (typeof c === 'string' ? c : c?.condition || ''))
      .map((term) => term.trim())
      .filter((term) => term.length > 2)
      .forEach((term) => terms.add(term));
  }

  let cleaned = String(notes);
  for (const term of [...terms].sort((a, b) => b.length - a.length)) {
    const escaped = escapeRegExp(term);
    const regex = new RegExp(`\\b${escaped}\\b`, 'gi');
    cleaned = cleaned.replace(regex, '');
  }

  cleaned = cleaned
    .replace(/\s{2,}/g, ' ')
    .replace(/,\s*,/g, ',')
    .replace(/\b(?:and|or)\b[\s,]*(?=$|[.,;!?])/gi, '')
    .replace(/([,;:.!?])\s*([,;:.!?]+)/g, '$1')
    .replace(/\s+([,;:.!?])/g, '$1')
    .replace(/([,;:.!?])([^\s])/g, '$1 $2')
    .replace(/\s{2,}/g, ' ')
    .trim();

  return cleaned;
}

export default function DiagnosisEngine({
  patients = [],
  patientSearch = '',
  diagnoses,
  setDiagnoses,
  selectedPatient,
  setSelectedPatient,
  showLoading,
  setPage,
  backendOk,
}) {
  const [step, setStep] = useState(0);
  const [selPt, setSelPt] = useState(
    selectedPatient ? normalizePatient(selectedPatient) : null
  );
  const [symptoms, setSymptoms] = useState('');
  const [notes, setNotes] = useState('');
  const [lab, setLab] = useState({
    glucose: '',
    hba1c: '',
    wbc: '',
    creatinine: '',
    troponin: '',
  });
  const [results, setResults] = useState(null);
  const [selDx, setSelDx] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [llmReady, setLlmReady] = useState(false);
  const [llmModel, setLlmModel] = useState('');
  const [lastRunSource, setLastRunSource] = useState(null); // 'llm' | 'rules'
  const [analysisError, setAnalysisError] = useState(null);

  // ── Pipeline state ──────────────────────────────────────────────────────────
  const [pipelineResult, setPipelineResult] = useState(null);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineError, setPipelineError] = useState(null);
  const [pipelineStep, setPipelineStep] = useState(-1); // 0-4 during run, 5 = done

  useEffect(() => {
    let cancelled = false;
    diagnosesApi
      .llmStatus()
      .then((s) => {
        if (!cancelled && s?.configured) {
          setLlmReady(true);
          setLlmModel(s.model || '');
        }
      })
      .catch(() => {
        if (!cancelled) setLlmReady(false);
      });
    return () => { cancelled = true; };
  }, []);

  const normalizedPatients = Array.isArray(patients)
    ? patients.map(normalizePatient)
    : [];
  const visiblePatients = normalizedPatients.filter((p) =>
    patientMatchesSearch(p, patientSearch, { includeConditions: false })
  );

  function setL(k) {
    return (e) => setLab((prev) => ({ ...prev, [k]: e.target.value }));
  }

  async function runAnalysis() {
    setAnalysisError(null);
    setStep(2);
    const pt = selPt ? normalizePatient(selPt) : null;

    let rows = buildDxResults(symptoms, lab);
    let source = 'rules';

    if (pt) {
      const cleanedNotes = cleanClinicalNotes(notes, symptoms, pt.conditions);
      const payload = {
        patient_id: pt.id,
        patient_name: pt.name,
        age: String(pt.age ?? ''),
        gender: String(pt.gender ?? ''),
        conditions: Array.isArray(pt.conditions) ? pt.conditions : [],
        allergies: Array.isArray(pt.allergies) ? pt.allergies : [],
        symptoms,
        clinical_notes: cleanedNotes || null,
        lab: {
          glucose: lab.glucose || null,
          hba1c: lab.hba1c || null,
          wbc: lab.wbc || null,
          creatinine: lab.creatinine || null,
          troponin: lab.troponin || null,
        },
      };

      if (cleanedNotes !== notes) {
        setNotes(cleanedNotes);
      }

      try {
        // Primary: cdssApi.js → diagnosePatient → POST /api/diagnose
        const data = await diagnosePatient(payload);
        if (Array.isArray(data?.suggestions) && data.suggestions.length > 0) {
          rows = data.suggestions.map((d, i) => ({
            rank: d.rank ?? i + 1,
            name: d.name,
            icd: d.icd,
            confidence: d.confidence,
            evidence: d.evidence,
            factors: Array.isArray(d.factors) && d.factors.length
              ? d.factors.map((f) => ({ n: f.n, v: f.v }))
              : [{ n: 'Clinical fit', v: 50 }],
          }));
          source = data.llm_used ? 'llm' : 'rules';
        }
      } catch (cdssErr) {
        // Secondary fallback: legacy LLM endpoint (requires OPENAI_API_KEY)
        if (llmReady) {
          try {
            const data = await diagnosesApi.llmSuggest(payload);
            if (Array.isArray(data?.suggestions) && data.suggestions.length > 0) {
              rows = data.suggestions.map((d, i) => ({
                rank: d.rank ?? i + 1,
                name: d.name,
                icd: d.icd,
                confidence: d.confidence,
                evidence: d.evidence,
                factors: Array.isArray(d.factors) && d.factors.length
                  ? d.factors.map((f) => ({ n: f.n, v: f.v }))
                  : [{ n: 'Clinical fit', v: 50 }],
              }));
              source = 'llm';
            }
          } catch (e) {
            rows = buildDxResults(symptoms, lab);
            source = 'rules';
            const msg = e?.message || cdssErr?.message || 'AI diagnosis request failed';
            setAnalysisError(`${msg} — showing rule-based results.`);
          }
        } else {
          const msg = cdssErr?.message || 'Could not reach the diagnosis API';
          setAnalysisError(`${msg} — showing rule-based results.`);
        }
      }
    } else if (!backendOk) {
      setAnalysisError('Backend offline — using local rule-based results only.');
    }

    setLastRunSource(source);
    setResults(rows);
    setStep(3);
  }

  async function confirmDx() {
    if (!selDx || !selPt) return;

    await showLoading('Saving confirmed diagnosis…', 900);

    const localEntry = {
      id: `DX-${Date.now()}`,
      patientId: selPt.id,
      patient_id: selPt.id,
      condition: selDx.name,
      diagnosis_name: selDx.name,
      icd: selDx.icd,
      diagnosis_code: selDx.icd,
      confidence: selDx.confidence,
      confidence_score: selDx.confidence,
      date: new Date().toISOString().split('T')[0],
      status: 'Confirmed',
      source: 'AI+Physician',
    };

    // Save to backend if available, then merge into local state
    if (backendOk) {
      try {
        const saved = await diagnosesApi.create({
          patient_id: selPt.id,
          diagnosis_name: selDx.name,
          diagnosis_code: selDx.icd,
          confidence_score: selDx.confidence,
          status: 'confirmed',
          source: 'AI+Physician',
        });
        setDiagnoses(prev => [{ ...localEntry, ...saved }, ...prev]);
      } catch {
        // Backend save failed — keep local entry so UI still works
        setDiagnoses(prev => [localEntry, ...prev]);
      }
    } else {
      setDiagnoses(prev => [localEntry, ...prev]);
    }

    // Always update the selected patient so Prescriptions auto-selects them
    setSelectedPatient?.(selPt);
    setConfirmed(true);
  }

  function reset() {
    setStep(0);
    setResults(null);
    setSelDx(null);
    setConfirmed(false);
    setLastRunSource(null);
    setPipelineResult(null);
    setPipelineError(null);
    setPipelineStep(-1);
    setSymptoms('');
    setNotes('');
    setLab({
      glucose: '',
      hba1c: '',
      wbc: '',
      creatinine: '',
      troponin: '',
    });
  }

  // ── Run Full Pipeline ───────────────────────────────────────────────────────
  const PIPELINE_STEP_LABELS = [
    '🔍 Agent 1: Triage & Feature Extraction',
    '🧠 Agent 2: LLM Differential Diagnosis',
    '✅ Agent 3: Verification & Confidence Scoring',
    '💊 Agent 4: Evidence-Based Medications',
    '📊 Agent 5: QA Accuracy Scoring',
  ];

  async function runPipeline() {
    if (!symptoms.trim()) return;
    setPipelineResult(null);
    setAnalysisError(null);
    setPipelineError(null);
    setPipelineLoading(true);
    setStep(2);

    // Animate steps
    const delay = (ms) => new Promise((r) => setTimeout(r, ms));
    for (let i = 0; i < 5; i++) {
      setPipelineStep(i);
      await delay(600);
    }

    const pt = selPt ? normalizePatient(selPt) : null;
    const cleanedNotes = cleanClinicalNotes(notes, symptoms, pt?.conditions);
    const payload = {
      patient_id:     pt?.id || null,
      patient_name:   pt?.name || null,
      age:            pt?.age || null,
      gender:         pt?.gender || null,
      symptoms,
      clinical_notes: cleanedNotes || null,
      medical_history: Array.isArray(pt?.conditions) ? pt.conditions : [],
      allergies:      Array.isArray(pt?.allergies)
                        ? pt.allergies.map((a) => (typeof a === 'string' ? { allergen: a } : a))
                        : [],
      current_meds:   [],
      vitals:         {},
      lab:            {
        glucose:    lab.glucose || null,
        hba1c:      lab.hba1c  || null,
        wbc:        lab.wbc    || null,
        creatinine: lab.creatinine || null,
        troponin:   lab.troponin  || null,
      },
    };

    if (cleanedNotes !== notes) {
      setNotes(cleanedNotes);
    }

    try {
      const result = await runClinicalPipeline(payload);
      setPipelineResult(result);
      setPipelineStep(5);
      // Also populate normal results from verified diagnoses so the rest of the
      // workflow (confirm, save) continues to work.
      const verified = Array.isArray(result.verified_diagnoses)
        ? result.verified_diagnoses
        : [];
      setResults(verified.map((d, i) => ({
        rank:       d.rank ?? i + 1,
        name:       d.name,
        icd:        d.icd,
        confidence: d.confidence,
        evidence:   d.evidence || '',
        factors:    d.factors || [{ n: 'Clinical fit', v: d.confidence || 50 }],
      })));
      setSelDx(null);
      setLastRunSource(result.llm_used ? 'llm' : 'rules');
      setStep(3);
    } catch (err) {
      setPipelineError(err?.response?.data?.detail || err?.message || 'Pipeline failed');
      setStep(1);
    } finally {
      setPipelineLoading(false);
    }
  }

  const confColor = (v) => v >= 75 ? '#34d399' : v >= 50 ? '#fbbf24' : '#f87171';
  const ptInitials = (name) => name?.split(' ').map(w => w[0]).slice(0,2).join('').toUpperCase() || '?';

  /* ── Full-page confirmed screen — no header/steps above ── */
  if (confirmed) {
    const conf   = selDx?.confidence ?? 0;
    const cColor = confColor(conf);
    const today  = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

    return (
      <div className="de-confirmed-fullpage">
        <div className="de-confirmed-card">

          {/* Top glow */}
          <div className="de-confirmed-glow" aria-hidden="true" />

          {/* ── 3-column horizontal layout ─────────────────── */}
          <div className="de-confirmed-hrow">

            {/* LEFT — animated ring + status */}
            <div className="de-confirmed-left">
              <div className="de-confirmed-ring">
                <div className="de-confirmed-ring-pulse" />
                <svg viewBox="0 0 24 24" fill="none" stroke="#34d399" strokeWidth="2.8"
                     width="36" height="36" style={{ position: 'relative', zIndex: 1 }}>
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
              </div>
              <div className="de-confirmed-status-chip">
                <span className="de-confirmed-status-dot" />
                Saved
              </div>
            </div>

            {/* CENTER — diagnosis details */}
            <div className="de-confirmed-center">
              <div className="de-confirmed-eyebrow">Diagnosis Confirmed</div>
              <div className="de-confirmed-dx-name">{selDx?.name}</div>

              <div className="de-confirmed-badges">
                <span className="de-confirmed-icd-badge">ICD-10: {selDx?.icd || '—'}</span>
                <span className="de-confirmed-conf-badge" style={{
                  background: `${cColor}18`, color: cColor, borderColor: `${cColor}40`,
                }}>
                  {conf}% confidence
                </span>
              </div>

              <div className="de-confirmed-meta-row">
                <span className="de-confirmed-meta-item">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="12" height="12">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
                  </svg>
                  {selPt?.name}
                </span>
                <span className="de-confirmed-meta-sep">·</span>
                <span className="de-confirmed-meta-item">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="12" height="12">
                    <rect x="3" y="4" width="18" height="18" rx="2"/>
                    <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
                  </svg>
                  {today}
                </span>
                <span className="de-confirmed-meta-sep">·</span>
                <span className="de-confirmed-meta-item">
                  <AiDiagnosisLogo size={11} />
                  AI + Physician
                </span>
              </div>
            </div>

            {/* RIGHT — action buttons stacked */}
            <div className="de-confirmed-right">
              <button className="de-btn de-btn--primary de-confirmed-btn-rx" onClick={() => {
                setSelectedPatient?.(selPt);
                setPage?.('prescriptions');
              }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                  <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>
                </svg>
                Go to Prescriptions
              </button>
              <button className="de-btn de-btn--view-patient de-confirmed-btn-pt" onClick={() => {
                setSelectedPatient?.(selPt);
                setPage?.('patient_detail');
              }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="13" height="13">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
                </svg>
                View Patient
              </button>
              <button className="de-btn de-btn--ghost de-confirmed-btn-new" onClick={reset}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="13" height="13">
                  <polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.95"/>
                </svg>
                New Diagnosis
              </button>
            </div>
          </div>

        </div>
      </div>
    );
  }

  return (
    <div className="de-root">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="de-header">
        <div className="de-header-left">
          <div className="de-header-icon">
            <AiDiagnosisLogo size={28} className="diagnosis-page-logo" title="AI diagnosis module" />
          </div>
          <div>
            <h1 className="de-title">AI Diagnostic Engine</h1>
            <p className="de-sub">
              {llmReady
                ? `LLM differential diagnosis (${llmModel || 'configured'}) · rule-based fallback`
                : 'Clinical rules engine · add LLM key to enable AI mode'}
            </p>
          </div>
        </div>
        <div className="de-engine-badge">
          <span className="de-engine-dot" />
          {llmReady ? 'LLM Active' : 'Rules Engine'}
        </div>
      </div>

      {/* ── Progress Steps ──────────────────────────────────────────────────── */}
      <div className="de-steps">
        {STEP_LABELS.map((label, i) => (
          <div key={i} className={`de-step ${i === step ? 'de-step--active' : i < step ? 'de-step--done' : ''}`}>
            <div className="de-step-circle">
              {i < step
                ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg>
                : <span>{i + 1}</span>
              }
            </div>
            <span className="de-step-label">{label}</span>
            {i < STEP_LABELS.length - 1 && <div className={`de-step-line ${i < step ? 'de-step-line--done' : ''}`} />}
          </div>
        ))}
      </div>

      {/* ── STEP 0: Select Patient ──────────────────────────────────────────── */}
      {step === 0 && (
        <div className="de-card">
          <div className="de-section-label">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
            Select Patient
          </div>

          {normalizedPatients.length === 0 ? (
            <div className="de-empty">No patients available — please add a patient first.</div>
          ) : visiblePatients.length === 0 ? (
            <div className="de-empty">No patients match your search. Clear the filter to see all patients.</div>
          ) : (
            <div className="de-patient-list">
              {visiblePatients.map(p => (
                <div
                  key={p.id}
                  className={`de-patient-card ${selPt?.id === p.id ? 'de-patient-card--selected' : ''}`}
                  onClick={() => setSelPt(p)}
                >
                  <div className="de-patient-avatar">{ptInitials(p.name)}</div>
                  <div className="de-patient-info">
                    <div className="de-patient-name">{p.name}</div>
                    <div className="de-patient-meta">
                      <span className="de-mrn">{p.mrn || `#${p.id}`}</span>
                      <span>·</span>
                      <span>{p.age}y</span>
                      <span>·</span>
                      <span style={{ textTransform: 'capitalize' }}>{String(p.gender).replace('Gender.', '')}</span>
                      {p.conditions.length > 0 && <><span>·</span><span>{p.conditions.slice(0,2).join(', ')}</span></>}
                    </div>
                  </div>
                  <div className="de-patient-right">
                    {p.allergies.length > 0
                      ? <span className="de-allergy-tag">⚠ Allergies</span>
                      : <span className="de-nkda-tag">NKDA</span>}
                    {selPt?.id === p.id && (
                      <div className="de-selected-check">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="de-footer">
            <button className="de-btn de-btn--primary" disabled={!selPt} onClick={() => setStep(1)}>
              Continue to Clinical Data
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="14" height="14"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 1: Clinical Data ───────────────────────────────────────────── */}
      {step === 1 && (
        <div className="de-card">
          {/* Patient summary chip */}
          <div className="de-patient-chip">
            <div className="de-patient-chip-avatar">{ptInitials(selPt?.name)}</div>
            <div>
              <div className="de-patient-chip-name">{selPt?.name}</div>
              <div className="de-patient-chip-meta">{selPt?.mrn} · {selPt?.age}y · {String(selPt?.gender || '').replace('Gender.','')}</div>
            </div>
            <button className="de-change-btn" onClick={() => setStep(0)}>Change</button>
          </div>

          {/* Allergy alert */}
          {Array.isArray(selPt?.allergies) && selPt.allergies.length > 0 && (
            <div className="de-allergy-alert">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16" style={{ flexShrink: 0 }}>
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              <div>
                <div className="de-allergy-alert-title">Known Allergies — Verify Before Prescribing</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 5 }}>
                  {selPt.allergies.map((a, i) => (
                    <span key={i} className="de-allergy-pill">{a}</span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Symptoms */}
          <div className="de-field-section">
            <div className="de-section-label">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
              Current Symptoms <span className="de-required">*</span>
            </div>
            <textarea
              className="de-textarea"
              rows={4}
              value={symptoms}
              onChange={e => setSymptoms(e.target.value)}
              placeholder="Describe presenting symptoms (e.g., fatigue, increased thirst, chest pain, shortness of breath…)"
            />
            {symptoms.trim() && (
              <div className="de-char-count">{symptoms.trim().split(/\s+/).length} words entered</div>
            )}
          </div>

          {/* Clinical Notes */}
          <div className="de-field-section">
            <div className="de-section-label">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
              Clinical Notes
            </div>
            <textarea
              className="de-textarea"
              rows={3}
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Free-text clinical notes"
            />
          </div>

          {/* Lab Results */}
          <div className="de-field-section">
            <div className="de-section-label">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18"/></svg>
              Laboratory Results
              <span className="de-label-hint">Optional — improves diagnostic accuracy</span>
            </div>
            <div className="de-lab-grid">
              {[
                { label: 'Blood Glucose', key: 'glucose', unit: 'mg/dL', normal: '70–99' },
                { label: 'HbA1c',         key: 'hba1c',   unit: '%',     normal: '<5.7%' },
                { label: 'WBC',           key: 'wbc',     unit: '×10³/μL', normal: '4–11' },
                { label: 'Creatinine',    key: 'creatinine', unit: 'mg/dL', normal: '0.6–1.2' },
                { label: 'Troponin',      key: 'troponin', unit: 'ng/mL', normal: '<0.04' },
              ].map(({ label, key, unit, normal }) => (
                <div key={key} className="de-lab-field">
                  <div className="de-lab-label">{label}</div>
                  <div className="de-lab-input-wrap">
                    <input
                      className="de-lab-input"
                      type="number" step="any"
                      value={lab[key]}
                      onChange={setL(key)}
                      placeholder="—"
                    />
                    <span className="de-lab-unit">{unit}</span>
                  </div>
                  <div className="de-lab-normal">Normal: {normal}</div>
                </div>
              ))}
            </div>
          </div>

          {pipelineError && (
            <div className="alert alert-critical" style={{ marginTop: 10 }}>
              <span className="alert-icon">⚠️</span>
              <div><b>Pipeline Error:</b> {pipelineError}</div>
            </div>
          )}

          <div className="de-footer de-footer--spaced">
            <button className="de-btn de-btn--ghost" onClick={() => setStep(0)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="14" height="14"><polyline points="15 18 9 12 15 6"/></svg>
              Back
            </button>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button
                className="de-btn de-btn--primary"
                disabled={!symptoms.trim()}
                onClick={runAnalysis}
              >
                <AiDiagnosisLogo size={16} className="btn-embed-ai-logo" aria-hidden />
                Run AI Analysis
              </button>
              <button
                className="de-btn de-btn--pipeline"
                disabled={!symptoms.trim() || pipelineLoading}
                onClick={runPipeline}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="15" height="15"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                5-Agent Pipeline
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── STEP 2: Processing ──────────────────────────────────────────────── */}
      {step === 2 && (
        <div className="de-card de-processing-card">
          <div className="de-processing-ring">
            <div className="de-processing-ring-inner">
              <AiDiagnosisLogo size={36} className="diagnosis-processing-logo" aria-hidden />
            </div>
          </div>
          <h2 className="de-processing-title">
            {pipelineLoading ? '5-Agent Pipeline Running…' : 'AI Analysis in Progress…'}
          </h2>
          <p className="de-processing-sub">
            {pipelineLoading
              ? 'Running multi-agent clinical pipeline — this may take 30–90 seconds'
              : llmReady
                ? 'LLM generating ranked differential diagnoses — please wait 30–90 seconds'
                : 'Clinical rules engine scoring differentials'}
          </p>

          {pipelineLoading && (
            <div className="de-pipeline-steps">
              {PIPELINE_STEP_LABELS.map((label, idx) => (
                <div key={idx} className={`de-pipe-step ${pipelineStep >= idx ? 'de-pipe-step--active' : ''} ${pipelineStep > idx ? 'de-pipe-step--done' : ''}`}>
                  <div className="de-pipe-step-icon">
                    {pipelineStep > idx
                      ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" width="12" height="12"><polyline points="20 6 9 17 4 12"/></svg>
                      : pipelineStep === idx
                        ? <div className="de-pipe-spinner" />
                        : <span style={{ fontSize: 10, fontWeight: 700 }}>{idx + 1}</span>
                    }
                  </div>
                  <span className="de-pipe-label">{label}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── STEP 3: Results ─────────────────────────────────────────────────── */}
      {step === 3 && !confirmed && (
        <div className="de-results-root">
          {analysisError && (
            <div className="alert alert-critical" style={{ marginBottom: 12 }}>
              <span className="alert-icon">⚠️</span>
              <div>{analysisError}</div>
            </div>
          )}
          {/* Source badge */}
          <div className="de-source-bar">
            <span className={`de-source-badge ${lastRunSource === 'llm' ? 'de-source-badge--llm' : 'de-source-badge--rules'}`}>
              {lastRunSource === 'llm' ? '🧠 AI Powered' : '⚡ Clinical Rules Check'}
            </span>
            <span className="de-source-note">
              These are AI suggestions only. A qualified doctor must review and approve before any treatment.
            </span>
          </div>

          <div className="de-results-grid">
            {/* Left: Diagnosis cards */}
            <div className="de-dx-list">
              <div className="de-section-label" style={{ marginBottom: 12 }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                AI Suggestions — Tap a result to select it
              </div>
              {results && results.length > 0 ? (
                results.map(d => (
                  <div
                    key={d.rank}
                    className={`de-dx-card ${selDx?.rank === d.rank ? 'de-dx-card--selected' : ''}`}
                    onClick={() => setSelDx(d)}
                  >
                    <div className="de-dx-card-left">
                      <div className="de-dx-rank" style={{ background: d.rank === 1 ? 'rgba(124,58,237,0.2)' : 'var(--surface3)', color: d.rank === 1 ? 'var(--accent3)' : 'var(--text3)' }}>
                        #{d.rank}
                      </div>
                    </div>
                    <div className="de-dx-card-body">
                      <div className="de-dx-card-top">
                        <div className="de-dx-name">{d.name}</div>
                        <div className="de-conf-pill" style={{ background: `${confColor(d.confidence)}20`, borderColor: `${confColor(d.confidence)}40`, color: confColor(d.confidence) }}>
                          {d.confidence}%
                        </div>
                      </div>
                      <div className="de-dx-icd">ICD-10: {d.icd}</div>
                      <div className="de-conf-bar-wrap">
                        <div className="de-conf-bar-track">
                          <div className="de-conf-bar-fill" style={{ width: `${d.confidence}%`, background: confColor(d.confidence) }} />
                        </div>
                      </div>
                      <div className="de-dx-evidence">{d.evidence}</div>
                      {Array.isArray(d.factors) && d.factors.length > 0 && (
                        <div className="de-xai-mini">
                          <div className="de-xai-mini-label">Feature Importance</div>
                          <XAIBarChart factors={d.factors} />
                        </div>
                      )}
                    </div>
                    {selDx?.rank === d.rank && (
                      <div className="de-dx-selected-indicator">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg>
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <div className="de-empty" style={{ padding: '32px 18px', textAlign: 'center' }}>
                  <div style={{ fontSize: 24, marginBottom: 8 }}>No verified diagnoses available</div>
                  <div className="text-muted" style={{ maxWidth: 360, margin: '0 auto' }}>
                    The pipeline completed, but no verified diagnosis suggestions were produced. Review the QA summary below or revise the patient data and run again.
                  </div>
                </div>
              )}
            </div>

            {/* Right: XAI + Guidelines */}
            <div className="de-side-col">
              <div className="de-card" style={{ padding: '18px' }}>
                <div className="de-section-label" style={{ marginBottom: 12 }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                  Why did AI suggest this?
                </div>
                {selDx ? (
                  <>
                    <div className="de-xai-name">{selDx.name}</div>
                    <div className="de-xai-conf-row">
                      <span className="de-xai-conf-label">AI Confidence</span>
                      <span className="de-xai-conf-val" style={{ color: confColor(selDx.confidence) }}>{selDx.confidence}%</span>
                    </div>
                    <div className="de-xai-factors-label">Which clues led to this result?</div>
                    <XAIBarChart factors={selDx.factors} />
                    <div className="sep" />
                    <div className="de-xai-reasoning-label">What the AI found:</div>
                    <div className="de-xai-reasoning-text">{selDx.evidence}</div>
                  </>
                ) : (
                  <div className="de-empty" style={{ padding: '16px 0' }}>
                    Tap a result on the left to see why the AI suggested it
                  </div>
                )}
              </div>

              <div className="de-card" style={{ padding: '18px' }}>
                <div className="de-section-label" style={{ marginBottom: 12 }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
                  What do medical guidelines say?
                </div>
                <div style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.75 }}>
                  {selDx?.name.includes('Diabetes')    && 'Diabetes is confirmed when HbA1c is 6.5% or higher, or fasting blood sugar is 126 mg/dL or more. (ADA 2024)'}
                  {selDx?.name.includes('Coronary')    && 'Chest pain should be evaluated immediately with a heart trace (ECG) and blood tests. Do not delay. (ACC/AHA 2021)'}
                  {selDx?.name.includes('Respiratory') && 'Most upper respiratory infections are viral and improve on their own. Antibiotics are usually not needed. (NICE CG69)'}
                  {!selDx && <span style={{ color: 'var(--text3)', fontSize: 12 }}>Select a diagnosis to read what official medical guidelines recommend.</span>}
                </div>
              </div>
            </div>
          </div>

          <div className="de-footer de-footer--spaced">
            <button className="de-btn de-btn--ghost" onClick={() => { setStep(1); setResults(null); setSelDx(null); }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="14" height="14"><polyline points="15 18 9 12 15 6"/></svg>
              Revise Data
            </button>
            <button
              className="de-btn de-btn--confirm"
              disabled={!selDx}
              onClick={confirmDx}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="15" height="15"><polyline points="20 6 9 17 4 12"/></svg>
              Confirm Diagnosis
            </button>
          </div>

          {pipelineResult && <PipelineResultPanels result={pipelineResult} />}
        </div>
      )}

    </div>
  );
}