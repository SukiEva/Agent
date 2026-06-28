from __future__ import annotations

import asyncio

from agent_core.auth import (
    AuthError,
    HeaderUserAuthenticator,
    NoopInternalAuthenticator,
    NoopUserAuthenticator,
    SharedSecretInternalAuthenticator,
    build_internal_auth_headers,
    build_internal_authenticator,
    build_user_authenticator,
)


def test_noop_authenticators() -> None:
    asyncio.run(_test_noop_authenticators())


async def _test_noop_authenticators() -> None:
    user = await NoopUserAuthenticator().authenticate({})
    internal = await NoopInternalAuthenticator().authenticate({})
    assert user.user_id == "anonymous"
    assert internal.service_id == "anonymous-service"


def test_header_user_authenticator() -> None:
    asyncio.run(_test_header_user_authenticator())


async def _test_header_user_authenticator() -> None:
    auth = HeaderUserAuthenticator()
    context = await auth.authenticate({"x-user-id": "u1", "x-tenant-id": "t1"})
    assert context.user_id == "u1"
    assert context.tenant_id == "t1"
    try:
        await auth.authenticate({})
    except AuthError:
        pass
    else:
        raise AssertionError("missing user header should fail")


def test_shared_secret_internal_authenticator() -> None:
    asyncio.run(_test_shared_secret_internal_authenticator())


async def _test_shared_secret_internal_authenticator() -> None:
    auth = SharedSecretInternalAuthenticator(secret="secret")
    context = await auth.authenticate(
        {
            "x-agent-internal-secret": "secret",
            "x-service-id": "demo-service",
            "x-agent-id": "demo_agent",
        }
    )
    assert context.service_id == "demo-service"
    assert context.agent_id == "demo_agent"
    try:
        await auth.authenticate({"x-agent-internal-secret": "wrong"})
    except AuthError:
        pass
    else:
        raise AssertionError("wrong internal secret should fail")


def test_auth_factories() -> None:
    assert isinstance(build_user_authenticator({"auth": {"user": {"mode": "noop"}}}), NoopUserAuthenticator)
    assert isinstance(
        build_internal_authenticator({"auth": {"internal": {"mode": "noop"}}}),
        NoopInternalAuthenticator,
    )
    assert isinstance(
        build_internal_authenticator({"auth": {"internal": {"mode": "shared_secret", "secret": "secret"}}}),
        SharedSecretInternalAuthenticator,
    )


def test_internal_auth_headers() -> None:
    headers = build_internal_auth_headers(
        {"auth": {"internal": {"mode": "shared_secret", "secret": "secret"}}},
        service_id="demo-service",
        agent_id="demo_agent",
    )
    assert headers == {
        "x-service-id": "demo-service",
        "x-agent-id": "demo_agent",
        "x-agent-internal-secret": "secret",
    }

    noop_headers = build_internal_auth_headers(
        {"auth": {"internal": {"mode": "noop"}}},
        service_id="demo-service",
    )
    assert noop_headers == {"x-service-id": "demo-service"}


if __name__ == "__main__":
    test_noop_authenticators()
    test_header_user_authenticator()
    test_shared_secret_internal_authenticator()
    test_auth_factories()
    test_internal_auth_headers()
    print("auth tests ok")
