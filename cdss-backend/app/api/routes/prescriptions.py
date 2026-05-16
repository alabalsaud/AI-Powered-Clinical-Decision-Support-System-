"""
app/api/routes/prescriptions.py — FR5, FR6, FR7
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import User, Patient, Prescription, SafetyCheck
from app.schemas.schemas import PrescriptionCreate, PrescriptionOut, DrugSafetyRequest, DrugSafetyResponse
from app.core.security import get_current_user
from app.services.drug_safety import run_safety_check
from app.services.audit import log_action

router = APIRouter(prefix="/prescriptions", tags=["Prescriptions"])


@router.post("/safety-check", response_model=DrugSafetyResponse)
def check_drug_safety(
    payload: DrugSafetyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run safety check WITHOUT creating a prescription (FR5, FR6)."""
    patient = db.query(Patient).filter(Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(404, "Patient not found")

    result = run_safety_check(payload.drug_name, patient, db, payload.dose)
    return result


@router.post("/", response_model=PrescriptionOut, status_code=201)
def create_prescription(
    payload: PrescriptionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create prescription — runs safety check automatically."""
    patient = db.query(Patient).filter(Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(404, "Patient not found")

    # Always run safety check before saving
    safety_result = run_safety_check(payload.drug_name, patient, db, payload.dose)

    # Block if critical
    if safety_result["blocked"]:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "prescription_blocked",
                "message": safety_result["message"],
                "alternatives": safety_result["alternatives"],
                "checks": safety_result["checks"],
            }
        )

    rx = Prescription(
        patient_id=payload.patient_id,
        prescriber_id=current_user.id,
        medication_id=payload.medication_id,
        treatment_plan_id=payload.treatment_plan_id,
        drug_name=payload.drug_name,
        dose=payload.dose,
        frequency=payload.frequency,
        route=payload.route,
        duration=payload.duration,
        special_instructions=payload.special_instructions,
    )
    db.add(rx)
    db.flush()

    # Save safety check results
    for check in safety_result["checks"]:
        sc = SafetyCheck(
            prescription_id=rx.id,
            check_type=check["check_type"],
            result=check["result"],
            severity=check.get("severity"),
            findings=check.get("findings"),
            alternatives=safety_result.get("alternatives"),
        )
        db.add(sc)

    db.commit()
    db.refresh(rx)

    log_action(db, "Prescription Created", user_id=current_user.id,
               resource_type="prescription", resource_id=rx.id,
               detail=f"Prescribed {rx.drug_name} {rx.dose} for patient {patient.full_name} — Safety: {safety_result['result_type']}",
               ip_address=request.client.host, log_type="prescription")
    return rx


@router.get("/patient/{patient_id}", response_model=List[PrescriptionOut])
def get_patient_prescriptions(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Prescription).filter(Prescription.patient_id == patient_id)\
             .order_by(Prescription.prescribed_date.desc()).all()


@router.get("/{prescription_id}", response_model=PrescriptionOut)
def get_prescription(
    prescription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rx = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not rx:
        raise HTTPException(404, "Prescription not found")
    return rx


@router.patch("/{prescription_id}/cancel", response_model=PrescriptionOut)
def cancel_prescription(
    prescription_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rx = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not rx:
        raise HTTPException(404, "Prescription not found")
    rx.status = "cancelled"
    rx.version += 1
    db.commit()
    db.refresh(rx)
    log_action(db, "Prescription Cancelled", user_id=current_user.id,
               resource_type="prescription", resource_id=rx.id,
               detail=f"Cancelled: {rx.drug_name}",
               ip_address=request.client.host, log_type="prescription")
    return rx
