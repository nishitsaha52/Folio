"""Persisted, source-free job diagnostics built on the existing audit trail."""

from sqlalchemy import select

from docagent.db import Audit
from docagent.logging_config import http_status

JOB_EVENTS = {"analysis_requested", "job_started", "job_stage", "generation_failed", "worker_interrupted", "worker_lease_expired", "generation_completed", "diagnostic_recovered"}


def stage_name(progress):
    if progress < 5:
        return "Waiting for worker"
    if progress < 25:
        return "Repository retrieval"
    if progress < 55:
        return "Static analysis"
    if progress < 70:
        return "Requirements synthesis"
    if progress < 80:
        return "Requirements synthesis or test execution"
    return "Document export"


def failure_details(exc, progress, message):
    from sqlalchemy.exc import SQLAlchemyError

    from docagent.github import GitHubError
    from docagent.scan_scope import ScanPolicyError
    from docagent.storage import StorageError

    stage = stage_name(progress)
    if isinstance(exc, ScanPolicyError):
        reason, explanation = "ignore_policy", "The repository ignore policy could not be read. Check access to .gitignore and .docagentignore before retrying."
    elif isinstance(exc, GitHubError) and exc.status == 413:
        reason, explanation = "archive_size", "The repository archive exceeds the configured size limit. Reduce tracked build/dependency files or deliberately adjust the archive limit."
    elif isinstance(exc, GitHubError):
        reason, explanation = "repository_access", "Repository retrieval failed. Check repository access, the selected reference and archive limits."
    elif isinstance(exc, StorageError):
        reason, explanation = "artifact_storage", "Artifact storage failed. Check the configured storage service and its permissions."
    elif isinstance(exc, SQLAlchemyError):
        reason, explanation = "database", "A database operation failed. Check database availability and worker connectivity."
    elif isinstance(exc, TimeoutError):
        reason, explanation = "timeout", "An operation timed out. Check the service used by this stage."
    elif isinstance(exc, OSError):
        reason, explanation = "filesystem", "The operating system could not access a required file or directory. Check available disk space and access permissions."
    elif isinstance(exc, ValueError) and exc.args and isinstance(exc.args[0], str) and exc.args[0] in {
        "Archive has too many entries", "Archive expansion exceeds the configured limit",
        "Unsafe archive path", "Archive symlinks are not allowed", "Duplicate archive path",
        "Expected a single repository archive root", "Archive path escaped workspace",
    }:
        reason, explanation = "archive_validation", f"Repository archive rejected: {exc.args[0]}. Check the tracked files and configured archive limits."
    else:
        reason, explanation = "stage_failed", f"{stage} failed with {type(exc).__name__}. Check the worker log for the safe diagnostic."
    return {"stage": stage, "stage_progress": progress, "last_message": message,
            "reason_code": reason, "error_type": type(exc).__name__,
            "http_status": http_status(exc), "message": explanation}


def job_diagnostics(db, job):
    entries = db.scalars(select(Audit).where(Audit.job_id == job.id, Audit.action.in_(JOB_EVENTS))
                         .order_by(Audit.id.desc()).limit(40)).all()
    allowed = {"stage", "stage_progress", "last_message", "reason_code", "error_type", "http_status",
               "message", "backend", "previous_status", "previous_worker"}
    history = [{"action": event.action, "created": event.created.isoformat(),
                **{key: value for key, value in event.detail.items() if key in allowed}} for event in reversed(entries)]
    backend = next((event.get("backend") for event in reversed(history)
                    if event["action"] in {"analysis_requested", "job_started", "diagnostic_recovered"} and event.get("backend")), None)
    return {"stage": stage_name(job.progress), "history": history, "backend": backend,
            "latest_failure": next((event for event in reversed(history)
                                    if event["action"] in {"generation_failed", "worker_interrupted", "diagnostic_recovered"}), None)}
