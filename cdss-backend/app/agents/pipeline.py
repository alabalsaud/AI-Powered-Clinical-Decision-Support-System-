"""
app/agents/pipeline.py — Clinical Pipeline Orchestrator

Runs all 5 agents in order and returns the final PipelineContext.

Usage
-----
from app.agents.pipeline import run_clinical_pipeline

result = run_clinical_pipeline(
    patient_input={
        "patient_id":    7,
        "patient_name":  "Humera Shaikh",
        "age":           25,
        "gender":        "Female",
        "symptoms":      "fever, sore throat, runny nose",
        "medical_history": [],
        "allergies_raw": [{"allergen": "Penicillin"}],
        "current_meds":  [],
        "vitals":        {},
        "lab":           {},
    },
    db=db_session,
    user_id=current_user.id,
)
"""
from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.agents.base import PipelineContext
from app.agents.triage_agent      import TriageAgent
from app.agents.diagnosis_agent   import DiagnosisAgent
from app.agents.verification_agent import VerificationAgent
from app.agents.medication_agent  import MedicationAgent
from app.agents.qa_agent          import QAAgent

logger = logging.getLogger("cdss.pipeline")

# Singleton agent instances (stateless — safe to reuse)
_triage       = TriageAgent()
_diagnosis    = DiagnosisAgent()
_verification = VerificationAgent()
_medication   = MedicationAgent()
_qa           = QAAgent()


def run_clinical_pipeline(
    patient_input: Dict[str, Any],
    *,
    db: Optional[Session] = None,
    user_id: Optional[int] = None,
) -> PipelineContext:
    """
    Execute the 5-agent pipeline and return the complete PipelineContext.

    Each agent adds its own keys to the context; keys from earlier agents are
    preserved and visible to later agents.

    Parameters
    ----------
    patient_input : dict
        Required: symptoms (str)
        Optional: patient_id, patient_name, age, gender, allergies_raw (list),
                  medical_history (list), current_meds (list), vitals (dict),
                  lab (dict), clinical_notes (str)
    db            : SQLAlchemy Session for audit logging (optional)
    user_id       : int for audit log attribution (optional)
    """
    # Initialise context from caller input
    ctx: PipelineContext = {
        "patient_id":      patient_input.get("patient_id"),
        "patient_name":    patient_input.get("patient_name"),
        "age":             patient_input.get("age"),
        "gender":          patient_input.get("gender"),
        "symptoms":        str(patient_input.get("symptoms") or ""),
        "clinical_notes":  patient_input.get("clinical_notes"),
        "medical_history": list(patient_input.get("medical_history") or []),
        "allergies_raw":   list(patient_input.get("allergies_raw") or []),
        "current_meds":    list(patient_input.get("current_meds") or []),
        "vitals":          dict(patient_input.get("vitals") or {}),
        "lab":             dict(patient_input.get("lab") or {}),
    }

    steps = [
        ("triage",        _triage,       lambda c: _triage.run(c)),
        ("diagnosis",     _diagnosis,    lambda c: _diagnosis.run(c)),
        ("verification",  _verification, lambda c: _verification.run(c)),
        ("medication",    _medication,   lambda c: _medication.run(c)),
        ("qa",            _qa,           lambda c: _qa.run(c, db=db, user_id=user_id)),
    ]

    ctx["pipeline_steps"] = []   # track which steps completed

    for step_name, _, runner in steps:
        try:
            logger.info("Pipeline step: %s", step_name)
            ctx = runner(ctx)
            ctx["pipeline_steps"].append({"step": step_name, "status": "ok"})
        except Exception as exc:
            logger.error("Pipeline step %s failed: %s", step_name, exc)
            logger.debug(traceback.format_exc())
            ctx["pipeline_steps"].append({
                "step":   step_name,
                "status": "error",
                "error":  str(exc),
            })
            # Non-fatal: continue so later agents see partial context

    return ctx
