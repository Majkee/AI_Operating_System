"""Pytest configuration and shared fixtures."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    dir_path = tempfile.mkdtemp()
    yield dir_path
    # Cleanup
    import shutil
    shutil.rmtree(dir_path, ignore_errors=True)


@pytest.fixture
def mock_config():
    """Create a mock configuration object."""
    config = MagicMock()
    config.api.api_key = "test-key"
    config.api.model = "claude-sonnet-4-20250514"
    config.api.max_tokens = 4096
    config.safety.require_confirmation = True
    config.safety.blocked_patterns = ["rm -rf /"]
    config.safety.dangerous_patterns = ["rm -rf"]
    config.ui.show_technical_details = False
    config.ui.use_colors = True
    config.ui.show_commands = True
    config.logging.enabled = True
    config.logging.level = "info"
    config.session.save_history = True
    config.session.history_path = "~/.config/aios/history"
    config.session.max_history = 100
    return config


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")
    monkeypatch.setenv("HOME", str(Path.home()))


@pytest.fixture
def sample_files(temp_dir):
    """Create sample files for testing."""
    files = {}

    # Create text file
    text_file = Path(temp_dir) / "sample.txt"
    text_file.write_text("This is sample content\nLine 2\nLine 3")
    files["text"] = text_file

    # Create Python file
    py_file = Path(temp_dir) / "sample.py"
    py_file.write_text("def hello():\n    print('Hello')\n")
    files["python"] = py_file

    # Create subdirectory with files
    subdir = Path(temp_dir) / "subdir"
    subdir.mkdir()
    (subdir / "nested.txt").write_text("Nested content")
    files["subdir"] = subdir

    # Create hidden file
    hidden = Path(temp_dir) / ".hidden"
    hidden.write_text("Hidden content")
    files["hidden"] = hidden

    return files


@pytest.fixture
def isolated_config(temp_dir, monkeypatch):
    """Set up isolated configuration for testing."""
    config_dir = Path(temp_dir) / ".config" / "aios"
    config_dir.mkdir(parents=True)

    history_dir = config_dir / "history"
    history_dir.mkdir()

    monkeypatch.setenv("HOME", temp_dir)

    return config_dir


# Markers for slow tests
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
