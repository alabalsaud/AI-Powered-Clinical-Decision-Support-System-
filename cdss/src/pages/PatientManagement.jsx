import { useState } from 'react';
import { patients as patientsApi } from '../api.js';
import { Modal, EmptyState } from '../components/UI.jsx';
import AiDiagnosisLogo from '../components/AiDiagnosisLogo.jsx';
import { patientMatchesSearch } from '../utils/patientSearch.js';

const EMPTY = {
  first_name:'', last_name:'', date_of_birth:'', gender:'Female',
  weight:'', height:'', blood_type:'A+', phone:'', email:'',
  allergies:'', medications:'', conditions:'',
};

/* ── SVG Icons ──────────────────────────────────────────── */
const IconView = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="13" height="13">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
    <circle cx="12" cy="12" r="3"/>
  </svg>
);
const IconDiagnose = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="13" height="13">
    <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
  </svg>
);
const IconTrash = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="13" height="13">
    <polyline points="3 6 5 6 21 6"/>
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
    <path d="M10 11v6M14 11v6"/>
    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
  </svg>
);
const IconWarning = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="28" height="28">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
    <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
  </svg>
);
const IconPlus = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" width="15" height="15">
    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
  </svg>
);
const IconSearch = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="15" height="15">
    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
  </svg>
);

