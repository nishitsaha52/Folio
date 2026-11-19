"""Opt-in acceptance against disposable PostgreSQL/Redis services and a real worker."""

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DOCAGENT_INTEGRATION_DATABASE_URL") or not os.getenv("DOCAGENT_INTEGRATION_REDIS_URL"),
    reason="Set integration service URLs to run PostgreSQL/Redis/Celery acceptance",
)


def test_postgres_redis_and_celery_worker(isolated, monkeypatch):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from docagent.config import settings
    from docagent.db import Base, DocumentVersion, Job, engine, init_db, session_factory
    from docagent.queue import create_redis_client
    from docagent.schemas import AnalysisConfig
    from docagent.storage import artifact_storage

    monkeypatch.setenv("DOCAGENT_DATABASE_URL", os.environ["DOCAGENT_INTEGRATION_DATABASE_URL"])
    monkeypatch.setenv("DOCAGENT_REDIS_URL", os.environ["DOCAGENT_INTEGRATION_REDIS_URL"])
    monkeypatch.setenv("DOCAGENT_REDIS_BACKEND", "real")
    monkeypatch.setenv("DOCAGENT_JOB_BACKEND", "celery")
    settings.cache_clear()
    engine.cache_clear()
    init_db()
    with engine().connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    redis = create_redis_client(settings())
    try:
        assert redis.ping()
    finally:
        redis.close()

    job_id = str(uuid.uuid4())
    config = AnalysisConfig(repository="demo/inventory", documents=["srs"], formats=["md"])
    with session_factory()() as db:
        db.add(Job(id=job_id, owner="integration", repository=config.repository,
                   config=config.model_dump(mode="json")))
        db.commit()

    repository = Path(__file__).resolve().parents[2]
    with (isolated / "worker.log").open("wb") as output:
        worker = subprocess.Popen(
            [sys.executable, "-m", "celery", "-A", "docagent.worker:celery", "worker",
             "--pool=solo", "--loglevel=WARNING", "--without-gossip", "--without-mingle", "--without-heartbeat"],
            cwd=repository, stdout=output, stderr=subprocess.STDOUT,
        )
        try:
            # This exercises broker delivery and a separate process, rather than eager mode.
            from docagent.jobs import enqueue

            enqueue(job_id)
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                assert worker.poll() is None, "The integration worker exited before completing its job"
                with session_factory()() as db:
                    job = db.get(Job, job_id)
                    assert job.status != "failed", job.message
                    if job.status == "completed":
                        assert job.progress == 100
                        assert db.get(DocumentVersion, (job_id, job.version)) is not None
                        assert artifact_storage().download(job_id, job.version).path.is_file()
                        break
                time.sleep(0.2)
            else:
                pytest.fail("The integration worker did not complete within 120 seconds")
        finally:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)
            artifact_storage().delete_job(job_id)
            with session_factory()() as db:
                job = db.get(Job, job_id)
                if job:
                    db.delete(job)
                    db.commit()
