# Validation record

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
