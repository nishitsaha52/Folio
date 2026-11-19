from docagent.analysis import scan_repository


def test_handler_guards_form_one_traceable_requirement(tmp_path):
    (tmp_path / "app.py").write_text('''from fastapi import FastAPI
app = FastAPI()
@app.post("/items")
def create_item(quantity: int):
    if quantity < 1:
        raise ValueError("quantity must be positive")
    if quantity > 100:
        raise ValueError("quantity exceeds limit")
    return {"quantity": quantity}
''')
    result = scan_repository(tmp_path, "a" * 40)
    assert len(result["requirements"]) == 1
    requirement = result["requirements"][0]
    assert "POST /items" in requirement["title"]
    assert "quantity < 1" in requirement["statement"]
    assert "quantity > 100" in requirement["statement"]
    related = [finding for finding in result["findings"] if finding["kind"] in {"api", "function", "business_rule"}]
    assert {eid for finding in related for eid in finding["evidence_ids"]} <= set(requirement["evidence_ids"])
    assert len(result["test_cases"]) == 3
    assert all(case["status"] == "unexecuted" for case in result["test_cases"])


def test_models_group_constraints_and_keep_internal_helpers_in_findings(tmp_path):
    (tmp_path / "models.py").write_text('''from pydantic import BaseModel, Field
class Item(BaseModel):
    quantity: int = Field(ge=1, le=100)
    name: str = Field(min_length=1)
def _helper(value):
    if value:
        return value
''')
    (tmp_path / "test_models.py").write_text('''from pydantic import BaseModel
class Fixture(BaseModel):
    quantity: int
''')
    result = scan_repository(tmp_path, "a" * 40)
    assert len(result["requirements"]) == 1
    assert result["requirements"][0]["title"] == "Item"
    assert "min_length=1" in result["requirements"][0]["statement"]
    assert any(finding["title"] == "_helper" for finding in result["findings"])
    assert any(finding["title"] == "Fixture" for finding in result["findings"])


def test_group_ids_survive_unrelated_declarations(tmp_path):
    source = tmp_path / "service.py"
    source.write_text("def total(value):\n    return value * 2\n")
    first = scan_repository(tmp_path, "a" * 40)
    source.write_text(source.read_text() + "\ndef another():\n    return 3\n")
    second = scan_repository(tmp_path, "b" * 40)
    assert first["requirements"][0]["id"] == second["requirements"][0]["id"]


def test_frontend_component_tests_are_not_acceptance_requirements(tmp_path):
    (tmp_path / "Widget.test.tsx").write_text("export function Fixture() { return <div />; }\n")
    result = scan_repository(tmp_path, "a" * 40)
    assert result["inventory"][0]["category"] == "test"
    assert not result["requirements"]
