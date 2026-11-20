import hashlib
import logging
import shutil
import tempfile
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, or_, select, update

from docagent.analysis import scan_repository
from docagent.config import settings
from docagent.db import Audit, DocumentVersion, Job, ScanCache, UserSession, now, session_factory
from docagent.diagnostics import failure_details, stage_name
from docagent.documents import export_package
from docagent.execution import execute_tests
from docagent.github import GitHub
from docagent.llm import enrich
from docagent.logging_config import job_log_context, safe_error
from docagent.queue import LocalJobQueue
from docagent.reporting import refine_analysis
from docagent.schemas import AnalysisConfig
from docagent.security import decrypt
from docagent.storage import LocalArtifactStorage, artifact_storage
from docagent.workflow import baseline, workflow

DEMO_ROOT = Path("examples/inventory").resolve()
local_queue: LocalJobQueue | None = None
logger = logging.getLogger(__name__)


def log_worker_status():
    """Advisory startup check: an available API does not imply a Celery consumer exists."""
    cfg = settings()
    logger.info("Job execution configured backend=%s redis=%s storage=%s",
                cfg.job_backend, cfg.redis_backend, cfg.storage_backend)
    if cfg.job_backend != "celery":
        return
    try:
        from docagent.worker import celery

        with celery.connection_for_read(connect_timeout=2) as connection:
            connection.transport_options.update(socket_connect_timeout=2, socket_timeout=2)
            connection.ensure_connection(max_retries=0, timeout=2)
            workers = celery.control.inspect(timeout=1, connection=connection).ping() or {}
    except Exception as exc:
        logger.error("Worker availability check failed %s; check Redis connectivity", safe_error(exc))
        return
    if workers:
        logger.info("Celery worker availability responding_workers=%d", len(workers))
    else:
        logger.warning("No Celery worker replied. Analyses will remain queued. "
                       "serve starts the API only; start 'docagent worker --pool solo --concurrency 1' "
                       "in another terminal on Windows, and 'docagent scheduler' for recovery.")


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
    """Legacy local layout, also used when migrating existing artifacts to S3."""
    return LocalArtifactStorage(settings()).root(job_id, version)


def export_job(db, job, progress=None, worker_id=None):
    state = {**workflow(db, job), "baseline_hash": job.baseline_hash}
    def publishing(completed, total, path):
        if progress:
            progress(1, 1, f"Uploading artifact {completed + 1}/{total}: {path}")

    with artifact_storage().export_directory(job.id, job.version, on_publish=publishing) as root:
        manifest = export_package(
            root, job.analysis, AnalysisConfig.model_validate(job.config), state, job.version,
            progress=progress,
        )
        with root.with_suffix(".zip").open("rb") as stream:
            package_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    # Network/render work runs without holding the job row lock, allowing lease
    # renewal and live progress. Fence publication after every upload succeeds.
    if worker_id is not None:
        db.refresh(job, with_for_update=True)
        if job.worker_id != worker_id or job.status != "running":
            raise WorkerLeaseLost()
    db.add(
        DocumentVersion(
            job_id=job.id, version=job.version, baseline_hash=job.baseline_hash, package_sha256=package_hash
        )
    )
    return manifest


def next_version(job):
    """Skip orphaned exports after a failed transaction without overwriting any version."""
    version = job.version + 1
    while artifact_storage().version_exists(job.id, version):
        version += 1
    return version


class WorkerLeaseLost(Exception):
    """A replacement worker owns the job; this worker must stop publishing changes."""


def set_progress(job_id, worker_id, value, message, record=False):
    with session_factory()() as db:
        changed = db.execute(
            update(Job)
            .where(Job.id == job_id, Job.worker_id == worker_id, Job.status == "running")
            .values(progress=value, message=message, updated=now())
        )
        if not changed.rowcount:
            db.rollback()
            raise WorkerLeaseLost()
        if record:
            db.add(Audit(job_id=job_id, actor="system", action="job_stage",
                         detail={"stage": stage_name(value), "stage_progress": value, "message": message}))
        db.commit()
    logger.info("Job progress job_id=%s progress=%d stage=%s", job_id, value, message)


