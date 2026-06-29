from __future__ import annotations

import re
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.tools.adapters.base import AdapterResult, ToolAdapterError
from app.tools.policy import CodeExecutorPolicy, FilesystemPolicy


class CodeExecutorAdapter:
    name = "code_executor"

    def __init__(self, code_policy: CodeExecutorPolicy, filesystem_policy: FilesystemPolicy) -> None:
        self.code_policy = code_policy
        self.filesystem_policy = filesystem_policy

    def execute(self, tool_input: Mapping[str, Any]) -> AdapterResult:
        command = tool_input.get("command")
        if not isinstance(command, list) or not all(isinstance(part, str) and part for part in command):
            raise ToolAdapterError("invalid_command", "Command must be a non-empty list of strings.")
        normalized = " ".join(command)
        self._check_blacklist(normalized)
        cwd = Path(str(tool_input.get("cwd") or ".")).resolve()
        self._check_cwd(cwd)
        timeout = int(tool_input.get("timeout_seconds") or self.code_policy.timeout_seconds)
        timeout = min(timeout, self.code_policy.timeout_seconds)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolAdapterError("tool_timeout", "Command execution timed out.") from exc
        duration = time.monotonic() - started
        return AdapterResult(
            output={
                "exit_code": completed.returncode,
                "stdout": completed.stdout[: self.code_policy.output_max_chars],
                "stderr": completed.stderr[: self.code_policy.output_max_chars],
                "duration_seconds": duration,
            },
            message="Command execution completed.",
        )

    def _check_blacklist(self, normalized: str) -> None:
        if normalized in self.code_policy.exact_commands:
            raise ToolAdapterError("command_denied", "Command is denied by exact blacklist.")
        for pattern in self.code_policy.patterns:
            if pattern and re.search(pattern, normalized, flags=re.IGNORECASE):
                raise ToolAdapterError("command_denied", "Command is denied by pattern blacklist.")

    def _check_cwd(self, cwd: Path) -> None:
        roots = [Path(root).resolve() for root in (*self.filesystem_policy.workspace_roots, *self.filesystem_policy.extra_allowed_directories)]
        if not any(_is_relative_to(cwd, root) for root in roots):
            raise ToolAdapterError("cwd_not_allowed", f"Command cwd is outside allowed roots: {cwd}")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

