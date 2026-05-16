"""
LLM-backed differential diagnosis suggestions (OpenAI-compatible Chat Completions).
Returns JSON shaped for the React DiagnosisEngine UI.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List

_ICD_CLEAN = re.compile(r"[^A-Za-z0-9.]")

import httpx

from app.core.config import settings

logger = logging.getLogger("cdss.llm")

# HTTP statuses worth retrying (transient overload / rate / gateway)
_TRANSIENT_STATUSES = frozenset({429, 502, 503, 504})


class LLMProviderError(Exception):
    """Upstream chat API returned a non-success status."""

    def __init__(self, status_code: int, body_snippet: str):
        self.status_code = int(status_code)
        self.body_snippet = (body_snippet or "").strip()[:500]
        super().__init__(f"HTTP {self.status_code}: {self.body_snippet}")


def _provider_error_snippet(resp: httpx.Response) -> str:
    """Best-effort text from OpenAI / OpenRouter / HF style JSON error bodies."""
    try:
        data = resp.json()
    except Exception:
        return (resp.text or "").strip()[:500]
    if not isinstance(data, dict):
        return (resp.text or "").strip()[:500]

    err = data.get("error")
    if isinstance(err, dict):
        msg = str(err.get("message") or "").strip()
        code = err.get("code")
        meta = err.get("metadata")
        extra = ""
        if isinstance(meta, dict):
            raw = meta.get("raw")
            pname = meta.get("provider_name")
            bits = [b for b in (raw, pname) if b]
            if bits:
                extra = " — " + " · ".join(str(b) for b in bits)[:400]
        # OpenRouter often sets message to "Provider returned error" while raw has the real reason
        if extra and (not msg or msg.lower() == "provider returned error"):
            tail = extra.lstrip(" —")
            return (f"HTTP {code}: {tail}" if code is not None else tail)[:500]
        if msg and extra:
            return (msg + extra)[:500]
        if msg:
            return (f"{msg} (code {code})" if code is not None else msg)[:400]
        return str(err.get("code") or err)[:400]
    if isinstance(err, str):
        return err[:400]
    m = data.get("message")
    if isinstance(m, str):
        return m[:400]
    return (resp.text or "").strip()[:500]


SYSTEM_PROMPT = """You are a clinical decision support assistant embedded in an educational CDSS demo.
You assist licensed clinicians by proposing DIFFERENTIAL diagnoses only — not definitive medical advice.

Rules:
- Output ONLY valid JSON (no markdown fences, no prose outside JSON).
- JSON shape: {"suggestions": [ ... ]}
- Each suggestion MUST have: rank (int 1..n), name (string), icd (string ICD-10 code like E11.9),
  confidence (integer 0-100, relative ranking only, NOT diagnostic certainty),
  evidence (short string: clinical reasoning in neutral tone),
  factors (array of {"n": string label, "v": integer 0-100} for explainability — illustrative feature weights, not real ML).
