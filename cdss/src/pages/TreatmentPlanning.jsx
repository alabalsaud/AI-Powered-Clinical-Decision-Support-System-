import { useState } from 'react';
import { ConfBar, EmptyState } from '../components/UI.jsx';
import AiDiagnosisLogo from '../components/AiDiagnosisLogo.jsx';
import { patientMatchesSearch } from '../utils/patientSearch.js';

const TX_MAP = {
  'E11.9': [
    {
      title: 'Metformin + Lifestyle (Recommended First-line)',
      recommended: true,
      meds: ['Metformin 500mg twice daily (titrate to 1000mg BD)'],
      lifestyle: [
        'Low-carbohydrate diet',
        '150 min/week moderate exercise',
        'Weight loss goal 5–10%',
      ],
      monitoring: [
        'HbA1c every 3 months',
        'Renal function annually',
        'Blood glucose self-monitoring',
      ],
      evidence:
        'ADA 2024 Standards — First-line therapy. Proven HbA1c reduction of 1–2%. Cardiovascular neutral.',
    },
    {
      title: 'Lifestyle Modifications Only',
      recommended: false,
      meds: [],
      lifestyle: [
        'Mediterranean diet',
        'Carbohydrate counting',
        '150–300 min/week aerobic activity',
        'Weight tracking weekly',
      ],
      monitoring: [
        'Monthly blood glucose',
        'HbA1c at 3 months',
        'Weight weekly',
      ],
      evidence:
        'Effective for early-stage T2DM. May delay pharmacotherapy by 2–3 years.',
    },
    {
      title: 'Metformin + SGLT2 Inhibitor',
      recommended: false,
      meds: ['Metformin 500mg twice daily', 'Empagliflozin 10mg once daily'],
      lifestyle: ['Low-carbohydrate diet', 'Regular aerobic exercise'],
      monitoring: [
        'Renal function quarterly',
        'eGFR before initiation',
        'DKA symptoms awareness',
      ],
      evidence:
        'EMPA-REG OUTCOME — Empagliflozin reduces CV events by 14% and HHF by 35% in high-risk patients.',
    },
  ],
  'I24.9': [
    {
      title: 'Dual Antiplatelet + Statin (DAPT — Standard of Care)',
      recommended: true,
      meds: [
        'Aspirin 81mg daily',
        'Ticagrelor 90mg twice daily',
        'Atorvastatin 80mg nightly',
      ],
      lifestyle: [
        'Strict rest initially',
        'Cardiac rehabilitation',
        'Smoking cessation',
        'Low-sodium diet',
      ],
      monitoring: [
        'Serial troponin',
        'Continuous ECG',
        'Renal function',
        'LFTs for statin',
      ],
      evidence:
        'ACC/AHA 2021 — DAPT reduces reinfarction risk by ~30%. High-dose statin within 24h recommended.',
    },
    {
      title: 'PCI + Medical Management',
      recommended: false,
      meds: [
        'Aspirin 81mg',
        'Clopidogrel 75mg daily',
        'Atorvastatin 80mg',
        'Beta-blocker (Metoprolol)',
      ],
      lifestyle: ['Cardiac rehab programme', 'Smoking cessation mandatory'],
      monitoring: [
        'Post-PCI ECG',
        'Echocardiogram at 6 weeks',
        'LFTs for statin',
      ],
      evidence:
        'Revascularisation reduces mortality in STEMI. Door-to-balloon time <90 min target.',
    },
  ],
};

function normalizePatient(p) {
  if (!p) return null;

  return {
    ...p,
    name:
      p.name ||
      p.full_name ||
      `${p.first_name || ''} ${p.last_name || ''}`.trim() ||
      'Unknown Patient',
    conditions: Array.isArray(p.conditions)
      ? p.conditions
      : Array.isArray(p.medical_histories)
        ? p.medical_histories.map((c) => c.condition).filter(Boolean)
        : [],
  };
}

function normalizeDiagnosis(d) {
  if (!d) return null;

  return {
    ...d,
    patientId: d.patientId ?? d.patient_id,
    condition: d.condition || d.diagnosis_name || 'Unknown Diagnosis',
    icd: d.icd || d.diagnosis_code || '',
    confidence: d.confidence ?? d.confidence_score ?? 0,
    status: d.status || 'Suggested',
  };
}

