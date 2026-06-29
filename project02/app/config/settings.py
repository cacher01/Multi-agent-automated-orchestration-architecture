from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATABASE_URL = "sqlite:///./data/app.db"


def _load_dotenv(path: Path = Path(".env")) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().strip('"').strip("'")] = value.strip().strip('"').strip("'")
    return values


def _get_value(env: Mapping[str, str], dotenv: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        value = env.get(name)
        if value:
            return value
        value = dotenv.get(name)
        if value:
            return value
    return None


def _get_int(
    env: Mapping[str, str],
    dotenv: Mapping[str, str],
    name: str,
    default: int,
) -> int:
    value = _get_value(env, dotenv, name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid integer setting {name}") from exc


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str | None
    deepseek_base_url: str | None
    deepseek_model: str | None
    database_url: str = DEFAULT_DATABASE_URL
    task_token_budget: int = 12_000
    agent_token_budget: int = 3_000
    max_llm_calls_per_task: int = 20
    max_child_agents_per_task: int = 6
    task_timeout_seconds: int = 300
    max_retry_attempts: int = 3

    def require_deepseek(self) -> None:
        missing = [
            name
            for name, value in {
                "DEEPSEEK_API_KEY": self.deepseek_api_key,
                "DEEPSEEK_BASE_URL": self.deepseek_base_url,
                "DEEPSEEK_MODEL": self.deepseek_model,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing required DeepSeek settings: {', '.join(missing)}")

    def safe_dict(self) -> dict[str, object]:
        return {
            "deepseek_api_key": "***" if self.deepseek_api_key else None,
            "deepseek_base_url": self.deepseek_base_url,
            "deepseek_model": self.deepseek_model,
            "database_url": self.database_url,
            "task_token_budget": self.task_token_budget,
            "agent_token_budget": self.agent_token_budget,
            "max_llm_calls_per_task": self.max_llm_calls_per_task,
            "max_child_agents_per_task": self.max_child_agents_per_task,
            "task_timeout_seconds": self.task_timeout_seconds,
            "max_retry_attempts": self.max_retry_attempts,
        }


def load_settings(
    env: Mapping[str, str] | None = None,
    dotenv_path: Path = Path(".env"),
) -> Settings:
    current_env = os.environ if env is None else env
    dotenv = _load_dotenv(dotenv_path)
    return Settings(
        deepseek_api_key=_get_value(current_env, dotenv, "DEEPSEEK_API_KEY", "DEEPSEEK_APIKEY"),
        deepseek_base_url=_get_value(
            current_env,
            dotenv,
            "DEEPSEEK_BASE_URL",
            "DEEPSEEK_API_BASE",
            "DEEPSEEK_BASE",
            "API_URL",
            "BASE_URL",
        ),
        deepseek_model=_get_value(
            current_env,
            dotenv,
            "DEEPSEEK_MODEL",
            "DEEPSEEK_MODEL_NAME",
            "MODEL_NAME",
            "MODEL",
        ),
        database_url=_get_value(current_env, dotenv, "DATABASE_URL") or DEFAULT_DATABASE_URL,
        task_token_budget=_get_int(current_env, dotenv, "TASK_TOKEN_BUDGET", 12_000),
        agent_token_budget=_get_int(current_env, dotenv, "AGENT_TOKEN_BUDGET", 3_000),
        max_llm_calls_per_task=_get_int(current_env, dotenv, "MAX_LLM_CALLS_PER_TASK", 20),
        max_child_agents_per_task=_get_int(current_env, dotenv, "MAX_CHILD_AGENTS_PER_TASK", 6),
        task_timeout_seconds=_get_int(current_env, dotenv, "TASK_TIMEOUT_SECONDS", 300),
        max_retry_attempts=_get_int(current_env, dotenv, "MAX_RETRY_ATTEMPTS", 3),
    )


settings = load_settings()
