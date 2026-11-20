"""Private versioned artifacts on disk or in an S3-compatible bucket.

Exports become visible only after the caller commits a DocumentVersion row.
Failed exports retain their version reservation so retries never overwrite them.
"""

import mimetypes
import shutil
import tempfile
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import boto3
from boto3.exceptions import Boto3Error
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from docagent.config import Settings, settings


class StorageError(Exception):
    """A storage failure whose SDK details must not be returned to the browser."""


class ArtifactNotFound(StorageError):
    pass


class InvalidArtifactPath(ValueError):
    pass


@contextmanager
def storage_errors():
    try:
        yield
    except FileNotFoundError:
        raise ArtifactNotFound("Artifact not found") from None
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
            raise ArtifactNotFound("Artifact not found") from None
        raise StorageError("Artifact storage is unavailable") from None
    except (BotoCoreError, Boto3Error, OSError):
        raise StorageError("Artifact storage is unavailable") from None


def version_name(version: int) -> str:
    if not isinstance(version, int) or version < 1:
        raise ValueError("Invalid artifact version")
    return f"v{version:04d}"


def validate_path(path: str) -> str:
    if (
        not path
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or any(c in path for c in "\\:")
        or any(ord(c) < 32 for c in path)
    ):
        raise InvalidArtifactPath("Invalid artifact path")
    return path


def artifact_key(job_id: str, version: int, path: str = "") -> str:
    root = f"{uuid.UUID(job_id)}/{version_name(version)}"
    return f"{root}/{validate_path(path)}" if path else f"{root}.zip"


@dataclass
class Download:
    path: Path
    filename: str
    cleanup: Callable[[], None] | None = None


class LocalArtifactStorage:
    def __init__(self, cfg: Settings):
        self.base = (cfg.data_dir / "artifacts").resolve()

    def root(self, job_id: str, version: int | None = None) -> Path:
        root = self.base / str(uuid.UUID(job_id))
        if version is not None:
            root /= version_name(version)
        # Neither a job nor a version may alias another job/version via a symlink.
        if root.resolve() != root:
            raise InvalidArtifactPath("Invalid artifact path")
        return root

    def _path(self, job_id: str, version: int, path: str = "") -> Path:
        root = self.root(job_id, version)
        if not path:
            target = root.with_suffix(".zip")
            boundary = root.parent
        else:
            target = root / validate_path(path)
            boundary = root
        if target.is_symlink() or not target.resolve().is_relative_to(boundary.resolve()):
            raise InvalidArtifactPath("Invalid artifact path")
        return target

    @contextmanager
    def export_directory(self, job_id: str, version: int, on_publish=None):
        # export_package creates this directory exclusively, reserving the version.
        with storage_errors():
            if self.version_exists(job_id, version):
                raise StorageError("Artifact version already exists")
            yield self.root(job_id, version)

    def version_exists(self, job_id: str, version: int) -> bool:
        return self.root(job_id, version).exists() or self._path(job_id, version).exists()

    def read_text(self, job_id: str, version: int, path: str) -> str:
        with storage_errors():
            return self._path(job_id, version, path).read_text(encoding="utf-8")

    def download(self, job_id: str, version: int, path: str = "") -> Download:
        target = self._path(job_id, version, path)
        if not target.is_file():
            raise ArtifactNotFound("Artifact not found")
        return Download(target, target.name)

    def delete_job(self, job_id: str):
        with storage_errors():
            root = self.root(job_id)
            if root.exists():
                shutil.rmtree(root)


