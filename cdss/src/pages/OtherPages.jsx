import { useState, useEffect, useCallback } from 'react';
import { SafetyBadge, EmptyState } from '../components/UI.jsx';
import UserAvatar from '../components/UserAvatar.jsx';
import AiDiagnosisLogo from '../components/AiDiagnosisLogo.jsx';
import { patients as patientsApi, diagnoses as diagnosesApi, prescriptions as prescriptionsApi, auditLogs as auditLogsApi, adminUsers as adminUsersApi } from '../api.js';
import { downloadClinicalReportPdf } from '../reportPdf.js';
import { patientMatchesSearch } from '../utils/patientSearch.js';
import { getPipelineMetrics } from '../api/cdssApi.js';

function reportPatientName(p) {
  if (!p) return 'Unknown';
  return (
    p.full_name ||
    p.name ||
    `${p.first_name || ''} ${p.last_name || ''}`.trim() ||
    'Unknown'
  );
}

function recordMatchesPatient(rec, patientId) {
  if (patientId == null || rec == null) return false;
  const rid = rec.patientId ?? rec.patient_id;
  if (rid == null) return false;
  return Number(rid) === Number(patientId);
}

// ─── REPORTS ─────────────────────────────────────────────────────────────────
export function ReportsModule({
  patients,
  setPatients,
  patientSearch = '',
  diagnoses,
  prescriptions,
  showLoading,
  backendOk,
}) {
  const [selPt,      setSelPt]      = useState(null);
  const [reportType, setReportType] = useState('Full Clinical Report');
  const [dateFrom,   setDateFrom]   = useState('');
  const [dateTo,     setDateTo]     = useState('');
  const [generated,  setGenerated]  = useState(false);

  useEffect(() => {
    if (!backendOk || patients.length > 0) return;
    let cancelled = false;
    patientsApi
      .list('')
      .then((data) => {
        if (!cancelled && Array.isArray(data)) setPatients(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [backendOk, patients.length, setPatients]);

  const reportPickerPatients = (Array.isArray(patients) ? patients : []).filter((p) =>
    patientMatchesSearch(p, patientSearch, { includeConditions: false })
  );

  // In-session data as fallback
  const ptDxSession = diagnoses.filter((d) => recordMatchesPatient(d, selPt?.id));
  const ptRxSession = prescriptions.filter((r) => recordMatchesPatient(r, selPt?.id));

  // Enriched data fetched from backend (filled during generate)
  const [liveData, setLiveData] = useState(null);

  const ptDx = liveData?.diagnoses ?? ptDxSession;
  const ptRx = liveData?.prescriptions ?? ptRxSession;
  const ptConditions = liveData?.conditions ?? selPt?.conditions ?? [];
  const ptAllergies  = liveData?.allergies  ?? selPt?.allergies  ?? [];

  async function fetchLivePatientData(patientId) {
    const [dxList, rxList, patDetail] = await Promise.allSettled([
      diagnosesApi.forPatient(patientId),
      prescriptionsApi.forPatient(patientId),
      patientsApi.get(patientId),
    ]);
    return {
      diagnoses:   dxList.status   === 'fulfilled' && Array.isArray(dxList.value)   ? dxList.value   : [],
      prescriptions: rxList.status === 'fulfilled' && Array.isArray(rxList.value)   ? rxList.value   : [],
      conditions:  patDetail.status === 'fulfilled' ? (patDetail.value?.conditions  ?? patDetail.value?.medical_histories ?? []) : [],
      allergies:   patDetail.status === 'fulfilled' ? (patDetail.value?.allergies   ?? []) : [],
    };
  }

  async function runPdfDownload(overrideData) {
    if (!selPt) return;
    const data = overrideData ?? liveData;
    downloadClinicalReportPdf({
      patient: selPt,
      reportType,
      dateFrom,
      dateTo,
      diagnoses:   data?.diagnoses    ?? ptDxSession,
      prescriptions: data?.prescriptions ?? ptRxSession,
      conditions:  data?.conditions   ?? ptConditions,
      allergies:   data?.allergies    ?? ptAllergies,
    });
  }

  async function generate() {
    if (!selPt) return;
    await showLoading('Fetching latest clinical data…', 600);
    let live = null;
    try {
      live = await fetchLivePatientData(selPt.id);
      setLiveData(live);
    } catch {
      // fallback to in-session state
    }
    await showLoading('Building PDF document…', 400);
    runPdfDownload(live);
    setGenerated(true);
  }

  function downloadPdfAgain() {
    runPdfDownload();
  }

  const REPORT_TYPES = [
    { type: 'Full Clinical Report', icon: '📄', desc: 'Complete record: demographics, diagnoses, treatments, prescriptions, AI reasoning' },
    { type: 'Diagnostic Report', Icon: AiDiagnosisLogo, desc: 'AI suggestions with confidence scores, XAI explanations, ICD-10 codes' },
    { type: 'Treatment Summary',    icon: '💊', desc: 'Treatment plans with evidence base and monitoring parameters' },
    { type: 'Prescription History', icon: '📋', desc: 'All prescriptions with drug safety verification results' },
  ];

  return (
    <div>
      <div className="section-hdr">
        <div>
          <div className="section-title">Clinical Reports</div>
          <div className="section-sub">Generate comprehensive clinical documentation (FR9 — Audit, NFR12)</div>
        </div>
      </div>

      <div className="grid-7-5">
        <div>
          {!generated ? (
            <div className="card">
              <div className="card-title">📊 Report Configuration</div>
              <div className="form-group">
                <label className="form-label">Patient *</label>
                <select
                  className="form-select"
                  value={selPt != null ? String(selPt.id) : ''}
                  onChange={(e) => {
                    const v = e.target.value;
                    setSelPt(patients.find((p) => String(p.id) === v) || null);
                  }}
                >
                  <option value="">Select patient…</option>
                  {reportPickerPatients.map((p) => (
                    <option key={p.id} value={String(p.id)}>
                      {reportPatientName(p)} — {p.mrn || `ID ${p.id}`}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Report Type</label>
                <select className="form-select" value={reportType} onChange={e => setReportType(e.target.value)}>
                  {REPORT_TYPES.map(t => <option key={t.type}>{t.type}</option>)}
                </select>
              </div>
              <div className="form-row form-row-2">
                <div className="form-group">
                  <label className="form-label">Date From</label>
                  <input className="form-input" type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Date To</label>
                  <input className="form-input" type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} />
                </div>
              </div>
              <button className="btn btn-primary" disabled={!selPt} onClick={generate}>
                📊 Generate Report
              </button>
            </div>
          ) : (
            <div className="card">
              <div className="flex-between mb-16">
                <div>
                  <span className="badge badge-green">✅ Report Generated</span>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: 700, marginTop: 8 }}>
                    {reportType}
                  </div>
                  <div className="text-xs text-muted" style={{ marginTop: 3 }}>
                    {reportPatientName(selPt)} · {selPt?.id} · {new Date().toLocaleDateString('en-SA')}
                  </div>
                </div>
                <div className="flex-center gap-8">
                  <button type="button" className="btn btn-secondary btn-sm" onClick={downloadPdfAgain}>
                    📄 PDF
                  </button>
                  <button className="btn btn-secondary btn-sm">📧 Email</button>
                  <button className="btn btn-secondary btn-sm" onClick={() => setGenerated(false)}>← Back</button>
                </div>
              </div>

              <div className="sep" />

              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, marginBottom: 10 }}>Patient Information</div>
              <div className="form-row form-row-2">
                {[['Name', reportPatientName(selPt)], ['Patient ID', selPt?.id], ['MRN', selPt?.mrn],
                  ['Age', selPt?.age != null ? `${selPt.age} years` : '—'], ['Gender', selPt?.gender], ['Blood Type', selPt?.blood_type || selPt?.bloodType || '—'],
                ].map(([l, v]) => (
                  <div key={l} className="info-row">
                    <span className="info-label">{l}</span><span className="info-value">{v}</span>
                  </div>
                ))}
              </div>

              {ptConditions.length > 0 && <>
                <div className="sep" />
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, marginBottom: 10 }}>Known Conditions</div>
                {ptConditions.map((c, i) => (
                  <div key={i} className="text-sm" style={{ padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
                    {c.condition || c} {c.icd_code ? <span className="text-xs text-muted">· {c.icd_code}</span> : null}
                  </div>
                ))}
              </>}

              {ptAllergies.length > 0 && <>
                <div className="sep" />
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, marginBottom: 10 }}>Allergies</div>
                {ptAllergies.map((a, i) => (
                  <div key={i} className="text-sm" style={{ padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
                    <span className="badge badge-red" style={{ marginRight: 6 }}>{a.allergen || a}</span>
                    {a.severity && <span className="text-xs text-muted">{a.severity}{a.reaction ? ` — ${a.reaction}` : ''}</span>}
                  </div>
                ))}
              </>}

              {ptDx.length > 0 && <>
                <div className="sep" />
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, marginBottom: 10 }}>Diagnoses</div>
                {ptDx.map(d => (
                  <div key={d.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                    <div className="flex-between">
                      <span className="text-bold">{d.condition || d.diagnosis_name}</span>
                      <span className="badge badge-blue">{(d.confidence ?? d.confidence_score ?? '—')}% confidence</span>
                    </div>
                    <div className="text-xs text-muted">ICD-10: {d.icd || d.diagnosis_code} · {d.date || (d.diagnosed_at && String(d.diagnosed_at).split('T')[0])} · {d.source}</div>
                  </div>
                ))}
              </>}

              {ptRx.length > 0 && <>
                <div className="sep" />
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, marginBottom: 10 }}>Prescriptions & Medications</div>
                {ptRx.map(r => {
                  const hasCritical = r.safety_checks?.some(s => s.result === 'Critical');
                  const hasWarning = r.safety_checks?.some(s => s.result === 'Warning' || s.result === 'Moderate');
                  const safety = hasCritical ? 'Critical' : hasWarning ? 'Warning' : (r.safety || r.safety_status || 'Safe');
                  return (
                  <div key={r.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                    <div className="flex-between">
                      <span className="text-bold">{r.drug_name || r.drug}</span>
                      <SafetyBadge status={safety} />
                    </div>
                    <div className="text-xs text-muted">
                      {[r.dose, r.frequency || r.freq, r.duration, r.route].filter(Boolean).join(' · ')}
                      {(r.date || r.prescribed_at) && <span> · {(r.date || String(r.prescribed_at || '').split('T')[0])}</span>}
                    </div>
                    {r.notes && <div className="text-xs text-muted" style={{ marginTop: 2 }}>Notes: {r.notes}</div>}
                  </div>
                  );
                })}
              </>}

              {ptDx.length === 0 && ptRx.length === 0 && ptConditions.length === 0 && (
                <div className="text-sm text-muted" style={{ padding: '12px 0' }}>
                  No clinical data found for this patient in the database.
                </div>
              )}

              <div className="sep" />
              <div style={{ fontSize: 11, color: 'var(--text3)', textAlign: 'center', lineHeight: 1.7 }}>
                AI-Powered CDSS · This report is an assistive tool — professional medical judgment is not replaced.<br />
                Audit logged · Physician: Dr. Alanoud Alsaud · {new Date().toLocaleString()}
              </div>
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-title">📋 Report Types</div>
          {REPORT_TYPES.map(r => (
            <div key={r.type}
              style={{ padding: '11px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer' }}
              onClick={() => setReportType(r.type)}>
              <div className="flex-center gap-8">
                <span className="report-type-icon" aria-hidden>
                  {r.Icon ? <r.Icon size={18} className="report-type-ai-logo" /> : r.icon}
                </span>
                <span className="text-bold text-sm"
                  style={{ color: reportType === r.type ? 'var(--accent)' : 'var(--text)' }}>
                  {r.type}
                </span>
              </div>
              <div className="text-xs text-muted" style={{ marginTop: 4 }}>{r.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── AUDIT LOGS (admin) ───────────────────────────────────────────────────────
// ─── PIPELINE PERFORMANCE ────────────────────────────────────────────────────

const GRADE_BG = { A: '#22c55e', B: '#3b82f6', C: '#f59e0b', D: '#ef4444' };

function MiniBar({ value, color }) {
  return (
    <div style={{ height: 6, width: 80, borderRadius: 3, background: 'rgba(255,255,255,0.08)', display: 'inline-block', verticalAlign: 'middle' }}>
      <div style={{ height: '100%', width: `${Math.min(100, value || 0)}%`, borderRadius: 3, background: color || '#3b82f6', transition: 'width 0.6s' }} />
    </div>
  );
}

export function PipelinePerformance({ backendOk }) {
  const [records, setRecords] = useState([]);
  const [avgScore, setAvgScore] = useState(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!backendOk) return;
    setLoading(true);
    getPipelineMetrics(50)
      .then((data) => {
        setRecords(data.records || []);
        setAvgScore(data.average_score);
        setTotal(data.total || 0);
      })
      .catch((e) => setError(e?.response?.data?.detail || e?.message || 'Failed to load metrics'))
      .finally(() => setLoading(false));
  }, [backendOk]);

  return (
    <div>
      <div className="section-hdr">
        <div>
          <div className="section-title">Pipeline Performance</div>
          <div className="section-sub">5-agent clinical pipeline accuracy history and QA scores</div>
        </div>
        <button
          className="btn btn-secondary"
          onClick={() => {
            setLoading(true);
            getPipelineMetrics(50)
              .then((d) => { setRecords(d.records || []); setAvgScore(d.average_score); setTotal(d.total || 0); })
              .catch((e) => setError(e?.message))
              .finally(() => setLoading(false));
          }}
          disabled={loading}
        >
          🔄 Refresh
        </button>
      </div>

      {!backendOk && (
        <div className="alert alert-critical">
          <span className="alert-icon">⚠️</span>
          <div>Backend offline — pipeline metrics unavailable</div>
        </div>
      )}

      {error && (
        <div className="alert alert-critical">
          <span className="alert-icon">⚠️</span>
          <div>{error}</div>
        </div>
      )}

      {loading ? (
        <div className="card" style={{ textAlign: 'center', padding: 40 }}>
          <div className="text-muted">Loading pipeline metrics…</div>
        </div>
      ) : records.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 40 }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🚀</div>
          <div className="text-bold">No pipeline runs yet</div>
          <div className="text-muted text-sm" style={{ marginTop: 6 }}>
            Use the <b>Run Full 5-Agent Pipeline</b> button in the Diagnosis Engine to generate your first run.
          </div>
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div style={{ display: 'flex', gap: 14, marginBottom: 16, flexWrap: 'wrap' }}>
            {[
              { label: 'Total Runs', value: total },
              { label: 'Avg Score (last 50)', value: avgScore != null ? `${avgScore}%` : '—' },
              { label: 'Latest Grade', value: records[0]?.grade || '—', color: GRADE_BG[records[0]?.grade] },
              { label: 'Latest Score', value: records[0]?.overall_score != null ? `${records[0].overall_score}%` : '—' },
            ].map((c) => (
              <div key={c.label} className="card" style={{ flex: 1, minWidth: 140, padding: '14px 16px', textAlign: 'center' }}>
                <div style={{ fontSize: 22, fontWeight: 800, color: c.color || 'var(--accent)' }}>{c.value}</div>
                <div style={{ fontSize: 12, color: 'var(--text2)', marginTop: 4 }}>{c.label}</div>
              </div>
            ))}
          </div>

          {/* Per-run table */}
          <div className="card" style={{ padding: 0, overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: 'rgba(255,255,255,0.04)' }}>
                  {['Timestamp', 'Patient', 'Grade', 'Score', 'Diag Conf', 'Sym Cov', 'Med Safety', 'Top Diagnosis', 'LLM', 'Urgency'].map((h) => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, color: 'var(--text2)', whiteSpace: 'nowrap', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {records.map((r, i) => {
                  const gradeColor = GRADE_BG[r.grade] || '#64748b';
                  return (
                    <tr key={r.run_id || i} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <td style={{ padding: '9px 12px', color: 'var(--text2)', whiteSpace: 'nowrap' }}>
                        {r.timestamp ? new Date(r.timestamp).toLocaleString() : '—'}
                      </td>
                      <td style={{ padding: '9px 12px' }}>{r.patient_id ? `#${r.patient_id}` : '—'}</td>
                      <td style={{ padding: '9px 12px' }}>
                        <span style={{
                          background: gradeColor, color: '#fff', fontWeight: 800,
                          padding: '2px 8px', borderRadius: 4, fontSize: 13,
                        }}>{r.grade || '?'}</span>
                      </td>
                      <td style={{ padding: '9px 12px', fontWeight: 700 }}>{r.overall_score ?? '—'}%</td>
                      <td style={{ padding: '9px 12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          {r.scores?.diagnosis_confidence ?? '—'}%
                          <MiniBar value={r.scores?.diagnosis_confidence} color="#3b82f6" />
                        </div>
                      </td>
                      <td style={{ padding: '9px 12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          {r.scores?.symptom_coverage ?? '—'}%
                          <MiniBar value={r.scores?.symptom_coverage} color="#8b5cf6" />
                        </div>
                      </td>
                      <td style={{ padding: '9px 12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          {r.scores?.medication_safety ?? '—'}%
                          <MiniBar value={r.scores?.medication_safety} color="#22c55e" />
                        </div>
                      </td>
                      <td style={{ padding: '9px 12px', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.top_diagnosis || '—'}
                      </td>
                      <td style={{ padding: '9px 12px' }}>
                        <span style={{ fontSize: 11, padding: '2px 6px', borderRadius: 4, background: r.llm_used ? 'rgba(59,130,246,0.15)' : 'rgba(255,255,255,0.07)', color: r.llm_used ? '#3b82f6' : 'var(--text3)' }}>
                          {r.llm_used ? 'LLM' : 'Rule'}
                        </span>
                      </td>
                      <td style={{ padding: '9px 12px' }}>
                        <span style={{
                          fontSize: 11, padding: '2px 6px', borderRadius: 4,
                          background: r.urgency === 'critical' ? 'rgba(239,68,68,0.15)' : r.urgency === 'urgent' ? 'rgba(245,158,11,0.15)' : 'rgba(34,197,94,0.1)',
                          color: r.urgency === 'critical' ? '#ef4444' : r.urgency === 'urgent' ? '#f59e0b' : '#22c55e',
                        }}>
                          {r.urgency || '—'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export function AuditLogs({ currentUser, backendOk }) {
  const isAdmin = String(currentUser?.role || '').toLowerCase() === 'administrator';
  const [logs, setLogs] = useState([]);
  const [staff, setStaff] = useState([]);
  const [filterUserId, setFilterUserId] = useState('');
  const [logType, setLogType] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [staffErr, setStaffErr] = useState('');
  const [deletingId, setDeletingId] = useState(null);

  const typeColor = {
    auth: 'var(--accent)',
    data: 'var(--green)',
    clinical: 'var(--purple)',
    prescription: 'var(--amber)',
  };

  useEffect(() => {
    if (!isAdmin || !backendOk) return;
    let c = false;
    adminUsersApi
      .list()
      .then((rows) => {
        if (!c) setStaff(Array.isArray(rows) ? rows : []);
      })
      .catch((e) => {
        if (!c) setStaffErr(e.message || 'Could not load users');
      });
    return () => {
      c = true;
    };
  }, [isAdmin, backendOk]);

  const loadLogs = useCallback(() => {
    if (!isAdmin || !backendOk) return;
    setLoading(true);
    setError('');
    const params = {};
    if (filterUserId) params.user_id = filterUserId;
    if (logType) params.log_type = logType;
    auditLogsApi
      .list(params)
      .then((rows) => setLogs(Array.isArray(rows) ? rows : []))
      .catch((e) => setError(e.message || 'Failed to load audit logs'))
      .finally(() => setLoading(false));
  }, [isAdmin, backendOk, filterUserId, logType]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const filteredLogs = logs.filter((log) => {
    const ts = new Date(log.created_at);
    if (dateFrom && ts < new Date(dateFrom)) return false;
    if (dateTo) {
      const end = new Date(dateTo);
      end.setHours(23, 59, 59, 999);
      if (ts > end) return false;
    }
    return true;
  });

  function clearFilters() {
    setFilterUserId('');
    setLogType('');
    setDateFrom('');
    setDateTo('');
  }

  async function deactivateStaff(u) {
    if (!window.confirm(`Deactivate account for ${u.full_name} (${u.email})? They will no longer be able to sign in.`)) return;
    setDeletingId(u.id);
    setStaffErr('');
    try {
      await adminUsersApi.deactivate(u.id);
      setStaff((prev) => prev.filter((x) => x.id !== u.id));
      loadLogs();
    } catch (e) {
      setStaffErr(e.message || 'Failed to deactivate user');
    } finally {
      setDeletingId(null);
    }
  }

  if (!isAdmin) {
    return (
      <div>
        <div className="section-title mb-16">Audit Logs</div>
        <EmptyState
          icon="🔒"
          title="Administrator only"
          sub="Sign in as an administrator to view the audit trail and manage staff."
        />
      </div>
    );
  }

  if (!backendOk) {
    return (
      <div>
        <div className="section-title mb-16">Audit Logs</div>
        <div className="alert alert-warning">
          <span className="alert-icon">⚠️</span>
          <div>
            <div className="alert-title">Backend offline</div>
            Connect the API server to load audit data.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="section-hdr">
        <div>
          <div className="section-title">Audit Logs</div>
          <div className="section-sub">Filter by physician (or any user) and review system activity</div>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={loadLogs} disabled={loading}>
          {loading ? 'Loading…' : '↻ Refresh'}
        </button>
      </div>

      {error && (
        <div className="alert alert-critical mb-16">
          <span className="alert-icon">❌</span>
          <div>{error}</div>
        </div>
      )}

      <div className="card mb-20">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <div className="card-title" style={{ margin: 0 }}>🔎 Filters</div>
          {(filterUserId || logType || dateFrom || dateTo) && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={clearFilters}>
              ✕ Clear filters
            </button>
          )}
        </div>
        <div className="form-row form-row-2" style={{ marginBottom: 12 }}>
          <div className="form-group">
            <label className="form-label">Actor (user)</label>
            <select
              className="form-select"
              value={filterUserId}
              onChange={(e) => setFilterUserId(e.target.value)}
            >
              <option value="">All users</option>
              {staff.map((u) => (
                <option key={u.id} value={String(u.id)}>
                  {u.full_name} — {u.email} ({u.role})
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Log type</label>
            <select className="form-select" value={logType} onChange={(e) => setLogType(e.target.value)}>
              <option value="">All types</option>
              <option value="auth">auth</option>
              <option value="data">data</option>
              <option value="clinical">clinical</option>
              <option value="prescription">prescription</option>
            </select>
          </div>
        </div>
        <div className="form-row form-row-2">
          <div className="form-group">
            <label className="form-label">📅 Date from</label>
            <input
              type="date"
              className="form-input"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              max={dateTo || undefined}
            />
          </div>
          <div className="form-group">
            <label className="form-label">📅 Date to</label>
            <input
              type="date"
              className="form-input"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              min={dateFrom || undefined}
            />
          </div>
        </div>
        {(dateFrom || dateTo) && (
          <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text3)' }}>
            Showing <strong style={{ color: 'var(--accent)' }}>{filteredLogs.length}</strong> of {logs.length} logs
            {dateFrom && ` from ${new Date(dateFrom).toLocaleDateString()}`}
            {dateTo && ` to ${new Date(dateTo).toLocaleDateString()}`}
          </div>
        )}
      </div>

      <div className="card mb-20">
        <div className="card-title">📋 Event log {filteredLogs.length > 0 && <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text3)', marginLeft: 6 }}>({filteredLogs.length} entries)</span>}</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>User</th>
                <th>Action</th>
                <th>Type</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {filteredLogs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-muted text-sm" style={{ padding: '18px 12px' }}>
                    {loading ? 'Loading…' : 'No log entries for this filter.'}
                  </td>
                </tr>
              ) : (
                filteredLogs.map((l) => (
                  <tr key={l.id}>
                    <td>
                      <span className="text-mono text-xs text-accent">
                        {l.created_at ? new Date(l.created_at).toLocaleString() : '—'}
                      </span>
                    </td>
                    <td className="td-main">
                      {l.user_full_name || l.user_email || (l.user_id != null ? `User #${l.user_id}` : '—')}
                      {l.user_email && l.user_full_name ? (
                        <div className="text-xs text-muted">{l.user_email}</div>
                      ) : null}
                    </td>
                    <td>{l.action}</td>
                    <td>
                      <span
                        className="badge"
                        style={{
                          background: `${typeColor[l.log_type] || 'var(--text3)'}22`,
                          color: typeColor[l.log_type] || 'var(--text2)',
                          border: `1px solid ${(typeColor[l.log_type] || 'var(--text3)')}44`,
                        }}
                      >
                        {l.log_type}
                      </span>
                    </td>
                    <td className="text-sm text-dim">{l.detail || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="card-title">👥 Staff — deactivate physician / nurse / pharmacist</div>
        <p className="text-sm text-muted mb-16" style={{ marginBottom: 14 }}>
          Administrator accounts cannot be removed here. Deactivated users cannot sign in.
        </p>
        {staffErr && (
          <div className="alert alert-critical mb-12">
            <span className="alert-icon">❌</span>
            <div>{staffErr}</div>
          </div>
        )}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {staff.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-muted text-sm" style={{ padding: '14px 12px' }}>
                    No users loaded.
                  </td>
                </tr>
              ) : (
                staff.map((u) => {
                  const isAdminUser = String(u.role || '').toLowerCase() === 'administrator';
                  return (
                    <tr key={u.id}>
                      <td className="td-main">{u.full_name}</td>
                      <td className="text-xs text-muted">{u.email}</td>
                      <td>
                        <span className="badge badge-blue">{u.role}</span>
                      </td>
                      <td>{u.is_active ? <span className="badge badge-green">Active</span> : <span className="badge badge-amber">Inactive</span>}</td>
                      <td>
                        {!isAdminUser && u.is_active ? (
                          <button
                            type="button"
                            className="btn btn-sm btn-danger"
                            disabled={deletingId === u.id}
                            onClick={() => deactivateStaff(u)}
                          >
                            {deletingId === u.id ? '…' : 'Deactivate'}
                          </button>
                        ) : (
                          <span className="text-xs text-muted">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── USER MANAGEMENT (admin) ──────────────────────────────────────────────────

export function UserManagement({ currentUser, backendOk }) {
  const isAdmin = String(currentUser?.role || '').toLowerCase() === 'administrator';
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  useEffect(() => {
    if (!isAdmin || !backendOk) return;
    loadUsers();
  }, [isAdmin, backendOk]);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminUsersApi.list();
      // Filter to show only physicians
      const physicians = Array.isArray(data) ? data.filter(u => String(u.role).toLowerCase() === 'physician') : [];
      setUsers(physicians);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleDelete = async (user) => {
    if (!confirm(`Are you sure you want to deactivate ${user.full_name || user.email}? This will prevent them from logging in.`)) return;
    setDeletingId(user.id);
    try {
      await adminUsersApi.deactivate(user.id);
      setUsers(prev => prev.filter(u => u.id !== user.id));
    } catch (e) {
      alert(`Failed to deactivate user: ${e?.response?.data?.detail || e?.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  if (!isAdmin) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: 40 }}>
        <div className="text-muted">Access denied — administrator required</div>
      </div>
    );
  }

  return (
    <div>
      <div className="section-hdr">
        <div>
          <div className="section-title">Staff Management</div>
          <div className="section-sub">View and manage physician accounts</div>
        </div>
        <button
          className="btn btn-secondary"
          onClick={loadUsers}
          disabled={loading}
        >
          🔄 Refresh
        </button>
      </div>

      {!backendOk && (
        <div className="alert alert-critical">
          <span className="alert-icon">⚠️</span>
          <div>Backend offline — user management unavailable</div>
        </div>
      )}

      {error && (
        <div className="alert alert-critical">
          <span className="alert-icon">⚠️</span>
          <div>{error}</div>
        </div>
      )}

      {loading ? (
        <div className="card" style={{ textAlign: 'center', padding: 40 }}>
          <div className="text-muted">Loading physicians…</div>
        </div>
      ) : users.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 40 }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>👨‍⚕️</div>
          <div className="text-bold">No physicians found</div>
          <div className="text-muted text-sm" style={{ marginTop: 6 }}>
            No physician accounts are currently active.
          </div>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: 'rgba(255,255,255,0.04)' }}>
                {['Name', 'Email', 'Username', 'License', 'Last Login', 'Actions'].map((h) => (
                  <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, color: 'var(--text2)', whiteSpace: 'nowrap', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <td style={{ padding: '9px 12px' }}>
                    <div style={{ fontWeight: 600 }}>{u.full_name || u.name || '—'}</div>
                  </td>
                  <td style={{ padding: '9px 12px', color: 'var(--text2)' }}>{u.email}</td>
                  <td style={{ padding: '9px 12px', color: 'var(--text2)' }}>{u.username || '—'}</td>
                  <td style={{ padding: '9px 12px', color: 'var(--text2)' }}>{u.license_number || '—'}</td>
                  <td style={{ padding: '9px 12px', color: 'var(--text2)', whiteSpace: 'nowrap' }}>
                    {u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}
                  </td>
                  <td style={{ padding: '9px 12px' }}>
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={() => handleDelete(u)}
                      disabled={deletingId === u.id}
                      style={{ fontSize: 11, padding: '4px 8px' }}
                    >
                      {deletingId === u.id ? 'Deactivating...' : 'Deactivate'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── SETTINGS ─────────────────────────────────────────────────────────────────
function LogoutGlyph({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}

export function Settings({ currentUser, onLogout }) {
  const displayName =
    currentUser?.full_name || currentUser?.name || currentUser?.username || '—';
  const displayLicense =
    currentUser?.license_number != null && String(currentUser.license_number).trim() !== ''
      ? currentUser.license_number
      : '—';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minHeight: '70vh', justifyContent: 'center' }}>
      <div className="section-title mb-20" style={{ width: '100%', maxWidth: 720, textAlign: 'left' }}>Settings</div>
      <div className="flex-col" style={{ gap: 14, maxWidth: 720, width: '100%' }}>
        <div className="card">
          <div className="card-title">👤 Profile</div>
          <div className="settings-profile-avatar-row">
            <UserAvatar user={currentUser} size={72} />
            <div className="text-xs text-muted" style={{ lineHeight: 1.5 }}>
              {currentUser?.profile_image
                ? 'Profile photo from registration.'
                : 'No photo — initials are shown in the sidebar.'}
            </div>
          </div>
          {[
            ['Name', displayName],
            ['Username', currentUser?.username || '—'],
            ['Email', currentUser?.email || '—'],
            ['Role', currentUser?.role || '—'],
            ['License', displayLicense],
          ].map(([l, v]) => (
            <div key={l} className="info-row">
              <span className="info-label">{l}</span>
              <span className="info-value">{v}</span>
            </div>
          ))}
            <div className="sep" />
            {typeof onLogout === 'function' && (
              <button type="button" className="btn btn-secondary settings-logout" onClick={onLogout}>
                <LogoutGlyph className="settings-logout-icon" />
                <span>Logout</span>
              </button>
            )}
        </div>
      </div>
    </div>
  );
}
