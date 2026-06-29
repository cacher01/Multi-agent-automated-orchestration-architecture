from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.llm.base import (
    LLMConfigurationError,
    LLMMessage,
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    LLMTimeoutError,
)


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip().strip('"').strip("'"), value.strip().strip('"').strip("'"))


@dataclass
class DeepSeekProvider(LLMProvider):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    timeout_seconds: float = 60.0
    provider_name: str = "deepseek"

    def __post_init__(self) -> None:
        _load_dotenv()
        self.api_key = self.api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = (
            self.base_url
            or os.getenv("DEEPSEEK_BASE_URL")
            or os.getenv("DEEPSEEK_API_BASE")
            or os.getenv("DEEPSEEK_BASE")
            or os.getenv("API_URL")
            or os.getenv("BASE_URL")
            or "https://api.deepseek.com"
        ).rstrip("/")
        self.model = (
            self.model
            or os.getenv("DEEPSEEK_MODEL")
            or os.getenv("DEEPSEEK_MODEL_NAME")
            or os.getenv("MODEL_NAME")
            or os.getenv("MODEL")
        )
        if not self.api_key:
            raise LLMConfigurationError("Missing DEEPSEEK_API_KEY")
        if not self.model:
            raise LLMConfigurationError("Missing DEEPSEEK_MODEL")

    def generate(
        self,
        messages: Sequence[LLMMessage | Mapping[str, str]],
        model_options: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [message.to_dict() if isinstance(message, LLMMessage) else dict(message) for message in messages],
        }
        payload.update(dict(model_options or {}))
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise LLMTimeoutError("DeepSeek request timed out") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise LLMTimeoutError("DeepSeek request timed out") from exc
            raise LLMProviderError(f"DeepSeek request failed: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise LLMProviderError("DeepSeek returned invalid JSON") from exc

        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("DeepSeek response missing message content") from exc

        usage = raw.get("usage") or {}
        return LLMResponse(
            content=content,
            raw_response=raw,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
            model=str(raw.get("model") or self.model),
            provider=self.provider_name,
        )
