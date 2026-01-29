"""
Configuration management for AIOS.

Loads configuration from multiple sources in order of priority:
1. Environment variables (AIOS_*)
2. User config (~/.config/aios/config.toml)
3. System config (/etc/aios/config.toml)
4. Default config (bundled with package)
"""

import os
import sys
from pathlib import Path
from typing import Any, List, Literal, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
from pydantic import BaseModel, ConfigDict, Field


class APIConfig(BaseModel):
    """API configuration."""
    api_key: Optional[str] = Field(default=None, description="Anthropic API key")
    model: str = Field(default="claude-sonnet-4-5-20250929", description="Model to use")
    max_tokens: int = Field(default=4096, description="Max tokens per response")
    streaming: bool = Field(default=True, description="Stream responses word-by-word")
    context_budget: int = Field(default=150000, description="Max tokens for conversation history")
    summarize_threshold: float = Field(
        default=0.75,
        description="Trigger summarization at this percentage of context budget (0.5-0.95)"
    )
    min_recent_messages: int = Field(
        default=6,
        description="Always keep at least this many recent messages (2-20)"
    )


class SafetyConfig(BaseModel):
    """Safety and guardrails configuration."""
    require_confirmation: bool = Field(default=True, description="Require confirmation for dangerous commands")
    blocked_patterns: list[str] = Field(
        default_factory=lambda: [
            r"rm -rf /",
            r"mkfs\.",
            r"dd if=.* of=/dev/",
            r":(){:|:&};:",
            r"> /dev/sda",
        ],
        description="Commands that are always blocked"
    )
    dangerous_patterns: list[str] = Field(
        default_factory=lambda: [
            r"rm -rf",
            r"chmod 777",
            r"chown",
            r"shutdown",
            r"reboot",
            r"systemctl stop",
            r"apt remove",
            r"apt purge",
        ],
        description="Commands requiring explicit confirmation"
    )


class UIConfig(BaseModel):
    """UI configuration."""
    show_technical_details: bool = Field(default=False, description="Show technical details")
    use_colors: bool = Field(default=True, description="Use colors in output")
    show_commands: bool = Field(default=True, description="Show commands being executed")


class LoggingConfig(BaseModel):
    """Logging configuration."""
    enabled: bool = Field(default=True, description="Enable audit logging")
    path: str = Field(default="~/.config/aios/logs/audit.log", description="Log file path")
    level: str = Field(default="info", description="Log level")


class SessionConfig(BaseModel):
    """Session configuration."""
    save_history: bool = Field(default=True, description="Save conversation history")
    history_path: str = Field(default="~/.config/aios/history", description="History file location")
    max_history: int = Field(default=1000, description="Maximum history entries")


class ExecutorConfig(BaseModel):
    """Executor configuration."""
    default_timeout: int = Field(default=30, description="Default command timeout in seconds")
    max_timeout: int = Field(default=3600, description="Maximum allowed timeout in seconds")


class CodeConfig(BaseModel):
    """Claude Code integration configuration."""
    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(default=True, description="Enable Claude Code integration")
    auto_detect: bool = Field(default=True, description="Auto-detect coding requests")
    auto_detect_sensitivity: str = Field(
        default="moderate",
        description="Detection sensitivity: high, moderate, low"
    )
    default_working_directory: Optional[str] = Field(
        default=None,
        description="Default CWD for code tasks"
    )
    auth_mode: Optional[Literal["api_key", "subscription"]] = Field(
        default=None,
        description="Auth mode: 'api_key' or 'subscription' (None = prompt on first use)"
    )


class WidgetsConfig(BaseModel):
    """Widgets configuration for welcome screen."""
    enabled: List[str] = Field(
        default=["cpu_memory"],
        description="List of enabled widget names"
    )


