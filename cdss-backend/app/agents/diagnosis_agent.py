"""
app/agents/diagnosis_agent.py — Agent 2: Diagnosis

Primary path  : calls suggest_diagnoses_llm() (OpenAI-compatible API).
Fallback path : calls generate_diagnoses() (rule-based BioGPT fallback).

Adds to PipelineContext:
  raw_diagnoses   : list[{rank, name, icd, confidence, evidence, factors}]
  llm_used        : bool
  diagnosis_model : str
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.agents.base import BaseAgent, PipelineContext
from app.core.config import settings

logger = logging.getLogger("cdss.agents.diagnosis")


def _to_standard(d: Dict[str, Any], idx: int) -> Dict[str, Any]:
    """Normalise any dict shape → standard pipeline diagnosis shape."""
    return {
        "rank":       d.get("rank") or idx + 1,
        "name":       str(d.get("name") or d.get("diagnosis") or "Unknown"),
        "icd":        str(d.get("icd") or d.get("icd10_code") or "R69"),
        "confidence": int(
            d.get("confidence")
            if d.get("confidence") is not None and d.get("confidence") > 1
            else round((d.get("confidence") or 0.5) * 100)
        ),
        "evidence":   str(d.get("evidence") or d.get("reasoning") or ""),
        "factors":    d.get("factors") or [{"n": "Clinical fit", "v": int(round((d.get("confidence") or 0.5) * 100))}],
    }


class DiagnosisAgent(BaseAgent):
    name = "DiagnosisAgent"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        self.log("Generating differential diagnoses…")

        symptoms     = ctx.get("symptoms") or ""
        conditions   = ctx.get("medical_history") or []
        allergies    = ctx.get("normalised_allergies") or []
        patient_name = ctx.get("patient_name") or "Unknown"
        age          = ctx.get("age")
        gender       = ctx.get("gender")
        lab          = ctx.get("lab") or {}
        notes        = ctx.get("clinical_notes")

        raw: List[Dict[str, Any]] = []
        llm_used = False
        model_used = "rule-based"

        # ── Primary: LLM path ─────────────────────────────────────────────────
        if settings.llm_configured and symptoms.strip():
            try:
                from app.services.llm_diagnosis import suggest_diagnoses_llm
                llm_ctx = {
                    "patient_name":   patient_name,
                    "age":            age,
                    "gender":         gender,
                    "conditions":     conditions,
                    "allergies":      allergies,
                    "symptoms":       symptoms,
                    "clinical_notes": notes,
                    "lab":            lab,
                }
                result = suggest_diagnoses_llm(llm_ctx)
                raw = [_to_standard(d, i) for i, d in enumerate(result.get("suggestions") or [])]
                model_used = result.get("model", settings.active_llm_model)
                llm_used = bool(raw)
                self.log(f"LLM returned {len(raw)} diagnoses (model={model_used})")
            except Exception as exc:
                self.log(f"LLM failed ({exc}), using rule-based fallback", "warning")

        # ── Fallback: rule-based ───────────────────────────────────────────────
        if not raw:
            try:
                from app.models.diagnosis_model import generate_diagnoses
                rule_input = {
                    "symptoms":        symptoms,
                    "age":             age,
                    "gender":          gender,
                    "medical_history": conditions,
                    "lab_values":      lab,
                    "clinical_notes":  notes,
                }
                rule_results = generate_diagnoses(rule_input)
                raw = [
                    _to_standard({
                        "rank":       i + 1,
                        "name":       d.get("diagnosis", ""),
                        "icd":        d.get("icd10_code", "R69"),
                        "confidence": int(round(d.get("confidence", 0.5) * 100)),
                        "evidence":   d.get("reasoning", ""),
                        "factors":    [{"n": "Clinical fit", "v": int(round(d.get("confidence", 0.5) * 100))}],
                    }, i)
                    for i, d in enumerate(rule_results)
                ]
                model_used = "rule-based"
                self.log(f"Rule-based returned {len(raw)} diagnoses")
            except Exception as exc:
                self.log(f"Rule-based fallback also failed: {exc}", "error")
                raw = []

        ctx["raw_diagnoses"]   = raw
        ctx["llm_used"]        = llm_used
        ctx["diagnosis_model"] = model_used
        return ctx
