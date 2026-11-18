import hashlib
import io
import uuid
import zipfile
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from docagent.config import Settings, settings
from docagent.db import DocumentVersion, Job, now, session_factory
from docagent.jobs import cleanup, next_version, output_root, run_job
from docagent.storage import (
    ArtifactNotFound,
    InvalidArtifactPath,
    LocalArtifactStorage,
    S3ArtifactStorage,
    StorageError,
    artifact_storage,
)
from moto import mock_aws
from pydantic import ValidationError


@pytest.fixture
def s3(isolated, monkeypatch):
    monkeypatch.setenv("DOCAGENT_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("DOCAGENT_S3_BUCKET", "test-artifacts")
    monkeypatch.setenv("DOCAGENT_S3_REGION", "us-east-1")
    monkeypatch.setenv("DOCAGENT_S3_PREFIX", "test/deployment")
    monkeypatch.setenv("DOCAGENT_S3_ENDPOINT_URL", "")
    monkeypatch.setenv("DOCAGENT_S3_ADDRESSING_STYLE", "path")
    monkeypatch.setenv("DOCAGENT_S3_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("DOCAGENT_S3_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("DOCAGENT_S3_SESSION_TOKEN", "")
    settings.cache_clear()
    artifact_storage.cache_clear()
    with mock_aws():
        storage = artifact_storage()
        storage.client.create_bucket(Bucket=storage.bucket)
        yield storage
    artifact_storage.cache_clear()
    settings.cache_clear()


def config(**kwargs):
    # Ignore the developer's .env and explicitly override fixture environment defaults.
    return Settings(_env_file=None, storage_backend="s3", s3_bucket="test-artifacts", **kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"s3_bucket": ""},
        {"s3_bucket": "s3://bucket"},
        {"s3_access_key_id": "incomplete"},
        {"s3_secret_access_key": "incomplete"},
        {"s3_session_token": "incomplete"},
        {"s3_prefix": "../other"},
        {"s3_prefix": "foo//bar"},
        {"s3_endpoint_url": "ftp://minio:9000"},
        {"s3_endpoint_url": "http://key:secret@minio:9000"},
        {"s3_endpoint_url": "http://minio:9000/console"},
    ],
)
def test_invalid_s3_settings(kwargs):
    values = {"storage_backend": "s3", "s3_bucket": "test-artifacts", **kwargs}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_minio_configuration_and_credential_chain(monkeypatch):
    session = Mock()
    monkeypatch.setattr(boto3.session, "Session", lambda: session)
    cfg = config(
        s3_endpoint_url="http://minio:9000",
        s3_addressing_style="path",
        s3_prefix="/team/docs/",
        s3_access_key_id="access",
        s3_secret_access_key="secret",
        s3_session_token="token",
    )
    storage = S3ArtifactStorage(cfg)
    kwargs = session.client.call_args.kwargs
    assert kwargs["endpoint_url"] == "http://minio:9000"
    assert kwargs["config"].s3["addressing_style"] == "path"
    assert kwargs["config"].signature_version == "s3v4"
    assert kwargs["aws_secret_access_key"] == "secret"
    assert kwargs["aws_session_token"] == "token"
    assert storage.prefix == "team/docs/artifacts/"
    assert "secret" not in repr(cfg.s3_secret_access_key)
    S3ArtifactStorage(config(s3_prefix=""))
    assert "aws_access_key_id" not in session.client.call_args.kwargs


@pytest.mark.parametrize("backend", ["local", "s3"])
def test_storage_roundtrip_and_isolation(backend, s3, tmp_path):
    storage = s3 if backend == "s3" else LocalArtifactStorage(Settings(_env_file=None, data_dir=tmp_path))
    job_id, other_id = str(uuid.uuid4()), str(uuid.uuid4())
    for identity in (job_id, other_id):
        with storage.export_directory(identity, 1) as root:
            root.mkdir(parents=True)
            (root / "nested").mkdir()
            (root / "nested" / "readme.md").write_text("# Café\n", encoding="utf-8")
            root.with_suffix(".zip").write_bytes(b"package")
    assert storage.version_exists(job_id, 1)
    assert not storage.version_exists(job_id, 2)
    assert storage.read_text(job_id, 1, "nested/readme.md") == "# Café\n"
    download = storage.download(job_id, 1)
    assert download.filename == "v0001.zip"
    assert download.path.read_bytes() == b"package"
    if download.cleanup:
        download.cleanup()
        assert not download.path.exists()
    with pytest.raises(StorageError, match="already exists"):
        with storage.export_directory(job_id, 1):
            pytest.fail("Existing version must not be replaced")
    for path in ("../other", "/etc/passwd", "nested/../../other", "C:/secret", "..\\secret", "a//b", "a/./b"):
        with pytest.raises(InvalidArtifactPath):
            storage.download(job_id, 1, path)
    with pytest.raises(ArtifactNotFound):
        storage.download(job_id, 1, "missing.md")
    storage.delete_job(job_id)
    storage.delete_job(job_id)  # Retention is retryable.
    assert not storage.version_exists(job_id, 1)
    assert storage.version_exists(other_id, 1)


