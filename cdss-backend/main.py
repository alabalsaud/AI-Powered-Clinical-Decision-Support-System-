"""
AI-Powered CDSS — FastAPI Backend
Main application entry point.
"""
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.db.database import engine, Base

# Import all models so SQLAlchemy creates their tables
from app.models import models  # noqa: F401

# Import routers
from app.api.routes import auth, admin, patients, diagnoses, prescriptions, treatments, audit
from app.api.routes import shorthand

logger = logging.getLogger("cdss.startup")

# ─── Global model registry ────────────────────────────────
# Populated during startup; read by /health and any route that needs inference.
ML_MODELS: Dict[str, Any] = {}
MODEL_STATUS: Dict[str, str] = {
    "bio_clinical_bert": "not_loaded",
    "biogpt_large":      "not_loaded",
}


def _load_models() -> None:
    """Load HuggingFace models into ML_MODELS. Errors are caught so the API
    still starts even when a model is unavailable (e.g. no GPU / disk space)."""
    try:
        from transformers import pipeline
        logger.info("Loading Bio_ClinicalBERT NER pipeline …")
        MODEL_STATUS["bio_clinical_bert"] = "loading"
        ML_MODELS["bio_clinical_bert"] = pipeline(
            "ner",
            model="emilyalsentzer/Bio_ClinicalBERT",
            aggregation_strategy="simple",
        )
        MODEL_STATUS["bio_clinical_bert"] = "loaded"
        logger.info("Bio_ClinicalBERT NER ready.")
    except Exception as exc:
        MODEL_STATUS["bio_clinical_bert"] = f"error: {exc}"
        logger.error("Bio_ClinicalBERT load failed: %s", exc)

    try:
        from transformers import pipeline
        logger.info("Loading BioGPT-Large text-generation pipeline …")
        MODEL_STATUS["biogpt_large"] = "loading"
        ML_MODELS["biogpt_large"] = pipeline(
            "text-generation",
            model="microsoft/BioGPT-Large",
        )
        MODEL_STATUS["biogpt_large"] = "loaded"
        logger.info("BioGPT-Large text-generation ready.")
    except Exception as exc:
        MODEL_STATUS["biogpt_large"] = f"error: {exc}"
        logger.error("BioGPT-Large load failed: %s", exc)


# ─── Lifespan (startup / shutdown) ───────────────────────
def _ensure_user_lock_columns() -> None:
    """Align legacy DBs with User.failed_login_count + User.account_locked (SQLite / Postgres)."""
    try:
        with engine.begin() as conn:
            d = conn.dialect.name
            if d == "sqlite":
                rows = conn.execute(text("PRAGMA table_info(users)")).fetchall()
                col_names = {r[1] for r in rows}
                if "failed_login_attempts" in col_names and "failed_login_count" not in col_names:
                    conn.execute(text("ALTER TABLE users RENAME COLUMN failed_login_attempts TO failed_login_count"))
                elif "failed_login_count" not in col_names:
                    conn.execute(
                        text("ALTER TABLE users ADD COLUMN failed_login_count INTEGER NOT NULL DEFAULT 0")
                    )
                if "account_locked" not in col_names:
                    conn.execute(
                        text("ALTER TABLE users ADD COLUMN account_locked BOOLEAN NOT NULL DEFAULT 0")
                    )
            elif d == "postgresql":
                conn.execute(
                    text(
                        """
                        DO $m$
                        BEGIN
                          IF EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'public' AND table_name = 'users'
                              AND column_name = 'failed_login_attempts'
                          ) AND NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'public' AND table_name = 'users'
                              AND column_name = 'failed_login_count'
                          ) THEN
                            ALTER TABLE users RENAME COLUMN failed_login_attempts TO failed_login_count;
                          END IF;
                        END
                        $m$;
                        """
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_count INTEGER NOT NULL DEFAULT 0"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_locked BOOLEAN NOT NULL DEFAULT false"
                    )
                )
    except Exception as exc:
        logger.warning("User lock column migration skipped: %s", exc)


