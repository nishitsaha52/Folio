from datetime import timedelta

from docagent.db import Job, JobAccess, Review, UserSession, init_db, now, session_factory
from docagent.db import TestResult as Result
from docagent.security import token_hash
from docagent.workflow import workflow
from sqlalchemy import select


def test_acceptance_invalidates_when_evidence_changes(client, completed, reviewer):
    with session_factory()() as db:
        job = db.get(Job, completed["id"])
        db.add(
            Review(
                job_id=job.id,
                baseline_hash=job.baseline_hash,
                stage="requirements",
                decision="approved",
                reviewer="reviewer",
                comment="Reviewed",
            )
        )
        for case in job.analysis["test_cases"]:
            db.add(
                Result(
                    job_id=job.id,
                    baseline_hash=job.baseline_hash,
                    test_case_id=case["id"],
                    status="passed",
                    source="manual_uat",
                    actual="Observed expected behavior",
                    evidence_reference="UAT-run-1",
                    severity="none",
                    reviewer="reviewer",
                )
            )
        db.flush()
        state = workflow(db, job)
        assert state["ready_for_acceptance"]
        db.add(
            Review(
                job_id=job.id,
                baseline_hash=state["acceptance_hash"],
                stage="uat",
                decision="approved",
                reviewer="reviewer",
                comment="Accepted",
            )
        )
        db.flush()
        assert workflow(db, job)["uat_status"] == "approved"
        db.add(
            Result(
                job_id=job.id,
                baseline_hash=job.baseline_hash,
                test_case_id=job.analysis["test_cases"][0]["id"],
                status="failed",
                source="manual_uat",
                actual="Regression observed",
                evidence_reference="UAT-run-2",
                severity="high",
                reviewer="reviewer",
            )
        )
        db.flush()
        state = workflow(db, job)
        assert state["uat_status"] == "pending"
        assert not state["ready_for_acceptance"]


def test_shared_viewer_cannot_approve(client, completed, reviewer):
    with session_factory()() as db:
        job = db.get(Job, completed["id"])
        user = db.get(UserSession, token_hash(client.cookies["docagent_session"]))
        job.owner = "github:other-owner"
        db.add(JobAccess(job_id=job.id, principal=user.owner, login=user.login, role="viewer"))
        db.commit()
    response = client.get(f"/api/jobs/{completed['id']}")
    assert response.status_code == 200
    assert response.json()["is_owner"] is False
    assert response.json()["can_review"] is False
    response = client.post(
        f"/api/jobs/{completed['id']}/reviews",
        json={
            "stage": "requirements",
            "decision": "comment",
            "comment": "A comment",
            "baseline_hash": completed["baseline_hash"],
        },
    )
    assert response.status_code == 403


def test_stale_result_is_rejected(client, completed, reviewer):
    response = client.post(
        f"/api/jobs/{completed['id']}/results",
        json={
            "baseline_hash": "0" * 64,
            "test_case_id": completed["analysis"]["test_cases"][0]["id"],
            "status": "passed",
            "actual": "Verified actual outcome",
            "evidence_reference": "https://ci.example/1",
            "source": "existing_report",
            "attested": True,
        },
    )
    assert response.status_code == 409


def test_recorded_result_and_document_versions(client, completed, reviewer):
    response = client.post(
        f"/api/jobs/{completed['id']}/results",
        json={
            "baseline_hash": completed["baseline_hash"],
            "test_case_id": completed["analysis"]["test_cases"][0]["id"],
            "status": "passed",
            "actual": "Verified expected output for the fixture",
            "evidence_reference": "https://ci.example/1",
            "source": "existing_report",
            "attested": True,
        },
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["workflow"]["counts"]["passed"] == 1
    assert updated["workflow"]["counts"]["unexecuted"] == len(completed["analysis"]["test_cases"]) - 1
    assert updated["version"] == 2
    assert client.get(f"/api/jobs/{completed['id']}/download", params={"version": 1}).status_code == 200


def test_migrations_match_models(isolated):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from docagent.db import Base, engine

    init_db()
    init_db()  # Repeated startup is safe.
    with engine().connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_expired_job_lease_is_requeued(client, completed, monkeypatch):
    import docagent.jobs as jobs

    delivered = []
    monkeypatch.setattr(jobs, "enqueue", delivered.append)
    with session_factory()() as db:
        job = db.get(Job, completed["id"])
        job.status = "running"
        job.lease_until = now() - timedelta(seconds=1)
        db.commit()
    assert jobs.recover_jobs() == 1
    assert delivered == [completed["id"]]


def test_retention_removes_artifacts_and_records(client, completed):
    from docagent.jobs import cleanup, output_root

    root = output_root(completed["id"])
    assert root.exists()
    with session_factory()() as db:
        job = db.get(Job, completed["id"])
        job.created = now() - timedelta(days=90)
        db.commit()
    assert cleanup() == 1
    assert not root.exists()
    with session_factory()() as db:
        assert not db.scalar(select(Job).where(Job.id == completed["id"]))
