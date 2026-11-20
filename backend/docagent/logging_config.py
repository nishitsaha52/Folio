"""Consistent console logging without enabling verbose credential-bearing SDK logs."""

import logging
import re
import traceback
from contextvars import ContextVar
from pathlib import Path

job_log_context = ContextVar("job_log_context", default="-")

SDK_LOGGERS = (
    "httpx", "httpx2", "httpcore", "httpcore2", "openai", "anthropic", "google.genai", "google.auth",
    "boto3", "botocore", "s3transfer", "urllib3", "sqlalchemy.engine",
)


def configure_logging(level: str):
    threshold = logging.getLevelNamesMapping()[level]
    logging.basicConfig(level=threshold, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger().setLevel(threshold)
    logging.getLogger("docagent").setLevel(threshold)
    for name in SDK_LOGGERS:
        logging.getLogger(name).setLevel(max(threshold, logging.WARNING))


def safe_error(exc: Exception) -> str:
    """Keep exception types and locations, omitting messages, source lines and locals."""
    details = ["error_type=" + type(exc).__name__]
    reason = getattr(exc, "reason", None)
    if isinstance(reason, str) and reason in {
        "output_token_limit", "empty_response", "schema_validation_failed", "incomplete_response",
    }:
        details.append("reason=" + reason)
    from pydantic import ValidationError

    if isinstance(exc, ValidationError):
        types = sorted({error["type"] for error in exc.errors(include_input=False, include_context=False)})
        details.append("validation_types=" + ",".join(types[:8]))
    status = http_status(exc)
    if status is not None:
        details.append(f"http_status={status}")
    state = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if isinstance(state, str) and re.fullmatch(r"[A-Z0-9]{5}", state):
        details.append("sqlstate=" + state)
    frames = traceback.extract_tb(exc.__traceback__)
    if frames:
        details.append("location=" + " > ".join(
            f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" for frame in frames[-6:]
        ))
    return " ".join(details)


def http_status(exc: Exception) -> int | None:
    """SDKs expose HTTP statuses under different attribute names (Gemini uses code)."""
    for attribute in ("status_code", "status", "code"):
        status = getattr(exc, attribute, None)
        if isinstance(status, int) and 100 <= status <= 599:
            return status
    return None
