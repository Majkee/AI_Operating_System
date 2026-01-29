"""Tests for StreamingDisplay and 'show' command."""

from collections import deque
from unittest.mock import MagicMock, patch

import pytest

from aios.ui.terminal import (
    StreamingDisplay,
    get_last_streaming_output,
    clear_last_streaming_output,
)


class TestStreamingDisplay:
    """Tests for the StreamingDisplay class."""

    def test_init_defaults(self):
        """Test default initialization."""
        console = MagicMock()
        display = StreamingDisplay(console, "Testing")

        assert display._description == "Testing"
        assert display._max_lines == 200
        assert display._total_lines == 0
        assert len(display._lines) == 0

    def test_init_custom_max_lines(self):
        """Test custom max_lines setting."""
        console = MagicMock()
        display = StreamingDisplay(console, "Testing", max_lines=50)

        assert display._max_lines == 50

    def test_add_line_increments_count(self):
        """Test that add_line increments the line counter."""
        console = MagicMock()
        display = StreamingDisplay(console, "Testing")
        display._progress = MagicMock()
        display._task_id = 0

        display.add_line("line 1")
        assert display._total_lines == 1

        display.add_line("line 2")
        assert display._total_lines == 2

    def test_add_line_stores_content(self):
        """Test that add_line stores the line content."""
        console = MagicMock()
        display = StreamingDisplay(console, "Testing")
        display._progress = MagicMock()
        display._task_id = 0

        display.add_line("hello world")
        assert "hello world" in display._lines

    def test_add_line_strips_newlines(self):
        """Test that add_line strips trailing newlines."""
        console = MagicMock()
        display = StreamingDisplay(console, "Testing")
        display._progress = MagicMock()
        display._task_id = 0

        display.add_line("hello\r\n")
        assert display._lines[-1] == "hello"

    def test_add_line_skips_empty(self):
        """Test that empty lines are not stored but counted."""
        console = MagicMock()
        display = StreamingDisplay(console, "Testing")
        display._progress = MagicMock()
        display._task_id = 0

        display.add_line("")
        assert display._total_lines == 1
        assert len(display._lines) == 0

    def test_add_line_updates_progress(self):
        """Test that add_line updates the progress display."""
        console = MagicMock()
        display = StreamingDisplay(console, "Testing")
        mock_progress = MagicMock()
        display._progress = mock_progress
        display._task_id = 0

        display.add_line("test line")

        mock_progress.update.assert_called_once_with(0, lines=1)

    def test_get_output_returns_joined_lines(self):
        """Test that get_output returns all lines joined."""
        console = MagicMock()
        display = StreamingDisplay(console, "Testing")
        display._progress = MagicMock()
        display._task_id = 0

        display.add_line("line 1")
        display.add_line("line 2")
        display.add_line("line 3")

        output = display.get_output()
        assert output == "line 1\nline 2\nline 3"

    def test_max_lines_limit(self):
        """Test that lines are limited to max_lines."""
        console = MagicMock()
        display = StreamingDisplay(console, "Testing", max_lines=3)
        display._progress = MagicMock()
        display._task_id = 0

        for i in range(10):
            display.add_line(f"line {i}")

        assert display._total_lines == 10
        assert len(display._lines) == 3
        assert "line 7" in display._lines
        assert "line 8" in display._lines
        assert "line 9" in display._lines

    def test_context_manager_enter(self):
        """Test context manager __enter__ starts progress."""
        console = MagicMock()
        display = StreamingDisplay(console, "Testing")

        with patch('aios.ui.terminal.Progress') as MockProgress:
            mock_progress = MagicMock()
            MockProgress.return_value = mock_progress
            mock_progress.__enter__ = MagicMock(return_value=mock_progress)
            mock_progress.__exit__ = MagicMock(return_value=False)
            mock_progress.add_task.return_value = 0

            result = display.__enter__()

            assert result is display
            MockProgress.assert_called_once()
            mock_progress.add_task.assert_called_once()

    def test_context_manager_exit_prints_completion(self):
        """Test context manager __exit__ prints completion message."""
        console = MagicMock()
        display = StreamingDisplay(console, "Testing")
        display._total_lines = 42
        display._progress = MagicMock()
        display._progress.__exit__ = MagicMock(return_value=False)

        display.__exit__(None, None, None)

        # Should print completion message
        console.print.assert_called()
        call_args = str(console.print.call_args_list)
        assert "42" in call_args
        assert "Completed" in call_args


