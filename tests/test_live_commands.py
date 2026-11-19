import json
from pathlib import Path
from urllib.parse import urlsplit

import boto3
import fakeredis
import pytest
import yaml
from docagent.checks import redis_check, run_checks, storage_check
from docagent.compose_config import write_compose_env
from docagent.config import Settings
from moto import mock_aws
from sqlalchemy.engine import URL, make_url


def test_compose_overrides_preserve_credentials_and_host_configuration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    original = "# host settings remain unchanged\nDOCAGENT_PUBLIC_URL=http://localhost:8000\n"
    Path(".env").write_text(original)
    password = "p@$'${LITERAL}:/%"
    database = URL.create("postgresql+psycopg", username="app", password=password,
                          host="127.0.0.1", port=15432, database="docagent", query={"application_name": "folio"})
    cfg = Settings(_env_file=None, database_url=database.render_as_string(hide_password=False),
                   redis_url="redis://:p$word@127.0.0.1:16379/1?client_name=${LITERAL}",
                   storage_backend="s3", s3_bucket="bucket", s3_endpoint_url="http://127.0.0.1:19000")
    result = write_compose_env(cfg, Path(".env.compose"))
    values = dict(line.split("=", 1) for line in Path(".env.compose").read_text().splitlines()
                  if line and not line.startswith("#"))
    converted = make_url(values["DOCAGENT_DATABASE_URL"])
    assert converted.password == password
    assert converted.host == "pgvector" and converted.port == 5432
    assert converted.query == database.query
    redis = urlsplit(values["DOCAGENT_REDIS_URL"])
    assert redis.hostname == "redis" and redis.port == 6379
    assert redis.password == "p$word" and redis.path == "/1" and redis.query == "client_name=${LITERAL}"
    assert values["DOCAGENT_S3_ENDPOINT_URL"] == "http://minio:9000"
    assert Path(".env").read_text() == original
    assert password not in json.dumps(result)


def test_compose_generator_refuses_to_replace_host_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path(".env").write_text("KEEP=unchanged\n")
    with pytest.raises(ValueError, match="separate output"):
        write_compose_env(Settings(_env_file=None), Path(".env"))
    assert Path(".env").read_text() == "KEEP=unchanged\n"


def test_compose_reuses_external_infrastructure():
    compose = yaml.safe_load(Path("compose.yaml").read_text())
    assert set(compose["services"]) == {"migrate", "api", "worker", "scheduler"}
    assert set(compose["volumes"]) == {"artifacts"}
    assert compose["networks"]["infrastructure"]["external"] is True
    for service in compose["services"].values():
        assert service["networks"] == ["infrastructure"]
        assert service["env_file"][1] == {"path": ".env.compose", "format": "raw"}


def test_service_errors_do_not_expose_credentials(monkeypatch):
    import docagent.checks as checks

    secret = "a-sensitive-database-password"
    monkeypatch.setattr(checks, "settings", lambda: Settings(_env_file=None))

    def fail(_):
        raise RuntimeError("Connection failed: password=" + secret)

    monkeypatch.setattr(checks, "postgres_check", fail)
    monkeypatch.setattr(checks, "redis_check", lambda *_: {})
    monkeypatch.setattr(checks, "storage_check", lambda *_: {})
    monkeypatch.setattr(checks, "encryption_check", lambda: {})
    result = run_checks(api_url="http://localhost:8000")
    assert result["status"] == "failed"
    assert result["checks"]["api_demo"]["status"] == "skipped"
    assert result["checks"]["postgresql"]["error_type"] == "RuntimeError"
    assert secret not in json.dumps(result)


def test_redis_probe_preserves_unrelated_keys(monkeypatch):
    import docagent.checks as checks

    client = fakeredis.FakeRedis(decode_responses=True)
    client.set("existing-application-data", "keep")
    monkeypatch.setattr(checks, "create_redis_client", lambda _: client)
    assert redis_check(Settings(_env_file=None, redis_backend="real"), True)["write_probe"] is True
    assert client.keys("*") == ["existing-application-data"]


@mock_aws
def test_storage_probe_preserves_unrelated_artifacts(tmp_path):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="live-check-bucket")
    sentinel = "docagent/artifacts/existing-application-data.txt"
    client.put_object(Bucket="live-check-bucket", Key=sentinel, Body=b"keep")
    cfg = Settings(_env_file=None, storage_backend="s3", s3_bucket="live-check-bucket", data_dir=tmp_path,
                   s3_access_key_id="test", s3_secret_access_key="test")
    result = storage_check(cfg, True)
    assert result["zip_checksum"] and result["immutable_version"] and result["temporary_probe_deleted"]
    assert [item["Key"] for item in client.list_objects_v2(Bucket="live-check-bucket")["Contents"]] == [sentinel]
