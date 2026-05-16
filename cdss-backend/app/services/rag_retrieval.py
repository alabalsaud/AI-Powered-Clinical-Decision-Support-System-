"""
RAG over local PDFs in rag_corpus/pdfs using TF-IDF retrieval (no GPU).

Flow:
  1) Put .pdf files in cdss-backend/rag_corpus/pdfs/
  2) Run: python -m scripts.ingest_rag
  3) Diagnosis LLM calls retrieve snippets and prepends them to the user prompt.

If the index is missing but PDFs exist, the first retrieval attempt rebuilds the index
(may be slow for large PDF folders).
"""
from __future__ import annotations

import logging
import pickle
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger("cdss.rag")

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PDF_DIR = BACKEND_ROOT / "rag_corpus" / "pdfs"
CHUNKS_DIR = BACKEND_ROOT / "rag_corpus" / "chunks"
INDEX_PATH = CHUNKS_DIR / "rag_tfidf.pkl"

_index_memory: Optional[Dict[str, Any]] = None


def _clear_memory_index() -> None:
    global _index_memory
    _index_memory = None


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf not installed — pip install pypdf")
        return ""
    try:
        reader = PdfReader(str(path))
        parts: List[str] = []
        for page in reader.pages:
            try:
                t = page.extract_text()
                if t:
                    parts.append(t)
            except Exception:
                continue
        return "\n\n".join(parts)
    except Exception as e:
        logger.warning("Failed to read PDF %s: %s", path.name, e)
        return ""


_WS = re.compile(r"\s+")


def _chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    text = _WS.sub(" ", text or "").strip()
    if not text:
        return []
    chunks: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + chunk_size, n)
        chunk = text[i:end].strip()
        if len(chunk) > 80:
            chunks.append(chunk)
        if end >= n:
            break
        i = max(end - overlap, i + 1)
    return chunks


def rebuild_rag_index() -> bool:
    """
    Read all PDFs under rag_corpus/pdfs and write TF-IDF index to rag_corpus/chunks/.
    Returns True if an index was written.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError:
        logger.warning("scikit-learn not installed — pip install scikit-learn")
        return False

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        logger.info("RAG: no PDFs in %s", PDF_DIR)
        if INDEX_PATH.exists():
            try:
                INDEX_PATH.unlink()
            except OSError:
                pass
        _clear_memory_index()
        return False

    all_chunks: List[str] = []
    sources: List[str] = []
    for pdf in pdfs:
        raw = _extract_pdf_text(pdf)
        if not raw:
            continue
        for ch in _chunk_text(
            raw,
            settings.RAG_CHUNK_CHARS,
            settings.RAG_CHUNK_OVERLAP,
        ):
            all_chunks.append(ch)
            sources.append(pdf.name)

    if not all_chunks:
        logger.warning("RAG: PDFs produced no extractable text")
        return False

    vectorizer = TfidfVectorizer(
        max_features=20_000,
        stop_words="english",
        min_df=1,
        max_df=0.92,
        ngram_range=(1, 2),
    )
    X = vectorizer.fit_transform(all_chunks)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "vectorizer": vectorizer,
        "X": X,
        "chunks": all_chunks,
        "sources": sources,
    }
    with open(INDEX_PATH, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    _clear_memory_index()
    logger.info(
        "RAG index rebuilt: %d chunks from %d PDFs → %s",
        len(all_chunks),
        len(pdfs),
        INDEX_PATH,
    )
    return True


def _load_index() -> Optional[Dict[str, Any]]:
    global _index_memory
    if _index_memory is not None:
        return _index_memory
    if not INDEX_PATH.exists():
        return None
    try:
        with open(INDEX_PATH, "rb") as f:
            _index_memory = pickle.load(f)
        return _index_memory
    except Exception as e:
        logger.warning("RAG failed to load index: %s", e)
        return None


def build_rag_query(context: Dict[str, Any]) -> str:
    """Turn diagnosis context into a retrieval query string."""
    parts = [str(context.get("symptoms") or "")]
    notes = context.get("clinical_notes")
    if notes:
        parts.append(str(notes))
    conds = context.get("conditions") or []
    if conds:
        parts.append(" ".join(str(c) for c in conds))
    q = " ".join(parts).strip()
    return q[:4000]


def retrieve_rag_snippets(query: str, top_k: Optional[int] = None) -> List[Dict[str, str]]:
    """
    Return top_k chunks as {source, text} for injecting into the LLM prompt.
    """
    if not settings.RAG_ENABLED:
        return []
    q = (query or "").strip()
    if not q:
        return []

    try:
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
    except ImportError:
        return []

    idx = _load_index()
    if idx is None and list(PDF_DIR.glob("*.pdf")):
        logger.info("RAG index missing — building from PDFs (first run may be slow)…")
        if rebuild_rag_index():
            idx = _load_index()

    if idx is None:
        return []

    k = top_k if top_k is not None else settings.RAG_TOP_K
    vec = idx["vectorizer"].transform([q])
    sim = cosine_similarity(vec, idx["X"])[0]
    order = np.argsort(sim)[::-1][: max(k * 3, k)]

    out: List[Dict[str, str]] = []
    seen = set()
    for i in order:
        if len(out) >= k:
            break
        score = float(sim[i])
        if score <= 0.01:
            continue
        text = idx["chunks"][i]
        src = idx["sources"][i]
        key = (src, text[:200])
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "source": src,
                "text": text[:2000],
                "score": round(score, 4),
            }
        )
    return out


def format_rag_for_prompt(snippets: List[Dict[str, str]]) -> str:
    if not snippets:
        return ""
    lines = [
        "Retrieved literature excerpts (supporting context only — not patient-specific; "
        "do not treat as definitive evidence; cite concepts generally in evidence field):",
    ]
    for i, s in enumerate(snippets, 1):
        lines.append(f"\n--- Source {i}: {s.get('source', '?')} ---\n{s.get('text', '')}")
    lines.append(
    "\nUse these excerpts only to inform differential diagnoses when relevant; "
        "if not relevant, ignore. Output JSON only as instructed."
    )
    return "\n".join(lines)