class TestLastStreamingOutput:
    """Tests for the module-level output storage."""

    def setup_method(self):
        """Clear stored output before each test."""
        clear_last_streaming_output()

    def test_get_returns_none_initially(self):
        """Test that get returns None when nothing stored."""
        assert get_last_streaming_output() is None

    def test_clear_removes_stored_output(self):
        """Test that clear removes stored output."""
        # Store something via StreamingDisplay
        console = MagicMock()
        display = StreamingDisplay(console, "Test")
        display._lines = deque(["line 1", "line 2"])
        display._total_lines = 2
        display._store_last_output()

        assert get_last_streaming_output() is not None

        clear_last_streaming_output()

        assert get_last_streaming_output() is None

    def test_store_captures_description(self):
        """Test that stored output includes description."""
        console = MagicMock()
        display = StreamingDisplay(console, "Installing package")
        display._lines = deque(["output"])
        display._total_lines = 1
        display._store_last_output()

        output = get_last_streaming_output()
        assert output["description"] == "Installing package"

    def test_store_captures_lines(self):
        """Test that stored output includes lines."""
        console = MagicMock()
        display = StreamingDisplay(console, "Test")
        display._lines = deque(["line 1", "line 2", "line 3"])
        display._total_lines = 3
        display._store_last_output()

        output = get_last_streaming_output()
        assert output["lines"] == ["line 1", "line 2", "line 3"]

    def test_store_captures_total(self):
        """Test that stored output includes total line count."""
        console = MagicMock()
        display = StreamingDisplay(console, "Test")
        display._lines = deque(["line 1"])
        display._total_lines = 100  # More than stored
        display._store_last_output()

        output = get_last_streaming_output()
        assert output["total"] == 100


class TestShowCommand:
    """Tests for the 'show' command in shell."""

    def _make_shell(self, mock_config):
        """Create an AIOSShell with mocked dependencies."""
        with patch("aios.shell.get_config", return_value=mock_config), \
             patch("aios.shell.ensure_config_dirs"), \
             patch("aios.shell.SafetyGuard"), \
             patch("aios.shell.CommandExecutor"), \
             patch("aios.shell.InteractiveExecutor"), \
             patch("aios.shell.FileHandler"), \
             patch("aios.shell.SystemContextGatherer"), \
             patch("aios.shell.SessionManager"), \
             patch("aios.shell.AuditLogger"), \
             patch("aios.shell.get_skill_manager"), \
             patch("aios.shell.get_system_info_cache"), \
             patch("aios.shell.get_tool_result_cache"), \
             patch("aios.shell.get_rate_limiter"), \
             patch("aios.shell.configure_rate_limiter"), \
             patch("aios.shell.PromptSession"), \
             patch("aios.shell.FileHistory"):

            from aios.shell import AIOSShell
            shell = AIOSShell()
            shell.ui = MagicMock()
            shell.ui.console = MagicMock()
            return shell

    def test_show_no_output(self, mock_config):
        """Test 'show' when no output is stored."""
        clear_last_streaming_output()
        shell = self._make_shell(mock_config)

        shell._show_last_output()

        shell.ui.print_info.assert_called_once()
        assert "No recent" in str(shell.ui.print_info.call_args)

    def test_show_with_output(self, mock_config):
        """Test 'show' displays stored output."""
        # Store some output
        console = MagicMock()
        display = StreamingDisplay(console, "Test Command")
        display._lines = deque(["output line 1", "output line 2"])
        display._total_lines = 2
        display._store_last_output()

        shell = self._make_shell(mock_config)

        shell._show_last_output()

        # Should print a panel
        shell.ui.console.print.assert_called_once()

        # Output should be cleared after showing
        assert get_last_streaming_output() is None

    def test_show_command_recognized(self, mock_config):
        """Test 'show' command is recognized in input handler."""
        clear_last_streaming_output()
        shell = self._make_shell(mock_config)

        # Should return True (continue) and not send to Claude
        result = shell._handle_user_input("show")

        assert result is True
        shell.ui.print_info.assert_called()  # Shows "no output" message

    def test_slash_show_command_recognized(self, mock_config):
        """Test '/show' command is recognized."""
        clear_last_streaming_output()
        shell = self._make_shell(mock_config)

        result = shell._handle_user_input("/show")

        assert result is True


class TestShowInCommandRegistry:
    """Tests for 'show' in command registry."""

    def test_show_in_registry(self):
        """Test 'show' command is in registry."""
        from aios.ui.completions import COMMAND_REGISTRY

        names = [e["name"] for e in COMMAND_REGISTRY]
        assert "show" in names

    def test_show_has_alias(self):
        """Test 'show' has /show alias."""
        from aios.ui.completions import COMMAND_REGISTRY

        entry = next(e for e in COMMAND_REGISTRY if e["name"] == "show")
        assert "/show" in entry["aliases"]

    def test_show_has_help(self):
        """Test 'show' has help text."""
        from aios.ui.completions import COMMAND_REGISTRY

        entry = next(e for e in COMMAND_REGISTRY if e["name"] == "show")
        assert entry["help"]
        assert "output" in entry["help"].lower()
