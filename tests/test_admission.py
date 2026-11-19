import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from docagent.config import settings
from docagent.db import Job, session_factory
from sqlalchemy import func, select


@pytest.mark.parametrize("limit", ["owner", "global"])
def test_concurrent_admission_cannot_exceed_limits(client, monkeypatch, limit):
    import docagent.api as api

    monkeypatch.setattr(settings(), "max_concurrent_jobs", 1 if limit == "owner" else 16)
    existing = 0 if limit == "owner" else 15
    with session_factory()() as db:
        for _ in range(existing):
            db.add(Job(id=str(uuid.uuid4()), owner="other", repository="owner/repo", config={}))
        db.commit()
    barrier = threading.Barrier(2)

    class GitHub:
        def __init__(self, token):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def repository(self, name):
            # Both requests arrive together after repository validation. The old
            # count-before-validation implementation accepted both of them.
            barrier.wait(timeout=10)
            return {"private": False}

    monkeypatch.setattr(api, "GitHub", GitHub)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(
            lambda _: client.post("/api/jobs", json={"repository": "owner/repo"}), range(2),
        ))
    assert sorted(response.status_code for response in responses) == [202, 429]
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == existing + 1
