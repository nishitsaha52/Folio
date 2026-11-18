import hashlib
import shutil
import tempfile
import threading
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, or_, select, update

from docagent.analysis import scan_repository
from docagent.config import settings
from docagent.db import Audit, DocumentVersion, Job, ScanCache, UserSession, now, session_factory
from docagent.documents import export_package
from docagent.execution import execute_tests
from docagent.github import GitHub
from docagent.llm import enrich
from docagent.queue import LocalJobQueue
from docagent.schemas import AnalysisConfig
from docagent.security import decrypt
from docagent.workflow import baseline, workflow

DEMO_ROOT = Path("examples/inventory").resolve()
local_queue: LocalJobQueue | None = None


def start_local_queue():
    global local_queue
    if local_queue is not None:
        raise RuntimeError("Local queue is already running; use one API process")
    local_queue = LocalJobQueue(settings(), run_job)


def stop_local_queue():
    global local_queue
    queue, local_queue = local_queue, None
    if queue is not None:
        queue.close()


def output_root(job_id, version=None):
    root = settings().data_dir.resolve() / "artifacts" / str(uuid.UUID(job_id))
    return root / f"v{version:04d}" if version is not None else root


def export_job(db, job):
    state = {**workflow(db, job), "baseline_hash": job.baseline_hash}
    manifest = export_package(
        output_root(job.id, job.version),
        job.analysis,
        AnalysisConfig.model_validate(job.config),
        state,
        job.version,
    )
    package = output_root(job.id) / f"v{job.version:04d}.zip"
    with package.open("rb") as stream:
        package_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    db.add(
        DocumentVersion(
            job_id=job.id, version=job.version, baseline_hash=job.baseline_hash, package_sha256=package_hash
        )
    )
    return manifest


def next_version(job):
    """Skip orphaned exports after a failed transaction without overwriting any version."""
    version = job.version + 1
    while output_root(job.id, version).exists():
        version += 1
    return version


def set_progress(job_id, value, message):
    with session_factory()() as db:
        db.execute(update(Job).where(Job.id == job_id).values(progress=value, message=message, updated=now()))
        db.commit()


