"""Explainable scan exclusions and safe per-path coverage diagnostics."""

import re
from pathlib import PurePosixPath

from docagent.security import redact


class ScanPolicyError(ValueError):
    """An unreadable exclusion policy must not silently expand source sharing."""


def generated_reason(path):
    p = PurePosixPath(path)
    if p.suffix.lower() not in {".js", ".css"}:
        return None
    if p.name.endswith((".min.js", ".min.css")):
        return "Minified browser build output"
    # Keep ordinary assets/app.js and source modules. Fingerprinted asset names
    # are a build convention, not a reason to ignore an entire static directory.
    match = re.search(r"[-.]([A-Za-z0-9_-]{8,32})\.(?:js|css)$", p.name)
    if "assets" in p.parts and match and re.search(r"[0-9A-Z]", match[1]):
        return "Fingerprinted browser build output"
    return None


def explicitly_included(spec, path):
    for pattern in reversed(spec.patterns):
        if pattern.match_file(path):
            return pattern.include is False
    return False


def unreadable(path, exc, reason="unreadable_file"):
    code = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
    return {
        "path": redact(str(path)),
        "reason": reason,
        "code": code,
        "message": "The operating system prevented access. The file may be blocked, quarantined, locked or removed. It was not inspected.",
    }
