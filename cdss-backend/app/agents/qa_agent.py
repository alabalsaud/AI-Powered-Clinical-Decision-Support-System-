"""
app/agents/qa_agent.py — Agent 5: QA / Accuracy Scoring

Computes 5 sub-scores and a weighted overall score, assigns a performance grade,
writes one record to generated_reports/pipeline_metrics.json, and calls log_action().

Scoring dimensions
------------------
diagnosis_confidence   (30%) — average final_confidence of top-3 verified diagnoses
symptom_coverage       (20%) — % of triage_features explained by the top diagnosis
medication_safety      (30%) — safe_drugs / total_suggested_drugs * 100
icd_validity           (10%) — % of verified diagnoses with valid ICD-10 format
allergy_safety         (10%) — 100 if zero blocked drugs, else 0

Grade bands
-----------
A  >= 85
B  >= 70
C  >= 55
D   < 55

Adds to PipelineContext:
  qa_scores         : {diagnosis_confidence, symptom_coverage, medication_safety,
                       icd_validity, allergy_safety}
  overall_score     : float  (0-100)
  performance_grade : str    ("A" | "B" | "C" | "D")
  run_id            : str
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.agents.base import BaseAgent, PipelineContext
from app.agents.verification_agent import _DX_EVIDENCE_MAP

_ICD10_RE = re.compile(r"^[A-Z]\d{2}(\.\d{1,4})?$", re.IGNORECASE)

WEIGHTS = {
    "diagnosis_confidence": 0.30,
    "symptom_coverage":     0.20,
    "medication_safety":    0.30,
    "icd_validity":         0.10,
    "allergy_safety":       0.10,
}

GRADE_BANDS = [
    (85, "A"),
    (70, "B"),
    (55, "C"),
    (0,  "D"),
]


def _metrics_path() -> Path:
    base = Path(__file__).resolve().parent.parent.parent
    out = base / "generated_reports"
    out.mkdir(parents=True, exist_ok=True)
    return out / "pipeline_metrics.json"


def _load_metrics() -> List[Dict[str, Any]]:
    p = _metrics_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_metrics(records: List[Dict[str, Any]]) -> None:
    _metrics_path().write_text(
        json.dumps(records, indent=2, default=str),
        encoding="utf-8",
    )


def _symptom_coverage(
    top_dx_name: str, triage_features: List[str]
) -> float:
    """Percentage of top-diagnosis expected features that appear in triage_features."""
    dx_lower = top_dx_name.lower()
    expected: List[str] = []
    for key, kw_list in _DX_EVIDENCE_MAP.items():
        if key in dx_lower or dx_lower in key:
            expected = kw_list
            break
    if not expected or not triage_features:
        return 50.0
    matched = sum(1 for kw in expected if kw in triage_features)
    return round(min(100.0, matched / len(expected) * 100), 1)


class QAAgent(BaseAgent):
    name = "QAAgent"

    def run(
        self,
        ctx: PipelineContext,
        *,
        db: Optional[Session] = None,
        user_id: Optional[int] = None,
    ) -> PipelineContext:
        self.log("Computing accuracy scores…")

        verified        = ctx.get("verified_diagnoses") or []
        triage_features = ctx.get("triage_features") or []
        total_safe      = ctx.get("total_safe_drugs") or 0
        total_warned    = ctx.get("total_warned_drugs") or 0
        total_blocked   = ctx.get("total_blocked_drugs") or 0
        patient_id      = ctx.get("patient_id")
        llm_used        = ctx.get("llm_used", False)

        # ── 1. Diagnosis confidence ─────────────────────────────────────────
        top3_conf = [d.get("confidence", 0) for d in verified[:3]]
        diag_conf_score = round(sum(top3_conf) / len(top3_conf), 1) if top3_conf else 0.0

        # ── 2. Symptom coverage ─────────────────────────────────────────────
        top_dx_name = verified[0].get("name", "") if verified else ""
        sym_cov_score = _symptom_coverage(top_dx_name, triage_features)

        # ── 3. Medication safety ────────────────────────────────────────────
        total_drugs = total_safe + total_warned + total_blocked
        if total_drugs == 0:
            med_safety_score = 100.0   # no drugs suggested → nothing unsafe
        else:
            med_safety_score = round((total_safe / total_drugs) * 100, 1)

        # ── 4. ICD-10 validity ──────────────────────────────────────────────
        if not verified:
            icd_score = 100.0
        else:
            valid_icds = sum(
                1 for d in verified
                if _ICD10_RE.match(str(d.get("icd") or ""))
            )
            icd_score = round((valid_icds / len(verified)) * 100, 1)

        # ── 5. Allergy safety ───────────────────────────────────────────────
        allergy_score = 0.0 if total_blocked > 0 else 100.0

        scores = {
            "diagnosis_confidence": diag_conf_score,
            "symptom_coverage":     sym_cov_score,
            "medication_safety":    med_safety_score,
            "icd_validity":         icd_score,
            "allergy_safety":       allergy_score,
        }

        overall = round(sum(scores[k] * w for k, w in WEIGHTS.items()), 1)

        grade = "D"
        for threshold, g in GRADE_BANDS:
            if overall >= threshold:
                grade = g
                break

        run_id = uuid.uuid4().hex[:12]

        self.log(
            f"run_id={run_id} overall={overall} grade={grade} "
            f"scores={scores}"
        )

        # ── Persist metrics ─────────────────────────────────────────────────
        try:
            records = _load_metrics()
            records.append({
                "run_id":       run_id,
                "timestamp":    datetime.now(timezone.utc).isoformat(),
                "patient_id":   patient_id,
                "overall_score": overall,
                "grade":        grade,
                "scores":       scores,
                "top_diagnosis": top_dx_name or None,
                "llm_used":     llm_used,
                "diagnosis_count": len(verified),
                "safe_drugs":   total_safe,
                "warned_drugs": total_warned,
                "blocked_drugs": total_blocked,
                "urgency":      ctx.get("urgency"),
            })
            _save_metrics(records)
        except Exception as exc:
            self.log(f"Could not write pipeline_metrics.json: {exc}", "warning")

        # ── Audit log ───────────────────────────────────────────────────────
        if db is not None:
            try:
                from app.services.audit import log_action
                log_action(
                    db,
                    "Clinical Pipeline Run",
                    user_id=user_id,
                    resource_type="patient",
                    resource_id=patient_id,
                    detail=(
                        f"run_id={run_id} grade={grade} score={overall} "
                        f"top_dx={top_dx_name!r} llm={llm_used}"
                    ),
                    log_type="clinical",
                )
            except Exception as exc:
                self.log(f"Audit log failed: {exc}", "warning")

        ctx["qa_scores"]         = scores
        ctx["overall_score"]     = overall
        ctx["performance_grade"] = grade
        ctx["run_id"]            = run_id
        return ctx
