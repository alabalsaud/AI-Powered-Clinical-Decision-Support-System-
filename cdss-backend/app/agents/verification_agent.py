"""
app/agents/verification_agent.py — Agent 3: Verification

Rule-based (no LLM). Responsibilities:
- Compute symptom_match_score for each raw diagnosis
- Validate ICD-10 code format
- Adjust final confidence: (llm_confidence * 0.70) + (symptom_match_score * 0.30)
- Filter diagnoses below MIN_CONFIDENCE threshold
- Generate human-readable verification notes

Adds to PipelineContext:
  verified_diagnoses  : list (sorted by final_confidence desc)
  verification_notes  : list[str]
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from app.agents.base import BaseAgent, PipelineContext

# Minimum confidence to keep a diagnosis in the verified set
MIN_CONFIDENCE = 15   # percent

# ICD-10 format: letter + 2 digits, optionally .digit(s)
_ICD10_RE = re.compile(r"^[A-Z]\d{2}(\.\d{1,4})?$", re.IGNORECASE)

# ─── Diagnosis → expected symptom keyword map ────────────────────────────────
# For each condition we list keywords that should appear in triage_features or
# symptom text to validate the diagnosis.

_DX_EVIDENCE_MAP: Dict[str, List[str]] = {
    # Infections
    "viral upper respiratory":   ["fever", "cough", "runny_nose", "sore_throat", "nasal_congestion"],
    "common cold":               ["runny_nose", "cough", "sore_throat"],
    "influenza":                 ["fever", "cough", "fatigue", "headache"],
    "bacterial sinusitis":       ["nasal_congestion", "headache", "fever", "runny_nose"],
    "community-acquired pneumonia": ["cough", "fever", "shortness_of_breath", "productive_sputum"],
    "pneumonia":                 ["cough", "fever", "shortness_of_breath"],
    "atypical pneumonia":        ["cough", "fever", "fatigue"],
    "covid-19":                  ["fever", "cough", "fatigue", "shortness_of_breath"],
    "urinary tract infection":   ["dysuria", "fever"],
    "sepsis":                    ["fever", "tachycardia", "confusion"],
    "strep pharyngitis":         ["sore_throat", "fever"],
    "pharyngitis":               ["sore_throat", "fever"],
    "otitis media":              ["fever", "headache"],
    # Cardiac / Vascular
    "acute myocardial infarction": ["chest_pain", "shortness_of_breath"],
    "myocardial infarction":     ["chest_pain"],
    "heart failure":             ["shortness_of_breath", "oedema", "fatigue"],
    "congestive heart failure":  ["shortness_of_breath", "oedema"],
    "angina":                    ["chest_pain", "shortness_of_breath"],
    "pulmonary embolism":        ["shortness_of_breath", "chest_pain"],
    "hypertension":              ["hypertension", "headache"],
    "atrial fibrillation":       ["tachycardia", "palpitations"],
    # Metabolic
    "type 2 diabetes":           ["fatigue", "polyuria", "polydipsia", "diabetes_symptoms"],
    "diabetes mellitus":         ["fatigue", "polyuria", "polydipsia"],
    "diabetic ketoacidosis":     ["nausea_vomiting", "fatigue", "diabetes_symptoms"],
    "metabolic syndrome":        ["fatigue", "hypertension", "diabetes_symptoms"],
    "hypothyroidism":            ["fatigue", "oedema"],
    "hyperthyroidism":           ["tachycardia", "fatigue"],
    # Respiratory
    "asthma":                    ["wheezing", "shortness_of_breath", "cough"],
    "copd":                      ["shortness_of_breath", "cough", "wheezing"],
    "bronchitis":                ["cough", "fever", "fatigue"],
    # GI
    "gastroenteritis":           ["nausea_vomiting", "diarrhoea", "abdominal_pain"],
    "gerd":                      ["abdominal_pain", "nausea_vomiting"],
    "peptic ulcer":              ["abdominal_pain", "nausea_vomiting"],
    "appendicitis":              ["abdominal_pain", "fever", "nausea_vomiting"],
    # Renal
    "chronic kidney disease":    ["oedema", "fatigue"],
    "acute kidney injury":       ["oedema", "fatigue"],
    # Haematological
    "anaemia":                   ["fatigue"],
    "iron deficiency anaemia":   ["fatigue"],
    # Musculoskeletal / Other
    "gout":                      ["joint_pain", "fever"],
    "rheumatoid arthritis":      ["joint_pain", "fatigue"],
    "cellulitis":                ["rash", "fever"],
    "migraine":                  ["headache", "nausea_vomiting"],
    "meningitis":                ["fever", "headache", "confusion"],
    "allergic rhinitis":         ["runny_nose", "nasal_congestion", "rash"],
}


def _symptom_match_score(
    dx_name: str,
    triage_features: List[str],
    symptom_text: str,
) -> float:
    """
    Return 0-100 score indicating how well the diagnosis matches presented features.
    """
    dx_lower = dx_name.lower()

    # Find the best matching rule in _DX_EVIDENCE_MAP
    expected: List[str] = []
    best_overlap = 0
    for key, kw_list in _DX_EVIDENCE_MAP.items():
        if key in dx_lower or dx_lower in key:
            overlap = sum(1 for kw in kw_list if kw in triage_features)
            if overlap > best_overlap:
                best_overlap = overlap
                expected = kw_list

    if not expected:
        # Unknown diagnosis — give a neutral 50
        return 50.0

    if not triage_features:
        return 30.0

    matched = sum(1 for kw in expected if kw in triage_features)
    return round(min(100.0, (matched / len(expected)) * 100), 1)


def _validate_icd10(code: str) -> bool:
    return bool(_ICD10_RE.match((code or "").strip()))


class VerificationAgent(BaseAgent):
    name = "VerificationAgent"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        self.log("Verifying diagnoses…")

        raw: List[Dict[str, Any]] = ctx.get("raw_diagnoses") or []
        triage_features: List[str] = ctx.get("triage_features") or []
        symptom_text = str(ctx.get("symptoms") or "").lower()
        notes: List[str] = []

        verified: List[Dict[str, Any]] = []

        for dx in raw:
            name       = dx.get("name", "")
            llm_conf   = min(100, max(0, int(dx.get("confidence") or 50)))
            icd        = str(dx.get("icd") or "R69")
            evidence   = dx.get("evidence", "")
            factors    = dx.get("factors") or []

            # Symptom match score
            sym_score = _symptom_match_score(name, triage_features, symptom_text)

            # Final blended confidence
            final_conf = round(llm_conf * 0.70 + sym_score * 0.30)

            # ICD validity
            icd_valid = _validate_icd10(icd)
            if not icd_valid:
                notes.append(f"{name}: ICD-10 code '{icd}' invalid format — marked R69.")
                icd = "R69"

            # Threshold filter
            if final_conf < MIN_CONFIDENCE:
                notes.append(f"{name}: dropped (final confidence {final_conf}% < {MIN_CONFIDENCE}%)")
                continue

            # Add verification metadata to the entry
            verified.append({
                **dx,
                "icd":                  icd,
                "icd_valid":            icd_valid,
                "llm_confidence":       llm_conf,
                "symptom_match_score":  sym_score,
                "confidence":           final_conf,  # overwrite with blended
                "evidence":             evidence,
                "factors":              factors,
            })

        # Sort by final confidence descending
        verified.sort(key=lambda d: d["confidence"], reverse=True)

        # Re-rank
        for i, d in enumerate(verified):
            d["rank"] = i + 1

        if not verified and raw:
            notes.append("All diagnoses filtered below threshold — returning unverified list.")
            verified = raw[:3]

        self.log(f"Verified {len(verified)}/{len(raw)} diagnoses. Notes: {len(notes)}")

        ctx["verified_diagnoses"] = verified
        ctx["verification_notes"] = notes
        return ctx
