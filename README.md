# Folio Repository Documentation Agent

Folio is a Python and React application for turning a GitHub repository into a versioned, evidence-linked documentation package. It includes a working local demo, static analysis, optional AI synthesis, document exports and authenticated review workflows.

The repository is an initial implementation, not a certification of production readiness. The local workflow and automated checks are runnable without credentials. Live GitHub OAuth/private-repository access, provider calls and the Docker execution worker require deployment-specific validation before production rollout. See [implementation coverage](docs/coverage.md) for precise scope and limits.

## Run locally

Requires Python 3.12+ and Node.js 22+. Run from the project root.

```powershell
python -m pip install uv==0.9.18
python -m uv sync --frozen --extra dev
Copy-Item .env.example .env
Set-Location frontend
npm.cmd ci
npm.cmd run build
Set-Location ..
./.venv/Scripts/python.exe -m docagent.cli serve
```

To generate an encryption key, run this command from the project root:

```powershell
./.venv/Scripts/python.exe -m docagent.cli key
```

Copy the generated value into `DOCAGENT_ENCRYPTION_KEY` in `.env`, then restart the application. If `.data/.encryption-key` already exists, reuse its value instead to preserve access to saved GitHub tokens. Keep the key private and do not commit `.env`.

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

## GitHub and AI configuration

Public repositories need only a GitHub URL or `owner/repository`. To discover user and organization repositories, connect a fine-grained PAT with **Metadata: read** and **Contents: read** on selected repositories. Organization SSO and token restrictions still apply. Repository discovery fetches all accessible pages; filtering is local.

Alternatively, set `DOCAGENT_GITHUB_CLIENT_ID` and `DOCAGENT_GITHUB_CLIENT_SECRET` for a GitHub OAuth app. Register `{DOCAGENT_PUBLIC_URL}/api/auth/github/callback`. OAuth uses expiring, one-time state and PKCE. Default `read:user` access is suitable for public repositories. Classic OAuth's `repo` scope grants broader access than read-only; prefer a fine-grained PAT for least-privilege private access. Expired/revoked credentials require reconnecting; automatic token refresh and GitHub App installation tokens are not implemented.

Set the desired `DOCAGENT_OPENAI_API_KEY`, `DOCAGENT_ANTHROPIC_API_KEY` or `DOCAGENT_GEMINI_API_KEY` on the server. Configure the corresponding `*_MODEL`, or type a model ID in the interface. Model availability is account-specific; no paid provider is enabled by default. SDK adapters use [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Claude structured output parsing](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), and [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output). They validate Pydantic schemas, retry transient failures, use only explicitly selected fallbacks, and record available token usage. No tools or repository-supplied instructions are executed by the LLM.

Private evidence requires explicit consent for **every** selected provider, including fallbacks. Secret files are excluded; known credentials are redacted. Add a `.docagentignore` using gitignore syntax to exclude proprietary paths. Redaction cannot identify every possible secret or sensitive business value. Review exclusions before authorizing external processing.

## Review and acceptance

Add authorized GitHub usernames to the server's comma-separated `DOCAGENT_REVIEWERS`. Approval cannot be recorded by an anonymous session or merely by typing a stakeholder name. Each analysis belongs to its creator's authenticated GitHub identity (or anonymous session). An authenticated owner can use the **Access** tab to grant or revoke viewer/reviewer access to a verified GitHub account. Reviewers need both access to the analysis and membership in the server allowlist.

- Generated requirements are candidates. Static declarations can be verified facts; business intent and every AI conclusion remain inferred.
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

## Deployment

See [deployment and operations](docs/deployment.md) and [security boundaries](docs/security.md). `compose.yaml` provides API, Celery workers, scheduler, PostgreSQL and Redis. A multi-stage Docker build bundles the React frontend. `uv.lock` and `frontend/package-lock.json` lock dependencies.

Generate an encryption key with `docagent key`, configure an HTTPS public URL and allowed hostname, set a strong `POSTGRES_PASSWORD`, then run `docker compose up --build -d` behind an HTTPS reverse proxy. The application fails startup if production mode lacks the encryption key, HTTPS URL, PostgreSQL or Celery. Docker is not required for local static analysis.

Optional test execution is disabled by default. It requires a dedicated worker with Docker and an administrator-built, digest-pinned image containing all needed test dependencies. Tests run with no network, no Linux capabilities, a read-only root filesystem, unprivileged identity, bounded memory/CPU/processes and ephemeral writable filesystems. No package installation takes place during analysis. The default Compose deployment intentionally does not expose a Docker socket.

## Development and checks

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
