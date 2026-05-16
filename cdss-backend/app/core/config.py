from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://cdss_user:cdss_password@localhost:5432/cdss_db"

    # ── JWT ───────────────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-this-to-a-long-random-string-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 14400   # 10 days — no annoying mid-session expiry

    # ── Patient PII encryption (Fernet) ───────────────────────────────────────
    # Leave empty in dev — a key will be derived from SECRET_KEY automatically.
    PII_FERNET_KEY: str = ""

    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "AI-CDSS"
    DEBUG: bool = True
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ── LLM Provider selection ────────────────────────────────────────────────
    # ollama | huggingface | openai | openrouter (openai/openrouter share OPENAI_* vars)
    LLM_PROVIDER: str = "ollama"

    # ── Ollama (local) ────────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "llama3"
    OLLAMA_API_KEY: str = "ollama"

    # ── Hugging Face Inference (OpenAI-compatible router) ───────────────────
    # Token: https://huggingface.co/settings/tokens — enable "Inference" permission
    HF_TOKEN: str = ""
    HF_BASE_URL: str = "https://router.huggingface.co/v1"
    HF_MODEL: str = "meta-llama/Llama-3.2-3B-Instruct"

    # ── OpenAI / OpenRouter ───────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"

    # ── Shared LLM parameters ────────────────────────────────────────────────
    LLM_TIMEOUT_SECONDS: float = 90.0
    LLM_MAX_RETRIES: int = 3
    LLM_RETRY_BACKOFF_SECONDS: float = 1.5
    # Some endpoints (e.g. older Ollama builds) reject response_format; set False to disable.
    LLM_USE_JSON_OBJECT: bool = True

    # ── Email / SMTP (Gmail) ──────────────────────────────────────────────────
    # Use a Gmail App Password (not your main Gmail password).
    # Enable: Google Account → Security → 2-Step Verification → App passwords
    SMTP_EMAIL: str = ""          # e.g. yourname@gmail.com
    SMTP_PASSWORD: str = ""       # 16-char Gmail App Password
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587

    # ── RAG (retrieval from rag_corpus/pdfs) ──────────────────────────────────
    # After adding PDFs, run: python -m scripts.ingest_rag  (from cdss-backend)
    RAG_ENABLED: bool = True
    RAG_TOP_K: int = 5
    RAG_CHUNK_CHARS: int = 1200
    RAG_CHUNK_OVERLAP: int = 200

    # ── Computed helpers ──────────────────────────────────────────────────────
    @property
    def llm_provider_norm(self) -> str:
        return (self.LLM_PROVIDER or "ollama").strip().lower()

    @property
    def hf_api_key(self) -> str:
        """HF token from HF_TOKEN, or OPENAI_API_KEY when it starts with hf_."""
        tok = (self.HF_TOKEN or "").strip()
        if tok:
            return tok
        oa = (self.OPENAI_API_KEY or "").strip()
        if oa.startswith("hf_"):
            return oa
        return ""

    @property
    def llm_configured(self) -> bool:
        """True when at least one LLM backend is usable."""
        p = self.llm_provider_norm
        if p == "ollama":
            return bool(self.OLLAMA_BASE_URL and self.OLLAMA_MODEL)
        if p == "huggingface":
            return bool(self.hf_api_key and (self.HF_MODEL or self.LLM_MODEL))
        return bool(self.OPENAI_API_KEY and self.OPENAI_API_KEY.strip())

    @property
    def active_llm_base_url(self) -> str:
        p = self.llm_provider_norm
        if p == "ollama":
            return self.OLLAMA_BASE_URL.rstrip("/")
        if p == "huggingface":
            return self.HF_BASE_URL.rstrip("/")
        return self.OPENAI_BASE_URL.rstrip("/")

    @property
    def active_llm_model(self) -> str:
        p = self.llm_provider_norm
        if p == "ollama":
            return self.OLLAMA_MODEL
        if p == "huggingface":
            return self.HF_MODEL or self.LLM_MODEL
        return self.LLM_MODEL

    @property
    def active_llm_api_key(self) -> str:
        p = self.llm_provider_norm
        if p == "ollama":
            return self.OLLAMA_API_KEY
        if p == "huggingface":
            return self.hf_api_key
        return self.OPENAI_API_KEY.strip()

    @property
    def origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
