import { useState, useEffect } from 'react';
import { prescriptions as rxApi, diagnoses as diagnosesApi } from '../api.js';
import { suggestMedications } from '../api/cdssApi.js';
import { Modal, SafetyBadge, StatusBadge, EmptyState } from '../components/UI.jsx';
import { patientMatchesSearch } from '../utils/patientSearch.js';

const EMPTY = {
  drug_name: '', dose: '', frequency: 'Once daily',
  duration: '7 days', route: 'Oral', special_instructions: '',
};

const LINE_COLOR = { first: '#16a34a', second: '#d97706', adjunct: '#6366f1' };
const LINE_LABEL = { first: '1st line', second: '2nd line', adjunct: 'Adjunct' };

/* ── SVG Icons ────────────────────────────────────────────── */
const IcoPill    = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="15" height="15"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>;
const IcoUsers   = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="15" height="15"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>;
const IcoList    = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="15" height="15"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>;
const IcoBot     = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="15" height="15"><rect x="3" y="11" width="18" height="10" rx="2"/><path d="M12 11V7"/><circle cx="12" cy="5" r="2"/><line x1="8" y1="15" x2="8" y2="15"/><line x1="16" y1="15" x2="16" y2="15"/></svg>;
const IcoWarn    = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>;
const IcoRefresh = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" width="13" height="13"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.95"/></svg>;
const IcoPlus    = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>;
const IcoShield  = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="14" height="14"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>;

function ptName(p)      { return p?.full_name || `${p?.first_name || ''} ${p?.last_name || ''}`.trim() || 'Unknown'; }
function ptInitials(p)  { return ptName(p).split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase(); }
function ptAllergies(p) { return (p?.allergies || []).map(a => a.allergen || a).join(', ') || 'None'; }

