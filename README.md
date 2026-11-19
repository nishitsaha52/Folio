# Folio Repository Documentation Agent

Folio is a Python and React application for turning a GitHub repository into a versioned, evidence-linked documentation package. It includes a working local demo, static analysis, optional AI synthesis, document exports and authenticated review workflows.

The repository is an initial implementation, not a certification of production readiness. The local workflow and automated checks are runnable without credentials. Live GitHub OAuth/private-repository access, provider calls and the Docker execution worker require deployment-specific validation before production rollout. See [implementation coverage](docs/coverage.md) for precise scope and limits.

## Run locally

Requires Python 3.12+ and Node.js 22+. Run from the project root.

Create the local configuration separately, once, if `.env` does not already exist:

```powershell
Copy-Item .env.example .env
```

Install the Python dependencies so the key-generation command is available:

```powershell
python -m pip install uv==0.9.18
python -m uv sync --frozen --extra dev
```

To generate an encryption key, run this command from the project root:

```powershell
./.venv/Scripts/python.exe -m docagent.cli key
```

Copy the generated value into `DOCAGENT_ENCRYPTION_KEY` in `.env` before starting the application. If `.data/.encryption-key` already exists, reuse its value instead to preserve access to saved GitHub tokens. Keep the key private and do not commit `.env`.

Install dependencies, build the frontend and start the application:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run build
Set-Location ..
./.venv/Scripts/python.exe -m docagent.cli init-db
./.venv/Scripts/python.exe -m docagent.cli serve
```

Run `init-db` before the first start and after application upgrades to apply database migrations explicitly. Development startup also initializes the database, which is why a separate command was previously unnecessary in the quick start. Compose runs migrations in its dedicated `migrate` service before starting the API and workers.

Open **http://localhost:8000**. Select **Explore the demo** to analyze the bundled inventory service and download a real package without GitHub authentication or paid AI calls. The demo fingerprint is explicitly identified as a local snapshot, not a GitHub commit.

Local jobs use **fakeredis by default**. No Redis server or Celery worker is needed. The in-memory queue lives inside the API process; completed documents and analysis history remain in the configured database and artifact storage. Pending jobs do not survive an application restart.

Artifacts use local storage by default. Set `DOCAGENT_STORAGE_BACKEND=s3` to store document versions, individual files and ZIP packages in Amazon S3 or MinIO. Configure the bucket and credentials in `.env`; for MinIO also set its S3 API endpoint and `DOCAGENT_S3_ADDRESSING_STYLE=path`. See [storage configuration and migration](docs/deployment.md#artifact-storage) for complete examples. `DOCAGENT_DATA_DIR` remains the local working directory for temporary files and runtime state.

```dotenv
DOCAGENT_JOB_BACKEND=local
DOCAGENT_REDIS_BACKEND=fake
```

When ready to use a real Redis service, set `DOCAGENT_REDIS_BACKEND=real` and `DOCAGENT_REDIS_URL=redis://localhost:6379/0` in `.env`, then restart. You can retain local job execution, or set `DOCAGENT_JOB_BACKEND=celery` and start the Celery worker and scheduler described in [deployment](docs/deployment.md). Celery requires real Redis. The production Compose configuration selects real Redis automatically.

On Linux or macOS, use `uv run docagent serve` after `uv sync --frozen --extra dev`; use `npm` instead of `npm.cmd`. On Windows, `scripts/start.ps1` starts a prepared installation.

For frontend development, run the API and `npm run dev` separately. Set `DOCAGENT_PUBLIC_URL=http://localhost:5173` so the CSRF origin and OAuth callback match Vite's proxied origin. For the built frontend use `http://localhost:8000`.

## Configuration options and use cases

Set these values in `.env`, then restart the application. The options below are supported by the current implementation; defaults refer to application settings.

