import io
import stat
import zipfile

import pytest
from docagent.analysis import analyze_file, scan_repository
from docagent.github import safe_extract
from docagent.security import redact, secret_path


def archive(name, data=b"hello", mode=0):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        item = zipfile.ZipInfo(name)
        # ZipInfo normalizes backslashes on Windows; preserve the malicious test input.
        item.filename = name
        item.external_attr = mode << 16
        z.writestr(item, data)
    stream.seek(0)
    return stream


@pytest.mark.parametrize(
    "name",
    [
        "repo/../../escape",
        "repo/C:/escape",
        "repo/x:stream",
        "repo/CON.txt",
        "repo/test. ",
        "/repo/escape",
        "repo\\escape",
    ],
)
def test_archive_rejects_unsafe_paths(tmp_path, name):
    with pytest.raises(ValueError):
        safe_extract(archive(name), tmp_path / "out", 10000, 100)


def test_archive_rejects_links_and_expansion(tmp_path):
    with pytest.raises(ValueError):
        safe_extract(archive("repo/link", mode=stat.S_IFLNK), tmp_path / "out", 10000, 100)
    with pytest.raises(ValueError):
        safe_extract(archive("repo/file", b"a" * 20), tmp_path / "out", 10, 100)


def test_archive_valid(tmp_path):
    safe_extract(archive("repo/module/main.py"), tmp_path / "out", 10000, 100)
    assert (tmp_path / "out/module/main.py").read_bytes() == b"hello"


def test_redaction():
    secret = "ghp_" + "a" * 36
    text = f'password = "hunter-secret"\napi_key: "{secret}"\nhttps://alice:password@example.com'
    result = redact(text)
    assert "hunter-secret" not in result and secret not in result and "alice:password" not in result
    assert secret_path("config/.env.production")


def test_python_evidence_and_no_execution(tmp_path):
    marker = tmp_path / "executed.txt"
    source = f"""from fastapi import FastAPI\nfrom pathlib import Path\nPath({str(marker)!r}).write_text("bad")\napp = FastAPI()\n@app.get("/stock")\ndef stock():\n    return {{"count": 1}}\n"""
    (tmp_path / "app.py").write_text(source)
    (tmp_path / ".env").write_text("PASSWORD=hidden")
    result = scan_repository(tmp_path, "a" * 40)
    assert not marker.exists()
    route = next(f for f in result["findings"] if f["kind"] == "api")
    assert route["metadata"]["route"] == "/stock"
    assert next(e for e in result["evidence"] if e["id"] == route["evidence_ids"][0])["start_line"] == 5
    assert all(f["path"] != ".env" for f in result["inventory"])
    assert all(t["status"] == "unexecuted" for t in result["test_cases"])


def test_tree_sitter_typescript():
    result = analyze_file("src/hello.ts", "export function greet(name: string): string { return name; }")
    assert any(f["title"] == "greet" for f in result["findings"])


def test_extensionless_readme_is_analyzed(tmp_path):
    (tmp_path / "README").write_text("This service manages inventory.")
    result = scan_repository(tmp_path, "a" * 40)
    assert result["stats"]["scanned_files"] == 1
    finding = next(f for f in result["findings"] if f["kind"] == "repository_description")
    assert finding["confidence"] == "inferred"


def test_incremental_and_stable_ids(isolated):
    from docagent.db import init_db, session_factory

    root = isolated / "repo"
    root.mkdir()
    (root / "app.py").write_text("def total(value):\n    return value * 2\n")
    init_db()
    with session_factory()() as db:
        first = scan_repository(root, "a" * 40, db=db, cache_scope="owner/repo")
        db.commit()
        second = scan_repository(root, "b" * 40, db=db, cache_scope="owner/repo")
        assert second["stats"]["reused_files"] == 1
        assert second["evidence"][0]["commit"] == "b" * 40
        assert first["requirements"][0]["id"] == second["requirements"][0]["id"]
        third = scan_repository(root, "b" * 40, db=db, cache_scope="another/repo")
        assert third["stats"]["reused_files"] == 0
