import logging
from datetime import timedelta

import pytest
from docagent.db import Job, init_db, now, session_factory
from docagent.schemas import AnalysisConfig


def test_worker_recovery_reuses_the_persisted_commit(isolated, monkeypatch):
    import docagent.jobs as jobs

    init_db()
    config = AnalysisConfig(repository="owner/repo", ref="main", formats=["md"])
    with session_factory()() as db:
        job = Job(id="00000000-0000-0000-0000-000000000001", owner="owner", repository="owner/repo",
                  config=config.model_dump(mode="json"))
        db.add(job)
        db.commit()
        job_id = job.id
    downloads, resolutions = [], []

    class GitHub:
        def __init__(self, token):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def repository(self, repository):
            return {"private": False, "default_branch": "main"}

        def resolve(self, repository, ref):
            resolutions.append(ref)
            return ("a" if len(resolutions) == 1 else "b") * 40

        def download(self, repository, commit, root):
            downloads.append(commit)
            if len(downloads) == 1:
                raise SystemExit("Simulated worker termination after commit resolution")
            root.mkdir()
            (root / "app.py").write_text("def run():\n    return 1\n")

    monkeypatch.setattr(jobs, "GitHub", GitHub)
    monkeypatch.setattr(jobs, "export_job", lambda *args, **kwargs: None)
    with pytest.raises(SystemExit):
        jobs.run_job(job_id)
    with session_factory()() as db:
        job = db.get(Job, job_id)
        assert job.resolved_commit == "a" * 40
        job.lease_until = now() - timedelta(seconds=1)
        db.commit()
    jobs.run_job(job_id)
    assert resolutions == ["main"]
    assert downloads == ["a" * 40, "a" * 40]
    with session_factory()() as db:
        job = db.get(Job, job_id)
        assert job.status == "completed"
        assert job.analysis["commit"] == job.resolved_commit == "a" * 40
        assert job.config["ref"] == "main"


def test_replaced_workers_cannot_pin_commits_or_change_progress(isolated):
    from docagent.jobs import WorkerLeaseLost, pin_commit, set_progress

    init_db()
    with session_factory()() as db:
        db.add(Job(id="job", owner="owner", repository="owner/repo", config={},
                   worker_id="replacement", status="running", progress=55))
        db.commit()
    with pytest.raises(WorkerLeaseLost):
        pin_commit("job", "old-worker", "b" * 40)
    with pytest.raises(WorkerLeaseLost):
        set_progress("job", "old-worker", 25, "Old progress")
    assert pin_commit("job", "replacement", "a" * 40) == "a" * 40
    assert pin_commit("job", "replacement", "b" * 40) == "a" * 40
    with session_factory()() as db:
        job = db.get(Job, "job")
        assert job.progress == 55
        job.status = "completed"
        job.progress = 100
        db.commit()
    with pytest.raises(WorkerLeaseLost):
        set_progress("job", "replacement", 80, "Late progress")


def test_job_lifecycle_and_failure_diagnostics_do_not_log_exception_content(isolated, monkeypatch, caplog):
    import docagent.jobs as jobs
    from docagent.logging_config import job_log_context

    init_db()
    config = AnalysisConfig(repository="demo/inventory", formats=["md"])
    job_id = "00000000-0000-0000-0000-000000000002"
    with session_factory()() as db:
        db.add(Job(id=job_id, owner="owner", repository=config.repository, config=config.model_dump(mode="json")))
        db.commit()

    def fail(*_args, **_kwargs):
        raise ValueError("credential-and-source-content")

    monkeypatch.setattr(jobs, "scan_repository", fail)
    with caplog.at_level(logging.INFO, logger="docagent"):
        jobs.run_job(job_id)
    assert f"Job started job_id={job_id}" in caplog.text
    assert "progress=25" in caplog.text
    assert f"Job failed job_id={job_id}" in caplog.text
    assert "error_type=ValueError" in caplog.text
    assert "credential-and-source-content" not in caplog.text
    assert job_log_context.get() == "-"
    with session_factory()() as db:
        assert db.get(Job, job_id).status == "failed"