| Setting | Value | Use case |
| --- | --- | --- |
| `DOCAGENT_STORAGE_BACKEND` | `local` (default) | Store generated artifacts on disk. Suitable for local development or a deployment with a shared artifact volume. |
| `DOCAGENT_STORAGE_BACKEND` | `s3` | Store artifacts in Amazon S3 or MinIO. Useful when API instances and workers run on different machines. Requires bucket configuration. |
| `DOCAGENT_S3_ADDRESSING_STYLE` | `auto` (default) | Let the AWS SDK choose the addressing style. Suitable for standard AWS S3 deployments. |
| `DOCAGENT_S3_ADDRESSING_STYLE` | `path` | Put the bucket in the URL path, such as `endpoint/bucket/key`. Commonly used with MinIO. |
| `DOCAGENT_S3_ADDRESSING_STYLE` | `virtual` | Put the bucket in the hostname, such as `bucket.endpoint/key`. Requires compatible DNS and TLS configuration. |
| `DOCAGENT_JOB_BACKEND` | `local` (default) | Run jobs inside the API process. Simple setup for development and demos; pending jobs do not survive a restart. |
| `DOCAGENT_JOB_BACKEND` | `celery` | Run jobs in separate workers with recovery support. Use for production and distributed deployments. Requires real Redis. |
| `DOCAGENT_REDIS_BACKEND` | `fake` (default) | Use in-memory fakeredis. No Redis server required; works with local jobs only. |
| `DOCAGENT_REDIS_BACKEND` | `real` | Connect to the Redis service specified by `DOCAGENT_REDIS_URL`. Supports local jobs or Celery. |
| `DOCAGENT_TEST_EXECUTION_ENABLED` | `false` (default) | Analyze sources and generate proposed test cases without executing repository tests. |
| `DOCAGENT_TEST_EXECUTION_ENABLED` | `true` | Permit users to request execution of existing repository tests. Requires Docker, a trusted digest-pinned `DOCAGENT_TEST_IMAGE` containing the dependencies, and a dedicated worker setup. Execution must still be selected for each analysis. |

S3 addressing follows the [AWS SDK configuration](https://docs.aws.amazon.com/boto3/latest/guide/configuration.html#using-a-configuration-file). The addressing setting is used only with `DOCAGENT_STORAGE_BACKEND=s3`; see [artifact storage](docs/deployment.md#artifact-storage) for AWS and MinIO examples. Enabling repository execution does not automatically pass any generated UAT case.

### Job and Redis combinations

| Job backend | Redis backend | Intended use |
| --- | --- | --- |
| `local` | `fake` | Simplest local setup; no external Redis service. |
| `local` | `real` | Local execution using an existing Redis service. The queue remains process-scoped and does not provide restart recovery. |
| `celery` | `real` | Separate workers and durable job recovery. Start the Celery worker and scheduler described in [deployment](docs/deployment.md). |

`celery` with `fake` Redis is rejected. Production mode additionally requires PostgreSQL, HTTPS and an encryption key.

The supplied `compose.yaml` explicitly selects `DOCAGENT_JOB_BACKEND=celery`, `DOCAGENT_REDIS_BACKEND=real` and `DOCAGENT_TEST_EXECUTION_ENABLED=false`, overriding those `.env` values. Changing them for Compose requires updating its service environment configuration.

### Log level

Set the console log level in `.env` for the API, worker and scheduler:

```dotenv
DOCAGENT_LOG_LEVEL=INFO
```

| Value | Use case |
| --- | --- |
| `DEBUG` | Detailed application and server diagnostics during troubleshooting. |
| `INFO` (default) | Routine startup and worker activity, plus warnings and errors. |
| `WARNING` | Warnings and errors with less routine output. |
| `ERROR` | Errors and critical failures only. |
| `CRITICAL` | Critical failures only. |

Values are case-insensitive. Restart native API/worker/scheduler processes after changing the setting. For Compose, rebuild the image after updating application code, then run `docker compose up -d --force-recreate` to reload `.env`; `docker compose restart` keeps the old container environment. View console output with `docker compose logs -f api worker scheduler`.

Override the level for a single process with `--log-level`:

```powershell
./.venv/Scripts/python.exe -m docagent.cli serve --log-level DEBUG
./.venv/Scripts/python.exe -m docagent.cli worker --pool solo --concurrency 1 --log-level WARNING
./.venv/Scripts/python.exe -m docagent.cli scheduler --schedule .data/celerybeat-schedule --log-level WARNING
```

The command-line value takes precedence over `.env`. HTTP access logs remain disabled, and HTTP/AI/storage SDK loggers stay at `WARNING` or above even with `DEBUG`, to avoid verbose request and credential-bearing output. Logs go to the console; no application log file is created. These worker/scheduler commands forward the selected level to Celery; direct `celery` commands use their own `--loglevel` option.

## GitHub and AI configuration

Public repositories need only a GitHub URL or `owner/repository`. To discover user and organization repositories, connect a fine-grained PAT with **Metadata: read** and **Contents: read** on selected repositories. Organization SSO and token restrictions still apply. Repository discovery fetches all accessible pages; filtering is local.

Alternatively, set `DOCAGENT_GITHUB_CLIENT_ID` and `DOCAGENT_GITHUB_CLIENT_SECRET` for a GitHub OAuth app. Register `{DOCAGENT_PUBLIC_URL}/api/auth/github/callback`. OAuth uses expiring, one-time state and PKCE. Default `read:user` access is suitable for public repositories. Classic OAuth's `repo` scope grants broader access than read-only; prefer a fine-grained PAT for least-privilege private access. Expired/revoked credentials require reconnecting; automatic token refresh and GitHub App installation tokens are not implemented.

### GitHub OAuth scope options

`DOCAGENT_GITHUB_OAUTH_SCOPES` accepts space-separated GitHub scopes. Quote combinations in `.env`:

| Value | Use case |
| --- | --- |
| `read:user` (default) | GitHub sign-in, profile access and public-repository analysis. |
| `"read:user repo"` | OAuth access to private repositories the user can access. GitHub's classic `repo` scope includes broad write permissions. |
| `"read:user read:org"` | Read profile and organization-membership information. `read:org` alone does not grant private repository contents; Folio's current repository-discovery flow does not require this additional scope. |

For private repository analysis, a fine-grained PAT with **Metadata: read** and **Contents: read** avoids classic OAuth's broad `repo` permission. See [GitHub's scope definitions](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps).

