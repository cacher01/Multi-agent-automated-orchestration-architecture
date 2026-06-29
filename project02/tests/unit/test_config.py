from pathlib import Path

import pytest

from app.config.settings import load_settings


def test_settings_defaults_and_safe_dict(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "DEEPSEEK_API_KEY=secret\nDEEPSEEK_BASE_URL=https://example.test\nDEEPSEEK_MODEL=deepseek\n",
        encoding="utf-8",
    )
    settings = load_settings(env={}, dotenv_path=dotenv)
    assert settings.task_token_budget == 12_000
    assert settings.database_url == "sqlite:///./data/app.db"
    assert settings.safe_dict()["deepseek_api_key"] == "***"
    assert "secret" not in str(settings.safe_dict())


def test_settings_accepts_user_provided_deepseek_aliases(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "DEEPSEEK_API_KEY=secret\nAPI_URL=https://example.test\nMODEL_NAME=deepseek\n",
        encoding="utf-8",
    )

    settings = load_settings(env={}, dotenv_path=dotenv)

    assert settings.deepseek_base_url == "https://example.test"
    assert settings.deepseek_model == "deepseek"


def test_missing_deepseek_settings_raises(tmp_path: Path) -> None:
    settings = load_settings(env={}, dotenv_path=tmp_path / ".env")
    with pytest.raises(RuntimeError, match="Missing required DeepSeek settings"):
        settings.require_deepseek()


def test_invalid_integer_setting_raises(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("TASK_TOKEN_BUDGET=abc\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid integer setting"):
        load_settings(env={}, dotenv_path=dotenv)
