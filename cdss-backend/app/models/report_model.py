"""
Clinical session report: LLM summarization (Llama-3.2-3B-Instruct), PDF export, audit logging.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from xml.sax.saxutils import escape

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.audit import log_action
from app.services.llm_diagnosis import LLMProviderError, _provider_error_snippet

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer

logger = logging.getLogger(__name__)

# OpenAI-compatible providers (e.g. OpenRouter, Together) accept this slug for Llama 3.2 3B Instruct.
CLINICAL_REPORT_LLM_MODEL = "meta-llama/Llama-3.2-3B-Instruct"

_TRANSIENT_STATUSES = frozenset({429, 502, 503, 504})

REPORT_SYSTEM_PROMPT = """You are a clinical documentation assistant for an educational clinical decision support system.
Summarize the session into a concise, factual structured report for clinician review.
Output plain text only (no markdown fences). Use EXACTLY these section headings in this order, each on its own line followed by a blank line then the body:

PATIENT DEMOGRAPHICS
PRESENTING COMPLAINTS
AI DIAGNOSIS SUGGESTIONS (include confidence scores when provided)
XAI REASONING
TREATMENT PLAN
PRESCRIPTIONS
DRUG SAFETY CHECK RESULTS

Rules:
- Use neutral clinical tone; do not assert definitive diagnoses.
- If a field is missing from the input, write "Not documented in session data." for that section.
- Keep each section focused; avoid repeating the same sentence across sections.
"""


def _get(d: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return default


def _jsonish(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    try:
        return json.dumps(v, indent=2, default=str)
    except TypeError:
        return str(v)


def _build_session_digest(session_data: Dict[str, Any]) -> str:
    """Flatten session_data for the LLM user message."""
    demographics = _get(session_data, "patient_demographics", "demographics", "patient", default={})
    complaints = _get(
        session_data,
        "presenting_complaints",
        "complaints",
        "symptoms",
        "chief_complaint",
        default="",
    )
    suggestions = _get(
        session_data,
        "ai_diagnosis_suggestions",
        "diagnosis_suggestions",
        "suggestions",
        "llm_suggestions",
        default=[],
    )
    xai = _get(session_data, "xai_reasoning", "xai", "explainability", "shap", default="")
    treatment = _get(session_data, "treatment_plan", "treatments", "treatment", default="")
    prescriptions = _get(session_data, "prescriptions", "medications", "meds", default=[])
    safety = _get(
        session_data,
        "drug_safety_check_results",
        "drug_safety",
        "safety_check",
        "drug_interactions",
        default="",
    )

    lines = [
        "Source session payload (summarize into the required sections):",
        "",
        "PATIENT DEMOGRAPHICS (raw):",
        _jsonish(demographics),
        "",
        "PRESENTING COMPLAINTS (raw):",
        _jsonish(complaints),
        "",
        "AI DIAGNOSIS SUGGESTIONS (raw, include any confidence scores):",
        _jsonish(suggestions),
        "",
        "XAI / EXPLAINABILITY (raw):",
        _jsonish(xai),
        "",
        "TREATMENT PLAN (raw):",
        _jsonish(treatment),
        "",
        "PRESCRIPTIONS (raw):",
        _jsonish(prescriptions),
        "",
        "DRUG SAFETY CHECK RESULTS (raw):",
        _jsonish(safety),
        "",
        "Session metadata (if any):",
        _jsonish({k: v for k, v in session_data.items() if k.startswith("session_")}),
    ]
    return "\n".join(lines)


def _fallback_structured_report(session_data: Dict[str, Any]) -> str:
    """Deterministic structured text when the LLM is unavailable."""
    digest = _build_session_digest(session_data)
    return (
        "PATIENT DEMOGRAPHICS\n\n"
        + _jsonish(_get(session_data, "patient_demographics", "demographics", "patient", default={}))
        + "\n\n"
        "PRESENTING COMPLAINTS\n\n"
        + _jsonish(
            _get(
                session_data,
                "presenting_complaints",
                "complaints",
                "symptoms",
                "chief_complaint",
                default="",
            )
        )
        + "\n\n"
        "AI DIAGNOSIS SUGGESTIONS (include confidence scores when provided)\n\n"
        + _jsonish(
            _get(
                session_data,
                "ai_diagnosis_suggestions",
                "diagnosis_suggestions",
                "suggestions",
                "llm_suggestions",
                default=[],
            )
        )
        + "\n\n"
        "XAI REASONING\n\n"
        + _jsonish(_get(session_data, "xai_reasoning", "xai", "explainability", "shap", default=""))
        + "\n\n"
        "TREATMENT PLAN\n\n"
        + _jsonish(_get(session_data, "treatment_plan", "treatments", "treatment", default=""))
        + "\n\n"
        "PRESCRIPTIONS\n\n"
        + _jsonish(_get(session_data, "prescriptions", "medications", "meds", default=[]))
        + "\n\n"
        "DRUG SAFETY CHECK RESULTS\n\n"
        + _jsonish(
            _get(
                session_data,
                "drug_safety_check_results",
                "drug_safety",
                "safety_check",
                "drug_interactions",
                default="",
            )
        )
        + "\n\n"
        "--- Raw digest (reference) ---\n"
        + digest
    )


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:\w+)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _call_llama_summary(user_content: str) -> str:
    from app.services.llm_http import chat_completions_url, chat_headers, resolve_model

    if not settings.llm_configured:
        raise ValueError("LLM not configured (HF_TOKEN / OPENAI_API_KEY / base URL)")

    url = chat_completions_url()
    headers = chat_headers()

    body: Dict[str, Any] = {
        "model": resolve_model(CLINICAL_REPORT_LLM_MODEL),
        "temperature": 0.25,
        "messages": [
            {"role": "system", "content": REPORT_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }

    max_retries = max(1, min(8, settings.LLM_MAX_RETRIES))
    backoff = max(0.3, settings.LLM_RETRY_BACKOFF_SECONDS)
    r: httpx.Response | None = None

    with httpx.Client(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
        for attempt in range(max_retries):
            r = client.post(url, headers=headers, json=body)
            if r.is_success:
                break
            snippet = _provider_error_snippet(r)
            if r.status_code == 400:
                raise LLMProviderError(400, snippet or r.reason_phrase)
            if r.status_code in _TRANSIENT_STATUSES and attempt < max_retries - 1:
                time.sleep(backoff * (attempt + 1))
                continue
            raise LLMProviderError(r.status_code, snippet or r.reason_phrase)

    if r is None or not r.is_success:
        raise LLMProviderError(0, "empty response from LLM client")

    try:
        payload = r.json()
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise ValueError(f"unexpected LLM response: {e!s}") from e

    return _strip_markdown_fences(str(content or ""))


def _reports_dir() -> Path:
    base = Path(__file__).resolve().parent.parent.parent
    out = base / "generated_reports"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _write_pdf(summary_text: str, pdf_path: Path) -> None:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="ReportTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=14,
    )
    mono = ParagraphStyle(
        name="ReportBodyMono",
        fontName="Courier",
        fontSize=9,
        leading=11,
        leftIndent=0,
    )

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        rightMargin=inch * 0.75,
        leftMargin=inch * 0.75,
        topMargin=inch * 0.75,
        bottomMargin=inch * 0.75,
    )
    story = [
        Paragraph(escape("Clinical Session Report"), title_style),
        Paragraph(escape(f"Generated (UTC): {datetime.utcnow().isoformat(timespec='seconds')}Z"), styles["Normal"]),
        Spacer(1, 0.2 * inch),
        Preformatted(summary_text, mono, maxLineLength=110),
    ]
    doc.build(story)


def generate_clinical_report(
    session_data: dict,
    *,
    db: Optional[Session] = None,
    user_id: Optional[int] = None,
    resource_type: Optional[str] = "session",
    resource_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Summarize a clinical session with Llama-3.2-3B-Instruct, write a PDF, and log to the audit trail when ``db`` is provided.

    Parameters
    ----------
    session_data : dict
        Typical keys (aliases accepted): patient demographics, complaints, AI suggestions with confidences,
        XAI reasoning, treatment plan, prescriptions, drug safety results.

    Returns
    -------
    dict
        ``summary_text``, ``pdf_path`` (absolute), ``model`` (LLM id or ``fallback``).
    """
    if not isinstance(session_data, dict):
        raise TypeError("session_data must be a dict")

    user_content = _build_session_digest(session_data)
    model_used = CLINICAL_REPORT_LLM_MODEL
    summary_text = ""

    try:
        summary_text = _call_llama_summary(user_content)
        if not summary_text.strip():
            raise ValueError("empty LLM summary")
    except (LLMProviderError, ValueError, httpx.RequestError) as exc:
        logger.warning("Clinical report LLM step failed (%s); using structured fallback.", exc)
        summary_text = _fallback_structured_report(session_data)
        model_used = "fallback"

    stem = datetime.utcnow().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    pdf_path = _reports_dir() / f"clinical_report_{stem}.pdf"
    _write_pdf(summary_text, pdf_path)

    logger.info(
        "Clinical report generated model=%s pdf=%s",
        model_used,
        pdf_path,
    )

    if db is not None:
        log_action(
            db,
            "Clinical Report Generated",
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=f"model={model_used} pdf={pdf_path.name}",
            ip_address=ip_address,
            log_type="clinical",
        )

    return {
        "summary_text": summary_text,
        "pdf_path": str(pdf_path.resolve()),
        "model": model_used,
    }
