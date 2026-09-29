from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CivicPulse"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://civicpulse:civicpulse@postgres:5432/civicpulse"
    redis_url: str = "redis://redis:6379/0"
    triage_provider: str = "simulated"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.1-8b-instant"
    ollama_model: str = "llama3.2:1b"
    ollama_base_url: str = "http://ollama:11434"
    triage_timeout_seconds: float = 10.0
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_timeout_seconds: float = 10.0
    cors_origins: str = "http://localhost:8080"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
