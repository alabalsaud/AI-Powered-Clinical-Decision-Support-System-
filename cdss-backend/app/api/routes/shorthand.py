"""
app/api/routes/shorthand.py — Shorthand /api/* convenience endpoints.

Mirrors the full /api/v1/* routes under a flat /api/* namespace so the
React frontend can use clean, version-free URLs.

Endpoints
---------
POST   /api/auth/login          — login (no JWT required)
GET    /api/auth/refresh         — refresh / validate current token
GET    /api/patients             — list patients
POST   /api/patients             — create patient
GET    /api/patients/{id}        — get patient detail
PUT    /api/patients/{id}        — update patient
POST   /api/diagnose             — AI differential diagnosis
POST   /api/drug-check           — drug-drug + drug-allergy safety check
POST   /api/prescribe            — create prescription with safety gate
POST   /api/report               — generate patient summary report
GET    /api/audit-logs           — audit log retrieval

All endpoints except POST /api/auth/login require JWT Bearer token.
CORS is handled globally in main.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, get_current_user, verify_password
from app.db.database import get_db
from app.models.models import (
    AuditLog, Diagnosis, Patient, Prescription, User,
)
from app.schemas.schemas import (
    PatientCreate, PatientOut, PatientUpdate,
    TokenResponse, UserLogin, UserOut,
)
from app.services.audit import log_action
from app.services.drug_safety import run_safety_check
from app.services.email_service import (
    generate_and_store_code, verify_code, consume_code, send_reset_email
)
from app.core.security import hash_password
from app.models.diagnosis_model import generate_diagnoses
from app.services.llm_diagnosis import suggest_diagnoses_llm, LLMProviderError
from app.services.drug_suggest import suggest_medications
from app.safety.drug_drug import check_drug_interactions
from app.safety.drug_allergy import check_drug_allergy
from app.agents.pipeline import run_clinical_pipeline

router = APIRouter(tags=["Shorthand API"])

MAX_FAILED_ATTEMPTS = 5


# ── Inline request/response schemas ──────────────────────────────────────────

class DiagnoseRequest(BaseModel):
    patient_id:      Optional[int]        = None
    patient_name:    Optional[str]        = None
    age:             Optional[Any]        = None
    gender:          Optional[str]        = None
    symptoms:        str
    medical_history: Optional[Any]        = None
    conditions:      Optional[List[Any]]  = None   # frontend sends this
    allergies:       Optional[List[Any]]  = None   # frontend sends this
    lab_values:      Optional[Dict]       = None   # legacy key
    lab:             Optional[Dict]       = None   # frontend sends this
    clinical_notes:  Optional[str]        = None


class DrugCheckRequest(BaseModel):
    patient_id:   Optional[int]       = None
    drug_name:    str
    current_meds: Optional[List[str]] = None
    allergies:    Optional[List[Dict]] = None


class PrescribeRequest(BaseModel):
    patient_id:  int
    drug_name:   str
    dose:        Optional[str] = None
    frequency:   Optional[str] = None
    duration:    Optional[str] = None
    notes:       Optional[str] = None


class ReportRequest(BaseModel):
    patient_id: int
    include:    Optional[List[str]] = None   # ["diagnoses","prescriptions","notes"]


# ── POST /api/auth/login ──────────────────────────────────────────────────────

@router.post("/auth/login", response_model=TokenResponse)
def shorthand_login(
    payload: UserLogin,
    request: Request,
    db: Session = Depends(get_db),
):
    """Authenticate and return JWT Bearer token. No prior token required."""
    email_norm = str(payload.email).strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email_norm).first()
    if not user:
        raise HTTPException(401, "Invalid credentials")

    if user.account_locked or user.failed_login_count >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(403, f"Account locked after {MAX_FAILED_ATTEMPTS} failed attempts.")

    if not verify_password(payload.password, user.hashed_password):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
            user.account_locked = True
        db.commit()
        remaining = max(0, MAX_FAILED_ATTEMPTS - user.failed_login_count)
        raise HTTPException(401, f"Invalid credentials. {remaining} attempt(s) remaining.")

    if not user.is_active:
        raise HTTPException(403, "Account is inactive.")

    user.failed_login_count = 0
    user.account_locked = False
    user.last_login = datetime.utcnow()
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    log_action(db, "Login", user_id=user.id,
               detail=f"Shorthand login: {user.email}",
               ip_address=request.client.host if request.client else None,
               log_type="auth")
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


# ── GET /api/auth/refresh ─────────────────────────────────────────────────────

@router.get("/auth/refresh")
def shorthand_refresh(current_user: User = Depends(get_current_user)):
    """Validate existing token and return a fresh one with extended expiry."""
    new_token = create_access_token({"sub": str(current_user.id)})
    return {
        "access_token": new_token,
        "token_type":   "bearer",
        "user":         UserOut.model_validate(current_user),
    }


# ── POST /api/auth/forgot-password ───────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str

@router.post("/auth/forgot-password")
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Generate a 6-digit reset code and email it to the user."""
    user = db.query(User).filter(
        func.lower(User.email) == body.email.lower()
    ).first()
    # Always return 200 to avoid email enumeration
    if not user or not user.is_active:
        return {"message": "If that email exists, a reset code has been sent."}
    code = generate_and_store_code(body.email)
    try:
        send_reset_email(body.email, code, user.full_name or "")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")
    return {"message": "If that email exists, a reset code has been sent."}