class S3ArtifactStorage:
    def __init__(self, cfg: Settings):
        self.bucket = cfg.s3_bucket
        self.prefix = f"{cfg.s3_prefix}/artifacts/" if cfg.s3_prefix else "artifacts/"
        self.scratch = cfg.data_dir.resolve()
        credentials = {}
        if cfg.s3_access_key_id.get_secret_value():
            credentials = {
                "aws_access_key_id": cfg.s3_access_key_id.get_secret_value(),
                "aws_secret_access_key": cfg.s3_secret_access_key.get_secret_value(),
                "aws_session_token": cfg.s3_session_token.get_secret_value() or None,
            }
        with storage_errors():
            # A dedicated Session avoids concurrent mutation of boto3's default session.
            self.client = boto3.session.Session().client(
                "s3",
                region_name=cfg.s3_region,
                endpoint_url=cfg.s3_endpoint_url or None,
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": cfg.s3_addressing_style},
                    connect_timeout=10,
                    read_timeout=60,
                    retries={"mode": "standard", "max_attempts": 3},
                ),
                **credentials,
            )

    def _key(self, job_id: str, version: int, path: str = "") -> str:
        return self.prefix + artifact_key(job_id, version, path)

    def version_exists(self, job_id: str, version: int) -> bool:
        with storage_errors():
            prefix = self._key(job_id, version, ".reserved").removesuffix(".reserved")
            if self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix, MaxKeys=1).get("Contents"):
                return True
            # Listing also works with prefix-scoped ListBucket policies, where HEAD
            # on an absent ZIP can return 403 rather than 404.
            key = self._key(job_id, version)
            objects = self.client.list_objects_v2(Bucket=self.bucket, Prefix=key, MaxKeys=1)
            return any(item["Key"] == key for item in objects.get("Contents", []))

    @contextmanager
    def export_directory(self, job_id: str, version: int, on_publish=None):
        with storage_errors():
            if self.version_exists(job_id, version):
                raise StorageError("Artifact version already exists")
            self.client.put_object(
                Bucket=self.bucket,
                Key=self._key(job_id, version, ".reserved"),
                Body=b"",
                IfNoneMatch="*",
            )
            self.scratch.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="docagent-export-", dir=self.scratch) as temp:
                root = Path(temp) / version_name(version)
                yield root
                files = [file for file in sorted(root.rglob("*")) if file.is_file()]
                for index, file in enumerate(files):
                    if file.is_file():
                        if on_publish:
                            on_publish(index, len(files) + 1, file.relative_to(root).as_posix())
                        self.client.upload_file(
                            str(file),
                            self.bucket,
                            self._key(job_id, version, file.relative_to(root).as_posix()),
                            ExtraArgs={
                                "ContentType": mimetypes.guess_type(file.name)[0]
                                or "application/octet-stream"
                            },
                        )
                if on_publish:
                    on_publish(len(files), len(files) + 1, "documentation.zip")
                self.client.upload_file(
                    str(root.with_suffix(".zip")),
                    self.bucket,
                    self._key(job_id, version),
                    ExtraArgs={"ContentType": "application/zip"},
                )

    def read_text(self, job_id: str, version: int, path: str) -> str:
        with storage_errors():
            response = self.client.get_object(Bucket=self.bucket, Key=self._key(job_id, version, path))
            with response["Body"] as body:
                # Match Path.read_text's universal newlines, including Windows exports.
                return body.read().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")

    def download(self, job_id: str, version: int, path: str = "") -> Download:
        key = self._key(job_id, version, path)
        with storage_errors():
            self.scratch.mkdir(parents=True, exist_ok=True)
            temporary = tempfile.TemporaryDirectory(prefix="docagent-download-", dir=self.scratch)
            target = Path(temporary.name) / "artifact"
            try:
                self.client.download_file(self.bucket, key, str(target))
            except BaseException:
                temporary.cleanup()
                raise
            return Download(target, key.rsplit("/", 1)[-1], temporary.cleanup)

    def delete_job(self, job_id: str):
        with storage_errors():
            # The trailing slash keeps deletion scoped to precisely one job.
            prefix = f"{self.prefix}{uuid.UUID(job_id)}/"
            pages = self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix)
            for page in pages:
                objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                if objects:
                    result = self.client.delete_objects(
                        Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True}
                    )
                    if result.get("Errors"):
                        # Keep the database record so the next retention run can retry.
                        raise StorageError("Artifact cleanup failed")


@lru_cache
def artifact_storage() -> LocalArtifactStorage | S3ArtifactStorage:
    cfg = settings()
    return S3ArtifactStorage(cfg) if cfg.storage_backend == "s3" else LocalArtifactStorage(cfg)
