from types import SimpleNamespace
from unittest.mock import MagicMock

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


def test_gemini_uses_json_schema_without_legacy_schema_conversion(monkeypatch):
    import docagent.llm as llm
    from docagent.config import Settings
    from google import genai

    cfg = Settings(_env_file=None, gemini_api_key="test-key")
    monkeypatch.setattr(llm, "settings", lambda: cfg)
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        text='{"requirements":[],"gaps":[]}',
        usage_metadata=SimpleNamespace(prompt_token_count=1, candidates_token_count=2),
    )
    manager = MagicMock()
    manager.__enter__.return_value = client
    monkeypatch.setattr(genai, "Client", lambda **kwargs: manager)
    result, usage = llm.call_provider("gemini", "configured-model", "Synthetic evidence")
    config = client.models.generate_content.call_args.kwargs["config"]
    assert config.response_schema is None
    assert config.response_json_schema == LLMOutput.model_json_schema()
    assert config.response_json_schema["additionalProperties"] is False
    assert result == LLMOutput(requirements=[], gaps=[])
    assert usage == {"input_tokens": 1, "output_tokens": 2}


def test_gemini_nonretryable_http_code_is_not_retried(tmp_path, caplog):
    from google.genai.errors import ClientError

    calls = []

    def fail(*_args):
        calls.append(True)
        raise ClientError(400, {"error": {"message": "credential-and-source-content", "status": "INVALID_ARGUMENT"}})

    config = AnalysisConfig(repository="owner/repo", providers=[{"provider": "gemini", "model": "m"}])
    result = enrich(sample(tmp_path), config, False, invoke=fail, sleep=lambda _: pytest.fail("Must not retry HTTP 400"))
    assert len(calls) == 1
    assert result["usage"][0]["status"] == "failed"
    assert "http_status=400" in caplog.text
    assert "credential-and-source-content" not in caplog.text


def synthetic_batches(tmp_path, count=24):
    analysis = sample(tmp_path)
    original = analysis["evidence"][0]
    analysis["evidence"] = [{**original, "id": f"SYN-{index}"} for index in range(count)]
    return analysis


def test_ai_reports_batch_progress_and_respects_total_time_budget(tmp_path, monkeypatch):
    import docagent.llm as llm
    from docagent.config import Settings

    monkeypatch.setattr(llm, "settings", lambda: Settings(
        _env_file=None, ai_time_budget_seconds=1, ai_request_timeout_seconds=1,
    ))
    clock = [0.0]
    calls, progress = [], []

    def invoke(*_args):
        calls.append(True)
        clock[0] = 2.0
        return LLMOutput(requirements=[], gaps=[]), {}

    config = AnalysisConfig(repository="owner/repo", providers=[{"provider": "gemini", "model": "m"}])
    result = enrich(synthetic_batches(tmp_path), config, False, invoke=invoke, clock=lambda: clock[0],
                    progress=lambda *args: progress.append(args))
    assert len(calls) == 1
    assert progress[0][:2] == (0, 3)
    assert any(item[0] == 1 for item in progress)
    assert progress[-1][:2] == (3, 3)
    assert any("time budget reached" in gap for gap in result["gaps"])
    assert result["requirements"]  # Static findings survive the budget.


def test_repeated_invalid_outputs_stop_without_repeating_identical_calls(tmp_path):
    from docagent.llm import ProviderResponseFailure

    calls = []

    def invoke(*_args):
        calls.append(True)
        raise ProviderResponseFailure("output_token_limit")

    config = AnalysisConfig(repository="owner/repo", providers=[{"provider": "gemini", "model": "m"}])
    result = enrich(synthetic_batches(tmp_path), config, False, invoke=invoke,
                    sleep=lambda _: pytest.fail("Malformed responses must not be retried unchanged"))
    assert len(calls) == 2
    assert any("provider failures" in gap for gap in result["gaps"])


def test_no_new_request_is_started_at_budget_edge(tmp_path, monkeypatch):
    import docagent.llm as llm
    from docagent.config import Settings

    monkeypatch.setattr(llm, "settings", lambda: Settings(_env_file=None, ai_time_budget_seconds=2))
    config = AnalysisConfig(repository="owner/repo", providers=[{"provider": "gemini", "model": "m"}])
    result = enrich(sample(tmp_path), config, False, clock=lambda: 0,
                    invoke=lambda *_: pytest.fail("Do not start a request with only two seconds remaining"))
    assert any("time budget reached" in gap for gap in result["gaps"])


def test_progress_failure_stops_before_any_provider_call(tmp_path):
    from docagent.jobs import WorkerLeaseLost

    def stop(*_args):
        raise WorkerLeaseLost()

    config = AnalysisConfig(repository="owner/repo", providers=[{"provider": "gemini", "model": "m"}])
    with pytest.raises(WorkerLeaseLost):
        enrich(sample(tmp_path), config, False, progress=stop,
               invoke=lambda *_: pytest.fail("Replaced worker must not call provider"))


def test_gemini_detects_truncation_before_parsing_partial_json(monkeypatch):
    import docagent.llm as llm
    from docagent.config import Settings
    from google import genai

    monkeypatch.setattr(llm, "settings", lambda: Settings(_env_file=None, gemini_api_key="test-key"))
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        text='{"requirements":[', candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")],
    )
    manager = MagicMock()
    manager.__enter__.return_value = client
    factory = MagicMock(return_value=manager)
    monkeypatch.setattr(genai, "Client", factory)
    with pytest.raises(llm.ProviderResponseFailure) as caught:
        llm.call_provider("gemini", "model", "Synthetic evidence", timeout_seconds=2)
    assert caught.value.reason == "output_token_limit"
    options = factory.call_args.kwargs["http_options"]
    assert options.timeout == 2000 and options.retry_options.attempts == 1
    config = client.models.generate_content.call_args.kwargs["config"]
    assert config.max_output_tokens == 12000
