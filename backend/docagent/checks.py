"""Credential-safe live checks for configured infrastructure and the demo API."""

import hashlib
import io
import time
import uuid
import zipfile
from pathlib import Path

import httpx
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from docagent.config import Settings, settings
from docagent.db import Base, DocumentVersion, Job
from docagent.queue import create_redis_client
from docagent.security import decrypt, encrypt
from docagent.storage import S3ArtifactStorage, StorageError


class CheckFailure(Exception):
    """A fixed diagnostic authored by the checker, without service exception text."""


def postgres_check(cfg: Settings):
    if not cfg.database_url.startswith("postgresql"):
        raise CheckFailure("Live checks require a PostgreSQL DOCAGENT_DATABASE_URL")
    database = create_engine(cfg.database_url, connect_args={"connect_timeout": 5})
    try:
        with database.connect() as connection:
            name, version = connection.execute(text("select current_database(), version()")).one()
            if not inspect(connection).has_table("alembic_version"):
                raise CheckFailure("Initialize the schema first: docagent init-db")
            revision = connection.execute(text("select version_num from alembic_version")).scalar_one()
            if compare_metadata(MigrationContext.configure(connection), Base.metadata):
                raise CheckFailure("Database schema differs from application models; run docagent init-db")
            return {"database": name, "version": version.split(" on ")[0], "migration": revision,
                    "models_match": True}
    finally:
        database.dispose()


def redis_check(cfg: Settings, write_probe: bool):
    if cfg.redis_backend != "real":
        raise CheckFailure("Live checks require DOCAGENT_REDIS_BACKEND=real")
    client = create_redis_client(cfg)
    key = "docagent:live-check:" + uuid.uuid4().hex
    created = False
    try:
        if not client.ping():
            raise CheckFailure("Redis did not answer PING")
        if write_probe:
            created = bool(client.set(key, "roundtrip-ok", nx=True, ex=60))
            if not created or client.get(key) != "roundtrip-ok":
                raise CheckFailure("Redis probe did not roundtrip")
        return {"backend": "real", "ping": True, "write_probe": write_probe}
    finally:
        try:
            if created:
                client.delete(key)
        finally:
            client.close()


def storage_check(cfg: Settings, write_probe: bool):
    if cfg.storage_backend != "s3":
        raise CheckFailure("Live checks require DOCAGENT_STORAGE_BACKEND=s3")
    storage = S3ArtifactStorage(cfg)
    probe_id = str(uuid.uuid4())
    result = {"backend": "s3", "bucket": cfg.s3_bucket, "prefix_listing": True,
              "write_probe": write_probe}
    try:
        storage.client.list_objects_v2(Bucket=storage.bucket, Prefix=storage.prefix, MaxKeys=1)
        if not write_probe:
            return result
        try:
            payload = "Folio artifact live check\n"
            with storage.export_directory(probe_id, 1) as root:
                root.mkdir()
                (root / "probe.txt").write_text(payload, encoding="utf-8", newline="\n")
                with zipfile.ZipFile(root.with_suffix(".zip"), "x", zipfile.ZIP_DEFLATED) as archive:
                    archive.write(root / "probe.txt", "probe.txt")
                expected_hash = hashlib.sha256(root.with_suffix(".zip").read_bytes()).hexdigest()
            if storage.read_text(probe_id, 1, "probe.txt") != payload:
                raise CheckFailure("Artifact text probe did not roundtrip")
            download = storage.download(probe_id, 1)
            try:
                if hashlib.sha256(download.path.read_bytes()).hexdigest() != expected_hash:
                    raise CheckFailure("Artifact ZIP checksum did not match")
            finally:
                if download.cleanup:
                    download.cleanup()
            try:
                with storage.export_directory(probe_id, 1):
                    raise CheckFailure("Artifact version was not immutable")
            except StorageError:
                result["immutable_version"] = True
        finally:
            storage.delete_job(probe_id)
        if storage.version_exists(probe_id, 1):
            raise CheckFailure("Temporary artifact probe was not deleted")
        result.update(zip_checksum=True, temporary_probe_deleted=True)
        return result
    finally:
        storage.client.close()


def encryption_check():
    probe = "live-check-" + uuid.uuid4().hex
    if decrypt(encrypt(probe)) != probe:
        raise CheckFailure("Encryption roundtrip failed")
    return {"roundtrip": True}


