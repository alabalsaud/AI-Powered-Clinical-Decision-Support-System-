"""
Unit tests for app/models/nlp_model.py — extract_medical_entities().

The tests mock main.ML_MODELS so the actual Bio_ClinicalBERT pipeline is
NOT required to be downloaded or running.  The keyword-fallback path is
exercised by default; the model path is exercised by injecting a fake
pipeline fixture.

Run:
    cd cdss-backend
    source venv/bin/activate
    pytest tests/test_nlp.py -v
"""
from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# ── Bootstrap a minimal stub for `main` so the import inside nlp_model
#    (from main import ML_MODELS) does not fail without a running server. ──────
_main_stub = types.ModuleType("main")
_main_stub.ML_MODELS = {}          # empty → keyword fallback by default
sys.modules.setdefault("main", _main_stub)

from app.models.nlp_model import extract_medical_entities  # noqa: E402

# ─── Five representative clinical notes ──────────────────────────────────────
CLINICAL_NOTES = [
    # 1 — Diabetic patient with acute symptoms
    (
        "67-year-old male with known diabetes and hypertension presents with "
        "fever (38.9 °C), chest pain, and shortness of breath. "
        "HbA1c 9.2%, glucose 14.3 mmol/L. Currently on metformin 1000 mg BD "
        "and lisinopril 10 mg OD."
    ),
    # 2 — Respiratory presentation
    (
        "Patient complains of cough productive of yellow sputum, dyspnea on "
        "exertion, and fatigue for 5 days. Chest X-ray shows right lower lobe "
        "consolidation consistent with pneumonia. WBC 14.2 × 10⁹/L. "
        "Started on azithromycin 500 mg daily."
    ),
    # 3 — Cardiac emergency
    (
        "Acute myocardial infarction. Patient presents with severe chest pain "
        "radiating to the left arm, diaphoresis, and nausea. "
        "Troponin I 2.8 ng/mL, INR 1.1. ECG shows ST elevation in V2-V4. "
        "Administered aspirin 300 mg stat and clopidogrel 600 mg loading dose."
    ),
    # 4 — Medication review / poly-pharmacy
    (
        "Annual medication review for 72-year-old female with atrial fibrillation, "
        "heart failure, and hypothyroidism. Currently on warfarin, furosemide, "
        "digoxin, and levothyroxine. Potassium 3.2 meq/L, INR 2.6. "
        "Reports mild dizziness and palpitations."
    ),
    # 5 — Post-operative observation note
    (
        "Day 2 post-operative note following laparoscopic cholecystectomy. "
        "Patient is afebrile. Mild abdominal pain at incision site, tenderness "
        "on palpation. Hemoglobin 10.1 g/dL, creatinine 88 µmol/L. "
        "Continued on acetaminophen 1 g QID for analgesia. No signs of "
        "hepatomegaly or jaundice."
    ),
]

VALID_CATEGORIES = {"SYMPTOM", "CONDITION", "MEDICATION", "LAB_VALUE", "OBSERVATION"}


class TestExtractMedicalEntitiesStructure(unittest.TestCase):
    """Validate the shape and contract of the returned dict."""

    def _run(self, text: str):
        return extract_medical_entities(text)

    def test_returns_dict_with_required_keys(self):
        result = self._run(CLINICAL_NOTES[0])
        self.assertIn("entities",   result)
        self.assertIn("summary",    result)
        self.assertIn("model_used", result)

    def test_summary_has_all_five_categories(self):
        result = self._run(CLINICAL_NOTES[0])
        for cat in VALID_CATEGORIES:
            self.assertIn(cat, result["summary"], f"Missing category: {cat}")

    def test_each_entity_has_required_fields(self):
        result = self._run(CLINICAL_NOTES[0])
        for ent in result["entities"]:
            self.assertIn("text",     ent)
            self.assertIn("category", ent)
            self.assertIn("score",    ent)
            self.assertIn("start",    ent)
            self.assertIn("end",      ent)
            self.assertIn("source",   ent)
            self.assertIn(ent["category"], VALID_CATEGORIES)

    def test_empty_string_returns_empty_result(self):
        result = self._run("")
        self.assertEqual(result["entities"], [])
        self.assertFalse(result["model_used"])

    def test_whitespace_only_returns_empty_result(self):
        result = self._run("   \n\t  ")
        self.assertEqual(result["entities"], [])


