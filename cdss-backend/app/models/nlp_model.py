"""
NLP model utilities — clinical named-entity recognition.

Uses the Bio_ClinicalBERT NER pipeline that is pre-loaded into
main.ML_MODELS['bio_clinical_bert'] at application startup.

Supported entity categories returned by extract_medical_entities():
    SYMPTOM       — patient-reported or observed symptom
    CONDITION     — diagnosed disease / medical problem
    MEDICATION    — drug, vaccine, or supplement name
    LAB_VALUE     — laboratory result or numeric measurement
    OBSERVATION   — clinical finding / physical examination finding
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ─── Entity-label mapping ─────────────────────────────────────────────────────
# Bio_ClinicalBERT (and common i2b2 / clinical NER fine-tunes) may produce
# labels in several formats.  This table normalises them to our five categories.
_LABEL_MAP: Dict[str, str] = {
    # i2b2 / n2c2 schema
    "problem":      "CONDITION",
    "treatment":    "MEDICATION",
    "test":         "LAB_VALUE",
    # Generic BERT NER schemas
    "disease":      "CONDITION",
    "disorder":     "CONDITION",
    "symptom":      "SYMPTOM",
    "sign":         "SYMPTOM",
    "finding":      "OBSERVATION",
    "observation":  "OBSERVATION",
    "drug":         "MEDICATION",
    "medication":   "MEDICATION",
    "chemical":     "MEDICATION",
    "lab":          "LAB_VALUE",
    "lab_value":    "LAB_VALUE",
    "labvalue":     "LAB_VALUE",
    "value":        "LAB_VALUE",
    "anatomy":      "OBSERVATION",
    "body_part":    "OBSERVATION",
    "procedure":    "OBSERVATION",
    "misc":         "OBSERVATION",
}

# Ordered patterns used as keyword fallback when the model produces an
# unmapped label or when the pipeline is unavailable.
_KEYWORD_PATTERNS: List[tuple[re.Pattern, str]] = [
    (re.compile(
        r"\b(fever|pain|cough|dyspnea|fatigue|nausea|vomiting|dizziness|"
        r"headache|chills|sweating|shortness of breath|chest pain|"
        r"palpitations|syncope|edema|swelling|rash|pruritus|diarrhea|"
        r"constipation|anorexia|malaise|weakness|myalgia|arthralgia)\b",
        re.I,
    ), "SYMPTOM"),
    (re.compile(
        r"\b(diabetes|hypertension|pneumonia|asthma|copd|heart failure|"
        r"myocardial infarction|stroke|sepsis|infection|cancer|tumor|"
        r"depression|anxiety|ckd|renal failure|liver disease|"
        r"atrial fibrillation|hypothyroidism|hyperthyroidism)\b",
        re.I,
    ), "CONDITION"),
    (re.compile(
        r"\b(metformin|lisinopril|atorvastatin|aspirin|warfarin|insulin|"
        r"amoxicillin|azithromycin|omeprazole|amlodipine|metoprolol|"
        r"furosemide|levothyroxine|prednisone|ibuprofen|acetaminophen|"
        r"ciprofloxacin|clopidogrel|digoxin|salbutamol)\b",
        re.I,
    ), "MEDICATION"),
    (re.compile(
        r"\b(glucose|hba1c|creatinine|hemoglobin|wbc|rbc|platelet|"
        r"sodium|potassium|bilirubin|alt|ast|tsh|bnp|troponin|"
        r"cholesterol|ldl|hdl|triglyceride|inr|pt|aptt|"
        r"\d+(\.\d+)?\s*(mg|mmol|µmol|g|%|units?|iu|meq|mmhg))\b",
        re.I,
    ), "LAB_VALUE"),
    (re.compile(
        r"\b(tachycardia|bradycardia|hypertensive|hypotensive|"
        r"murmur|crepitations|wheeze|consolidation|effusion|"
        r"hepatomegaly|splenomegaly|lymphadenopathy|jaundice|"
        r"pallor|cyanosis|clubbing|oedema|tenderness)\b",
        re.I,
    ), "OBSERVATION"),
]

# Categories we accept in output
_VALID_CATEGORIES = frozenset({"SYMPTOM", "CONDITION", "MEDICATION", "LAB_VALUE", "OBSERVATION"})


def _map_label(raw_label: str) -> Optional[str]:
    """Map a raw model entity label to one of our five categories."""
    clean = raw_label.lower().lstrip("b-").lstrip("i-")
    return _LABEL_MAP.get(clean)


def _keyword_entities(text: str) -> List[Dict[str, Any]]:
    """Regex keyword fallback — always returns something for well-known terms."""
    found: List[Dict[str, Any]] = []
    for pattern, category in _KEYWORD_PATTERNS:
        for m in pattern.finditer(text):
            found.append({
                "text":     m.group(0),
                "category": category,
                "score":    0.70,
                "start":    m.start(),
                "end":      m.end(),
                "source":   "keyword",
            })
    return found


def _deduplicate(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate spans, preferring higher-score entries."""
    seen: Dict[tuple, Dict[str, Any]] = {}
    for ent in entities:
        key = (ent["text"].lower(), ent["category"])
        if key not in seen or ent["score"] > seen[key]["score"]:
            seen[key] = ent
    return sorted(seen.values(), key=lambda e: e["start"])


