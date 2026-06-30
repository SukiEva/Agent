from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ServiceBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None


class ServerBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)


class RedisBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    url: str = "redis://localhost:6379/0"


class RuntimeBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    store: Literal["memory", "redis"] = "memory"
    ttl_seconds: int = Field(default=3600, ge=1)
    event_maxlen: int = Field(default=1000, ge=1)


class UserAuthBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    mode: Literal["noop", "header"] = "noop"


class InternalAuthBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    mode: Literal["noop", "shared_secret"] = "noop"
    secret: str = ""


class AuthBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    user: UserAuthBlock = Field(default_factory=UserAuthBlock)
    internal: InternalAuthBlock = Field(default_factory=InternalAuthBlock)


class FilesBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    local_root: str = ".data/files"


class LoggingBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    level: str = "INFO"
    format: Literal["json", "text"] = "json"


class TimeoutsBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_seconds: int = Field(default=600, ge=1)
    business_task_seconds: int = Field(default=300, ge=1)
    bridge_action_seconds: int = Field(default=30, ge=1)
    llm_call_seconds: int = Field(default=60, ge=1)


class LlmBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4.1-mini"
    temperature: float = Field(default=0.2, ge=0)
    timeout_seconds: int = Field(default=60, ge=1)
    required: bool = False


class GatewayBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    base_url: str | None = None


class RoutingBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    master_agent_id: str | None = None


class RegistryBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str | None = None


class ServiceSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    service: ServiceBlock = Field(default_factory=ServiceBlock)
    server: ServerBlock = Field(default_factory=ServerBlock)
    redis: RedisBlock = Field(default_factory=RedisBlock)
    runtime: RuntimeBlock = Field(default_factory=RuntimeBlock)
    auth: AuthBlock = Field(default_factory=AuthBlock)
    files: FilesBlock = Field(default_factory=FilesBlock)
    logging: LoggingBlock = Field(default_factory=LoggingBlock)
    timeouts: TimeoutsBlock = Field(default_factory=TimeoutsBlock)
    llm: LlmBlock | None = None
    gateway: GatewayBlock | None = None
    routing: RoutingBlock | None = None
    registry: RegistryBlock | None = None


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        from omegaconf import OmegaConf

        loaded = OmegaConf.load(path)
        return dict(OmegaConf.to_container(loaded, resolve=True) or {})
    except ModuleNotFoundError:
        return _load_minimal_yaml(path)


def load_service_config(service_conf_dir: Path, env: str = "dev") -> dict[str, Any]:
    core_default = Path(__file__).resolve().parents[1] / "conf" / "default.yaml"
    config: dict[str, Any] = {}
    for path in (
        core_default,
        service_conf_dir / "default.yaml",
        service_conf_dir / f"{env}.yaml",
    ):
        config = deep_merge(config, load_yaml_file(path))
    return validate_service_config(config)


def validate_service_config(config: dict[str, Any]) -> dict[str, Any]:
    settings = ServiceSettings.model_validate(config)
    return settings.model_dump(mode="python", exclude_none=True)


def _load_minimal_yaml(path: Path) -> dict[str, Any]:
    # Minimal indentation-based YAML reader for simple local config files.
    lines = [
        line
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any] | list[Any]]] = [(-1, root)]
    for index, raw_line in enumerate(lines):
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith("- "):
            if not isinstance(parent, list):
                continue
            item_text = line[2:].strip()
            if ":" in item_text:
                key, value = item_text.split(":", 1)
                item: dict[str, Any] = {key.strip(): _parse_scalar(value.strip())}
                parent.append(item)
                stack.append((indent, item))
            else:
                parent.append(_parse_scalar(item_text))
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if isinstance(parent, dict):
            if value:
                parent[key] = _parse_scalar(value)
            else:
                child = [] if _next_content_is_list(lines, index, indent) else {}
                parent[key] = child
                stack.append((indent, child))
    return root


def _next_content_is_list(lines: list[str], index: int, current_indent: int) -> bool:
    for next_line in lines[index + 1 :]:
        next_indent = len(next_line) - len(next_line.lstrip(" "))
        if next_indent <= current_indent:
            return False
        return next_line.strip().startswith("- ")
    return False


def _parse_scalar(value: str) -> Any:
    if value == "":
        return {}
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value
