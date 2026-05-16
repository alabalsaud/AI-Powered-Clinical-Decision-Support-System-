/**
 * api.js — Centralised API client
 * All calls to the FastAPI backend go through here.
 * Base URL: http://localhost:8000/api/v1
 */

const BASE = 'http://localhost:8000/api/v1';

/** FastAPI may return detail as string, {message}, or Pydantic 422 array */
function formatApiDetail(detail) {
  if (detail == null) return 'Request failed';
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'object' && detail !== null && !Array.isArray(detail)) {
    let base = '';
    if (typeof detail.message === 'string') base = detail.message;
    else if (typeof detail.msg === 'string') base = detail.msg;
    if (base && typeof detail.hint === 'string') return `${base} — ${detail.hint}`;
    if (base) return base;
    if (typeof detail.provider_message === 'string' && detail.provider_message) {
      const head = typeof detail.message === 'string' ? detail.message : 'LLM provider error';
      let out = `${head}: ${detail.provider_message.slice(0, 280)}`;
      if (typeof detail.hint === 'string') out += ` — ${detail.hint}`;
      return out;
    }
  }
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => {
      if (typeof d === 'string') return d;
      const loc = Array.isArray(d.loc) ? d.loc.filter(Boolean).join(' › ') : '';
      const m = d.msg || d.message || JSON.stringify(d);
      return loc ? `${loc}: ${m}` : m;
    });
    return parts.join(' ');
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return 'Request failed';
  }
}

// ─── Token storage ────────────────────────────────────────
export function getToken()        { return localStorage.getItem('cdss_token'); }
export function setToken(t)       { localStorage.setItem('cdss_token', t); }
export function clearToken()      { localStorage.removeItem('cdss_token'); localStorage.removeItem('cdss_user'); }
export function getStoredUser()   {
  try { return JSON.parse(localStorage.getItem('cdss_user')); } catch { return null; }
}
export function storeUser(u)      { localStorage.setItem('cdss_user', JSON.stringify(u)); }

// ─── Session-expired event ────────────────────────────────
// Dispatched when any authenticated request returns 401.
// App.jsx listens and redirects to login.
export function onSessionExpired(callback) {
  window.addEventListener('cdss:session-expired', callback);
  return () => window.removeEventListener('cdss:session-expired', callback);
}
function _dispatchSessionExpired() {
  clearToken();
  window.dispatchEvent(new CustomEvent('cdss:session-expired'));
}

// ─── Core fetch wrapper ───────────────────────────────────
async function request(method, path, body = null, requiresAuth = true) {
  const headers = { 'Content-Type': 'application/json' };
  if (requiresAuth) {
    const token = getToken();
    if (!token) {
      _dispatchSessionExpired();
      throw new Error('Not authenticated');
    }
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return null; // No content

  // 401 = token expired or invalid → force re-login
  if (res.status === 401 && requiresAuth) {
    _dispatchSessionExpired();
    const err = new Error('Your session has expired. Please log in again.');
    err.status = 401;
    throw err;
  }

  const data = await res.json();

  if (!res.ok) {
    const msg = formatApiDetail(data?.detail);
    const err = new Error(msg);
    err.status = res.status;
    err.detail = data?.detail;
    throw err;
  }

  return data;
}

const get    = (path)          => request('GET',    path);
const post   = (path, body)    => request('POST',   path, body);
const put    = (path, body)    => request('PUT',    path, body);
const patch  = (path, body)    => request('PATCH',  path, body);
const del    = (path)          => request('DELETE', path);

// ─── AUTH ─────────────────────────────────────────────────
export const auth = {
  async login(email, password) {
    const data = await request('POST', '/auth/login', { email, password }, false);
    setToken(data.access_token);
    storeUser(data.user);
    return data;
  },

  async register(payload) {
    const data = await request('POST', '/auth/register', payload, false);
    return data;
  },

  async logout() {
    try { await post('/auth/logout'); } catch {}
    clearToken();
  },

  async me() {
    return get('/auth/me');
  },
};

// ─── PATIENTS ─────────────────────────────────────────────
export const patients = {
  list(search = '') {
    const t = typeof search === 'string' ? search.trim() : '';
    const qs = t ? `?search=${encodeURIComponent(t)}` : '';
    return get(`/patients/${qs}`);
  },
  get(id)                    { return get(`/patients/${id}`); },
  create(payload)            { return post('/patients/', payload); },
  update(id, payload)        { return put(`/patients/${id}`, payload); },
  deactivate(id)             { return del(`/patients/${id}`); },
  addAllergy(id, payload)    { return post(`/patients/${id}/allergies`, payload); },
  addCondition(id, payload)  { return post(`/patients/${id}/conditions`, payload); },
};

// ─── DIAGNOSES ────────────────────────────────────────────
export const diagnoses = {
  forPatient(patientId)      { return get(`/diagnoses/patient/${patientId}`); },
  get(id)                    { return get(`/diagnoses/${id}`); },
  create(payload)            { return post('/diagnoses/', payload); },
  confirm(id)                { return put(`/diagnoses/${id}/confirm`); },
  llmStatus()                { return get('/diagnoses/llm-status'); },
  llmSuggest(payload)        { return post('/diagnoses/llm-suggest', payload); },
};

// ─── PRESCRIPTIONS ────────────────────────────────────────
export const prescriptions = {
  forPatient(patientId)      { return get(`/prescriptions/patient/${patientId}`); },
  get(id)                    { return get(`/prescriptions/${id}`); },
  safetyCheck(payload)       { return post('/prescriptions/safety-check', payload); },
  create(payload)            { return post('/prescriptions/', payload); },
  cancel(id)                 { return patch(`/prescriptions/${id}/cancel`); },
};

// ─── TREATMENTS ───────────────────────────────────────────
export const treatments = {
  forPatient(patientId)      { return get(`/treatments/patient/${patientId}`); },
  get(id)                    { return get(`/treatments/${id}`); },
  create(payload)            { return post('/treatments/', payload); },
};

// ─── AUDIT (admin only) ───────────────────────────────────
export const auditLogs = {
  list(params = {}) {
    const sp = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v).trim() !== '') sp.append(k, String(v));
    });
    const s = sp.toString();
    return get(s ? `/audit/?${s}` : '/audit/');
  },
};

// ─── ADMIN ────────────────────────────────────────────────
export const adminUsers = {
  list(params = {}) {
    const sp = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v).trim() !== '') sp.append(k, String(v));
    });
    const s = sp.toString();
    return get(s ? `/admin/users?${s}` : '/admin/users');
  },
  deactivate(userId) {
    return del(`/admin/users/${userId}`);
  },
};

// ─── HEALTH ───────────────────────────────────────────────
export async function checkHealth() {
  try {
    const res = await fetch('http://localhost:8000/health');
    return res.ok;
  } catch {
    return false;
  }
}
