"""Application configuration loaded from environment via pydantic-settings."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Values are read from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Socrata / datos.gov.co
    socrata_app_token: str = ""
    socrata_domain: str = "www.datos.gov.co"

    # Supabase
    supabase_url: str = ""
    supabase_service_key: str = ""

    # LLM via LiteLLM (provider-agnostic, OpenAI-compatible)
    litellm_model: str = "gpt-4.1-mini"
    litellm_api_base: str = ""
    litellm_api_key: str = ""
    # Fallback direct provider for the demo laptop
    openai_api_key: str = ""

    # Embeddings (Gemini free tier)
    gemini_api_key: str = ""

    # Telegram
    telegram_bot_token: str = ""

    # Misc
    log_level: str = "INFO"

    @property
    def litellm_api_key_resolved(self) -> str:
        """Resolve the API key: prefer LiteLLM key, fall back to OpenAI key."""
        return self.litellm_api_key or self.openai_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