@router.post("/auth/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Verify the reset code and update the user's password."""
    if not verify_code(body.email, body.code):
        raise HTTPException(status_code=400, detail="Invalid or expired reset code.")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters.")
    user = db.query(User).filter(
        func.lower(User.email) == body.email.lower()
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.hashed_password = hash_password(body.new_password)
    user.failed_login_count = 0
    user.account_locked = False
    db.commit()
    consume_code(body.email)
    return {"message": "Password reset successful. You can now sign in."}


# ── GET /api/patients ─────────────────────────────────────────────────────────

@router.get("/patients", response_model=List[PatientOut])
def shorthand_list_patients(
    search: Optional[str] = Query(None),
    skip:   int           = Query(0, ge=0),
    limit:  int           = Query(50, le=200),
    db:     Session       = Depends(get_db),
    _:      User          = Depends(get_current_user),
):
    """List active patients; optional search matches MRN (names are encrypted at rest)."""
    q = db.query(Patient).filter(Patient.is_active == True)
    if search and search.strip():
        s = search.strip()
        term = f"%{s}%"
        parts = [Patient.mrn.ilike(term)]
        if s.isdigit():
            parts.append(Patient.id == int(s))
        q = q.filter(or_(*parts))
    return q.order_by(Patient.created_at.desc()).offset(skip).limit(limit).all()


# ── POST /api/patients ────────────────────────────────────────────────────────

@router.post("/patients", response_model=PatientOut, status_code=201)
def shorthand_create_patient(
    payload: PatientCreate,
    request: Request,
    db:      Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new patient record."""
    count = db.query(Patient).count()
    mrn   = f"MRN-{10000 + count + 1}"
    from app.models.models import Allergy as AllergyModel, MedicalHistory
    patient = Patient(
        mrn=mrn,
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
    db.flush()
    for a in (payload.allergies or []):
        db.add(AllergyModel(
            patient_id=patient.id, allergen=a.allergen,
            allergy_type=a.allergy_type, severity=a.severity, reaction=a.reaction,
        ))
    for c in (payload.conditions or []):
        db.add(MedicalHistory(
            patient_id=patient.id, condition=c.condition,
            icd_code=c.icd_code, diagnosed_date=c.diagnosed_date, notes=c.notes,
        ))
    db.commit()
    db.refresh(patient)
    log_action(db, "Patient Created", user_id=current_user.id, resource_type="patient",
               resource_id=patient.id, detail=f"MRN {mrn}",
               ip_address=request.client.host if request.client else None)
    return patient


# ── GET /api/patients/{id} ────────────────────────────────────────────────────

@router.get("/patients/{patient_id}", response_model=PatientOut)
def shorthand_get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    _:  User    = Depends(get_current_user),
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    return patient


# ── PUT /api/patients/{id} ────────────────────────────────────────────────────

@router.put("/patients/{patient_id}", response_model=PatientOut)
def shorthand_update_patient(
    patient_id: int,
    payload:    PatientUpdate,
    request:    Request,
    db:         Session = Depends(get_db),
    current_user: User  = Depends(get_current_user),
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if hasattr(patient, field) and value is not None:
            setattr(patient, field, value)
    db.commit()
    db.refresh(patient)
    log_action(db, "Patient Updated", user_id=current_user.id, resource_type="patient",
               resource_id=patient_id, ip_address=request.client.host if request.client else None)
    return patient


# ── POST /api/diagnose ────────────────────────────────────────────────────────

@router.post("/diagnose")
def shorthand_diagnose(
    payload: DiagnoseRequest,
    request: Request,
    db:      Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    AI differential diagnosis — uses OpenAI-compatible LLM when configured,
    otherwise falls back to the rule-based engine.
    Returns {suggestions: [...], llm_used: bool, model: str}.
    """
    from datetime import date as _date

    # ── Resolve patient context from DB when patient_id supplied ─────────────
    db_age:        Any         = payload.age
    db_gender:     Optional[str] = payload.gender
    db_history:    List[str]   = []
    db_allergies:  List[str]   = []
    db_name:       Optional[str] = payload.patient_name

    if payload.patient_id:
        patient = db.query(Patient).filter(Patient.id == payload.patient_id).first()
        if patient:
            try:
                dob     = datetime.strptime(patient.date_of_birth, "%Y-%m-%d").date()
                db_age  = (_date.today() - dob).days // 365
            except Exception:
                pass
            db_gender    = patient.gender.value if hasattr(patient.gender, "value") else str(patient.gender)
            db_history   = [mh.condition for mh in patient.medical_histories]
            db_allergies = [a.allergen for a in patient.allergies]
            db_name      = patient.full_name

    # Merge: DB values take priority over inline payload fields
    conditions = db_history or [str(c) for c in (payload.conditions or [])] or (payload.medical_history or [])
    allergies  = db_allergies or [
        (a.get("allergen") if isinstance(a, dict) else str(a))
        for a in (payload.allergies or [])
    ]
    merged_lab = {**(payload.lab_values or {}), **(payload.lab or {})}

    llm_used = False
    model    = "rule-based"

    # ── Try LLM path first ───────────────────────────────────────────────────
    if settings.llm_configured:
        ctx = {
            "patient_id":     payload.patient_id,
            "patient_name":   db_name or "Unknown",
            "age":            db_age,
            "gender":         db_gender,
            "conditions":     conditions,
            "allergies":      allergies,
            "symptoms":       payload.symptoms,
            "clinical_notes": payload.clinical_notes,
            "lab":            merged_lab,
        }
        try:
            result = suggest_diagnoses_llm(ctx)
            suggestions = result["suggestions"]
            model = result["model"]
            llm_used = True
            rag_info = result.get("rag")
        except (LLMProviderError, Exception):
            suggestions = None   # fall through to rule-based
            rag_info = None

        if suggestions:
            log_action(db, "AI Diagnose (LLM)", user_id=current_user.id,
                       resource_type="diagnosis",
                       detail=f"model={model} symptoms={payload.symptoms[:80]}",
                       ip_address=request.client.host if request.client else None)
            return {
                "suggestions": suggestions,
                "llm_used": True,
                "model": model,
                "rag": rag_info or {"used": False, "chunks": 0, "sources": []},
            }

    # ── Rule-based fallback ───────────────────────────────────────────────────
    patient_data: Dict[str, Any] = {
        "symptoms":        payload.symptoms,
        "age":             db_age,
        "gender":          db_gender,
        "medical_history": conditions,
        "lab_values":      merged_lab,
        "clinical_notes":  payload.clinical_notes,
    }
    rule_diagnoses = generate_diagnoses(patient_data)

    # Normalise rule-based output to the same {rank,name,icd,confidence,evidence,factors} shape
    suggestions = [
        {
            "rank":       i + 1,
            "name":       d["diagnosis"],
            "icd":        d.get("icd10_code", "R69"),
            "confidence": int(round(d["confidence"] * 100)),
            "evidence":   d.get("reasoning", "Rule-based match."),
            "factors":    [{"n": "Clinical fit", "v": int(round(d["confidence"] * 100))}],
        }
        for i, d in enumerate(rule_diagnoses)
    ]

    log_action(db, "AI Diagnose (rules)", user_id=current_user.id,
               resource_type="diagnosis",
               detail=f"symptoms={payload.symptoms[:80]}",
               ip_address=request.client.host if request.client else None)
    return {
        "suggestions": suggestions,
        "llm_used": False,
        "model": "rule-based",
        "rag": {"used": False, "chunks": 0, "sources": []},
    }


# ── POST /api/drug-check ──────────────────────────────────────────────────────

@router.post("/drug-check")
def shorthand_drug_check(
    payload: DrugCheckRequest,
    db:      Session = Depends(get_db),
    _:       User    = Depends(get_current_user),
):
    """
    Drug-drug + drug-allergy safety check.
    Accepts inline current_meds / allergies lists, or pulls from DB via patient_id.
    """
    current_meds: List[str] = list(payload.current_meds or [])
    allergies:    List[Dict] = list(payload.allergies or [])

    if payload.patient_id:
        patient = db.query(Patient).filter(Patient.id == payload.patient_id).first()
        if patient:
            if not current_meds:
                current_meds = [
                    rx.drug_name for rx in patient.prescriptions
                    if str(rx.status).lower() in ("active", "pending")
                ]
            if not allergies:
                allergies = [
                    {"allergen": a.allergen, "severity": str(a.severity), "reaction": a.reaction}
                    for a in patient.allergies
                ]

    ddi = check_drug_interactions(payload.drug_name, current_meds)
    dda = check_drug_allergy(payload.drug_name, allergies)

    has_contraindicated = any(r["severity"] == "Contraindicated" for r in ddi)
    has_allergy_block   = any(r["risk_level"] == "Contraindicated" for r in dda)
    blocked             = has_contraindicated or has_allergy_block

    severity_rank = {"Contraindicated": 4, "High": 3, "Major": 3,
                     "Moderate": 2, "Low": 1, "Minor": 1}
    all_issues = ddi + dda
    overall = "safe"
    if all_issues:
        top_sev = max(severity_rank.get(r.get("severity") or r.get("risk_level", ""), 0) for r in all_issues)
        overall = "critical" if top_sev >= 3 else "warning"

    return {
        "drug":              payload.drug_name,
        "blocked":           blocked,
        "overall":           overall,
        "drug_interactions": ddi,
        "allergy_conflicts": dda,
        "interaction_count": len(ddi),
        "allergy_count":     len(dda),
    }


# ── POST /api/prescribe ───────────────────────────────────────────────────────

@router.post("/prescribe", status_code=201)
def shorthand_prescribe(
    payload: PrescribeRequest,
    request: Request,
    db:      Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a prescription with automatic safety gate (blocks on critical conflicts)."""
    patient = db.query(Patient).filter(Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(404, "Patient not found")

    safety = run_safety_check(payload.drug_name, patient, db, payload.dose)
    if safety["blocked"]:
        raise HTTPException(422, detail={
            "error":        "prescription_blocked",
            "message":      safety["message"],
            "alternatives": safety["alternatives"],
            "checks":       safety["checks"],
        })

    from app.models.models import PrescriptionStatus
    rx = Prescription(
        patient_id=patient.id,
        prescriber_id=current_user.id,
        drug_name=payload.drug_name,
        dose=payload.dose,
        frequency=payload.frequency,
        duration=payload.duration,
        notes=payload.notes,
        status=PrescriptionStatus.active,
        safety_status=safety["result_type"].capitalize(),
    )
    db.add(rx)
    db.commit()
    db.refresh(rx)

    log_action(db, "Prescription Created", user_id=current_user.id,
               resource_type="prescription", resource_id=rx.id,
               detail=f"{payload.drug_name} — {payload.dose}",
               ip_address=request.client.host if request.client else None)
    return {
        "id":         rx.id,
        "drug_name":  rx.drug_name,
        "dose":       rx.dose,
        "status":     str(rx.status),
        "patient_id": rx.patient_id,
        "safety":     safety,
    }


# ── POST /api/report ──────────────────────────────────────────────────────────

@router.post("/report")
def shorthand_report(
    payload: ReportRequest,
    db:      Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a structured patient summary report.
    include: list of sections to include — defaults to all.
    Sections: diagnoses | prescriptions | allergies | conditions | notes
    """
    patient = db.query(Patient).filter(Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(404, "Patient not found")

    sections = set(payload.include or ["diagnoses", "prescriptions", "allergies", "conditions"])
    report: Dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat(),
        "generated_by": current_user.full_name,
        "patient": {
            "id":            patient.id,
            "mrn":           patient.mrn,
            "name":          patient.full_name,
            "date_of_birth": patient.date_of_birth,
            "gender":        str(patient.gender),
            "blood_type":    patient.blood_type,
            "weight_kg":     patient.weight,
            "height_cm":     patient.height,
        },
    }

    if "conditions" in sections:
        report["conditions"] = [
            {"condition": mh.condition, "icd_code": mh.icd_code,
             "diagnosed_date": mh.diagnosed_date, "active": mh.is_active}
            for mh in patient.medical_histories
        ]

    if "allergies" in sections:
        report["allergies"] = [
            {"allergen": a.allergen, "type": a.allergy_type,
             "severity": str(a.severity), "reaction": a.reaction}
            for a in patient.allergies
        ]

    if "diagnoses" in sections:
        diag_rows = db.query(Diagnosis)\
            .filter(Diagnosis.patient_id == patient.id)\
            .order_by(Diagnosis.diagnosed_at.desc()).limit(10).all()
        report["diagnoses"] = [
            {"id": d.id, "condition": d.condition, "icd_code": d.icd_code,
             "status": str(d.status), "confidence": d.confidence,
             "diagnosed_at": d.diagnosed_at.isoformat() if d.diagnosed_at else None}
            for d in diag_rows
        ]

    if "prescriptions" in sections:
        rx_rows = db.query(Prescription)\
            .filter(Prescription.patient_id == patient.id)\
            .order_by(Prescription.prescribed_at.desc()).limit(20).all()
        report["prescriptions"] = [
            {"id": rx.id, "drug": rx.drug_name, "dose": rx.dose,
             "frequency": rx.frequency, "status": str(rx.status),
             "prescribed_at": rx.prescribed_at.isoformat() if rx.prescribed_at else None}
            for rx in rx_rows
        ]

    log_action(db, "Report Generated", user_id=current_user.id,
               resource_type="patient", resource_id=patient.id,
               detail=f"Sections: {', '.join(sections)}")
    return report


# ── POST /api/suggest-medications ────────────────────────────────────────────

class MedSuggestRequest(BaseModel):
    patient_id:  Optional[int]       = None
    diagnoses:   Optional[List[str]] = None   # confirmed diagnosis names
    symptoms:    Optional[str]       = None   # presenting symptoms
    allergies:   Optional[List[str]] = None   # allergen names
    conditions:  Optional[List[str]] = None   # known conditions


@router.post("/suggest-medications")
def shorthand_suggest_medications(
    payload: MedSuggestRequest,
    db:      Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Evidence-based medication suggestions based on confirmed diagnoses / symptoms.
    Rule-based engine — no LLM hallucination. Sources: WHO EML, NICE, BNF.
    """
    diagnoses  = list(payload.diagnoses  or [])
    symptoms   = payload.symptoms
    allergies  = list(payload.allergies  or [])
    conditions = list(payload.conditions or [])

    # Enrich from DB if patient_id provided
    if payload.patient_id:
        patient = db.query(Patient).filter(Patient.id == payload.patient_id).first()
        if patient:
            db_conditions = [mh.condition for mh in patient.medical_histories]
            db_allergies  = [a.allergen for a in patient.allergies]
            if not diagnoses:
                diagnoses = db_conditions
            if not conditions:
                conditions = db_conditions
            if not allergies:
                allergies = db_allergies

    result = suggest_medications(
        diagnoses=diagnoses,
        symptoms=symptoms,
        allergies=allergies,
        conditions=conditions,
    )
    return result


# ── POST /api/clinical-pipeline ──────────────────────────────────────────────

class ClinicalPipelineRequest(BaseModel):
    patient_id:      Optional[int]       = None
    patient_name:    Optional[str]       = None
    age:             Optional[Any]       = None
    gender:          Optional[str]       = None
    symptoms:        str
    clinical_notes:  Optional[str]       = None
    medical_history: Optional[List[Any]] = None
    conditions:      Optional[List[Any]] = None   # alias for medical_history
    allergies:       Optional[List[Any]] = None
    current_meds:    Optional[List[str]] = None
    vitals:          Optional[Dict]      = None
    lab:             Optional[Dict]      = None


@router.post("/clinical-pipeline")
def shorthand_clinical_pipeline(
    payload: ClinicalPipelineRequest,
    request: Request,
    db:      Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run the full 5-agent clinical decision pipeline.
    Returns verified diagnoses, safe medication recommendations, and QA scores.
    """
    # Enrich from DB when patient_id is provided
    allergies_raw  = list(payload.allergies or [])
    history        = list(payload.medical_history or payload.conditions or [])
    current_meds   = list(payload.current_meds or [])
    patient_name   = payload.patient_name
    age            = payload.age
    gender         = payload.gender

    if payload.patient_id:
        patient = db.query(Patient).filter(Patient.id == payload.patient_id).first()
        if patient:
            from datetime import date as _date
            if not age:
                try:
                    dob = datetime.strptime(patient.date_of_birth, "%Y-%m-%d").date()
                    age = (_date.today() - dob).days // 365
                except Exception:
                    pass
            if not gender:
                gender = patient.gender.value if hasattr(patient.gender, "value") else str(patient.gender)
            if not history:
                history = [mh.condition for mh in patient.medical_histories]
            if not allergies_raw:
                allergies_raw = [
                    {"allergen": a.allergen, "severity": str(a.severity), "reaction": a.reaction}
                    for a in patient.allergies
                ]
            if not current_meds:
                current_meds = [
                    rx.drug_name for rx in patient.prescriptions
                    if str(rx.status).lower() in ("active", "pending")
                ]
            if not patient_name:
                patient_name = patient.full_name

    result = run_clinical_pipeline(
        patient_input={
            "patient_id":    payload.patient_id,
            "patient_name":  patient_name,
            "age":           age,
            "gender":        gender,
            "symptoms":      payload.symptoms,
            "clinical_notes": payload.clinical_notes,
            "medical_history": history,
            "allergies_raw": allergies_raw,
            "current_meds":  current_meds,
            "vitals":        payload.vitals or {},
            "lab":           payload.lab or {},
        },
        db=db,
        user_id=current_user.id,
    )

    # Return a clean JSON-serialisable subset (exclude raw SQLAlchemy objects)
    return {
        "run_id":             result.get("run_id"),
        "urgency":            result.get("urgency"),
        "triage_features":    result.get("triage_features"),
        "llm_used":           result.get("llm_used"),
        "diagnosis_model":    result.get("diagnosis_model"),
        "verified_diagnoses": result.get("verified_diagnoses") or [],
        "verification_notes": result.get("verification_notes") or [],
        "medication_groups":  result.get("medication_groups") or [],
        "total_safe_drugs":   result.get("total_safe_drugs", 0),
        "total_warned_drugs": result.get("total_warned_drugs", 0),
        "total_blocked_drugs": result.get("total_blocked_drugs", 0),
        "qa_scores":          result.get("qa_scores") or {},
        "overall_score":      result.get("overall_score", 0),
        "performance_grade":  result.get("performance_grade", "D"),
        "pipeline_steps":     result.get("pipeline_steps") or [],
    }


# ── GET /api/pipeline-metrics ─────────────────────────────────────────────────

@router.get("/pipeline-metrics")
def shorthand_pipeline_metrics(
    limit: int = Query(50, ge=1, le=500),
    _:     User = Depends(get_current_user),
):
    """Return pipeline performance history from pipeline_metrics.json."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent.parent.parent / "generated_reports" / "pipeline_metrics.json"
    if not p.exists():
        return {"records": [], "total": 0, "average_score": None}
    try:
        records = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"records": [], "total": 0, "average_score": None}

    records = list(reversed(records))  # newest first
    total = len(records)
    subset = records[:limit]
    avg = round(sum(r.get("overall_score", 0) for r in subset) / len(subset), 1) if subset else None
    return {"records": subset, "total": total, "average_score": avg}


# ── GET /api/audit-logs ───────────────────────────────────────────────────────

@router.get("/audit-logs")
def shorthand_audit_logs(
    skip:       int           = Query(0, ge=0),
    limit:      int           = Query(50, le=500),
    log_type:   Optional[str] = Query(None),
    user_id:    Optional[int] = Query(None),
    db:         Session       = Depends(get_db),
    current_user: User        = Depends(get_current_user),
):
    """Retrieve audit logs. Admins see all logs; others see only their own."""
    role = str(getattr(current_user, "role", "")).lower()
    is_admin = "admin" in role

    q = db.query(AuditLog)
    if not is_admin:
        q = q.filter(AuditLog.user_id == current_user.id)
    elif user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if log_type:
        q = q.filter(AuditLog.log_type == log_type)

    total = q.count()
    logs  = q.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip":  skip,
        "limit": limit,
        "logs": [
            {
                "id":            lg.id,
                "action":        lg.action,
                "user_id":       lg.user_id,
                "resource_type": lg.resource_type,
                "resource_id":   lg.resource_id,
                "detail":        lg.detail,
                "log_type":      lg.log_type,
                "ip_address":    lg.ip_address,
                "timestamp":     lg.timestamp.isoformat() if lg.timestamp else None,
            }
            for lg in logs
        ],
    }