def run_job(job_id):
    # Atomic transition avoids duplicate Celery deliveries running the same job twice.
    worker_id = str(uuid.uuid4())
    with session_factory()() as db:
        claimed = db.execute(
            update(Job)
            .where(
                Job.id == job_id,
                or_(Job.status == "queued", (Job.status == "running") & (Job.lease_until < now())),
            )
            .values(
                status="running",
                progress=5,
                message="Retrieving repository",
                updated=now(),
                worker_id=worker_id,
                lease_until=now() + timedelta(minutes=3),
            )
        )
        db.commit()
        if not claimed.rowcount:
            return
        job = db.get(Job, job_id)
        config = AnalysisConfig.model_validate(job.config)
        credential = job.credential
        owner = job.owner
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(30):
            try:
                with session_factory()() as heartbeat_db:
                    heartbeat_db.execute(
                        update(Job)
                        .where(Job.id == job_id, Job.worker_id == worker_id, Job.status == "running")
                        .values(lease_until=now() + timedelta(minutes=3))
                    )
                    heartbeat_db.commit()
            except Exception:
                # Transient DB outages are retried at the next heartbeat. No source or keys in logs.
                continue

    thread = threading.Thread(target=heartbeat, daemon=True, name="docagent-lease")
    thread.start()
    try:
        token = decrypt(credential)
        cfg = settings()
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="docagent-source-", dir=cfg.data_dir) as temp:
            root = Path(temp) / "source"
            if config.repository == "demo/inventory":
                shutil.copytree(DEMO_ROOT, root)
                from docagent.db import digest

                commit = digest(
                    [
                        (p.relative_to(root).as_posix(), p.read_text())
                        for p in sorted(root.rglob("*"))
                        if p.is_file()
                    ]
                )[:40]
                private = False
            else:
                with GitHub(token) as github:
                    metadata = github.repository(config.repository)
                    private = metadata["private"]
                    if private and any(p.provider not in config.consent_providers for p in config.providers):
                        raise PermissionError("Private repository AI consent is missing")
                    commit = github.resolve(config.repository, config.ref or metadata["default_branch"])
                    github.download(config.repository, commit, root)
            set_progress(job_id, 25, "Extracting syntax and dependency evidence")
            with session_factory()() as db:
                analysis = scan_repository(
                    root, commit, config.depth, db=db, cache_scope=f"{owner}:{config.repository}"
                )
                db.commit()
            analysis.update(repository=config.repository, private=private)
            if config.repository == "demo/inventory":
                analysis["gaps"].append(
                    "Bundled demo snapshot: commit is a content fingerprint, not a real GitHub commit. Source files are in examples/inventory."
                )
            set_progress(job_id, 55, "Synthesizing evidence-based requirements")
            with session_factory()() as db:
                analysis = enrich(
                    analysis, config, private, db=db, cache_scope=f"{owner}:{config.repository}"
                )
                db.commit()
            if config.execute_tests:
                set_progress(job_id, 70, "Running tests in isolated container")
                analysis["execution"] = execute_tests(root, commit, config.test_profile)
            set_progress(job_id, 80, "Generating versioned documentation package")
            with session_factory()() as db:
                job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
                if job.worker_id != worker_id:
                    return
                previous = db.scalar(
                    select(Job)
                    .where(
                        Job.owner == owner,
                        Job.repository == job.repository,
                        Job.status == "completed",
                        Job.id != job.id,
                    )
                    .order_by(Job.created.desc())
                )
                if previous and previous.analysis:
                    old = {x["path"]: x["sha256"] for x in previous.analysis["inventory"]}
                    new = {x["path"]: x["sha256"] for x in analysis["inventory"]}
                    changed = {p for p in old.keys() | new.keys() if old.get(p) != new.get(p)}
                    analysis["changes"] = {
                        "previous_job": previous.id,
                        "previous_commit": previous.analysis["commit"],
                        "added": sorted(new.keys() - old.keys()),
                        "removed": sorted(old.keys() - new.keys()),
                        "modified": sorted(p for p in old.keys() & new.keys() if old[p] != new[p]),
                        "affected_requirement_ids": [
                            r["id"] for r in analysis["requirements"] if r["module"] in changed
                        ],
                    }
                job.analysis = analysis
                job.baseline_hash = baseline(analysis)
                if output_root(job.id, job.version).exists():
                    job.version = next_version(job)
                export_job(db, job)
                job.status = "completed"
                job.progress = 100
                job.message = "Documentation ready for review"
                job.credential = ""
                job.lease_until = None
                db.add(
                    Audit(
                        job_id=job.id,
                        actor="system",
                        action="generation_completed",
                        detail={"commit": commit, "version": job.version},
                    )
                )
                db.commit()
    except Exception:
        # Source and SDK exceptions can contain secrets. Persist a fixed message only.
        with session_factory()() as db:
            job = db.get(Job, job_id)
            if job and job.worker_id == worker_id:
                job.status = "failed"
                job.message = "Analysis failed. Check repository access, archive limits, provider configuration and worker prerequisites. Source content and credentials were omitted from errors."
                job.credential = ""
                job.lease_until = None
                db.add(
                    Audit(
                        job_id=job.id,
                        actor="system",
                        action="generation_failed",
                        detail={"stage_progress": job.progress},
                    )
                )
                db.commit()
    finally:
        stop.set()
        thread.join(timeout=2)


def enqueue(job_id):
    if settings().job_backend == "celery":
        from docagent.worker import analyze_task

        analyze_task.delay(job_id)
    else:
        if local_queue is None:
            raise RuntimeError("Local queue has not started")
        return local_queue.enqueue(job_id)


def cleanup():
    cutoff = now() - timedelta(days=settings().retention_days)
    removed = 0
    with session_factory()() as db:
        for job in db.scalars(
            select(Job).where(Job.created < cutoff, Job.status.in_(["completed", "failed"]))
        ):
            root = output_root(job.id)
            if root.is_dir() and root.resolve().is_relative_to((settings().data_dir / "artifacts").resolve()):
                shutil.rmtree(root)
            db.delete(job)
            removed += 1
        db.execute(delete(UserSession).where(UserSession.expires < now()))
        db.execute(delete(ScanCache).where(ScanCache.updated < cutoff))
        db.commit()
    return removed


def recover_jobs():
    """Celery Beat re-delivers expired leases and queued IDs; atomic claim prevents duplicate work."""
    with session_factory()() as db:
        jobs = db.scalars(
            select(Job).where(
                or_(Job.status == "queued", (Job.status == "running") & (Job.lease_until < now()))
            )
        ).all()
        for job in jobs:
            if job.status == "running":
                db.add(
                    Audit(
                        job_id=job.id,
                        actor="system",
                        action="worker_lease_expired",
                        detail={"previous_worker": job.worker_id},
                    )
                )
            enqueue(job.id)
        db.commit()
    return len(jobs)
