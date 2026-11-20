import errno
import io
import zipfile
from pathlib import Path

import pytest
from docagent.analysis import scan_repository
from docagent.github import safe_extract
from docagent.scan_scope import ScanPolicyError


def test_generated_assets_are_explained_and_handwritten_source_is_kept(tmp_path):
    assets = tmp_path / "static/react/assets"
    assets.mkdir(parents=True)
    (assets / "main-9eRkOz9F.js").write_text("export function bundled() {}")
    (assets / "app.js").write_text("export function handwritten() {}")
    result = scan_repository(tmp_path, "a" * 40)
    assert {item["path"] for item in result["inventory"]} == {"static/react/assets/app.js"}
    assert result["scope"]["auto_exclusions"] == [{
        "path": "static/react/assets/main-9eRkOz9F.js",
        "reason": "Fingerprinted browser build output",
    }]
    assert result["scope"]["suggested_ignore_patterns"] == ["static/react/assets/**"]
    (tmp_path / ".docagentignore").write_text("!static/react/assets/main-9eRkOz9F.js\n")
    included = scan_repository(tmp_path, "a" * 40)
    assert any(item["path"].endswith("main-9eRkOz9F.js") for item in included["inventory"])


def test_read_failure_is_a_coverage_gap_and_scan_continues(tmp_path, monkeypatch):
    (tmp_path / "blocked.py").write_text("def blocked(): pass")
    (tmp_path / "good.py").write_text("def available(): return 2")
    read = Path.read_bytes

    def blocked(path):
        if path.name == "blocked.py":
            raise OSError(errno.EINVAL, "credential-and-source-content")
        return read(path)

    monkeypatch.setattr(Path, "read_bytes", blocked)
    events = []
    result = scan_repository(tmp_path, "a" * 40, on_event=events.append)
    assert result["stats"]["scanned_files"] == 1
    assert result["scope"]["partial"] is True
    assert result["scope"]["skipped_files"][0]["path"] == "blocked.py"
    assert result["scope"]["skipped_files"][0]["code"] == errno.EINVAL
    assert "credential-and-source-content" not in str(result)
    assert any("blocked.py" in gap for gap in result["gaps"])
    assert events[0]["scanned_files"] == 0
    assert events[-1]["skipped_files"] == 1


def test_unreadable_ignore_policy_does_not_expand_the_scan(tmp_path, monkeypatch):
    (tmp_path / ".docagentignore").write_text("private/**")
    read = Path.read_text

    def blocked(path, *args, **kwargs):
        if path.name == ".docagentignore":
            raise PermissionError(errno.EACCES, "private-policy")
        return read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", blocked)
    with pytest.raises(ScanPolicyError):
        scan_repository(tmp_path, "a" * 40)


def test_archive_write_block_is_reported_and_partial_files_are_not_scanned(tmp_path, monkeypatch):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("repo/blocked.py", "def blocked(): pass")
        zip_file.writestr("repo/good.py", "def good(): pass")
    archive.seek(0)
    write = Path.write_bytes

    def blocked(path, data):
        if path.name == "blocked.py":
            write(path, b"partial")
            raise PermissionError(errno.EACCES, "private-source-detail")
        return write(path, data)

    monkeypatch.setattr(Path, "write_bytes", blocked)
    root = tmp_path / "source"
    skipped = safe_extract(archive, root, 10000, 100)
    assert skipped[0]["reason"] == "archive_write_blocked"
    result = scan_repository(root, "a" * 40, skipped_paths=skipped)
    assert {item["path"] for item in result["inventory"]} == {"good.py"}
    assert result["scope"]["partial"]
