"""core/config.py 配置类测试"""

from pathlib import Path

import pytest

from src.core.config import Settings
from src.core.exceptions import ConfigError


class TestSettings:
    def test_default_values(self) -> None:
        """验证默认配置值"""
        settings = Settings()
        assert settings.APP_NAME == "Smart Assistant"
        assert settings.APP_VERSION == "3.0.0"
        assert settings.MODEL_NAME == "qwen-plus"
        assert settings.MODEL_NAME_LIGHT == "qwen-turbo"
        assert settings.JWT_EXPIRE_MINUTES == 1440
        assert settings.TOOL_TIMEOUT == 15
        assert settings.TOOL_WRITE_TIMEOUT == 20
        assert settings.AGENT_RECURSION_LIMIT == 10
        assert settings.TOKEN_DAILY_LIMIT == 500_000

    def test_allowed_extensions_list(self) -> None:
        settings = Settings()
        exts = settings.allowed_extensions_list
        assert isinstance(exts, list)
        assert "txt" in exts
        assert "pdf" in exts

    def test_custom_allowed_extensions(self) -> None:
        settings = Settings(ALLOWED_EXTENSIONS="csv,json")
        assert settings.allowed_extensions_list == ["csv", "json"]

    def test_upload_dir_relative(self) -> None:
        settings = Settings(UPLOAD_DIR="data/uploads")
        assert settings.upload_dir.name == "uploads"

    def test_chroma_path_relative(self) -> None:
        settings = Settings(CHROMA_PERSIST_DIR="data/chroma_db")
        assert "chroma_db" in settings.chroma_path

    def test_validate_required_missing_key(self) -> None:
        settings = Settings(OPENAI_API_KEY="")
        with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
            settings.validate_required()

    def test_validate_required_ok(self) -> None:
        settings = Settings(OPENAI_API_KEY="sk-test", SMTP_USERNAME="user@test.com")
        settings.validate_required()  # 不抛异常

    def test_rate_limit_configs(self) -> None:
        settings = Settings()
        assert "_default" in settings.TOOL_RATE_LIMIT_USER_TOOL
        assert settings.TOOL_RATE_LIMIT_USER_TOOL["do_send_email"] == 3
        assert settings.TOOL_RATE_LIMIT_USER_TOTAL == 60

    def test_tool_input_max_lengths_default(self) -> None:
        settings = Settings()
        assert settings.TOOL_INPUT_MAX_LENGTHS["add_memo.title"] == 50
        assert settings.TOOL_INPUT_MAX_LENGTHS["_default"] == 5000

    def test_model_config_extra_ignore(self) -> None:
        """extra="ignore" 应忽略未定义的 env 变量"""
        settings = Settings(UNKNOWN_KEY="value")
        assert not hasattr(settings, "UNKNOWN_KEY")
