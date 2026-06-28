from __future__ import annotations

from types import SimpleNamespace
import sys
from pathlib import Path

from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "apps" / "agent-server" / "src"))

from agent_server.main import _user_auth_headers  # noqa: E402


def test_user_auth_headers_fall_back_to_query_params_for_sse() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings={
                "auth": {
                    "user": {
                        "mode": "header",
                        "user_header": "x-user-id",
                        "tenant_header": "x-tenant-id",
                    }
                }
            }
        )
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/conversations/conv_1/events",
            "query_string": b"user_id=u1&tenant_id=t1",
            "headers": [],
        }
    )

    headers = _user_auth_headers(app, request)

    assert headers["x-user-id"] == "u1"
    assert headers["x-tenant-id"] == "t1"


def test_user_auth_headers_prefer_explicit_headers() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings={"auth": {"user": {"mode": "header"}}}
        )
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/conversations/conv_1/events",
            "query_string": b"user_id=query-user",
            "headers": [(b"x-user-id", b"header-user")],
        }
    )

    headers = _user_auth_headers(app, request)

    assert headers["x-user-id"] == "header-user"


if __name__ == "__main__":
    test_user_auth_headers_fall_back_to_query_params_for_sse()
    test_user_auth_headers_prefer_explicit_headers()
    print("agent server auth tests ok")