export default function PatientManagement({
  patients,
  setPatients,
  setPage,
  setSelectedPatient,
  showLoading,
  backendOk,
  patientSearch,
  setPatientSearch,
  currentUser,
}) {
  const search    = patientSearch ?? '';
  const setSearch = setPatientSearch ?? (() => {});
  const [showModal,     setShowModal]     = useState(false);
  const [form,          setForm]          = useState(EMPTY);
  const [apiError,      setApiError]      = useState('');
  const [deleteTarget,  setDeleteTarget]  = useState(null);   // patient to confirm delete
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError,   setDeleteError]   = useState('');

  function f(k) { return e => setForm(p => ({ ...p, [k]: e.target.value })); }

  // ── Helpers ─────────────────────────────────────────────
  function ptName(p)       { return p.full_name || `${p.first_name} ${p.last_name}`; }
  function ptAllergies(p)  { return p.allergies || []; }
  function ptConditions(p) { return p.medical_histories?.map(h => h.condition) || p.conditions || []; }

  // ── Save new patient ────────────────────────────────────
  async function handleSave() {
    if (!form.first_name || !form.last_name || !form.date_of_birth) return;
    setApiError('');
    const payload = {
      first_name:    form.first_name,
      last_name:     form.last_name,
      date_of_birth: form.date_of_birth,
      gender:        form.gender,
      weight:        parseFloat(form.weight) || null,
      height:        parseFloat(form.height) || null,
      blood_type:    form.blood_type || null,
      phone:         form.phone || null,
      email:         form.email || null,
      allergies: form.allergies
        ? form.allergies.split(',').map(s => s.trim()).filter(Boolean)
            .map(a => ({ allergen: a, allergy_type: 'Drug', severity: 'Moderate' }))
        : [],
      conditions: form.conditions
        ? form.conditions.split(',').map(s => s.trim()).filter(Boolean)
            .map(c => ({ condition: c }))
        : [],
    };

    if (backendOk) {
      try {
        await showLoading('Saving patient to PostgreSQL…', 800);
        const newPt = await patientsApi.create(payload);
        setPatients(prev => [newPt, ...prev]);
      } catch (e) {
        setApiError(e.message || 'Failed to save patient');
        return;
      }
    } else {
      await showLoading('Saving patient (offline mode)…', 800);
      const mock = {
        id: Date.now(), mrn: `MRN-${Date.now()}`,
        first_name: form.first_name, last_name: form.last_name,
        full_name: `${form.first_name} ${form.last_name}`,
        date_of_birth: form.date_of_birth, gender: form.gender,
        weight: parseFloat(form.weight)||0, height: parseFloat(form.height)||0,
        blood_type: form.blood_type, phone: form.phone,
        is_active: true, version: 1,
        created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        allergies: payload.allergies.map((a,i) => ({ id:i, patient_id:0, created_at:new Date().toISOString(), ...a })),
        medical_histories: payload.conditions.map((c,i) => ({ id:i, patient_id:0, is_active:true, created_at:new Date().toISOString(), ...c })),
      };
      setPatients(prev => [mock, ...prev]);
    }
    setShowModal(false);
    setForm(EMPTY);
  }

  // ── Delete (soft-deactivate) ─────────────────────────────
  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    setDeleteError('');
    try {
      if (backendOk) {
        await patientsApi.deactivate(deleteTarget.id);
      }
      setPatients(prev => prev.filter(x => x.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (e) {
      setDeleteError(e.message || 'Failed to delete patient. Please try again.');
    } finally {
      setDeleteLoading(false);
    }
  }

  const filtered = patients.filter(p =>
    patientMatchesSearch(p, search, { includeConditions: true })
  );

  return (
    <div>
      {/* ── Header ───────────────────────────────────────── */}
      <div className="pm-header">
        <div>
          <h1 className="section-title">Patient Management</h1>
          <p className="section-sub">
            {backendOk
              ? `PostgreSQL · ${patients.length} patient${patients.length !== 1 ? 's' : ''} loaded`
              : 'Offline mode — changes stored locally only'}
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          <IconPlus /> New Patient
        </button>
      </div>

      {/* ── Alerts ───────────────────────────────────────── */}
      {apiError && !showModal && (
        <div className="alert alert-critical mb-16">
          <span className="alert-icon">❌</span>
          <div>{apiError}</div>
        </div>
      )}
      {!backendOk && (
        <div className="alert alert-warning mb-16">
          <span className="alert-icon">⚠️</span>
          <div>
            <div className="alert-title">Backend Offline</div>
            Start the FastAPI server to enable full functionality.
          </div>
        </div>
      )}

      {/* ── Table Card ───────────────────────────────────── */}
      <div className="card">
        {/* Search bar */}
        <div className="pm-search-row">
          <div className="pm-search-box">
            <IconSearch />
            <input
              className="pm-search-input"
              placeholder="Search by name, MRN, or condition…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <span className="pm-count">{filtered.length} patient{filtered.length !== 1 ? 's' : ''}</span>
        </div>

        {filtered.length === 0 ? (
          <EmptyState
            icon="👥"
            title="No patients found"
            sub={patients.length === 0
              ? 'Add your first patient or start the backend to load data'
              : 'Try a different search term'}
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>MRN</th>
                  <th>Name</th>
                  <th>DOB</th>
                  <th>Gender</th>
                  <th>Blood</th>
                  <th>Conditions</th>
                  <th>Allergies</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(p => (
                  <tr key={p.id}>
                    <td>
                      <span className="pm-mrn">{p.mrn}</span>
                    </td>
                    <td className="td-main">{ptName(p)}</td>
                    <td className="text-xs text-muted">{p.date_of_birth}</td>
                    <td className="text-sm" style={{ color: 'var(--text2)' }}>{p.gender}</td>
                    <td>
                      <span className="badge badge-blue">{p.blood_type || '—'}</span>
                    </td>
                    <td>
                      {ptConditions(p).length > 0
                        ? ptConditions(p).slice(0, 2).map((c, i) => (
                            <span key={i} className="badge badge-purple"
                              style={{ marginRight: 3, marginBottom: 2, fontSize: 10 }}>
                              {c}
                            </span>
                          ))
                        : <span className="text-muted text-xs">—</span>}
                    </td>
                    <td>
                      {ptAllergies(p).length > 0
                        ? ptAllergies(p).slice(0, 2).map((a, i) => (
                            <span key={i} className="badge badge-red"
                              style={{ marginRight: 3, fontSize: 10 }}>
                              ⚠ {a.allergen || a}
                            </span>
                          ))
                        : <span className="badge badge-green">NKDA</span>}
                    </td>
                    <td>
                      <div className="pm-actions">
                        {/* View */}
                        <button
                          type="button"
                          className="pm-btn pm-btn--view"
                          title="View patient record"
                          onClick={() => { setSelectedPatient(p); setPage('patient_detail'); }}
                        >
                          <IconView /> View
                        </button>
                        {/* Diagnose */}
                        <button
                          type="button"
                          className="pm-btn pm-btn--diagnose"
                          title="Run AI diagnosis"
                          onClick={() => { setSelectedPatient(p); setPage('diagnosis'); }}
                        >
                          <AiDiagnosisLogo size={13} className="btn-embed-ai-logo" aria-hidden />
                          Diagnose
                        </button>
                        {/* Delete */}
                        <button
                          type="button"
                          className="pm-btn pm-btn--delete"
                          title="Delete patient record"
                          onClick={() => { setDeleteTarget(p); setDeleteError(''); }}
                        >
                          <IconTrash /> Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Delete Confirmation Modal ─────────────────────── */}
      {deleteTarget && (
        <div className="pm-del-overlay" onClick={() => !deleteLoading && setDeleteTarget(null)}>
          <div className="pm-del-modal" onClick={e => e.stopPropagation()}>
            {/* Icon */}
            <div className="pm-del-icon-wrap">
              <div className="pm-del-icon-ring">
                <span style={{ color: '#f87171' }}><IconWarning /></span>
              </div>
            </div>

            {/* Content */}
            <div className="pm-del-content">
              <h2 className="pm-del-title">Delete Patient Record?</h2>
              <p className="pm-del-sub">
                You are about to permanently remove this patient from the active list.
                This action cannot be undone.
              </p>

              {/* Patient info card */}
              <div className="pm-del-patient-card">
                <div className="pm-del-patient-avatar">
                  {ptName(deleteTarget).charAt(0).toUpperCase()}
                </div>
                <div className="pm-del-patient-info">
                  <div className="pm-del-patient-name">{ptName(deleteTarget)}</div>
                  <div className="pm-del-patient-meta">
                    <span className="pm-mrn">{deleteTarget.mrn}</span>
                    <span>·</span>
                    <span>{deleteTarget.gender}</span>
                    <span>·</span>
                    <span>{deleteTarget.date_of_birth}</span>
                  </div>
                </div>
              </div>

              {/* Warning note */}
              <div className="pm-del-warning-note">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                  <circle cx="12" cy="12" r="10"/>
                  <line x1="12" y1="8" x2="12" y2="12"/>
                  <line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                All diagnoses, prescriptions and reports linked to this patient will also be hidden.
              </div>

              {/* Error */}
              {deleteError && (
                <div className="alert alert-critical" style={{ marginTop: 12, fontSize: 12 }}>
                  <span className="alert-icon" style={{ fontSize: 14 }}>❌</span>
                  <div>{deleteError}</div>
                </div>
              )}
            </div>

            {/* Footer buttons */}
            <div className="pm-del-footer">
              <button
                type="button"
                className="pm-del-btn-cancel"
                onClick={() => setDeleteTarget(null)}
                disabled={deleteLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                className="pm-del-btn-confirm"
                onClick={confirmDelete}
                disabled={deleteLoading}
              >
                {deleteLoading ? (
                  <>
                    <span className="pm-del-spinner" />
                    Deleting…
                  </>
                ) : (
                  <>
                    <IconTrash /> Yes, Delete Patient
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── New Patient Modal ─────────────────────────────── */}
      {showModal && (
        <Modal
          title="New Patient Registration"
          size="modal-lg"
          onClose={() => { setShowModal(false); setForm(EMPTY); setApiError(''); }}
          footer={
            <>
              <button className="btn btn-secondary"
                onClick={() => { setShowModal(false); setForm(EMPTY); }}>
                Cancel
              </button>
              <button className="btn btn-primary"
                disabled={!form.first_name || !form.last_name || !form.date_of_birth}
                onClick={handleSave}>
                💾 Save to PostgreSQL
              </button>
            </>
          }
        >
          {apiError && (
            <div className="alert alert-critical mb-12">
              <span className="alert-icon">❌</span>
              <div>{apiError}</div>
            </div>
          )}
          <div className="form-row form-row-2">
            <div className="form-group">
              <label className="form-label">First Name *</label>
              <input className="form-input" value={form.first_name} onChange={f('first_name')} placeholder="First name" />
            </div>
            <div className="form-group">
              <label className="form-label">Last Name *</label>
              <input className="form-input" value={form.last_name} onChange={f('last_name')} placeholder="Last name" />
            </div>
          </div>
          <div className="form-row form-row-3">
            <div className="form-group">
              <label className="form-label">Date of Birth *</label>
              <input className="form-input" type="date" value={form.date_of_birth} onChange={f('date_of_birth')} />
            </div>
            <div className="form-group">
              <label className="form-label">Gender</label>
              <select className="form-select" value={form.gender} onChange={f('gender')}>
                <option>Female</option><option>Male</option><option>Other</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Blood Type</label>
              <select className="form-select" value={form.blood_type} onChange={f('blood_type')}>
                {['A+','A-','B+','B-','O+','O-','AB+','AB-'].map(b => <option key={b}>{b}</option>)}
              </select>
            </div>
          </div>
          <div className="form-row form-row-2">
            <div className="form-group">
              <label className="form-label">Weight (kg)</label>
              <input className="form-input" type="number" value={form.weight} onChange={f('weight')} placeholder="kg" />
            </div>
            <div className="form-group">
              <label className="form-label">Height (cm)</label>
              <input className="form-input" type="number" value={form.height} onChange={f('height')} placeholder="cm" />
            </div>
          </div>
          <div className="form-row form-row-2">
            <div className="form-group">
              <label className="form-label">Phone</label>
              <input className="form-input" value={form.phone} onChange={f('phone')} placeholder="05xxxxxxxx" />
            </div>
            <div className="form-group">
              <label className="form-label">Email</label>
              <input className="form-input" type="email" value={form.email} onChange={f('email')} placeholder="patient@email.com" />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Known Allergies (comma-separated)</label>
            <input className="form-input" value={form.allergies} onChange={f('allergies')} placeholder="Penicillin, Sulfa, NSAIDs…" />
          </div>
          <div className="form-group">
            <label className="form-label">Medical Conditions (comma-separated)</label>
            <textarea className="form-textarea" value={form.conditions} onChange={f('conditions')} placeholder="Type 2 Diabetes, Hypertension…" />
          </div>
        </Modal>
      )}
    </div>
  );
}
