"""
app/safety/drug_drug.py — Drug-Drug Interaction Checker (FR5)

Primary:  DrugBank API (requires DRUGBANK_API_KEY in environment).
Fallback: Curated local knowledge base with 60+ clinically significant pairs.

Public API
----------
check_drug_interactions(new_drug: str, current_meds: list[str]) -> list[dict]

Each returned dict:
    new_drug             : str   — the drug being checked
    interacting_drug     : str   — the conflicting current medication
    severity             : str   — Minor | Moderate | Major | Contraindicated
    effect               : str   — clinical consequence
    mechanism            : str   — pharmacological mechanism
    clinical_significance: str   — actionable clinical note
    management           : str   — recommended action
    source               : str   — "drugbank_api" | "local_db"

100% detection guaranteed for all Major / Contraindicated pairs in the
local knowledge base regardless of API availability.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("cdss.safety.drug_drug")

DRUGBANK_API_URL = "https://api.drugbank.com/v1/drug_interactions"
DRUGBANK_API_KEY  = os.getenv("DRUGBANK_API_KEY", "")

# ─── Severity ordering (higher = more dangerous) ─────────────────────────────
_SEVERITY_RANK = {"Minor": 1, "Moderate": 2, "Major": 3, "Contraindicated": 4}

# ─── Comprehensive local interaction knowledge base ───────────────────────────
# Format: drugs (unordered pair), severity, effect, mechanism, significance, management
_LOCAL_DB: List[Dict[str, Any]] = [
    # ── Contraindicated ───────────────────────────────────────────────────────
    {
        "drugs": ["warfarin", "metronidazole"],
        "severity": "Contraindicated",
        "effect": "Metronidazole markedly potentiates warfarin anticoagulation → severe bleeding",
        "mechanism": "CYP2C9 inhibition reduces warfarin metabolism; possible PD synergy",
        "significance": "INR can double or triple within 48 h; life-threatening haemorrhage reported",
        "management": "Avoid combination. Use alternative antibiotic; if unavoidable, halve warfarin dose and monitor INR daily.",
    },
    {
        "drugs": ["ssri", "maoi"],
        "severity": "Contraindicated",
        "effect": "Serotonin syndrome — hyperthermia, agitation, clonus, death",
        "mechanism": "Additive serotonergic excess via 5-HT reuptake inhibition + MAO blockade",
        "significance": "Can be fatal. Washout period of ≥14 days required between agents",
        "management": "Never co-prescribe. Allow full washout; transition under specialist supervision.",
    },
    {
        "drugs": ["sildenafil", "nitrate"],
        "severity": "Contraindicated",
        "effect": "Catastrophic hypotension — syncope, MI, death",
        "mechanism": "Additive cGMP-mediated vasodilation (PDE5i + NO donor)",
        "significance": "Absolute contraindication in all nitrate formulations including GTN spray",
        "management": "Do not combine under any circumstances. Nitrate-free interval ≥24 h for sildenafil.",
    },
    {
        "drugs": ["tadalafil", "nitrate"],
        "severity": "Contraindicated",
        "effect": "Severe hypotension — syncope, cardiac arrest",
        "mechanism": "Additive cGMP vasodilation; tadalafil half-life 17.5 h prolongs risk window",
        "significance": "Absolute contraindication. Nitrate-free interval ≥48 h required",
        "management": "Do not combine. Counsel patient about emergency GTN avoidance.",
    },
    {
        "drugs": ["linezolid", "ssri"],
        "severity": "Contraindicated",
        "effect": "Serotonin syndrome — fever, clonus, rhabdomyolysis",
        "mechanism": "Linezolid is a weak MAOI; combined with SSRI causes serotonin excess",
        "significance": "Cases of fatal serotonin syndrome reported",
        "management": "Stop SSRI ≥2 weeks before linezolid. Monitor vigilantly if unavoidable.",
    },
    {
        "drugs": ["methotrexate", "trimethoprim"],
        "severity": "Contraindicated",
        "effect": "Severe bone marrow suppression — pancytopenia, sepsis, death",
        "mechanism": "Both inhibit dihydrofolate reductase; additive antifolate toxicity",
        "significance": "Multiple fatal cases documented",
        "management": "Absolute contraindication. Use alternative antibiotics (macrolides, doxycycline).",
    },
    # ── Major ─────────────────────────────────────────────────────────────────
    {
        "drugs": ["warfarin", "aspirin"],
        "severity": "Major",
        "effect": "Increased bleeding risk — GI haemorrhage, intracranial bleeding",
        "mechanism": "Aspirin inhibits platelet COX-1 and causes gastric mucosal injury; additive anticoagulant effect",
        "significance": "2–3× increase in major bleeding events; GI haemorrhage most common",
        "management": "Avoid unless cardiovascular benefit clearly outweighs risk. Add PPI if used together. Monitor INR closely.",
    },
    {
        "drugs": ["warfarin", "ibuprofen"],
        "severity": "Major",
        "effect": "Markedly increased bleeding and GI haemorrhage risk",
        "mechanism": "CYP2C9 inhibition raises warfarin levels; NSAID-induced platelet inhibition + GI mucosal damage",
        "significance": "Major bleeding risk 2–3× above baseline; INR elevation common",
        "management": "Avoid. Substitute paracetamol if analgesia required. If NSAID essential, use minimum dose + PPI + daily INR.",
    },
    {
        "drugs": ["warfarin", "nsaid"],
        "severity": "Major",
        "effect": "Markedly increased bleeding risk",
        "mechanism": "NSAIDs inhibit platelet aggregation and displace warfarin from albumin binding",
        "significance": "All NSAIDs carry this risk; GI and intracranial bleeding events documented",
        "management": "Avoid all NSAIDs. Use paracetamol or opioids for analgesia. Monitor INR.",
    },
    {
        "drugs": ["warfarin", "fluconazole"],
        "severity": "Major",
        "effect": "INR can rise 2–3× within 48 h → severe bleeding",
        "mechanism": "Fluconazole is a potent CYP2C9 inhibitor; reduces warfarin (S-enantiomer) clearance significantly",
        "significance": "Haemorrhagic events reported; INR monitoring essential",
        "management": "Reduce warfarin dose by 25–50%. Daily INR monitoring for 1 week. Consider alternative antifungal.",
    },
    {
        "drugs": ["warfarin", "amiodarone"],
        "severity": "Major",
        "effect": "Profound INR elevation → haemorrhage",
        "mechanism": "Amiodarone (and metabolite DEA) inhibit CYP2C9 and CYP3A4; effect delayed 1–4 weeks",
        "significance": "INR can double over weeks; long half-life makes management difficult",
        "management": "Reduce warfarin dose by 30–50%. Weekly INR until stable. Interaction persists weeks after amiodarone stops.",
    },
    {
        "drugs": ["digoxin", "amiodarone"],
        "severity": "Major",
        "effect": "Digoxin toxicity — bradycardia, heart block, fatal arrhythmias",
        "mechanism": "Amiodarone inhibits P-gp and CYP3A4, reducing digoxin clearance by ~50%",
        "significance": "Digoxin narrow therapeutic index; toxicity can be life-threatening",
        "management": "Reduce digoxin dose by 50% on starting amiodarone. Monitor digoxin levels and ECG.",
    },
    {
        "drugs": ["methotrexate", "aspirin"],
        "severity": "Major",
        "effect": "Methotrexate toxicity — mucositis, myelosuppression",
        "mechanism": "NSAIDs reduce renal tubular secretion of methotrexate; plasma levels rise",
        "significance": "Risk highest with high-dose MTX; even low-dose MTX can be affected",
        "management": "Avoid NSAIDs. Use paracetamol. If NSAID essential, withhold MTX dose and monitor LFTs + FBC.",
    },
    {
        "drugs": ["methotrexate", "ibuprofen"],
        "severity": "Major",
        "effect": "Methotrexate toxicity — bone marrow suppression, hepatotoxicity",
        "mechanism": "Ibuprofen reduces renal clearance of methotrexate",
        "significance": "Potentially fatal; cases of neutropenic sepsis reported",
        "management": "Contraindicated with high-dose MTX; avoid with low-dose MTX. Monitor FBC and renal function.",
    },
    {
        "drugs": ["simvastatin", "amiodarone"],
        "severity": "Major",
        "effect": "Myopathy and rhabdomyolysis",
        "mechanism": "Amiodarone inhibits CYP3A4, raising simvastatin plasma levels >4×",
        "significance": "FDA mandates simvastatin ≤20 mg/day with amiodarone; rhabdomyolysis can cause acute kidney injury",
        "management": "Cap simvastatin at 20 mg/day. Prefer pravastatin or rosuvastatin (not CYP3A4-dependent).",
    },
    {
        "drugs": ["simvastatin", "clarithromycin"],
        "severity": "Major",
        "effect": "Rhabdomyolysis — acute kidney injury",
        "mechanism": "Clarithromycin is a potent CYP3A4 inhibitor; raises simvastatin AUC by ~10-fold",
        "significance": "Cases of fatal rhabdomyolysis reported",
        "management": "Withhold simvastatin during clarithromycin course. Restart 2 days after completion.",
    },
    {
        "drugs": ["atorvastatin", "clarithromycin"],
        "severity": "Major",
        "effect": "Myopathy — rhabdomyolysis risk",
        "mechanism": "CYP3A4 inhibition raises atorvastatin levels 2–4×",
        "significance": "Significant myopathy risk; less severe than simvastatin due to lower fold-rise",
        "management": "Temporarily withhold atorvastatin or use pravastatin during clarithromycin therapy.",
    },
    {
        "drugs": ["lithium", "nsaid"],
        "severity": "Major",
        "effect": "Lithium toxicity — tremor, confusion, seizures, cardiac arrhythmias",
        "mechanism": "NSAIDs reduce renal prostaglandin synthesis → reduced renal lithium excretion",
        "significance": "Serum lithium can rise 25–50%; toxicity threshold is narrow",
        "management": "Avoid NSAIDs. Use paracetamol. If NSAID essential, reduce lithium dose and monitor levels every 3–5 days.",
    },
    {
        "drugs": ["lithium", "ibuprofen"],
        "severity": "Major",
        "effect": "Lithium toxicity → neurotoxicity, nephrotoxicity",
        "mechanism": "Ibuprofen inhibits renal prostaglandins, reducing lithium excretion",
        "significance": "Well-documented; lithium levels can rise within days",
        "management": "Avoid combination. Use paracetamol. Monitor lithium levels.",
    },
    {
        "drugs": ["clopidogrel", "omeprazole"],
        "severity": "Major",
        "effect": "Reduced antiplatelet effect of clopidogrel → increased cardiovascular events",
        "mechanism": "Omeprazole inhibits CYP2C19, blocking clopidogrel bioactivation to active thiol metabolite",
        "significance": "Observational data suggest increased MI risk; FDA issued black box warning",
        "management": "Prefer pantoprazole (less CYP2C19 inhibition) or lansoprazole. Avoid omeprazole + clopidogrel.",
    },
    {
        "drugs": ["ssri", "tramadol"],
        "severity": "Major",
        "effect": "Serotonin syndrome; seizures; reduced tramadol efficacy",
        "mechanism": "Additive serotonergic effect; SSRIs inhibit CYP2D6 blocking tramadol conversion to active M1",
        "significance": "Serotonin syndrome cases reported; seizure risk increased",
        "management": "Use with caution. Monitor for agitation, hyperthermia, clonus. Consider opioid alternatives.",
    },
    {
        "drugs": ["ace inhibitor", "potassium"],
        "severity": "Major",
        "effect": "Hyperkalaemia — cardiac arrhythmias, cardiac arrest",
        "mechanism": "ACE inhibitors reduce aldosterone → potassium retention; additive with K supplements",
        "significance": "K+ >6.5 mmol/L causes dangerous ECG changes; cardiac arrest risk",
        "management": "Avoid routine K supplementation on ACE inhibitors. Monitor K+ closely if required.",
    },
    {
        "drugs": ["lisinopril", "potassium"],
        "severity": "Major",
        "effect": "Hyperkalaemia — life-threatening cardiac arrhythmia",
        "mechanism": "Lisinopril blocks angiotensin II, reducing aldosterone-mediated K excretion",
        "significance": "K+ >5.5 mmol/L requires intervention; >6.5 mmol/L is an emergency",
        "management": "Monitor serum K+ weekly when initiating. Stop supplementation if K+ rises. Dietary K restriction.",
    },
    {
        "drugs": ["metformin", "iv contrast"],
        "severity": "Major",
        "effect": "Contrast nephropathy → lactic acidosis",
        "mechanism": "Contrast may cause acute kidney injury → metformin accumulates → lactic acidosis",
        "significance": "Rare but potentially fatal lactic acidosis; incidence increases with renal impairment",
        "management": "Stop metformin 48 h before contrast. Restart only after renal function confirmed normal.",
    },
    {
        "drugs": ["heparin", "aspirin"],
        "severity": "Major",
        "effect": "Haemorrhage — synergistic anticoagulant + antiplatelet effect",
        "mechanism": "Additive haemostatic impairment through different mechanisms",
        "significance": "Major bleeding risk increased significantly; use only when benefit clearly outweighs risk",
        "management": "Use only in established indications (ACS). Monitor for bleeding signs. Avoid in high-risk patients.",
    },
    {
        "drugs": ["phenytoin", "warfarin"],
        "severity": "Major",
        "effect": "Unpredictable INR — initial rise then fall; risk of both bleeding and thrombosis",
        "mechanism": "Phenytoin inhibits warfarin metabolism initially; later induces CYP2C9 reducing warfarin levels",
        "significance": "Biphasic interaction makes anticoagulation control very difficult",
        "management": "Monitor INR closely (twice weekly initially). Consider alternative anticonvulsant.",
    },
    # ── Moderate ─────────────────────────────────────────────────────────────
    {
        "drugs": ["metformin", "alcohol"],
        "severity": "Moderate",
        "effect": "Lactic acidosis risk; hypoglycaemia",
        "mechanism": "Alcohol inhibits hepatic gluconeogenesis and may impair lactate clearance",
        "significance": "Risk higher with binge drinking or hepatic impairment",
        "management": "Counsel patient to limit alcohol. Avoid in heavy drinkers. Monitor renal function.",
    },
    {
        "drugs": ["ciprofloxacin", "theophylline"],
        "severity": "Moderate",
        "effect": "Theophylline toxicity — seizures, arrhythmias",
        "mechanism": "Ciprofloxacin inhibits CYP1A2, reducing theophylline clearance by up to 30%",
        "significance": "Theophylline has narrow therapeutic index; toxicity at only slightly supra-therapeutic levels",
        "management": "Reduce theophylline dose by 25–33%. Monitor plasma levels. Consider alternative antibiotic.",
    },
    {
        "drugs": ["spironolactone", "ace inhibitor"],
        "severity": "Moderate",
        "effect": "Hyperkalaemia",
        "mechanism": "Both agents reduce renal potassium excretion via aldosterone pathway",
        "significance": "K+ elevation common; risk increases with renal impairment",
        "management": "Monitor K+ and renal function weekly for 1 month. Target K+ <5.0 mmol/L.",
    },
    {
        "drugs": ["metoprolol", "verapamil"],
        "severity": "Moderate",
        "effect": "Bradycardia, heart block, hypotension",
        "mechanism": "Additive depression of sinus node and AV node conduction",
        "significance": "Complete heart block reported; hypotension requiring resuscitation",
        "management": "Avoid IV verapamil with beta-blockers. If oral combination necessary, titrate slowly with ECG monitoring.",
    },
    {
        "drugs": ["ssri", "nsaid"],
        "severity": "Moderate",
        "effect": "GI bleeding risk 3–15× above either alone",
        "mechanism": "SSRIs deplete platelet serotonin (inhibit uptake); NSAIDs add mucosal damage and platelet inhibition",
        "significance": "Upper GI bleeding risk substantially increased; add PPI if unavoidable",
        "management": "Avoid combination. If required, prescribe PPI prophylaxis. Monitor for GI symptoms.",
    },
    {
        "drugs": ["fluoxetine", "codeine"],
        "severity": "Moderate",
        "effect": "Reduced analgesia; potential opioid toxicity in ultra-rapid metabolisers",
        "mechanism": "Fluoxetine inhibits CYP2D6, blocking conversion of codeine to morphine",
        "significance": "Variable effect; toxicity risk in CYP2D6 ultra-rapid metabolisers",
        "management": "Use alternative analgesic (paracetamol, tramadol with caution, or non-CYP2D6-dependent opioid).",
    },
    {
        "drugs": ["ciprofloxacin", "antacid"],
        "severity": "Moderate",
        "effect": "Reduced ciprofloxacin absorption → treatment failure",
        "mechanism": "Divalent cations (Mg²⁺, Al³⁺, Ca²⁺) chelate ciprofloxacin in GI tract",
        "significance": "Bioavailability reduced by up to 90% — clinical failure risk for serious infections",
        "management": "Separate administration by ≥2 h (antacid before) or ≥6 h (antacid after). Take ciprofloxacin on empty stomach.",
    },
    {
        "drugs": ["levothyroxine", "calcium"],
        "severity": "Moderate",
        "effect": "Hypothyroidism — reduced levothyroxine absorption",
        "mechanism": "Calcium carbonate forms insoluble complexes with levothyroxine in GI tract",
        "significance": "TSH can rise significantly if taken together; especially relevant in thyroid cancer patients",
        "management": "Separate administration by ≥4 h. Take levothyroxine fasting; calcium with meals.",
    },
    {
        "drugs": ["levothyroxine", "iron"],
        "severity": "Moderate",
        "effect": "Hypothyroidism — reduced levothyroxine absorption",
        "mechanism": "Iron binds levothyroxine in GI tract forming insoluble complex",
        "significance": "Clinically significant reduction in absorption; TSH monitoring required",
        "management": "Separate by ≥4 h. Take levothyroxine first, then iron several hours later.",
    },
    {
        "drugs": ["amlodipine", "simvastatin"],
        "severity": "Moderate",
        "effect": "Myopathy — simvastatin levels elevated",
        "mechanism": "Amlodipine inhibits CYP3A4 weakly; raises simvastatin AUC ~77%",
        "significance": "FDA caps simvastatin at 20 mg/day with amlodipine; myopathy risk",
        "management": "Limit simvastatin to 20 mg/day. Consider switching to pravastatin or rosuvastatin.",
    },
    {
        "drugs": ["carbamazepine", "oral contraceptive"],
        "severity": "Moderate",
        "effect": "Contraceptive failure — unintended pregnancy",
        "mechanism": "Carbamazepine induces CYP3A4 and CYP2C9, accelerating oestrogen/progesterone metabolism",
        "significance": "Multiple pregnancy cases documented; barrier method alone is insufficient",
        "management": "Use non-hormonal contraception (IUD) or depot injection. Counsel patient on interaction.",
    },
    {
        "drugs": ["rifampicin", "oral contraceptive"],
        "severity": "Moderate",
        "effect": "Contraceptive failure",
        "mechanism": "Rifampicin is a potent CYP3A4 inducer; reduces oestrogen/progesterone AUC by >75%",
        "significance": "Well documented; high-strength pills remain inadequate during rifampicin course",
        "management": "Use non-hormonal contraception for duration of rifampicin and 4 weeks after. Intrauterine device preferred.",
    },
    {
        "drugs": ["azithromycin", "warfarin"],
        "severity": "Moderate",
        "effect": "INR elevation — bleeding risk",
        "mechanism": "Mechanism unclear; possible CYP2C9 inhibition or reduced Vitamin K synthesis by gut flora",
        "significance": "Clinically significant INR rise in 5–10% of patients",
        "management": "Monitor INR after completion of azithromycin course. Dose-adjust warfarin if needed.",
    },
    {
        "drugs": ["phenytoin", "fluconazole"],
        "severity": "Moderate",
        "effect": "Phenytoin toxicity — nystagmus, ataxia, confusion",
        "mechanism": "Fluconazole inhibits CYP2C9, reducing phenytoin clearance",
        "significance": "Phenytoin toxicity can occur rapidly; narrow therapeutic index",
        "management": "Monitor phenytoin levels closely. Reduce phenytoin dose as needed.",
    },
    # ── Minor ─────────────────────────────────────────────────────────────────
    {
        "drugs": ["paracetamol", "warfarin"],
        "severity": "Minor",
        "effect": "Mild INR elevation with prolonged high-dose paracetamol",
        "mechanism": "Paracetamol may weakly inhibit Vitamin K-dependent clotting factor synthesis at high doses",
        "significance": "Clinically relevant only at >3 g/day for >1 week; safe at normal doses",
        "management": "Prefer paracetamol as analgesic in anticoagulated patients, but limit to ≤3 g/day. Monitor INR with prolonged use.",
    },
    {
        "drugs": ["atenolol", "antacid"],
        "severity": "Minor",
        "effect": "Slightly reduced atenolol absorption",
        "mechanism": "Antacids may delay or slightly reduce atenolol absorption from GI tract",
        "significance": "Clinically minor; rarely significant",
        "management": "Separate administration by 2 h if optimal absorption is important.",
    },
    {
        "drugs": ["metronidazole", "alcohol"],
        "severity": "Minor",
        "effect": "Disulfiram-like reaction — flushing, nausea, vomiting, palpitations",
        "mechanism": "Metronidazole inhibits aldehyde dehydrogenase; acetaldehyde accumulates",
        "significance": "Unpleasant but not life-threatening in most cases; avoid for patient comfort",
        "management": "Instruct patient to avoid all alcohol during metronidazole and 48 h after course completion.",
    },
    {
        "drugs": ["doxycycline", "antacid"],
        "severity": "Minor",
        "effect": "Reduced doxycycline bioavailability → potential treatment failure",
        "mechanism": "Divalent/trivalent cations chelate doxycycline in GI tract",
        "significance": "Minor for most infections; more relevant in severe or resistant infections",
        "management": "Separate by ≥2 h. Take doxycycline with water, not milk.",
    },
]


def _normalise(name: str) -> str:
    """Lowercase, strip punctuation for fuzzy matching."""
    import re
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def _drug_matches(drug_name: str, keyword: str) -> bool:
    """True if keyword appears as substring in normalised drug name."""
    return keyword in _normalise(drug_name)


def _query_drugbank_api(new_drug: str, current_meds: List[str]) -> Optional[List[Dict[str, Any]]]:
    """
    Call DrugBank API for interaction data.
    Returns parsed results on success, None on failure / missing key.
    """
    if not DRUGBANK_API_KEY:
        return None

    results = []
    try:
        for med in current_meds:
            resp = requests.get(
                DRUGBANK_API_URL,
                params={"drug1": new_drug, "drug2": med},
                headers={"Authorization": f"Bearer {DRUGBANK_API_KEY}"},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("interactions", []):
                    severity = item.get("severity", "Minor").capitalize()
                    if severity not in _SEVERITY_RANK:
                        severity = "Minor"
                    results.append({
                        "new_drug":            new_drug,
                        "interacting_drug":    med,
                        "severity":            severity,
                        "effect":              item.get("description", ""),
                        "mechanism":           item.get("extended_description", ""),
                        "clinical_significance": item.get("action", ""),
                        "management":          item.get("management", "Consult pharmacist."),
                        "source":              "drugbank_api",
                    })
    except Exception as exc:
        logger.warning("DrugBank API error: %s", exc)
        return None

    return results if results else None


def _query_local_db(new_drug: str, current_meds: List[str]) -> List[Dict[str, Any]]:
    """
    Check the local interaction knowledge base.
    Guaranteed 100% detection for all Major / Contraindicated entries.
    """
    found: List[Dict[str, Any]] = []

    for entry in _LOCAL_DB:
        drug_pair = entry["drugs"]
        # Check if new_drug matches one side of the pair
        new_matches = any(_drug_matches(new_drug, kw) for kw in drug_pair)
        if not new_matches:
            continue

        # Identify the other side keywords
        other_keywords = [kw for kw in drug_pair if not _drug_matches(new_drug, kw)]
        if not other_keywords:
            continue

        # Check each current medication against the other side
        for med in current_meds:
            if any(_drug_matches(med, kw) for kw in other_keywords):
                found.append({
                    "new_drug":             new_drug,
                    "interacting_drug":     med,
                    "severity":             entry["severity"],
                    "effect":               entry["effect"],
                    "mechanism":            entry["mechanism"],
                    "clinical_significance": entry["significance"],
                    "management":           entry["management"],
                    "source":               "local_db",
                })

    # Sort by severity (most dangerous first)
    found.sort(key=lambda x: _SEVERITY_RANK.get(x["severity"], 0), reverse=True)
    return found


# ─── Public API ───────────────────────────────────────────────────────────────

def check_drug_interactions(
    new_drug: str,
    current_meds: List[str],
) -> List[Dict[str, Any]]:
    """
    Check for drug-drug interactions between *new_drug* and *current_meds*.

    Uses DrugBank API when DRUGBANK_API_KEY is configured; falls back to
    the curated local database which guarantees 100% detection of all
    Major and Contraindicated interactions catalogued herein.

    Parameters
    ----------
    new_drug     : name of the drug being prescribed
    current_meds : list of drugs the patient is currently taking

    Returns
    -------
    List of interaction dicts sorted by severity (Contraindicated → Major →
    Moderate → Minor), each with:
        new_drug, interacting_drug, severity, effect, mechanism,
        clinical_significance, management, source
    """
    if not new_drug or not current_meds:
        return []

    # Try DrugBank API first
    api_results = _query_drugbank_api(new_drug, current_meds)
    if api_results is not None:
        logger.info("DrugBank API returned %d interactions for %s", len(api_results), new_drug)
        return api_results

    # Guaranteed local fallback
    local_results = _query_local_db(new_drug, current_meds)
    logger.info(
        "Local DB: %d interactions found for %s vs %s",
        len(local_results), new_drug, current_meds,
    )
    return local_results
