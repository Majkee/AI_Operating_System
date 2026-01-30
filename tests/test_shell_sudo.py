"""Tests for sudo, timeout, and streaming features in CommandHandler."""

from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass
from typing import Optional

import pytest

from aios.claude.tools import ToolResult
from aios.executor.sandbox import CommandResult
from aios.tasks import TaskManager


# ---------------------------------------------------------------------------
# Helpers — lightweight stand-ins so we don't need a full AIOSShell
# ---------------------------------------------------------------------------

def _make_command_handler(mock_config):
    """
    Build a CommandHandler with mocked dependencies for testing.
    """
    from aios.safety.guardrails import SafetyGuard, SafetyCheck, RiskLevel
    from aios.safety.audit import AuditLogger, ActionType
    from aios.ui.terminal import TerminalUI
    from aios.ui.prompts import ConfirmationPrompt
    from aios.handlers import CommandHandler

    # Provide a real SafetyGuard (compiled patterns are needed)
    with patch("aios.safety.guardrails.get_config", return_value=mock_config):
        safety = SafetyGuard()

    ui = MagicMock(spec=TerminalUI)
    prompts = MagicMock(spec=ConfirmationPrompt)
    audit = MagicMock(spec=AuditLogger)
    executor = MagicMock()
    executor.DEFAULT_TIMEOUT = 30
    task_manager = TaskManager()

    handler = CommandHandler(
        executor=executor,
        safety=safety,
        audit=audit,
        ui=ui,
        prompts=prompts,
        task_manager=task_manager,
    )

    # Expose mocks for assertions
    handler._mock_executor = executor
    handler._mock_ui = ui
    handler._mock_prompts = prompts
    handler._mock_audit = audit

    return handler


def _ok_result(**kwargs):
    """Return a successful CommandResult."""
    defaults = dict(success=True, stdout="ok", stderr="", return_code=0)
    defaults.update(kwargs)
    return CommandResult(**defaults)


