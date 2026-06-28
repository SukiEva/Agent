from __future__ import annotations

from pathlib import Path
from typing import Any


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
    return config


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