def test_ai_batch_progress_checkpoints_cache_without_sqlite_writer_lock(isolated, monkeypatch, caplog):
    import docagent.jobs as jobs
    import docagent.llm as llm
    from docagent.db import ScanCache
    from docagent.schemas import LLMOutput
    from sqlalchemy import func, select

    init_db()
    config = AnalysisConfig(repository="demo/inventory", formats=["md"],
                            providers=[{"provider": "gemini", "model": "synthetic-model"}])
    job_id = "00000000-0000-0000-0000-000000000003"
    with session_factory()() as db:
        db.add(Job(id=job_id, owner="owner", repository=config.repository, config=config.model_dump(mode="json")))
        db.commit()
    monkeypatch.setattr(llm, "call_provider", lambda *args, **kwargs: (LLMOutput(requirements=[], gaps=[]), {}))
    with caplog.at_level(logging.INFO, logger="docagent"):
        jobs.run_job(job_id)
    assert "Synthesized requirements (batch" in caplog.text
    with session_factory()() as db:
        assert db.get(Job, job_id).status == "completed"
        assert db.scalar(select(func.count()).select_from(ScanCache)) > 0


def test_restart_preserves_last_stage_and_does_not_replace_existing_failures(isolated):
    from docagent.db import Audit
    from docagent.diagnostics import job_diagnostics
    from docagent.jobs import interrupt_local_jobs
    from sqlalchemy import select

    init_db()
    with session_factory()() as db:
        db.add(Job(id="interrupted", owner="owner", repository="owner/repo", config={},
                   status="running", progress=87, message="Writing test plan as PDF", credential="encrypted"))
        db.add(Job(id="already-failed", owner="owner", repository="owner/repo", config={},
                   status="failed", progress=25, message="Original failure"))
        db.commit()
    interrupt_local_jobs()
    interrupt_local_jobs()
    with session_factory()() as db:
        job = db.get(Job, "interrupted")
        assert job.status == "failed" and job.credential == ""
        assert "87%" in job.message and "Writing test plan as PDF" in job.message
        history = job_diagnostics(db, job)["history"]
        assert len(history) == 1
        assert history[0]["last_message"] == "Writing test plan as PDF"
        assert db.get(Job, "already-failed").message == "Original failure"
        assert len(db.scalars(select(Audit).where(Audit.job_id == "interrupted")).all()) == 1


def test_export_progress_can_write_and_replaced_worker_cannot_publish(isolated, monkeypatch):
    import docagent.jobs as jobs
    from docagent.db import DocumentVersion
    from sqlalchemy import select

    init_db()
    config = AnalysisConfig(repository="demo/inventory", formats=["md"])
    job_id = "00000000-0000-0000-0000-000000000099"
    with session_factory()() as db:
        db.add(Job(id=job_id, owner="owner", repository=config.repository,
                   config=config.model_dump(mode="json")))
        db.commit()

    def export(root, *args, progress=None):
        root.mkdir(parents=True)
        root.with_suffix(".zip").write_bytes(b"draft export")
        progress(1, 2, "Writing requirements as Word")
        # A separate connection can update the row during rendering. Publication
        # must then detect replacement and retain the uncommitted export as orphaned.
        with session_factory()() as db:
            job = db.get(Job, job_id)
            assert job.progress > 80
            job.worker_id = "replacement"
            db.commit()
        return []

    monkeypatch.setattr(jobs, "export_package", export)
    jobs.run_job(job_id)
    with session_factory()() as db:
        assert db.get(Job, job_id).worker_id == "replacement"
        assert db.get(Job, job_id).status == "running"
        assert db.scalar(select(DocumentVersion).where(DocumentVersion.job_id == job_id)) is None
