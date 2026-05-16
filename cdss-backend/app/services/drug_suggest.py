"""
Evidence-based drug suggestion service.

Maps confirmed diagnoses / presenting symptoms to first-line, second-line,
and adjunct medications using a curated clinical reference table.

This is a RULE-BASED engine — no LLM is used for drug names to ensure accuracy.
Sources: WHO Essential Medicines List, NICE guidelines, UpToDate, BNF.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# ─── Clinical drug database ──────────────────────────────────────────────────
# Each entry:
#   name          : generic INN name + strength
#   class         : pharmacological class
#   indication    : primary indication
#   dose          : typical adult dose
#   frequency     : dosing frequency
#   duration      : typical course duration
#   route         : administration route
#   contraindications : list of absolute contraindications
#   interactions  : major drug interactions to warn about
#   notes         : patient counselling / monitoring notes
#   line          : "first" | "second" | "adjunct"

_DRUG_CATALOG: List[Dict[str, Any]] = [
    # ── Antipyretics / Analgesics ─────────────────────────────────────────────
    {
        "id": "D-PAR500", "name": "Paracetamol 500mg", "class": "Analgesic / Antipyretic",
        "indication": "Fever, Mild–moderate pain", "dose": "500–1000mg", "frequency": "Every 4–6 hours",
        "duration": "As needed (max 5 days for fever)", "route": "Oral",
        "max_daily": "4000mg/day",
        "contraindications": ["Severe hepatic impairment", "Paracetamol hypersensitivity"],
        "interactions": ["Warfarin (high doses)", "Alcohol"],
        "notes": "Do not exceed 4 g/day. Check other products for hidden paracetamol. Avoid alcohol.",
        "line": "first",
        "tags": ["fever", "pain", "headache", "viral", "urti", "flu", "influenza"],
    },
    {
        "id": "D-IBU400", "name": "Ibuprofen 400mg", "class": "NSAID / Antipyretic",
        "indication": "Fever, Inflammation, Mild–moderate pain", "dose": "400mg", "frequency": "Every 6–8 hours",
        "duration": "Up to 5 days", "route": "Oral",
        "contraindications": ["Peptic ulcer", "Renal impairment", "Aspirin/NSAID allergy", "Third trimester pregnancy"],
        "interactions": ["Warfarin", "ACE inhibitors", "Diuretics", "Aspirin"],
        "notes": "Take with food. Avoid in renal impairment. Do not combine with other NSAIDs.",
        "line": "first",
        "tags": ["fever", "pain", "inflammation", "viral", "urti", "flu"],
    },
    # ── Antibiotics ────────────────────────────────────────────────────────────
    {
        "id": "D-AMX500", "name": "Amoxicillin 500mg", "class": "Penicillin Antibiotic",
        "indication": "Bacterial sinusitis, Strep pharyngitis, Mild pneumonia, UTI", "dose": "500mg",
        "frequency": "Three times daily", "duration": "7–10 days", "route": "Oral",
        "contraindications": ["Penicillin allergy", "Beta-lactam allergy"],
        "interactions": ["Warfarin", "Methotrexate", "Oral contraceptives"],
        "notes": "Complete the full course. Take with or without food.",
        "line": "first",
        "tags": ["bacterial", "sinusitis", "pharyngitis", "uti", "pneumonia", "otitis"],
    },
    {
        "id": "D-AZI500", "name": "Azithromycin 500mg", "class": "Macrolide Antibiotic",
        "indication": "Community-acquired pneumonia, Atypical pneumonia, Bacterial sinusitis (penicillin-allergic)",
        "dose": "500mg day 1, then 250mg", "frequency": "Once daily", "duration": "5 days", "route": "Oral",
        "contraindications": ["Liver disease", "QT prolongation", "Azithromycin hypersensitivity"],
        "interactions": ["Warfarin", "QT-prolonging drugs", "Antacids (separate by 2h)"],
        "notes": "Complete full 5-day course. Report palpitations. Avoid antacids within 2 hours.",
        "line": "second",
        "tags": ["bacterial", "pneumonia", "sinusitis", "atypical", "penicillin allergy"],
    },
    {
        "id": "D-CEF250", "name": "Cefuroxime 250mg", "class": "2nd-gen Cephalosporin",
        "indication": "Respiratory tract infections, UTI, Otitis media", "dose": "250–500mg",
        "frequency": "Twice daily", "duration": "7 days", "route": "Oral",
        "contraindications": ["Cephalosporin allergy", "Severe penicillin allergy (cross-reactivity ~1%)"],
        "interactions": ["Warfarin", "Probenecid"],
        "notes": "Take with food to improve absorption. Complete full course.",
        "line": "second",
        "tags": ["bacterial", "respiratory", "uti", "otitis", "bronchitis"],
    },
    {
        "id": "D-DOX100", "name": "Doxycycline 100mg", "class": "Tetracycline Antibiotic",
        "indication": "Atypical pneumonia, Chlamydia, Malaria prophylaxis, Lyme disease", "dose": "100mg",
        "frequency": "Twice daily", "duration": "7–14 days", "route": "Oral",
        "contraindications": ["Pregnancy", "Children < 8 years", "Tetracycline hypersensitivity"],
        "interactions": ["Antacids", "Iron", "Calcium", "Warfarin"],
        "notes": "Take with plenty of water. Avoid lying down for 30 min after. Avoid sun exposure (photosensitivity).",
        "line": "second",
        "tags": ["atypical", "pneumonia", "chlamydia", "lyme", "bacterial"],
    },
    {
        "id": "D-CIP500", "name": "Ciprofloxacin 500mg", "class": "Fluoroquinolone",
        "indication": "UTI (complicated), Pyelonephritis, GI infections", "dose": "500mg",
        "frequency": "Twice daily", "duration": "7–14 days", "route": "Oral",
        "contraindications": ["Tendon disease", "QT prolongation", "Children (avoid)", "Epilepsy"],
        "interactions": ["Antacids (separate 2h)", "Warfarin", "QT-prolonging drugs", "Theophylline"],
        "notes": "Drink 2–3 L water/day. Avoid sun exposure. Report tendon pain immediately.",
        "line": "second",
        "tags": ["uti", "pyelonephritis", "gi infection", "bacterial"],
    },
    # ── Diabetes ───────────────────────────────────────────────────────────────
    {
        "id": "D-MET500", "name": "Metformin 500mg", "class": "Biguanide",
        "indication": "Type 2 Diabetes Mellitus", "dose": "500mg (titrate to 1000mg twice daily)",
        "frequency": "Twice daily with meals", "duration": "Long-term / Ongoing", "route": "Oral",
        "contraindications": ["eGFR < 30 mL/min", "Hepatic impairment", "Contrast media use (hold 48h)", "Alcoholism"],
        "interactions": ["Alcohol", "Iodinated contrast agents", "Carbonic anhydrase inhibitors"],
        "notes": "Take with meals to reduce GI side effects. Monitor eGFR and B12 annually. Avoid alcohol.",
        "line": "first",
        "tags": ["diabetes", "type 2 diabetes", "hyperglycaemia", "t2dm"],
    },
    {
        "id": "D-EMP10", "name": "Empagliflozin 10mg", "class": "SGLT2 Inhibitor",
        "indication": "Type 2 Diabetes, Heart failure (HFrEF), CKD", "dose": "10mg",
        "frequency": "Once daily", "duration": "Long-term", "route": "Oral",
        "contraindications": ["eGFR < 20", "DKA", "Recurrent UTI / genital infections"],
        "interactions": ["Diuretics (additive hypotension)", "Insulin (adjust dose)"],
        "notes": "Hold before surgery or prolonged fasting. Monitor for genital infections. Adequate hydration required.",
        "line": "second",
        "tags": ["diabetes", "type 2 diabetes", "heart failure", "ckd", "t2dm"],
    },
    {
        "id": "D-GLI5", "name": "Glipizide 5mg", "class": "Sulfonylurea",
        "indication": "Type 2 Diabetes (when Metformin insufficient)", "dose": "5mg",
        "frequency": "Once daily before breakfast", "duration": "Long-term", "route": "Oral",
        "contraindications": ["Type 1 Diabetes", "DKA", "Sulfonamide allergy", "Hepatic/renal impairment"],
        "interactions": ["Alcohol", "NSAIDs", "Warfarin", "Beta-blockers (mask hypoglycaemia)"],
        "notes": "Risk of hypoglycaemia — carry glucose tablets. Do not skip meals.",
        "line": "second",
        "tags": ["diabetes", "type 2 diabetes", "t2dm"],
    },
    # ── Hypertension / Cardiovascular ────────────────────────────────────────
    {
        "id": "D-LIS10", "name": "Lisinopril 10mg", "class": "ACE Inhibitor",
        "indication": "Hypertension, Heart failure, Diabetic nephropathy", "dose": "10mg (titrate to 20–40mg)",
        "frequency": "Once daily", "duration": "Long-term", "route": "Oral",
        "contraindications": ["Pregnancy", "Bilateral renal artery stenosis", "Angioedema history", "Hyperkalaemia"],
        "interactions": ["NSAIDs (reduce effect + nephrotoxicity)", "Potassium supplements", "ARBs"],
        "notes": "Monitor potassium and creatinine. Persistent dry cough is common — switch to ARB if intolerable.",
        "line": "first",
        "tags": ["hypertension", "heart failure", "diabetic nephropathy", "ckd"],
    },
    {
        "id": "D-AML5", "name": "Amlodipine 5mg", "class": "Calcium Channel Blocker (CCB)",
        "indication": "Hypertension, Stable angina", "dose": "5mg (up to 10mg)",
        "frequency": "Once daily", "duration": "Long-term", "route": "Oral",
        "contraindications": ["Cardiogenic shock", "Severe aortic stenosis"],
        "interactions": ["Simvastatin (limit simva to 20mg)", "Grapefruit juice", "CYP3A4 inhibitors"],
        "notes": "May cause ankle oedema. Avoid grapefruit juice. Take at same time daily.",
        "line": "first",
        "tags": ["hypertension", "angina", "cardiovascular"],
    },
    {
        "id": "D-ATE50", "name": "Atenolol 50mg", "class": "Beta-1 Blocker",
        "indication": "Hypertension, Angina, Heart failure (HR control)", "dose": "50mg",
        "frequency": "Once daily", "duration": "Long-term", "route": "Oral",
        "contraindications": ["Asthma / reactive airway disease", "Second/third degree heart block", "Bradycardia", "Cardiogenic shock"],
        "interactions": ["Verapamil/Diltiazem (bradycardia)", "Insulin (masks hypoglycaemia)", "NSAIDs"],
        "notes": "Do not stop abruptly — taper over 2 weeks. Monitor heart rate and blood pressure.",
        "line": "second",
        "tags": ["hypertension", "angina", "heart failure", "tachycardia"],
    },
    {
        "id": "D-ASP81", "name": "Aspirin 81mg", "class": "Antiplatelet / NSAID",
        "indication": "CVD secondary prevention, ACS, Post-MI", "dose": "81mg",
        "frequency": "Once daily", "duration": "Long-term", "route": "Oral",
        "contraindications": ["Active peptic ulcer", "Aspirin / NSAID allergy", "Children with viral illness (Reye's syndrome)"],
        "interactions": ["Warfarin", "Other NSAIDs", "Clopidogrel (increases bleeding risk)"],
        "notes": "Take with food to protect stomach. Do not use for fever in children.",
        "line": "adjunct",
        "tags": ["cvd prevention", "acs", "myocardial infarction", "angina", "stroke prevention"],
    },
    # ── Heart Failure ──────────────────────────────────────────────────────────
    {
        "id": "D-FUR40", "name": "Furosemide 40mg", "class": "Loop Diuretic",
        "indication": "Heart failure (fluid overload), Oedema, Hypertension", "dose": "40mg",
        "frequency": "Once daily (morning)", "duration": "Long-term", "route": "Oral",
        "contraindications": ["Anuria", "Sulfonamide allergy", "Severe electrolyte depletion"],
        "interactions": ["NSAIDs (reduce diuretic effect)", "Aminoglycosides (ototoxicity)", "ACE inhibitors (first-dose hypotension)"],
        "notes": "Weigh daily — report gain >2 kg in 2 days. Monitor potassium — may need supplement.",
        "line": "first",
        "tags": ["heart failure", "oedema", "fluid overload", "hypertension"],
    },
    {
        "id": "D-SPR25", "name": "Spironolactone 25mg", "class": "Mineralocorticoid Antagonist (K⁺-sparing diuretic)",
        "indication": "Heart failure (HFrEF), Hyperaldosteronism, Resistant hypertension", "dose": "25mg",
        "frequency": "Once daily", "duration": "Long-term", "route": "Oral",
        "contraindications": ["Hyperkalaemia (K+ >5.0)", "eGFR < 30", "Addison's disease"],
        "interactions": ["ACE inhibitors / ARBs (hyperkalaemia risk)", "NSAIDs", "Potassium supplements"],
        "notes": "Monitor potassium and renal function. Avoid salt substitutes (contain KCl). Gynaecomastia may occur.",
        "line": "second",
        "tags": ["heart failure", "oedema", "hypertension"],
    },
    # ── Lipid-lowering ────────────────────────────────────────────────────────
    {
        "id": "D-ATO20", "name": "Atorvastatin 20mg", "class": "HMG-CoA Reductase Inhibitor (Statin)",
        "indication": "Hyperlipidaemia, CVD prevention, Diabetic patients", "dose": "20mg",
        "frequency": "Once daily (evening)", "duration": "Long-term", "route": "Oral",
        "contraindications": ["Active liver disease", "Pregnancy / Breastfeeding", "Unexplained raised ALT"],
        "interactions": ["Grapefruit juice (large amounts)", "Cyclosporine", "Fibrates (myopathy risk)", "Erythromycin"],
        "notes": "Avoid grapefruit juice. Report muscle pain immediately (rhabdomyolysis risk). Monitor LFTs at baseline.",
        "line": "first",
        "tags": ["hyperlipidaemia", "dyslipidaemia", "cvd prevention", "diabetes", "hypertension"],
    },
    # ── Thyroid ───────────────────────────────────────────────────────────────
    {
        "id": "D-LEV50", "name": "Levothyroxine 50mcg", "class": "Thyroid Hormone Replacement",
        "indication": "Hypothyroidism", "dose": "25–50mcg (titrate by TSH)",
        "frequency": "Once daily on empty stomach", "duration": "Long-term", "route": "Oral",
        "contraindications": ["Thyrotoxicosis", "Untreated adrenal insufficiency", "Acute MI"],
        "interactions": ["Calcium / Iron / Antacids (separate by 4h)", "Warfarin (potentiates)", "Cholestyramine"],
        "notes": "Take 30–60 min before breakfast. Separate calcium/iron by 4 hours. Monitor TSH every 6–12 months.",
        "line": "first",
        "tags": ["hypothyroidism", "thyroid"],
    },
    # ── Respiratory / Asthma / COPD ──────────────────────────────────────────
    {
        "id": "D-SAL100", "name": "Salbutamol 100mcg inhaler", "class": "Short-acting Beta-2 Agonist (SABA)",
        "indication": "Asthma (reliever), COPD (reliever)", "dose": "1–2 puffs (100–200mcg)",
        "frequency": "As needed (max 8 puffs/day)", "duration": "Ongoing (PRN)", "route": "Inhaled",
        "contraindications": ["Hypersensitivity to salbutamol"],
        "interactions": ["Beta-blockers (antagonise bronchodilation)", "Diuretics (hypokalaemia risk)"],
        "notes": "Shake well. Rinse mouth after use. If using >3 times/week, review preventer therapy.",
        "line": "first",
        "tags": ["asthma", "copd", "bronchospasm", "wheeze", "shortness of breath"],
    },
    {
        "id": "D-FLU100", "name": "Fluticasone 100mcg inhaler", "class": "Inhaled Corticosteroid (ICS)",
        "indication": "Asthma (preventer), Eosinophilic airway inflammation", "dose": "100–500mcg",
        "frequency": "Twice daily", "duration": "Long-term", "route": "Inhaled",
        "contraindications": ["Active pulmonary TB", "Untreated fungal infection"],
        "interactions": ["Ritonavir / Cobicistat (systemic steroid effect)"],
        "notes": "Rinse mouth and gargle after EVERY use (prevents oral candidiasis). Does not treat acute attacks.",
        "line": "first",
        "tags": ["asthma", "copd", "eosinophilic"],
    },
    # ── Gastro ────────────────────────────────────────────────────────────────
    {
        "id": "D-OMP20", "name": "Omeprazole 20mg", "class": "Proton Pump Inhibitor (PPI)",
        "indication": "GERD, Peptic ulcer disease, H. pylori eradication (with antibiotics)", "dose": "20mg",
        "frequency": "Once daily before breakfast", "duration": "4–8 weeks (ulcer), long-term (GERD)", "route": "Oral",
        "contraindications": ["Hypersensitivity to PPIs"],
        "interactions": ["Clopidogrel (reduce antiplatelet effect — avoid co-prescription)", "Methotrexate", "Atazanavir"],
        "notes": "Take 30 min before meals. Long-term use: monitor Mg²⁺, B12, and bone density.",
        "line": "first",
        "tags": ["gerd", "reflux", "peptic ulcer", "gastritis", "h. pylori"],
    },
    {
        "id": "D-MET10D", "name": "Metoclopramide 10mg", "class": "Prokinetic / Antiemetic",
        "indication": "Nausea, Vomiting, Gastroparesis", "dose": "10mg",
        "frequency": "Three times daily before meals", "duration": "5 days maximum", "route": "Oral",
        "contraindications": ["GI obstruction", "Parkinson's disease", "Children < 1 year"],
        "interactions": ["Opioids (compete for GI motility)", "Anticholinergics"],
        "notes": "Short-term use only (max 5 days). Risk of tardive dyskinesia with long-term use.",
        "line": "first",
        "tags": ["nausea", "vomiting", "gastroparesis", "gastroenteritis"],
    },
    # ── Renal / Electrolytes ──────────────────────────────────────────────────
    {
        "id": "D-BIC500", "name": "Sodium Bicarbonate 500mg", "class": "Alkalinising Agent",
        "indication": "Metabolic acidosis in CKD, Prevention of contrast nephropathy", "dose": "500mg",
        "frequency": "Three times daily", "duration": "Long-term (CKD)", "route": "Oral",
        "contraindications": ["Metabolic alkalosis", "Hypernatraemia", "Oedema"],
        "interactions": ["Tetracyclines", "Quinolones (reduced absorption)"],
        "notes": "Separate from other medications by 2 hours. Monitor serum bicarbonate levels.",
        "line": "adjunct",
        "tags": ["ckd", "metabolic acidosis", "kidney disease"],
    },
    # ── Psychiatric / Neurological ────────────────────────────────────────────
    {
        "id": "D-SER50", "name": "Sertraline 50mg", "class": "SSRI Antidepressant",
        "indication": "Depression, Anxiety disorders, PTSD, OCD", "dose": "50mg (up to 200mg)",
        "frequency": "Once daily (morning or night)", "duration": "At least 6–12 months", "route": "Oral",
        "contraindications": ["MAOIs within 14 days", "Pimozide", "Serotonin syndrome risk"],
        "interactions": ["MAOIs", "Tramadol (serotonin syndrome)", "Warfarin (increase INR)"],
        "notes": "Allow 4–6 weeks for full therapeutic effect. Do not stop abruptly — taper. May worsen suicidal ideation initially.",
        "line": "first",
        "tags": ["depression", "anxiety", "ptsd", "ocd", "psychiatric"],
    },
    # ── Anticoagulation ───────────────────────────────────────────────────────
    {
        "id": "D-WAR5", "name": "Warfarin 5mg", "class": "Vitamin K Antagonist (VKA)",
        "indication": "Atrial fibrillation (stroke prevention), DVT / PE treatment, Mechanical heart valves", "dose": "Individualised by INR",
        "frequency": "Once daily (same time)", "duration": "Long-term (AF/valves) or 3–6 months (DVT/PE)", "route": "Oral",
        "contraindications": ["Active bleeding", "Severe hepatic impairment", "Pregnancy (except mechanical valves)"],
        "interactions": ["Many — especially: Aspirin, NSAIDs, Amiodarone, Fluconazole, Antibiotics, Vitamin K foods"],
        "notes": "INR target 2.0–3.0 (or 2.5–3.5 for mechanical valves). Consistent vitamin K intake. Regular INR monitoring.",
        "line": "first",
        "tags": ["atrial fibrillation", "dvt", "pulmonary embolism", "stroke prevention"],
    },
    # ── Iron / Haematinics ────────────────────────────────────────────────────
    {
        "id": "D-IRO200", "name": "Ferrous Sulphate 200mg", "class": "Iron Supplement",
        "indication": "Iron deficiency anaemia", "dose": "200mg",
        "frequency": "Once to twice daily on empty stomach", "duration": "3–6 months", "route": "Oral",
        "contraindications": ["Haemochromatosis", "Haemolytic anaemia", "Regular blood transfusions"],
        "interactions": ["Tetracyclines / Quinolones (separate by 2h)", "Calcium / Antacids (separate by 2h)", "Levothyroxine (separate by 4h)"],
        "notes": "Take on empty stomach for best absorption. Vitamin C enhances absorption. Dark stools expected.",
        "line": "first",
        "tags": ["anaemia", "iron deficiency", "anemia", "iron deficiency anaemia"],
    },
    # ── Gout ─────────────────────────────────────────────────────────────────
    {
        "id": "D-ALL300", "name": "Allopurinol 300mg", "class": "Xanthine Oxidase Inhibitor",
        "indication": "Gout prophylaxis, Hyperuricaemia", "dose": "100–300mg",
        "frequency": "Once daily", "duration": "Long-term", "route": "Oral",
        "contraindications": ["Acute gout attack (do not start during attack)", "Hypersensitivity"],
        "interactions": ["Azathioprine / Mercaptopurine (fatal — DO NOT combine)", "Warfarin", "Ampicillin (rash)"],
        "notes": "Do not start during acute attack — wait 2–4 weeks. Drink 2–3 L water/day to prevent kidney stones.",
        "line": "first",
        "tags": ["gout", "hyperuricaemia", "uric acid"],
    },
]

# ─── Diagnosis → drug mapping ─────────────────────────────────────────────────
# Maps lowercase diagnosis/symptom keywords to drug IDs (ordered: first-line first)

_DX_TO_DRUGS: List[Dict[str, Any]] = [
    {"keywords": ["fever", "pyrexia", "hyperthermia"],
     "drugs": ["D-PAR500", "D-IBU400"],
     "rationale": "Antipyretics are first-line for fever. Use Paracetamol preferentially; add Ibuprofen if needed and not contraindicated."},

    {"keywords": ["viral", "urti", "upper respiratory", "common cold", "flu", "influenza", "rhinitis"],
     "drugs": ["D-PAR500", "D-IBU400"],
     "rationale": "Viral URTI is self-limiting. Antibiotics are NOT indicated. Symptomatic relief with antipyretics."},

    {"keywords": ["bacterial sinusitis", "sinusitis", "sinus infection"],
     "drugs": ["D-AMX500", "D-AZI500", "D-CEF250"],
     "rationale": "Bacterial sinusitis: Amoxicillin first-line. Azithromycin for penicillin-allergic patients."},

    {"keywords": ["pneumonia", "community-acquired pneumonia", "cap", "chest infection"],
     "drugs": ["D-AMX500", "D-AZI500", "D-CEF250", "D-DOX100"],
     "rationale": "CAP: Amoxicillin first-line for mild-moderate; add Azithromycin for atypical coverage."},

    {"keywords": ["urinary tract infection", "uti", "cystitis", "dysuria"],
     "drugs": ["D-CEF250", "D-CIP500", "D-AMX500"],
     "rationale": "Uncomplicated UTI: Cefuroxime or Ciprofloxacin. Amoxicillin only if susceptibility confirmed."},

    {"keywords": ["pharyngitis", "tonsillitis", "strep throat", "sore throat"],
     "drugs": ["D-AMX500", "D-AZI500"],
     "rationale": "Group A Strep pharyngitis: Amoxicillin first-line. Azithromycin if penicillin-allergic."},

    {"keywords": ["type 2 diabetes", "diabetes mellitus", "diabetes", "t2dm", "hyperglycaemia"],
     "drugs": ["D-MET500", "D-EMP10", "D-GLI5", "D-ATO20"],
     "rationale": "T2DM: Metformin first-line (unless contraindicated). SGLT2i add-on for CV/renal benefit. Statin for CV risk reduction."},

    {"keywords": ["hypertension", "high blood pressure", "essential hypertension"],
     "drugs": ["D-LIS10", "D-AML5", "D-ATE50", "D-FUR40", "D-ATO20"],
     "rationale": "Hypertension: ACE inhibitor (Lisinopril) or CCB (Amlodipine) first-line. Add statin if CV risk high."},

    {"keywords": ["heart failure", "congestive heart failure", "hfrEF", "cardiac failure"],
     "drugs": ["D-LIS10", "D-FUR40", "D-SPR25", "D-EMP10", "D-ATE50"],
     "rationale": "HFrEF: ACE inhibitor + loop diuretic + mineralocorticoid antagonist + SGLT2i (if T2DM). Beta-blocker for rate."},

    {"keywords": ["atrial fibrillation", "af", "afib", "atrial flutter"],
     "drugs": ["D-ATE50", "D-WAR5", "D-ASP81"],
     "rationale": "AF: Rate control (Beta-blocker) + anticoagulation (Warfarin/DOAC) based on CHA₂DS₂-VASc score."},

    {"keywords": ["asthma", "bronchial asthma", "reactive airway", "bronchospasm"],
     "drugs": ["D-SAL100", "D-FLU100"],
     "rationale": "Asthma: SABA (Salbutamol) as reliever + ICS (Fluticasone) as preventer. Review trigger avoidance."},

    {"keywords": ["copd", "chronic obstructive", "emphysema", "chronic bronchitis"],
     "drugs": ["D-SAL100", "D-FLU100"],
     "rationale": "COPD: SABA for relief; ICS/LABA for persistent symptoms. Smoking cessation essential."},

    {"keywords": ["gerd", "gastroesophageal reflux", "reflux", "heartburn", "peptic ulcer"],
     "drugs": ["D-OMP20"],
     "rationale": "GERD/PUD: PPI (Omeprazole) first-line. Lifestyle modification essential."},

    {"keywords": ["nausea", "vomiting", "gastroparesis", "gastroenteritis"],
     "drugs": ["D-MET10D", "D-OMP20"],
     "rationale": "Nausea/vomiting: Metoclopramide short-term. Ensure adequate hydration."},

    {"keywords": ["hypothyroidism", "underactive thyroid", "low tsh"],
     "drugs": ["D-LEV50"],
     "rationale": "Hypothyroidism: Levothyroxine titrated by TSH. Lifelong replacement required."},

    {"keywords": ["iron deficiency", "iron deficiency anaemia", "anaemia", "anemia"],
     "drugs": ["D-IRO200", "D-PAR500"],
     "rationale": "Iron deficiency anaemia: Ferrous sulphate + investigate and treat the underlying cause."},

    {"keywords": ["hyperlipidaemia", "dyslipidaemia", "high cholesterol", "hypercholesterolaemia"],
     "drugs": ["D-ATO20"],
     "rationale": "Dyslipidaemia: Statin (Atorvastatin) first-line for LDL reduction and CV risk."},

    {"keywords": ["gout", "gouty arthritis", "uric acid", "hyperuricaemia"],
     "drugs": ["D-IBU400", "D-ALL300"],
     "rationale": "Gout: NSAIDs (Ibuprofen) for acute attack; Allopurinol for long-term urate-lowering (do NOT start during acute)."},

    {"keywords": ["depression", "major depressive", "mdd"],
     "drugs": ["D-SER50"],
     "rationale": "Depression: SSRI (Sertraline) first-line. Allow 4–6 weeks for response. Combine with therapy."},

    {"keywords": ["anxiety", "generalised anxiety", "gad", "panic"],
     "drugs": ["D-SER50"],
     "rationale": "Anxiety: SSRI (Sertraline) first-line for GAD/panic. Avoid benzodiazepines long-term."},

    {"keywords": ["ckd", "chronic kidney disease", "renal failure", "nephropathy"],
     "drugs": ["D-LIS10", "D-FUR40", "D-BIC500"],
     "rationale": "CKD: ACE inhibitor for proteinuria/BP; loop diuretic for fluid; bicarbonate if acidotic. Avoid NSAIDs/nephrotoxins."},

    {"keywords": ["myocardial infarction", "mi", "acs", "acute coronary", "stemi", "nstemi"],
     "drugs": ["D-ASP81", "D-ATE50", "D-LIS10", "D-ATO20"],
     "rationale": "Post-MI: Aspirin + Beta-blocker + ACE inhibitor + Statin (ABCS regimen)."},
]

# Build a lookup index from drug ID → drug info
_DRUG_LOOKUP: Dict[str, Dict[str, Any]] = {d["id"]: d for d in _DRUG_CATALOG}


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def suggest_medications(
    diagnoses: List[str],
    symptoms: Optional[str] = None,
    allergies: Optional[List[str]] = None,
    conditions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Return evidence-based drug suggestions for the given diagnoses / symptoms.

    Parameters
    ----------
    diagnoses  : list of confirmed diagnosis names (strings)
    symptoms   : free-text symptom string (optional)
    allergies  : list of allergen names (to filter out contraindicated drugs)
    conditions : additional known conditions (merged with diagnoses for matching)

    Returns
    -------
    dict with:
        suggestions : list[{drug, rationale, alternatives}]
        matched_diagnoses : list of matched condition names
        warning : str (if any)
    """
    allergy_lower = [_normalise(a) for a in (allergies or [])]
    context_text = " ".join([
        _normalise(d) for d in (diagnoses or [])
    ] + [
        _normalise(c) for c in (conditions or [])
    ] + [_normalise(symptoms or "")])

    matched_rules: List[Dict[str, Any]] = []
    seen_rule_keys: set = set()

    for rule in _DX_TO_DRUGS:
        if any(kw in context_text for kw in rule["keywords"]):
            key = tuple(rule["drugs"])
            if key not in seen_rule_keys:
                seen_rule_keys.add(key)
                matched_rules.append(rule)

    suggestions: List[Dict[str, Any]] = []
    seen_drug_ids: set = set()
    matched_diagnoses: List[str] = []

    for rule in matched_rules:
        matched_diagnoses.append(rule["keywords"][0].title())
        group_drugs: List[Dict[str, Any]] = []

        for drug_id in rule["drugs"]:
            if drug_id in seen_drug_ids:
                continue
            drug = _DRUG_LOOKUP.get(drug_id)
            if not drug:
                continue

            # Check for allergy contraindications
            ci_lower = [_normalise(c) for c in drug.get("contraindications", [])]
            allergy_conflict = any(
                any(al in ci or ci in al for ci in ci_lower)
                for al in allergy_lower
            )
            if allergy_conflict:
                continue

            seen_drug_ids.add(drug_id)
            group_drugs.append({
                "id": drug["id"],
                "name": drug["name"],
                "class": drug["class"],
                "indication": drug["indication"],
                "dose": drug["dose"],
                "frequency": drug["frequency"],
                "duration": drug["duration"],
                "route": drug["route"],
                "line": drug["line"],
                "contraindications": drug.get("contraindications", []),
                "interactions": drug.get("interactions", []),
                "notes": drug.get("notes", ""),
                "max_daily": drug.get("max_daily"),
            })

        if group_drugs:
            suggestions.append({
                "matched_on": rule["keywords"][0].title(),
                "rationale": rule["rationale"],
                "drugs": group_drugs,
            })

    warning = ""
    if not suggestions:
        warning = "No specific drug recommendations found for the provided diagnoses. Please consult clinical guidelines."

    return {
        "suggestions": suggestions,
        "matched_diagnoses": list(dict.fromkeys(matched_diagnoses)),
        "warning": warning,
        "disclaimer": (
            "These suggestions are evidence-based references for educational purposes only. "
            "Final prescribing decisions must be made by a licensed clinician "
            "based on individual patient assessment."
        ),
    }