### AI model options

Set the desired `DOCAGENT_OPENAI_API_KEY`, `DOCAGENT_ANTHROPIC_API_KEY` or `DOCAGENT_GEMINI_API_KEY` on the server. Configure the corresponding `*_MODEL`, or type a model ID in the interface. Model availability is account-specific; no paid provider is enabled by default. SDK adapters use [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Claude structured output parsing](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), and [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output). They validate Pydantic schemas, retry transient failures, use only explicitly selected fallbacks, and record available token usage. No tools or repository-supplied instructions are executed by the LLM.

Each model variable accepts **one model ID**, rather than a comma-separated list. The project does not maintain a fixed model allowlist. These candidates were checked against provider documentation on **19 November 2026**; the use-case groupings apply the providers' published speed, cost and capability tiers to Folio's workload.

| Variable | Lower-cost extraction | General documentation | More demanding analysis |
| --- | --- | --- | --- |
| `DOCAGENT_OPENAI_MODEL` | `gpt-6-luna` | `gpt-6.2-sol` | `gpt-6.2-astra` |
| `DOCAGENT_ANTHROPIC_MODEL` | `claude-haiku-5-5` | `claude-sonnet-5-5` | `claude-opus-5-5` |
| `DOCAGENT_GEMINI_MODEL` | `gemini-3.5-flash-lite` | `gemini-4-hydrogen` | `gemini-4-carbon` |

