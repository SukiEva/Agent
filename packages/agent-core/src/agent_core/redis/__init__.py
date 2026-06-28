from __future__ import annotations


def redis_key(namespace: str, resource_id: str, suffix: str) -> str:
    return f"{namespace}:{{{resource_id}}}:{suffix}"


def conversation_state_key(conversation_id: str) -> str:
    return redis_key("conversation", conversation_id, "state")


def conversation_events_key(conversation_id: str) -> str:
    return redis_key("conversation", conversation_id, "events")


def action_state_key(action_id: str) -> str:
    return redis_key("action", action_id, "state")


def action_result_key(action_id: str) -> str:
    return redis_key("action", action_id, "result")


def run_state_key(run_id: str) -> str:
    return redis_key("run", run_id, "state")
