import pytest
from docagent.analysis import scan_repository
from docagent.llm import enrich
from docagent.schemas import AnalysisConfig, LLMOutput, LLMRequirement


def sample(tmp_path):
    (tmp_path / "a.py").write_text("def hello():\n    return 'hello'\n")
    return scan_repository(tmp_path, "a" * 40)


def test_private_consent_blocks_before_call(tmp_path):
    config = AnalysisConfig(
        repository="owner/repo", providers=[{"provider": "openai", "model": "configured-model"}]
    )
    with pytest.raises(PermissionError):
        enrich(sample(tmp_path), config, True, invoke=lambda *a: pytest.fail("Must not call provider"))


def test_fallback_and_invalid_citations(tmp_path):
    analysis = sample(tmp_path)
    config = AnalysisConfig(
        repository="owner/repo",
        providers=[{"provider": "openai", "model": "m"}, {"provider": "anthropic", "model": "m"}],
        consent_providers=["openai", "anthropic"],
    )
    calls = []

    def invoke(provider, model, prompt):
        calls.append(provider)
        if provider == "openai":
            raise RuntimeError("fake outage")
        return LLMOutput(
            requirements=[
                LLMRequirement(title="bad", statement="unsupported", evidence_ids=["missing"]),
                LLMRequirement(
                    title="Greeting",
                    statement="Returns a greeting",
                    evidence_ids=[analysis["evidence"][0]["id"]],
                ),
            ],
            gaps=[],
        ), {"input_tokens": 10, "output_tokens": 20}

    result = enrich(analysis, config, True, invoke=invoke, sleep=lambda _: None)
    assert calls == ["openai", "openai", "openai", "anthropic"]
    assert not any(r["title"] == "bad" for r in result["requirements"])
    assert next(r for r in result["requirements"] if r["title"] == "Greeting")["confidence"] == "inferred"
    assert result["usage"][-1]["output_tokens"] == 20


def test_unchanged_evidence_reuses_ai_cache(isolated):
    from docagent.db import init_db, session_factory

    root = isolated / "source"
    root.mkdir()
    analysis = sample(root)
    init_db()
    config = AnalysisConfig(repository="owner/repo", providers=[{"provider": "openai", "model": "m"}])
    calls = []

    def invoke(*args):
        calls.append(args)
        return LLMOutput(requirements=[], gaps=[]), {"input_tokens": 10, "output_tokens": 5}

    with session_factory()() as db:
        enrich(analysis, config, False, invoke=invoke, db=db, cache_scope="owner/repo")
        db.commit()
        result = enrich(sample(root), config, False, invoke=invoke, db=db, cache_scope="owner/repo")
        assert len(calls) == 1
        assert result["usage"][0]["status"] == "reused"


def test_ai_scenarios_are_traceable_and_never_executed(tmp_path):
    analysis = sample(tmp_path)
    config = AnalysisConfig(repository="owner/repo", providers=[{"provider": "openai", "model": "m"}])

    def invoke(*args):
        return LLMOutput.model_validate(
            {
                "requirements": [
                    {
                        "title": "Greeting",
                        "statement": "Returns hello",
                        "evidence_ids": [analysis["evidence"][0]["id"]],
                        "scenarios": [
                            {
                                "title": "Greeting result",
                                "category": "positive",
                                "preconditions": ["Load module in an isolated test environment"],
                                "steps": ["Invoke hello() without arguments"],
                                "expected": "Returns the string hello",
                            }
                        ],
                    }
                ],
                "gaps": [],
            }
        ), {"input_tokens": 10, "output_tokens": 20}

    result = enrich(analysis, config, False, invoke=invoke)
    generated = next(t for t in result["test_cases"] if t["source"] == "llm")
    assert generated["status"] == "unexecuted"
    assert generated["steps"] == ["Invoke hello() without arguments"]
    assert any(r["id"] == generated["requirement_id"] for r in result["requirements"])
    assert (
        len(
            [
                t
                for t in result["test_cases"]
                if t["requirement_id"] == generated["requirement_id"] and t["category"] == "positive"
            ]
        )
        == 1
    )
