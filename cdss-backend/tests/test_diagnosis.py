"""
test_diagnosis.py — unit tests for app/models/diagnosis_model.py.

Coverage targets
----------------
* generate_diagnoses() on 20 varied clinical cases → >80 % top-5 accuracy
  (expected diagnosis must appear somewhere in the 5 returned entries).
* Rule-based fallback path (ML_MODELS empty).
* BioGPT model pipeline path (mock).
* _parse_generated_text, _normalise_entry, _lookup_icd10 internals.
* Edge cases: empty input, minimal keys, all-None labs, confidence clamping.

Run:
    cd cdss-backend && source venv/bin/activate
    pytest tests/test_diagnosis.py -v
"""
from __future__ import annotations

import json
import sys
import types
import unittest
from unittest.mock import MagicMock

# ── stub main.ML_MODELS ──────────────────────────────────────────────────────
_main_stub = types.ModuleType("main")
_main_stub.ML_MODELS = {}
sys.modules.setdefault("main", _main_stub)

from app.models.diagnosis_model import (  # noqa: E402
    _lookup_icd10,
    _normalise_entry,
    _parse_generated_text,
    generate_diagnoses,
)


# ── 20 labelled clinical cases ────────────────────────────────────────────────
# Cases are chosen so that their keywords trigger the rule-based fallback.
# The rule-based model covers: diabetes, hypertension, pneumonia, myocardial
# infarction, heart failure, pulmonary embolism, UTI, and sepsis.
# A case is "correct" if any diagnosis name (lower-cased) contains at least
# one accepted label from the set.

_CASES = [
    # 1 — T2DM: explicit diabetes keywords
    (
        {
            "age": 52, "gender": "male",
            "symptoms": "polyuria, polydipsia, blurred vision, fatigue",
            "lab_values": {"HbA1c": "9.5%", "fasting glucose": "13.2 mmol/L"},
        },
        {"diabetes"},
    ),
    # 2 — T2DM: HbA1c + glucose
    (
        {
            "age": 61, "gender": "female",
            "symptoms": "fatigue, increased thirst, frequent urination",
            "lab_values": {"glucose": "11.0 mmol/L", "HbA1c": "8.1%"},
        },
        {"diabetes"},
    ),
    # 3 — T2DM: polydipsia keyword
    (
        {
            "age": 47, "gender": "male",
            "symptoms": "polyuria and polydipsia, nocturia",
            "medical_history": ["obesity"],
        },
        {"diabetes"},
    ),
    # 4 — Hypertension: blood pressure keyword
    (
        {
            "age": 60, "gender": "female",
            "symptoms": "headache, dizziness",
            "lab_values": {"blood pressure": "178/104 mmHg"},
        },
        {"hypertension"},
    ),
    # 5 — Hypertension: hypertensive keyword
    (
        {
            "age": 55, "gender": "male",
            "symptoms": "hypertensive urgency, blurred vision",
            "medical_history": ["hypertension"],
        },
        {"hypertension"},
    ),
    # 6 — Pneumonia: consolidation + fever + cough
    (
        {
            "age": 34, "gender": "male",
            "symptoms": "fever, productive cough, pleuritic pain",
            "lab_values": {"CXR": "right lower lobe consolidation", "WBC": "15.6"},
        },
        {"pneumonia"},
    ),
    # 7 — Pneumonia: sputum + cough + fever
    (
        {
            "age": 70, "gender": "female",
            "symptoms": "fever, cough productive of green sputum, rigors",
        },
        {"pneumonia"},
    ),
    # 8 — Pneumonia: explicit pneumonia keyword in history
    (
        {
            "age": 28, "gender": "male",
            "symptoms": "cough and fever for 5 days, consolidation on X-ray",
            "medical_history": ["previous pneumonia episode"],
        },
        {"pneumonia"},
    ),
    # 9 — AMI: chest pain + troponin + ST elevation
    (
        {
            "age": 67, "gender": "male",
            "symptoms": "severe chest pain radiating to left arm, diaphoresis",
            "lab_values": {"troponin I": "3.1 ng/mL", "ECG": "ST elevation V2-V4"},
        },
        {"myocardial infarction"},
    ),
    # 10 — AMI: myocardial keyword + chest pain
    (
        {
            "age": 58, "gender": "female",
            "symptoms": "crushing chest pain, nausea, diaphoresis",
            "medical_history": ["myocardial infarction 3 years ago"],
        },
        {"myocardial infarction"},
    ),
    # 11 — AMI: troponin rise
    (
        {
            "age": 72, "gender": "male",
            "symptoms": "chest pain at rest",
            "lab_values": {"troponin": "elevated 2.4 ng/mL"},
        },
        {"myocardial infarction"},
    ),
    # 12 — Heart Failure: dyspnea + oedema + BNP
    (
        {
            "age": 72, "gender": "female",
            "symptoms": "dyspnea on exertion, ankle oedema, orthopnea",
            "lab_values": {"BNP": "620 pg/mL"},
        },
        {"heart failure"},
    ),
    # 13 — Heart Failure: heart failure keyword
    (
        {
            "age": 80, "gender": "male",
            "symptoms": "worsening dyspnea and edema",
            "medical_history": ["heart failure", "hypertension"],
        },
        {"heart failure"},
    ),
    # 14 — Pulmonary Embolism: dyspnea + pleuritic + DVT
    (
        {
            "age": 45, "gender": "female",
            "symptoms": "sudden dyspnea, pleuritic chest pain, haemoptysis",
            "medical_history": ["DVT", "recent long-haul flight"],
        },
        {"pulmonary embolism", "embolism"},
    ),
    # 15 — Pulmonary Embolism: embolism + hypoxia
    (
        {
            "age": 39, "gender": "male",
            "symptoms": "dyspnea, hypoxia, pleuritic pain",
            "lab_values": {"D-dimer": "3.8 µg/mL"},
        },
        {"pulmonary embolism", "embolism"},
    ),
    # 16 — UTI: dysuria + pyuria + frequency
    (
        {
            "age": 28, "gender": "female",
            "symptoms": "dysuria, urinary frequency, suprapubic pain",
            "lab_values": {"urinalysis": "pyuria, nitrites positive"},
        },
        {"urinary tract infection", "uti"},
    ),
    # 17 — UTI: UTI keyword
    (
        {
            "age": 33, "gender": "female",
            "symptoms": "burning on urination, frequency, UTI symptoms",
            "lab_values": {"urinalysis": "positive"},
        },
        {"urinary tract infection", "uti"},
    ),
    # 18 — Sepsis: sepsis + fever + tachycardia
    (
        {
            "age": 55, "gender": "male",
            "symptoms": "fever, tachycardia, confusion, rigors",
            "lab_values": {"WBC": "22 × 10⁹/L", "lactate": "3.5 mmol/L"},
        },
        {"sepsis"},
    ),
    # 19 — Sepsis: leukocytosis + fever
    (
        {
            "age": 68, "gender": "female",
            "symptoms": "high fever, tachycardia, hypotension",
            "lab_values": {"WBC": "leukocytosis 24 × 10⁹/L"},
            "medical_history": ["recent abdominal surgery"],
        },
        {"sepsis"},
    ),
    # 20 — Sepsis: explicit sepsis keyword
    (
        {
            "age": 45, "gender": "male",
            "symptoms": "sepsis presentation with fever and tachycardia",
        },
        {"sepsis"},
    ),
]

