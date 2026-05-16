#!/usr/bin/env python3
"""
Build / refresh the TF-IDF index from PDFs in rag_corpus/pdfs.

Usage (from cdss-backend):
  source .run-venv/bin/activate
  python -m scripts.ingest_rag
"""
from app.services.rag_retrieval import PDF_DIR, INDEX_PATH, rebuild_rag_index


def main() -> None:
    ok = rebuild_rag_index()
    if ok:
        print(f"OK — index written to {INDEX_PATH}")
    else:
        print(f"No index written. Add PDFs under: {PDF_DIR}")


if __name__ == "__main__":
    main()