- Provide 3 to 6 ranked suggestions when clinically reasonable.
- Prefer common, evidence-aligned differentials for the presented data; include serious diagnoses when red flags exist.
- If information is insufficient, still give best-effort differentials and lower confidences; note uncertainty briefly in evidence.
- Never claim the patient has a disease; use wording like "consistent with" in evidence where appropriate.
"""


def _build_user_content(ctx: Dict[str, Any]) -> str:
    parts = [
        "Patient context (for differential diagnosis only):",
        f"- Name / ID: {ctx.get('patient_name', 'Unknown')}",
        f"- Age: {ctx.get('age', 'N/A')}",
        f"- Gender: {ctx.get('gender', 'N/A')}",
    ]
    conds = ctx.get("conditions") or []
    if conds:
        parts.append(f"- Known conditions: {', '.join(str(c) for c in conds)}")
    alls = ctx.get("allergies") or []
    if alls:
        parts.append(f"- Allergies: {', '.join(str(a) for a in alls)}")
    parts.append("")
    parts.append("Presenting symptoms (required):")
    parts.append(ctx.get("symptoms") or "(none)")
    notes = ctx.get("clinical_notes")
    if notes:
        parts.append("")
        parts.append("Clinical notes:")
        parts.append(str(notes))
    lab = ctx.get("lab") or {}
    if any(str(v).strip() for v in lab.values()):
        parts.append("")
        parts.append("Laboratory values (may be incomplete):")
        for k, v in lab.items():
            if str(v).strip():
                parts.append(f"  - {k}: {v}")
    rag_block = ctx.get("rag_block")
    if rag_block:
        parts.append("")
        parts.append(str(rag_block))
    parts.append("")
    parts.append('Respond with JSON only: {"suggestions": [...]}')
    return "\n".join(parts)


def _normalize_suggestion(raw: Dict[str, Any], idx: int) -> Dict[str, Any]:
    factors_in = raw.get("factors") or []
    factors: List[Dict[str, Any]] = []
    for f in factors_in[:12]:
        if not isinstance(f, dict):
            continue
        n = str(f.get("n") or f.get("name") or "Factor")[:80]
        try:
            v = int(f.get("v", f.get("value", 0)))
        except (TypeError, ValueError):
            v = 0
        v = max(0, min(100, v))
        factors.append({"n": n, "v": v})
    if not factors:
        factors = [{"n": "Clinical fit", "v": 50}]

    try:
        conf = int(raw.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0
    conf = max(0, min(100, conf))

    icd = _ICD_CLEAN.sub("", str(raw.get("icd") or raw.get("icd10") or "R69")).strip()[:12]
    if len(icd) < 3:
        icd = "R69"

    name = str(raw.get("name") or raw.get("diagnosis") or "Unspecified condition").strip()[:300]
    evidence = str(raw.get("evidence") or raw.get("rationale") or "").strip()[:1200]
    if not evidence:
        evidence = "Differential based on supplied clinical data; requires physician validation."

    try:
        rank = int(raw.get("rank", idx + 1))
    except (TypeError, ValueError):
        rank = idx + 1

    return {
        "rank": rank,
        "name": name,
        "icd": icd.upper(),
        "confidence": conf,
        "evidence": evidence,
        "factors": factors,
    }


def _parse_llm_json(text: str) -> List[Dict[str, Any]]:
    text = text.strip()
    # Strip accidental markdown code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("root must be object")
    suggestions = data.get("suggestions")
    if not isinstance(suggestions, list):
        raise ValueError("missing suggestions array")
    out: List[Dict[str, Any]] = []
    for i, item in enumerate(suggestions):
        if isinstance(item, dict):
            out.append(_normalize_suggestion(item, i))
    out.sort(key=lambda x: x["rank"])
    for i, row in enumerate(out, start=1):
        row["rank"] = i
    if not out:
        raise ValueError("empty suggestions")
    return out


def suggest_diagnoses_llm(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call OpenAI-compatible Chat Completions. Returns {"suggestions": [...], "model": str}.
    Retries transient 429/502/503/504. Raises LLMProviderError on final provider failure.
    """
    rag_snippets: List[Dict[str, str]] = []
    ctx_send = dict(context)
    if settings.RAG_ENABLED:
        try:
            from app.services.rag_retrieval import (
                build_rag_query,
                format_rag_for_prompt,
                retrieve_rag_snippets,
            )
            rq = build_rag_query(context)
            rag_snippets = retrieve_rag_snippets(rq)
            if rag_snippets:
                ctx_send["rag_block"] = format_rag_for_prompt(rag_snippets)
        except Exception as exc:
            logger.warning("RAG retrieval skipped: %s", exc)

    from app.services.llm_http import chat_completions_url, chat_headers, resolve_model

    url = chat_completions_url()
    headers = chat_headers()
    body: Dict[str, Any] = {
        "model": resolve_model(),
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_content(ctx_send)},
        ],
    }
    if settings.LLM_USE_JSON_OBJECT:
        body["response_format"] = {"type": "json_object"}

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
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM response is not JSON: {e!s}") from e

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError("unexpected API response shape") from e

    suggestions = _parse_llm_json(content)
    rag_meta = {
        "used": len(rag_snippets) > 0,
        "chunks": len(rag_snippets),
        "sources": [s.get("source", "") for s in rag_snippets],
    }
    return {"suggestions": suggestions, "model": settings.active_llm_model, "rag": rag_meta}
