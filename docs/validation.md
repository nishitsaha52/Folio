# Validation record

## 19 November 2026 configurable logging

Added case-insensitive `DOCAGENT_LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; default `INFO`) and per-process `--log-level` overrides for `docagent serve`, `docagent worker` and `docagent scheduler`. Compose uses these entry points. HTTP access logging remains disabled; SDK loggers retain at least a `WARNING` threshold. The README documents levels, command overrides and container recreation after environment-file changes.

- Backend: **102 passed, one explicitly skipped integration test**; Ruff passed. New tests exercise environment validation, actual application/SDK log filtering, command-line precedence, Uvicorn access-log suppression and forwarding effective levels to worker/scheduler commands.
- Rebuilt the Linux image and started an isolated Compose stack against the existing external infrastructure. Migrations succeeded; the API was healthy and the worker/scheduler remained running. Captured console output contained `INFO` records from all three services and none of the configured credentials.
- The real live check passed with a 44-entry demo package, PostgreSQL/MinIO/API checksum agreement, previews and access controls. Reports are retained in `.data/logging-validation/services.json` and `logging.json`; the matching package is `demo.zip`. No external AI calls were made.
- Removed the isolated test containers and their scratch volume. Existing infrastructure containers retained their IDs and remained healthy. Generated demo records and MinIO artifacts were retained.

## 19 November 2026 Compose and documented live commands

Added permanent `docagent check-services` and `docagent compose-env` commands, documented explicit `init-db` in the README quick start, and changed Compose to reuse the existing `pgvector`, `redis` and `minio` containers on the external `infra-shared` network. Connection overrides are generated into the ignored `.env.compose`; the host `.env` remains unchanged.

- Backend verification: **92 passed, one explicitly skipped integration test**; Ruff and `git diff --check` passed. New regressions cover credential-preserving URL conversion, refusing to overwrite `.env`, external infrastructure topology, safe error reporting and preservation of unrelated Redis keys/MinIO objects during probe cleanup.
- Native live command: PostgreSQL schema revision `004` matched the application models; authenticated Redis, MinIO read/write/checksum/immutability/cleanup and encryption checks passed.
- Docker: built the multi-stage image, including the React production build, using a clean source-only Linux build context. Direct WSL builds from this Windows checkout hit a cache-directory metadata permission error; the workaround did not change or delete the Windows cache. `docker compose config --quiet` passed.
- Started an isolated Compose project on host port `18000`. The migration service exited successfully, the API became healthy, and the scheduler and Linux Celery worker (prefork concurrency two) ran against the existing infrastructure. The documented container `check-services --write-probe --api-url ...` command passed, including a real 44-entry package, PostgreSQL/MinIO/API checksum agreement, previews and access checks, without external AI calls.
- Headless Edge passed desktop/mobile layout, real generation/download, previews, SVG loading, configuration and anonymous approval restrictions with no JavaScript errors. The first attempt timed out during mobile navigation; the complete retry passed. Desktop and mobile screenshots were inspected.
- Saved the report/package under `.data/compose-validation/compose.json` and `compose.zip`, and browser evidence under `.data/compose-validation/browser-retry/`. Removed only the isolated application's containers and scratch volume. Original PostgreSQL, Redis and MinIO container IDs were unchanged and all three remained healthy; the external network and infrastructure volumes were preserved. Generated demo records/artifacts remain available in the configured services.

This adds single-host Linux Compose generation acceptance. Multi-host deployment, Linux worker-failure recovery, live GitHub authentication, paid AI providers, AWS S3 and isolated repository-test execution remain separate acceptance work. The entries below preserve earlier results and their then-current limits.

## 19 November 2026 live infrastructure acceptance

Tested the services configured in `.env` from the Windows host, using real PostgreSQL, authenticated Redis, MinIO and separate API/Celery worker/scheduler processes. The worker used the `solo` pool for this Windows development run. Each run used an isolated Celery queue; the configured database, Redis database and MinIO bucket/prefix were retained.

| Check | Result |
| --- | --- |
| PostgreSQL | Connected to `docagent` on PostgreSQL 18.6, applied migrations through `004`, and verified all 10 public tables match the application schema |
| Redis | Authenticated Redis 8.8.3 connection; PING and temporary write/read/delete passed |
| MinIO | Configured `docagent` bucket passed prefix listing, upload, text/ZIP retrieval, checksum validation, immutable-version reservation and deletion of temporary probe artifacts |
| API and Celery | A real HTTP demo request was delivered through Redis to a separate worker; PostgreSQL stored the completed job and committed document version |
| Exports | Downloaded a valid 44-entry ZIP containing seven DOCX files, seven PDFs, one XLSX, four SVGs and four PNGs; PostgreSQL's package checksum matched MinIO and the HTTP download |
| Previews and storage | Markdown preview matched the individual file download; committed artifacts were read from MinIO without a local artifact copy |
| Scheduler recovery | The real 60-second Beat schedule recovered a queued job after its isolated broker delivery was removed and another job with a deliberately expired worker lease; both completed and the lease-expiration audit was recorded |
| Access controls | Cross-session job/download access, path traversal, uncommitted version downloads, invalid CSRF and anonymous approval attempts were rejected |
| Concurrent admission | At an owner limit of two, three simultaneous HTTP requests returned `202`, `202`, `429`; PostgreSQL contained exactly two queued probe jobs |
| Browser acceptance | Headless Edge passed desktop/mobile layouts, real demo generation, all 44 package artifacts, Markdown preview, SVG loading, anonymous approval restrictions and configuration; no JavaScript errors were observed |
| Cleanup and retained evidence | Temporary MinIO/Redis probes and admission-only jobs were removed. Generated demo jobs and packages were retained. Test API/worker/scheduler processes were stopped |

Three programmatic jobs exercised normal generation and the two recovery scenarios; an additional demo ran through the browser. PostgreSQL cache reuse was also observed. Generated UAT cases remained unexecuted and no reviewer decisions or actual test-result attestations were fabricated. No external AI calls were made.

Credential-free reports and downloadable ZIPs are stored under the Git-ignored `.data/live-checks/` directory, with a combined summary at `.data/live-checks/live-testing-results.json`. No runtime source changes were needed for this acceptance run.

This validates the configured local infrastructure and Windows `solo` worker flow. Live GitHub OAuth/private repositories, paid AI providers, AWS S3, Linux/multiple-worker or multi-host deployment, and isolated Docker repository-test execution still need their own acceptance checks. Earlier entries below describe the scope and service availability at the time of those runs.

## 19 November 2026 reassessment

Checked the revised working tree on Windows using Python 3.12.10 and Node.js 24.18.0.

- Backend: the final full suite passed with 86 tests, one explicitly skipped service-integration test and 80% statement coverage, including both concurrent-admission regressions and worker/migration checks.
- Frontend: TypeScript/Vite production build passed; all 13 Vitest tests passed, covering configuration consent, authentication/CSRF rotation, review approval, test attestation, stale polling, pagination and requirement editing.
- Browser: headless Edge passed the real demo, all 44 package artifacts, Markdown preview, SVG diagrams, anonymous approval restrictions, configuration and desktop/mobile layout checks. No JavaScript errors were observed. Desktop and mobile screenshots were inspected.
- Regression checks reproduce and prevent missing Python package-root/multiple-import edges, sibling CLI ZIP replacement, changing commits on worker recovery and stale worker progress. Queue admission was additionally reproduced with two accepted requests at an owner limit of one; it is now serialized in the database, with regressions for both owner and global limits.
- Ruff passed. SQLite migrations match SQLAlchemy models. Existing deployments must apply revisions `003` and `004` before running the updated application.

The new CI `services` job starts disposable PostgreSQL and Redis services and runs a real Celery subprocess acceptance test. It was not exercised locally because those services are unavailable; the ordinary local suite skips it explicitly. To run it against disposable services, set `DOCAGENT_INTEGRATION_DATABASE_URL` and `DOCAGENT_INTEGRATION_REDIS_URL`, then run `pytest tests/integration -v`.

Live OAuth/private-repository access, paid AI providers, real S3/MinIO policies and Docker repository-test execution remain outside this local validation. The optional container runner is disabled by default and has 19% statement coverage in the local suite; it needs dedicated execution validation before enabling it.

## 19 November 2026 frontend extraction follow-up

Workspace sections, navigation/authentication presentation and individual report tabs were extracted into focused components. Repository discovery and artifact/audit loading now have dedicated hooks. App retains navigation/filter/credential state; Report retains search, pagination and baseline-bound mutation dialogs. See [frontend organization](frontend.md).

| Coordinator | Before | After |
| --- | --- | --- |
| `App.tsx` | 639 lines | 200 lines |
| `components/Report.tsx` | 657 lines | 155 lines |

The production build and final TypeScript check passed. All 19 Vitest tests passed, including filter/input persistence across navigation, stale artifact responses, Markdown preview success/failure and result submission through the extracted tests tab. Headless Edge passed the real demo and all 44 package artifacts without JavaScript errors. Desktop, mobile, report, configuration and diagram screenshots matched the preceding acceptance run pixel for pixel.

## 18 November 2026 record

Validated locally on 18 November 2026 with Python 3.12.10 and Node.js 22.12.0 on Windows.

| Check | Result |
| --- | --- |
| Backend automated suite | Full regression passed (67 tests); final storage regression passed (21 tests, including one additional prefix-permission regression) |
| Artifact storage | Local and emulated S3 generation, previews, ZIP/individual downloads, historical versions, cross-host retrieval, access isolation, failed uploads/reviews, orphan-version retry and paginated retention passed; MinIO endpoint/path-style and credential-chain selection tested |
| Local queue | fakeredis FIFO dispatch, graceful draining, isolated application lifetimes and demo-to-ZIP integration passed without a real Redis connection; real-client selection and connection failure handling tested with doubles |
| Python lint | Ruff passed |
| Frontend | TypeScript and Vite production build passed; Vitest passed |
| Browser acceptance | Headless Edge passed desktop/mobile layouts, real demo generation, ZIP download, Markdown preview, SVG loading, anonymous approval restrictions and configuration form checks |
| Browser JavaScript errors | None observed during the acceptance run |
| Demo exports | 44 files, including seven DOCX files, seven PDFs, XLSX RTM, Markdown, diagram sources and SVG/PNG exports |
| Export inspection | All seven DOCX files passed structural checks; all 18 PDF pages contained readable text within page bounds; representative PDF pages were visually inspected; XLSX retained test IDs, filters, frozen panes and unexecuted statuses |
| Live public GitHub access | `octocat/Hello-World` retrieved and analyzed at commit `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`; extensionless README included |
| Schema consistency | Alembic upgrades and SQLAlchemy model comparison passed |
| Formal workflow | Unauthorized approval, stale results, viewer-only review attempts, premature UAT acceptance and uncommitted artifact downloads were rejected in tests |

The browser configuration check uses a clearly identified mocked repository response. The demo generation and package downloads use the real local backend. Provider fallback and private-code consent are tested with doubles; no private code or paid AI requests were sent during development.

Not exercised against live services in this environment: S3/MinIO buckets and their deployment policies, GitHub OAuth callback and private/organization repositories, OpenAI/Claude/Gemini generation, PostgreSQL/Celery multi-process operation, Docker image builds and isolated repository-test execution. These require deployment credentials and infrastructure. Generated test cases in the demo remain **unexecuted**; the passing checks above validate this agent, not the demo application's UAT.