REQUIRED_ACCURACY = 0.80    # ≥80 % of 20 cases must have the expected label in top-5
REQUIRED_KEYS = {"diagnosis", "confidence", "icd10_code", "reasoning"}


class TestGenerateDiagnosesAccuracy(unittest.TestCase):
    """Run generate_diagnoses over all 20 cases and measure top-5 accuracy."""

    def setUp(self):
        sys.modules["main"].ML_MODELS = {}   # use rule-based path

    def _accepted(self, diagnoses: list, labels: set) -> bool:
        for d in diagnoses:
            name = d.get("diagnosis", "").lower()
            if any(lbl.lower() in name for lbl in labels):
                return True
        return False

    def test_overall_accuracy_80_percent(self):
        hits = 0
        misses = []
        for i, (pd, labels) in enumerate(_CASES, start=1):
            results = generate_diagnoses(pd)
            if self._accepted(results, labels):
                hits += 1
            else:
                misses.append((i, labels, [d["diagnosis"] for d in results]))

        accuracy = hits / len(_CASES)
        self.assertGreaterEqual(
            accuracy,
            REQUIRED_ACCURACY,
            f"Accuracy {accuracy:.0%} below {REQUIRED_ACCURACY:.0%}. "
            f"Missed cases: {misses}",
        )

    def test_each_result_has_required_keys(self):
        for pd, _ in _CASES:
            for d in generate_diagnoses(pd):
                for k in REQUIRED_KEYS:
                    self.assertIn(k, d, f"Key '{k}' missing in {d}")

    def test_confidence_in_range(self):
        for pd, _ in _CASES:
            for d in generate_diagnoses(pd):
                c = d["confidence"]
                self.assertGreaterEqual(c, 0.0, f"Negative confidence in {d}")
                self.assertLessEqual(c,  1.0, f"Confidence > 1.0 in {d}")

    def test_sorted_by_confidence_descending(self):
        for pd, _ in _CASES:
            confs = [d["confidence"] for d in generate_diagnoses(pd)]
            self.assertEqual(
                confs,
                sorted(confs, reverse=True),
                "Diagnoses not sorted by confidence desc",
            )

    def test_at_most_5_results(self):
        for pd, _ in _CASES:
            self.assertLessEqual(len(generate_diagnoses(pd)), 5)

    def test_icd10_format_non_empty(self):
        for pd, _ in _CASES:
            for d in generate_diagnoses(pd):
                icd = d.get("icd10_code", "")
                self.assertTrue(len(icd) >= 3, f"ICD code too short: '{icd}'")