class AIOSConfig(BaseModel):
    """Main AIOS configuration."""
    api: APIConfig = Field(default_factory=APIConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    executor: ExecutorConfig = Field(default_factory=ExecutorConfig)
    code: CodeConfig = Field(default_factory=CodeConfig)
    widgets: WidgetsConfig = Field(default_factory=WidgetsConfig)


def get_config_paths() -> list[Path]:
    """Get configuration file paths in order of priority."""
    paths = []

    # User config (highest priority)
    user_config = Path.home() / ".config" / "aios" / "config.toml"
    paths.append(user_config)

    # System config
    system_config = Path("/etc/aios/config.toml")
    paths.append(system_config)

    # Default config (bundled inside package — works for pip/wheel installs)
    default_config = Path(__file__).parent / "data" / "default.toml"
    if not default_config.exists():
        # Fallback for Docker / editable / development installs
        # Try both possible locations
        fallback1 = Path(__file__).parent.parent / "config" / "default.toml"
        fallback2 = Path(__file__).parent.parent / "app-config" / "default.toml"
        if fallback1.exists():
            default_config = fallback1
        elif fallback2.exists():
            default_config = fallback2
    paths.append(default_config)

    return paths


def load_toml_config(path: Path) -> dict[str, Any]:
    """Load configuration from a TOML file."""
    if path.exists():
        with open(path, "rb") as f:
            return tomllib.load(f)
    return {}


def merge_configs(base: dict, override: dict) -> dict:
    """Deep merge two configuration dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def load_env_overrides() -> dict[str, Any]:
    """Load configuration overrides from environment variables."""
    overrides: dict[str, Any] = {}

    # API key from environment
    api_key = os.environ.get("AIOS_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        overrides.setdefault("api", {})["api_key"] = api_key

    # Model override
    model = os.environ.get("AIOS_MODEL")
    if model:
        overrides.setdefault("api", {})["model"] = model

    # Debug mode
    if os.environ.get("AIOS_DEBUG"):
        overrides.setdefault("ui", {})["show_technical_details"] = True
        overrides.setdefault("logging", {})["level"] = "debug"

    return overrides


def load_config() -> AIOSConfig:
    """Load configuration from all sources."""
    config_data: dict[str, Any] = {}

    # Load from files (lowest to highest priority)
    for path in reversed(get_config_paths()):
        file_config = load_toml_config(path)
        config_data = merge_configs(config_data, file_config)

    # Apply environment overrides (highest priority)
    env_overrides = load_env_overrides()
    config_data = merge_configs(config_data, env_overrides)

    return AIOSConfig(**config_data)


def ensure_config_dirs() -> None:
    """Ensure configuration directories exist."""
    user_config_dir = Path.home() / ".config" / "aios"
    user_config_dir.mkdir(parents=True, exist_ok=True)

    # Create history directory
    history_dir = user_config_dir / "history"
    history_dir.mkdir(exist_ok=True)


# Global config instance
_config: Optional[AIOSConfig] = None


def get_config() -> AIOSConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        ensure_config_dirs()
        _config = load_config()
    return _config


def reset_config() -> None:
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None


def is_first_login() -> bool:
    """
    Check if this is the first login by checking if user config exists 
    and has been explicitly configured via the setup wizard.
    
    Returns True if:
    - User config file doesn't exist, OR
    - User config file exists but doesn't have setup_complete flag set
      (meaning user hasn't run the new setup wizard)
    """
    user_config_file = Path.home() / ".config" / "aios" / "config.toml"
    
    # If user config doesn't exist, it's first login
    if not user_config_file.exists():
        return True
    
    try:
        # Read only the user config file (not merged with defaults)
        with open(user_config_file, "rb") as f:
            config_data = tomllib.load(f)
            # Check if setup_complete flag is set
            # This flag is only set by the new setup wizard
            setup_complete = config_data.get("setup_complete", False)
            
            # If setup_complete flag is set, user has run the wizard
            if setup_complete:
                return False
            
            # If setup_complete is not set, treat as first login
            # This handles old config files created before the flag was added
            return True
    except (OSError, IOError, KeyError, ValueError) as e:
        # On any error reading config, assume first login to be safe
        return True