class TestKeywordFallback(unittest.TestCase):
    """Tests run with ML_MODELS empty (keyword-only path)."""

    def setUp(self):
        sys.modules["main"].ML_MODELS = {}

    # Note 1 — diabetes / hypertension note
    def test_note1_detects_condition_diabetes(self):
        result = extract_medical_entities(CLINICAL_NOTES[0])
        conditions = [e["text"].lower() for e in result["entities"] if e["category"] == "CONDITION"]
        self.assertTrue(
            any("diabetes" in c for c in conditions),
            f"Expected 'diabetes' in CONDITION, got: {conditions}",
        )

    def test_note1_detects_medication_metformin(self):
        result = extract_medical_entities(CLINICAL_NOTES[0])
        meds = [e["text"].lower() for e in result["entities"] if e["category"] == "MEDICATION"]
        self.assertTrue(
            any("metformin" in m for m in meds),
            f"Expected 'metformin' in MEDICATION, got: {meds}",
        )

    def test_note1_detects_symptom_fever(self):
        result = extract_medical_entities(CLINICAL_NOTES[0])
        symptoms = [e["text"].lower() for e in result["entities"] if e["category"] == "SYMPTOM"]
        self.assertTrue(
            any("fever" in s for s in symptoms),
            f"Expected 'fever' in SYMPTOM, got: {symptoms}",
        )

    def test_note1_detects_lab_value(self):
        result = extract_medical_entities(CLINICAL_NOTES[0])
        labs = [e["text"].lower() for e in result["entities"] if e["category"] == "LAB_VALUE"]
        self.assertTrue(len(labs) > 0, f"Expected at least one LAB_VALUE, got: {labs}")

    # Note 2 — pneumonia / respiratory
    def test_note2_detects_condition_pneumonia(self):
        result = extract_medical_entities(CLINICAL_NOTES[1])
        conditions = [e["text"].lower() for e in result["entities"] if e["category"] == "CONDITION"]
        self.assertTrue(
            any("pneumonia" in c for c in conditions),
            f"Expected 'pneumonia' in CONDITION, got: {conditions}",
        )

    def test_note2_detects_medication_azithromycin(self):
        result = extract_medical_entities(CLINICAL_NOTES[1])
        meds = [e["text"].lower() for e in result["entities"] if e["category"] == "MEDICATION"]
        self.assertTrue(
            any("azithromycin" in m for m in meds),
            f"Expected 'azithromycin' in MEDICATION, got: {meds}",
        )

    # Note 3 — cardiac / AMI
    def test_note3_detects_condition_myocardial_infarction(self):
        result = extract_medical_entities(CLINICAL_NOTES[2])
        conditions = [e["text"].lower() for e in result["entities"] if e["category"] == "CONDITION"]
        self.assertTrue(
            any("myocardial infarction" in c for c in conditions),
            f"Expected 'myocardial infarction' in CONDITION, got: {conditions}",
        )

    def test_note3_detects_medication_aspirin(self):
        result = extract_medical_entities(CLINICAL_NOTES[2])
        meds = [e["text"].lower() for e in result["entities"] if e["category"] == "MEDICATION"]
        self.assertTrue(
            any("aspirin" in m for m in meds),
            f"Expected 'aspirin' in MEDICATION, got: {meds}",
        )

    # Note 4 — poly-pharmacy
    def test_note4_detects_symptom_palpitations(self):
        result = extract_medical_entities(CLINICAL_NOTES[3])
        symptoms = [e["text"].lower() for e in result["entities"] if e["category"] == "SYMPTOM"]
        self.assertTrue(
            any("palpitations" in s for s in symptoms),
            f"Expected 'palpitations' in SYMPTOM, got: {symptoms}",
        )

    def test_note4_detects_multiple_medications(self):
        result = extract_medical_entities(CLINICAL_NOTES[3])
        meds = [e["text"].lower() for e in result["entities"] if e["category"] == "MEDICATION"]
        self.assertGreaterEqual(len(meds), 2, f"Expected ≥2 medications, got: {meds}")

    # Note 5 — post-operative
    def test_note5_detects_observation_tenderness(self):
        result = extract_medical_entities(CLINICAL_NOTES[4])
        obs = [e["text"].lower() for e in result["entities"] if e["category"] == "OBSERVATION"]
        self.assertTrue(
            any("tenderness" in o for o in obs),
            f"Expected 'tenderness' in OBSERVATION, got: {obs}",
        )

    def test_note5_detects_medication_acetaminophen(self):
        result = extract_medical_entities(CLINICAL_NOTES[4])
        meds = [e["text"].lower() for e in result["entities"] if e["category"] == "MEDICATION"]
        self.assertTrue(
            any("acetaminophen" in m for m in meds),
            f"Expected 'acetaminophen' in MEDICATION, got: {meds}",
        )


class TestModelPipelinePath(unittest.TestCase):
    """Tests that exercise the live-model branch using a mock pipeline."""

    def _make_mock_pipe(self):
        """Return a callable that mimics transformers NER pipeline output."""
        def _pipe(text):
            return [
                {"entity_group": "problem",   "word": "chest pain", "score": 0.92, "start": 0, "end": 10},
                {"entity_group": "treatment", "word": "aspirin",    "score": 0.88, "start": 11, "end": 18},
                {"entity_group": "test",      "word": "troponin",   "score": 0.85, "start": 19, "end": 27},
            ]
        return _pipe

    def test_model_entities_are_mapped_correctly(self):
        sys.modules["main"].ML_MODELS = {"bio_clinical_bert": self._make_mock_pipe()}
        result = extract_medical_entities("chest pain aspirin troponin")
        self.assertTrue(result["model_used"])
        categories = {e["category"] for e in result["entities"]}
        self.assertIn("CONDITION",  categories)   # problem → CONDITION
        self.assertIn("MEDICATION", categories)   # treatment → MEDICATION
        self.assertIn("LAB_VALUE",  categories)   # test → LAB_VALUE

    def test_model_source_tagged_correctly(self):
        sys.modules["main"].ML_MODELS = {"bio_clinical_bert": self._make_mock_pipe()}
        result = extract_medical_entities("chest pain aspirin troponin")
        sources = {e["source"] for e in result["entities"]}
        self.assertIn("model", sources)

    def test_model_exception_falls_back_to_keyword(self):
        bad_pipe = MagicMock(side_effect=RuntimeError("model crashed"))
        sys.modules["main"].ML_MODELS = {"bio_clinical_bert": bad_pipe}
        result = extract_medical_entities(CLINICAL_NOTES[0])
        # Should still return results via keyword fallback
        self.assertFalse(result["model_used"])
        self.assertGreater(len(result["entities"]), 0)

    def tearDown(self):
        sys.modules["main"].ML_MODELS = {}


if __name__ == "__main__":
    unittest.main()
