"""Application configuration loaded from environment via pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> str:
    """Walk up from this module to find the repo-root .env."""
    p = Path(__file__).resolve()
    for parent in [p.parent, *p.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            return str(candidate)
    return ".env"


class Settings(BaseSettings):
    """All runtime configuration. Values are read from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=_find_env_file(), env_file_encoding="utf-8", extra="ignore"
    )

    # Socrata / datos.gov.co
    socrata_app_token: str = ""
    socrata_domain: str = "www.datos.gov.co"

    # Supabase
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_secret_key: str = ""

    # LLM via LiteLLM (provider-agnostic, OpenAI-compatible)
    litellm_model: str = "gpt-4.1-mini"
    litellm_small_model: str = "qwen3.7-plus"
    litellm_api_base: str = ""
    litellm_api_key: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""

    # Embeddings (Gemini free tier) — multiple keys for quota cycling
    gemini_api_key: str = ""
    gemini_api_keys: str = ""

    # Telegram
    telegram_bot_token: str = ""

    # Misc
    log_level: str = "INFO"
    numpy_fallback: bool = False
    enable_reranker: bool = True
    # LLM latency budget (interactive latency guard against slow/flaky providers)
    llm_timeout_s: float = 15.0
    llm_max_attempts: int = 2
    llm_backoff_max_s: float = 2.0
    # Reranker latency budget
    rerank_timeout_s: float = 8.0
    rerank_max_candidates: int = 8
    cors_origins: list[str] = [
        "http://localhost:3000",
        "https://concurso-datos-ia.vercel.app",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @property
    def litellm_api_key_resolved(self) -> str:
        return self.litellm_api_key or self.openai_api_key

    @property
    def supabase_key_resolved(self) -> str:
        return self.supabase_service_key or self.supabase_secret_key

    @property
    def gemini_keys_list(self) -> list[str]:
        keys = [k.strip() for k in self.gemini_api_keys.split(",") if k.strip()]
        if not keys and self.gemini_api_key:
            keys = [self.gemini_api_key]
        return keys


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
