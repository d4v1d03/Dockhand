"""Settings, read from the environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # llm (openai-compatible); validated where used
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.2

    # infra
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "sqlite:///data/dockhand.db"

    # sandbox
    sandbox_image: str = "dockhand-sandbox:latest"
    sandbox_network: str = "bridge"  # or "none"
    sandbox_memory: str = "2g"
    sandbox_cpus: float = 2.0
    sandbox_ttl_minutes: int = 60

    # agent limits
    max_steps: int = 40
    max_tool_output_chars: int = 8000
    default_tool_timeout_s: int = 120
    max_tool_timeout_s: int = 600


@lru_cache
def get_settings() -> Settings:
    return Settings()
