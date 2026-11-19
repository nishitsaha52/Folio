from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCAGENT_", env_file=".env", extra="ignore")
    env: str = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    public_url: str = "http://localhost:8000"
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    database_url: str = "sqlite:///.data/docagent.db"
    data_dir: Path = Path(".data")
    storage_backend: Literal["local", "s3"] = "local"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""
    s3_prefix: str = "docagent"
    s3_access_key_id: SecretStr = SecretStr("")
    s3_secret_access_key: SecretStr = SecretStr("")
    s3_session_token: SecretStr = SecretStr("")
    s3_addressing_style: Literal["auto", "path", "virtual"] = "auto"
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

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def storage(self):
        if self.storage_backend == "s3":
            if not self.s3_bucket.strip() or any(c in self.s3_bucket for c in "/\\:"):
                raise ValueError("S3 storage requires DOCAGENT_S3_BUCKET (a bucket name, not a URL)")
            self.s3_prefix = self.s3_prefix.strip("/")
            if self.s3_prefix and (
                any(part in {"", ".", ".."} for part in self.s3_prefix.split("/"))
                or any(c in self.s3_prefix for c in "\\:")
                or any(ord(c) < 32 for c in self.s3_prefix)
            ):
                raise ValueError("DOCAGENT_S3_PREFIX must be a relative object prefix without traversal")
            if self.s3_endpoint_url:
                endpoint = urlsplit(self.s3_endpoint_url)
                if (
                    endpoint.scheme not in {"http", "https"}
                    or not endpoint.hostname
                    or endpoint.username
                    or endpoint.password
                    or endpoint.query
                    or endpoint.fragment
                    or endpoint.path not in {"", "/"}
                ):
                    raise ValueError(
                        "DOCAGENT_S3_ENDPOINT_URL must be an HTTP(S) service URL without credentials"
                    )
            access_key = self.s3_access_key_id.get_secret_value()
            secret_key = self.s3_secret_access_key.get_secret_value()
            if bool(access_key) != bool(secret_key):
                raise ValueError("Set both DOCAGENT_S3_ACCESS_KEY_ID and DOCAGENT_S3_SECRET_ACCESS_KEY")
            if self.s3_session_token.get_secret_value() and not access_key:
                raise ValueError("DOCAGENT_S3_SESSION_TOKEN requires explicit S3 access and secret keys")
        return self

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
