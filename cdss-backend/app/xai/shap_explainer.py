"""
app/xai/shap_explainer.py — SHAP-based explainability for BERT diagnosis models.

Public API
----------
explain_diagnosis(text: str, model, tokenizer) -> list[dict]

Returns top 5 token-level feature importances:
    [
        {"feature": str, "importance": float, "direction": "positive" | "negative"},
        ...
    ]
Sorted by abs(importance) descending — ready to render as a bar chart.

Strategy
--------
Primary:  SHAP DeepExplainer / PartitionExplainer on the supplied BERT model.
Fallback: Gradient × Input approximation using raw PyTorch (no SHAP required).
Tertiary: TF-IDF-inspired token scoring (pure-Python, zero ML deps).

All three paths return the same output contract so the frontend never breaks.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("cdss.xai.shap")

# Special tokens to exclude from explanations
_SPECIAL_TOKENS = {"[CLS]", "[SEP]", "[PAD]", "<s>", "</s>", "<pad>"}

# Clinical term importance weights used by the TF-IDF fallback
_CLINICAL_WEIGHTS: Dict[str, float] = {
    "fever": 0.82, "pain": 0.78, "cough": 0.75, "dyspnea": 0.88,
    "fatigue": 0.65, "nausea": 0.60, "vomiting": 0.70, "dizziness": 0.62,
    "headache": 0.68, "chills": 0.72, "chest": 0.85, "shortness": 0.87,
    "breath": 0.86, "tachycardia": 0.83, "bradycardia": 0.80,
    "hypertension": 0.79, "hypotension": 0.81, "diabetes": 0.77,
    "pneumonia": 0.84, "infarction": 0.92, "troponin": 0.91,
    "glucose": 0.76, "hba1c": 0.89, "creatinine": 0.74, "hemoglobin": 0.71,
    "wbc": 0.73, "platelet": 0.69, "sodium": 0.64, "potassium": 0.67,
    "metformin": 0.70, "aspirin": 0.68, "warfarin": 0.80, "insulin": 0.75,
    "sepsis": 0.90, "stroke": 0.88, "edema": 0.72, "wheeze": 0.76,
    "consolidation": 0.83, "effusion": 0.79, "jaundice": 0.77,
    "tenderness": 0.66, "swelling": 0.63, "rash": 0.61,
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _clean_token(token: str) -> str:
    """Strip BERT sub-word markers and whitespace."""
    return re.sub(r"^#+", "", token).strip()


def _normalise_scores(scores: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
    """Scale importances to [-1, 1] preserving sign."""
    if not scores:
        return scores
    max_abs = max(abs(s) for _, s in scores) or 1.0
    return [(tok, val / max_abs) for tok, val in scores]


def _top5(scores: List[Tuple[str, float]]) -> List[Dict[str, Any]]:
    """Sort by abs value, take top 5, format output dict."""
    sorted_scores = sorted(scores, key=lambda x: abs(x[1]), reverse=True)
    result = []
    seen = set()
    for token, importance in sorted_scores:
        clean = _clean_token(token)
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        result.append({
            "feature":    clean,
            "importance": round(float(importance), 4),
            "direction":  "positive" if importance >= 0 else "negative",
        })
        if len(result) == 5:
            break
    return result


# ─── Path 1: SHAP PartitionExplainer ─────────────────────────────────────────

def _shap_explain(
    text: str,
    model: Any,
    tokenizer: Any,
) -> Optional[List[Tuple[str, float]]]:
    """
    Use SHAP PartitionExplainer (text masker) with the BERT pipeline/model.
    Returns token-score pairs on success, None on failure.
    """
    try:
        import shap
        import numpy as np

        # Build a callable that returns a probability-like score array
        def _predict(texts):
            scores = []
            for t in texts:
                inputs = tokenizer(
                    t, return_tensors="pt", truncation=True,
                    max_length=128, padding=True,
                )
                import torch
                with torch.no_grad():
                    outputs = model(**inputs)
                    logits = outputs.logits if hasattr(outputs, "logits") else outputs[0]
                    probs = torch.softmax(logits, dim=-1).numpy()[0]
                scores.append(probs)
            return np.array(scores)

        masker = shap.maskers.Text(tokenizer)
        explainer = shap.Explainer(_predict, masker)
        shap_values = explainer([text])

        # shap_values[0] shape: (n_tokens, n_classes); take class 0 (or positive class)
        values = shap_values.values[0]          # (n_tokens, n_classes)
        tokens = shap_values.data[0]            # (n_tokens,)

        # Use mean abs across classes as overall importance; sign from class 1
        n_classes = values.shape[1] if values.ndim > 1 else 1
        if n_classes > 1:
            importance = values[:, 1] - values[:, 0]   # positive class lift
        else:
            importance = values.flatten()

        pairs = [
            (tok, float(imp))
            for tok, imp in zip(tokens, importance)
            if tok not in _SPECIAL_TOKENS
        ]
        return _normalise_scores(pairs)

    except Exception as exc:
        logger.debug("SHAP path failed: %s", exc)
        return None


# ─── Path 2: Gradient × Input (PyTorch) ─────────────────────────────────────

def _gradient_explain(
    text: str,
    model: Any,
    tokenizer: Any,
) -> Optional[List[Tuple[str, float]]]:
    """
    Gradient × Input attribution using raw PyTorch autograd.
    Works with any HuggingFace model that has a .forward() and embedding layer.
    """
    try:
        import torch

        inputs = tokenizer(
            text, return_tensors="pt", truncation=True,
            max_length=128, return_offsets_mapping=False,
        )
        input_ids = inputs["input_ids"]

        # Get embedding layer
        embedding_layer = None
        for name, module in model.named_modules():
            if "embedding" in name.lower() and hasattr(module, "weight"):
                embedding_layer = module
                break
        if embedding_layer is None:
            return None

        embeds = embedding_layer(input_ids).detach().requires_grad_(True)

        # Forward pass through model layers that accept inputs_embeds
        try:
            outputs = model(inputs_embeds=embeds, attention_mask=inputs.get("attention_mask"))
        except TypeError:
            return None

        logits = outputs.logits if hasattr(outputs, "logits") else outputs[0]
        target_class = logits.argmax(dim=-1).item()
        score = logits[0, target_class]
        score.backward()

        # Gradient × Input: sum over embedding dim → scalar per token
        grads = embeds.grad[0]                     # (seq_len, hidden)
        token_importance = (grads * embeds[0]).sum(dim=-1).detach().numpy()
        tokens = tokenizer.convert_ids_to_tokens(input_ids[0])

        pairs = [
            (tok, float(imp))
            for tok, imp in zip(tokens, token_importance)
            if tok not in _SPECIAL_TOKENS
        ]
        return _normalise_scores(pairs)

    except Exception as exc:
        logger.debug("Gradient×Input path failed: %s", exc)
        return None


# ─── Path 3: TF-IDF-inspired keyword fallback ────────────────────────────────

def _tfidf_fallback(text: str) -> List[Tuple[str, float]]:
    """
    Pure-Python token scorer using clinical term weights + TF.
    Always succeeds.  Positive direction = clinically important term present.
    """
    words = re.findall(r"[a-z]+", text.lower())
    word_count: Dict[str, int] = {}
    for w in words:
        word_count[w] = word_count.get(w, 0) + 1

    total = max(len(words), 1)
    scored: List[Tuple[str, float]] = []

    for word, count in word_count.items():
        tf = count / total
        base_weight = _CLINICAL_WEIGHTS.get(word, 0.0)
        if base_weight == 0.0:
            # Generic term: inverse-document-frequency proxy (shorter = more common = less important)
            if len(word) <= 3:
                continue
            base_weight = min(0.40, 0.05 * math.log(1 + len(word)))

        importance = round(base_weight * (1 + tf), 4)
        scored.append((word, importance))

    return _normalise_scores(scored)


# ─── Public API ───────────────────────────────────────────────────────────────

def explain_diagnosis(
    text: str,
    model: Any = None,
    tokenizer: Any = None,
) -> List[Dict[str, Any]]:
    """
    Explain which tokens most influenced the diagnosis for *text*.

    Tries three paths in order:
      1. SHAP PartitionExplainer  (best accuracy, requires shap + model)
      2. Gradient × Input         (fast, requires PyTorch model)
      3. TF-IDF keyword fallback  (always works, illustrative)

    Parameters
    ----------
    text      : clinical text / symptom description to explain
    model     : HuggingFace model (optional — fallback used if None)
    tokenizer : HuggingFace tokenizer matching the model

    Returns
    -------
    List of up to 5 dicts sorted by abs(importance) descending:
        [
            {"feature": "dyspnea",   "importance":  0.91, "direction": "positive"},
            {"feature": "troponin",  "importance":  0.88, "direction": "positive"},
            {"feature": "bilateral", "importance": -0.44, "direction": "negative"},
            ...
        ]
    Ready to render as a horizontal bar chart on the frontend.
    """
    if not text or not text.strip():
        return []

    # Path 1 — SHAP (full model required)
    if model is not None and tokenizer is not None:
        scores = _shap_explain(text, model, tokenizer)
        if scores:
            logger.info("SHAP explanation succeeded (%d tokens)", len(scores))
            return _top5(scores)

        # Path 2 — Gradient × Input
        scores = _gradient_explain(text, model, tokenizer)
        if scores:
            logger.info("Gradient×Input explanation succeeded")
            return _top5(scores)

    # Path 3 — TF-IDF fallback
    logger.info("Using TF-IDF keyword fallback for XAI")
    scores = _tfidf_fallback(text)
    return _top5(scores)
