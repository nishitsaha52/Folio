"""Opt-in execution inside an administrator-managed disposable Docker container."""

import hashlib
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from defusedxml.ElementTree import parse

from docagent.config import settings
from docagent.security import redact, secret_path


def junit_summary(path: Path):
    if path.is_symlink() or path.stat().st_size > 5_000_000:
        raise ValueError("Invalid test report")
    root = parse(path).getroot()
    cases = list(root.iter("testcase"))
    counts = {"passed": 0, "failed": 0, "blocked": 0, "total": len(cases)}
    for case in cases:
        if case.find("failure") is not None or case.find("error") is not None:
            counts["failed"] += 1
        elif case.find("skipped") is not None:
            counts["blocked"] += 1
        else:
            counts["passed"] += 1
    return counts


def execute_tests(root: Path, commit: str, profile: str):
    cfg = settings()
    if not cfg.test_execution_enabled:
        raise ValueError("Test execution is disabled by the administrator")
    if not re.fullmatch(r"[\w./:-]+@sha256:[a-f0-9]{64}", cfg.test_image):
        raise ValueError("A trusted digest-pinned test image is required")
    if not shutil.which("docker"):
        raise ValueError("Docker is not available on this worker")
    container = f"docagent-test-{uuid.uuid4().hex}"
    with tempfile.TemporaryDirectory(prefix="docagent-tests-", dir=cfg.data_dir) as workspace:
        workspace = Path(workspace).resolve()
        source, output = workspace / "source", workspace / "results"
        output.mkdir()

        def exclude(directory, names):
            return [
                name
                for name in names
                if secret_path((Path(directory) / name).relative_to(root).as_posix())
                or (Path(directory) / name).is_symlink()
                or name in {".git", "node_modules", ".venv"}
            ]

        shutil.copytree(root, source, ignore=exclude)
        command = (
            ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--junitxml=/results/junit.xml"]
            if profile == "pytest"
            else ["npm", "test", "--", "--runInBand"]
        )
        # The fixed wrapper copies the read-only source into ephemeral storage. No package install or network.
        wrapper = (
            "import shutil,subprocess,sys,time,pathlib;shutil.copytree('/source','/work/repo');"
            "result=subprocess.call(sys.argv[1:],cwd='/work/repo',stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
            "pathlib.Path('/results/exit_code').write_text(str(result));time.sleep(300)"
        )
        args = [
            "docker",
            "run",
            "--detach",
            "--log-driver=none",
            "--name",
            container,
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=128",
            "--memory=1g",
            "--cpus=1",
            "--user=65534:65534",
            "--tmpfs=/tmp:rw,nosuid,size=128m",
            "--tmpfs=/work:rw,nosuid,size=512m",
            "--tmpfs=/results:rw,nosuid,size=32m,mode=1777",
            "--mount",
            f"type=bind,source={source},target=/source,readonly",
            "--env=HOME=/tmp",
            "--entrypoint=python",
            cfg.test_image,
            "-c",
            wrapper,
            *command,
        ]
        output.chmod(0o777)
        try:
            # Discard arbitrary test logs; they may contain secrets and can be unbounded.
            started = subprocess.run(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False
            )
            if started.returncode:
                raise ValueError("Container could not be started")
            deadline = time.monotonic() + cfg.test_timeout
            while time.monotonic() < deadline:
                check = subprocess.run(
                    [
                        "docker",
                        "exec",
                        container,
                        "python",
                        "-c",
                        "import pathlib,sys;p=pathlib.Path('/results/exit_code');sys.exit(0 if p.is_file() else 3)",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                )
                if check.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise subprocess.TimeoutExpired(args, cfg.test_timeout)
            exit_response = subprocess.run(
                ["docker", "exec", container, "python", "-c", "print(open('/results/exit_code').read(8))"],
                capture_output=True,
                timeout=10,
                check=False,
            )
            exit_code = int(exit_response.stdout.decode().strip())
            # Copy the bounded report while the container's tmpfs is still mounted.
            # No writable host mount or repository-controlled logs are exposed.
            report = output / "junit.xml"
            if profile == "pytest":
                subprocess.run(
                    ["docker", "cp", f"{container}:/results/junit.xml", str(report)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=20,
                    check=False,
                )
            counts = junit_summary(report) if profile == "pytest" and report.is_file() else None
            return {
                "source": "executed_test_results",
                "commit": commit,
                "profile": profile,
                "exit_code": exit_code,
                "counts": counts,
                "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest() if counts else None,
                "note": "Counts describe repository tests reported by the runner. No generated UAT case is automatically marked passed. Repository-controlled test assertions still need review.",
            }
        except subprocess.TimeoutExpired:
            return {
                "source": "executed_test_results",
                "commit": commit,
                "profile": profile,
                "counts": None,
                "note": "Execution timed out. Results are blocked and no pass is inferred.",
            }
        except (ValueError, OSError):
            return {
                "source": "executed_test_results",
                "commit": commit,
                "counts": None,
                "note": redact("Execution evidence could not be validated. No pass is inferred."),
            }
        finally:
            subprocess.run(
                ["docker", "rm", "-f", container],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