def _widen_encrypted_patient_columns() -> None:
    """
    Encrypted PII columns must be wide enough to hold Fernet ciphertext
    (≈100–220 chars). If the DB was created before encryption was added
    (or was created with a smaller VARCHAR), widen them now.
    """
    try:
        with engine.begin() as conn:
            d = conn.dialect.name
            if d == "postgresql":
                # Use DO … IF to avoid errors when column is already wide enough.
                conn.execute(text("""
                    DO $$
                    BEGIN
                        -- first_name
                        IF (SELECT character_maximum_length
                            FROM information_schema.columns
                            WHERE table_name = 'patients' AND column_name = 'first_name') < 512 THEN
                            ALTER TABLE patients ALTER COLUMN first_name TYPE VARCHAR(512);
                        END IF;

                        -- last_name
                        IF (SELECT character_maximum_length
                            FROM information_schema.columns
                            WHERE table_name = 'patients' AND column_name = 'last_name') < 512 THEN
                            ALTER TABLE patients ALTER COLUMN last_name TYPE VARCHAR(512);
                        END IF;

                        -- date_of_birth
                        IF (SELECT character_maximum_length
                            FROM information_schema.columns
                            WHERE table_name = 'patients' AND column_name = 'date_of_birth') < 256 THEN
                            ALTER TABLE patients ALTER COLUMN date_of_birth TYPE VARCHAR(256);
                        END IF;

                        -- phone
                        IF (SELECT character_maximum_length
                            FROM information_schema.columns
                            WHERE table_name = 'patients' AND column_name = 'phone') < 256 THEN
                            ALTER TABLE patients ALTER COLUMN phone TYPE VARCHAR(256);
                        END IF;

                        -- email
                        IF (SELECT character_maximum_length
                            FROM information_schema.columns
                            WHERE table_name = 'patients' AND column_name = 'email') < 512 THEN
                            ALTER TABLE patients ALTER COLUMN email TYPE VARCHAR(512);
                        END IF;
                    END
                    $$;
                """))
                logger.info("Patient PII column widths verified/updated.")
            elif d == "sqlite":
                # SQLite doesn't enforce VARCHAR lengths so nothing to do.
                pass
    except Exception as exc:
        logger.warning("Patient PII column migration skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: DB tables + schema migrations (models load lazily on first use)
    Base.metadata.create_all(bind=engine)
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_image TEXT"))
    except Exception:
        pass
    _ensure_user_lock_columns()
    _widen_encrypted_patient_columns()

    logger.info("Startup complete — NLP models will load on first inference request.")
    yield
    # Shutdown: release model memory
    ML_MODELS.clear()
    logger.info("ML models unloaded.")


# ─── FastAPI app ──────────────────────────────────────────
app = FastAPI(
    title="AI-Powered Clinical Decision Support System",
    description="Backend API for AI-CDSS — Alfaisal University SE495 Capstone",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── CORS (allow React dev server) ────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────
PREFIX = "/api/v1"
app.include_router(auth.router,          prefix=PREFIX)
app.include_router(admin.router,         prefix=PREFIX)
app.include_router(patients.router,      prefix=PREFIX)
app.include_router(diagnoses.router,     prefix=PREFIX)
app.include_router(prescriptions.router, prefix=PREFIX)
app.include_router(treatments.router,    prefix=PREFIX)
app.include_router(audit.router,         prefix=PREFIX)
app.include_router(shorthand.router,     prefix="/api")


# ─── Health check ─────────────────────────────────────────
@app.get("/health", tags=["System"])
def health_check():
    all_loaded = all(v == "loaded" for v in MODEL_STATUS.values())
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": "1.0.0",
        "models": MODEL_STATUS,
        "models_ready": all_loaded,
    }


@app.get("/", tags=["System"])
def root():
    return {
        "message": "AI-CDSS API running",
        "docs": "/docs",
        "health": "/health",
    }
