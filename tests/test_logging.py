import logging
import sys
from types import SimpleNamespace

import pytest
from docagent.cli import main
from docagent.config import Settings, settings
from docagent.logging_config import SDK_LOGGERS, configure_logging
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def restore_logging():
    names = ("", "docagent", *SDK_LOGGERS)
    levels = {name: logging.getLogger(name).level for name in names}
    root_handlers = logging.getLogger().handlers[:]
    yield
    for name, level in levels.items():
        logging.getLogger(name).setLevel(level)
    logging.getLogger().handlers[:] = root_handlers


@pytest.mark.parametrize("value, expected", [("debug", "DEBUG"), (" INFO ", "INFO"),
                                             ("Warning", "WARNING"), ("ERROR", "ERROR"),
                                             ("critical", "CRITICAL")])
def test_log_level_environment_is_case_insensitive(monkeypatch, value, expected):
    monkeypatch.setenv("DOCAGENT_LOG_LEVEL", value)
    assert Settings(_env_file=None).log_level == expected


def test_invalid_log_level_is_rejected(monkeypatch):
    monkeypatch.setenv("DOCAGENT_LOG_LEVEL", "VERBOSE")
    with pytest.raises(ValidationError, match="log_level"):
        Settings(_env_file=None)


def test_debug_logs_application_without_enabling_sdk_request_logging(caplog):
    configure_logging("DEBUG")
    logging.getLogger("docagent.queue").debug("Application diagnostic")
    logging.getLogger("httpx").debug("Sensitive request diagnostic")
    logging.getLogger("botocore.auth").debug("Sensitive signing diagnostic")
    assert "Application diagnostic" in caplog.text
    assert "Sensitive" not in caplog.text
    configure_logging("ERROR")
    caplog.clear()
    logging.getLogger("docagent.queue").warning("Routine warning")
    logging.getLogger("httpx").warning("SDK warning")
    logging.getLogger("docagent.queue").error("Application failure")
    assert "warning" not in caplog.text
    assert "Application failure" in caplog.text


@pytest.mark.parametrize("override, expected", [(None, "warning"), ("DEBUG", "debug")])
def test_serve_passes_effective_level_and_keeps_access_logs_disabled(isolated, monkeypatch, override, expected):
    import uvicorn

    monkeypatch.setenv("DOCAGENT_LOG_LEVEL", "WARNING")
    settings.cache_clear()
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    arguments = ["docagent", "serve", "--host", "0.0.0.0", "--port", "8123"]
    if override:
        arguments.extend(["--log-level", override])
    monkeypatch.setattr(sys, "argv", arguments)
    main()
    assert calls == [(("docagent.api:app",), {"host": "0.0.0.0", "port": 8123,
                                           "log_level": expected, "access_log": False})]
    # The application lifespan must see the same override as the server.
    assert settings().log_level.lower() == expected


def test_worker_and_scheduler_forward_configured_level(isolated, monkeypatch):
    monkeypatch.setenv("DOCAGENT_LOG_LEVEL", "ERROR")
    settings.cache_clear()
    calls = []
    celery = SimpleNamespace(worker_main=lambda args: calls.append(args), start=lambda args: calls.append(args))
    monkeypatch.setitem(sys.modules, "docagent.worker", SimpleNamespace(celery=celery))
    monkeypatch.setattr(sys, "argv", ["docagent", "worker", "--pool", "solo", "--concurrency", "1"])
    main()
    monkeypatch.setattr(sys, "argv", ["docagent", "scheduler", "--log-level", "debug",
                                     "--schedule", str(isolated / "beat" / "state")])
    main()
    assert calls[0] == ["worker", "--loglevel=ERROR", "--concurrency=1", "--pool=solo"]
    assert calls[1] == ["beat", "--loglevel=DEBUG", "--schedule=" + str(isolated / "beat" / "state")]
    assert (isolated / "beat").is_dir()
