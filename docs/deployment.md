# Deployment and operations

## Configuration

Use `.env.example` as a starting point. The application never returns server-side AI keys to the browser. In production inject keys through the deployment secret store rather than a checked-in file. Store a persistent Fernet key in `DOCAGENT_ENCRYPTION_KEY`; losing it makes stored GitHub tokens unreadable. The same key is required by API and worker processes. Development auto-generates a key in `.data/.encryption-key`.

Set `DOCAGENT_PUBLIC_URL` to the exact HTTPS browser origin, and `DOCAGENT_ALLOWED_HOSTS` to its hostname plus `localhost` for container health checks. The reverse proxy must preserve Host, terminate TLS and restrict request size and rate. Do not enable query-string access logs on OAuth callback routes. The supplied server disables access logging. Do not enable SDK debug logging.

`DOCAGENT_LOG_LEVEL` controls API, worker and scheduler console output through the supplied `docagent` entry points. It accepts `DEBUG`, `INFO` (default), `WARNING`, `ERROR` and `CRITICAL`, case-insensitively. Each entry point also accepts `--log-level` as a per-process override. SDK loggers retain a minimum `WARNING` threshold. Native processes need a restart after configuration changes; Compose containers need recreation (`docker compose up -d --force-recreate`) to reload environment files. Inspect output with `docker compose logs -f api worker scheduler`.

Configure full `DOCAGENT_DATABASE_URL` and `DOCAGENT_REDIS_URL` values in `.env`, with URL-encoded credentials where necessary. The supplied Compose file reuses the existing `pgvector`, `redis` and `minio` containers on the external `infra-shared` network. It does not create infrastructure containers, publish their ports or manage their volumes. Restrict their existing host bindings and network access independently.

Run `docagent compose-env` from the project root to generate the Git-ignored `.env.compose`. It preserves credentials, the database name and Redis database number while replacing loopback hosts with `pgvector:5432`, `redis:6379` and, for MinIO, `minio:9000`. The host `.env` remains unchanged. Regenerate the override after changing credentials. Compose 2.30+ is required for its raw environment-file format. Protect both files as secrets. For other aliases, use `--database-host`, `--redis-host` and `--minio-host`; configure the external network with `DOCAGENT_DOCKER_NETWORK`.

## Startup

