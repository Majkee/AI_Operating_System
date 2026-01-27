"""Tests for configuration management."""

import os
import tempfile
from pathlib import Path

import pytest
import tomli_w

from aios.config import (
    AIOSConfig,
    APIConfig,
    SafetyConfig,
    UIConfig,
    LoggingConfig,
    SessionConfig,
    load_toml_config,
    merge_configs,
    load_env_overrides,
    load_config,
    reset_config,
)


class TestConfigModels:
    """Test configuration model defaults and validation."""

    def test_api_config_defaults(self):
        """Test APIConfig has correct defaults."""
        config = APIConfig()
        assert config.api_key is None
        assert config.model == "claude-sonnet-4-5-20250929"
        assert config.max_tokens == 4096

    def test_safety_config_defaults(self):
        """Test SafetyConfig has correct defaults."""
        config = SafetyConfig()
        assert config.require_confirmation is True
        assert len(config.blocked_patterns) > 0
        assert len(config.dangerous_patterns) > 0
        assert "rm -rf /" in config.blocked_patterns

    def test_ui_config_defaults(self):
        """Test UIConfig has correct defaults."""
        config = UIConfig()
        assert config.show_technical_details is False
        assert config.use_colors is True
        assert config.show_commands is True

    def test_logging_config_defaults(self):
        """Test LoggingConfig has correct defaults."""
        config = LoggingConfig()
        assert config.enabled is True
        assert config.level == "info"

    def test_session_config_defaults(self):
        """Test SessionConfig has correct defaults."""
        config = SessionConfig()
        assert config.save_history is True
        assert config.max_history == 1000

    def test_full_config_defaults(self):
        """Test AIOSConfig assembles all sections."""
        config = AIOSConfig()
        assert isinstance(config.api, APIConfig)
        assert isinstance(config.safety, SafetyConfig)
        assert isinstance(config.ui, UIConfig)
        assert isinstance(config.logging, LoggingConfig)
        assert isinstance(config.session, SessionConfig)


class TestConfigLoading:
    """Test configuration loading from files."""

    def test_load_toml_config_exists(self):
        """Test loading an existing TOML file."""
        # Create temp file and close it before reading
        fd, temp_path = tempfile.mkstemp(suffix=".toml")
        try:
            with os.fdopen(fd, "wb") as f:
                tomli_w.dump({"api": {"model": "test-model"}}, f)

            config = load_toml_config(Path(temp_path))
            assert config["api"]["model"] == "test-model"
        finally:
            os.unlink(temp_path)

    def test_load_toml_config_not_exists(self):
        """Test loading a non-existent file returns empty dict."""
        config = load_toml_config(Path("/nonexistent/config.toml"))
        assert config == {}

    def test_merge_configs_simple(self):
        """Test merging two flat configs."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = merge_configs(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_configs_nested(self):
        """Test merging nested configs."""
        base = {"api": {"model": "base-model", "max_tokens": 1000}}
        override = {"api": {"model": "override-model"}}
        result = merge_configs(base, override)
        assert result["api"]["model"] == "override-model"
        assert result["api"]["max_tokens"] == 1000

    def test_merge_configs_deep_nested(self):
        """Test merging deeply nested configs."""
        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"c": 3}}}
        result = merge_configs(base, override)
        assert result["a"]["b"]["c"] == 3
        assert result["a"]["b"]["d"] == 2


class TestEnvironmentOverrides:
    """Test environment variable configuration."""

    def setup_method(self):
        """Save original environment."""
        self.original_env = os.environ.copy()

    def teardown_method(self):
        """Restore original environment."""
        os.environ.clear()
        os.environ.update(self.original_env)
        reset_config()

    def test_anthropic_api_key(self):
        """Test ANTHROPIC_API_KEY is loaded."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key-123"
        overrides = load_env_overrides()
        assert overrides["api"]["api_key"] == "test-key-123"

    def test_aios_api_key_priority(self):
        """Test AIOS_API_KEY takes priority over ANTHROPIC_API_KEY."""
        os.environ["ANTHROPIC_API_KEY"] = "anthropic-key"
        os.environ["AIOS_API_KEY"] = "aios-key"
        overrides = load_env_overrides()
        assert overrides["api"]["api_key"] == "aios-key"

    def test_model_override(self):
        """Test AIOS_MODEL override."""
        os.environ["AIOS_MODEL"] = "claude-opus-4-5-20251101"
        overrides = load_env_overrides()
        assert overrides["api"]["model"] == "claude-opus-4-5-20251101"

    def test_debug_mode(self):
        """Test AIOS_DEBUG enables debug settings."""
        os.environ["AIOS_DEBUG"] = "1"
        overrides = load_env_overrides()
        assert overrides["ui"]["show_technical_details"] is True
        assert overrides["logging"]["level"] == "debug"

    def test_no_overrides(self):
        """Test empty overrides when no env vars set."""
        # Clear relevant env vars
        for key in list(os.environ.keys()):
            if key.startswith("AIOS_") or key == "ANTHROPIC_API_KEY":
                del os.environ[key]
        overrides = load_env_overrides()
        assert overrides == {}


class TestConfigIntegration:
    """Test full configuration loading integration."""

    def setup_method(self):
        """Save original environment and reset config."""
        self.original_env = os.environ.copy()
        reset_config()

    def teardown_method(self):
        """Restore original environment and reset config."""
        os.environ.clear()
        os.environ.update(self.original_env)
        reset_config()

    def test_load_config_returns_aios_config(self):
        """Test load_config returns AIOSConfig instance."""
        config = load_config()
        assert isinstance(config, AIOSConfig)

    def test_env_overrides_applied(self):
        """Test environment variables override file config."""
        os.environ["AIOS_MODEL"] = "test-model-env"
        config = load_config()
        assert config.api.model == "test-model-env"

    def test_config_with_custom_values(self):
        """Test config with custom API key."""
        os.environ["ANTHROPIC_API_KEY"] = "sk-test-key"
        config = load_config()
        assert config.api.api_key == "sk-test-key"
