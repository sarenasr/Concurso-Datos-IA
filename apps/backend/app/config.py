"""Application configuration loaded from environment via pydantic-settings."""

from functools import lru_cache
from pathlib import Path

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
    litellm_model: str = "anthropic/claude-sonnet-4.5"
    litellm_small_model: str = "anthropic/claude-sonnet-4.5"
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
    # Reranker: hosted cross-encoder (cohere/rerank-v3.5) via OpenRouter, using
    # the same OPENROUTER_API_KEY as chat/embeddings. Fast (~200-500ms) and
    # accurate, so it's safe to leave on; it no-ops gracefully with no key.
    enable_reranker: bool = True
    # LLM latency budget (interactive latency guard against slow/flaky providers)
    llm_timeout_s: float = 15.0
    llm_max_attempts: int = 2
    llm_backoff_max_s: float = 2.0
    # Reranker: single HTTP call to OpenRouter's hosted rerank endpoint (a
    # cross-encoder, not an LLM completion) — cheap enough to allow a larger
    # candidate batch than the old LLM-based reranker.
    rerank_model: str = "cohere/rerank-4-pro"
    rerank_timeout_s: float = 3.0
    rerank_max_candidates: int = 20
    cors_origins: str = (
        "http://localhost:3000,"
        "https://concurso-datos-ia.vercel.app,"
        "https://concurso-datos-bc75r6uwk-sarenasrs-projects.vercel.app,"
        "https://concurso-datos-ia-git-main-sarenasrs-projects.vercel.app"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]

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