export default function TreatmentPlanning({ patients = [], patientSearch = '', diagnoses = [] }) {
  const [selPt, setSelPt] = useState(null);
  const [selDx, setSelDx] = useState(null);
  const [selTx, setSelTx] = useState(null);

  const safePatients = Array.isArray(patients) ? patients.map(normalizePatient) : [];
  const pickerPatients = safePatients.filter((p) =>
    patientMatchesSearch(p, patientSearch, { includeConditions: false })
  );
  const safeDiagnoses = Array.isArray(diagnoses)
    ? diagnoses.map(normalizeDiagnosis)
    : [];

  const ptDx = safeDiagnoses.filter((d) => d.patientId === selPt?.id);
  const options = selDx ? TX_MAP[selDx.icd] || [] : [];

  return (
    <div>
      <div className="section-hdr">
        <div>
          <div className="section-title">Treatment Planning</div>
          <div className="section-sub">
            Evidence-based recommendations aligned with clinical guidelines (FR4)
          </div>
        </div>
      </div>

      <div className="grid-2 mb-20">
        <div className="card">
          <div className="card-title">👥 Select Patient</div>

          {safePatients.length === 0 ? (
            <EmptyState
              icon="👤"
              title="No patients available"
              sub="Please add a patient first"
            />
          ) : pickerPatients.length === 0 ? (
            <EmptyState
              icon="🔍"
              title="No matching patients"
              sub="Try another name or MRN, or clear the search in the top bar"
            />
          ) : (
            pickerPatients.map((p) => (
              <div
                key={p.id}
                className={`diag-card ${selPt?.id === p.id ? 'active' : ''}`}
                onClick={() => {
                  setSelPt(p);
                  setSelDx(null);
                  setSelTx(null);
                }}
              >
                <div className="text-bold">{p.name}</div>
                <div
                  className="text-sm text-muted mt-8"
                  style={{ marginTop: 4 }}
                >
                  {p.mrn || p.id} ·{' '}
                  {p.conditions.length > 0
                    ? p.conditions.join(', ')
                    : 'No conditions'}
                </div>
              </div>
            ))
          )}
        </div>

        <div className="card">
          <div className="card-title card-title-with-ai-logo">
            <AiDiagnosisLogo size={22} className="card-title-ai-logo" aria-hidden />
            Select Diagnosis
          </div>

          {!selPt ? (
            <EmptyState icon="👤" title="Select a patient first" />
          ) : ptDx.length === 0 ? (
            <EmptyState
              icon={<AiDiagnosisLogo size={40} className="empty-state-ai-logo" />}
              title="No diagnoses for this patient"
              sub="Run AI Diagnosis first"
            />
          ) : (
            ptDx.map((d) => (
              <div
                key={d.id}
                className={`diag-card ${selDx?.id === d.id ? 'active' : ''}`}
                onClick={() => {
                  setSelDx(d);
                  setSelTx(null);
                }}
              >
                <div className="text-bold">{d.condition}</div>
                <div
                  className="flex-center gap-8 mt-8"
                  style={{ marginTop: 6 }}
                >
                  <span className="text-mono text-xs text-accent">
                    {d.icd || 'No ICD'}
                  </span>
                  <ConfBar value={d.confidence} />
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {selDx && options.length > 0 && (
        <div>
          <div className="alert alert-info">
            <span className="alert-icon">ℹ️</span>
            <div>
              Evidence-based treatment options for <b>{selDx.condition}</b>.
              Based on current clinical guidelines.
            </div>
          </div>

          {options.map((opt, i) => (
            <div
              key={i}
              className="card mb-12"
              style={{
                borderLeft: `3px solid ${
                  opt.recommended ? 'var(--accent)' : 'var(--border)'
                }`,
                marginBottom: 12,
              }}
            >
              <div className="flex-between mb-12" style={{ marginBottom: 12 }}>
                <div className="flex-center gap-8">
                  <span className="text-bold">{opt.title}</span>
                  {opt.recommended && (
                    <span className="badge badge-green">★ Recommended</span>
                  )}
                </div>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => setSelTx(i)}
                >
                  {selTx === i ? '✅ Selected' : 'Select Plan'}
                </button>
              </div>

              <div className="grid-3">
                <div>
                  <div className="form-label">💊 Medications</div>
                  {Array.isArray(opt.meds) && opt.meds.length > 0 ? (
                    opt.meds.map((m, j) => (
                      <div
                        key={j}
                        className="text-sm"
                        style={{ padding: '3px 0', color: 'var(--text)' }}
                      >
                        • {m}
                      </div>
                    ))
                  ) : (
                    <div className="text-sm text-muted">No medications</div>
                  )}
                </div>

                <div>
                  <div className="form-label">🏃 Lifestyle</div>
                  {Array.isArray(opt.lifestyle) &&
                    opt.lifestyle.map((l, j) => (
                      <div
                        key={j}
                        className="text-sm text-dim"
                        style={{ padding: '3px 0' }}
                      >
                        • {l}
                      </div>
                    ))}
                </div>

                <div>
                  <div className="form-label">🔬 Monitoring</div>
                  {Array.isArray(opt.monitoring) &&
                    opt.monitoring.map((m, j) => (
                      <div
                        key={j}
                        className="text-sm text-dim"
                        style={{ padding: '3px 0' }}
                      >
                        • {m}
                      </div>
                    ))}
                </div>
              </div>

              <div className="sep" />
              <div className="text-xs text-dim" style={{ lineHeight: 1.6 }}>
                <b style={{ color: 'var(--accent)' }}>Evidence Base:</b>{' '}
                {opt.evidence}
              </div>
            </div>
          ))}
        </div>
      )}

      {selDx && options.length === 0 && (
        <EmptyState
          icon="📋"
          title="Treatment guidelines not yet available for this diagnosis"
          sub="Contact the clinical team for specialised guidance"
        />
      )}
    </div>
  );
}