def _timeout_result(**kwargs):
    """Return a timed-out CommandResult."""
    defaults = dict(success=False, stdout="partial", stderr="", return_code=-1, timed_out=True)
    defaults.update(kwargs)
    return CommandResult(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSudoPrepend:
    """use_sudo flag should prepend 'sudo ' to the command."""

    def test_use_sudo_prepends_sudo(self, mock_config):
        handler = _make_command_handler(mock_config)
        handler._mock_executor.execute.return_value = _ok_result()

        params = {
            "command": "apt-get update",
            "explanation": "Updating packages",
            "use_sudo": True,
        }
        result = handler.handle_run_command(params)

        # executor.execute should have received the sudo-prefixed command
        call_args = handler._mock_executor.execute.call_args
        actual_cmd = call_args[0][0] if call_args[0] else call_args[1].get("command", "")
        # If streaming was not used, the command goes through executor.execute
        # The command string should start with 'sudo '
        assert actual_cmd.startswith("sudo "), f"Expected sudo prefix, got: {actual_cmd}"

    def test_use_sudo_no_double_prefix(self, mock_config):
        handler = _make_command_handler(mock_config)
        handler._mock_executor.execute.return_value = _ok_result()

        params = {
            "command": "sudo apt-get update",
            "explanation": "Updating packages",
            "use_sudo": True,
        }
        result = handler.handle_run_command(params)

        call_args = handler._mock_executor.execute.call_args
        actual_cmd = call_args[0][0] if call_args[0] else call_args[1].get("command", "")
        # Should NOT have double sudo
        assert not actual_cmd.startswith("sudo sudo"), f"Double sudo prefix: {actual_cmd}"
        assert actual_cmd.startswith("sudo "), f"Expected single sudo prefix, got: {actual_cmd}"

    def test_no_sudo_by_default(self, mock_config):
        handler = _make_command_handler(mock_config)
        handler._mock_executor.execute.return_value = _ok_result()

        params = {
            "command": "ls -la",
            "explanation": "Listing files",
        }
        result = handler.handle_run_command(params)

        call_args = handler._mock_executor.execute.call_args
        actual_cmd = call_args[0][0] if call_args[0] else call_args[1].get("command", "")
        assert actual_cmd == "ls -la"


class TestCustomTimeout:
    """Custom timeout values should reach the executor."""

    def test_custom_timeout_passed(self, mock_config):
        handler = _make_command_handler(mock_config)
        handler._mock_executor.execute.return_value = _ok_result()

        params = {
            "command": "wget http://example.com/big.tar.gz",
            "explanation": "Downloading file",
            "timeout": 1800,
        }
        result = handler.handle_run_command(params)

        call_args = handler._mock_executor.execute.call_args
        assert call_args[1].get("timeout") == 1800 or (
            len(call_args[0]) > 2 and call_args[0][2] == 1800
        )

    def test_timeout_info_shown_when_over_60(self, mock_config):
        handler = _make_command_handler(mock_config)
        handler._mock_executor.execute.return_value = _ok_result()

        params = {
            "command": "make -j4",
            "explanation": "Compiling",
            "timeout": 600,
        }
        handler.handle_run_command(params)

        # Should have printed an info message about the timeout
        handler._mock_ui.print_info.assert_called()
        info_calls = [str(c) for c in handler._mock_ui.print_info.call_args_list]
        assert any("10 minute" in c for c in info_calls), f"Expected timeout info, got: {info_calls}"


class TestLongRunningStreaming:
    """long_running flag should delegate to the streaming executor."""

    def test_long_running_uses_streaming(self, mock_config):
        handler = _make_command_handler(mock_config)

        # Make the streaming display context manager work
        mock_display = MagicMock()
        mock_display.__enter__ = MagicMock(return_value=mock_display)
        mock_display.__exit__ = MagicMock(return_value=False)
        handler._mock_ui.print_streaming_output.return_value = mock_display

        # Mock Popen so no real process is spawned
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.poll.return_value = 0
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0

        import subprocess as _sp
        with patch.object(_sp, "Popen", return_value=mock_proc):
            params = {
                "command": "steamcmd +login anonymous +quit",
                "explanation": "Installing game server",
                "timeout": 3600,
                "long_running": True,
            }
            result = handler.handle_run_command(params)

        # Streaming display should have been used, not the standard executor
        handler._mock_ui.print_streaming_output.assert_called_once()
        handler._mock_executor.execute.assert_not_called()

    def test_non_long_running_uses_standard(self, mock_config):
        handler = _make_command_handler(mock_config)
        handler._mock_executor.execute.return_value = _ok_result()

        params = {
            "command": "echo hello",
            "explanation": "Test",
        }
        result = handler.handle_run_command(params)

        handler._mock_executor.execute.assert_called_once()


class TestTimeoutMessage:
    """Timeout should produce a user-friendly message."""

    def test_timeout_message(self, mock_config):
        handler = _make_command_handler(mock_config)
        handler._mock_executor.execute.return_value = _timeout_result()

        params = {
            "command": "sleep 999",
            "explanation": "Sleeping",
            "timeout": 120,
        }
        result = handler.handle_run_command(params)

        assert not result.success
        assert "timed out" in result.user_friendly_message.lower()
        assert "120" in result.user_friendly_message


class TestExecutorConfig:
    """ExecutorConfig should be loadable and have correct defaults."""

    def test_executor_config_defaults(self):
        from aios.config import ExecutorConfig
        cfg = ExecutorConfig()
        assert cfg.default_timeout == 30
        assert cfg.max_timeout == 3600

    def test_executor_config_in_aios_config(self):
        from aios.config import AIOSConfig, ExecutorConfig
        config = AIOSConfig()
        assert isinstance(config.executor, ExecutorConfig)
        assert config.executor.default_timeout == 30
        assert config.executor.max_timeout == 3600


class TestToolSchema:
    """Tool schema should include the new parameters."""

    def test_run_command_has_timeout(self):
        from aios.claude.tools import BUILTIN_TOOLS
        run_cmd = next(t for t in BUILTIN_TOOLS if t["name"] == "run_command")
        props = run_cmd["input_schema"]["properties"]
        assert "timeout" in props
        assert props["timeout"]["type"] == "integer"

    def test_run_command_has_use_sudo(self):
        from aios.claude.tools import BUILTIN_TOOLS
        run_cmd = next(t for t in BUILTIN_TOOLS if t["name"] == "run_command")
        props = run_cmd["input_schema"]["properties"]
        assert "use_sudo" in props
        assert props["use_sudo"]["type"] == "boolean"

    def test_run_command_has_long_running(self):
        from aios.claude.tools import BUILTIN_TOOLS
        run_cmd = next(t for t in BUILTIN_TOOLS if t["name"] == "run_command")
        props = run_cmd["input_schema"]["properties"]
        assert "long_running" in props
        assert props["long_running"]["type"] == "boolean"

    def test_new_params_not_required(self):
        from aios.claude.tools import BUILTIN_TOOLS
        run_cmd = next(t for t in BUILTIN_TOOLS if t["name"] == "run_command")
        required = run_cmd["input_schema"]["required"]
        assert "timeout" not in required
        assert "use_sudo" not in required
        assert "long_running" not in required


class TestSafetyGuardSudo:
    """Safety guardrails should recognise the sudo pattern as moderate."""

    def test_sudo_detected_as_moderate(self, mock_config):
        with patch("aios.safety.guardrails.get_config", return_value=mock_config):
            from aios.safety.guardrails import SafetyGuard, RiskLevel
            guard = SafetyGuard()

        check = guard.check_command("sudo apt-get update")
        assert check.is_allowed
        assert check.risk_level == RiskLevel.MODERATE


class TestSystemPrompt:
    """System prompt should contain the new guidance sections."""

    def test_prompt_mentions_sudo(self):
        from aios.prompts import get_prompt_manager, reset_prompt_manager
        reset_prompt_manager()
        prompt = get_prompt_manager().build_prompt()
        assert "use_sudo" in prompt
        assert "passwordless sudo" in prompt

    def test_prompt_mentions_timeout(self):
        from aios.prompts import get_prompt_manager, reset_prompt_manager
        reset_prompt_manager()
        prompt = get_prompt_manager().build_prompt()
        assert "timeout" in prompt.lower()
        assert "3600" in prompt

    def test_prompt_mentions_long_running(self):
        from aios.prompts import get_prompt_manager, reset_prompt_manager
        reset_prompt_manager()
        prompt = get_prompt_manager().build_prompt()
        assert "long_running" in prompt
