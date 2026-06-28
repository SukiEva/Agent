from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from agent_core.schemas.auth import AuthContext, InternalAuthContext


class AuthError(Exception):
    pass


class UserAuthenticator:
    async def authenticate(self, headers: Mapping[str, str]) -> AuthContext:
        raise NotImplementedError


class InternalAuthenticator:
    async def authenticate(self, headers: Mapping[str, str]) -> InternalAuthContext:
        raise NotImplementedError


class NoopUserAuthenticator(UserAuthenticator):
    async def authenticate(self, headers: Mapping[str, str]) -> AuthContext:
        return AuthContext()


class NoopInternalAuthenticator(InternalAuthenticator):
    async def authenticate(self, headers: Mapping[str, str]) -> InternalAuthContext:
        return InternalAuthContext()


@dataclass
class HeaderUserAuthenticator(UserAuthenticator):
    user_header: str = "x-user-id"
    tenant_header: str = "x-tenant-id"

    async def authenticate(self, headers: Mapping[str, str]) -> AuthContext:
        user_id = headers.get(self.user_header)
        if not user_id:
            raise AuthError(f"missing required header: {self.user_header}")
        return AuthContext(
            user_id=user_id,
            tenant_id=headers.get(self.tenant_header),
        )


@dataclass
class SharedSecretInternalAuthenticator(InternalAuthenticator):
    secret: str
    header: str = "x-agent-internal-secret"
    service_header: str = "x-service-id"
    agent_header: str = "x-agent-id"

    async def authenticate(self, headers: Mapping[str, str]) -> InternalAuthContext:
        if headers.get(self.header) != self.secret:
            raise AuthError("invalid internal shared secret")
        return InternalAuthContext(
            service_id=headers.get(self.service_header, "unknown-service"),
            agent_id=headers.get(self.agent_header),
            scopes=["internal"],
        )


def build_user_authenticator(settings: dict[str, object]) -> UserAuthenticator:
    auth_settings = _auth_settings(settings).get("user", {})
    mode = auth_settings.get("mode", "noop")
    if mode == "noop":
        return NoopUserAuthenticator()
    if mode == "header":
        return HeaderUserAuthenticator(
            user_header=str(auth_settings.get("user_header", "x-user-id")).lower(),
            tenant_header=str(auth_settings.get("tenant_header", "x-tenant-id")).lower(),
        )
    raise ValueError(f"unsupported user auth mode: {mode}")


def build_internal_authenticator(settings: dict[str, object]) -> InternalAuthenticator:
    auth_settings = _auth_settings(settings).get("internal", {})
    mode = auth_settings.get("mode", "noop")
    if mode == "noop":
        return NoopInternalAuthenticator()
    if mode == "shared_secret":
        secret = str(auth_settings.get("secret", ""))
        if not secret:
            raise ValueError("internal shared_secret auth requires auth.internal.secret")
        return SharedSecretInternalAuthenticator(
            secret=secret,
            header=str(auth_settings.get("header", "x-agent-internal-secret")).lower(),
        )
    raise ValueError(f"unsupported internal auth mode: {mode}")


def build_internal_auth_headers(
    settings: dict[str, object],
    *,
    service_id: str,
    agent_id: str | None = None,
) -> dict[str, str]:
    auth_settings = _auth_settings(settings).get("internal", {})
    mode = auth_settings.get("mode", "noop")
    headers = {"x-service-id": service_id}
    if agent_id:
        headers["x-agent-id"] = agent_id
    if mode == "noop":
        return headers
    if mode == "shared_secret":
        secret = str(auth_settings.get("secret", ""))
        if not secret:
            raise ValueError("internal shared_secret auth requires auth.internal.secret")
        header = str(auth_settings.get("header", "x-agent-internal-secret")).lower()
        headers[header] = secret
        return headers
    raise ValueError(f"unsupported internal auth mode: {mode}")


def _auth_settings(settings: dict[str, object]) -> dict[str, object]:
    value = settings.get("auth", {})
    return value if isinstance(value, dict) else {}
