# Security boundaries

## Trust model

Repository content, dependency manifests, test files, source comments and LLM responses are untrusted. Static analysis parses text and syntax; it never imports the repository, runs git hooks, installs dependencies or invokes repository commands. OAuth/PAT and LLM API credentials originate from explicit configuration or the authenticated browser session.

GitHub API paths are constructed from constrained owner/repository identifiers and escaped refs. Archives come from GitHub's fixed API/codeload hosts. Redirect authorization is not forwarded. Extraction rejects traversal, Windows ADS/device names, duplicates, symlinks, oversized archives and excessive expansion. Temporary source directories are created independently of the original repository.

## Sessions and access

Sessions use random opaque HTTP-only SameSite cookies; only a digest is stored in the database. Production cookies are Secure. CSRF tokens and an exact origin check protect mutations. Authentication rotates the session identifier and CSRF token. Jobs and artifacts are scoped to a stable GitHub user ID or an anonymous session. An authenticated owner can explicitly grant access to another GitHub account; usernames are resolved to stable IDs, and grants can be revoked. Viewer grants cannot record decisions even when that account is on the reviewer allowlist. Downloads validate the path against the job's artifact root.

Reviewer identity comes from GitHub, not a submitted name. A server allowlist controls formal reviews and evidence attestations. Decisions bind to baseline hashes. A UAT acceptance hash also includes the requirements decision and latest evidence record IDs. Editing a requirement or replacing evidence cannot silently preserve a stale approval.

## Private data and AI

GitHub tokens are encrypted with Fernet in sessions and temporary queued jobs. API keys remain server-side. The scanner excludes secret files and common generated/dependency directories, respects root `.gitignore` and `.docagentignore`, and redacts common token formats, credential assignments, private keys, JWTs and URL credentials. Redaction also applies before exporting and storing extracted payloads. Do not treat regex matching as complete secret detection.

For private repositories, the server verifies explicit consent for every selected provider before any external call. Fallback cannot introduce an unselected provider. Prompts contain bounded evidence records, a separate trusted instruction and no tool capabilities. Responses are schema-validated and references must belong to the exact supplied batch. These checks reduce prompt injection impact but do not prove semantic correctness; AI-generated requirements stay inferred.

## Evidence and audit

Generated tests are never passed by default. Manual/existing-report results require an authenticated authorized reviewer, a current baseline and attestation. The application stores the evidence reference and actual result, and versions the output. Existing reports are trusted through reviewer attestation, not automatic upload or unverified repository artifacts.

Audit records and artifact versions are append-only through the application API. Database administrators can modify them; this is not a tamper-proof external audit service or regulated electronic signature implementation. Retention intentionally deletes aged analyses, associated audit records and artifacts. Set retention to meet the organization's approved policy.

## Deployment responsibilities

TLS termination, secret-store integration, encrypted disks/backups, request-rate limiting, storage quotas, malware/secret scanning policy, worker isolation, durable recovery and access review are deployment responsibilities. The repository includes controls and tests, but does not replace penetration testing or organization-specific security acceptance.
