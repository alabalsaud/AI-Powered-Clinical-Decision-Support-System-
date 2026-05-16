/**
 * Client-side patient filter: full display name, MRN, numeric id, optional conditions.
 */
function displayName(p) {
  return (p?.full_name || `${p?.first_name || ''} ${p?.last_name || ''}`).trim();
}

function conditionStrings(p) {
  if (Array.isArray(p?.medical_histories)) {
    return p.medical_histories.map((h) => String(h?.condition || '').toLowerCase());
  }
  if (Array.isArray(p?.conditions)) {
    return p.conditions.map((c) =>
      typeof c === 'string' ? c.toLowerCase() : String(c?.condition || '').toLowerCase()
    );
  }
  return [];
}

/**
 * @param {object} p - patient row from API or mock
 * @param {string} raw - search text
 * @param {{ includeConditions?: boolean }} opts
 */
export function patientMatchesSearch(p, raw, opts = {}) {
  const { includeConditions = false } = opts;
  const q = String(raw || '').trim().toLowerCase();
  if (!q) return true;

  const name = displayName(p).toLowerCase();
  const mrn = String(p?.mrn || '').toLowerCase();
  const idStr = String(p?.id ?? '');

  if (name.includes(q) || mrn.includes(q)) return true;
  if (idStr.includes(q)) return true;

  const compact = (s) => s.replace(/[\s_-]/g, '');
  const mComp = compact(mrn);
  const qComp = compact(q);
  if (mComp && qComp && mComp.includes(qComp)) return true;

  if (includeConditions && conditionStrings(p).some((c) => c.includes(q))) return true;

  return false;
}
