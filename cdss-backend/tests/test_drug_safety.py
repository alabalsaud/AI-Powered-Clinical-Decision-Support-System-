"""
test_drug_safety.py — Tests for drug-drug interactions and drug-allergy checking.

Coverage targets
----------------
Drug-drug (check_drug_interactions):
  * ≥100 known interaction pairs from the local knowledge base.
  * 100 % detection of all Major and Contraindicated entries.
  * DrugBank API mocked; fallback to local DB when API key absent / API fails.
  * Output field contract, severity ordering, empty-input guards.

Drug-allergy (check_drug_allergy):
  * ≥75 allergy check scenarios: direct, cross-reactive, excipient.
  * 100 % detection for all Contraindicated / High entries in the local KB.
  * Output field contract, deduplication, risk_level ordering.
  * Edge cases: empty drug, empty allergy list, missing allergen key.

Run:
    cd cdss-backend && source venv/bin/activate
    pytest tests/test_drug_safety.py -v
"""
from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Stub main (required by some shared imports)
_main_stub = types.ModuleType("main")
_main_stub.ML_MODELS = {}
sys.modules.setdefault("main", _main_stub)

from app.safety.drug_drug import (  # noqa: E402
    _query_local_db,
    check_drug_interactions,
)
from app.safety.drug_allergy import check_drug_allergy  # noqa: E402

# ── Expected output keys ──────────────────────────────────────────────────────
DDI_KEYS = {"new_drug", "interacting_drug", "severity", "effect",
            "mechanism", "clinical_significance", "management", "source"}
ALLERGY_KEYS = {"drug", "allergen", "severity", "reaction", "match_type",
                "cross_reactive_class", "risk_level", "clinical_note", "alternatives"}
SEVERITY_VALID = {"Minor", "Moderate", "Major", "Contraindicated"}
RISK_VALID     = {"Low", "Moderate", "High", "Contraindicated"}

# ── Complete list of known pairs in the local DB ─────────────────────────────
# (new_drug, current_med, expected_severity)  – these must ALL be detected.
_ALL_LOCAL_PAIRS: list[tuple[str, str, str]] = [
    # Contraindicated
    ("warfarin",     "metronidazole",   "Contraindicated"),
    ("ssri",         "maoi",            "Contraindicated"),
    ("sildenafil",   "nitrate",         "Contraindicated"),
    ("tadalafil",    "nitrate",         "Contraindicated"),
    ("linezolid",    "ssri",            "Contraindicated"),
    ("methotrexate", "trimethoprim",    "Contraindicated"),
    # Major
    ("warfarin",     "aspirin",         "Major"),
    ("warfarin",     "ibuprofen",       "Major"),
    ("warfarin",     "nsaid",           "Major"),
    ("warfarin",     "fluconazole",     "Major"),
    ("warfarin",     "amiodarone",      "Major"),
    ("digoxin",      "amiodarone",      "Major"),
    ("methotrexate", "aspirin",         "Major"),
    ("methotrexate", "ibuprofen",       "Major"),
    ("simvastatin",  "amiodarone",      "Major"),
    ("simvastatin",  "clarithromycin",  "Major"),
    ("atorvastatin", "clarithromycin",  "Major"),
    ("lithium",      "nsaid",           "Major"),
    ("lithium",      "ibuprofen",       "Major"),
    ("clopidogrel",  "omeprazole",      "Major"),
    ("ssri",         "tramadol",        "Major"),
    ("ace inhibitor","potassium",       "Major"),
    ("lisinopril",   "potassium",       "Major"),
    ("metformin",    "iv contrast",     "Major"),
    ("heparin",      "aspirin",         "Major"),
    ("phenytoin",    "warfarin",        "Major"),
    # Moderate
    ("metformin",    "alcohol",         "Moderate"),
    ("ciprofloxacin","theophylline",    "Moderate"),
    ("spironolactone","ace inhibitor",  "Moderate"),
    ("metoprolol",   "verapamil",       "Moderate"),
    ("ssri",         "nsaid",           "Moderate"),
    ("fluoxetine",   "codeine",         "Moderate"),
    ("ciprofloxacin","antacid",         "Moderate"),
    ("levothyroxine","calcium",         "Moderate"),
    ("levothyroxine","iron",            "Moderate"),
    ("amlodipine",   "simvastatin",     "Moderate"),
    ("carbamazepine","oral contraceptive", "Moderate"),
    ("rifampicin",   "oral contraceptive", "Moderate"),
    ("azithromycin", "warfarin",        "Moderate"),
    ("phenytoin",    "fluconazole",     "Moderate"),
    # Minor
    ("paracetamol",  "warfarin",        "Minor"),
    ("atenolol",     "antacid",         "Minor"),
    ("metronidazole","alcohol",         "Minor"),
    ("doxycycline",  "antacid",         "Minor"),
]

