import hashlib
import json
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from docagent.config import settings


def now():
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class JobAdmission(Base):
    """Singleton row serializing queue admission across API processes."""

    __tablename__ = "job_admission"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class UserSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str] = mapped_column(String(100), index=True)
    login: Mapped[str] = mapped_column(String(100), default="")
    token: Mapped[str] = mapped_column(Text, default="")
    csrf: Mapped[str] = mapped_column(String(100))
    oauth_state: Mapped[str] = mapped_column(String(100), default="")
    oauth_verifier: Mapped[str] = mapped_column(String(150), default="")
    oauth_started: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires: Mapped[datetime] = mapped_column(DateTime)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(100), index=True)
    repository: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="Waiting for worker")
    config: Mapped[dict] = mapped_column(JSON)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    baseline_hash: Mapped[str] = mapped_column(String(64), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    # Encrypted, temporary credential for queued workers. Removed at job completion.
    credential: Mapped[str] = mapped_column(Text, default="")
    worker_id: Mapped[str] = mapped_column(String(36), default="")
    resolved_commit: Mapped[str] = mapped_column(String(40), default="", server_default="")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class JobAccess(Base):
    __tablename__ = "job_access"
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    principal: Mapped[str] = mapped_column(String(100), primary_key=True)
    login: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))
    created: Mapped[datetime] = mapped_column(DateTime, default=now)


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    baseline_hash: Mapped[str] = mapped_column(String(64))
    package_sha256: Mapped[str] = mapped_column(String(64))
    created: Mapped[datetime] = mapped_column(DateTime, default=now)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    baseline_hash: Mapped[str] = mapped_column(String(64))
    stage: Mapped[str] = mapped_column(String(30))
    decision: Mapped[str] = mapped_column(String(30))
    reviewer: Mapped[str] = mapped_column(String(100))
    comment: Mapped[str] = mapped_column(Text)
    created: Mapped[datetime] = mapped_column(DateTime, default=now)


class TestResult(Base):
    __tablename__ = "test_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    baseline_hash: Mapped[str] = mapped_column(String(64))
    test_case_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(30))
    actual: Mapped[str] = mapped_column(Text)
    evidence_reference: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20))
    reviewer: Mapped[str] = mapped_column(String(100))
    created: Mapped[datetime] = mapped_column(DateTime, default=now)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[datetime] = mapped_column(DateTime, default=now)


class ScanCache(Base):
    __tablename__ = "scan_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    updated: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


@lru_cache
def engine():
    cfg = settings()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    e = create_engine(
        cfg.database_url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False, "timeout": 30}
        if cfg.database_url.startswith("sqlite")
        else {},
    )
    if cfg.database_url.startswith("sqlite"):

        @event.listens_for(e, "connect")
        def sqlite_pragmas(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")

    return e


def session_factory():
    return sessionmaker(engine(), expire_on_commit=False)


def init_db():
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    with engine().begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def save_cache(db, key, payload):
    """Concurrent jobs may discover the same content; writes must be idempotent."""
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    db.execute(
        insert(ScanCache)
        .values(key=key, payload=payload, updated=now())
        .on_conflict_do_nothing(index_elements=["key"])
    )
