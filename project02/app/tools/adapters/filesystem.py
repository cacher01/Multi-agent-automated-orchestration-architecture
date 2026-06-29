from __future__ import annotations

import fnmatch
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.tools.adapters.base import AdapterResult, ToolAdapterError
from app.tools.policy import FilesystemPolicy


class FileReaderAdapter:
    name = "file_reader"

    def __init__(self, policy: FilesystemPolicy) -> None:
        self.policy = policy

    def execute(self, tool_input: Mapping[str, Any]) -> AdapterResult:
        path = _resolve_allowed_path(str(tool_input.get("path") or ""), self.policy)
        max_chars = int(tool_input.get("max_chars") or 20000)
        content = path.read_text(encoding="utf-8")
        truncated = len(content) > max_chars
        return AdapterResult(
            output={"path": str(path), "content": content[:max_chars], "truncated": truncated},
            message="File read completed.",
        )


class FileWriterAdapter:
    name = "file_writer"

    def __init__(self, policy: FilesystemPolicy) -> None:
        self.policy = policy

    def execute(self, tool_input: Mapping[str, Any]) -> AdapterResult:
        path = _resolve_allowed_path(str(tool_input.get("path") or ""), self.policy, must_exist=False)
        operation = str(tool_input.get("operation") or "create")
        content = str(tool_input.get("content") or "")
        expected_hash = tool_input.get("expected_hash")
        if operation not in {"create", "update", "append"}:
            raise ToolAdapterError("invalid_operation", f"Unsupported file operation: {operation}")
        if operation == "create" and path.exists():
            raise ToolAdapterError("file_exists", "Refusing to create a file that already exists.")
        if operation == "update" and not path.exists():
            raise ToolAdapterError("file_missing", "Cannot update a missing file.")
        if expected_hash and path.exists() and _sha256(path.read_bytes()) != str(expected_hash):
            raise ToolAdapterError("hash_mismatch", "File hash does not match expected_hash.")
        path.parent.mkdir(parents=True, exist_ok=True)
        if operation == "append":
            with path.open("a", encoding="utf-8") as handle:
                written = handle.write(content)
        else:
            written = path.write_text(content, encoding="utf-8")
        return AdapterResult(
            output={"path": str(path), "operation": operation, "bytes_written": written},
            message="File write completed.",
        )


def _resolve_allowed_path(raw_path: str, policy: FilesystemPolicy, must_exist: bool = True) -> Path:
    if not raw_path:
        raise ToolAdapterError("invalid_path", "Path is required.")
    path = Path(raw_path).resolve()
    if must_exist and not path.exists():
        raise ToolAdapterError("file_missing", f"File does not exist: {path}")
    if _is_denied(path, policy.denied_paths):
        raise ToolAdapterError("path_denied", f"Path is denied by policy: {path.name}")
    allowed_roots = [Path(root).resolve() for root in (*policy.workspace_roots, *policy.extra_allowed_directories)]
    if not any(_is_relative_to(path, root) for root in allowed_roots):
        raise ToolAdapterError("path_not_allowed", f"Path is outside allowed roots: {path}")
    return path


def _is_denied(path: Path, patterns: tuple[str, ...]) -> bool:
    normalized = path.as_posix()
    return any(fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

