import { useState, useEffect } from 'react';
import { auth as authApi, getStoredUser, getToken, checkHealth, patients as patientsApi, diagnoses as diagnosesApi, prescriptions as rxApi, onSessionExpired } from './api.js';

/* ── localStorage helpers ───────────────────────────────── */
const LS_DX = 'cdss_diagnoses';
const LS_RX = 'cdss_prescriptions';

function lsLoad(key) {
  try { return JSON.parse(localStorage.getItem(key) || '[]'); } catch { return []; }
}
function lsSave(key, data) {
  try { localStorage.setItem(key, JSON.stringify(data)); } catch { /* storage full – silent */ }
}
function lsClear(key) {
  try { localStorage.removeItem(key); } catch { /* silent */ }
}

/** Merge two arrays by id — backend entries take precedence over local ones */
function mergeById(local, remote) {
  const map = new Map(local.map(d => [String(d.id), d]));
  remote.forEach(d => map.set(String(d.id), d));
  return Array.from(map.values());
}
import LoginPage          from './pages/LoginPage.jsx';
import Dashboard          from './pages/Dashboard.jsx';
import PatientManagement  from './pages/PatientManagement.jsx';
import PatientDetail      from './pages/PatientDetail.jsx';
import DiagnosisEngine    from './pages/DiagnosisEngine.jsx';
import TreatmentPlanning  from './pages/TreatmentPlanning.jsx';
import PrescriptionModule from './pages/PrescriptionModule.jsx';
import { ReportsModule, AuditLogs, PipelinePerformance, Settings, UserManagement } from './pages/OtherPages.jsx';
import { LoadingOverlay } from './components/UI.jsx';
import UserAvatar from './components/UserAvatar.jsx';
import AiDiagnosisLogo from './components/AiDiagnosisLogo.jsx';
import ThemeToggle from './ThemeToggle.jsx';

const NAV = [
  { key: 'dashboard',     icon: '⚡', label: 'Dashboard'    },
  { key: 'patients',      icon: '👥', label: 'Patients'      },
  { key: 'diagnosis',     icon: null, Icon: AiDiagnosisLogo, label: 'AI Diagnosis'  },
  { key: 'treatment',     icon: '🌿', label: 'Treatment'     },
  { key: 'prescriptions', icon: '💊', label: 'Prescriptions' },
  { key: 'reports',       icon: '📊', label: 'Reports'       },
  { key: 'pipeline',      icon: '🚀', label: 'Pipeline QA'   },
  { key: 'audit',         icon: '🔍', label: 'Audit Logs'    },
  { key: 'users',         icon: '👨‍⚕️', label: 'Staff'        },
  { key: 'settings',      icon: '⚙️', label: 'Settings'      },
];

const ADMIN_NAV_KEYS = new Set([
  'dashboard', 'patients', 'diagnosis', 'treatment', 'prescriptions', 'reports',
  'audit', 'pipeline', 'users', 'settings',
]);
const ADMIN_BLOCKED_PAGES = new Set();

function navItemsForRole(role) {
  const r = String(role || '').toLowerCase();
  if (r === 'administrator') return NAV.filter((n) => ADMIN_NAV_KEYS.has(n.key));
  return NAV.filter((n) => n.key !== 'audit' && n.key !== 'users');
}

