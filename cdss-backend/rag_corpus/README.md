# RAG document corpus (local PDFs)

Put **downloaded PDFs here** for a future RAG pipeline.

## Folder layout

| Path | Purpose |
|------|--------|
| **`pdfs/`** | Your PDF files (PMC articles, guidelines you have rights to use, etc.) |
| `chunks/` | *(future)* Extracted text chunks — ignored by git |
| `embeddings/` | *(future)* Cached vectors — ignored by git |

## What to do now

1. Download PDFs from PMC (or other sources you are allowed to use).
2. Save them under:
   ```text
   cdss-backend/rag_corpus/pdfs/
   ```
   Example: `cdss-backend/rag_corpus/pdfs/PMC13155452.pdf` or keep publisher filenames.

3. **Do not** put patient data, exports with PHI, or internal hospital records in this folder unless your institution approves and you have a separate security review.

## Git

- **`pdfs/*.pdf` is gitignored** — large files stay on your machine and are not pushed by default.
- The folder is still tracked via `pdfs/.gitkeep` so the path exists for everyone who clones the repo.

## Licensing & ethics (read before indexing)

- **PMC**: Many articles are open access under **specific licenses** (CC BY, etc.). Check each article’s **“Copyright / License”** on the PMC HTML page before using text in a product or publication.
- **Course / research demo**: Usually you still need to **cite sources** and respect **non-commercial** or **attribution** clauses where they apply.
- This project does **not** automatically scrape PMC; you **manually** place files you have reviewed.

## Next step (when you implement RAG)

- Add an ingest script that: reads `pdfs/` → extracts text → chunks → embeds → stores (e.g. `pgvector` or a local vector store).
- Wire retrieval into the LLM diagnosis prompt in `app/services/llm_diagnosis.py` (or agents pipeline).

If you rename or organize PDFs, use **ASCII filenames** when possible to avoid path issues on some systems.

---

## RAG is implemented (TF‑IDF over PDFs)

1. Put `.pdf` files in `pdfs/`.
2. Install deps: `pip install pypdf scikit-learn` (or `pip install -r requirements.txt`).
3. Build index:
   ```bash
   cd cdss-backend
   source .run-venv/bin/activate   # if you use a venv
   python -m scripts.ingest_rag
   ```
4. Restart the API. **AI Diagnosis** (`POST /api/diagnose`) will prepend top matching chunks to the LLM prompt.
5. Response JSON may include `rag: { "used": true, "chunks": 5, "sources": ["file.pdf", ...] }`.

**Toggle / tune (optional)** in `cdss-backend/.env`:

```env
RAG_ENABLED=true
RAG_TOP_K=5
```

If the index is missing, the **first** diagnosis request may trigger a slow auto-build when PDFs exist.

