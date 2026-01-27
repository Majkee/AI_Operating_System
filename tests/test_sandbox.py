"""Tests for command execution sandbox."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from aios.executor.sandbox import (
    CommandResult,
    CommandExecutor,
    InteractiveExecutor,
)

# Skip certain tests on Windows
IS_WINDOWS = sys.platform == "win32"
skip_on_windows = pytest.mark.skipif(IS_WINDOWS, reason="Test not compatible with Windows")


class TestCommandResult:
    """Test CommandResult dataclass."""

    def test_success_result(self):
        """Test successful command result."""
        result = CommandResult(
            success=True,
            stdout="output",
            stderr="",
            return_code=0
        )
        assert result.success is True
        assert result.output == "output"

    def test_failed_result(self):
        """Test failed command result."""
        result = CommandResult(
            success=False,
            stdout="",
            stderr="error message",
            return_code=1
        )
        assert result.success is False
        assert result.output == "error message"

    def test_output_prefers_stdout(self):
        """Test that output property prefers stdout."""
        result = CommandResult(
            success=True,
            stdout="stdout content",
            stderr="stderr content",
            return_code=0
        )
        assert result.output == "stdout content"

    def test_output_falls_back_to_stderr(self):
        """Test that output falls back to stderr when no stdout."""
        result = CommandResult(
            success=False,
            stdout="",
            stderr="error output",
            return_code=1
        )
        assert result.output == "error output"

    def test_user_friendly_timeout(self):
        """Test user-friendly message for timeout."""
        result = CommandResult(
            success=False,
            stdout="",
            stderr="",
            return_code=-1,
            timed_out=True
        )
        assert "too long" in result.to_user_friendly().lower()

    def test_user_friendly_success_with_output(self):
        """Test user-friendly message for successful command with output."""
        result = CommandResult(
            success=True,
            stdout="Command output here",
            stderr="",
            return_code=0
        )
        assert result.to_user_friendly() == "Command output here"

    def test_user_friendly_success_no_output(self):
        """Test user-friendly message for successful command without output."""
        result = CommandResult(
            success=True,
            stdout="",
            stderr="",
            return_code=0
        )
        assert result.to_user_friendly() == "Done!"

    def test_user_friendly_error_message(self):
        """Test user-friendly message uses error_message."""
        result = CommandResult(
            success=False,
            stdout="",
            stderr="",
            return_code=1,
            error_message="Custom error"
        )
        assert result.to_user_friendly() == "Custom error"

    def test_user_friendly_stderr(self):
        """Test user-friendly message uses stderr."""
        result = CommandResult(
            success=False,
            stdout="",
            stderr="Some error occurred",
            return_code=1
        )
        assert "Some error occurred" in result.to_user_friendly()

    def test_user_friendly_return_code(self):
        """Test user-friendly message shows return code as fallback."""
        result = CommandResult(
            success=False,
            stdout="",
            stderr="",
            return_code=42
        )
        assert "42" in result.to_user_friendly()


class TestCommandExecutor:
    """Test CommandExecutor class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        # Mock config
        self.mock_config = MagicMock()
        self.mock_config.ui.show_technical_details = False

    def teardown_method(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_execute_simple_command(self):
        """Test executing a simple command."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            result = executor.execute("echo 'hello world'")
            assert result.success is True
            assert "hello world" in result.stdout

    @skip_on_windows
    def test_execute_with_working_directory(self):
        """Test executing command in specific directory."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            result = executor.execute("pwd", working_directory=self.temp_dir)
            assert result.success is True
            # Normalize paths for comparison
            assert Path(result.stdout.strip()).resolve() == Path(self.temp_dir).resolve()

    def test_execute_nonexistent_directory(self):
        """Test executing in non-existent directory."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            result = executor.execute("ls", working_directory="/nonexistent/path")
            assert result.success is False
            assert "not found" in result.error_message.lower()

    def test_execute_failing_command(self):
        """Test executing a command that fails."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            result = executor.execute("exit 1")
            assert result.success is False
            assert result.return_code == 1

    def test_execute_with_stderr(self):
        """Test command that produces stderr."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            result = executor.execute("echo 'error' >&2")
            assert "error" in result.stderr

    @skip_on_windows
    def test_execute_with_timeout(self):
        """Test command timeout handling."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            # Command that would run forever
            result = executor.execute("sleep 60", timeout=1)
            assert result.success is False
            assert result.timed_out is True

    def test_execute_respects_max_timeout(self):
        """Test that timeout is capped at MAX_TIMEOUT."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            # Request very long timeout
            result = executor.execute("echo test", timeout=9999)
            # Should succeed (command is fast)
            assert result.success is True

    @skip_on_windows
    def test_execute_with_env(self):
        """Test command with custom environment."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            result = executor.execute(
                "echo $MY_VAR",
                env={"MY_VAR": "custom_value"}
            )
            assert result.success is True
            assert "custom_value" in result.stdout

    @skip_on_windows
    def test_check_command_exists_true(self):
        """Test checking for existing command."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            assert executor.check_command_exists("echo") is True

    @skip_on_windows
    def test_check_command_exists_false(self):
        """Test checking for non-existing command."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            assert executor.check_command_exists("nonexistent_command_xyz") is False

    def test_execute_multiline_output(self):
        """Test command with multiline output."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            result = executor.execute("echo -e 'line1\\nline2\\nline3'")
            assert result.success is True
            assert "line1" in result.stdout
            assert "line2" in result.stdout
            assert "line3" in result.stdout

    @skip_on_windows
    def test_execute_special_characters(self):
        """Test command with special characters."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            result = executor.execute("echo 'test & special | chars'")
            assert result.success is True
            assert "special" in result.stdout

    def test_execute_creates_file(self):
        """Test command that creates a file."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            test_file = Path(self.temp_dir) / "test.txt"
            result = executor.execute(
                f"echo 'content' > {test_file}",
                working_directory=self.temp_dir
            )
            assert result.success is True
            assert test_file.exists()

    def test_default_timeout(self):
        """Test that default timeout is applied."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            assert executor.DEFAULT_TIMEOUT == 30

    def test_max_timeout(self):
        """Test max timeout constant."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = CommandExecutor()
            assert executor.MAX_TIMEOUT == 3600


class TestInteractiveExecutor:
    """Test InteractiveExecutor class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_config = MagicMock()

    def test_execute_streaming_simple(self):
        """Test streaming execution."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = InteractiveExecutor()
            lines_received = []

            def callback(line):
                lines_received.append(line)

            result = executor.execute_streaming(
                "echo -e 'line1\\nline2'",
                on_output=callback
            )
            assert result.success is True
            assert len(lines_received) >= 1

    def test_execute_streaming_no_callback(self):
        """Test streaming execution without callback."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = InteractiveExecutor()
            result = executor.execute_streaming("echo test")
            assert result.success is True
            assert "test" in result.stdout

    @skip_on_windows
    def test_execute_streaming_timeout(self):
        """Test streaming execution timeout."""
        with patch("aios.executor.sandbox.get_config", return_value=self.mock_config):
            executor = InteractiveExecutor()
            result = executor.execute_streaming("sleep 60", timeout=1)
            assert result.success is False
            assert result.timed_out is True
