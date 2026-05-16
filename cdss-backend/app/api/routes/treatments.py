"""
app/api/routes/treatments.py — FR4
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import User, Patient, TreatmentPlan
from app.schemas.schemas import TreatmentPlanCreate, TreatmentPlanOut
from app.core.security import get_current_user
from app.services.audit import log_action

router = APIRouter(prefix="/treatments", tags=["Treatment Plans"])


@router.post("/", response_model=TreatmentPlanOut, status_code=201)
def create_treatment_plan(
    payload: TreatmentPlanCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = TreatmentPlan(
        patient_id=payload.patient_id,
        diagnosis_id=payload.diagnosis_id,
        title=payload.title,
        treatment_description=payload.treatment_description,
        medications=payload.medications,
        lifestyle=payload.lifestyle,
        monitoring=payload.monitoring,
        references=payload.references,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    log_action(db, "Treatment Plan Created", user_id=current_user.id,
               resource_type="treatment", resource_id=plan.id,
               detail=f"Plan: {plan.title}",
               ip_address=request.client.host, log_type="clinical")
    return plan


@router.get("/patient/{patient_id}", response_model=List[TreatmentPlanOut])
def get_patient_plans(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(TreatmentPlan).filter(TreatmentPlan.patient_id == patient_id).all()


@router.get("/{plan_id}", response_model=TreatmentPlanOut)
def get_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = db.query(TreatmentPlan).filter(TreatmentPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Treatment plan not found")
    return plan
