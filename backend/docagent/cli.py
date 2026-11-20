import argparse
import json
import uuid
from pathlib import Path

from docagent.config import LOG_LEVELS


def main():
    parser = argparse.ArgumentParser(description="Evidence-based repository documentation")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("key", help="Generate a Fernet encryption key")
    commands.add_parser("init-db", help="Create the initial database schema")
    commands.add_parser("cleanup", help="Purge expired sessions, cache and completed artifacts")
    compose = commands.add_parser("compose-env", help="Generate .env.compose for existing service containers")
    compose.add_argument("--output", type=Path, default=Path(".env.compose"))
    compose.add_argument("--database-host", default="pgvector")
    compose.add_argument("--redis-host", default="redis")
    compose.add_argument("--minio-host", default="minio")
    checks = commands.add_parser("check-services", help="Check configured PostgreSQL, real Redis and S3/MinIO")
    checks.add_argument("--write-probe", action="store_true", help="Write and delete uniquely named service probes")
    checks.add_argument("--api-url", help="Also create and validate a real demo through a running API")
    checks.add_argument("--timeout", type=int, default=120, help="Seconds to wait for demo generation")
    checks.add_argument("--output", type=Path, help="Save a JSON report and, with --api-url, its demo ZIP")
    serve = commands.add_parser("serve", help="Run the API; Celery mode also requires a separate worker")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--host", default="127.0.0.1")
    worker = commands.add_parser("worker", help="Run a Celery worker using the configured log level")
    worker.add_argument("--concurrency", type=int, default=2)
    worker.add_argument("--pool", choices=["prefork", "solo", "threads"], default=None)
    scheduler = commands.add_parser("scheduler", help="Run Celery Beat using the configured log level")
    scheduler.add_argument("--schedule", type=Path, default=None)
    for command in (serve, worker, scheduler):
        command.add_argument("--log-level", type=str.upper, choices=LOG_LEVELS,
                             help="Override DOCAGENT_LOG_LEVEL for this process")
    scan = commands.add_parser("scan", help="Analyze a local directory without executing it or using AI")
    scan.add_argument("path", type=Path)
    scan.add_argument("--output", type=Path, required=True)
    scan.add_argument("--depth", choices=["basic", "standard", "comprehensive"], default="standard")
    scan.add_argument("--formats", nargs="+", choices=["md", "docx", "pdf"], default=["md", "docx", "pdf"])
    args = parser.parse_args()
    if args.command == "compose-env":
        from docagent.compose_config import write_compose_env
        from docagent.config import settings

        try:
            result = write_compose_env(
                settings(), args.output, args.database_host, args.redis_host, args.minio_host,
            )
        except Exception as exc:
            # Settings and URL parser errors may contain credentials.
            print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
            raise SystemExit(1) from None
        print(json.dumps({"status": "passed", **result}))
        return
    if args.command == "check-services":
        from docagent.checks import run_checks

        if args.timeout < 1:
            parser.error("--timeout must be positive")
        if args.output and args.output.suffix.lower() != ".json":
            parser.error("--output must be a .json report path")
        result = run_checks(args.write_probe, args.api_url, args.timeout, args.output)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["status"] == "passed" else 1)
    if args.command == "key":
        from cryptography.fernet import Fernet

        print(Fernet.generate_key().decode())
    elif args.command == "init-db":
        from docagent.db import init_db

        init_db()
        print("Database initialized")
    elif args.command in {"serve", "worker", "scheduler"}:
        from docagent.config import settings
        from docagent.logging_config import configure_logging

        config = settings()
        if args.log_level:
            config.log_level = args.log_level
        configure_logging(config.log_level)
        if args.command == "serve":
            import uvicorn

            uvicorn.run("docagent.api:app", host=args.host, port=args.port,
                        log_level=config.log_level.lower(), access_log=False)
        else:
            if args.command == "worker" and args.concurrency < 1:
                parser.error("--concurrency must be positive")
            from docagent.worker import celery

            options = ["--loglevel=" + config.log_level]
            if args.command == "worker":
                options.append("--concurrency=" + str(args.concurrency))
                if args.pool:
                    options.append("--pool=" + args.pool)
                celery.worker_main(["worker", *options])
            else:
                if args.schedule:
                    args.schedule.parent.mkdir(parents=True, exist_ok=True)
                    options.append("--schedule=" + str(args.schedule))
                celery.start(["beat", *options])
    elif args.command == "cleanup":
        from docagent.db import init_db
        from docagent.jobs import cleanup

        init_db()
        print(f"Removed {cleanup()} expired analyses")
    elif args.command == "scan":
        from docagent.analysis import scan_repository
        from docagent.db import Job, digest, init_db, session_factory
        from docagent.documents import export_package, package_path
        from docagent.reporting import refine_analysis
        from docagent.schemas import AnalysisConfig
        from docagent.workflow import baseline, workflow

        if not args.path.is_dir():
            parser.error("The source path must be a directory")
        if args.output.resolve().is_relative_to(args.path.resolve()):
            parser.error("Place output outside the analyzed source directory")
        if args.output.exists() or package_path(args.output).exists():
            parser.error("Output directory or ZIP already exists; choose a new output directory")
        analysis = scan_repository(args.path, "local-uncommitted", args.depth)
        fingerprint = digest(analysis["inventory"])[:40]
        analysis["commit"] = fingerprint
        for e in analysis["evidence"]:
            e["commit"] = fingerprint
        analysis.update(repository="local/" + args.path.resolve().name, private=True)
        analysis = refine_analysis(analysis)
        analysis["gaps"].append(
            "Local snapshot fingerprint is not a verified Git commit; source links must be resolved locally."
        )
        config = AnalysisConfig(repository="local/snapshot", depth=args.depth, formats=args.formats)
        init_db()
        with session_factory()() as db:
            job = Job(
                id=str(uuid.uuid4()),
                owner="local",
                repository=analysis["repository"],
                config=config.model_dump(),
                analysis=analysis,
                baseline_hash=baseline(analysis),
            )
            state = {**workflow(db, job), "baseline_hash": job.baseline_hash}
            manifest = export_package(args.output.resolve(), analysis, config, state, 1)
        print(
            json.dumps(
                {
                    "output": str(args.output.resolve()),
                    "package": str(package_path(args.output.resolve())),
                    "files": len(manifest),
                    "requirements": len(analysis["requirements"]),
                }
            )
        )


if __name__ == "__main__":
    main()