export default function App() {
  const [authed,        setAuthed]        = useState(!!getToken());
  const [currentUser,   setCurrentUser]   = useState(getStoredUser());
  const [page,          setPage]          = useState('dashboard');
  const [sessionMsg,    setSessionMsg]    = useState('');
  const [loading,       setLoading]       = useState(false);
  const [loadMsg,       setLoadMsg]       = useState('');
  const [backendOk,     setBackendOk]     = useState(null);
  const [patients,      setPatients]      = useState([]);
  // ── Persistent state: pre-loaded from localStorage ───────
  const [diagnoses,     setDiagnoses]     = useState(() => lsLoad(LS_DX));
  const [prescriptions, setPrescriptions] = useState(() => lsLoad(LS_RX));
  // ────────────────────────────────────────────────────────
  const [selectedPt,    setSelectedPt]    = useState(null);
  const [patientSearch, setPatientSearch] = useState('');
  const [sidebarOpen,   setSidebarOpen]   = useState(false);

  useEffect(() => { checkHealth().then(ok => setBackendOk(ok)); }, []);

  // Auto-save diagnoses to localStorage whenever they change
  useEffect(() => { lsSave(LS_DX, diagnoses); }, [diagnoses]);

  // Auto-save prescriptions to localStorage whenever they change
  useEffect(() => { lsSave(LS_RX, prescriptions); }, [prescriptions]);

  // Auto-logout when any API call returns 401 (token expired)
  useEffect(() => {
    return onSessionExpired(() => {
      lsClear(LS_DX);
      lsClear(LS_RX);
      setAuthed(false);
      setCurrentUser(null);
      setPatients([]);
      setDiagnoses([]);
      setPrescriptions([]);
      setSessionMsg('Your session expired. Please log in again.');
    });
  }, []);

  // Proactively refresh token once per day (tokens last 7 days, so this gives plenty of buffer)
  useEffect(() => {
    if (!authed) return;
    const REFRESH_MS = 24 * 60 * 60 * 1000; // every 24 hours
    const id = setInterval(async () => {
      try {
        const token = getToken();
        if (!token) return;
        const res = await fetch('http://localhost:8000/api/auth/refresh', {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          if (data?.access_token) localStorage.setItem('cdss_token', data.access_token);
        }
      } catch {
        // silent — user still has 6 more days on their token
      }
    }, REFRESH_MS);
    return () => clearInterval(id);
  }, [authed]);

  useEffect(() => {
    if (!authed || backendOk !== true) return;
    let cancelled = false;

    // Load patients
    patientsApi.list('').then((data) => {
      if (cancelled) return;
      const pts = Array.isArray(data) ? data : [];
      setPatients(pts);

      // For each patient, fetch their diagnoses and prescriptions from backend
      // then merge into (and persist) local state
      pts.forEach(pt => {
        diagnosesApi.forPatient(pt.id)
          .then(remote => {
            if (cancelled || !Array.isArray(remote) || remote.length === 0) return;
            setDiagnoses(prev => mergeById(prev, remote));
          })
          .catch(() => {});

        rxApi.forPatient(pt.id)
          .then(remote => {
            if (cancelled || !Array.isArray(remote) || remote.length === 0) return;
            setPrescriptions(prev => mergeById(prev, remote));
          })
          .catch(() => {});
      });
    }).catch(() => {});

    return () => { cancelled = true; };
  }, [authed, backendOk]);

  const sidebarNav = navItemsForRole(currentUser?.role);

  useEffect(() => {
    if (!authed || !currentUser) return;
    const r = String(currentUser.role || '').toLowerCase();
    if (r === 'administrator' && ADMIN_BLOCKED_PAGES.has(page)) setPage('dashboard');
    if (r !== 'administrator' && (page === 'audit' || page === 'users')) setPage('dashboard');
    if (r === 'administrator' && page === 'pipeline') setPage('pipeline'); // allowed for admin
  }, [authed, currentUser?.role, page]);

  function showLoading(msg, ms = 1400) {
    setLoadMsg(msg); setLoading(true);
    return new Promise(r => setTimeout(() => { setLoading(false); r(); }, ms));
  }

  function navigate(key) { setPage(key); setSidebarOpen(false); }

  async function handleLogout() {
    await authApi.logout();
    lsClear(LS_DX);
    lsClear(LS_RX);
    setAuthed(false); setCurrentUser(null);
    setPatients([]); setDiagnoses([]); setPrescriptions([]);
    setPatientSearch('');
  }

  if (!authed) {
    return (
      <LoginPage
        onLogin={u => { setCurrentUser(u); setAuthed(true); setSessionMsg(''); }}
        sessionMessage={sessionMsg}
      />
    );
  }

  const warnCount = prescriptions.filter(p =>
    p.safety_checks?.some(sc => sc.result === 'Critical' || sc.result === 'Warning')
  ).length;

  const shared = {
    patients, setPatients, diagnoses, setDiagnoses,
    prescriptions, setPrescriptions,
    selectedPatient: selectedPt, setSelectedPatient: setSelectedPt,
    setPage: navigate, showLoading, currentUser,
    backendOk,
    patientSearch, setPatientSearch,
  };

  const pages = {
    dashboard:      <Dashboard          {...shared} />,
    patients:       <PatientManagement  {...shared} />,
    patient_detail: <PatientDetail      {...shared} />,
    diagnosis:      <DiagnosisEngine    {...shared} />,
    treatment:      <TreatmentPlanning  {...shared} />,
    prescriptions:  <PrescriptionModule {...shared} />,
    reports:        <ReportsModule      {...shared} />,
    pipeline:       <PipelinePerformance backendOk={backendOk} />,
    audit:          <AuditLogs          currentUser={currentUser} backendOk={backendOk} />,
    users:          <UserManagement      currentUser={currentUser} backendOk={backendOk} />,
    settings:       <Settings           currentUser={currentUser} onLogout={handleLogout} />,
  };

  return (
    <>
      {loading && <LoadingOverlay message={loadMsg} />}
      <div className="app">
        <div className="bg-atmosphere" aria-hidden="true" />
        <div className="bg-glow" aria-hidden="true" />
        <div className="bg-glow2" aria-hidden="true" />

          {/* Mobile sidebar overlay */}
        {sidebarOpen && (
          <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} aria-hidden="true" />
        )}

        {/* SIDEBAR */}
        <aside className={`sidebar${sidebarOpen ? ' sidebar--open' : ''}`}>
          <div className="sidebar-logo">
            <div className="logo-icon">🏥</div>
            <div>
              <div className="logo-text">AI · CDSS</div>
              <div className="logo-sub">Clinical Decision Support</div>
            </div>
          </div>
          <nav className="sidebar-nav">
            <div className="nav-section-label">Main</div>
            {sidebarNav.map(n => {
              const badge = n.key === 'patients' ? (patients.length > 0 ? String(patients.length) : null)
                : n.key === 'prescriptions' ? (warnCount > 0 ? String(warnCount) : null) : null;
              return (
                <div key={n.key}
                  className={`nav-item ${page === n.key || (page === 'patient_detail' && n.key === 'patients') ? 'active' : ''}`}
                  onClick={() => navigate(n.key)}>
                  <span className="nav-icon">
                    {n.Icon ? <n.Icon size={18} className="nav-ai-diagnosis-logo" /> : n.icon}
                  </span>
                  <span>{n.label}</span>
                  {badge && <span className={`nav-badge ${n.key === 'patients' ? 'blue' : ''}`}>{badge}</span>}
                </div>
              );
            })}
          </nav>
          <div className="sidebar-footer">
            <div className="user-card" onClick={() => navigate('settings')}>
              <UserAvatar user={currentUser} size={34} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="user-name" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {currentUser?.full_name || currentUser?.name}
                </div>
                <div className="user-role">{currentUser?.role || 'Physician'}</div>
              </div>
              <span style={{ color: 'var(--text3)', fontSize: 13 }}>⚙️</span>
            </div>
          </div>
        </aside>

        {/* MAIN */}
        <main className="main">
          <div className="topbar">
            <button
              type="button"
              className="topbar-hamburger"
              onClick={() => setSidebarOpen(v => !v)}
              aria-label="Toggle navigation menu"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                {sidebarOpen
                  ? <><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></>
                  : <><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></>
                }
              </svg>
            </button>
            <div className="topbar-title">{sidebarNav.find(n => n.key === page)?.label || NAV.find(n => n.key === page)?.label || 'Dashboard'}</div>
            <div className="topbar-search">
              <span>🔍</span>
              <input
                className="form-input"
                style={{ minWidth: 0, flex: 1, maxWidth: 360 }}
                placeholder="Search patients by name or MRN…"
                value={patientSearch}
                onChange={(e) => setPatientSearch(e.target.value)}
                aria-label="Search patients by name or MRN"
              />
            </div>
            <ThemeToggle />
            <button
              type="button"
              className="topbar-logout"
              onClick={handleLogout}
              aria-label="Log out of AI-CDSS"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
              <span>Logout</span>
            </button>
          </div>
          <div className="page-content">{pages[page] ?? pages.dashboard}</div>
        </main>
      </div>
    </>
  );
}