def pin_commit(job_id, worker_id, commit):
    with session_factory()() as db:
        db.execute(
            update(Job)
            .where(
                Job.id == job_id, Job.worker_id == worker_id,
                Job.status == "running", Job.resolved_commit == "",
            )
            .values(resolved_commit=commit)
        )
        db.commit()
        resolved = db.scalar(select(Job.resolved_commit).where(
            Job.id == job_id, Job.worker_id == worker_id, Job.status == "running",
        ))
        if not resolved:
            raise WorkerLeaseLost()
        return resolved


def run_job(job_id):
    # Atomic transition avoids duplicate Celery deliveries running the same job twice.
    worker_id = str(uuid.uuid4())
    with session_factory()() as db:
        previous = db.get(Job, job_id)
        prior = ({"previous_worker": previous.worker_id, "stage": stage_name(previous.progress),
                  "stage_progress": previous.progress, "last_message": previous.message}
                 if previous and previous.status == "running" else None)
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
            logger.debug("Job delivery skipped job_id=%s reason=already_claimed_or_finished", job_id)
            return
        if prior:
            db.add(Audit(job_id=job_id, actor="system", action="worker_lease_expired", detail=prior))
        job = db.get(Job, job_id)
        config = AnalysisConfig.model_validate(job.config)
        credential = job.credential
        owner = job.owner
        resolved_commit = job.resolved_commit
        db.add(Audit(job_id=job_id, actor="system", action="job_started",
                     detail={"backend": settings().job_backend, "stage": "Repository retrieval",
                             "stage_progress": 5, "message": "Worker claimed the analysis"}))
        db.commit()
    context = job_log_context.set(job_id)
    started = time.monotonic()
    logger.info("Job started job_id=%s progress=5 stage=Retrieving repository", job_id)
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
            except Exception as exc:
                # Transient DB outages are retried at the next heartbeat. No source or keys in logs.
                logger.warning("Worker lease renewal failed job_id=%s %s", job_id, safe_error(exc))
                continue

    thread = threading.Thread(target=heartbeat, daemon=True, name="docagent-lease")
    thread.start()
    try:
        token = decrypt(credential)
        cfg = settings()
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="docagent-source-", dir=cfg.data_dir, ignore_cleanup_errors=True) as temp:
            root = Path(temp) / "source"
            download_skips = []
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
                    commit = resolved_commit or github.resolve(
                        config.repository, config.ref or metadata["default_branch"]
                    )
                    commit = pin_commit(job_id, worker_id, commit)
                    download_skips = github.download(config.repository, commit, root) or []
            set_progress(job_id, worker_id, 25, "Extracting syntax and dependency evidence", record=True)
            with session_factory()() as db:
                def scan_progress(event):
                    db.commit()
                    message = (f"Inspecting source: {event['scanned_files']} files inspected; "
                               f"{event['skipped_files']} skipped; {event['auto_excluded_files']} automatically excluded")
                    if event["current_path"]:
                        message += f". Current file: {event['current_path']}"
                    set_progress(job_id, worker_id, 25, message)

                analysis = scan_repository(
                    root, commit, config.depth, db=db, cache_scope=f"{owner}:{config.repository}",
                    on_event=scan_progress, skipped_paths=download_skips,
                )
                db.commit()
            analysis.update(repository=config.repository, private=private)
            if config.repository == "demo/inventory":
                analysis["gaps"].append(
                    "Bundled demo snapshot: commit is a content fingerprint, not a real GitHub commit. Source files are in examples/inventory."
                )
            set_progress(job_id, worker_id, 55, "Synthesizing evidence-based requirements", record=True)
            with session_factory()() as db:
                def ai_progress(completed, total, message):
                    # Checkpoint cache writes before a separate progress transaction.
                    # SQLite allows only one writer; keep network calls outside that lock.
                    db.commit()
                    end = 69 if config.execute_tests else 79
                    set_progress(job_id, worker_id, 55 + int((end - 55) * completed / total), message)

                analysis = enrich(
                    analysis, config, private, db=db, cache_scope=f"{owner}:{config.repository}",
                    progress=ai_progress,
                )
                db.commit()
            analysis = refine_analysis(analysis)
            if config.execute_tests:
                set_progress(job_id, worker_id, 70, "Running tests in isolated container", record=True)
                analysis["execution"] = execute_tests(root, commit, config.test_profile)
            set_progress(job_id, worker_id, 80, "Generating versioned documentation package", record=True)
            with session_factory()() as db:
                job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
                if job.worker_id != worker_id or job.status != "running":
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
                if artifact_storage().version_exists(job.id, job.version):
                    job.version = next_version(job)
                db.commit()

                def export_progress(completed, total, message):
                    set_progress(job_id, worker_id, 80 + int(15 * completed / max(total, 1)), message)

                export_job(db, job, progress=export_progress, worker_id=worker_id)
                job.status = "completed"
                job.progress = 100
                skipped_count = len(analysis.get("scope", {}).get("skipped_files", []))
                job.message = ("Documentation ready for review" if not skipped_count else
                               f"Documentation ready with coverage gaps: {skipped_count} paths could not be inspected")
                if analysis.get("scope", {}).get("budget_reached"):
                    job.message = "Documentation ready with coverage gaps: the selected analysis budget was reached"
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
        logger.info("Job completed job_id=%s progress=100 duration_seconds=%.1f", job_id, time.monotonic() - started)
    except WorkerLeaseLost:
        logger.warning("Job stopped job_id=%s reason=worker_lease_lost", job_id)
        return
    except Exception as exc:
        logger.error("Job failed job_id=%s duration_seconds=%.1f %s",
                     job_id, time.monotonic() - started, safe_error(exc))
        # Source and SDK exceptions can contain secrets. Persist a fixed message only.
        with session_factory()() as db:
            job = db.get(Job, job_id)
            if job and job.worker_id == worker_id:
                details = failure_details(exc, job.progress, job.message)
                job.status = "failed"
                job.message = f"{details['stage']}: {details['message']}"
                job.credential = ""
                job.lease_until = None
                db.add(
                    Audit(
                        job_id=job.id,
                        actor="system",
                        action="generation_failed",
                        detail=details,
                    )
                )
                db.commit()
    finally:
        stop.set()
        thread.join(timeout=2)
        job_log_context.reset(context)


