/**
 * cdssApi.js — Axios-based API client for AI-CDSS
 *
 * Base URL  : http://localhost:8000/api  (shorthand flat routes)
 * Auth      : JWT Bearer token (localStorage key: cdss_token)
 * Interceptors:
 *   - Request  → attach Authorization header when a token is present
 *   - Response → redirect to /login (clear token) on HTTP 401
 */

import axios from 'axios';

// ── Instance ─────────────────────────────────────────────────────────────────

const cdssApi = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 120_000,   // LLM calls on free-tier OpenRouter can take 30–90s
  headers: { 'Content-Type': 'application/json' },
});

// ── Request interceptor: inject Bearer token ──────────────────────────────────

cdssApi.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('cdss_token');
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (err) => Promise.reject(err),
);

// ── Response interceptor: handle 401 → logout ─────────────────────────────────

cdssApi.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('cdss_token');
      localStorage.removeItem('cdss_user');
      // Trigger a page reload so the React app re-renders the login screen.
      // This avoids a hard dependency on a router or global auth context.
      window.location.reload();
    }
    // Normalise the error message so callers can do err.message without digging into err.response
    const detail = err.response?.data?.detail;
    if (detail) {
      const msg =
        typeof detail === 'string'
          ? detail
          : typeof detail?.message === 'string'
            ? detail.message
            : JSON.stringify(detail);
      err.message = msg;
    }
    return Promise.reject(err);
  },
);

// ── Exported domain functions ─────────────────────────────────────────────────

/**
 * Authenticate and obtain a JWT.
 *
 * @param {string} email
 * @param {string} password
 * @returns {Promise<{access_token: string, user: object}>}
 */
export async function loginUser(email, password) {
  const { data } = await cdssApi.post(
    '/auth/login',
    { email, password },
    { headers: { Authorization: undefined } }, // login does not require a token
  );
  if (data.access_token) {
    localStorage.setItem('cdss_token', data.access_token);
  }
  if (data.user) {
    localStorage.setItem('cdss_user', JSON.stringify(data.user));
  }
  return data;
}

/**
 * Run AI differential diagnosis for a patient.
 *
 * @param {object} patientData
 *   {patient_id, patient_name, age, gender, conditions, allergies,
 *    symptoms, clinical_notes, lab: {glucose, hba1c, wbc, creatinine, troponin}}
 * @returns {Promise<{suggestions: Array<{rank,name,icd,confidence,evidence,factors}>}>}
 */
export async function diagnosePatient(patientData) {
  const { data } = await cdssApi.post('/diagnose', patientData);
  return data;
}

/**
 * Run drug-drug interaction + drug-allergy safety check.
 *
 * @param {string}   drug      — drug being prescribed
 * @param {string[]} meds      — current medications
 * @param {Array}    allergies — patient allergy list (each: {allergen, severity?, reaction?})
 * @returns {Promise<object>}  — {interactions: [], allergy_conflicts: [], overall: string}
 */
export async function checkDrugSafety(drug, meds = [], allergies = []) {
  const { data } = await cdssApi.post('/drug-check', {
    drug_name: drug,
    current_meds: meds,
    allergies,
  });
  return data;
}

/**
 * Generate a structured clinical session report (PDF + LLM summary).
 *
 * @param {object} sessionData
 *   {patient_demographics, presenting_complaints, ai_diagnosis_suggestions,
 *    xai_reasoning, treatment_plan, prescriptions, drug_safety_check_results}
 * @returns {Promise<{summary_text: string, pdf_path: string, model: string}>}
 */
export async function generateReport(sessionData) {
  const { data } = await cdssApi.post('/report', sessionData);
  return data;
}

/**
 * Evidence-based medication suggestions for a patient.
 *
 * @param {object} params
 *   {patient_id?, diagnoses?: string[], symptoms?: string,
 *    allergies?: string[], conditions?: string[]}
 * @returns {Promise<{suggestions: Array, matched_diagnoses: string[], warning: string, disclaimer: string}>}
 */
export async function suggestMedications(params) {
  const { data } = await cdssApi.post('/suggest-medications', params);
  return data;
}

/**
 * Run the full 5-agent clinical decision pipeline.
 *
 * @param {object} params
 *   {patient_id?, patient_name?, age?, gender?, symptoms (required),
 *    clinical_notes?, medical_history?, allergies?, current_meds?,
 *    vitals?, lab?}
 * @returns {Promise<PipelineResult>}
 *   {run_id, urgency, triage_features, llm_used, diagnosis_model,
 *    verified_diagnoses, verification_notes, medication_groups,
 *    total_safe_drugs, total_warned_drugs, total_blocked_drugs,
 *    qa_scores, overall_score, performance_grade, pipeline_steps}
 */
export async function runClinicalPipeline(params) {
  const { data } = await cdssApi.post('/clinical-pipeline', params);
  return data;
}

/**
 * Fetch pipeline performance history.
 *
 * @param {number} limit - max records to return (default 50)
 * @returns {Promise<{records: Array, total: number, average_score: number|null}>}
 */
export async function getPipelineMetrics(limit = 50) {
  const { data } = await cdssApi.get('/pipeline-metrics', { params: { limit } });
  return data;
}

export default cdssApi;
