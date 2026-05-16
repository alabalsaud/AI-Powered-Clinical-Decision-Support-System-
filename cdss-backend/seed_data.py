"""
seed_data.py
Run this ONCE after the database is set up to populate:
  - Medications reference table
  - Drug interactions table
  - A default admin/physician user for demo login

Usage:
    python seed_data.py
"""

import sys
import os

# Make sure we can import the app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import SessionLocal, engine, Base
from app.models.models import (
    User, Medication, DrugInteraction,
    Patient, Allergy, MedicalHistory, Diagnosis, AIAnalysis, Prescription
)
from app.core.security import hash_password
from datetime import datetime


def seed():
    # Create all tables first
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("🌱 Seeding database...")

        # ── 1. Default Users ──────────────────────────────────────────
        if not db.query(User).filter(User.email == "dr.alanoud@hospital.sa").first():
            users = [
                User(
                    username="dr.alanoud",
                    email="dr.alanoud@hospital.sa",
                    full_name="Dr. Alanoud Alsaud",
                    hashed_password=hash_password("SecurePass123!"),
                    role="physician",
                    license_number="SAU-12345",
                    is_active=True,
                ),
                User(
                    username="nurse.reem",
                    email="nurse.reem@hospital.sa",
                    full_name="Nurse Reem Al-Qahtani",
                    hashed_password=hash_password("SecurePass123!"),
                    role="nurse",
                    license_number="SAU-67890",
                    is_active=True,
                ),
                User(
                    username="admin",
                    email="admin@hospital.sa",
                    full_name="System Administrator",
                    hashed_password=hash_password("AdminPass123!"),
                    role="administrator",
                    is_active=True,
                ),
            ]
            db.add_all(users)
            db.flush()
            print(f"  Created {len(users)} users")

        # ── 2. Medications ────────────────────────────────────────────
        if db.query(Medication).count() == 0:
            medications = [
                Medication(
                    generic_name="Metformin",
                    brand_names="Glucophage, Glumetza",
                    drug_class="Biguanide",
                    indication="Type 2 Diabetes Mellitus — first-line therapy",
                    contraindications=["CKD Stage IV-V (eGFR < 30)", "Liver disease", "Contrast dye procedures", "Lactic acidosis history"],
                    common_interactions=["Alcohol", "IV contrast agents", "Cimetidine"],
                    max_daily_dose="2000mg/day",
                ),
                Medication(
                    generic_name="Lisinopril",
                    brand_names="Zestril, Prinivil",
                    drug_class="ACE Inhibitor",
                    indication="Hypertension, Heart failure, Diabetic nephropathy",
                    contraindications=["Pregnancy", "Angioedema history", "Bilateral renal artery stenosis", "Hyperkalaemia"],
                    common_interactions=["NSAIDs", "Potassium supplements", "Potassium-sparing diuretics", "Lithium"],
                    max_daily_dose="40mg/day",
                ),
                Medication(
                    generic_name="Amoxicillin",
                    brand_names="Amoxil, Trimox",
                    drug_class="Penicillin antibiotic",
                    indication="Bacterial infections — respiratory, urinary, skin",
                    contraindications=["Penicillin allergy", "Cephalosporin allergy (cross-reactivity ~10%)"],
                    common_interactions=["Warfarin", "Methotrexate", "Oral contraceptives"],
                    max_daily_dose="3000mg/day",
                ),
                Medication(
                    generic_name="Azithromycin",
                    brand_names="Zithromax, Z-Pack",
                    drug_class="Macrolide antibiotic",
                    indication="Community-acquired pneumonia, Sinusitis, STIs",
                    contraindications=["Liver disease", "QT prolongation", "Macrolide allergy"],
                    common_interactions=["Warfarin", "QT-prolonging drugs", "Digoxin", "Antacids"],
                    max_daily_dose="500mg/day",
                ),
                Medication(
                    generic_name="Atorvastatin",
                    brand_names="Lipitor",
                    drug_class="HMG-CoA Reductase Inhibitor (Statin)",
                    indication="Hyperlipidaemia, CVD prevention",
                    contraindications=["Active liver disease", "Pregnancy", "Breastfeeding"],
                    common_interactions=["Cyclosporine", "Fibrates", "Niacin", "Amiodarone", "Clarithromycin"],
                    max_daily_dose="80mg/day",
                ),
                Medication(
                    generic_name="Aspirin",
                    brand_names="Bayer, Disprin",
                    drug_class="NSAID / Antiplatelet",
                    indication="CVD prevention, Pain, Antipyretic",
                    contraindications=["Active peptic ulcer", "Aspirin allergy", "Haemophilia", "Children <16y (Reye syndrome)"],
                    common_interactions=["Warfarin", "Clopidogrel", "NSAIDs", "Methotrexate", "ACE inhibitors"],
                    max_daily_dose="4000mg/day (analgesia); 100mg/day (antiplatelet)",
                ),
                Medication(
                    generic_name="Empagliflozin",
                    brand_names="Jardiance",
                    drug_class="SGLT2 Inhibitor",
                    indication="Type 2 Diabetes, Heart failure, CKD",
                    contraindications=["eGFR < 30 (T2DM)", "Diabetic ketoacidosis", "Type 1 Diabetes"],
                    common_interactions=["Diuretics (dehydration risk)", "Insulin (hypoglycaemia)", "Loop diuretics"],
                    max_daily_dose="25mg/day",
                ),
                Medication(
                    generic_name="Levothyroxine",
                    brand_names="Synthroid, Euthyrox",
                    drug_class="Thyroid hormone replacement",
                    indication="Hypothyroidism, TSH suppression in thyroid cancer",
                    contraindications=["Thyrotoxicosis", "Uncorrected adrenal insufficiency", "Recent MI"],
                    common_interactions=["Calcium carbonate", "Iron supplements", "Antacids", "Warfarin", "Digoxin"],
                    max_daily_dose="Weight-based; typically 1.6 mcg/kg/day",
                ),
                Medication(
                    generic_name="Salbutamol",
                    brand_names="Ventolin, ProAir",
                    drug_class="Short-acting beta-2 agonist (SABA)",
                    indication="Asthma, COPD — acute bronchospasm relief",
                    contraindications=["Hypersensitivity to salbutamol"],
                    common_interactions=["Beta-blockers (antagonism)", "MAO inhibitors", "Diuretics (hypokalaemia)"],
                    max_daily_dose="As needed; max 8 puffs/day",
                ),
                Medication(
                    generic_name="Warfarin",
                    brand_names="Coumadin, Jantoven",
                    drug_class="Vitamin K antagonist anticoagulant",
                    indication="AF, DVT/PE treatment and prevention, mechanical heart valves",
                    contraindications=["Active bleeding", "Pregnancy", "Severe liver disease", "Recent neurosurgery"],
                    common_interactions=["Aspirin", "NSAIDs", "Antibiotics (many)", "Amiodarone", "Omeprazole", "St John's Wort"],
                    max_daily_dose="Individualised by INR target",
                ),
                Medication(
                    generic_name="Ciprofloxacin",
                    brand_names="Cipro, Cipromax",
                    drug_class="Fluoroquinolone antibiotic",
                    indication="UTI, GI infections, respiratory infections",
                    contraindications=["Fluoroquinolone allergy", "Tendon disorders history", "QT prolongation", "Children"],
                    common_interactions=["Antacids (reduced absorption)", "Warfarin (increased INR)", "NSAIDs", "Theophylline"],
                    max_daily_dose="1500mg/day",
                ),
                Medication(
                    generic_name="Omeprazole",
                    brand_names="Prilosec, Losec",
                    drug_class="Proton Pump Inhibitor (PPI)",
                    indication="GERD, Peptic ulcer, H. pylori eradication",
                    contraindications=["Hypersensitivity to PPIs"],
                    common_interactions=["Clopidogrel (reduced effect)", "Methotrexate", "Warfarin", "Digoxin"],
                    max_daily_dose="40mg/day",
                ),
            ]
            db.add_all(medications)
            db.flush()
            print(f"  ✅ Created {len(medications)} medications")

            # ── 3. Drug Interactions ──────────────────────────────────
            # Get medication IDs by name
            med_map = {m.generic_name: m.id for m in db.query(Medication).all()}

            interactions_data = [
                ("Warfarin",    "Aspirin",        "Major",        "Significantly increased bleeding risk — combined anticoagulation and antiplatelet effect",
                                                                   "Avoid combination; if necessary, use lowest effective doses with close INR monitoring"),
                ("Warfarin",    "Ciprofloxacin",  "Moderate",     "Ciprofloxacin inhibits warfarin metabolism — elevated INR",
                                                                   "Monitor INR closely; may need warfarin dose reduction"),
                ("Warfarin",    "Omeprazole",     "Moderate",     "Omeprazole inhibits CYP2C19 — increased warfarin effect",
                                                                   "Monitor INR; consider alternative PPI (pantoprazole)"),
                ("Metformin",   "Empagliflozin",  "Minor",        "Additive glucose-lowering effect — beneficial combination",
                                                                   "Monitor for hypoglycaemia; combination is often intentional"),
                ("Aspirin",     "Ciprofloxacin",  "Minor",        "NSAIDs may increase risk of seizures with fluoroquinolones",
                                                                   "Use with caution; monitor for CNS symptoms"),
                ("Atorvastatin","Azithromycin",   "Moderate",     "Azithromycin inhibits CYP3A4 — increased statin exposure and myopathy risk",
                                                                   "Limit atorvastatin dose; monitor for muscle symptoms"),
                ("Levothyroxine","Omeprazole",    "Minor",        "PPIs may reduce levothyroxine absorption",
                                                                   "Take levothyroxine on empty stomach, 30-60 min before PPI"),
            ]

            for d1, d2, severity, desc, management in interactions_data:
                id1 = med_map.get(d1)
                id2 = med_map.get(d2)
                if id1 and id2:
                    db.add(DrugInteraction(
                        medication_id_1=id1,
                        medication_id_2=id2,
                        severity=severity,
                        description=desc,
                        management=management,
                    ))
            print(f"  ✅ Created {len(interactions_data)} drug interactions")

        # ── 4. Sample Patients ────────────────────────────────────────
        if db.query(Patient).count() == 0:
            doctor = db.query(User).filter(User.email == "dr.alanoud@hospital.sa").first()

            patients_data = [
                {
                    "mrn": "MRN-10001",
                    "first_name": "Hayfa", "last_name": "Almineefi",
                    "date_of_birth": "1979-03-12", "gender": "Female",
                    "weight": 68.0, "height": 162.0, "blood_type": "A+",
                    "phone": "0501234567",
                    "allergies": [
                        {"allergen": "Penicillin", "allergy_type": "Drug", "severity": "Severe",   "reaction": "Anaphylaxis"},
                        {"allergen": "Sulfa",      "allergy_type": "Drug", "severity": "Moderate", "reaction": "Rash"},
                    ],
                    "conditions": [
                        {"condition": "Type 2 Diabetes Mellitus", "icd_code": "E11.9", "diagnosed_date": "2023-01-15"},
                        {"condition": "Essential Hypertension",   "icd_code": "I10",   "diagnosed_date": "2022-06-10"},
                    ],
                },
                {
                    "mrn": "MRN-10002",
                    "first_name": "Loulwah", "last_name": "Ababtain",
                    "date_of_birth": "1996-07-24", "gender": "Female",
                    "weight": 55.0, "height": 158.0, "blood_type": "O+",
                    "phone": "0512345678",
                    "allergies": [
                        {"allergen": "Aspirin", "allergy_type": "Drug", "severity": "Moderate", "reaction": "Urticaria"},
                    ],
                    "conditions": [
                        {"condition": "Bronchial Asthma", "icd_code": "J45.9", "diagnosed_date": "2020-04-20"},
                    ],
                },
                {
                    "mrn": "MRN-10003",
                    "first_name": "Luluh", "last_name": "Almousa",
                    "date_of_birth": "1989-11-03", "gender": "Female",
                    "weight": 62.0, "height": 165.0, "blood_type": "B-",
                    "phone": "0523456789",
                    "allergies": [],
                    "conditions": [],
                },
                {
                    "mrn": "MRN-10004",
                    "first_name": "Meshael", "last_name": "Alissa",
                    "date_of_birth": "1972-05-18", "gender": "Female",
                    "weight": 74.0, "height": 160.0, "blood_type": "AB+",
                    "phone": "0534567890",
                    "allergies": [
                        {"allergen": "NSAIDs", "allergy_type": "Drug", "severity": "Moderate", "reaction": "GI upset"},
                    ],
                    "conditions": [
                        {"condition": "Hypothyroidism",  "icd_code": "E03.9", "diagnosed_date": "2019-09-01"},
                        {"condition": "Osteoporosis",    "icd_code": "M81.0", "diagnosed_date": "2021-03-15"},
                    ],
                },
                {
                    "mrn": "MRN-10005",
                    "first_name": "Ahmed", "last_name": "Al-Rashid",
                    "date_of_birth": "1979-02-14", "gender": "Male",
                    "weight": 85.0, "height": 175.0, "blood_type": "A-",
                    "phone": "0545678901",
                    "allergies": [
                        {"allergen": "Penicillin", "allergy_type": "Drug", "severity": "Severe", "reaction": "Anaphylaxis"},
                    ],
                    "conditions": [
                        {"condition": "Type 2 Diabetes Mellitus", "icd_code": "E11.9",  "diagnosed_date": "2021-08-20"},
                        {"condition": "CKD Stage II",              "icd_code": "N18.2",  "diagnosed_date": "2022-11-05"},
                        {"condition": "Essential Hypertension",    "icd_code": "I10",    "diagnosed_date": "2020-03-18"},
                    ],
                },
            ]

            created_patients = []
            for pd in patients_data:
                p = Patient(
                    mrn=pd["mrn"], first_name=pd["first_name"], last_name=pd["last_name"],
                    date_of_birth=pd["date_of_birth"], gender=pd["gender"],
                    weight=pd["weight"], height=pd["height"],
                    blood_type=pd["blood_type"], phone=pd["phone"],
                )
                db.add(p)
                db.flush()
                for a in pd["allergies"]:
                    db.add(Allergy(patient_id=p.id, **a))
                for c in pd["conditions"]:
                    db.add(MedicalHistory(patient_id=p.id, **c))
                created_patients.append(p)

            db.flush()
            print(f"  ✅ Created {len(created_patients)} sample patients")

            # ── 5. Sample Diagnoses + Prescriptions ──────────────────
            if doctor:
                p1 = db.query(Patient).filter(Patient.mrn == "MRN-10001").first()
                p2 = db.query(Patient).filter(Patient.mrn == "MRN-10002").first()

                if p1:
                    dx1 = Diagnosis(
                        patient_id=p1.id, physician_id=doctor.id,
                        diagnosis_name="Type 2 Diabetes Mellitus",
                        diagnosis_code="E11.9", confidence_score=92.0,
                        status="confirmed", source="AI+Physician", is_confirmed=True,
                    )
                    db.add(dx1)
                    db.flush()
                    db.add(AIAnalysis(
                        diagnosis_id=dx1.id, model_version="ensemble-v1",
                        confidence_score=92.0,
                        shap_values={"Blood Glucose": 88, "HbA1c": 92, "Symptoms": 85, "BMI": 61},
                        reasoning="Elevated HbA1c 7.2% is diagnostic per ADA 2024 criteria.",
                    ))

                    met = db.query(Medication).filter(Medication.generic_name == "Metformin").first()
                    db.add(Prescription(
                        patient_id=p1.id, prescriber_id=doctor.id,
                        medication_id=met.id if met else None,
                        drug_name="Metformin 500mg",
                        dose="500mg", frequency="Twice daily",
                        route="Oral", duration="Ongoing",
                        special_instructions="Take with meals to reduce GI side effects.",
                        status="active",
                    ))

                if p2:
                    dx2 = Diagnosis(
                        patient_id=p2.id, physician_id=doctor.id,
                        diagnosis_name="Bronchial Asthma",
                        diagnosis_code="J45.909", confidence_score=95.0,
                        status="confirmed", source="AI+Physician", is_confirmed=True,
                    )
                    db.add(dx2)

                print("  ✅ Created sample diagnoses and prescriptions")

        db.commit()
        print("\n✅ Database seeded successfully!")
        print("\n🔑 Login credentials:")
        print("   Physician : dr.alanoud@hospital.sa  /  SecurePass123!")
        print("   Nurse     : nurse.reem@hospital.sa  /  SecurePass123!")
        print("   Admin     : admin@hospital.sa        /  AdminPass123!")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Seeding failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
