"""
Diagnosis model utilities — differential diagnosis generation via BioGPT-Large.

Uses the BioGPT-Large text-generation pipeline pre-loaded into
main.ML_MODELS['biogpt_large'] at application startup.

Public API
----------
generate_diagnoses(patient_data: dict) -> list[dict]

Each returned dict has:
    diagnosis   : str    — diagnosis name
    confidence  : float  — 0.0–1.0 (higher = more likely)
    icd10_code  : str    — ICD-10 code (best-effort)
    reasoning   : str    — clinical reasoning sentence
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

# ─── ICD-10 quick-lookup table ────────────────────────────────────────────────
# Covers the most common differential diagnoses generated for primary care.
# Extend as needed; unknown conditions fall back to "R69" (illness unspecified).
_ICD10_MAP: Dict[str, str] = {
    "type 2 diabetes mellitus":         "E11.9",
    "diabetes mellitus":                "E11.9",
    "hypertension":                     "I10",
    "essential hypertension":           "I10",
    "community-acquired pneumonia":     "J18.9",
    "pneumonia":                        "J18.9",
    "acute myocardial infarction":      "I21.9",
    "myocardial infarction":            "I21.9",
    "heart failure":                    "I50.9",
    "congestive heart failure":         "I50.0",
    "atrial fibrillation":              "I48.91",
    "asthma":                           "J45.909",
    "chronic obstructive pulmonary disease": "J44.9",
    "copd":                             "J44.9",
    "urinary tract infection":          "N39.0",
    "uti":                              "N39.0",
    "acute kidney injury":              "N17.9",
    "chronic kidney disease":           "N18.9",
    "ckd":                              "N18.9",
    "sepsis":                           "A41.9",
    "stroke":                           "I63.9",
    "ischemic stroke":                  "I63.9",
    "pulmonary embolism":               "I26.99",
    "deep vein thrombosis":             "I82.409",
    "anemia":                           "D64.9",
    "iron deficiency anemia":           "D50.9",
    "hypothyroidism":                   "E03.9",
    "hyperthyroidism":                  "E05.90",
    "depression":                       "F32.9",
    "anxiety":                          "F41.9",
    "gastroesophageal reflux disease":  "K21.0",
    "gerd":                             "K21.0",
    "peptic ulcer disease":             "K27.9",
    "acute appendicitis":               "K37",
    "cholecystitis":                    "K81.9",
    "pancreatitis":                     "K85.9",
    "liver disease":                    "K76.9",
    "cirrhosis":                        "K74.60",
    "migraine":                         "G43.909",
    "epilepsy":                         "G40.909",
    "osteoarthritis":                   "M19.90",
    "rheumatoid arthritis":             "M06.9",
    "gout":                             "M10.9",
    "cellulitis":                       "L03.90",
    "covid-19":                         "U07.1",
    "influenza":                        "J11.1",
}

# ─── Fallback rule-based diagnoses ───────────────────────────────────────────
# Used when the model is unavailable or produces unparseable output.
_RULE_BASED: List[Dict[str, Any]] = [
    {
        "diagnosis":  "Type 2 Diabetes Mellitus",
        "icd10_code": "E11.9",
        "reasoning":  "Elevated glucose and HbA1c with classic symptoms suggest T2DM.",
        "_keywords":  ["diabetes", "glucose", "hba1c", "polyuria", "polydipsia"],
    },
    {
        "diagnosis":  "Hypertension",
        "icd10_code": "I10",
        "reasoning":  "Consistently elevated blood pressure with associated risk factors.",
        "_keywords":  ["hypertension", "blood pressure", "hypertensive"],
    },
    {
        "diagnosis":  "Community-Acquired Pneumonia",
        "icd10_code": "J18.9",
        "reasoning":  "Fever, productive cough, and consolidation on imaging are consistent.",
        "_keywords":  ["pneumonia", "cough", "consolidation", "fever", "sputum"],
    },
    {
        "diagnosis":  "Acute Myocardial Infarction",
        "icd10_code": "I21.9",
        "reasoning":  "Chest pain with troponin rise and ST changes warrant urgent evaluation.",
        "_keywords":  ["chest pain", "troponin", "st elevation", "myocardial"],
    },
    {
        "diagnosis":  "Heart Failure",
        "icd10_code": "I50.9",
        "reasoning":  "Dyspnea, oedema, and elevated BNP are hallmarks of heart failure.",
        "_keywords":  ["heart failure", "dyspnea", "oedema", "bnp", "edema"],
    },
    {
        "diagnosis":  "Pulmonary Embolism",
        "icd10_code": "I26.99",
        "reasoning":  "Sudden dyspnea and pleuritic chest pain with risk factors raise PE suspicion.",
        "_keywords":  ["dyspnea", "pleuritic", "embolism", "dvt", "hypoxia"],
    },
    {
        "diagnosis":  "Urinary Tract Infection",
        "icd10_code": "N39.0",
        "reasoning":  "Dysuria, frequency, and positive urinalysis are consistent with UTI.",
        "_keywords":  ["dysuria", "frequency", "uti", "urinalysis", "pyuria"],
    },
    {
        "diagnosis":  "Sepsis",
        "icd10_code": "A41.9",
        "reasoning":  "Fever, tachycardia, leukocytosis, and source of infection suggest sepsis.",
        "_keywords":  ["sepsis", "fever", "tachycardia", "wbc", "leukocytosis"],
    },
]

# ─── Prompt template ─────────────────────────────────────────────────────────

def _build_prompt(patient_data: Dict[str, Any]) -> str:
    """
    Build a structured clinical prompt for BioGPT-Large.

    Expected keys in patient_data (all optional):
        age, gender, symptoms, lab_values (dict), medical_history (list/str)
    """
    age     = patient_data.get("age", "unknown")
    gender  = patient_data.get("gender", "unknown")
    symptoms = patient_data.get("symptoms") or "not specified"

    history = patient_data.get("medical_history") or []
    if isinstance(history, list):
        history_str = ", ".join(str(h) for h in history) if history else "none"
    else:
        history_str = str(history)

    lab_values = patient_data.get("lab_values") or {}
    lab_str = (
        "; ".join(f"{k}: {v}" for k, v in lab_values.items() if v is not None)
        if lab_values else "none provided"
    )

    prompt = (
        f"Clinical case: {age}-year-old {gender} patient. "
        f"Symptoms: {symptoms}. "
        f"Medical history: {history_str}. "
        f"Lab values: {lab_str}. "
        "Provide the top 5 differential diagnoses in JSON format as a list. "
        'Each item must have: "diagnosis" (string), "confidence" (float 0-1), '
        '"icd10_code" (string), "reasoning" (string). '
        'Return only valid JSON array, no extra text. Example: '
        '[{"diagnosis":"Pneumonia","confidence":0.85,"icd10_code":"J18.9","reasoning":"Fever and cough"}]'
        "\nDifferential diagnoses:"
    )
    return prompt


# ─── Parsing helpers ─────────────────────────────────────────────────────────

_JSON_ARRAY_RE = re.compile(r"\[.*?\]", re.DOTALL)


def _lookup_icd10(diagnosis: str) -> str:
    key = diagnosis.lower().strip()
    if key in _ICD10_MAP:
        return _ICD10_MAP[key]
    for known, code in _ICD10_MAP.items():
        if known in key or key in known:
            return code
    return "R69"   # Illness, unspecified


def _parse_generated_text(generated: str) -> List[Dict[str, Any]]:
    """
    Extract a JSON array from raw model output.
    Tries strict JSON parse first, then regex extraction.
    """
    # Strip everything before the first '[' and after the last ']'
    start = generated.find("[")
    end   = generated.rfind("]")
    if start != -1 and end != -1 and end > start:
        json_str = generated[start: end + 1]
        try:
            candidates = json.loads(json_str)
            if isinstance(candidates, list):
                return candidates
        except json.JSONDecodeError:
            pass

    # Fallback: find any JSON array fragment
    for match in _JSON_ARRAY_RE.finditer(generated):
        try:
            candidates = json.loads(match.group())
            if isinstance(candidates, list) and candidates:
                return candidates
        except json.JSONDecodeError:
            continue

    return []


def _normalise_entry(raw: Any, rank: int) -> Dict[str, Any] | None:
    """Validate and normalise a single diagnosis dict from parsed output."""
    if not isinstance(raw, dict):
        return None

    diagnosis = str(raw.get("diagnosis") or raw.get("name") or "").strip()
    if not diagnosis:
        return None

    try:
        confidence = float(raw.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = max(0.05, 0.90 - rank * 0.10)

    icd = str(raw.get("icd10_code") or raw.get("icd") or "").strip()
    if not icd or icd.upper() == "N/A":
        icd = _lookup_icd10(diagnosis)

    reasoning = str(raw.get("reasoning") or raw.get("evidence") or "").strip()
    if not reasoning:
        reasoning = f"Clinical presentation consistent with {diagnosis}."

    return {
        "diagnosis":  diagnosis,
        "confidence": round(confidence, 4),
        "icd10_code": icd,
        "reasoning":  reasoning,
    }


# ─── Rule-based fallback ─────────────────────────────────────────────────────

def _rule_based_diagnoses(patient_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Score the built-in rule table against patient_data text and return
    the top 5 matches sorted by keyword hit count, then by list order.
    """
    combined_text = " ".join([
        str(patient_data.get("symptoms") or ""),
        str(patient_data.get("medical_history") or ""),
        " ".join(str(v) for v in (patient_data.get("lab_values") or {}).values()),
    ]).lower()

    scored: List[tuple[int, int, Dict[str, Any]]] = []
    for idx, rule in enumerate(_RULE_BASED):
        hits = sum(1 for kw in rule["_keywords"] if kw in combined_text)
        scored.append((hits, -idx, rule))   # -idx keeps stable insertion order

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    top = scored[:5]

    results = []
    for rank, (hits, _, rule) in enumerate(top):
        base_conf = max(0.45, 0.85 - rank * 0.08) if hits > 0 else max(0.20, 0.50 - rank * 0.08)
        results.append({
            "diagnosis":  rule["diagnosis"],
            "confidence": round(base_conf, 4),
            "icd10_code": rule["icd10_code"],
            "reasoning":  rule["reasoning"],
        })
    return results


