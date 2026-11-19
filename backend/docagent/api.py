import base64
import copy
import hashlib
import json
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated, Literal
from urllib.parse import urlencode

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, SecretStr
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware

from docagent.config import settings
from docagent.db import (
    Audit,
    DocumentVersion,
    Job,
    JobAccess,
    JobAdmission,
    Review,
    TestResult,
    UserSession,
    init_db,
    now,
    session_factory,
)
from docagent.github import GitHub, GitHubError
from docagent.jobs import (
    cleanup,
    enqueue,
    export_job,
    next_version,
    start_local_queue,
    stop_local_queue,
)
from docagent.logging_config import configure_logging
from docagent.schemas import (
    AnalysisConfig,
    CollaboratorInput,
    RequirementEdit,
    ResultInput,
    ReviewInput,
    StrictModel,
)
from docagent.security import decrypt, encrypt, new_token, redact, token_hash
from docagent.storage import (
    ArtifactNotFound,
    InvalidArtifactPath,
    StorageError,
    artifact_storage,
    validate_path,
)
from docagent.workflow import baseline, workflow


@asynccontextmanager
async def lifespan(app):
    configure_logging(settings().log_level)
    if settings().env == "production":
        # Migrations run once as a deployment step, never concurrently across API replicas.
        with session_factory()() as db:
            db.execute(select(Job.id).limit(0))
    else:
        init_db()
    if settings().job_backend == "local":
        with session_factory()() as db:
            for job in db.scalars(select(Job).where(Job.status.in_(["running", "queued"]))):
                job.status = "failed"
                job.message = "Local worker was restarted. Start a new analysis to retry."
                job.credential = ""
            db.commit()
    cleanup()
    local = settings().job_backend == "local"
    if local:
        start_local_queue()
    try:
        yield
    finally:
        if local:
            stop_local_queue()


def get_db():
    with session_factory()() as db:
        yield db


DB = Annotated[Session, Depends(get_db)]


