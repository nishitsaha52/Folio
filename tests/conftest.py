import os
from pathlib import Path

import pytest

# Test state never shares credentials or the application's database.
os.environ["DOCAGENT_ENV"] = "development"
os.environ["DOCAGENT_JOB_BACKEND"] = "local"
os.environ["DOCAGENT_REDIS_BACKEND"] = "fake"
os.environ["DOCAGENT_DATA_DIR"] = str(Path(".data/test-default").resolve())
os.environ["DOCAGENT_DATABASE_URL"] = "sqlite:///" + str(Path(".data/test-default/test.db").resolve())


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    from docagent.config import settings
    from docagent.db import engine
    from docagent.security import cipher

    monkeypatch.setenv("DOCAGENT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DOCAGENT_DATABASE_URL", "sqlite:///" + str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("DOCAGENT_REVIEWERS", "reviewer")
    settings.cache_clear()
    engine.cache_clear()
    cipher.cache_clear()
    yield tmp_path
    engine().dispose()
    engine.cache_clear()
    settings.cache_clear()
    cipher.cache_clear()


@pytest.fixture
def client(isolated, monkeypatch):
    import docagent.api as api
    from fastapi.testclient import TestClient

    monkeypatch.setattr(api, "enqueue", lambda job_id: None)
    with TestClient(api.create_app()) as client:
        info = client.get("/api/session").json()
        client.headers["X-CSRF-Token"] = info["csrf_token"]
        yield client


@pytest.fixture
def completed(client):
    from docagent.jobs import run_job

    response = client.post("/api/demo", json={})
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    run_job(job_id)
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "completed", job
    return job


@pytest.fixture
def reviewer(client):
    from docagent.db import UserSession, session_factory
    from docagent.security import token_hash

    with session_factory()() as db:
        user = db.get(UserSession, token_hash(client.cookies["docagent_session"]))
        user.login = "reviewer"
        db.commit()
    return client