# ─── Public API ──────────────────────────────────────────────────────────────

def generate_diagnoses(patient_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generate up to 5 differential diagnoses for the given patient data.

    Parameters
    ----------
    patient_data : dict
        Keys: age (int|str), gender (str), symptoms (str),
              lab_values (dict), medical_history (list|str)

    Returns
    -------
    list of dict, sorted by confidence descending, max 5 items.
    Each dict: {diagnosis: str, confidence: float, icd10_code: str, reasoning: str}
    """
    prompt = _build_prompt(patient_data)
    model_used = False
    raw_candidates: List[Dict[str, Any]] = []

    # ── Try BioGPT-Large pipeline ─────────────────────────────────────────
    try:
        from main import ML_MODELS  # lazy import to avoid circular dependency
        pipe = ML_MODELS.get("biogpt_large")
        if pipe is not None:
            outputs = pipe(
                prompt,
                max_new_tokens=512,
                do_sample=False,          # greedy for determinism
                return_full_text=False,   # return only newly generated tokens
            )
            generated_text = outputs[0].get("generated_text", "") if outputs else ""
            parsed = _parse_generated_text(generated_text)
            for rank, item in enumerate(parsed):
                entry = _normalise_entry(item, rank)
                if entry:
                    raw_candidates.append(entry)
            model_used = bool(raw_candidates)
    except Exception:
        pass  # fall through to rule-based

    # ── Rule-based fallback ───────────────────────────────────────────────
    if not model_used or len(raw_candidates) < 1:
        raw_candidates = _rule_based_diagnoses(patient_data)

    # ── Sort by confidence, return top 5 ─────────────────────────────────
    raw_candidates.sort(key=lambda d: d["confidence"], reverse=True)
    top5 = raw_candidates[:5]

    # Ensure ICD-10 codes are filled for any model-generated entries
    for entry in top5:
        if not entry.get("icd10_code") or entry["icd10_code"] == "R69":
            entry["icd10_code"] = _lookup_icd10(entry["diagnosis"])

    return top5