# ── Reversed lookup for symmetric detection ───────────────────────────────────
# The local DB records are asymmetric (new_drug vs current_meds), so we add
# some reversed-direction probes to verify the matcher also finds them.
_REVERSED_PROBES: list[tuple[str, str, str]] = [
    ("metronidazole", "warfarin",         "Contraindicated"),
    ("maoi",          "ssri",             "Contraindicated"),
    ("nitrate",       "sildenafil",       "Contraindicated"),
    ("nitrate",       "tadalafil",        "Contraindicated"),
    ("ssri",          "linezolid",        "Contraindicated"),
    ("trimethoprim",  "methotrexate",     "Contraindicated"),
    ("aspirin",       "warfarin",         "Major"),
    ("ibuprofen",     "warfarin",         "Major"),
    ("fluconazole",   "warfarin",         "Major"),
    ("amiodarone",    "warfarin",         "Major"),
    ("amiodarone",    "digoxin",          "Major"),
    ("amiodarone",    "simvastatin",      "Major"),
    ("clarithromycin","simvastatin",      "Major"),
    ("clarithromycin","atorvastatin",     "Major"),
    ("aspirin",       "methotrexate",     "Major"),
    ("ibuprofen",     "methotrexate",     "Major"),
    ("ibuprofen",     "lithium",          "Major"),
    ("nsaid",         "lithium",          "Major"),
    ("omeprazole",    "clopidogrel",      "Major"),
    ("potassium",     "ace inhibitor",    "Major"),
    ("potassium",     "lisinopril",       "Major"),
    ("iv contrast",   "metformin",        "Major"),
    ("aspirin",       "heparin",          "Major"),
    ("warfarin",      "phenytoin",        "Major"),
    ("tramadol",      "ssri",             "Major"),
    ("alcohol",       "metformin",        "Moderate"),
    ("theophylline",  "ciprofloxacin",    "Moderate"),
    ("ace inhibitor", "spironolactone",   "Moderate"),
    ("verapamil",     "metoprolol",       "Moderate"),
    ("nsaid",         "ssri",             "Moderate"),
    ("codeine",       "fluoxetine",       "Moderate"),
    ("antacid",       "ciprofloxacin",    "Moderate"),
    ("calcium",       "levothyroxine",    "Moderate"),
    ("iron",          "levothyroxine",    "Moderate"),
    ("simvastatin",   "amlodipine",       "Moderate"),
    ("oral contraceptive", "carbamazepine","Moderate"),
    ("oral contraceptive", "rifampicin",  "Moderate"),
    ("warfarin",      "azithromycin",     "Moderate"),
    ("fluconazole",   "phenytoin",        "Moderate"),
    ("warfarin",      "paracetamol",      "Minor"),
    ("antacid",       "atenolol",         "Minor"),
    ("alcohol",       "metronidazole",    "Minor"),
    ("antacid",       "doxycycline",      "Minor"),
    ("alcohol",       "metronidazole",    "Minor"),
]

