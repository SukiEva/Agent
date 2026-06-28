from __future__ import annotations

import io
import json
import logging

from agent_core.logging import bind_context, configure_logging, configure_service_logging, get_logger


def test_json_logging_includes_context_and_redacts_secrets() -> None:
    stream = io.StringIO()
    configure_logging(level="INFO", json_format=True)
    root = logging.getLogger()
    root.handlers[0].stream = stream

    logger = get_logger("test")
    with bind_context(trace_id="trace_1", api_key="secret", nested={"token": "secret"}):
        logger.info("hello")

    payload = json.loads(stream.getvalue())
    assert payload["message"] == "hello"
    assert payload["trace_id"] == "trace_1"
    assert payload["api_key"] == "[REDACTED]"
    assert payload["nested"]["token"] == "[REDACTED]"


def test_service_logging_uses_settings() -> None:
    stream = io.StringIO()
    configure_service_logging({"logging": {"level": "ERROR", "format": "text"}})
    root = logging.getLogger()
    root.handlers[0].stream = stream

    logger = get_logger("test")
    logger.info("ignored")
    logger.error("visible")

    output = stream.getvalue()
    assert "ignored" not in output
    assert "ERROR test visible" in output


if __name__ == "__main__":
    test_json_logging_includes_context_and_redacts_secrets()
    test_service_logging_uses_settings()
    print("logging tests ok")
