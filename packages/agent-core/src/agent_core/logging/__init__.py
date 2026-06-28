from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import json
import logging
from typing import Iterator


_context: ContextVar[dict[str, object]] = ContextVar("agent_log_context", default={})
_SENSITIVE_KEYS = {"api_key", "authorization", "cookie", "secret", "token", "password"}


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.agent_context = current_context()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, self.datefmt),
        }
        context = getattr(record, "agent_context", {})
        if isinstance(context, dict):
            payload.update(_redact(context))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str = "INFO", *, json_format: bool = True) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.addFilter(ContextFilter())
    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def configure_service_logging(settings: dict[str, object]) -> None:
    logging_settings = settings.get("logging", {})
    if not isinstance(logging_settings, dict):
        logging_settings = {}
    configure_logging(
        level=str(logging_settings.get("level", "INFO")),
        json_format=str(logging_settings.get("format", "json")) == "json",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


@contextmanager
def bind_context(**fields: object) -> Iterator[None]:
    current = dict(_context.get())
    current.update({key: value for key, value in fields.items() if value is not None})
    token = _context.set(current)
    try:
        yield
    finally:
        _context.reset(token)


def current_context() -> dict[str, object]:
    return dict(_context.get())


def _redact(value: object) -> object:
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for key, item in value.items():
            lowered = key.lower()
            if lowered in _SENSITIVE_KEYS or any(part in lowered for part in _SENSITIVE_KEYS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