def user_session(request: Request, db: DB):
    cookie = request.cookies.get("docagent_session", "")
    session = db.get(UserSession, token_hash(cookie)) if cookie else None
    if session is None or session.expires < now():
        raise HTTPException(401, "Session expired. Refresh the page.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(csrf, session.csrf):
            raise HTTPException(403, "Invalid CSRF token")
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != settings().public_url.rstrip("/"):
            raise HTTPException(403, "Unexpected request origin")
    return session


User = Annotated[UserSession, Depends(user_session)]


def owner_job(db, user, job_id, lock=False):
    shared = select(JobAccess.job_id).where(JobAccess.principal == user.owner)
    stmt = select(Job).where(Job.id == job_id, or_(Job.owner == user.owner, Job.id.in_(shared)))
    if lock:
        stmt = stmt.with_for_update()
    job = db.scalar(stmt)
    if job is None:
        raise HTTPException(404, "Analysis not found")
    return job


def require_complete(job):
    if job.status != "completed":
        raise HTTPException(409, "Analysis is not complete")


def can_review(user, db, job):
    names = {name.strip().casefold() for name in settings().reviewers.split(",") if name.strip()}
    if not user.login or user.login.casefold() not in names:
        return False
    grant = db.get(JobAccess, (job.id, user.owner))
    return job.owner == user.owner or grant is not None and grant.role == "reviewer"


def require_reviewer(user, db, job):
    if not can_review(user, db, job):
        raise HTTPException(403, "An authenticated GitHub account listed in DOCAGENT_REVIEWERS is required")


def set_cookie(response, token):
    response.set_cookie(
        "docagent_session",
        token,
        httponly=True,
        secure=settings().env == "production",
        samesite="lax",
        max_age=settings().session_hours * 3600,
        path="/",
    )


def create_session(db, response):
    token = new_token()
    session = UserSession(
        id=token_hash(token),
        owner=f"anonymous:{uuid.uuid4()}",
        csrf=new_token(),
        expires=now() + timedelta(hours=settings().session_hours),
    )
    db.add(session)
    db.commit()
    set_cookie(response, token)
    return session


def connect_user(db, session, token, identity, response):
    owner = f"github:{identity['id']}"
    if session.owner.startswith("anonymous:"):
        for job in db.scalars(select(Job).where(Job.owner == session.owner)):
            job.owner = owner
    new_cookie = new_token()
    replacement = UserSession(
        id=token_hash(new_cookie),
        owner=owner,
        login=identity["login"],
        token=encrypt(token),
        csrf=new_token(),
        expires=now() + timedelta(hours=settings().session_hours),
    )
    db.delete(session)
    db.add(replacement)
    db.commit()
    set_cookie(response, new_cookie)


def job_view(db, job, full=False, user=None):
    value = {
        "id": job.id,
        "repository": job.repository,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "version": job.version,
        "baseline_hash": job.baseline_hash,
        "created": job.created.isoformat(),
        "updated": job.updated.isoformat(),
    }
    if full:
        value.update(config=job.config, analysis=job.analysis, workflow=workflow(db, job))
        value["versions"] = list(
            db.scalars(
                select(DocumentVersion.version)
                .where(DocumentVersion.job_id == job.id)
                .order_by(DocumentVersion.version)
            )
        )
        if user:
            value.update(is_owner=job.owner == user.owner, can_review=can_review(user, db, job))
    return value


class PATInput(StrictModel):
    token: SecretStr = Field(min_length=10, max_length=300)


def create_app():
    cfg = settings()
    app = FastAPI(title="Repository Documentation Agent", version="0.1.0", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h.strip() for h in cfg.allowed_hosts.split(",")])

    @app.middleware("http")
    async def security_headers(request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "JSON request body required"}, status_code=415)
            # Stop streaming oversized bodies rather than relying on client Content-Length.
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 128_000:
                    return JSONResponse({"detail": "Request body too large"}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        if request.url.path in {"/docs", "/redoc"}:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; object-src 'none'; frame-ancestors 'none'"
            )
        if cfg.env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # FastAPI's default error body echoes rejected input (which may be a token).
        return JSONResponse(
            {
                "detail": [
                    {"field": ".".join(map(str, err["loc"])), "message": "Invalid value"}
                    for err in exc.errors()
                ]
            },
            status_code=422,
        )

    @app.exception_handler(GitHubError)
    async def github_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.exception_handler(StorageError)
    async def storage_error(request, exc):
        if isinstance(exc, ArtifactNotFound):
            return JSONResponse({"detail": "Artifact not found"}, status_code=404)
        return JSONResponse({"detail": "Artifact storage is unavailable. Try again later."}, status_code=503)

    @app.exception_handler(InvalidArtifactPath)
    async def invalid_artifact_path(request, exc):
        return JSONResponse({"detail": "Invalid artifact path"}, status_code=400)

    @app.get("/api/health")
    def health(db: DB):
        db.execute(select(1))
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/session")
    def session_info(request: Request, response: Response, db: DB):
        cookie = request.cookies.get("docagent_session", "")
        user = db.get(UserSession, token_hash(cookie)) if cookie else None
        if user is None or user.expires < now():
            user = create_session(db, response)
        reviewers = {s.strip().casefold() for s in cfg.reviewers.split(",")}
        return {
            "login": user.login or None,
            "csrf_token": user.csrf,
            "can_review": bool(user.login) and user.login.casefold() in reviewers,
            "oauth_enabled": bool(cfg.github_client_id),
            "test_execution_enabled": cfg.test_execution_enabled,
            "providers": [
                {
                    "id": name,
                    "configured": bool(getattr(cfg, f"{name}_api_key").get_secret_value()),
                    "model": getattr(cfg, f"{name}_model"),
                }
                for name in ("openai", "anthropic", "gemini")
            ],
        }

    @app.post("/api/auth/pat")
    def authenticate(data: PATInput, user: User, db: DB, response: Response):
        token = data.token.get_secret_value()
        with GitHub(token) as github:
            identity = github.user()
        connect_user(db, user, token, identity, response)
        return {"login": identity["login"]}

    @app.post("/api/auth/logout")
    def logout(user: User, db: DB, response: Response):
        db.delete(user)
        db.commit()
        response.delete_cookie("docagent_session")
        return {"status": "disconnected"}

    @app.get("/api/auth/github/start")
    def oauth_start(user: User, db: DB):
        if not cfg.github_client_id:
            raise HTTPException(409, "GitHub OAuth is not configured")
        user.oauth_state = new_token()
        user.oauth_verifier = new_token()
        user.oauth_started = now()
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(user.oauth_verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        db.commit()
        params = {
            "client_id": cfg.github_client_id,
            "redirect_uri": cfg.public_url + "/api/auth/github/callback",
            "scope": cfg.github_oauth_scopes,
            "state": user.oauth_state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return RedirectResponse("https://github.com/login/oauth/authorize?" + urlencode(params))

    @app.get("/api/auth/github/callback")
    def oauth_callback(code: str, state: str, user: User, db: DB):
        if (
            not user.oauth_state
            or not secrets.compare_digest(state, user.oauth_state)
            or not user.oauth_started
            or now() - user.oauth_started > timedelta(minutes=10)
        ):
            raise HTTPException(403, "OAuth state is invalid or expired")
        verifier = user.oauth_verifier
        user.oauth_state = user.oauth_verifier = ""
        user.oauth_started = None
        db.commit()
        try:
            result = httpx.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": cfg.github_client_id,
                    "client_secret": cfg.github_client_secret.get_secret_value(),
                    "code": code,
                    "redirect_uri": cfg.public_url + "/api/auth/github/callback",
                    "code_verifier": verifier,
                },
                timeout=30,
            )
            token = result.json().get("access_token")
            if not token:
                raise ValueError("Missing token")
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, "GitHub OAuth exchange failed") from None
        with GitHub(token) as github:
            identity = github.user()
        response = RedirectResponse("/")
        connect_user(db, user, token, identity, response)
        return response

    @app.get("/api/repositories")
    def repositories(user: User, page: int = Query(1, ge=1, le=1000)):
        if not user.token:
            raise HTTPException(401, "Connect GitHub to discover accessible repositories")
        with GitHub(decrypt(user.token)) as github:
            return github.repositories(page)

    @app.get("/api/repositories/{owner}/{name}")
    def repository(owner: str, name: str, user: User):
        config = AnalysisConfig(repository=f"{owner}/{name}")
        with GitHub(decrypt(user.token)) as github:
            return github.repository(config.repository)

    @app.get("/api/repositories/{owner}/{name}/refs")
    def refs(
        owner: str,
        name: str,
        user: User,
        kind: Literal["branches", "tags"] = "branches",
        page: int = Query(1, ge=1, le=1000),
    ):
        config = AnalysisConfig(repository=f"{owner}/{name}")
        with GitHub(decrypt(user.token)) as github:
            return github.refs(config.repository, kind, page)

    def start_job(config, user, db, demo=False):
        if config.repository == "demo/inventory" and not demo:
            raise HTTPException(422, "Use the demo endpoint for the bundled fixture")
        if config.execute_tests and not cfg.test_execution_enabled:
            raise HTTPException(409, "Test execution is disabled by the administrator")
        if not demo:
            with GitHub(decrypt(user.token)) as github:
                metadata = github.repository(config.repository)
            if metadata["private"] and any(
                p.provider not in config.consent_providers for p in config.providers
            ):
                raise HTTPException(
                    422, "Consent is required for each provider and fallback receiving private code"
                )
        # A write acquires a row lock in PostgreSQL and a writer lock in SQLite.
        # Hold it through count + insert + commit; perform external I/O beforehand.
        admission = db.execute(update(JobAdmission).where(JobAdmission.id == 1).values(id=1))
        if admission.rowcount != 1:
            raise HTTPException(503, "Queue admission is unavailable. Check database migrations.")
        active = db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(["running", "queued"])))
        owned = db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.owner == user.owner, Job.status.in_(["running", "queued"]))
        )
        if active >= 16 or owned >= cfg.max_concurrent_jobs:
            raise HTTPException(429, "Analysis queue is full. Wait for an active job to finish.")
        job = Job(
            id=str(uuid.uuid4()),
            owner=user.owner,
            repository=config.repository,
            config=config.model_dump(mode="json"),
            credential=user.token,
        )
        db.add(job)
        db.flush()
        db.add(
            Audit(
                job_id=job.id,
                actor=user.login or "anonymous",
                action="generation_requested",
                detail={
                    "providers": [p.provider for p in config.providers],
                    "consent_providers": config.consent_providers,
                    "execute_tests": config.execute_tests,
                },
            )
        )
        db.commit()
        try:
            enqueue(job.id)
        except Exception:
            job.status = "failed"
            job.message = "Background queue unavailable. Retry after the worker is restored."
            job.credential = ""
            db.commit()
        return job_view(db, job)

    @app.post("/api/jobs", status_code=202)
    def create_job(config: AnalysisConfig, user: User, db: DB):
        return start_job(config, user, db)

    @app.post("/api/demo", status_code=202)
    def demo(user: User, db: DB):
        return start_job(
            AnalysisConfig(repository="demo/inventory", formats=["md", "docx", "pdf"]), user, db, demo=True
        )

    @app.get("/api/jobs")
    def list_jobs(user: User, db: DB):
        shared = select(JobAccess.job_id).where(JobAccess.principal == user.owner)
        return [
            job_view(db, job)
            for job in db.scalars(
                select(Job)
                .where(or_(Job.owner == user.owner, Job.id.in_(shared)))
                .order_by(Job.created.desc())
                .limit(100)
            )
        ]

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, user: User, db: DB):
        return job_view(db, owner_job(db, user, job_id), full=True, user=user)

    @app.get("/api/jobs/{job_id}/collaborators")
    def collaborators(job_id: str, user: User, db: DB):
        job = owner_job(db, user, job_id)
        if job.owner != user.owner:
            raise HTTPException(403, "Only the analysis owner can manage access")
        return [
            {"login": row.login, "role": row.role}
            for row in db.scalars(select(JobAccess).where(JobAccess.job_id == job_id))
        ]

    @app.post("/api/jobs/{job_id}/collaborators")
    def grant_access(job_id: str, data: CollaboratorInput, user: User, db: DB):
        job = owner_job(db, user, job_id, lock=True)
        if job.owner != user.owner or not user.login:
            raise HTTPException(403, "The authenticated analysis owner must grant access")
        if not data.acknowledged:
            raise HTTPException(
                422, "Acknowledge sharing all artifacts and source evidence with this account"
            )
        with GitHub(decrypt(user.token)) as github:
            identity = github.request(f"/users/{data.login}").json()
        principal = f"github:{identity['id']}"
        grant = db.get(JobAccess, (job.id, principal))
        if grant is None:
            grant = JobAccess(job_id=job.id, principal=principal, login=identity["login"], role=data.role)
            db.add(grant)
        else:
            grant.role = data.role
        db.add(
            Audit(
                job_id=job.id,
                actor=user.login,
                action="access_granted",
                detail={"login": identity["login"], "role": data.role},
            )
        )
        db.commit()
        return {"login": identity["login"], "role": data.role}

    @app.delete("/api/jobs/{job_id}/collaborators/{login}")
    def revoke_access(job_id: str, login: str, user: User, db: DB):
        job = owner_job(db, user, job_id, lock=True)
        if job.owner != user.owner:
            raise HTTPException(403, "Only the analysis owner can revoke access")
        row = db.scalar(
            select(JobAccess).where(
                JobAccess.job_id == job_id, func.lower(JobAccess.login) == login.casefold()
            )
        )
        if row:
            db.delete(row)
            db.add(
                Audit(job_id=job.id, actor=user.login, action="access_revoked", detail={"login": row.login})
            )
            db.commit()
        return {"status": "revoked"}

    @app.get("/api/jobs/{job_id}/files")
    def files(job_id: str, user: User, db: DB, version: int | None = Query(None, ge=1)):
        job = owner_job(db, user, job_id)
        require_complete(job)
        version = version or job.version
        if db.get(DocumentVersion, (job.id, version)) is None:
            raise HTTPException(404, "Committed document version not found")
        if version > job.version:
            raise HTTPException(404, "Document version not found")
        return json.loads(artifact_storage().read_text(job.id, version, "manifest.json"))

    @app.get("/api/jobs/{job_id}/download")
    def download(job_id: str, user: User, db: DB, path: str = "", version: int | None = Query(None, ge=1)):
        job = owner_job(db, user, job_id)
        require_complete(job)
        version = version or job.version
        if db.get(DocumentVersion, (job.id, version)) is None:
            raise HTTPException(404, "Committed document version not found")
        if version > job.version:
            raise HTTPException(404, "Document version not found")
        download = artifact_storage().download(job.id, version, path)
        return FileResponse(
            download.path, filename=download.filename,
            media_type="application/zip" if not path else None,
            background=BackgroundTask(download.cleanup) if download.cleanup else None,
        )

    @app.get("/api/jobs/{job_id}/preview")
    def preview(job_id: str, path: str, user: User, db: DB):
        job = owner_job(db, user, job_id)
        require_complete(job)
        if db.get(DocumentVersion, (job.id, job.version)) is None:
            raise HTTPException(404, "Committed document version not found")
        try:
            validate_path(path)
        except InvalidArtifactPath:
            raise HTTPException(404, "Markdown preview not found") from None
        if not path.endswith(".md"):
            raise HTTPException(404, "Markdown preview not found")
        return {"content": artifact_storage().read_text(job.id, job.version, path)}

    @app.get("/api/jobs/{job_id}/audit")
    def audit(job_id: str, user: User, db: DB):
        owner_job(db, user, job_id)
        return [
            {
                "id": a.id,
                "actor": a.actor,
                "action": a.action,
                "detail": a.detail,
                "created": a.created.isoformat(),
            }
            for a in db.scalars(select(Audit).where(Audit.job_id == job_id).order_by(Audit.id))
        ]

    @app.post("/api/jobs/{job_id}/reviews")
    def review(job_id: str, data: ReviewInput, user: User, db: DB):
        job = owner_job(db, user, job_id, lock=True)
        require_complete(job)
        require_reviewer(user, db, job)
        state = workflow(db, job)
        expected_hash = job.baseline_hash if data.stage == "requirements" else state["acceptance_hash"]
        if data.baseline_hash != expected_hash:
            raise HTTPException(409, "Baseline changed. Refresh and review the current version.")
        if data.decision == "approved" and not data.acknowledged:
            raise HTTPException(422, "Explicit reviewer acknowledgement is required")
        if data.stage == "requirements" and data.decision == "approved" and not job.analysis["requirements"]:
            raise HTTPException(409, "An empty requirements baseline cannot be approved")
        if data.stage == "uat" and data.decision == "approved" and not state["ready_for_acceptance"]:
            raise HTTPException(
                409, "Current requirements approval and passing evidence for all cases are required"
            )
        db.add(
            Review(
                job_id=job.id,
                baseline_hash=expected_hash,
                stage=data.stage,
                decision=data.decision,
                reviewer=user.login,
                comment=redact(data.comment),
            )
        )
        db.add(
            Audit(
                job_id=job.id,
                actor=user.login,
                action="review_recorded",
                detail={"stage": data.stage, "decision": data.decision, "baseline_hash": expected_hash},
            )
        )
        job.version = next_version(job)
        db.flush()
        export_job(db, job)
        db.commit()
        return job_view(db, job, full=True, user=user)

    @app.post("/api/jobs/{job_id}/results")
    def record_result(job_id: str, data: ResultInput, user: User, db: DB):
        job = owner_job(db, user, job_id, lock=True)
        require_complete(job)
        require_reviewer(user, db, job)
        if not data.attested:
            raise HTTPException(422, "A reviewer must attest that the result evidence was verified")
        if data.baseline_hash != job.baseline_hash:
            raise HTTPException(
                409, "Baseline changed. Revalidate this test result against the current requirements."
            )
        if not any(t["id"] == data.test_case_id for t in job.analysis["test_cases"]):
            raise HTTPException(422, "Unknown test case")
        payload = data.model_dump(exclude={"attested", "baseline_hash"}, mode="json")
        payload["actual"] = redact(payload["actual"])
        payload["evidence_reference"] = redact(payload["evidence_reference"])
        if data.status == "passed" and data.severity != "none":
            raise HTTPException(422, "A passing case cannot have an unresolved defect severity")
        db.add(TestResult(job_id=job.id, baseline_hash=job.baseline_hash, reviewer=user.login, **payload))
        db.add(
            Audit(
                job_id=job.id,
                actor=user.login,
                action="test_result_recorded",
                detail={"test_case_id": data.test_case_id, "status": data.status, "source": data.source},
            )
        )
        job.version = next_version(job)
        db.flush()
        export_job(db, job)
        db.commit()
        return job_view(db, job, full=True, user=user)

    @app.patch("/api/jobs/{job_id}/requirements/{requirement_id}")
    def edit_requirement(job_id: str, requirement_id: str, data: RequirementEdit, user: User, db: DB):
        job = owner_job(db, user, job_id, lock=True)
        require_complete(job)
        require_reviewer(user, db, job)
        if data.baseline_hash != job.baseline_hash:
            raise HTTPException(409, "Baseline changed. Refresh before editing.")
        analysis = copy.deepcopy(job.analysis)
        requirement = next((r for r in analysis["requirements"] if r["id"] == requirement_id), None)
        if requirement is None:
            raise HTTPException(404, "Requirement not found")
        requirement.update(statement=redact(data.statement), source="reviewer", confidence="inferred")
        job.analysis = analysis
        job.baseline_hash = baseline(analysis)
        job.version = next_version(job)
        db.add(
            Audit(
                job_id=job.id,
                actor=user.login,
                action="requirement_edited",
                detail={
                    "requirement_id": requirement_id,
                    "rationale": redact(data.rationale),
                    "baseline_hash": job.baseline_hash,
                },
            )
        )
        db.flush()
        export_job(db, job)
        db.commit()
        return job_view(db, job, full=True, user=user)

    if cfg.frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=cfg.frontend_dir, html=True), name="frontend")
    else:

        @app.get("/")
        def missing_frontend():
            return {
                "message": "Build the React frontend: cd frontend && npm ci && npm run build",
                "api": "/docs",
            }

    return app


app = create_app()