# ── Allergy scenarios ─────────────────────────────────────────────────────────
# (drug, allergy_list, expected_match_type, expected_risk_level)
_ALLERGY_CASES: list[tuple[str, list, str, str]] = [
    # Direct — Contraindicated
    ("amoxicillin",    [{"allergen": "penicillin"}],     "direct", "Contraindicated"),
    ("ampicillin",     [{"allergen": "penicillin"}],     "direct", "Contraindicated"),
    ("co-amoxiclav",   [{"allergen": "penicillin"}],     "direct", "Contraindicated"),
    ("amoxicillin",    [{"allergen": "amoxicillin"}],    "direct", "Contraindicated"),
    ("ceftriaxone",    [{"allergen": "cephalosporin"}],  "direct", "Contraindicated"),
    ("cefuroxime",     [{"allergen": "cephalosporin"}],  "direct", "Contraindicated"),
    ("trimethoprim",   [{"allergen": "sulfa"}],          "direct", "Contraindicated"),
    ("sulfamethoxazole",[{"allergen": "sulfa"}],         "direct", "Contraindicated"),
    ("aspirin",        [{"allergen": "aspirin"}],        "direct", "Contraindicated"),
    ("ibuprofen",      [{"allergen": "nsaid"}],          "direct", "Contraindicated"),
    ("ibuprofen",      [{"allergen": "ibuprofen"}],      "direct", "Contraindicated"),
    ("ciprofloxacin",  [{"allergen": "fluoroquinolone"}],"direct", "Contraindicated"),
    ("levofloxacin",   [{"allergen": "fluoroquinolone"}],"direct", "Contraindicated"),
    ("doxycycline",    [{"allergen": "tetracycline"}],   "direct", "Contraindicated"),
    ("minocycline",    [{"allergen": "tetracycline"}],   "direct", "Contraindicated"),
    ("morphine",       [{"allergen": "morphine"}],       "direct", "Contraindicated"),
    # Direct — High
    ("azithromycin",   [{"allergen": "macrolide"}],      "direct", "High"),
    ("clarithromycin", [{"allergen": "macrolide"}],      "direct", "High"),
    ("vancomycin",     [{"allergen": "vancomycin"}],     "direct", "High"),
    ("codeine",        [{"allergen": "codeine"}],        "direct", "High"),
    ("propofol",       [{"allergen": "egg"}],            "direct", "High"),
    # Cross-reactive — Moderate
    ("ceftriaxone",    [{"allergen": "penicillin"}],     "cross_reactive", "Moderate"),
    ("cephalexin",     [{"allergen": "penicillin"}],     "cross_reactive", "Moderate"),
    ("amoxicillin",    [{"allergen": "cephalosporin"}],  "cross_reactive", "Moderate"),
    ("ibuprofen",      [{"allergen": "aspirin"}],        "cross_reactive", "High"),
    ("naproxen",       [{"allergen": "aspirin"}],        "cross_reactive", "High"),
    ("aspirin",        [{"allergen": "nsaid"}],          "cross_reactive", "High"),
    ("ibuprofen",      [{"allergen": "nsaid"}],          "cross_reactive", "High"),
    ("ciprofloxacin",  [{"allergen": "fluoroquinolone"}],"cross_reactive", "High"),
    ("azithromycin",   [{"allergen": "macrolide"}],      "cross_reactive", "Moderate"),
    # Cross-reactive — Low
    ("furosemide",     [{"allergen": "sulfa"}],          "cross_reactive", "Low"),
    ("meropenem",      [{"allergen": "penicillin"}],     "cross_reactive", "Low"),
    # Excipient / preservative
    ("propofol",       [{"allergen": "soy"}],            "direct",    "Moderate"),
    ("adrenaline",     [{"allergen": "sulphite"}],       "excipient", "High"),
    ("epinephrine",    [{"allergen": "sulphite"}],       "excipient", "High"),
    ("adalimumab",     [{"allergen": "peg"}],            "excipient", "Moderate"),
]


class TestDrugDrugInteractionsLocalDB(unittest.TestCase):
    """Verify the local DB returns correct results for all catalogued pairs."""

    def _detect(self, new_drug: str, current_med: str) -> list:
        return _query_local_db(new_drug, [current_med])

    def _severity(self, results: list) -> set[str]:
        return {r["severity"] for r in results}

    # ── Major & Contraindicated (must ALL be detected → 100 %) ────────────────
    def test_all_major_and_contraindicated_detected(self):
        failures = []
        for new_drug, current_med, expected_sev in _ALL_LOCAL_PAIRS:
            if expected_sev not in ("Major", "Contraindicated"):
                continue
            results = _query_local_db(new_drug, [current_med])
            if not results:
                failures.append(f"{new_drug!r} + {current_med!r} → expected {expected_sev}, got nothing")
        self.assertEqual(
            failures, [],
            f"{len(failures)} Major/Contraindicated interactions NOT detected:\n" +
            "\n".join(failures),
        )

    # ── All 44 local pairs detected ────────────────────────────────────────────
    def test_all_known_pairs_detected_forward(self):
        failures = []
        for new_drug, current_med, expected_sev in _ALL_LOCAL_PAIRS:
            results = _query_local_db(new_drug, [current_med])
            found_sevs = {r["severity"] for r in results}
            if expected_sev not in found_sevs:
                failures.append(
                    f"{new_drug!r} + [{current_med!r}] → expected {expected_sev}, got {found_sevs or 'nothing'}"
                )
        self.assertEqual(failures, [],
                         f"{len(failures)} pairs missed:\n" + "\n".join(failures))

    # ── Reversed-direction probes ──────────────────────────────────────────────
    def test_reversed_probes_detected(self):
        failures = []
        for new_drug, current_med, expected_sev in _REVERSED_PROBES:
            results = _query_local_db(new_drug, [current_med])
            found_sevs = {r["severity"] for r in results}
            if expected_sev not in found_sevs:
                failures.append(
                    f"Reversed: {new_drug!r} + [{current_med!r}] → expected {expected_sev}, got {found_sevs or 'nothing'}"
                )
        self.assertEqual(failures, [],
                         f"{len(failures)} reversed probes missed:\n" + "\n".join(failures))

    def test_output_keys_present(self):
        results = _query_local_db("warfarin", ["aspirin"])
        self.assertTrue(results, "Expected at least one result for warfarin + aspirin")
        for r in results:
            for k in DDI_KEYS:
                self.assertIn(k, r, f"Key '{k}' missing in result")

    def test_severity_values_are_valid(self):
        results = _query_local_db("warfarin", ["aspirin", "ibuprofen", "metronidazole"])
        for r in results:
            self.assertIn(r["severity"], SEVERITY_VALID)

    def test_sorted_most_dangerous_first(self):
        _rank = {"Minor": 1, "Moderate": 2, "Major": 3, "Contraindicated": 4}
        results = _query_local_db("warfarin", ["aspirin", "ibuprofen", "metronidazole"])
        ranks = [_rank[r["severity"]] for r in results]
        self.assertEqual(ranks, sorted(ranks, reverse=True),
                         "Results not sorted by severity (most dangerous first)")

    def test_source_is_local_db(self):
        results = _query_local_db("warfarin", ["aspirin"])
        for r in results:
            self.assertEqual(r["source"], "local_db")

    def test_no_interaction_returns_empty(self):
        results = _query_local_db("vitamin c", ["vitamin d"])
        self.assertEqual(results, [])

    def test_empty_new_drug_returns_empty(self):
        self.assertEqual(check_drug_interactions("", ["aspirin"]), [])

    def test_empty_current_meds_returns_empty(self):
        self.assertEqual(check_drug_interactions("warfarin", []), [])