class TestGenerateDiagnosesEdgeCases(unittest.TestCase):
    def setUp(self):
        sys.modules["main"].ML_MODELS = {}

    def test_empty_patient_data_returns_list(self):
        result = generate_diagnoses({})
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_minimal_data_symptoms_only(self):
        result = generate_diagnoses({"symptoms": "chest pain"})
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_all_none_values_returns_list(self):
        result = generate_diagnoses({"age": None, "gender": None, "symptoms": None,
                                     "lab_values": None, "medical_history": None})
        self.assertIsInstance(result, list)

    def test_list_medical_history_accepted(self):
        result = generate_diagnoses({
            "symptoms": "dyspnea",
            "medical_history": ["asthma", "eczema"],
        })
        self.assertIsInstance(result, list)

    def test_string_medical_history_accepted(self):
        result = generate_diagnoses({
            "symptoms": "fever",
            "medical_history": "no significant past medical history",
        })
        self.assertIsInstance(result, list)


class TestModelPipeline(unittest.TestCase):
    """Exercise the BioGPT-Large pipeline branch via a mock."""

    def _biogpt_pipe(self, prompt, **kw):
        payload = [
            {"diagnosis": "Type 2 Diabetes Mellitus", "confidence": 0.91,
             "icd10_code": "E11.9", "reasoning": "Elevated glucose and HbA1c."},
            {"diagnosis": "Hypertension", "confidence": 0.75,
             "icd10_code": "I10", "reasoning": "Elevated BP."},
        ]
        return [{"generated_text": json.dumps(payload)}]

    def setUp(self):
        sys.modules["main"].ML_MODELS = {"biogpt_large": self._biogpt_pipe}

    def tearDown(self):
        sys.modules["main"].ML_MODELS = {}

    def test_model_path_uses_parsed_results(self):
        result = generate_diagnoses({"symptoms": "polyuria, HbA1c 9%"})
        names = [d["diagnosis"] for d in result]
        self.assertIn("Type 2 Diabetes Mellitus", names)

    def test_model_exception_falls_back_to_rule_based(self):
        bad = MagicMock(side_effect=RuntimeError("GPU OOM"))
        sys.modules["main"].ML_MODELS = {"biogpt_large": bad}
        result = generate_diagnoses({"symptoms": "fever, cough"})
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)


class TestInternals(unittest.TestCase):
    """Unit tests for the private helpers."""

    # _lookup_icd10
    def test_exact_match(self):
        self.assertEqual(_lookup_icd10("hypertension"), "I10")

    def test_partial_substring_match(self):
        self.assertEqual(_lookup_icd10("essential hypertension"), "I10")

    def test_unknown_returns_r69(self):
        self.assertEqual(_lookup_icd10("Venusian space flu"), "R69")

    def test_case_insensitive(self):
        self.assertEqual(_lookup_icd10("PNEUMONIA"), "J18.9")

    # _normalise_entry
    def test_normalise_valid(self):
        raw = {"diagnosis": "Pneumonia", "confidence": 0.87,
               "icd10_code": "J18.9", "reasoning": "Fever and consolidation."}
        entry = _normalise_entry(raw, 0)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["diagnosis"], "Pneumonia")
        self.assertAlmostEqual(entry["confidence"], 0.87, places=3)
        self.assertEqual(entry["icd10_code"], "J18.9")

    def test_normalise_clamps_confidence_above_1(self):
        raw = {"diagnosis": "Test", "confidence": 2.5}
        entry = _normalise_entry(raw, 0)
        self.assertLessEqual(entry["confidence"], 1.0)

    def test_normalise_clamps_confidence_below_0(self):
        raw = {"diagnosis": "Test", "confidence": -0.3}
        entry = _normalise_entry(raw, 0)
        self.assertGreaterEqual(entry["confidence"], 0.0)

    def test_normalise_fills_missing_reasoning(self):
        raw = {"diagnosis": "Test", "confidence": 0.5}
        entry = _normalise_entry(raw, 0)
        self.assertTrue(len(entry["reasoning"]) > 0)

    def test_normalise_none_diagnosis_returns_none(self):
        self.assertIsNone(_normalise_entry({"confidence": 0.9}, 0))

    def test_normalise_non_dict_returns_none(self):
        self.assertIsNone(_normalise_entry("not a dict", 0))

    # _parse_generated_text
    def test_parse_valid_json_array(self):
        text = json.dumps([
            {"diagnosis": "Sepsis", "confidence": 0.8, "icd10_code": "A41.9",
             "reasoning": "Fever + leukocytosis."},
        ])
        result = _parse_generated_text(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["diagnosis"], "Sepsis")

    def test_parse_embedded_in_prose(self):
        text = 'The model says: [{"diagnosis":"Gout","confidence":0.7,"icd10_code":"M10.9","reasoning":"Uric acid."}] that is all.'
        result = _parse_generated_text(text)
        self.assertEqual(len(result), 1)

    def test_parse_invalid_json_returns_empty(self):
        self.assertEqual(_parse_generated_text("not json at all"), [])

    def test_parse_empty_string_returns_empty(self):
        self.assertEqual(_parse_generated_text(""), [])


if __name__ == "__main__":
    unittest.main()