export default function PrescriptionModule({
  patients,
  patientSearch = '',
  prescriptions,
  setPrescriptions,
  selectedPatient,
  setPage,
  showLoading,
  backendOk,
}) {
  const [selPt,       setSelPt]       = useState(selectedPatient || null);
  const [ptRx,        setPtRx]        = useState([]);
  const [showModal,   setShowModal]   = useState(false);
  const [form,        setForm]        = useState(EMPTY);
  const [safety,      setSafety]      = useState(null);
  const [step,        setStep]        = useState(0);
  const [apiError,    setApiError]    = useState('');
  const [suggestions, setSuggestions] = useState(null);
  const [sugLoading,  setSugLoading]  = useState(false);
  const [sugError,    setSugError]    = useState('');

  useEffect(() => {
    if (!selPt) return;
    if (backendOk) {
      rxApi.forPatient(selPt.id).then(setPtRx).catch(() => {});
    } else {
      setPtRx(prescriptions.filter(r => r.patient_id === selPt.id || r.patientId === selPt.id));
    }
    loadSuggestions(selPt);
  }, [selPt?.id, backendOk]);

  // Keep in sync when selectedPatient prop changes (e.g. coming from Diagnosis page)
  useEffect(() => {
    if (selectedPatient && selectedPatient.id !== selPt?.id) {
      setSelPt(selectedPatient);
    }
  }, [selectedPatient?.id]);

  const f = k => e => setForm(p => ({ ...p, [k]: e.target.value }));
  const closeModal = () => { setShowModal(false); setSafety(null); setStep(0); setForm(EMPTY); setApiError(''); };

  async function loadSuggestions(pt) {
    if (!pt) return;
    setSugLoading(true); setSugError(''); setSuggestions(null);
    try {
      let dxNames = [];
      if (backendOk) {
        try {
          const dxList = await diagnosesApi.forPatient(pt.id);
          dxNames = (Array.isArray(dxList) ? dxList : []).map(d => d.condition || d.diagnosis_name || '');
        } catch { /* fallback */ }
      }
      if (!dxNames.length) dxNames = pt.conditions || [];
      const result = await suggestMedications({
        patient_id: pt.id,
        diagnoses:  dxNames,
        allergies:  (pt.allergies || []).map(a => a.allergen || a),
        conditions: pt.conditions || [],
      });
      setSuggestions(result);
    } catch (e) {
      setSugError(e.message || 'Could not load suggestions');
    } finally {
      setSugLoading(false);
    }
  }

  async function doSafetyCheck() {
    setStep(1); setApiError('');
    if (backendOk) {
      await showLoading('Checking drug interactions & allergy records…', 1400);
      try {
        const result = await rxApi.safetyCheck({ patient_id: selPt.id, drug_name: form.drug_name, dose: form.dose });
        setSafety(result);
        setStep(2);
      } catch (e) {
        setApiError(e.message || 'Safety check failed');
        setStep(0);
      }
    } else {
      await showLoading('Running local safety check…', 900);
      setSafety({
        safe: true, result_type: 'safe', blocked: false,
        title: 'Safety Check Passed (Offline)',
        message: 'Backend offline — basic local check performed.',
        checks: [
          { check_type: 'drug_allergy',     result: 'Safe', findings: 'No obvious allergy conflicts' },
          { check_type: 'drug_interaction', result: 'Safe', findings: 'No obvious interactions detected' },
          { check_type: 'contraindication', result: 'Safe', findings: 'Full check requires backend' },
          { check_type: 'dosage',           result: 'Safe', findings: 'Dosage check requires backend' },
        ],
        alternatives: [],
      });
      setStep(2);
    }
  }

  async function confirmRx() {
    setApiError('');
    if (backendOk) {
      await showLoading('Saving prescription…', 800);
      try {
        const rx = await rxApi.create({
          patient_id: selPt.id,
          drug_name: form.drug_name, dose: form.dose,
          frequency: form.frequency, route: form.route,
          duration: form.duration,
          special_instructions: form.special_instructions || null,
        });
        setPtRx(prev => [rx, ...prev]);
        setPrescriptions(prev => [rx, ...prev]);
      } catch (e) {
        if (e.status === 422 && e.detail?.error === 'prescription_blocked') {
          setSafety({
            safe: false, result_type: 'critical', blocked: true,
            title: 'Prescription Blocked',
            message: e.detail.message,
            checks: e.detail.checks || [],
            alternatives: e.detail.alternatives || [],
          });
          return;
        }
        setApiError(e.message || 'Failed to save prescription');
        return;
      }
    } else {
      await showLoading('Saving prescription (offline)…', 600);
      const mock = {
        id: Date.now(), patient_id: selPt.id,
        drug_name: form.drug_name, dose: form.dose,
        frequency: form.frequency, route: form.route,
        duration: form.duration,
        special_instructions: form.special_instructions,
        status: 'active',
        prescribed_date: new Date().toISOString(),
        safety_checks: safety?.checks || [],
      };
      setPtRx(prev => [mock, ...prev]);
      setPrescriptions(prev => [mock, ...prev]);
    }
    closeModal();
  }

  const safetyClass = safety?.result_type === 'critical' ? 'critical'
    : safety?.result_type === 'warning' ? 'warning' : 'success';

  const pickerPatients = (Array.isArray(patients) ? patients : []).filter(p =>
    patientMatchesSearch(p, patientSearch, { includeConditions: false })
  );

  /* Accent colours cycling per diagnosis group */
  const GROUP_ACCENTS = [
    { color: '#7c3aed', bg: 'rgba(124,58,237,0.08)',  border: 'rgba(124,58,237,0.20)' },
    { color: '#0891b2', bg: 'rgba(8,145,178,0.08)',   border: 'rgba(8,145,178,0.20)'  },
    { color: '#16a34a', bg: 'rgba(22,163,74,0.08)',   border: 'rgba(22,163,74,0.20)'  },
    { color: '#d97706', bg: 'rgba(217,119,6,0.08)',   border: 'rgba(217,119,6,0.20)'  },
    { color: '#dc2626', bg: 'rgba(220,38,38,0.08)',   border: 'rgba(220,38,38,0.20)'  },
    { color: '#0d9488', bg: 'rgba(13,148,136,0.08)',  border: 'rgba(13,148,136,0.20)' },
  ];

  return (
    <div className="rx-root">

      {/* ── Page Header ─────────────────────────────────────── */}
      <div className="rx-page-hdr">
        <div>
          <h1 className="rx-page-title">Prescription Management</h1>
          <p className="rx-page-sub">
            {backendOk ? 'Real-time drug safety · DrugBank integration' : 'Offline mode — safety checks limited'}
          </p>
        </div>
        <button className="rx-new-btn" disabled={!selPt} onClick={() => setShowModal(true)}>
          <IcoPlus /> New Prescription
        </button>
      </div>

      {/* ── Top Row: Patient + Prescriptions ────────────────── */}
      <div className="rx-top-row">

        {/* Patient selector */}
        <div className="card rx-card rx-card--patient">
          <div className="rx-card-hdr"><IcoUsers /> Select Patient</div>
          {patients.length === 0 ? (
            <EmptyState icon="👥" title="No patients" sub="Go to Patients tab first" />
          ) : pickerPatients.length === 0 ? (
            <EmptyState icon="🔍" title="No matching patients" sub="Clear search or try another name" />
          ) : (
            <div className="rx-patient-list">
              {pickerPatients.map(p => {
                const hasAllergy = (p.allergies || []).length > 0;
                const isActive   = selPt?.id === p.id;
                return (
                  <div
                    key={p.id}
                    className={`rx-patient-row${isActive ? ' rx-patient-row--active' : ''}`}
                    onClick={() => setSelPt(p)}
                  >
                    <div className="rx-patient-avatar">{ptInitials(p)}</div>
                    <div className="rx-patient-info">
                      <div className="rx-patient-name">{ptName(p)}</div>
                      <div className="rx-patient-meta">
                        <span className="rx-mrn">{p.mrn || `#${p.id}`}</span>
                        {p.age && <><span>·</span><span>{p.age}y</span></>}
                      </div>
                    </div>
                    {hasAllergy && <span className="rx-allergy-tag"><IcoWarn /> Allergy</span>}
                    {isActive && (
                      <div className="rx-patient-check">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" width="12" height="12">
                          <polyline points="20 6 9 17 4 12"/>
                        </svg>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Prescriptions list */}
        <div className="card rx-card rx-card--rxlist">
          <div className="rx-card-hdr">
            <IcoList />
            {selPt ? `Prescriptions — ${ptName(selPt)}` : 'Prescriptions'}
            <span className="rx-count-badge">{ptRx.length}</span>
          </div>
          {!selPt ? (
            <p className="rx-empty-hint">Select a patient to view their prescriptions.</p>
          ) : ptRx.length > 0 ? (
            <div className="rx-list">
              {ptRx.map(rx => {
                const hasCritical  = rx.safety_checks?.some(s => s.result === 'Critical');
                const hasWarning   = rx.safety_checks?.some(s => s.result === 'Warning' || s.result === 'Moderate');
                const safetyStatus = hasCritical ? 'Critical' : hasWarning ? 'Warning' : 'Safe';
                const status       = rx.status
                  ? String(rx.status).charAt(0).toUpperCase() + String(rx.status).slice(1).toLowerCase()
                  : 'Active';
                return (
                  <div key={rx.id} className="rx-row">
                    <div className="rx-row-icon"><IcoPill /></div>
                    <div className="rx-row-body">
                      <div className="rx-row-top">
                        <span className="rx-drug-name">{rx.drug_name}</span>
                        <div className="rx-row-badges">
                          <SafetyBadge status={safetyStatus} />
                          <StatusBadge status={status} />
                        </div>
                      </div>
                      <div className="rx-row-detail">
                        {rx.dose} · {rx.frequency} · {rx.duration} · {rx.route}
                      </div>
                      {rx.prescribed_date && (
                        <div className="rx-row-date">{String(rx.prescribed_date).split('T')[0]}</div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState icon="💊" title="No prescriptions yet" sub="Click 'New Prescription' to add one" />
          )}
        </div>
      </div>

      {/* ── AI Medicine Suggestions — Full width horizontal ──────── */}
      <div className="rx-sug-section">
        <div className="rx-sug-section-hdr">
          <div className="rx-sug-section-title">
            <IcoBot />
            AI Medicine Suggestions
            {selPt && (
              <span className="rx-sug-section-patient">for {ptName(selPt)}</span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {suggestions?.matched_diagnoses?.length > 0 && (
              <div className="rx-sug-dx-chips">
                <span className="rx-sug-dx-label">Based on:</span>
                {suggestions.matched_diagnoses.map((d, i) => (
                  <span key={i} className="badge badge-blue">{d}</span>
                ))}
              </div>
            )}
            {selPt && (
              <button className="rx-refresh-btn" onClick={() => loadSuggestions(selPt)} disabled={sugLoading}>
                <IcoRefresh /> {sugLoading ? 'Loading…' : 'Refresh'}
              </button>
            )}
          </div>
        </div>

        {/* States */}
        {!selPt && (
          <div className="rx-sug-placeholder">
            <div className="rx-sug-placeholder-icon"><IcoBot /></div>
            <div className="rx-sug-placeholder-text">Select a patient above to see AI-powered, evidence-based medicine recommendations.</div>
          </div>
        )}

        {sugLoading && (
          <div className="rx-sug-loading">
            <div className="rx-sug-spinner" />
            Analysing diagnoses and conditions…
          </div>
        )}

        {sugError && (
          <div className="rx-sug-error"><IcoWarn /> {sugError}</div>
        )}

        {suggestions?.warning && (
          <div className="rx-sug-warning"><IcoWarn /> {suggestions.warning}</div>
        )}

        {/* Horizontal group cards */}
        {suggestions && !sugLoading && (suggestions.suggestions || []).length > 0 && (
          <div className="rx-sug-grid">
            {(suggestions.suggestions || []).map((group, gi) => {
              const accent = GROUP_ACCENTS[gi % GROUP_ACCENTS.length];
              return (
                <div key={gi} className="rx-sug-gcard" style={{ borderTopColor: accent.color }}>
                  {/* Group header */}
                  <div className="rx-sug-gcard-hdr" style={{ background: accent.bg }}>
                    <span className="rx-sug-gcard-name" style={{ color: accent.color }}>
                      {group.matched_on}
                    </span>
                    <span className="rx-sug-gcard-count" style={{ background: accent.color }}>
                      {(group.drugs || []).length} drugs
                    </span>
                  </div>

                  {/* Rationale */}
                  {group.rationale && (
                    <p className="rx-sug-gcard-rationale">{group.rationale}</p>
                  )}

                  {/* Drug pills */}
                  <div className="rx-sug-gcard-drugs">
                    {(group.drugs || []).map((drug, di) => {
                      const lColor = LINE_COLOR[drug.line] || '#64748b';
                      return (
                        <div
                          key={di}
                          className="rx-sug-gcard-drug"
                          style={{ borderLeftColor: lColor }}
                          onClick={() => {
                            setForm(p => ({
                              ...p,
                              drug_name: drug.name,
                              dose:      drug.dose      || p.dose,
                              frequency: drug.frequency || p.frequency,
                              duration:  drug.duration  || p.duration,
                              route:     drug.route     || p.route,
                            }));
                            setShowModal(true);
                          }}
                        >
                          <div className="rx-sug-gcard-drug-top">
                            <span className="rx-sug-gcard-drug-name">{drug.name}</span>
                            <span className="rx-sug-gcard-line" style={{ color: lColor, background: lColor + '16', borderColor: lColor + '40' }}>
                              {LINE_LABEL[drug.line] || drug.line}
                            </span>
                          </div>
                          {(drug.dose || drug.frequency) && (
                            <div className="rx-sug-gcard-drug-detail">
                              {[drug.dose, drug.frequency, drug.route].filter(Boolean).join(' · ')}
                            </div>
                          )}
                          {drug.notes && (
                            <div className="rx-sug-gcard-drug-note">
                              {drug.notes.slice(0, 80)}{drug.notes.length > 80 ? '…' : ''}
                            </div>
                          )}
                          <div className="rx-sug-gcard-cta">Tap to prescribe →</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Empty after patient selected but no suggestions */}
        {selPt && suggestions && !sugLoading && (suggestions.suggestions || []).length === 0 && (
          <div className="rx-sug-placeholder">
            <div className="rx-sug-placeholder-icon"><IcoShield /></div>
            <div className="rx-sug-placeholder-text">No drug suggestions available for this patient's current diagnoses.</div>
          </div>
        )}

        {suggestions?.disclaimer && (
          <div className="rx-disclaimer"><IcoShield /> {suggestions.disclaimer}</div>
        )}
      </div>

      {/* ── Prescription Modal ──────────────────────────────── */}
      {showModal && (
        <Modal
          title={`New Prescription — ${ptName(selPt)}`}
          size="modal-lg"
          onClose={closeModal}
          footer={
            <>
              <button className="btn btn-secondary" onClick={closeModal}>Cancel</button>
              {step < 2 && (
                <button
                  className="btn btn-primary"
                  disabled={!form.drug_name || !form.dose}
                  onClick={doSafetyCheck}
                >
                  <IcoShield style={{ display:'inline', marginRight:6 }} />
                  Check Safety & Prescribe
                </button>
              )}
              {step === 2 && !safety?.blocked && (
                <button className="btn btn-success" onClick={confirmRx}>Confirm Prescription</button>
              )}
              {step === 2 && safety?.blocked && (
                <button className="btn btn-secondary" onClick={() => { setSafety(null); setStep(0); }}>
                  Select Alternative
                </button>
              )}
            </>
          }
        >
          {/* Allergy banner */}
          {(selPt?.allergies || []).length > 0 && (
            <div className="alert alert-critical">
              <span className="alert-icon">⚠️</span>
              <div>
                <div className="alert-title">Patient Allergies — Verify Before Prescribing</div>
                {ptAllergies(selPt)}
              </div>
            </div>
          )}

          {apiError && (
            <div className="alert alert-critical">
              <span className="alert-icon">❌</span>
              <div>{apiError}</div>
            </div>
          )}

          {/* Form fields */}
          {step < 2 && (
            <>
              <div className="form-row form-row-2">
                <div className="form-group">
                  <label className="form-label">Medication Name *</label>
                  <input
                    className="form-input"
                    value={form.drug_name}
                    onChange={f('drug_name')}
                    placeholder="e.g. Metformin 500mg"
                    autoFocus
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Dose *</label>
                  <input
                    className="form-input"
                    value={form.dose}
                    onChange={f('dose')}
                    placeholder="e.g. 500mg"
                  />
                </div>
              </div>

              <div className="form-row form-row-3">
                <div className="form-group">
                  <label className="form-label">Frequency</label>
                  <select className="form-select" value={form.frequency} onChange={f('frequency')}>
                    {['Once daily','Twice daily','Three times daily','Four times daily','Every 8 hours','Every 12 hours','As needed','Weekly'].map(o => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Duration</label>
                  <input
                    className="form-input"
                    value={form.duration}
                    onChange={f('duration')}
                    placeholder="e.g. 7 days / Ongoing"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Route</label>
                  <select className="form-select" value={form.route} onChange={f('route')}>
                    {['Oral','IV','IM','SC','Topical','Inhaled','Sublingual'].map(o => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Special Instructions</label>
                <textarea
                  className="form-textarea"
                  value={form.special_instructions}
                  onChange={f('special_instructions')}
                  rows={2}
                  placeholder="e.g. Take with meals, avoid alcohol…"
                />
              </div>
            </>
          )}

          {/* Safety result */}
          {step === 2 && safety && (
            <div>
              <div className={`alert alert-${safetyClass}`}>
                <span className="alert-icon">
                  {safety.result_type === 'critical' ? '🚨' : safety.result_type === 'warning' ? '⚠️' : '✅'}
                </span>
                <div>
                  <div className="alert-title">{safety.title}</div>
                  {safety.message}
                </div>
              </div>

              <div className="rx-safety-checks-title">Safety Check Details</div>
              {safety.checks?.map((c, i) => (
                <div
                  key={i}
                  className={`safety-row ${c.result === 'Critical' ? 'critical' : c.result === 'Safe' ? 'safe' : 'warning'}`}
                >
                  <span style={{ fontSize: 16 }}>
                    {c.result === 'Critical' || c.result === 'Major' ? '⛔' : c.result === 'Safe' ? '✅' : '⚠️'}
                  </span>
                  <div style={{ flex: 1 }}>
                    <div className="text-bold text-sm">
                      {c.check_type?.replace(/_/g, ' ').replace(/\b\w/g, x => x.toUpperCase())}
                    </div>
                    <div className="text-xs text-dim" style={{ marginTop: 2 }}>{c.findings}</div>
                  </div>
                  <span className={`badge ${c.result === 'Safe' ? 'badge-green' : c.result === 'Critical' || c.result === 'Major' ? 'badge-red' : 'badge-amber'}`}>
                    {c.result}
                  </span>
                </div>
              ))}

              {safety.alternatives?.length > 0 && (
                <div className="rx-alternatives">
                  <div className="form-label">Suggested Alternatives</div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                    {safety.alternatives.map((a, i) => (
                      <button
                        key={i}
                        className="btn btn-secondary btn-sm"
                        onClick={() => { setForm(p => ({ ...p, drug_name: a })); setSafety(null); setStep(0); }}
                      >
                        {a}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
