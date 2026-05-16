import { patientMatchesSearch } from '../utils/patientSearch.js';
import AiDiagnosisLogo from '../components/AiDiagnosisLogo.jsx';

function normalizeDashboardPatient(p) {
  const name =
    p?.full_name ||
    p?.name ||
    `${p?.first_name || ''} ${p?.last_name || ''}`.trim() ||
    'Unknown';
  const conditions = Array.isArray(p?.conditions)
    ? p.conditions
    : Array.isArray(p?.medical_histories)
      ? p.medical_histories.map((h) => h?.condition).filter(Boolean)
      : [];
  const allergies = Array.isArray(p?.allergies)
    ? p.allergies.map((a) => (typeof a === 'string' ? a : a?.allergen)).filter(Boolean)
    : [];
  const age =
    p?.age ??
    (p?.date_of_birth
      ? new Date().getFullYear() - new Date(p.date_of_birth).getFullYear()
      : '—');
  const lastVisit = p?.last_visit || p?.lastVisit || p?.updated_at?.split('T')[0] || '—';
  return { ...p, name, conditions, allergies, age, lastVisit };
}

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

const IconPatients = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="22" height="22">
    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
    <circle cx="9" cy="7" r="4"/>
    <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>
  </svg>
);

const IconPrescriptions = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="22" height="22">
    <path d="M12 22h6a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v3"/>
    <path d="M14 2v4a2 2 0 0 0 2 2h4"/>
    <path d="M3 15h6m-3-3v6"/>
  </svg>
);

const IconPlus = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" width="20" height="20">
    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
  </svg>
);

const IconRx = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="20" height="20">
    <path d="M12 22h6a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v3"/>
    <path d="M14 2v4a2 2 0 0 0 2 2h4M3 15h6m-3-3v6"/>
  </svg>
);

const IconChart = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="20" height="20">
    <path d="M18 20V10M12 20V4M6 20v-6"/>
  </svg>
);

const IconChevron = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="14" height="14">
    <polyline points="9 18 15 12 9 6"/>
  </svg>
);

