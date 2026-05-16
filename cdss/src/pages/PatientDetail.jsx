import { useState, useMemo } from 'react';
import { ConfBar, SafetyBadge, StatusBadge, EmptyState } from '../components/UI.jsx';
import AiDiagnosisLogo from '../components/AiDiagnosisLogo.jsx';

/* ── Helpers ───────────────────────────────────────────── */
function recordPatientId(rec) {
  return rec?.patientId ?? rec?.patient_id;
}

function buildVM(p) {
  if (!p) return null;
  const name = p.full_name || p.name || `${p.first_name || ''} ${p.last_name || ''}`.trim() || 'Unknown';
  const age  = p.age ?? (p.date_of_birth ? new Date().getFullYear() - new Date(p.date_of_birth).getFullYear() : null);
  const allergies  = Array.isArray(p.allergies)
    ? p.allergies.map(a => typeof a === 'string' ? a : a?.allergen).filter(Boolean) : [];
  const conditions = Array.isArray(p.medical_histories)
    ? p.medical_histories.map(h => h?.condition).filter(Boolean)
    : Array.isArray(p.conditions) ? p.conditions.map(c => typeof c === 'string' ? c : c?.condition).filter(Boolean) : [];
  const medications = Array.isArray(p.medications)
    ? p.medications.map(m => typeof m === 'string' ? m : m?.drug_name || m?.name).filter(Boolean) : [];
  const gender = String(p.gender?.value ?? p.gender ?? '—').replace('Gender.', '');
  return {
    ...p, name, age, gender,
    dob:       p.date_of_birth || p.dob || '—',
    bloodType: p.blood_type || p.bloodType || '—',
    weight:    p.weight != null && p.weight !== '' ? p.weight : null,
    height:    p.height != null && p.height !== '' ? p.height : null,
    phone:     p.phone || '—',
    email:     p.email || '—',
    mrn:       p.mrn || '—',
    status:    p.is_active === false ? 'Inactive' : 'Active',
    medications, conditions, allergies, id: p.id,
  };
}

function bmi(w, h) {
  if (!w || !h) return null;
  const v = w / Math.pow(h / 100, 2);
  return v.toFixed(1);
}

function bloodTypeColor(bt) {
  const map = { 'A+':'#7c3aed','A-':'#6d28d9','B+':'#0d9488','B-':'#0891b2','O+':'#d97706','O-':'#b45309','AB+':'#dc2626','AB-':'#b91c1c' };
  return map[bt] || '#6d28d9';
}

/* ── SVG Icons ─────────────────────────────────────────── */
const IcoBack = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" width="14" height="14">
    <polyline points="15 18 9 12 15 6"/>
  </svg>
);
const IcoUser = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="16" height="16">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
    <circle cx="12" cy="7" r="4"/>
  </svg>
);
const IcoPill = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="16" height="16">
    <path d="M12 22h6a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v3"/>
    <path d="M14 2v4a2 2 0 0 0 2 2h4M3 15h6m-3-3v6"/>
  </svg>
);
const IcoHeart = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="16" height="16">
    <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
  </svg>
);
const IcoWarn = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
    <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
  </svg>
);
const IcoCalendar = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="16" height="16">
    <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/>
    <line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
  </svg>
);
const IcoActivity = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
  </svg>
);
const IcoClipboard = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="16" height="16">
    <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
    <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
  </svg>
);

const TABS = [
  { key: 'overview',      label: 'Overview',      Icon: IcoUser },
  { key: 'history',       label: 'History',        Icon: IcoCalendar },
  { key: 'diagnoses',     label: 'Diagnoses',      Icon: IcoActivity },
  { key: 'prescriptions', label: 'Prescriptions',  Icon: IcoClipboard },
];