def api_check(cfg: Settings, api_url: str, timeout: int, package_output: Path | None):
    with httpx.Client(base_url=api_url.rstrip("/"), timeout=30, headers={"Origin": cfg.public_url}) as client:
        def request(method, path, expected=200, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.status_code != expected:
                raise CheckFailure(f"API request returned HTTP {response.status_code}; expected {expected}")
            return response

        request("GET", "/api/health")
        session = request("GET", "/api/session").json()
        client.headers["X-CSRF-Token"] = session["csrf_token"]
        requested = request("POST", "/api/demo", expected=202, json={}).json()
        job_id = str(uuid.UUID(requested["id"]))
        path = f"/api/jobs/{job_id}"
        deadline = time.monotonic() + timeout
        while True:
            job = request("GET", path).json()
            if job["status"] == "completed":
                break
            if job["status"] == "failed":
                raise CheckFailure("Demo generation failed; check the worker and artifact storage")
            if time.monotonic() >= deadline:
                raise CheckFailure("Demo timed out; ensure the configured job worker is running")
            time.sleep(0.5)
        package = request("GET", path + "/download").content
        checksum = hashlib.sha256(package).hexdigest()
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            if archive.testzip() is not None:
                raise CheckFailure("Downloaded ZIP failed CRC validation")
            names = archive.namelist()
            counts = {ext: sum(name.endswith("." + ext) for name in names)
                      for ext in ("docx", "pdf", "xlsx", "svg", "png")}
            if counts != {"docx": 7, "pdf": 7, "xlsx": 1, "svg": 4, "png": 4}:
                raise CheckFailure("Demo package did not contain all expected export formats")
        files = request("GET", path + "/files").json()["files"]
        markdown = next(item["path"] for item in files if item["path"].endswith(".md"))
        preview = request("GET", path + "/preview", params={"path": markdown}).json()["content"]
        individual = request("GET", path + "/download", params={"path": markdown}).text
        if individual.replace("\r\n", "\n") != preview:
            raise CheckFailure("Markdown preview did not match the individual download")
        database = create_engine(cfg.database_url, connect_args={"connect_timeout": 5})
        try:
            with Session(database) as db:
                stored = db.get(DocumentVersion, (job_id, job["version"]))
                record = db.get(Job, job_id)
                if not record or record.status != "completed" or not stored or stored.package_sha256 != checksum:
                    raise CheckFailure("API package did not match the configured database version")
        finally:
            database.dispose()
        storage = S3ArtifactStorage(cfg)
        try:
            downloaded = storage.download(job_id, job["version"])
            try:
                if hashlib.sha256(downloaded.path.read_bytes()).hexdigest() != checksum:
                    raise CheckFailure("API package did not match the configured artifact storage")
            finally:
                if downloaded.cleanup:
                    downloaded.cleanup()
        finally:
            storage.client.close()
        request("GET", path + "/download", expected=400, params={"path": "../../.env"})
        with httpx.Client(base_url=api_url.rstrip("/"), timeout=30) as other:
            if other.get("/api/session").status_code != 200 or other.get(path).status_code != 404:
                raise CheckFailure("Cross-session analysis access was not denied")
        if job["config"]["providers"] or job["analysis"]["execution"] is not None:
            raise CheckFailure("The demo unexpectedly enabled AI or repository-test execution")
        if job["workflow"]["counts"]["passed"] != 0:
            raise CheckFailure("Generated UAT cases were unexpectedly marked passed")
        if package_output:
            package_output.parent.mkdir(parents=True, exist_ok=True)
            package_output.write_bytes(package)
        return {"job_id": job_id, "version": job["version"], "zip_entries": len(names), "formats": counts,
                "package_sha256": checksum, "database_and_storage_match": True,
                "markdown_preview_matches": True, "access_controls": True, "external_ai_calls": 0}


def run_checks(write_probe=False, api_url=None, timeout=120, output: Path | None = None):
    checks = {}

    def run(name, action):
        try:
            checks[name] = {"status": "passed", **action()}
        except Exception as exc:
            failure = {"status": "failed", "error_type": type(exc).__name__}
            if isinstance(exc, CheckFailure):
                failure["detail"] = str(exc)
            original = getattr(exc, "orig", None)
            if original is not None and getattr(original, "sqlstate", None):
                failure["database_error_code"] = original.sqlstate
            # Never emit exception messages, connection URLs, input values or SDK responses.
            checks[name] = failure

    try:
        cfg = settings()
    except Exception as exc:
        return {"status": "failed", "checks": {"configuration": {
            "status": "failed", "error_type": type(exc).__name__}}}
    run("postgresql", lambda: postgres_check(cfg))
    run("redis", lambda: redis_check(cfg, write_probe))
    run("artifact_storage", lambda: storage_check(cfg, write_probe))
    run("encryption", encryption_check)
    if api_url:
        if all(item["status"] == "passed" for item in checks.values()):
            run("api_demo", lambda: api_check(cfg, api_url, timeout, output.with_suffix(".zip") if output else None))
        else:
            checks["api_demo"] = {"status": "skipped", "detail": "Fix the service checks before running the demo"}
    return {"status": "passed" if all(item["status"] == "passed" for item in checks.values()) else "failed",
            "checks": checks}
