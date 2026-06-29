import os
from dataclasses import dataclass
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _env(name: str, default: str = "", aliases: tuple[str, ...] = ()) -> str:
    for key in (name, *aliases):
        value = os.getenv(key)
        if value is not None and value != "":
            return value
    return default


def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class Settings:
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.2
    llm_max_tokens: int = 8192
    request_timeout_seconds: int = 120
    task_timeout_seconds: int = 600
    tavily_api_key: str = ""
    weather_api_key: str = ""
    weather_base_url: str = "https://api.weatherapi.com/v1"
    weather_provider: str = "weatherapi"
    database_url: str = "sqlite:///./orchestration.db"
    artifact_root: str = "artifacts"
    artifact_max_files_per_task: int = 10
    artifact_max_file_bytes: int = 1024 * 1024
    artifact_max_archive_input_bytes: int = 5 * 1024 * 1024
    max_swarm_rounds: int = 2
    hard_max_swarm_rounds: int = 3
    max_agents: int = 4
    hard_max_agents: int = 6
    max_concurrent_agents: int = 2
    hard_max_concurrent_agents: int = 3
    max_tool_calls: int = 12
    react_max_tool_calls: int = 5
    max_fetch_chars: int = 12000
    search_results_limit: int = 5
    research_max_queries: int = 5
    research_auto_fetch_pages: int = 3
    research_supplemental_searches: int = 1
    evidence_per_subtask: int = 3
    fetch_top_results: int = 2
    llm_retries: int = 2
    tavily_retries: int = 1
    fetch_retries: int = 1

    @classmethod
    def from_env_file(cls, path: str | Path = ".env") -> "Settings":
        load_env_file(path)
        return cls.from_environment()

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            llm_base_url=_env(
                "LLM_BASE_URL",
                "https://api.deepseek.com",
                aliases=("DEEPSEEK_API_BASE_URL",),
            ),
            llm_api_key=_env("LLM_API_KEY", aliases=("DEEPSEEK_API_KEY",)),
            llm_model=_env("LLM_MODEL", "deepseek-chat", aliases=("MODEL_NAME",)),
            llm_temperature=float(_env("LLM_TEMPERATURE", "0.2")),
            llm_max_tokens=_int_env("LLM_MAX_TOKENS", 8192),
            request_timeout_seconds=_int_env("REQUEST_TIMEOUT_SECONDS", 120),
            task_timeout_seconds=_int_env("TASK_TIMEOUT_SECONDS", 600),
            tavily_api_key=_env("TAVILY_API_KEY"),
            weather_api_key=_env("WEATHER_API_KEY"),
            weather_base_url=_env(
                "WEATHER_BASE_URL", "https://api.weatherapi.com/v1"
            ).rstrip("/"),
            weather_provider=_env("WEATHER_PROVIDER", "weatherapi"),
            database_url=_env("DATABASE_URL", "sqlite:///./orchestration.db"),
            artifact_root=_env("ARTIFACT_ROOT", "artifacts"),
            artifact_max_files_per_task=_int_env(
                "ARTIFACT_MAX_FILES_PER_TASK", 10
            ),
            artifact_max_file_bytes=_int_env(
                "ARTIFACT_MAX_FILE_BYTES", 1024 * 1024
            ),
            artifact_max_archive_input_bytes=_int_env(
                "ARTIFACT_MAX_ARCHIVE_INPUT_BYTES", 5 * 1024 * 1024
            ),
            max_swarm_rounds=_int_env("MAX_SWARM_ROUNDS", 2),
            hard_max_swarm_rounds=_int_env("HARD_MAX_SWARM_ROUNDS", 3),
            max_agents=_int_env("MAX_AGENTS", 4),
            hard_max_agents=_int_env("HARD_MAX_AGENTS", 6),
            max_concurrent_agents=_int_env("MAX_CONCURRENT_AGENTS", 2),
            hard_max_concurrent_agents=_int_env("HARD_MAX_CONCURRENT_AGENTS", 3),
            max_tool_calls=_int_env("MAX_TOOL_CALLS", 12),
            react_max_tool_calls=_int_env("REACT_MAX_TOOL_CALLS", 5),
            max_fetch_chars=_int_env("MAX_FETCH_CHARS", 12000),
            search_results_limit=_int_env("SEARCH_RESULTS_LIMIT", 5),
            research_max_queries=_int_env("RESEARCH_MAX_QUERIES", 5),
            research_auto_fetch_pages=_int_env("RESEARCH_AUTO_FETCH_PAGES", 3),
            research_supplemental_searches=_int_env(
                "RESEARCH_SUPPLEMENTAL_SEARCHES", 1
            ),
            evidence_per_subtask=_int_env("EVIDENCE_PER_SUBTASK", 3),
            fetch_top_results=_int_env("FETCH_TOP_RESULTS", 2),
            llm_retries=_int_env("LLM_RETRIES", 2),
            tavily_retries=_int_env("TAVILY_RETRIES", 1),
            fetch_retries=_int_env("FETCH_RETRIES", 1),
        )

    def __post_init__(self) -> None:
        pairs = [
            ("max_swarm_rounds", self.max_swarm_rounds, self.hard_max_swarm_rounds),
            ("max_agents", self.max_agents, self.hard_max_agents),
            (
                "max_concurrent_agents",
                self.max_concurrent_agents,
                self.hard_max_concurrent_agents,
            ),
        ]
        for name, value, hard_value in pairs:
            if value > hard_value:
                raise ValueError(f"{name} cannot exceed hard limit {hard_value}")
