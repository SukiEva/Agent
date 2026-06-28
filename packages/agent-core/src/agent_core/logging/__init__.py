from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import logging
from typing import Iterator


_context: ContextVar[dict[str, object]] = ContextVar("agent_log_context", default={})


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def get_logger(name: str) -> logging.LoggerAdapter[logging.Logger]:
    return logging.LoggerAdapter(logging.getLogger(name), extra={})


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
