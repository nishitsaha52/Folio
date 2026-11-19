import json
import sys
import zipfile

import pytest
from docagent.cli import main


def test_sibling_cli_scans_have_independent_packages(isolated, monkeypatch, capsys):
    source = isolated / "source"
    source.mkdir()
    (source / "app.py").write_text("def first():\n    return 1\n")
    first = isolated / "first.docs"
    monkeypatch.setattr(sys, "argv", ["docagent", "scan", str(source), "--output", str(first), "--formats", "md"])
    main()
    result = json.loads(capsys.readouterr().out)
    first_zip = isolated / "first.docs.zip"
    assert result["package"] == str(first_zip)
    original = first_zip.read_bytes()
    (source / "app.py").write_text("def second():\n    return 2\n")
    second = isolated / "second"
    monkeypatch.setattr(sys, "argv", ["docagent", "scan", str(source), "--output", str(second), "--formats", "md"])
    main()
    assert first_zip.read_bytes() == original
    with zipfile.ZipFile(isolated / "second.zip") as archive:
        analysis = json.loads(archive.read("repository-documentation/06-analysis/Repository_Analysis_Summary.json"))
    assert any(finding["title"] == "second" for finding in analysis["findings"])
    assert not (isolated / "v0001.zip").exists()


def test_cli_does_not_overwrite_an_existing_zip(isolated, monkeypatch):
    source = isolated / "source"
    source.mkdir()
    output = isolated / "existing"
    package = isolated / "existing.zip"
    package.write_bytes(b"previous package")
    monkeypatch.setattr(sys, "argv", ["docagent", "scan", str(source), "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert package.read_bytes() == b"previous package"
    assert not output.exists()
