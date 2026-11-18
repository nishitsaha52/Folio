import hashlib
import re
import secrets
from functools import lru_cache
from pathlib import PurePosixPath

from cryptography.fernet import Fernet

from docagent.config import settings

SECRET_PATTERNS = [
    (
        re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----"),
        "[REDACTED PRIVATE KEY]",
    ),
    (
        re.compile(
            r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{30,}|AKIA[A-Z0-9]{16})\b"
        ),
        "[REDACTED TOKEN]",
    ),
    (
        re.compile(
            r"(?i)((?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\s*[\"']?\s*[:=]\s*)[\"']([^\"'\r\n]{3,})[\"']"
        ),
        r'\1"[REDACTED]"',
    ),
    (re.compile(r"(?im)^([A-Z_]*(?:PASSWORD|SECRET|TOKEN|API_KEY)[A-Z_]*\s*=)[^\r\n]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(https?://)[^\s/:]+:[^\s/@]+@"), r"\1[REDACTED]@"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"), "[REDACTED JWT]"),
]


def redact(text: str) -> str:
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_object(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_object(v) for v in value]
    if isinstance(value, dict):
        return {k: redact_object(v) for k, v in value.items()}
    return value


def secret_path(path: str) -> bool:
    p = PurePosixPath(path.lower())
    return (
        any(x in {".git", ".ssh", ".aws", ".azure", ".gnupg"} for x in p.parts)
        or p.name.startswith(".env")
        or p.suffix in {".pem", ".key", ".p12", ".pfx", ".keystore"}
        or p.name
        in {
            "credentials",
            "credentials.json",
            "secrets.json",
            "secrets.yaml",
            "id_rsa",
            "id_ed25519",
            ".npmrc",
            ".pypirc",
        }
    )


@lru_cache
def cipher():
    cfg = settings()
    key = cfg.encryption_key.get_secret_value()
    if not key:
        keyfile = cfg.data_dir / ".encryption-key"
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Exclusive creation prevents two startup processes from replacing the key.
            with keyfile.open("xb") as f:
                f.write(Fernet.generate_key())
            keyfile.chmod(0o600)
        except FileExistsError:
            pass
        key = keyfile.read_text().strip()
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    return cipher().encrypt(value.encode()).decode() if value else ""


def decrypt(value: str) -> str:
    return cipher().decrypt(value.encode()).decode() if value else ""


def token_hash(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def new_token():
    return secrets.token_urlsafe(32)
