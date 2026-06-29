from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_TOOL_POLICY_PATH = Path("config/tool_policy.yaml")


@dataclass(frozen=True)
class FilesystemPolicy:
    workspace_roots: tuple[str, ...] = (".",)
    extra_allowed_directories: tuple[str, ...] = ()
    denied_paths: tuple[str, ...] = (".env", "**/*.pem", "**/*.key")


@dataclass(frozen=True)
class CodeExecutorPolicy:
    timeout_seconds: int = 120
    output_max_chars: int = 20000
    exact_commands: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ("rm -rf", "Remove-Item .* -Recurse", "git reset --hard", "git clean -fd")


@dataclass(frozen=True)
class ApiCallerPolicy:
    allowed_domains: tuple[str, ...] = ()


@dataclass(frozen=True)
class WebSearchPolicy:
    provider: str = "auto"


@dataclass(frozen=True)
class ToolPolicy:
    web_search: WebSearchPolicy = field(default_factory=WebSearchPolicy)
    filesystem: FilesystemPolicy = field(default_factory=FilesystemPolicy)
    code_executor: CodeExecutorPolicy = field(default_factory=CodeExecutorPolicy)
    api_caller: ApiCallerPolicy = field(default_factory=ApiCallerPolicy)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> ToolPolicy:
        filesystem_data = _mapping(data.get("filesystem"))
        executor_data = _mapping(data.get("code_executor"))
        blacklist_data = _mapping(executor_data.get("blacklist"))
        api_data = _mapping(data.get("api_caller"))
        search_data = _mapping(data.get("web_search"))
        return cls(
            web_search=WebSearchPolicy(provider=str(search_data.get("provider") or "auto")),
            filesystem=FilesystemPolicy(
                workspace_roots=_strings(filesystem_data.get("workspace_roots"), default=(".",)),
                extra_allowed_directories=_strings(filesystem_data.get("extra_allowed_directories")),
                denied_paths=_strings(filesystem_data.get("denied_paths"), default=(".env", "**/*.pem", "**/*.key")),
            ),
            code_executor=CodeExecutorPolicy(
                timeout_seconds=_int(executor_data.get("timeout_seconds"), 120),
                output_max_chars=_int(executor_data.get("output_max_chars"), 20000),
                exact_commands=_strings(blacklist_data.get("exact_commands")),
                patterns=_strings(
                    blacklist_data.get("patterns"),
                    default=("rm -rf", "Remove-Item .* -Recurse", "git reset --hard", "git clean -fd"),
                ),
            ),
            api_caller=ApiCallerPolicy(allowed_domains=_strings(api_data.get("allowed_domains"))),
        )


def load_tool_policy(path: Path | str = DEFAULT_TOOL_POLICY_PATH) -> ToolPolicy:
    policy_path = Path(path)
    if not policy_path.exists():
        return ToolPolicy()
    parsed = _parse_yaml_subset(policy_path.read_text(encoding="utf-8"))
    return ToolPolicy.from_mapping(parsed)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: object, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    return default


def _int(value: object, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def _parse_yaml_subset(text: str) -> dict[str, Any]:
    lines = [
        (len(raw) - len(raw.lstrip(" ")), raw.strip())
        for raw in text.splitlines()
        if raw.strip() and not raw.strip().startswith("#")
    ]
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    for index, (indent, stripped) in enumerate(lines):
        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if stripped.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError("Invalid tool policy list item placement.")
            parent.append(_parse_scalar(stripped[2:].strip()))
            continue

        key, separator, raw_value = stripped.partition(":")
        if not separator:
            raise ValueError(f"Invalid tool policy line: {stripped}")
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value:
            if not isinstance(parent, dict):
                raise ValueError("Invalid tool policy mapping placement.")
            parent[key] = _parse_scalar(raw_value)
            continue

        next_is_list = index + 1 < len(lines) and lines[index + 1][0] > indent and lines[index + 1][1].startswith("- ")
        child: dict[str, Any] | list[Any] = [] if next_is_list else {}
        if not isinstance(parent, dict):
            raise ValueError("Invalid tool policy nested mapping placement.")
        parent[key] = child
        stack.append((indent, child))
    return root


def _parse_scalar(value: str) -> Any:
    if value in {"[]", "{}"}:
        return [] if value == "[]" else {}
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.isdigit():
        return int(value)
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value

