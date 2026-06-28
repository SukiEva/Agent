from __future__ import annotations

from typing import Any


def hypercorn_bind(settings: dict[str, Any]) -> list[str]:
    server = settings.get("server", {})
    if not isinstance(server, dict):
        server = {}
    host = str(server.get("host", "0.0.0.0"))
    port = int(server.get("port", 8000))
    return [f"{host}:{port}"]