1. Configure PostgreSQL, authenticated Redis, the existing artifact bucket and a persistent encryption key. Ensure all three infrastructure containers share `infra-shared`. Compose honors the environment mode in `.env`; for production set `DOCAGENT_ENV=production`, the HTTPS origin, allowed hosts and reviewer GitHub usernames.
2. Run `docagent compose-env`, `docker compose config --quiet`, `docker compose build api` and `docker compose up -d --no-build`. The initialization service applies migrations before the API and workers start. For a native installation, run `docagent init-db` explicitly before `docagent serve`.
3. Configure an HTTPS reverse proxy to `127.0.0.1:8000` and verify `/api/health`.
4. Register the exact GitHub OAuth callback if using OAuth. Test least-privilege PAT access for organizations and SSO.
5. Run `docagent check-services --write-probe` against the configured infrastructure. Once the API and worker are running, add `--api-url https://your-public-origin --output .data/live-checks/end-to-end.json` to test a real demo and save its package. For the local HTTP Compose setup, run `docker compose exec -T api docagent check-services --write-probe --api-url http://localhost:8000 --output /data/live-checks/compose.json`. See the [README live commands](../README.md#live-service-checks) and complete the external acceptance checks in `coverage.md` before accepting real customer data.

API instances and workers share PostgreSQL and either the local artifact volume or the same S3 bucket/prefix. Redis transports job IDs only; repository credentials are encrypted in PostgreSQL, then removed from the job at completion. Do not expose Redis publicly. A worker credential remains encrypted in an active job during recovery. Inspect repeatedly failing jobs during operations.

Local mode defaults to `DOCAGENT_JOB_BACKEND=local` and `DOCAGENT_REDIS_BACKEND=fake`. An in-process fakeredis list holds job IDs, consumed by a thread pool sized by `DOCAGENT_MAX_CONCURRENT_JOBS` (default 2). No Redis service, Docker or Celery worker is needed, and `DOCAGENT_REDIS_URL` is ignored. Graceful shutdown drains accepted work; a forced restart loses the in-memory queue. Restarted local queued/running jobs are marked failed and must be resubmitted. Completed artifacts and database history are retained. Do not run local mode behind multiple API processes.

To switch to a real Redis service, set `DOCAGENT_REDIS_BACKEND=real` and `DOCAGENT_REDIS_URL` in `.env`, then restart the application. Local execution can use real Redis, but its per-process queue is still temporary and does not provide restart recovery. Real Redis connection failures are reported rather than silently falling back to fakeredis.

For durable workers, also set `DOCAGENT_JOB_BACKEND=celery`, configure PostgreSQL and run `docagent worker --concurrency 2` plus `docagent scheduler --schedule .data/celerybeat-schedule`. Both use `DOCAGENT_LOG_LEVEL`; use `--log-level WARNING` to override it for one process. Use the supplied Linux containers for the Celery deployment. Compose explicitly selects `redis_backend=real`; production rejects fake Redis because in-process state cannot be shared with separate Celery workers. Workers renew a three-minute lease every 30 seconds. Celery Beat requeues expired leases and queued job IDs every minute; an atomic claim prevents duplicate deliveries from starting concurrent work. Recovery restarts the job with the same resolved input configuration and reusable content caches.

## Artifact storage

Before upgrading an existing deployment, run `docagent init-db` with API and workers stopped. Revision `003` adds the persisted resolved commit; revision `004` adds the singleton queue-admission lock. Queue counts and insertion now share one transaction so simultaneous requests cannot exceed owner or global job limits. The Compose migration service applies both revisions before starting the application.

GitHub jobs persist their resolved SHA before downloading source. Recovery reuses that SHA even if the requested branch or tag moves. Replaced workers cannot publish progress, change the pinned commit or commit their analysis. Existing jobs without a pinned SHA resolve it on their next execution.

`DOCAGENT_STORAGE_BACKEND=local` is the default and preserves the existing layout at `DOCAGENT_DATA_DIR/artifacts/<job-id>/`. The backend is a deployment setting, independent of the local/Celery job backend and fake/real Redis settings. Configure all API, worker and scheduler processes identically, then restart them after changes.

For **Amazon S3**, create a private bucket and configure:

```dotenv
DOCAGENT_STORAGE_BACKEND=s3
DOCAGENT_S3_BUCKET=my-document-artifacts
DOCAGENT_S3_REGION=ap-south-1
DOCAGENT_S3_PREFIX=docagent
DOCAGENT_S3_ENDPOINT_URL=
DOCAGENT_S3_ADDRESSING_STYLE=auto
DOCAGENT_S3_ACCESS_KEY_ID=
DOCAGENT_S3_SECRET_ACCESS_KEY=
DOCAGENT_S3_SESSION_TOKEN=
```

Empty application credential settings use the standard AWS credential chain, including IAM roles, AWS environment variables and shared profiles. Alternatively, set both `DOCAGENT_S3_ACCESS_KEY_ID` and `DOCAGENT_S3_SECRET_ACCESS_KEY`; temporary credentials also require `DOCAGENT_S3_SESSION_TOKEN`. Credentials stay on the server. The AWS SDK verifies TLS certificates; use `AWS_CA_BUNDLE` for a private certificate authority. See the [AWS SDK configuration reference](https://docs.aws.amazon.com/boto3/latest/guide/configuration.html).

For **MinIO**, use the same backend with your existing bucket and service account:

```dotenv
DOCAGENT_STORAGE_BACKEND=s3
DOCAGENT_S3_BUCKET=document-artifacts
DOCAGENT_S3_REGION=us-east-1
DOCAGENT_S3_ENDPOINT_URL=http://localhost:9000
DOCAGENT_S3_PREFIX=docagent
DOCAGENT_S3_ADDRESSING_STYLE=path
DOCAGENT_S3_ACCESS_KEY_ID=<MINIO_ACCESS_KEY>
DOCAGENT_S3_SECRET_ACCESS_KEY=<MINIO_SECRET_KEY>
DOCAGENT_S3_SESSION_TOKEN=
```

Use MinIO's S3 API port (commonly 9000), not its web console. Set the region to match the server if customized. In Docker, `localhost` refers to the application container: the generated `.env.compose` selects `http://minio:9000` on the shared network. For other infrastructure layouts, configure a reachable endpoint; omit `--minio-host` rewriting by managing the override file directly when using a remote S3-compatible service. AWS S3 with an empty custom endpoint is left unchanged by the generator. Use HTTPS outside local development. Compose reads the remaining S3 settings from `.env`; it does not provision a bucket or MinIO server.

Objects are stored as `<prefix>/artifacts/<job-id>/v0001/<file>` and `<prefix>/artifacts/<job-id>/v0001.zip`. An empty prefix uses `artifacts/` directly. The application needs bucket `s3:ListBucket` permission scoped to this prefix and object `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` and `s3:AbortMultipartUpload` permissions within it. Bucket creation and public access are unnecessary. Downloads and previews pass through the authenticated API, so the bucket can remain private and need not be accessible by the browser.

Exporting uses a temporary directory, uploads every generated file and the ZIP, and only then registers the committed version in the database. Failed uploads leave a reserved version that retries skip; retention removes those objects with the job. Remote downloads use temporary local files that are removed after the response. `DOCAGENT_DATA_DIR` must remain writable and have enough space for source extraction, generation and downloads. It also holds the development encryption key, the default SQLite database and the Compose scheduler state. With S3 and PostgreSQL, artifact sharing no longer requires a shared filesystem, though the supplied Compose deployment retains its volume for runtime state. The explicit `docagent scan --output ...` CLI command continues to export to that local output directory.

### Switching existing storage

Changing the backend, bucket or prefix does not automatically move existing artifacts. Stop API, worker and scheduler processes, back up the database and artifact directory, and copy the full `artifacts/` tree (including manifests and ZIPs) to the new location while retaining all job/version paths. For example, with AWS CLI credentials configured and the default local directory/prefix:

```sh
aws s3 sync .data/artifacts/ s3://my-document-artifacts/docagent/artifacts/
```

For MinIO, add `--endpoint-url https://your-minio-host` to the command. Use the actual mounted `/data/artifacts/` directory for a Compose deployment. Verify the copied files before switching configuration and restarting all processes. Retain the original data until historical previews and downloads have been checked. Reversing the switch requires copying the same tree back to local storage. Database records and package hashes remain unchanged.

## Retention and recovery

`DOCAGENT_RETENTION_DAYS` defaults to 30. `docagent cleanup` removes expired sessions/cache and old completed or failed job records and artifacts from the selected backend. S3 cleanup includes all committed and orphaned versions under each expired job's prefix; failed object deletion keeps the database records for a later retry. In versioned buckets, deletion creates delete markers: configure bucket lifecycle rules to expire noncurrent versions and incomplete multipart uploads if physical erasure is required. Object Lock or retention policies can prevent deletion. Celery Beat schedules cleanup daily; local mode runs it at startup. A normal job always removes its temporary source directory. After a worker hard kill, inspect and purge stale `docagent-source-*`, `docagent-tests-*`, `docagent-export-*` and `docagent-download-*` directories only after confirming no active job/request owns them.

Back up PostgreSQL, artifact storage and the encryption key separately, encrypt all backups and test restoration. Generated documents may contain proprietary code evidence even when known secrets are redacted. Restrict filesystem access and use encrypted disks/object storage. Monitor disk usage: archive and scan limits bound individual inputs but are not a global tenant storage quota.

Alembic schema migrations are packaged in `backend/docagent/migrations`. `docagent init-db` upgrades to the current head. The Compose migration service runs once before the API and workers; production API replicas do not race to run migrations. Add a reviewed revision for each model change and test upgrades and rollback against backups before deployment.

## Optional test worker

Set `DOCAGENT_TEST_EXECUTION_ENABLED=true` only on a dedicated worker, and set `DOCAGENT_TEST_IMAGE` to `registry/image@sha256:<64 hex characters>`. The image must include Python (the fixed wrapper), pytest or npm, and repository-specific test dependencies. Pre-pull it on the worker; the runner uses `--pull=never` and does not install packages.

The runner uses an unprivileged user, read-only source mount/root filesystem, no network, no capabilities, no-new-privileges, CPU/memory/PID limits, timeout and bounded tmpfs work/report space. It discards test logs and copies only the JUnit report, if present. It always removes its container after completion or timeout. Repository tests can still manipulate their own results; counts are provenance-labelled and never automatically map to generated UAT passes.

Do not mount the Docker socket into the public API container. A Docker worker has powerful host access: isolate it on a dedicated host/VM with no production secrets and configure daemon, image and filesystem policies. Container isolation is not a formal security boundary against a kernel exploit.
