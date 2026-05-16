"""Shared OpenAI-compatible chat completion HTTP settings for all LLM backends."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.config import settings


def chat_completions_url() -> str:
    return settings.active_llm_base_url.rstrip("/") + "/chat/completions"


def chat_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {
        "Authorization": f"Bearer {settings.active_llm_api_key}",
        "Content-Type": "application/json",
    }
    base = settings.active_llm_base_url.lower()
    if "openrouter.ai" in base:
        headers.setdefault("HTTP-Referer", "http://localhost:5173")
        headers.setdefault("X-OpenRouter-Title", settings.APP_NAME)
    return headers


def resolve_model(model: Optional[str] = None) -> str:
    return model or settings.active_llm_model
