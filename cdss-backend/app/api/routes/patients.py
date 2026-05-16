"""
app/api/routes/patients.py
Patient CRUD endpoints (FR1).
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import User, Patient, Allergy, MedicalHistory
from app.schemas.schemas import PatientCreate, PatientUpdate, PatientOut, AllergyCreate, MedicalHistoryCreate
from app.core.security import get_current_user, require_admin
from app.services.audit import log_action

router = APIRouter(prefix="/patients", tags=["Patients"])


def _generate_mrn(db: Session) -> str:
    count = db.query(Patient).count()
    return f"MRN-{10000 + count + 1}"


@router.get("/", response_model=list[PatientOut])
def list_patients(
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Patient).filter(Patient.is_active == True)
    if search:
        s = search.strip()
        if s:
            # Name fields are encrypted at rest (Fernet); search by MRN / numeric id only in SQL.
            term = f"%{s}%"
            parts = [Patient.mrn.ilike(term)]
            if s.isdigit():
                parts.append(Patient.id == int(s))
            q = q.filter(or_(*parts))
    return q.order_by(Patient.created_at.desc()).offset(skip).limit(limit).all()


@router.post("/", response_model=PatientOut, status_code=201)
def create_patient(
    payload: PatientCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patient = Patient(
        mrn=_generate_mrn(db),
        first_name=payload.first_name,
        last_name=payload.last_name,
        date_of_birth=payload.date_of_birth,
        gender=payload.gender,
        weight=payload.weight,
        height=payload.height,
        blood_type=payload.blood_type,
        phone=payload.phone,
        email=payload.email,
    )
    db.add(patient)
    db.flush()  # get patient.id before committing

    # Add allergies
    for a in (payload.allergies or []):
        db.add(Allergy(
            patient_id=patient.id,
            allergen=a.allergen,
            allergy_type=a.allergy_type,
            severity=a.severity,
            reaction=a.reaction,
        ))

    # Add medical history conditions
    for c in (payload.conditions or []):
        db.add(MedicalHistory(
            patient_id=patient.id,
            condition=c.condition,
            icd_code=c.icd_code,
            diagnosed_date=c.diagnosed_date,
            notes=c.notes,
        ))

    db.commit()
    db.refresh(patient)

    log_action(db, "Patient Created", user_id=current_user.id,
               resource_type="patient", resource_id=patient.id,
               detail=f"New patient: {patient.full_name} ({patient.mrn})",
               ip_address=request.client.host, log_type="data")
    return patient


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.is_active == True).first()
    if not patient:
        raise HTTPException(404, "Patient not found")

    log_action(db, "Patient Viewed", user_id=current_user.id,
               resource_type="patient", resource_id=patient.id,
               detail=f"Accessed: {patient.full_name} ({patient.mrn})",
               ip_address=request.client.host, log_type="data")
    return patient


@router.put("/{patient_id}", response_model=PatientOut)
def update_patient(
    patient_id: int,
    payload: PatientUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(404, "Patient not found")

    # Optimistic locking check
    if patient.version != payload.version:
        raise HTTPException(409, "Record was modified by another user. Please refresh and try again.")

    update_data = payload.model_dump(exclude={"version"}, exclude_none=True)
    for k, v in update_data.items():
        setattr(patient, k, v)
    patient.version += 1

    db.commit()
    db.refresh(patient)

    log_action(db, "Patient Updated", user_id=current_user.id,
               resource_type="patient", resource_id=patient.id,
               detail=f"Updated: {patient.full_name}",
               ip_address=request.client.host, log_type="data")
    return patient


@router.delete("/{patient_id}", status_code=204)
def deactivate_patient(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    patient.is_active = False
    db.commit()
    log_action(db, "Patient Deactivated", user_id=current_user.id,
               resource_type="patient", resource_id=patient.id,
               detail=f"{current_user.role} deactivated patient: {patient.full_name} ({patient.mrn})",
               ip_address=request.client.host, log_type="data")


@router.post("/{patient_id}/allergies", status_code=201)
def add_allergy(
    patient_id: int,
    payload: AllergyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    allergy = Allergy(patient_id=patient_id, **payload.model_dump())
    db.add(allergy)
    db.commit()
    db.refresh(allergy)
    return allergy


@router.post("/{patient_id}/conditions", status_code=201)
def add_condition(
    patient_id: int,
    payload: MedicalHistoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    cond = MedicalHistory(patient_id=patient_id, **payload.model_dump())
    db.add(cond)
    db.commit()
    db.refresh(cond)
    return cond