def extract_medical_entities(text: str) -> Dict[str, Any]:
    """
    Extract clinical named entities from *text* using Bio_ClinicalBERT.

    Tries the globally loaded NER pipeline first; falls back to keyword
    matching if the model is not yet loaded or raises an exception.

    Returns
    -------
    {
        "entities": [
            {
                "text":     str,      # matched span
                "category": str,      # SYMPTOM | CONDITION | MEDICATION |
                                      # LAB_VALUE | OBSERVATION
                "score":    float,    # confidence 0-1
                "start":    int,      # char offset in original text
                "end":      int,
                "source":   str,      # "model" | "keyword"
            },
            ...
        ],
        "summary": {
            "SYMPTOM":     [...],
            "CONDITION":   [...],
            "MEDICATION":  [...],
            "LAB_VALUE":   [...],
            "OBSERVATION": [...],
        },
        "model_used": bool,
    }
    """
    if not text or not text.strip():
        return {
            "entities": [],
            "summary":  {c: [] for c in _VALID_CATEGORIES},
            "model_used": False,
        }

    model_used = False
    raw_entities: List[Dict[str, Any]] = []

    # ── Try the live NER pipeline ──────────────────────────────────────────
    try:
        from main import ML_MODELS  # imported lazily to avoid circular deps
        pipe = ML_MODELS.get("bio_clinical_bert")
        if pipe is not None:
            results = pipe(text)           # list of dicts with word, entity_group, score, start, end
            for r in results:
                label = r.get("entity_group") or r.get("entity") or ""
                category = _map_label(label)
                if category is None:
                    continue
                raw_entities.append({
                    "text":     r.get("word", "").strip(),
                    "category": category,
                    "score":    round(float(r.get("score", 0.0)), 4),
                    "start":    r.get("start", 0),
                    "end":      r.get("end", 0),
                    "source":   "model",
                })
            model_used = True
    except Exception:
        pass  # fall through to keyword fallback

    # ── Keyword fallback (always runs; fills gaps) ─────────────────────────
    keyword_hits = _keyword_entities(text)
    if not model_used:
        raw_entities = keyword_hits
    else:
        # Supplement model output: add keyword hits for spans not covered
        model_spans = {(e["start"], e["end"]) for e in raw_entities}
        for kw in keyword_hits:
            overlap = any(
                kw["start"] < end and kw["end"] > start
                for start, end in model_spans
            )
            if not overlap:
                raw_entities.append(kw)

    entities = _deduplicate(raw_entities)

    # ── Build summary grouped by category ─────────────────────────────────
    summary: Dict[str, List[str]] = {c: [] for c in _VALID_CATEGORIES}
    for ent in entities:
        cat = ent["category"]
        if cat in summary and ent["text"] not in summary[cat]:
            summary[cat].append(ent["text"])

    return {
        "entities":   entities,
        "summary":    summary,
        "model_used": model_used,
    }