def test_s3_generation_previews_downloads_history_and_retention(s3, client, completed, reviewer, tmp_path):
    job_id = completed["id"]
    url = f"/api/jobs/{job_id}"
    assert not output_root(job_id).exists()
    assert not list(settings().data_dir.glob("docagent-export-*"))
    files = client.get(f"{url}/files")
    assert files.status_code == 200
    markdown = next(file["path"] for file in files.json()["files"] if file["path"].endswith(".md"))
    preview = client.get(f"{url}/preview", params={"path": markdown})
    assert preview.status_code == 200
    individual = client.get(f"{url}/download", params={"path": markdown})
    assert individual.status_code == 200
    assert individual.text.replace("\r\n", "\n") == preview.json()["content"]
    package = client.get(f"{url}/download")
    assert package.status_code == 200
    assert package.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        assert any(name.endswith(".docx") for name in archive.namelist())
    with session_factory()() as db:
        version = db.get(DocumentVersion, (job_id, 1))
        assert version.package_sha256 == hashlib.sha256(package.content).hexdigest()
    assert not list(settings().data_dir.glob("docagent-download-*"))

    # A different API/worker machine needs no local artifact copy.
    s3.scratch = tmp_path / "another-host"
    assert client.get(f"{url}/download").content == package.content
    assert not list(s3.scratch.glob("docagent-download-*"))
    changed = client.post(
        f"{url}/reviews",
        json={
            "stage": "requirements",
            "decision": "comment",
            "comment": "Reviewed the source",
            "baseline_hash": completed["baseline_hash"],
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == 2
    assert client.get(f"{url}/download", params={"version": 1}).content == package.content
    for endpoint in ("files", "download"):
        assert client.get(f"{url}/{endpoint}", params={"version": 3}).status_code == 404
    assert client.get(f"{url}/download", params={"path": "../../other"}).status_code == 400
    assert client.get(f"{url}/download", params={"path": "missing.md"}).status_code == 404
    assert client.get(f"{url}/preview", params={"path": "../../other.md"}).status_code == 404
    assert client.get(f"{url}/preview", params={"path": "manifest.json"}).status_code == 404
    client.cookies.clear()
    client.get("/api/session")
    for endpoint in ("files", "download", "preview"):
        assert client.get(f"{url}/{endpoint}", params={"path": markdown}).status_code == 404

    with session_factory()() as db:
        db.get(Job, job_id).created = now() - timedelta(days=90)
        db.commit()
    assert cleanup() == 1
    assert not s3.version_exists(job_id, 1)
    assert not s3.version_exists(job_id, 2)
    with session_factory()() as db:
        assert db.get(Job, job_id) is None


def test_partial_upload_is_not_committed_and_retry_skips_it(s3, client, monkeypatch):
    original_upload = s3.client.upload_file

    def fail_zip(filename, bucket, key, **kwargs):
        if key.endswith(".zip"):
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "sensitive-sdk-details"}}, "PutObject"
            )
        return original_upload(filename, bucket, key, **kwargs)

    monkeypatch.setattr(s3.client, "upload_file", fail_zip)
    job_id = client.post("/api/demo", json={}).json()["id"]
    run_job(job_id)
    with session_factory()() as db:
        job = db.get(Job, job_id)
        assert job.status == "failed"
        assert "sensitive-sdk-details" not in job.message
        assert db.get(DocumentVersion, (job_id, 1)) is None
        assert next_version(job) == 2
        job.status = "queued"
        db.commit()
    assert s3.version_exists(job_id, 1)
    assert not list(settings().data_dir.glob("docagent-export-*"))
    monkeypatch.setattr(s3.client, "upload_file", original_upload)
    run_job(job_id)
    result = client.get(f"/api/jobs/{job_id}").json()
    assert result["status"] == "completed"
    assert result["version"] == 2
    assert client.get(f"/api/jobs/{job_id}/download", params={"version": 1}).status_code == 404
    assert client.get(f"/api/jobs/{job_id}/files", params={"version": 1}).status_code == 404
    assert client.get(f"/api/jobs/{job_id}/download").status_code == 200


