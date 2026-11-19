import pytest
from docagent.analysis import scan_repository


@pytest.mark.parametrize("source_root", ["", "src", "backend", "services/python"])
def test_python_package_roots(tmp_path, source_root):
    package = tmp_path / source_root / "example"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "api.py").write_text("from example.service import run\n")
    (package / "service.py").write_text("def run():\n    return 1\n")
    result = scan_repository(tmp_path, "a" * 40)
    prefix = source_root + "/" if source_root else ""
    assert any(edge["source"] == prefix + "example/api.py" and edge["target"] == prefix + "example/service.py"
               for edge in result["edges"])


def test_all_relative_modules_and_package_initializers_are_retained(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "api.py").write_text("from . import first as alias, second\nfrom .first import value\n")
    (package / "first.py").write_text("value = 1\n")
    (package / "second.py").write_text("value = 2\n")
    result = scan_repository(tmp_path, "a" * 40)
    edges = [edge for edge in result["edges"] if edge["source"] == "pkg/api.py"]
    assert {edge["target"] for edge in edges if edge["line"] == 1} == {
        "pkg/__init__.py", "pkg/first.py", "pkg/second.py",
    }
    assert any(edge["target"] == "pkg/first.py" and edge["line"] == 2 for edge in edges)


def test_declared_namespace_source_root(tmp_path):
    package = tmp_path / "python" / "example"
    package.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[tool.setuptools.packages.find]\nwhere = ["python"]\n')
    (package / "api.py").write_text("from example.service import run\n")
    (package / "service.py").write_text("def run():\n    return 1\n")
    result = scan_repository(tmp_path, "a" * 40)
    assert any(edge["target"] == "python/example/service.py" for edge in result["edges"])


def test_ambiguous_packages_are_not_falsely_linked(tmp_path):
    for source_root in ("first/src", "second/src"):
        package = tmp_path / source_root / "example"
        package.mkdir(parents=True)
        (package / "service.py").write_text("value = 1\n")
    (tmp_path / "consumer.py").write_text("import example.service\n")
    result = scan_repository(tmp_path, "a" * 40)
    assert not result["edges"]


def test_repository_root_initializer_and_source_root_precedence(tmp_path):
    (tmp_path / "__init__.py").write_text("")
    for source_root in ("first/src", "second/src"):
        package = tmp_path / source_root / "example"
        package.mkdir(parents=True)
        (package / "service.py").write_text("value = 1\n")
    (tmp_path / "first/src/example/api.py").write_text("import example.service\n")
    result = scan_repository(tmp_path, "a" * 40)
    assert [edge["target"] for edge in result["edges"]] == ["first/src/example/service.py"]
