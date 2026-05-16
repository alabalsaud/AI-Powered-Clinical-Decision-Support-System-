"""
app/agents/triage_agent.py — Agent 1: Triage

Rule-based (no LLM). Responsibilities:
- Extract normalised clinical feature keywords from free-text symptoms + notes
- Score urgency: critical / urgent / routine
- Normalise the allergy list into lowercase strings
- Populate PipelineContext with: triage_features, urgency, normalised_allergies
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.agents.base import BaseAgent, PipelineContext


# ─── Urgency keyword tables ───────────────────────────────────────────────────

_CRITICAL_KEYWORDS = [
    "chest pain", "crushing chest", "mi", "heart attack", "stemi", "nstemi",
    "stroke", "facial droop", "arm weakness", "sudden confusion",
    "respiratory failure", "cannot breathe", "unable to breathe", "apnea",
    "anaphylaxis", "anaphylactic", "severe allergy",
    "septic shock", "sepsis", "hypotension", "systolic <90",
    "loss of consciousness", "unresponsive", "cardiac arrest",
    "severe bleeding", "haemorrhage", "hemorrhage",
    "oxygen saturation <90", "spo2 <90",
    "gcs", "altered consciousness",
    "pulmonary embolism", "dvt", "acute abdomen",
    "meningitis", "severe headache + neck stiffness",
    "diabetic ketoacidosis", "dka",
    "eclampsia", "seizure", "status epilepticus",
]

_URGENT_KEYWORDS = [
    "high fever", "fever >39", "fever above 39", "persistent fever",
    "shortness of breath", "dyspnea", "difficulty breathing", "sob",
    "severe pain", "severe abdominal", "severe headache",
    "tachycardia", "heart rate >120", "palpitations",
    "vomiting blood", "haemoptysis", "hemoptysis", "blood in urine",
    "acute pain", "worsening", "rapid deterioration",
    "urinary retention", "acute kidney",
    "cellulitis", "spreading redness", "wound infection",
    "hypoglycaemia", "hypoglycemia", "blood sugar <60",
    "dehydration", "severe diarrhoea",
    "confusion", "disorientation",
]

# ─── Clinical feature extraction keywords ────────────────────────────────────
# Maps extracted feature tag → patterns to detect in text

_FEATURE_PATTERNS: Dict[str, List[str]] = {
    "fever":                ["fever", "pyrexia", "temperature", "febrile", "hot"],
    "cough":                ["cough", "coughing", "productive cough", "dry cough"],
    "sore_throat":          ["sore throat", "throat pain", "pharyngitis", "tonsil"],
    "runny_nose":           ["runny nose", "rhinorrhoea", "rhinorrhea", "nasal discharge", "nasal congestion"],
    "chest_pain":           ["chest pain", "chest tightness", "substernal", "angina", "palpitation"],
    "shortness_of_breath":  ["shortness of breath", "dyspnea", "difficulty breathing", "sob", "breathless"],
    "fatigue":              ["fatigue", "tiredness", "lethargy", "weakness", "malaise"],
    "headache":             ["headache", "cephalalgia", "migraine", "head pain"],
    "nausea_vomiting":      ["nausea", "vomiting", "emesis", "throwing up"],
    "diarrhoea":            ["diarrhoea", "diarrhea", "loose stools", "watery stool"],
    "abdominal_pain":       ["abdominal pain", "belly pain", "stomach pain", "epigastric", "cramping"],
    "dysuria":              ["dysuria", "painful urination", "burning urination", "frequency"],
    "joint_pain":           ["joint pain", "arthralgia", "arthritis", "swollen joint"],
    "rash":                 ["rash", "urticaria", "hives", "skin eruption", "pruritus", "itching"],
    "polyuria":             ["polyuria", "frequent urination", "excessive urination"],
    "polydipsia":           ["polydipsia", "excessive thirst", "increased thirst"],
    "oedema":               ["oedema", "edema", "swelling", "puffiness"],
    "confusion":            ["confusion", "disorientation", "altered mental", "delirium"],
    "syncope":              ["syncope", "fainting", "loss of consciousness", "blackout"],
    "hypertension":         ["hypertension", "high blood pressure", "bp elevated"],
    "tachycardia":          ["tachycardia", "rapid heart", "heart rate"],
    "diabetes_symptoms":    ["polyuria", "polydipsia", "glucose", "hba1c", "diabetic"],
    "productive_sputum":    ["sputum", "phlegm", "productive", "mucopurulent"],
    "wheezing":             ["wheeze", "wheezing", "whistling breath"],
    "nasal_congestion":     ["nasal congestion", "blocked nose", "stuffy nose"],
}

# ─── Allergy normalisation ────────────────────────────────────────────────────

_ALLERGY_ALIASES: Dict[str, str] = {
    "pcn": "penicillin", "pen": "penicillin",
    "asa": "aspirin", "acetylsalicylic acid": "aspirin",
    "sulfa": "sulfonamide", "sulphonamide": "sulfonamide",
    "nsaid": "nsaids", "non-steroidal": "nsaids",
    "cephalosporin": "cephalosporins",
    "macrolide": "macrolides",
    "fluoroquinolone": "fluoroquinolones",
    "codeine": "opioids",
    "morphine": "opioids",
}


def _normalise_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _extract_features(text: str) -> List[str]:
    t = _normalise_text(text)
    features: List[str] = []
    for tag, patterns in _FEATURE_PATTERNS.items():
        if any(p in t for p in patterns):
            features.append(tag)
    return features


def _score_urgency(text: str) -> str:
    t = _normalise_text(text)
    if any(kw in t for kw in _CRITICAL_KEYWORDS):
        return "critical"
    if any(kw in t for kw in _URGENT_KEYWORDS):
        return "urgent"
    return "routine"


def _normalise_allergy(raw: Any) -> str:
    if isinstance(raw, dict):
        val = raw.get("allergen") or raw.get("name") or raw.get("allergy") or ""
    else:
        val = str(raw or "")
    n = _normalise_text(val)
    return _ALLERGY_ALIASES.get(n, n)


class TriageAgent(BaseAgent):
    name = "TriageAgent"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        self.log("Starting triage…")

        # Combine all text sources for feature extraction
        combined = " ".join([
            str(ctx.get("symptoms") or ""),
            str(ctx.get("clinical_notes") or ""),
            " ".join(str(h) for h in (ctx.get("medical_history") or [])),
            " ".join(str(v) for v in (ctx.get("lab") or {}).values()),
            " ".join(str(v) for v in (ctx.get("vitals") or {}).values()),
        ])

        features = _extract_features(combined)
        urgency = _score_urgency(combined)
        norm_allergies = [
            _normalise_allergy(a)
            for a in (ctx.get("allergies_raw") or [])
            if a
        ]
        # Deduplicate
        norm_allergies = list(dict.fromkeys(norm_allergies))

        ctx["triage_features"] = features
        ctx["urgency"] = urgency
        ctx["normalised_allergies"] = norm_allergies

        self.log(
            f"urgency={urgency} features={features[:5]} allergies={norm_allergies}"
        )
        return ctx