export default function PatientDetail({ selectedPatient, patient: patientProp, diagnoses, prescriptions, setPage }) {
  const [tab, setTab] = useState('overview');
  const raw     = selectedPatient ?? patientProp;
  const patient = useMemo(() => buildVM(raw), [raw]);

  if (!patient) {
    return <EmptyState icon="👤" title="No patient selected" sub="Go to Patients and click View" />;
  }

  const pid  = patient.id;
  const ptDx = (Array.isArray(diagnoses)     ? diagnoses     : []).filter(d => recordPatientId(d) === pid);
  const ptRx = (Array.isArray(prescriptions) ? prescriptions : []).filter(r => recordPatientId(r) === pid);
  const bmiVal = bmi(patient.weight, patient.height);
  const initials = patient.name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
  const btColor  = bloodTypeColor(patient.bloodType);

  const history = [
    { date: 'Oct 2025', title: 'Type 2 Diabetes Diagnosed',   sub: 'HbA1c: 7.2% — Started Metformin 500mg', dot: 'amber' },
    { date: 'Aug 2025', title: 'Hypertension Follow-up',      sub: 'BP: 148/92 — Lisinopril adjusted to 10mg', dot: 'purple' },
    { date: 'Jun 2025', title: 'Annual Check-up',             sub: 'All vitals within normal range', dot: 'green' },
    { date: 'Jan 2025', title: 'Lab Results Reviewed',        sub: 'Lipid panel: LDL 3.2, HDL 1.1', dot: '' },
  ];

  return (
    <div className="pd-root">

      {/* ── Profile Header ───────────────────────────────── */}
      <div className="pd-header">
        <div className="pd-header-top">
          <button type="button" className="pd-back-btn" onClick={() => setPage('patients')}>
            <IcoBack /> Back
          </button>
          <div className="pd-actions">
            <button
              type="button" className="pd-action-btn pd-action-btn--secondary"
              onClick={() => setPage('diagnosis')}
            >
              <AiDiagnosisLogo size={15} className="btn-embed-ai-logo" aria-hidden />
              AI Diagnosis
            </button>
            <button
              type="button" className="pd-action-btn pd-action-btn--primary"
              onClick={() => setPage('prescriptions')}
            >
              <IcoPill /> Prescribe
            </button>
          </div>
        </div>

        {/* Profile card */}
        <div className="pd-profile">
          <div className="pd-avatar">{initials}</div>
          <div className="pd-profile-info">
            <h1 className="pd-name">{patient.name}</h1>
            <div className="pd-meta">
              <span className="pd-mrn-chip">{patient.mrn}</span>
              <span className="pd-meta-sep">·</span>
              <span>{patient.age ? `${patient.age} yrs` : '—'}</span>
              <span className="pd-meta-sep">·</span>
              <span style={{ textTransform: 'capitalize' }}>{patient.gender}</span>
              <span className="pd-meta-sep">·</span>
              <span>{patient.dob}</span>
            </div>
            {/* Quick stat chips */}
            <div className="pd-chips">
              <span className="pd-chip" style={{ background: `${btColor}22`, borderColor: `${btColor}44`, color: btColor }}>
                🩸 {patient.bloodType}
              </span>
              {patient.weight && (
                <span className="pd-chip">⚖️ {patient.weight} kg</span>
              )}
              {patient.height && (
                <span className="pd-chip">📏 {patient.height} cm</span>
              )}
              {bmiVal && (
                <span className="pd-chip">BMI {bmiVal}</span>
              )}
              <span className={`pd-chip pd-chip--status ${patient.status === 'Active' ? 'pd-chip--active' : 'pd-chip--inactive'}`}>
                {patient.status === 'Active' ? '●' : '○'} {patient.status}
              </span>
            </div>
          </div>
        </div>

        {/* Allergy banner */}
        {patient.allergies.length > 0 && (
          <div className="pd-allergy-banner">
            <div className="pd-allergy-icon"><IcoWarn /></div>
            <div>
              <div className="pd-allergy-title">Known Drug Allergies — Always Verify Before Prescribing</div>
              <div className="pd-allergy-list">
                {patient.allergies.map((a, i) => (
                  <span key={i} className="pd-allergy-pill">{a}</span>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Tabs ─────────────────────────────────────────── */}
      <div className="pd-tabs">
        {TABS.map(t => (
          <button
            key={t.key} type="button"
            className={`pd-tab${tab === t.key ? ' pd-tab--active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            <t.Icon />
            <span>{t.label}</span>
            {t.key === 'diagnoses'     && ptDx.length > 0 && <span className="pd-tab-badge">{ptDx.length}</span>}
            {t.key === 'prescriptions' && ptRx.length > 0 && <span className="pd-tab-badge">{ptRx.length}</span>}
          </button>
        ))}
      </div>

      {/* ── TAB: Overview ────────────────────────────────── */}
      {tab === 'overview' && (
        <div className="pd-overview-grid">
          {/* Demographics */}
          <div className="card pd-demo-card">
            <div className="pd-section-label"><IcoUser /> Demographics</div>
            <div className="pd-info-grid">
              {[
                ['Age',          patient.age ? `${patient.age} years` : '—'],
                ['Gender',       patient.gender],
                ['Date of Birth',patient.dob],
                ['Blood Type',   patient.bloodType],
                ['Weight',       patient.weight ? `${patient.weight} kg` : '—'],
                ['Height',       patient.height ? `${patient.height} cm` : '—'],
                ['BMI',          bmiVal ? `${bmiVal}` : '—'],
                ['Phone',        patient.phone],
                ['Email',        patient.email],
                ['MRN',          patient.mrn],
                ['Status',       patient.status],
              ].map(([label, value]) => (
                <div key={label} className="pd-info-row">
                  <span className="pd-info-label">{label}</span>
                  <span className={`pd-info-value${label === 'Status' ? (patient.status === 'Active' ? ' pd-status-active' : ' pd-status-inactive') : ''}`}>
                    {value}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Right column */}
          <div className="pd-right-col">
            {/* Conditions */}
            <div className="card">
              <div className="pd-section-label"><IcoHeart /> Active Conditions</div>
              {patient.conditions.length > 0 ? (
                <div className="pd-conditions-list">
                  {patient.conditions.map((c, i) => (
                    <div key={i} className="pd-condition-row">
                      <span className="pd-condition-dot" />
                      <span className="pd-condition-text">{c}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="pd-empty-text">No known conditions</p>
              )}
            </div>

            {/* Allergies */}
            <div className="card">
              <div className="pd-section-label" style={{ color: 'var(--red)' }}>
                <IcoWarn /> Allergies
              </div>
              {patient.allergies.length > 0 ? (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
                  {patient.allergies.map((a, i) => (
                    <span key={i} className="badge badge-red" style={{ fontSize: 12 }}>⚠ {a}</span>
                  ))}
                </div>
              ) : (
                <span className="badge badge-green" style={{ fontSize: 12 }}>NKDA — No Known Drug Allergies</span>
              )}
            </div>

            {/* Medications */}
            <div className="card">
              <div className="pd-section-label"><IcoPill /> Current Medications</div>
              {patient.medications.length > 0 ? (
                <div className="pd-conditions-list">
                  {patient.medications.map((m, i) => (
                    <div key={i} className="pd-condition-row">
                      <span className="pd-condition-dot" style={{ background: 'var(--green)' }} />
                      <span className="pd-condition-text">{m}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="pd-empty-text">No current medications</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── TAB: History ─────────────────────────────────── */}
      {tab === 'history' && (
        <div className="card">
          <div className="pd-section-label mb-16"><IcoCalendar /> Medical History Timeline</div>
          <div className="pd-timeline">
            {history.map((h, i) => (
              <div key={i} className="pd-tl-item">
                <div className={`pd-tl-dot pd-tl-dot--${h.dot || 'default'}`} />
                <div className="pd-tl-connector" />
                <div className="pd-tl-content">
                  <span className="pd-tl-date">{h.date}</span>
                  <div className="pd-tl-title">{h.title}</div>
                  <div className="pd-tl-sub">{h.sub}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── TAB: Diagnoses ───────────────────────────────── */}
      {tab === 'diagnoses' && (
        <div className="card">
          <div className="pd-section-label mb-16">
            <AiDiagnosisLogo size={16} className="card-title-ai-logo" aria-hidden />
            Diagnosis History
          </div>
          {ptDx.length > 0 ? ptDx.map(d => {
            const conf = d.confidence ?? d.confidence_score ?? 0;
            const st   = d.status || 'Suggested';
            const dt   = d.date || (d.diagnosed_at && String(d.diagnosed_at).split('T')[0]) || '';
            return (
              <div key={d.id} className="pd-dx-card">
                <div className="pd-dx-top">
                  <div className="pd-dx-name">{d.condition || d.diagnosis_name || '—'}</div>
                  <StatusBadge status={st} />
                </div>
                <div className="pd-dx-icd">ICD-10: {d.icd || d.diagnosis_code || '—'}</div>
                <div className="pd-dx-footer">
                  <ConfBar value={conf} />
                  <span className="badge badge-blue">{d.source || '—'}</span>
                  {dt && <span className="text-muted text-xs">{dt}</span>}
                </div>
              </div>
            );
          }) : (
            <EmptyState
              icon={<AiDiagnosisLogo size={40} className="empty-state-ai-logo" />}
              title="No diagnoses yet"
              sub="Run an AI diagnosis from the Diagnosis module"
            />
          )}
        </div>
      )}

      {/* ── TAB: Prescriptions ───────────────────────────── */}
      {tab === 'prescriptions' && (
        <div className="card">
          <div className="pd-section-label mb-16"><IcoClipboard /> Prescription History</div>
          {ptRx.length > 0 ? ptRx.map(rx => {
            const hasCritical = rx.safety_checks?.some(s => s.result === 'Critical');
            const hasWarning  = rx.safety_checks?.some(s => s.result === 'Warning' || s.result === 'Moderate');
            const safety      = hasCritical ? 'Critical' : hasWarning ? 'Warning' : rx.safety || 'Safe';
            const st          = rx.status ? String(rx.status).charAt(0).toUpperCase() + String(rx.status).slice(1).toLowerCase() : 'Active';
            const dt          = rx.date || (rx.prescribed_date && String(rx.prescribed_date).split('T')[0]) || '';
            return (
              <div key={rx.id} className="pd-rx-card">
                <div className="pd-rx-top">
                  <div className="pd-rx-drug">{rx.drug_name || rx.drug}</div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <SafetyBadge status={safety} />
                    <StatusBadge status={st} />
                  </div>
                </div>
                <div className="pd-rx-dose">{rx.dose} · {rx.frequency || rx.freq} · {rx.duration}</div>
                <div className="pd-rx-meta">
                  <span>{rx.prescriber || rx.prescriber_name || '—'}</span>
                  {dt && <span>· {dt}</span>}
                </div>
              </div>
            );
          }) : (
            <EmptyState icon="💊" title="No prescriptions yet" />
          )}
        </div>
      )}
    </div>
  );
}
