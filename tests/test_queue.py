import threading
from unittest.mock import Mock

import fakeredis
import pytest
import redis
from docagent.config import Settings
from docagent.queue import LocalJobQueue, create_redis_client
from fastapi.testclient import TestClient
from pydantic import ValidationError


def forbid_real_redis(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Fake mode attempted a real Redis connection")

    monkeypatch.setattr(redis.connection.Connection, "_connect", fail)


def test_default_fake_client_ignores_real_url(monkeypatch):
    forbid_real_redis(monkeypatch)
    config = Settings(_env_file=None, redis_url="redis://127.0.0.1:1/0")
    first = create_redis_client(config)
    second = create_redis_client(config)
    try:
        assert isinstance(first, fakeredis.FakeRedis)
        first.set("application-state", "one")
        assert first.get("application-state") == "one"
        assert second.get("application-state") is None
    finally:
        first.close()
        second.close()


def test_fake_queue_consumes_fifo_and_drains_on_shutdown(monkeypatch):
    forbid_real_redis(monkeypatch)
    started, release = threading.Event(), threading.Event()
    received = []

    def handle(job_id):
        if job_id == "first":
            started.set()
            assert release.wait(5)
        received.append(job_id)

    queue = LocalJobQueue(Settings(_env_file=None, max_concurrent_jobs=1), handle)
    try:
        futures = [queue.enqueue("first")]
        assert started.wait(5)
        futures.extend(queue.enqueue(job_id) for job_id in ("second", "third"))
        assert queue.client.lrange(queue.key, 0, -1) == ["second", "third"]
    finally:
        release.set()
        queue.close()
    for future in futures:
        future.result(timeout=5)
    assert received == ["first", "second", "third"]
    queue.close()
    with pytest.raises(RuntimeError, match="closed"):
        queue.enqueue("fourth")


def test_real_client_uses_configured_url(monkeypatch):
    factory = Mock()
    monkeypatch.setattr(redis.Redis, "from_url", factory)
    config = Settings(_env_file=None, redis_backend="real", redis_url="redis://redis:6379/2")
    assert create_redis_client(config) is factory.return_value
    factory.assert_called_once_with(
        config.redis_url, decode_responses=True, socket_connect_timeout=5, socket_timeout=5
    )


def test_unavailable_real_redis_fails_without_silent_fallback(monkeypatch):
    client = Mock()
    client.ping.side_effect = redis.ConnectionError("credential-must-not-appear")
    monkeypatch.setattr(redis.Redis, "from_url", Mock(return_value=client))
    with pytest.raises(RuntimeError, match="Local queue unavailable") as error:
        LocalJobQueue(Settings(_env_file=None, redis_backend="real"), Mock())
    assert "credential-must-not-appear" not in str(error.value)
    client.close.assert_called_once()


@pytest.mark.parametrize(
    "options",
    [
        {"redis_backend": "unknown"},
        {"job_backend": "celery", "redis_backend": "fake"},
        {"max_concurrent_jobs": 0},
    ],
)
def test_invalid_queue_configuration(options):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **options)


def test_production_requires_real_redis():
    options = dict(
        _env_file=None,
        env="production",
        encryption_key="configured-in-deployment",
        public_url="https://example.org",
        database_url="postgresql+psycopg://localhost/docagent",
        job_backend="celery",
    )
    with pytest.raises(ValidationError, match="REDIS_BACKEND=real"):
        Settings(**options, redis_backend="fake")
    assert Settings(**options, redis_backend="real").redis_backend == "real"


def test_demo_runs_through_fake_queue_without_redis(isolated, monkeypatch):
    import docagent.api as api
    import docagent.jobs as jobs

    forbid_real_redis(monkeypatch)
    finished = threading.Event()
    original = jobs.run_job

    def run_and_signal(job_id):
        try:
            original(job_id)
        finally:
            finished.set()

    monkeypatch.setattr(jobs, "run_job", run_and_signal)
    with TestClient(api.create_app()) as client:
        assert isinstance(jobs.local_queue.client, fakeredis.FakeRedis)
        client.headers["X-CSRF-Token"] = client.get("/api/session").json()["csrf_token"]
        response = client.post("/api/demo", json={})
        assert response.status_code == 202, response.text
        job_id = response.json()["id"]
        assert finished.wait(30), "Local queue did not finish the demo"
        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "completed", job
        package = client.get(f"/api/jobs/{job_id}/download")
        assert package.status_code == 200
        assert package.content.startswith(b"PK")
    assert jobs.local_queue is None
    # A second application lifetime gets a fresh, usable queue.
    with TestClient(api.create_app()):
        assert jobs.local_queue.client.ping()
    assert jobs.local_queue is None
