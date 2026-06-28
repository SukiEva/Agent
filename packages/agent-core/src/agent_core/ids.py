from __future__ import annotations

from uuid import uuid4


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def new_conversation_id() -> str:
    return new_id("conv")


def new_client_id() -> str:
    return new_id("client")


def new_run_id() -> str:
    return new_id("run")


def new_task_id() -> str:
    return new_id("task")


def new_action_id() -> str:
    return new_id("act")


def new_message_id() -> str:
    return new_id("msg")
