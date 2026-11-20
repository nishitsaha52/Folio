import copy
import json
from pathlib import Path
from zipfile import ZipFile

from docagent.analysis import scan_repository
from docagent.diagrams import graph_sets
from docagent.documents import export_package
from docagent.reporting import balanced_evidence, operation_title, refine_analysis
from docagent.schemas import AnalysisConfig


def sample(tmp_path):
    (tmp_path / "app.py").write_text('''from fastapi import FastAPI, HTTPException
app = FastAPI()
@app.get("/api/items")
def list_items():
    """Return the available catalogue."""
    return {"count": 2}
@app.delete("/api/items/{item_id}")
def delete_item(item_id: int):
    if item_id < 1:
        raise HTTPException(400, "Item ID must be positive")
    return {"status": "removed"}
def stable_id(value):
    return str(value)
''')
    example = tmp_path / "examples"
    example.mkdir()
    (example / "demo.py").write_text('''from fastapi import FastAPI
app = FastAPI()
@app.get("/unrelated")
def unrelated():
    return {"demo": True}
''')
    result = scan_repository(tmp_path, "a" * 40)
    result["repository"] = "owner/catalogue"
    return result


def test_capabilities_preserve_raw_candidates_and_exclude_examples(tmp_path):
    raw = sample(tmp_path)
    before = copy.deepcopy(raw)
    readable = refine_analysis(raw)
    assert raw == before
    assert len(readable["requirements"]) == 1
    assert readable["technical_candidates"]["requirements"] == before["requirements"]
    feature = readable["features"][0]
    assert {op["route"] for op in feature["operations"]} == {"/api/items", "/api/items/{item_id}"}
    assert "stable_id" not in readable["requirements"][0]["statement"]
    assert readable["report_scope"]["supporting_routes"] == 1
    assert refine_analysis(readable) == readable
    assert any(c["category"] == "positive" and '"count": 2' in c["expected"] for c in readable["test_cases"])
    assert any(c["category"] == "negative" and "HTTP 400" in c["expected"] for c in readable["test_cases"])
    assert all(c["status"] == "unexecuted" for c in readable["test_cases"])
    assert not any("Prepare a valid fixture after reviewing" in " ".join(c["steps"]) for c in readable["test_cases"])
    graphs = graph_sets(readable)
    assert "unrelated" not in json.dumps(graphs)


def test_library_does_not_invent_acceptance_scenarios(tmp_path):
    (tmp_path / "library.py").write_text("def transform(value):\n    return value.process()\n")
    readable = refine_analysis(scan_repository(tmp_path, "a" * 40))
    assert readable["requirements"]
    assert not readable["test_cases"]
    assert "need review" in readable["requirements"][0]["statement"]


def test_workflow_names_do_not_invent_an_authentication_provider():
    ordinary = {"metadata": {"route": "/api/tasks/start", "method": "POST"}}
    github = {"metadata": {"route": "/api/auth/github/start", "method": "GET"}}
    assert "GitHub" not in operation_title(ordinary)
    assert operation_title(github) == "Start GitHub sign in"


def test_ai_budget_samples_multiple_files_before_large_helper(tmp_path):
    raw = sample(tmp_path)
    first = raw["evidence"][0]
    raw["evidence"] = [{**first, "id": f"helper-{i}", "path": "large_helper.py"} for i in range(80)] + [
        {**first, "id": "other-module", "path": "other.py"}
    ]
    balanced = balanced_evidence(raw)
    assert balanced[1]["id"] == "other-module"


def test_all_formats_share_tables_diagrams_and_full_appendices(tmp_path):
    readable = refine_analysis(sample(tmp_path))
    state = {"baseline_hash": "b" * 64, "requirements_status": "pending", "acceptance_hash": "c" * 64,
             "uat_status": "pending", "counts": {"passed": 0, "failed": 0, "blocked": 0,
                                                "unexecuted": len(readable["test_cases"])},
             "results": [], "reviews": [], "ready_for_acceptance": False}
    root = tmp_path / "export"
    export_package(root, readable, AnalysisConfig(repository="owner/catalogue", formats=["md", "docx", "pdf"]), state, 1)
    assert (root / "06-analysis/Technical_Candidates.json").is_file()
    assert "stable_id" in (root / "06-analysis/Technical_Reference.md").read_text()
    srs = (root / "01-requirements/Software_Requirements_Specification.md").read_text()
    assert "stable_id" not in srs
    assert "| Operation | Description | Evidence |" in srs
    assert "Code evaluates:" not in srs
    with ZipFile(root / "03-architecture/System_Architecture.docx") as archive:
        assert any(name.startswith("word/media/") for name in archive.namelist())
        xml = archive.read("word/document.xml").decode()
        assert "<w:tbl>" in xml and "w:bookmarkStart" in xml
        assert "w:pBdr" not in xml
    from openpyxl import load_workbook

    workbook = load_workbook(root / "02-testing/Requirements_Traceability_Matrix.xlsx")
    assert "Coverage" in workbook.sheetnames
    assert workbook["Traceability"]["K1"].value == "Expected outcome"
    files = json.loads((root / "manifest.json").read_text())["files"]
    assert all((root / entry["path"]).stat().st_size == entry["bytes"] for entry in files)
    assert Path(str(root) + ".zip").is_file()


def test_spreadsheet_export_does_not_rescan_all_cells_per_record(tmp_path, monkeypatch):
    from docagent.documents import write_rtm
    from openpyxl.worksheet.worksheet import Worksheet

    readable = refine_analysis(sample(tmp_path))
    example = readable["test_cases"][0]
    readable["test_cases"] = [{**example, "id": f"TC-{index}"} for index in range(1000)]
    examined = [0]
    original = Worksheet.max_column.fget

    def measured(sheet):
        examined[0] += len(sheet._cells)
        return original(sheet)

    monkeypatch.setattr(Worksheet, "max_column", property(measured))
    write_rtm(tmp_path / "traceability.xlsx", readable, {"results": []})
    assert examined[0] < 100_000
