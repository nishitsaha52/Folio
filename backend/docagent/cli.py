import argparse
import json
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Evidence-based repository documentation")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("key", help="Generate a Fernet encryption key")
    commands.add_parser("init-db", help="Create the initial database schema")
    commands.add_parser("cleanup", help="Purge expired sessions, cache and completed artifacts")
    serve = commands.add_parser("serve", help="Run the local server")
    serve.add_argument("--port", type=int, default=8000)
    scan = commands.add_parser("scan", help="Analyze a local directory without executing it or using AI")
    scan.add_argument("path", type=Path)
    scan.add_argument("--output", type=Path, required=True)
    scan.add_argument("--depth", choices=["basic", "standard", "comprehensive"], default="standard")
    scan.add_argument("--formats", nargs="+", choices=["md", "docx", "pdf"], default=["md", "docx", "pdf"])
    args = parser.parse_args()
    if args.command == "key":
        from cryptography.fernet import Fernet

        print(Fernet.generate_key().decode())
    elif args.command == "init-db":
        from docagent.db import init_db

        init_db()
        print("Database initialized")
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("docagent.api:app", host="127.0.0.1", port=args.port, access_log=False)
    elif args.command == "cleanup":
        from docagent.db import init_db
        from docagent.jobs import cleanup

        init_db()
        print(f"Removed {cleanup()} expired analyses")
    elif args.command == "scan":
        from docagent.analysis import scan_repository
        from docagent.db import Job, digest, init_db, session_factory
        from docagent.documents import export_package
        from docagent.schemas import AnalysisConfig
        from docagent.workflow import baseline, workflow

        if not args.path.is_dir():
            parser.error("The source path must be a directory")
        if args.output.resolve().is_relative_to(args.path.resolve()):
            parser.error("Place output outside the analyzed source directory")
        analysis = scan_repository(args.path, "local-uncommitted", args.depth)
        fingerprint = digest(analysis["inventory"])[:40]
        analysis["commit"] = fingerprint
        for e in analysis["evidence"]:
            e["commit"] = fingerprint
        analysis.update(repository="local/" + args.path.resolve().name, private=True)
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
                    "files": len(manifest),
                    "requirements": len(analysis["requirements"]),
                }
            )
        )


if __name__ == "__main__":
    main()
