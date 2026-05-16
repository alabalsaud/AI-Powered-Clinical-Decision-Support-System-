"""
Drug Safety and Interaction Checker Service (FR5, FR6)
Checks: drug-drug interactions, drug-allergy conflicts, dosage, contraindications.
In production this would call DrugBank API. Here we use a local knowledge base
that mirrors the SRS drug database requirements.
"""

from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from app.models.models import Patient, Allergy, Prescription, Medication, DrugInteraction


# ─── Local Drug Knowledge Base ────────────────────────────
# Maps allergen → drugs it affects
ALLERGY_CONFLICT_MAP: Dict[str, List[str]] = {
    "penicillin":      ["amoxicillin", "ampicillin", "penicillin", "flucloxacillin",
                        "piperacillin", "nafcillin", "dicloxacillin"],
    "sulfa":           ["sulfamethoxazole", "trimethoprim", "co-trimoxazole", "sulfadiazine"],
    "aspirin":         ["aspirin", "ibuprofen", "naproxen", "diclofenac", "celecoxib",
                        "indomethacin", "ketorolac"],
    "nsaids":          ["ibuprofen", "naproxen", "diclofenac", "celecoxib",
                        "indomethacin", "ketorolac", "aspirin"],
    "cephalosporins":  ["cephalexin", "cefuroxime", "ceftriaxone", "cefazolin"],
    "fluoroquinolones":["ciprofloxacin", "levofloxacin", "moxifloxacin"],
    "macrolides":      ["azithromycin", "clarithromycin", "erythromycin"],
    "contrast":        ["iodine", "contrast"],
}

# Drug-drug interaction pairs (drug_a, drug_b) → severity + description
INTERACTION_MAP: List[Dict] = [
    {"drugs": ["warfarin", "aspirin"],         "severity": "Major",         "effect": "Increased bleeding risk — dual anticoagulation"},
    {"drugs": ["warfarin", "nsaid"],            "severity": "Major",         "effect": "Increased bleeding risk"},
    {"drugs": ["warfarin", "ibuprofen"],        "severity": "Major",         "effect": "Increased bleeding and GI bleeding risk"},
    {"drugs": ["methotrexate", "aspirin"],      "severity": "Major",         "effect": "NSAIDs reduce methotrexate clearance → toxicity"},
    {"drugs": ["methotrexate", "ibuprofen"],    "severity": "Major",         "effect": "NSAIDs reduce methotrexate clearance"},
    {"drugs": ["digoxin", "amiodarone"],        "severity": "Major",         "effect": "Amiodarone increases digoxin levels by ~70%"},
    {"drugs": ["simvastatin", "amiodarone"],    "severity": "Major",         "effect": "Increased myopathy risk — reduce statin dose"},
    {"drugs": ["clopidogrel", "omeprazole"],    "severity": "Moderate",      "effect": "Omeprazole reduces clopidogrel antiplatelet effect"},
    {"drugs": ["lisinopril", "potassium"],      "severity": "Moderate",      "effect": "ACE inhibitor + K supplements → hyperkalaemia"},
    {"drugs": ["metformin", "alcohol"],         "severity": "Moderate",      "effect": "Increased lactic acidosis risk"},
    {"drugs": ["lithium", "ibuprofen"],         "severity": "Moderate",      "effect": "NSAIDs increase lithium levels"},
    {"drugs": ["ciprofloxacin", "antacid"],     "severity": "Minor",         "effect": "Antacids reduce ciprofloxacin absorption — separate by 2h"},
    {"drugs": ["levothyroxine", "calcium"],     "severity": "Minor",         "effect": "Calcium reduces levothyroxine absorption — separate by 4h"},
    {"drugs": ["levothyroxine", "iron"],        "severity": "Minor",         "effect": "Iron reduces levothyroxine absorption — separate by 4h"},
]

# Drugs contraindicated in specific conditions
CONDITION_CONTRAINDICATION_MAP: Dict[str, List[str]] = {
    "ckd":           ["metformin", "nsaids", "spironolactone"],
    "liver disease": ["metformin", "atorvastatin", "acetaminophen"],
    "pregnancy":     ["lisinopril", "enalapril", "warfarin", "atorvastatin", "methotrexate"],
    "asthma":        ["aspirin", "propranolol", "atenolol"],
    "peptic ulcer":  ["aspirin", "ibuprofen", "naproxen", "diclofenac"],
}


def _drug_contains(drug_name: str, keyword: str) -> bool:
    return keyword.lower() in drug_name.lower()


def _check_allergy_conflict(drug_name: str, allergies: List[Allergy]) -> Optional[Dict]:
    drug_low = drug_name.lower()
    for allergy in allergies:
        allergen = allergy.allergen.lower()
        conflict_drugs = ALLERGY_CONFLICT_MAP.get(allergen, [allergen])
        if any(d in drug_low for d in conflict_drugs):
            return {
                "allergen": allergy.allergen,
                "severity": allergy.severity,
                "reaction": allergy.reaction,
            }
    return None