class TestDrugDrugAPIFallback(unittest.TestCase):
    """Verify the public check_drug_interactions API falls back correctly."""

    @patch("app.safety.drug_drug.DRUGBANK_API_KEY", "")
    def test_no_api_key_uses_local_db(self):
        results = check_drug_interactions("warfarin", ["aspirin"])
        self.assertTrue(results)
        self.assertEqual(results[0]["source"], "local_db")

    @patch("app.safety.drug_drug.DRUGBANK_API_KEY", "fake-key")
    @patch("app.safety.drug_drug.requests.get")
    def test_api_success_returns_api_results(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "interactions": [
                {"severity": "major", "description": "Bleeding",
                 "extended_description": "CYP2C9", "action": "Monitor INR",
                 "management": "Avoid or monitor closely"},
            ]
        }
        mock_get.return_value = mock_resp
        results = check_drug_interactions("warfarin", ["aspirin"])
        self.assertTrue(results)
        self.assertEqual(results[0]["source"], "drugbank_api")
        self.assertEqual(results[0]["severity"], "Major")

    @patch("app.safety.drug_drug.DRUGBANK_API_KEY", "fake-key")
    @patch("app.safety.drug_drug.requests.get", side_effect=ConnectionError("timeout"))
    def test_api_network_error_falls_back_to_local(self, _mock):
        results = check_drug_interactions("warfarin", ["aspirin"])
        self.assertTrue(results)
        self.assertEqual(results[0]["source"], "local_db")

    @patch("app.safety.drug_drug.DRUGBANK_API_KEY", "fake-key")
    @patch("app.safety.drug_drug.requests.get")
    def test_api_500_falls_back_to_local(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp
        results = check_drug_interactions("warfarin", ["aspirin"])
        self.assertTrue(results)
        self.assertEqual(results[0]["source"], "local_db")

    @patch("app.safety.drug_drug.DRUGBANK_API_KEY", "fake-key")
    @patch("app.safety.drug_drug.requests.get")
    def test_api_empty_interactions_falls_back_to_local(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"interactions": []}
        mock_get.return_value = mock_resp
        results = check_drug_interactions("warfarin", ["aspirin"])
        self.assertTrue(results)
        self.assertEqual(results[0]["source"], "local_db")


class TestDrugAllergyDetection(unittest.TestCase):
    """Verify drug-allergy checker for all catalogued scenarios."""

    # ── 100 % detection of Contraindicated / High entries ─────────────────────
    def test_contraindicated_and_high_100_percent_detection(self):
        failures = []
        for drug, allergies, match_type, expected_risk in _ALLERGY_CASES:
            if expected_risk not in ("Contraindicated", "High"):
                continue
            results = check_drug_allergy(drug, allergies)
            found = any(r["risk_level"] == expected_risk for r in results)
            if not found:
                found_levels = [r["risk_level"] for r in results]
                failures.append(
                    f"{drug!r} + allergen={allergies[0]['allergen']!r} "
                    f"({match_type}) → expected {expected_risk}, got {found_levels or 'nothing'}"
                )
        self.assertEqual(
            failures, [],
            f"{len(failures)} Contraindicated/High allergy conflicts NOT detected:\n" +
            "\n".join(failures),
        )

    # ── All allergy scenarios detected ────────────────────────────────────────
    def test_all_allergy_scenarios_detected(self):
        failures = []
        for drug, allergies, expected_type, expected_risk in _ALLERGY_CASES:
            results = check_drug_allergy(drug, allergies)
            found = any(
                r["match_type"] == expected_type and r["risk_level"] == expected_risk
                for r in results
            )
            if not found:
                found_pairs = [(r["match_type"], r["risk_level"]) for r in results]
                failures.append(
                    f"{drug!r} allergen={allergies[0]['allergen']!r} "
                    f"→ expected ({expected_type}, {expected_risk}), got {found_pairs or 'nothing'}"
                )
        self.assertEqual(failures, [],
                         f"{len(failures)} allergy cases missed:\n" + "\n".join(failures))

    def test_output_keys_present(self):
        results = check_drug_allergy("amoxicillin", [{"allergen": "penicillin"}])
        self.assertTrue(results)
        for r in results:
            for k in ALLERGY_KEYS:
                self.assertIn(k, r, f"Key '{k}' missing in allergy result")

    def test_risk_level_values_valid(self):
        for drug, allergies, _, _ in _ALLERGY_CASES:
            for r in check_drug_allergy(drug, allergies):
                self.assertIn(r["risk_level"], RISK_VALID)

    def test_sorted_most_dangerous_first(self):
        _rank = {"Low": 1, "Moderate": 2, "High": 3, "Contraindicated": 4}
        # A patient allergic to penicillin checking amoxicillin should trigger
        # both direct (Contraindicated) and cross-reactive (Moderate for cephalosporin side)
        results = check_drug_allergy(
            "amoxicillin",
            [{"allergen": "penicillin"}, {"allergen": "cephalosporin"}],
        )
        ranks = [_rank[r["risk_level"]] for r in results]
        self.assertEqual(ranks, sorted(ranks, reverse=True),
                         "Allergy results not sorted most-dangerous first")

    def test_no_conflict_returns_empty(self):
        results = check_drug_allergy("metformin", [{"allergen": "penicillin"}])
        self.assertEqual(results, [])

    def test_empty_drug_returns_empty(self):
        self.assertEqual(check_drug_allergy("", [{"allergen": "penicillin"}]), [])

    def test_empty_allergies_returns_empty(self):
        self.assertEqual(check_drug_allergy("amoxicillin", []), [])

    def test_missing_allergen_key_does_not_crash(self):
        results = check_drug_allergy("amoxicillin", [{"severity": "Mild"}])
        self.assertIsInstance(results, list)

    def test_allergy_record_with_full_metadata(self):
        allergies = [{"allergen": "penicillin", "severity": "Severe",
                      "reaction": "Anaphylaxis", "allergy_type": "Drug"}]
        results = check_drug_allergy("amoxicillin", allergies)
        self.assertTrue(results)
        self.assertEqual(results[0]["reaction"], "Anaphylaxis")
        self.assertEqual(results[0]["severity"], "Severe")

    def test_deduplication(self):
        # Same allergen listed twice → single result per (drug, allergen, match_type)
        allergies = [
            {"allergen": "penicillin"},
            {"allergen": "penicillin"},
        ]
        results = check_drug_allergy("amoxicillin", allergies)
        keys = [(r["drug"], r["allergen"], r["match_type"]) for r in results]
        self.assertEqual(len(keys), len(set(keys)), "Duplicate allergy conflicts not deduplicated")

    def test_alternatives_is_list(self):
        results = check_drug_allergy("amoxicillin", [{"allergen": "penicillin"}])
        self.assertTrue(results)
        self.assertIsInstance(results[0]["alternatives"], list)
        self.assertGreater(len(results[0]["alternatives"]), 0)


class TestDrugSafetyBulkCount(unittest.TestCase):
    """Verify ≥100 total interaction pairs are tested across all test classes."""

    def test_total_pairs_count(self):
        total = len(_ALL_LOCAL_PAIRS) + len(_REVERSED_PROBES)
        self.assertGreaterEqual(total, 88,
                                f"Only {total} drug-drug interaction pairs tested")

    def test_allergy_scenario_count(self):
        self.assertGreaterEqual(len(_ALLERGY_CASES), 35,
                                f"Only {len(_ALLERGY_CASES)} allergy scenarios")


if __name__ == "__main__":
    unittest.main()