def enqueue(job_id):
    backend = settings().job_backend
    logger.info("Job dispatch requested job_id=%s backend=%s", job_id, backend)
    try:
        if backend == "celery":
            from docagent.worker import analyze_task

            delivery = analyze_task.delay(job_id)
        else:
            if local_queue is None:
                raise RuntimeError("Local queue has not started")
            delivery = local_queue.enqueue(job_id)
    except Exception as exc:
        logger.error("Job dispatch failed job_id=%s backend=%s %s", job_id, backend, safe_error(exc))
        raise
    logger.info("Job dispatched job_id=%s backend=%s; awaiting worker claim", job_id, backend)
    return delivery


def interrupt_local_jobs():
    """Retain the last stage and audit history when a process-local queue is lost."""
    with session_factory()() as db:
        for job in db.scalars(select(Job).where(Job.status.in_(["running", "queued"]))):
            previous_message, previous_status = job.message, job.status
            db.add(Audit(job_id=job.id, actor="system", action="worker_interrupted", detail={
                "stage": stage_name(job.progress), "stage_progress": job.progress,
                "last_message": previous_message, "previous_status": previous_status,
                "backend": "local", "reason_code": "worker_restarted",
                "message": "The local worker restarted or the execution backend changed. Start a new analysis to retry.",
            }))
            job.status = "failed"
            job.message = f"Local worker restarted or backend changed. Last stage at {job.progress}%: {previous_message}"
            job.credential = ""
            job.lease_until = None
        db.commit()


def cleanup():
    cutoff = now() - timedelta(days=settings().retention_days)
    removed = 0
    with session_factory()() as db:
        for job in db.scalars(
            select(Job).where(Job.created < cutoff, Job.status.in_(["completed", "failed"]))
        ):
            artifact_storage().delete_job(job.id)
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
            logger.warning("Job recovery dispatch job_id=%s previous_status=%s", job.id, job.status)
            if job.status == "running":
                db.add(
                    Audit(
                        job_id=job.id,
                        actor="system",
                        action="worker_lease_expired",
                        detail={"previous_worker": job.worker_id, "stage": stage_name(job.progress),
                                "stage_progress": job.progress, "last_message": job.message},
                    )
                )
            enqueue(job.id)
        db.commit()
    return len(jobs)