export default function Dashboard({
  patients,
  patientSearch = '',
  diagnoses = [],
  prescriptions = [],
  backendOk,
  setPage,
  setSelectedPatient,
}) {
  const dashPatients = (Array.isArray(patients) ? patients : [])
    .filter((p) => patientMatchesSearch(p, patientSearch, { includeConditions: true }))
    .map(normalizeDashboardPatient);

  const nPatients   = Array.isArray(patients)      ? patients.length      : 0;
  const nDx         = Array.isArray(diagnoses)     ? diagnoses.length     : 0;
  const nRx         = Array.isArray(prescriptions) ? prescriptions.length : 0;
  const nRxWarnings = Array.isArray(prescriptions)
    ? prescriptions.filter((p) =>
        p.safety_checks?.some((sc) => sc.result === 'Critical' || sc.result === 'Warning')
      ).length
    : 0;

  const todayStr = new Date().toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  });

  const stats = [
    {
      label: 'Total Patients',
      value: nPatients,
      sub: backendOk ? 'Synced from server' : 'Local / offline',
      Icon: IconPatients,
      bar: 'linear-gradient(90deg,#7c3aed,#c084fc)',
      iconClr: '#a78bfa',
      iconBg: 'rgba(124,58,237,0.15)',
    },
    {
      label: 'AI Diagnoses',
      value: nDx,
      sub: 'This session',
      AiIcon: AiDiagnosisLogo,
      bar: 'linear-gradient(90deg,#6d28d9,#f0abfc)',
      iconClr: '#e879f9',
      iconBg: 'rgba(217,70,239,0.15)',
    },
    {
      label: 'Prescriptions',
      value: nRx,
      sub: nRxWarnings > 0 ? `${nRxWarnings} safety warnings` : 'No warning flags',
      Icon: IconPrescriptions,
      bar: 'linear-gradient(90deg,#0d9488,#34d399)',
      iconClr: '#34d399',
      iconBg: 'rgba(16,185,129,0.15)',
    },
  ];

  const actions = [
    { Icon: IconPlus,       label: 'New Patient',    page: 'patients',      clr: '#7c3aed', bg: 'rgba(124,58,237,0.12)' },
    { AiIcon: AiDiagnosisLogo, label: 'AI Diagnosis', page: 'diagnosis',    clr: '#d946ef', bg: 'rgba(217,70,239,0.12)' },
    { Icon: IconRx,         label: 'Prescriptions',  page: 'prescriptions', clr: '#10b981', bg: 'rgba(16,185,129,0.12)' },
    { Icon: IconChart,      label: 'Reports',        page: 'reports',       clr: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
  ];

  return (
    <div className="db-root">

      {/* ─── BANNER ─────────────────────────────────────── */}
      <div className="db-banner">
        <div className="db-banner-inner">
          <div className="db-banner-left">
            <div className="db-banner-eyebrow">
              <span className={`db-dot ${backendOk === null ? 'db-dot--amber' : backendOk ? 'db-dot--green' : 'db-dot--red'}`} />
              {backendOk === null ? 'Connecting…' : backendOk ? 'API Live' : 'API Offline'}
              <span className="db-banner-divider" />
              {todayStr}
            </div>
            <h1 className="db-banner-title">{getGreeting()}, Doctor</h1>
            <p className="db-banner-sub">AI-powered decision support — real-time patient insights at a glance.</p>
          </div>
          <div className="db-banner-badge-wrap">
            <span className="db-banner-badge">{nPatients}<span>Patients</span></span>
            <span className="db-banner-badge db-banner-badge--fuchsia">{nDx}<span>Diagnoses</span></span>
          </div>
        </div>
        <div className="db-banner-glow" aria-hidden="true" />
      </div>

      {/* ─── STAT CARDS ─────────────────────────────────── */}
      <div className="db-stats">
        {stats.map((s, i) => (
          <div key={i} className="db-stat" style={{ '--db-bar': s.bar, '--db-icon-bg': s.iconBg }}>
            <div className="db-stat-bar" />
            <div className="db-stat-body">
              <div>
                <div className="db-stat-label">{s.label}</div>
                <div className="db-stat-value">{s.value}</div>
                <div className="db-stat-sub">{s.sub}</div>
              </div>
              <div className="db-stat-icon" style={{ background: s.iconBg }}>
                <span style={{ color: s.iconClr }}>
                  {s.AiIcon ? <s.AiIcon size={22} /> : <s.Icon />}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* ─── QUICK ACTIONS ──────────────────────────────── */}
      <div className="db-section-label">⚡ Quick Actions</div>
      <div className="db-actions">
        {actions.map((a, i) => (
          <button
            key={i}
            type="button"
            className="db-action"
            style={{ '--dba-clr': a.clr, '--dba-bg': a.bg }}
            onClick={() => setPage(a.page)}
          >
            <span className="db-action-icon">
              <span style={{ color: a.clr }}>
                {a.AiIcon ? <a.AiIcon size={20} /> : <a.Icon />}
              </span>
            </span>
            <span className="db-action-label">{a.label}</span>
            <span className="db-action-arrow"><IconChevron /></span>
          </button>
        ))}
      </div>

      {/* ─── ACTIVE PATIENTS TABLE ──────────────────────── */}
      <div className="db-table-card">
        <div className="db-table-header">
          <div className="db-section-label" style={{ marginBottom: 0 }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="13" height="13">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
            </svg>
            Active Patients
          </div>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => setPage('patients')}>
            View all →
          </button>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Patient Name</th>
                <th>Age</th>
                <th>Conditions</th>
                <th>Allergies</th>
                <th>Last Updated</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {dashPatients.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ padding: '36px 0', textAlign: 'center' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.3"
                        width="36" height="36" style={{ color: 'var(--text3)', opacity: 0.45 }}>
                        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                        <circle cx="9" cy="7" r="4"/>
                        <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>
                      </svg>
                      <span style={{ fontSize: 13, color: 'var(--text3)' }}>
                        {patients.length === 0
                          ? 'No patients yet — add a patient to get started.'
                          : 'No patients match your search.'}
                      </span>
                    </div>
                  </td>
                </tr>
              ) : (
                dashPatients.slice(0, 6).map((p) => (
                  <tr key={p.id}>
                    <td>
                      <span className="db-id-badge">#{p.id}</span>
                    </td>
                    <td>
                      <span className="td-main">{p.name}</span>
                    </td>
                    <td style={{ color: 'var(--text2)', fontWeight: 500 }}>{p.age}</td>
                    <td>
                      {p.conditions.length > 0 ? (
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                          {p.conditions.slice(0, 2).map((c, ci) => (
                            <span key={ci} className="badge badge-purple" style={{ fontSize: '10px' }}>{c}</span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-muted text-xs">None</span>
                      )}
                    </td>
                    <td>
                      {p.allergies.length > 0 ? (
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                          {p.allergies.slice(0, 2).map((a, ai) => (
                            <span key={ai} className="badge badge-red" style={{ fontSize: '10px' }}>⚠ {a}</span>
                          ))}
                        </div>
                      ) : (
                        <span className="badge badge-green" style={{ fontSize: '10px' }}>NKDA</span>
                      )}
                    </td>
                    <td className="text-muted text-xs">{p.lastVisit}</td>
                    <td>
                      <button
                        type="button"
                        className="db-view-btn"
                        onClick={() => { setSelectedPatient(p); setPage('patient_detail'); }}
                      >
                        View <IconChevron />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
