"""
app/agents/base.py

Shared base class and PipelineContext definition for the 5-agent clinical pipeline.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

import httpx
from typing_extensions import TypedDict

from app.core.config import settings
from app.services.llm_http import chat_completions_url, chat_headers, resolve_model

logger = logging.getLogger("cdss.agents")

_TRANSIENT = frozenset({429, 502, 503, 504})


# ─── Shared pipeline state ────────────────────────────────────────────────────

class PipelineContext(TypedDict, total=False):
    # ── Input ─────────────────────────────────────────────────────────────────
    patient_id:          Optional[int]
    patient_name:        Optional[str]
    age:                 Optional[Any]
    gender:              Optional[str]
    symptoms:            str
    clinical_notes:      Optional[str]
    medical_history:     List[str]
    allergies_raw:       List[Any]           # original list from caller
    current_meds:        List[str]
    vitals:              Dict[str, Any]
    lab:                 Dict[str, Any]

    # ── Agent 1 — Triage ──────────────────────────────────────────────────────
    triage_features:     List[str]           # normalised clinical keywords
    urgency:             str                 # "critical" | "urgent" | "routine"
    normalised_allergies: List[str]          # lowercase allergen strings

    # ── Agent 2 — Diagnosis ───────────────────────────────────────────────────
    raw_diagnoses:       List[Dict[str, Any]]
    llm_used:            bool
    diagnosis_model:     str

    # ── Agent 3 — Verification ────────────────────────────────────────────────
    verified_diagnoses:  List[Dict[str, Any]]
    verification_notes:  List[str]

    # ── Agent 4 — Medication ──────────────────────────────────────────────────
    medication_groups:   List[Dict[str, Any]]
    total_safe_drugs:    int
    total_warned_drugs:  int
    total_blocked_drugs: int

    # ── Agent 5 — QA ──────────────────────────────────────────────────────────
    qa_scores:           Dict[str, float]
    overall_score:       float
    performance_grade:   str                 # "A" | "B" | "C" | "D"
    run_id:              str


# ─── Base agent ───────────────────────────────────────────────────────────────

class BaseAgent:
    """Shared LLM caller and logging helpers for all pipeline agents."""

    name: str = "BaseAgent"

    def _call_llm(
        self,
        messages: List[Dict[str, str]],
        *,
        json_mode: bool = False,
        model: Optional[str] = None,
    ) -> str:
        """
        Call the configured OpenAI-compatible Chat Completions endpoint.
        Returns the raw content string.
        Raises ValueError if LLM not configured or response is empty.
        """
        if not settings.llm_configured:
            raise ValueError(
                "LLM not configured — set HF_TOKEN (huggingface) or OPENAI_API_KEY in .env"
            )

        url = chat_completions_url()
        headers = chat_headers()

        body: Dict[str, Any] = {
            "model": resolve_model(model),
            "temperature": 0.15,
            "messages": messages,
        }
        if json_mode and settings.LLM_USE_JSON_OBJECT:
            body["response_format"] = {"type": "json_object"}

        max_retries = max(1, min(4, settings.LLM_MAX_RETRIES))
        backoff = max(0.5, settings.LLM_RETRY_BACKOFF_SECONDS)

        with httpx.Client(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            for attempt in range(max_retries):
                r = client.post(url, headers=headers, json=body)
                if r.is_success:
                    break
                if r.status_code == 400:
                    raise ValueError(f"LLM bad request: {r.text[:300]}")
                if r.status_code in _TRANSIENT and attempt < max_retries - 1:
                    time.sleep(backoff * (attempt + 1))
                    continue
                raise ValueError(f"LLM HTTP {r.status_code}: {r.text[:300]}")

        try:
            content = r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Unexpected LLM response shape: {exc}") from exc

        return (content or "").strip()

    def _parse_json_content(self, text: str) -> Any:
        """Strip markdown fences and parse JSON from LLM output."""
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)

    def log(self, msg: str, level: str = "info") -> None:
        getattr(logger, level, logger.info)(f"[{self.name}] {msg}")
