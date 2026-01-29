"""Tests for multi-step progress display."""

from unittest.mock import MagicMock, patch

import pytest

from aios.ui.terminal import MultiStepProgress, TerminalUI, TrackedMultiStepProgress


class TestMultiStepProgress:
    """Tests for the MultiStepProgress class."""

    def test_single_step_no_display(self):
        """Single-step operations don't show progress."""
        console = MagicMock()
        progress = MultiStepProgress(console, total=1)

        with progress:
            progress.update(1, "Doing something")
            progress.step_complete()

        # No progress bar for single steps
        assert progress._progress is None

    def test_multi_step_shows_progress(self):
        """Multi-step operations show progress."""
        console = MagicMock()
        progress = MultiStepProgress(console, total=3)

        # Mock the Progress class to avoid terminal output
        with patch('aios.ui.terminal.Progress') as MockProgress:
            mock_progress = MagicMock()
            MockProgress.return_value = mock_progress
            mock_progress.__enter__ = MagicMock(return_value=mock_progress)
            mock_progress.__exit__ = MagicMock(return_value=False)
            mock_progress.add_task.return_value = 0

            with progress:
                progress.update(1, "Step one")
                progress.step_complete()
                progress.update(2, "Step two")
                progress.step_complete()
                progress.update(3, "Step three")
                progress.step_complete()

            # Verify Progress was created for multi-step
            MockProgress.assert_called_once()

            # Verify update was called with step info in description
            update_calls = mock_progress.update.call_args_list
            assert any("Step 1/3" in str(call) for call in update_calls)

    def test_update_tracks_current_step(self):
        """Update method tracks current step number."""
        console = MagicMock()
        progress = MultiStepProgress(console, total=1)

        progress.update(1, "Test step")

        assert progress._current == 1
        assert progress._description == "Test step"

    def test_completion_message(self):
        """Completion message shows total operations."""
        console = MagicMock()
        progress = MultiStepProgress(console, total=5)

        with patch('aios.ui.terminal.Progress') as MockProgress:
            mock_progress = MagicMock()
            MockProgress.return_value = mock_progress
            mock_progress.__enter__ = MagicMock(return_value=mock_progress)
            mock_progress.__exit__ = MagicMock(return_value=False)
            mock_progress.add_task.return_value = 0

            with progress:
                for i in range(1, 6):
                    progress.update(i, f"Step {i}")
                    progress.step_complete()

        # Check completion message was printed
        console.print.assert_called()
        call_args = str(console.print.call_args)
        assert "5" in call_args
        assert "Completed" in call_args


class TestTerminalUIProgressFactory:
    """Tests for TerminalUI.multi_step_progress factory method."""

    def test_factory_creates_progress(self):
        """Factory method creates TrackedMultiStepProgress wrapping MultiStepProgress."""
        with patch('aios.ui.terminal.get_config') as mock_config:
            mock_config.return_value.ui.use_colors = True
            mock_config.return_value.ui.show_technical_details = False
            mock_config.return_value.ui.show_commands = False

            ui = TerminalUI()
            tracked = ui.multi_step_progress(total=3)

            assert isinstance(tracked, TrackedMultiStepProgress)
            assert isinstance(tracked._progress, MultiStepProgress)
            assert tracked._progress._total == 3


class TestShellToolDescriptions:
    """Tests for tool call description generation."""

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
            return shell

    def test_run_command_description(self, mock_config):
        """run_command tool generates meaningful description."""
        shell = self._make_shell(mock_config)

        desc = shell._get_tool_description("run_command", {"command": "ls -la /home"})
        assert "Running:" in desc
        assert "ls -la" in desc

    def test_read_file_description(self, mock_config):
        """read_file tool shows filename."""
        shell = self._make_shell(mock_config)

        desc = shell._get_tool_description("read_file", {"path": "/home/user/config.yaml"})
        assert "Reading:" in desc
        assert "config.yaml" in desc

    def test_write_file_description(self, mock_config):
        """write_file tool shows filename."""
        shell = self._make_shell(mock_config)

        desc = shell._get_tool_description("write_file", {"path": "/tmp/output.txt"})
        assert "Writing:" in desc
        assert "output.txt" in desc

    def test_search_files_description(self, mock_config):
        """search_files tool shows query."""
        shell = self._make_shell(mock_config)

        desc = shell._get_tool_description("search_files", {"query": "*.pdf"})
        assert "Searching" in desc
        assert "*.pdf" in desc

    def test_unknown_tool_fallback(self, mock_config):
        """Unknown tools get nice fallback description."""
        shell = self._make_shell(mock_config)

        desc = shell._get_tool_description("some_custom_tool", {})
        assert desc == "Some Custom Tool"

    def test_long_command_truncated(self, mock_config):
        """Long commands are truncated in description."""
        shell = self._make_shell(mock_config)

        long_cmd = "find /home -name '*.txt' -exec grep -l 'pattern' {} \\; | sort | uniq"
        desc = shell._get_tool_description("run_command", {"command": long_cmd})
        assert len(desc) < len(long_cmd) + 20  # Allow for "Running: " prefix


class TestProcessToolCallsWithProgress:
    """Integration tests for tool processing with progress display."""

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
            return shell

    def test_single_tool_call_no_progress_message(self, mock_config):
        """Single tool call doesn't show completion message."""
        shell = self._make_shell(mock_config)
        shell.tool_handler.execute = MagicMock(return_value=MagicMock(
            success=True, output="ok", error=None, user_friendly_message=""
        ))

        # Mock the progress to avoid actual display
        mock_progress = MagicMock()
        mock_progress.__enter__ = MagicMock(return_value=mock_progress)
        mock_progress.__exit__ = MagicMock(return_value=False)
        shell.ui.multi_step_progress = MagicMock(return_value=mock_progress)

        tool_calls = [{"id": "1", "name": "read_file", "input": {"path": "/tmp/test"}}]
        shell._process_tool_calls(tool_calls)

        # Progress created with total=1
        shell.ui.multi_step_progress.assert_called_with(1)

    def test_multiple_tool_calls_shows_progress(self, mock_config):
        """Multiple tool calls show progress updates."""
        shell = self._make_shell(mock_config)
        shell.tool_handler.execute = MagicMock(return_value=MagicMock(
            success=True, output="ok", error=None, user_friendly_message=""
        ))

        mock_progress = MagicMock()
        mock_progress.__enter__ = MagicMock(return_value=mock_progress)
        mock_progress.__exit__ = MagicMock(return_value=False)
        shell.ui.multi_step_progress = MagicMock(return_value=mock_progress)

        tool_calls = [
            {"id": "1", "name": "read_file", "input": {"path": "/tmp/a"}},
            {"id": "2", "name": "read_file", "input": {"path": "/tmp/b"}},
            {"id": "3", "name": "write_file", "input": {"path": "/tmp/c"}},
        ]
        shell._process_tool_calls(tool_calls)

        # Progress created with total=3
        shell.ui.multi_step_progress.assert_called_with(3)

        # Update called for each step
        assert mock_progress.update.call_count == 3
        assert mock_progress.step_complete.call_count == 3