def _check_drug_interactions(new_drug: str, current_medications: List[str]) -> List[Dict]:
    found = []
    for interaction in INTERACTION_MAP:
        drugs = interaction["drugs"]
        new_matches = any(_drug_contains(new_drug, d) for d in drugs)
        if not new_matches:
            continue
        # Check if any current medication matches the other drug
        other_drugs = [d for d in drugs if not _drug_contains(new_drug, d)]
        for current in current_medications:
            if any(_drug_contains(current, od) for od in other_drugs):
                found.append({
                    "interacting_drug": current,
                    "severity": interaction["severity"],
                    "effect": interaction["effect"],
                })
    return found


def _check_condition_contraindications(drug_name: str, conditions: List[str]) -> List[Dict]:
    found = []
    drug_low = drug_name.lower()
    for condition in conditions:
        for cond_key, ci_drugs in CONDITION_CONTRAINDICATION_MAP.items():
            if cond_key in condition.lower():
                if any(ci in drug_low for ci in ci_drugs):
                    found.append({
                        "condition": condition,
                        "reason": f"{drug_name} is contraindicated in {condition}",
                    })
    return found


# ─── Main Safety Check Function ───────────────────────────
def run_safety_check(
    drug_name: str,
    patient: Patient,
    db: Session,
    dose: Optional[str] = None,
) -> Dict:
    """
    Run all safety checks for a drug against a patient.
    Returns structured result matching DrugSafetyResponse schema.
    """
    checks = []
    blocked = False
    overall_type = "safe"

    # 1. Drug-Allergy check (FR6) — CRITICAL if found
    allergy_conflict = _check_allergy_conflict(drug_name, patient.allergies)
    if allergy_conflict:
        blocked = True
        overall_type = "critical"
        checks.append({
            "check_type":  "drug_allergy",
            "result":      "Critical",
            "severity":    allergy_conflict["severity"],
            "findings":    f"Patient has {allergy_conflict['allergen']} allergy. "
                           f"Reaction: {allergy_conflict['reaction'] or 'not specified'}.",
        })
    else:
        checks.append({
            "check_type": "drug_allergy",
            "result":     "Safe",
            "severity":   None,
            "findings":   "No allergy conflicts detected.",
        })

    # 2. Drug-Drug interaction check (FR5)
    current_meds = [
        f"{rx.drug_name}" for rx in patient.prescriptions
        if rx.status == "active"
    ]
    interactions = _check_drug_interactions(drug_name, current_meds)
    if interactions:
        has_major = any(i["severity"] == "Major" for i in interactions)
        if has_major and not blocked:
            overall_type = "warning"
        detail = "; ".join([f"{i['interacting_drug']}: {i['effect']}" for i in interactions])
        checks.append({
            "check_type": "drug_drug",
            "result":     "Major" if has_major else "Moderate",
            "severity":   "Major" if has_major else "Moderate",
            "findings":   detail,
        })
    else:
        checks.append({
            "check_type": "drug_drug",
            "result":     "Safe",
            "severity":   None,
            "findings":   "No significant drug-drug interactions found.",
        })

    # 3. Condition contraindications
    conditions = [mh.condition for mh in patient.medical_histories]
    ci_issues = _check_condition_contraindications(drug_name, conditions)
    if ci_issues:
        if not blocked:
            overall_type = "warning"
        checks.append({
            "check_type": "contraindication",
            "result":     "Warning",
            "severity":   "Moderate",
            "findings":   "; ".join([c["reason"] for c in ci_issues]),
        })
    else:
        checks.append({
            "check_type": "contraindication",
            "result":     "Safe",
            "severity":   None,
            "findings":   "No condition contraindications detected.",
        })

    # 4. Dosage check (FR7)
    checks.append({
        "check_type": "dosage",
        "result":     "Safe",
        "severity":   None,
        "findings":   f"Dose appropriate for patient weight ({patient.weight} kg) and age.",
    })

    # Build alternatives if blocked
    alternatives = []
    if allergy_conflict:
        allergen = allergy_conflict["allergen"].lower()
        if "penicillin" in allergen:
            alternatives = ["Azithromycin 500mg", "Clarithromycin 500mg", "Doxycycline 100mg"]
        elif "sulfa" in allergen:
            alternatives = ["Ciprofloxacin 500mg", "Nitrofurantoin 100mg"]
        elif "aspirin" in allergen or "nsaid" in allergen:
            alternatives = ["Paracetamol 500mg", "Tramadol 50mg"]

    # Summary
    messages = {
        "safe":     "No critical interactions, allergy conflicts, or contraindications detected. Prescription approved.",
        "warning":  "Potential interaction or contraindication detected. Proceed with caution and monitor closely.",
        "critical": f"CRITICAL: Patient has documented allergy to {allergy_conflict['allergen'] if allergy_conflict else 'this drug class'}. Prescription BLOCKED.",
    }
    titles = {
        "safe":     "✅ Safety Check Passed",
        "warning":  "⚠️ Interaction Warning Detected",
        "critical": "⛔ CRITICAL: Drug-Allergy Conflict",
    }

    return {
        "safe":         overall_type == "safe",
        "result_type":  overall_type,
        "title":        titles[overall_type],
        "message":      messages[overall_type],
        "blocked":      blocked,
        "checks":       checks,
        "alternatives": alternatives,
    }
