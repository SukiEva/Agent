from __future__ import annotations


def redis_key(namespace: str, resource_id: str, suffix: str) -> str:
    return f"{namespace}:{{{resource_id}}}:{suffix}"
