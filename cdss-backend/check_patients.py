"""
View all patient records from the CDSS database.
Command: python check_patients.py
"""
from app.db.database import SessionLocal
from app.models.models import Patient, Allergy, MedicalHistory

db = SessionLocal()
patients = db.query(Patient).order_by(Patient.id).all()

active   = [p for p in patients if p.is_active]
deleted  = [p for p in patients if not p.is_active]

print("\n" + "=" * 80)
print(f"   CDSS DATABASE — All Patients  (Total: {len(patients)}  |  Active: {len(active)}  |  Deleted: {len(deleted)})")
print("=" * 80)

for p in patients:
    name   = p.full_name or f"{p.first_name} {p.last_name}"
    status = "✅ Active" if p.is_active else "❌ Deleted"
    gender = str(p.gender.value) if hasattr(p.gender, 'value') else str(p.gender or "—")

    allergies   = db.query(Allergy).filter(Allergy.patient_id == p.id).all()
    conditions  = db.query(MedicalHistory).filter(MedicalHistory.patient_id == p.id).all()

    allergy_list   = ", ".join(a.allergen for a in allergies) if allergies else "NKDA"
    condition_list = ", ".join(c.condition for c in conditions) if conditions else "None"

    print(f"""
  ID         : {p.id}
  MRN        : {p.mrn}
  Name       : {name}
  Gender     : {gender}
  DOB        : {p.date_of_birth}
  Blood Type : {p.blood_type or "—"}
  Phone      : {p.phone or "—"}
  Allergies  : {allergy_list}
  Conditions : {condition_list}
  Status     : {status}
  Created    : {str(p.created_at)[:19]}
  {"-" * 55}""")

db.close()
print("\n✅ Done!\n")
