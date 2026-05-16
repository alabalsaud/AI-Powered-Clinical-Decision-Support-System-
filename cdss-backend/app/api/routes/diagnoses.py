"""
app/api/routes/diagnoses.py  — FR3, FR8
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session
from typing import List

from app.core.config import settings
from app.db.database import get_db
from app.models.models import User, Patient, Diagnosis, AIAnalysis
from app.schemas.schemas import (
    DiagnosisCreate,
    DiagnosisUpdate,
    DiagnosisOut,
    LLMDiagnosisRequest,
    LLMDiagnosisResponse,
    LLMStatusOut,
)
from app.core.security import get_current_user
from app.services.audit import log_action
from app.services.llm_diagnosis import suggest_diagnoses_llm, LLMProviderError

router = APIRouter(prefix="/diagnoses", tags=["Diagnoses"])


def _llm_upstream_hint(status_code: int) -> str:
    if status_code == 503:
        return (
            "Upstream is overloaded or the model endpoint is unavailable. "
            "Retry in 1–2 minutes; try another model in LLM_MODEL; for OpenRouter free tier try a different :free model."
        )
    if status_code == 429:
        return "Rate limited — wait and retry, reduce calls, or use a paid tier / different provider."
    if status_code == 401:
        return "Invalid or expired API key — check HF_TOKEN or OPENAI_API_KEY in cdss-backend/.env and restart the server."
    if status_code == 400:
        return "Bad request to provider — check LLM_MODEL and LLM_USE_JSON_OBJECT=false if JSON mode is unsupported."
    if status_code in (502, 504):
        return "Gateway timeout from provider — often transient; retries already attempted."
    return "See provider_message for details from the upstream API."


@router.get("/llm-status", response_model=LLMStatusOut)
def llm_status(current_user: User = Depends(get_current_user)):
    """Whether an API key is configured for LLM-backed diagnosis suggestions."""
    return LLMStatusOut(configured=settings.llm_configured, model=settings.active_llm_model)


@router.post("/llm-suggest", response_model=LLMDiagnosisResponse)
def llm_suggest_diagnoses(
    payload: LLMDiagnosisRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Propose ranked differential diagnoses using an OpenAI-compatible LLM.
    Requires OPENAI_API_KEY in environment. For production, review data governance.
    """
    if not settings.llm_configured:
        raise HTTPException(
            status_code=501,
            detail={"message": "LLM not configured", "code": "llm_not_configured"},
        )
    if not (payload.symptoms or "").strip():
        raise HTTPException(400, "symptoms are required")

    ctx = payload.model_dump()
    try:
        result = suggest_diagnoses_llm(ctx)
    except LLMProviderError as e:
        hint = _llm_upstream_hint(e.status_code)
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"LLM provider returned HTTP {e.status_code}",
                "provider_message": e.body_snippet or None,
                "code": "llm_provider_error",
                "hint": hint,
            },
        ) from e
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail={"message": f"LLM request failed: {e!s}", "code": "llm_network_error"},
        ) from e
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(
            status_code=502,
            detail={"message": f"LLM output invalid: {e!s}", "code": "llm_parse_error"},
        ) from e

    log_action(
        db,
        "LLM Diagnosis Suggestion",
        user_id=current_user.id,
        resource_type="diagnosis",
        resource_id=None,
        detail=f"model={result['model']} suggestions={len(result['suggestions'])}",
        ip_address=request.client.host if request.client else None,
        log_type="clinical",
    )
    try:
        return LLMDiagnosisResponse(
            suggestions=result["suggestions"],
            model=result["model"],
            llm_used=True,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=502,
            detail={"message": f"LLM output failed validation: {e!s}", "code": "llm_parse_error"},
        ) from e


@router.get("/patient/{patient_id}", response_model=List[DiagnosisOut])
def get_patient_diagnoses(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Diagnosis).filter(Diagnosis.patient_id == patient_id)\
             .order_by(Diagnosis.diagnosed_at.desc()).all()


@router.post("/", response_model=DiagnosisOut, status_code=201)
def create_diagnosis(
    payload: DiagnosisCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patient = db.query(Patient).filter(Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(404, "Patient not found")

    dx = Diagnosis(
        patient_id=payload.patient_id,
        physician_id=current_user.id,
        diagnosis_name=payload.diagnosis_name,
        diagnosis_code=payload.diagnosis_code,
        confidence_score=payload.confidence_score,
        source=payload.source,
        notes=payload.notes,
    )
    db.add(dx)
    db.flush()

    # Store AI analysis if provided
    if payload.ai_suggestions or payload.shap_values:
        ai = AIAnalysis(
            diagnosis_id=dx.id,
            confidence_score=payload.confidence_score or 0,
            shap_values=payload.shap_values,
            all_suggestions=payload.ai_suggestions,
            reasoning=payload.reasoning,
        )
        db.add(ai)

    db.commit()
    db.refresh(dx)

    log_action(db, "Diagnosis Created", user_id=current_user.id,
               resource_type="diagnosis", resource_id=dx.id,
               detail=f"AI diagnosis: {dx.diagnosis_name} ({dx.confidence_score}%) for patient {patient.full_name}",
               ip_address=request.client.host, log_type="clinical")
    return dx


@router.put("/{diagnosis_id}/confirm", response_model=DiagnosisOut)
def confirm_diagnosis(
    diagnosis_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dx = db.query(Diagnosis).filter(Diagnosis.id == diagnosis_id).first()
    if not dx:
        raise HTTPException(404, "Diagnosis not found")
    dx.is_confirmed = True
    dx.status = "confirmed"
    dx.source = "AI+Physician"
    dx.version += 1
    db.commit()
    db.refresh(dx)
    log_action(db, "Diagnosis Confirmed", user_id=current_user.id,
               resource_type="diagnosis", resource_id=dx.id,
               detail=f"Confirmed: {dx.diagnosis_name}",
               ip_address=request.client.host, log_type="clinical")
    return dx


@router.get("/{diagnosis_id}", response_model=DiagnosisOut)
def get_diagnosis(
    diagnosis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dx = db.query(Diagnosis).filter(Diagnosis.id == diagnosis_id).first()
    if not dx:
        raise HTTPException(404, "Diagnosis not found")
    return dx
