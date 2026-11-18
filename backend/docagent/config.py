from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCAGENT_", env_file=".env", extra="ignore")
    env: str = "development"
    public_url: str = "http://localhost:8000"
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    database_url: str = "sqlite:///.data/docagent.db"
    data_dir: Path = Path(".data")
    encryption_key: SecretStr = SecretStr("")
    job_backend: Literal["local", "celery"] = "local"
    redis_backend: Literal["fake", "real"] = "fake"
    redis_url: str = "redis://localhost:6379/0"
    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")
    github_oauth_scopes: str = "read:user"
    reviewers: str = ""
    openai_api_key: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    openai_model: str = ""
    anthropic_model: str = ""
    gemini_model: str = ""
    retention_days: int = 30
    session_hours: int = 24
    max_archive_bytes: int = 100_000_000
    max_expanded_bytes: int = 300_000_000
    max_archive_files: int = 50_000
    max_file_bytes: int = 512_000
    max_concurrent_jobs: int = 2
    test_execution_enabled: bool = False
    test_image: str = ""
    test_timeout: int = 180
    frontend_dir: Path = Path("frontend/dist")

    @model_validator(mode="after")
    def production(self):
        if self.env == "production":
            if not self.encryption_key.get_secret_value():
                raise ValueError("Production requires DOCAGENT_ENCRYPTION_KEY")
            if not self.public_url.startswith("https://"):
                raise ValueError("Production requires an HTTPS public URL")
            if not self.database_url.startswith("postgresql") or self.job_backend != "celery":
                raise ValueError("Production requires PostgreSQL and Celery")
        if self.job_backend == "celery" and self.redis_backend != "real":
            raise ValueError("Celery requires DOCAGENT_REDIS_BACKEND=real; fakeredis requires local jobs")
        if self.max_concurrent_jobs < 1:
            raise ValueError("max_concurrent_jobs must be positive")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