def test_s3_error_is_sanitized_and_download_scratch_is_removed(s3, client, completed):
    with Stubber(s3.client) as stub:
        stub.add_client_error("head_object", "AccessDenied", "private-secret-detail", 403)
        response = client.get(f"/api/jobs/{completed['id']}/download")
        assert response.status_code == 503
        assert "private-secret-detail" not in response.text
    assert not list(settings().data_dir.glob("docagent-download-*"))


def test_s3_failed_review_preserves_committed_version(s3, client, completed, reviewer, monkeypatch):
    def unavailable(*args, **kwargs):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "secret"}}, "PutObject")

    monkeypatch.setattr(s3.client, "upload_file", unavailable)
    response = client.post(
        f"/api/jobs/{completed['id']}/reviews",
        json={
            "stage": "requirements",
            "decision": "comment",
            "comment": "Reviewed the source",
            "baseline_hash": completed["baseline_hash"],
        },
    )
    assert response.status_code == 503
    with session_factory()() as db:
        job = db.get(Job, completed["id"])
        assert job.version == 1
        assert db.get(DocumentVersion, (job.id, 2)) is None
        assert next_version(job) == 3
    assert client.get(f"/api/jobs/{completed['id']}/download").status_code == 200


def test_cleanup_failure_retains_records_for_retry(s3, client, completed, monkeypatch):
    with session_factory()() as db:
        db.get(Job, completed["id"]).created = now() - timedelta(days=90)
        db.commit()
    original = s3.client.delete_objects
    monkeypatch.setattr(s3.client, "delete_objects", lambda **kwargs: {"Errors": [{"Code": "AccessDenied"}]})
    with pytest.raises(StorageError, match="cleanup failed"):
        cleanup()
    with session_factory()() as db:
        assert db.get(Job, completed["id"]) is not None
        assert db.get(DocumentVersion, (completed["id"], 1)) is not None
    monkeypatch.setattr(s3.client, "delete_objects", original)
    assert cleanup() == 1


def test_s3_cleanup_paginates_and_stays_in_job_prefix(s3):
    job_id = str(uuid.uuid4())
    prefix = f"{s3.prefix}{job_id}/"
    with Stubber(s3.client) as stub:
        stub.add_response(
            "list_objects_v2",
            {
                "Contents": [{"Key": prefix + "a"}],
                "IsTruncated": True,
                "NextContinuationToken": "next",
            },
            {"Bucket": s3.bucket, "Prefix": prefix},
        )
        stub.add_response(
            "delete_objects",
            {},
            {
                "Bucket": s3.bucket,
                "Delete": {"Objects": [{"Key": prefix + "a"}], "Quiet": True},
            },
        )
        stub.add_response(
            "list_objects_v2",
            {
                "Contents": [{"Key": prefix + "b"}],
                "IsTruncated": False,
            },
            {"Bucket": s3.bucket, "Prefix": prefix, "ContinuationToken": "next"},
        )
        stub.add_response(
            "delete_objects",
            {},
            {
                "Bucket": s3.bucket,
                "Delete": {"Objects": [{"Key": prefix + "b"}], "Quiet": True},
            },
        )
        s3.delete_job(job_id)
        stub.assert_no_pending_responses()


def test_orphan_zip_reserves_version(s3):
    job_id = str(uuid.uuid4())
    s3.client.put_object(Bucket=s3.bucket, Key=f"{s3.prefix}{job_id}/v0002.zip", Body=b"orphan")
    assert next_version(SimpleNamespace(id=job_id, version=1)) == 3


def test_s3_version_check_uses_only_prefix_scoped_listing(s3, monkeypatch):
    job_id = str(uuid.uuid4())
    monkeypatch.setattr(s3.client, "head_object", Mock(side_effect=AssertionError("Unscoped HEAD")))
    # A similarly named object must not reserve this version.
    key = f"{s3.prefix}{job_id}/v0001.zip"
    s3.client.put_object(Bucket=s3.bucket, Key=key + ".other", Body=b"other")
    assert not s3.version_exists(job_id, 1)
    s3.client.put_object(Bucket=s3.bucket, Key=key, Body=b"package")
    assert s3.version_exists(job_id, 1)