Check the current [OpenAI model catalog](https://developers.openai.com/api/docs/models), [Claude model catalog](https://platform.claude.com/docs/en/models/overview) and [Gemini model catalog](https://aistudio.google.com/docs/models) for availability and changes.

For general-purpose evaluation, use these model defaults with the corresponding API keys:

```dotenv
DOCAGENT_OPENAI_MODEL=gpt-6.2-sol
DOCAGENT_ANTHROPIC_MODEL=claude-sonnet-5-5
DOCAGENT_GEMINI_MODEL=gemini-4-hydrogen
```

These values prefill the interface. Users still select the provider and any fallback explicitly; setting all three model variables does not send evidence to all providers. Model values may be left blank for static-only use. Live provider calls remain unvalidated in this project: confirm account access and structured-output compatibility for the selected model before relying on it.

Private evidence requires explicit consent for **every** selected provider, including fallbacks. Secret files are excluded; known credentials are redacted. Add a `.docagentignore` using gitignore syntax to exclude proprietary paths. Redaction cannot identify every possible secret or sensitive business value. Review exclusions before authorizing external processing.

## Review and acceptance

Add authorized GitHub usernames to the server's comma-separated `DOCAGENT_REVIEWERS`. Approval cannot be recorded by an anonymous session or merely by typing a stakeholder name. Each analysis belongs to its creator's authenticated GitHub identity (or anonymous session). An authenticated owner can use the **Access** tab to grant or revoke viewer/reviewer access to a verified GitHub account. Reviewers need both access to the analysis and membership in the server allowlist.

- Generated requirements are candidates. Static declarations can be verified facts; business intent and every AI conclusion remain inferred.
- Static candidates group a public callable or model with its guards and constraints. Internal helpers and test fixtures remain available in findings and evidence. Reports paginate all requirements and test cases.
- Generated positive, negative and boundary tests begin **unexecuted**. AI synthesis can derive concrete scenario inputs, steps and expected outcomes from its cited evidence, including authentication and integration scenarios. Static fallback scenarios explicitly require fixture and acceptance-rule review before execution.
- Reviewers can edit requirement statements, record comments, request changes or explicitly approve the current baseline.
- A recorded result requires the current baseline, a test-case ID, actual outcome, evidence reference and reviewer attestation. Existing reports and manual UAT remain distinct.
- Repository execution counts are separate from generated UAT cases. A successful process never automatically passes a generated case.
- Final UAT approval requires current requirements approval and passing evidence for every case. New requirements invalidate prior results and approval; new result evidence invalidates prior UAT acceptance.
- Each mutation generates a new downloadable artifact version. History and prior decisions remain available. Electronic decisions identify the authenticated reviewer; handwritten signatures are never fabricated.

## Outputs

All seven requested deliverables are supported. Markdown previews are always included, with selectable DOCX and PDF exports. Packages also include a native XLSX traceability matrix, Mermaid and Graphviz source, SVG/PNG diagrams, JSON findings and evidence, gaps, baseline hashes and approval records.

```text
01-requirements/       SRS and requirements sign-off
02-testing/            Test/UAT report, RTM.xlsx and acceptance sign-off
03-architecture/       System architecture and diagram exports
04-data-flow/          DFD document and levels 0, 1 and 2
05-technology-stack/   Technology and dependency inventory
06-analysis/           Findings, evidence, gaps and workflow state
README.md
manifest.json
```

The selected documentation types determine which folders and files are generated. Unsupported Level 2 flows explicitly show insufficient evidence. Import edges are labelled as code dependencies, never as demonstrated runtime data flow.

## Local directory analysis

The CLI scans local sources without importing them, executing tests or using external AI. Choose an output directory outside the scanned source tree.

```powershell
./.venv/Scripts/python.exe -m docagent.cli scan ./examples/inventory --output ./outputs/inventory-docs --formats md docx pdf
```

This creates `outputs/inventory-docs/` and `outputs/inventory-docs.zip`. Each output directory has its own ZIP, including names containing dots. Existing output directories or ZIPs are rejected so earlier packages are preserved.

## Deployment

See [deployment and operations](docs/deployment.md) and [security boundaries](docs/security.md). `compose.yaml` provides the API, migration service, Celery worker and scheduler. It reuses your existing `pgvector`, `redis` and `minio` containers on the external `infra-shared` network. It does not create or manage those services or their data volumes. A multi-stage Docker build bundles the React frontend. `uv.lock` and `frontend/package-lock.json` lock dependencies.

### Compose with existing services

Requires Docker Compose 2.30+ and the existing services connected to `infra-shared`, with network aliases `pgvector`, `redis` and `minio`. Keep the configured credentials and host connection URLs in `.env`. Generate a separate, Git-ignored `.env.compose` with container connection URLs; the command preserves credentials and leaves `.env` unchanged:

```powershell
./.venv/Scripts/python.exe -m docagent.cli compose-env
docker compose config --quiet
docker compose build api
docker compose up -d --no-build
docker compose ps
docker compose exec -T api docagent check-services --write-probe --api-url http://localhost:8000 --output /data/live-checks/compose.json
```

The generated URLs use `pgvector:5432`, `redis:6379` and `minio:9000`. Regenerate `.env.compose` after changing connection credentials. Set `DOCAGENT_DOCKER_NETWORK` to change the shared network; use `compose-env --database-host NAME --redis-host NAME --minio-host NAME` for different service aliases. `DOCAGENT_API_PORT` controls the host port (default `8000`); set `DOCAGENT_PUBLIC_URL` to the matching browser origin. Keep `.env.compose` private because it contains connection credentials.

If Docker is installed only in WSL Ubuntu, prefix Docker commands with `wsl.exe -d Ubuntu --`, from this project directory. Run the Python commands above in PowerShell. If WSL cannot read Windows cache-directory metadata during a build, build from a project checkout in the WSL Linux filesystem.

Compose retains `DOCAGENT_ENV` from `.env`, so the current development setup can use HTTP on localhost. For production, set `DOCAGENT_ENV=production`, configure an HTTPS public URL, allowed hostname and persistent encryption key, and put the API behind an HTTPS reverse proxy. Production startup requires the encryption key, HTTPS URL, PostgreSQL and Celery. Docker is not required for local static analysis.

## Live service checks

These checks use the services configured in `.env` and require PostgreSQL, real Redis and an existing S3/MinIO bucket. Initialize or upgrade the schema first. The default check verifies schema compatibility, Redis connectivity, bucket listing and encryption without writing service probes:

```powershell
./.venv/Scripts/python.exe -m docagent.cli init-db
./.venv/Scripts/python.exe -m docagent.cli check-services
./.venv/Scripts/python.exe -m docagent.cli check-services --write-probe --output .data/live-checks/services.json
```

`--write-probe` additionally tests Redis write/read/delete and artifact upload/download, checksums and immutable versions. It removes only its own uniquely named temporary probes. Reports omit credentials; the command exits with a nonzero status on failure. Create the bucket beforehand; this command does not provision infrastructure.

For a complete demo through HTTP and the configured worker, start the API and, when using `DOCAGENT_JOB_BACKEND=celery`, a worker and scheduler. For Windows development, run these in three separate PowerShell terminals from the project root:

```powershell
# Terminal 1: API
./.venv/Scripts/python.exe -m docagent.cli serve
# Terminal 2: Windows development worker
./.venv/Scripts/python.exe -m docagent.cli worker --pool solo --concurrency 1
# Terminal 3: scheduler
./.venv/Scripts/python.exe -m docagent.cli scheduler --schedule .data/celerybeat-schedule
```

Use the supplied Linux containers for a production Celery deployment. Local job execution needs only the API. With the API and worker running, execute in another terminal:

```powershell
./.venv/Scripts/python.exe -m docagent.cli check-services --write-probe --api-url http://localhost:8000 --output .data/live-checks/end-to-end.json
```

This creates a retained demo analysis without external AI calls or repository-test execution. It checks HTTP access controls, previews, all export formats and package checksums against PostgreSQL and MinIO. The JSON report and matching `.zip` package are saved under `.data/live-checks/`. Use `--timeout 240` for a slower worker. For HTTPS deployments, use the public HTTPS URL with `--api-url` so secure session cookies work.

Optional browser checks against the running API require Playwright and Microsoft Edge:

```powershell
python -m uv pip install --python ./.venv/Scripts/python.exe playwright
./.venv/Scripts/python.exe scripts/ui_smoke.py --channel msedge --output .data/live-checks/browser
```

Optional test execution is disabled by default. It requires a dedicated worker with Docker and an administrator-built, digest-pinned image containing all needed test dependencies. Tests run with no network, no Linux capabilities, a read-only root filesystem, unprivileged identity, bounded memory/CPU/processes and ephemeral writable filesystems. No package installation takes place during analysis. The default Compose deployment intentionally does not expose a Docker socket.

## Development and checks

See [frontend organization](docs/frontend.md) for component boundaries, state ownership and interaction checks.

```powershell
./.venv/Scripts/python.exe -m ruff check backend tests
./.venv/Scripts/python.exe -m pytest --cov=docagent --cov-report=term-missing
Set-Location frontend
npm.cmd run build
npm.cmd test
```

The tests cover archive traversal, credential redaction, execution prevention, parser evidence, cache isolation, private-provider consent, fallback, document exports, access control and approval invalidation. GitHub Actions runs backend and frontend checks on pushes and pull requests. See the [validation record](docs/validation.md) for completed checks and live integration limits.

Optional browser acceptance: install Playwright and its Chromium browser, start the application, then run `python scripts/ui_smoke.py`. On Windows, `--channel msedge` uses installed Edge. The browser check runs the real demo, downloads all exports, checks previews and diagrams, confirms anonymous approval is disabled and checks mobile overflow. Only repository configuration layout uses an explicitly mocked API response.

Backend API: `/docs` and `/openapi.json`. Health: `/api/health`. The default local database, runtime data and artifacts live under `.data/` and are excluded from Git. S3 mode stores artifacts in the configured bucket; encrypted tokens and scan cache remain in the database.
