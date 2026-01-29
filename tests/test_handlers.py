"""Tests for handler modules - command, file, system, and app handlers."""

import platform
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from aios.claude.tools import ToolResult
from aios.executor.sandbox import CommandResult
from aios.executor.files import FileResult, SearchResult, FileInfo
from aios.tasks import TaskManager


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def mock_executor():
    """Create a mock command executor."""
    executor = MagicMock()
    executor.DEFAULT_TIMEOUT = 30
    executor.execute.return_value = CommandResult(
        success=True, stdout="output", stderr="", return_code=0
    )
    executor.check_command_exists.return_value = True
    return executor


@pytest.fixture
def mock_safety():
    """Create a mock safety guard."""
    from aios.safety.guardrails import SafetyCheck, RiskLevel

    safety = MagicMock()
    # Default: command is allowed
    safety.check_command.return_value = SafetyCheck(
        is_allowed=True,
        requires_confirmation=False,
        risk_level=RiskLevel.SAFE,
        user_warning=None,
        safe_alternative=None,
    )
    safety.check_file_write.return_value = SafetyCheck(
        is_allowed=True,
        requires_confirmation=False,
        risk_level=RiskLevel.SAFE,
    )
    safety.check_package_operation.return_value = SafetyCheck(
        is_allowed=True,
        requires_confirmation=True,
        risk_level=RiskLevel.MODERATE,
    )
    return safety


@pytest.fixture
def mock_audit():
    """Create a mock audit logger."""
    return MagicMock()


@pytest.fixture
def mock_ui():
    """Create a mock terminal UI."""
    ui = MagicMock()
    return ui


@pytest.fixture
def mock_prompts():
    """Create a mock confirmation prompts."""
    from aios.ui.prompts import ConfirmationResult

    prompts = MagicMock()
    prompts.confirm.return_value = ConfirmationResult.YES
    prompts.confirm_dangerous_action.return_value = ConfirmationResult.YES
    prompts.ask_clarification.return_value = "user response"
    return prompts


@pytest.fixture
def mock_files():
    """Create a mock file handler."""
    files = MagicMock()
    files.read_file.return_value = FileResult(
        success=True, message="Read successful", data="file content"
    )
    files.write_file.return_value = FileResult(
        success=True, message="Written successfully"
    )
    files.search_files.return_value = SearchResult(files=[], truncated=False, total_count=0)
    files.list_directory.return_value = SearchResult(files=[], truncated=False, total_count=0)
    return files


@pytest.fixture
def mock_system():
    """Create a mock system context gatherer."""
    from aios.context.system import SystemContext

    system = MagicMock()
    context = MagicMock(spec=SystemContext)
    context.to_summary.return_value = "System summary"
    context.disk_info = []
    context.memory_info = None
    context.cpu_count = 4
    context.cpu_percent = 25.0
    system.get_context.return_value = context
    system.get_running_processes.return_value = []
    return system


@pytest.fixture
def command_handler(mock_executor, mock_safety, mock_audit, mock_ui, mock_prompts):
    """Create a command handler with mocked dependencies."""
    from aios.handlers import CommandHandler

    return CommandHandler(
        executor=mock_executor,
        safety=mock_safety,
        audit=mock_audit,
        ui=mock_ui,
        prompts=mock_prompts,
        task_manager=TaskManager(),
    )


@pytest.fixture
def file_handler(mock_files, mock_safety, mock_audit, mock_ui, mock_prompts):
    """Create a file handler with mocked dependencies."""
    from aios.handlers import FileToolHandler

    return FileToolHandler(
        files=mock_files,
        safety=mock_safety,
        audit=mock_audit,
        ui=mock_ui,
        prompts=mock_prompts,
    )


@pytest.fixture
def system_handler(mock_system, mock_audit, mock_ui):
    """Create a system handler with mocked dependencies."""
    from aios.handlers import SystemHandler

    return SystemHandler(
        system=mock_system,
        audit=mock_audit,
        ui=mock_ui,
    )


@pytest.fixture
def app_handler(mock_executor, mock_safety, mock_audit, mock_ui, mock_prompts):
    """Create an app handler with mocked dependencies."""
    from aios.handlers import AppHandler

    def mock_streaming(cmd, cwd, timeout, desc):
        return CommandResult(success=True, stdout="streaming output", stderr="", return_code=0)

    return AppHandler(
        executor=mock_executor,
        safety=mock_safety,
        audit=mock_audit,
        ui=mock_ui,
        prompts=mock_prompts,
        streaming_executor=mock_streaming,
    )


# ===========================================================================
# CommandHandler Tests
# ===========================================================================

class TestCommandHandler:
    """Tests for CommandHandler."""

    def test_simple_command_execution(self, command_handler, mock_executor):
        """Test basic command execution."""
        params = {"command": "echo hello", "explanation": "Test echo"}
        result = command_handler.handle_run_command(params)

        assert result.success is True
        mock_executor.execute.assert_called_once()

    def test_sudo_prepends_sudo(self, command_handler, mock_executor):
        """Test that use_sudo prepends sudo to command."""
        params = {
            "command": "apt-get update",
            "explanation": "Update packages",
            "use_sudo": True,
        }
        command_handler.handle_run_command(params)

        call_args = mock_executor.execute.call_args
        actual_cmd = call_args[0][0] if call_args[0] else call_args[1].get("command", "")
        assert actual_cmd.startswith("sudo ")

    def test_sudo_no_double_prefix(self, command_handler, mock_executor):
        """Test that use_sudo doesn't double-prefix sudo."""
        params = {
            "command": "sudo apt-get update",
            "explanation": "Update packages",
            "use_sudo": True,
        }
        command_handler.handle_run_command(params)

        call_args = mock_executor.execute.call_args
        actual_cmd = call_args[0][0] if call_args[0] else call_args[1].get("command", "")
        assert not actual_cmd.startswith("sudo sudo")

    def test_custom_timeout(self, command_handler, mock_executor):
        """Test that custom timeout is passed to executor."""
        params = {
            "command": "long-running-task",
            "explanation": "Long task",
            "timeout": 1800,
        }
        command_handler.handle_run_command(params)

        call_args = mock_executor.execute.call_args
        assert call_args[1].get("timeout") == 1800

    def test_blocked_command_rejected(self, command_handler, mock_safety):
        """Test that blocked commands are rejected."""
        from aios.safety.guardrails import SafetyCheck, RiskLevel

        mock_safety.check_command.return_value = SafetyCheck(
            is_allowed=False,
            requires_confirmation=False,
            risk_level=RiskLevel.FORBIDDEN,
            reason="Command is blocked",
            user_warning="This command is not allowed.",
        )

        params = {"command": "rm -rf /", "explanation": "Dangerous"}
        result = command_handler.handle_run_command(params)

        assert result.success is False
        assert "not allowed" in result.user_friendly_message.lower()

    def test_confirmation_required(self, command_handler, mock_safety, mock_prompts):
        """Test that dangerous commands require confirmation."""
        from aios.safety.guardrails import SafetyCheck, RiskLevel
        from aios.ui.prompts import ConfirmationResult

        mock_safety.check_command.return_value = SafetyCheck(
            is_allowed=True,
            requires_confirmation=True,
            risk_level=RiskLevel.DANGEROUS,
            user_warning="This is dangerous",
        )
        mock_prompts.confirm_dangerous_action.return_value = ConfirmationResult.NO

        params = {"command": "rm -rf ~/*", "explanation": "Delete all"}
        result = command_handler.handle_run_command(params)

        assert result.success is False
        mock_prompts.confirm_dangerous_action.assert_called_once()

    def test_background_task_created(self, command_handler):
        """Test that background=True creates a task."""
        params = {
            "command": "echo hello",
            "explanation": "Background task",
            "background": True,
        }
        result = command_handler.handle_run_command(params)

        assert result.success is True
        assert "background" in result.output.lower() or "Background" in result.output

    def test_long_running_uses_streaming(self, command_handler, mock_executor, mock_ui):
        """Test that long_running uses streaming display."""
        mock_display = MagicMock()
        mock_display.__enter__ = MagicMock(return_value=mock_display)
        mock_display.__exit__ = MagicMock(return_value=False)
        mock_ui.print_streaming_output.return_value = mock_display

        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.poll.return_value = 0
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0

        import subprocess
        with patch.object(subprocess, "Popen", return_value=mock_proc):
            params = {
                "command": "long-task",
                "explanation": "Long running",
                "long_running": True,
                "timeout": 3600,
            }
            command_handler.handle_run_command(params)

        mock_ui.print_streaming_output.assert_called_once()
        mock_executor.execute.assert_not_called()


# ===========================================================================
# FileToolHandler Tests
# ===========================================================================

class TestFileToolHandler:
    """Tests for FileToolHandler."""

    def test_read_file_success(self, file_handler, mock_files):
        """Test successful file read."""
        params = {"path": "/home/user/test.txt", "explanation": "Read test"}
        result = file_handler.handle_read_file(params)

        assert result.success is True
        assert result.output == "file content"
        mock_files.read_file.assert_called_once()

    def test_read_file_not_found(self, file_handler, mock_files):
        """Test file read when file doesn't exist."""
        mock_files.read_file.return_value = FileResult(
            success=False, message="", error="File not found"
        )

        params = {"path": "/nonexistent.txt", "explanation": "Read"}
        result = file_handler.handle_read_file(params)

        assert result.success is False
        assert result.error == "File not found"

    def test_read_file_permission_denied(self, file_handler, mock_files):
        """Test file read when permission is denied (path traversal protection)."""
        mock_files.read_file.side_effect = PermissionError(
            "Access denied: '/etc/passwd' is outside allowed locations."
        )

        params = {"path": "/etc/passwd", "explanation": "Read system file"}
        result = file_handler.handle_read_file(params)

        assert result.success is False
        assert "access denied" in result.user_friendly_message.lower()

    def test_write_file_success(self, file_handler, mock_files):
        """Test successful file write."""
        params = {
            "path": "/home/user/output.txt",
            "content": "new content",
            "explanation": "Write test",
        }
        result = file_handler.handle_write_file(params)

        assert result.success is True
        mock_files.write_file.assert_called_once()

    def test_write_file_confirmation_required(self, file_handler, mock_prompts):
        """Test that file write requests confirmation."""
        params = {
            "path": "/home/user/output.txt",
            "content": "new content",
            "requires_confirmation": True,
        }
        file_handler.handle_write_file(params)

        mock_prompts.confirm.assert_called()

    def test_write_file_cancelled(self, file_handler, mock_prompts, mock_files):
        """Test that cancelled write returns appropriate result."""
        from aios.ui.prompts import ConfirmationResult

        mock_prompts.confirm.return_value = ConfirmationResult.NO

        params = {"path": "/home/user/output.txt", "content": "new content"}
        result = file_handler.handle_write_file(params)

        assert result.success is False
        mock_files.write_file.assert_not_called()

    def test_write_file_permission_denied(self, file_handler, mock_files):
        """Test file write when permission is denied (path traversal protection)."""
        mock_files.write_file.side_effect = PermissionError(
            "Access denied: '/etc/hosts' is outside allowed locations."
        )

        params = {
            "path": "/etc/hosts",
            "content": "malicious content",
            "explanation": "Write system file",
        }
        result = file_handler.handle_write_file(params)

        assert result.success is False
        assert "access denied" in result.user_friendly_message.lower()

    def test_search_files_success(self, file_handler, mock_files):
        """Test successful file search."""
        from datetime import datetime

        mock_files.search_files.return_value = SearchResult(
            files=[
                FileInfo(
                    path=Path("/home/user/test.txt"),
                    name="test.txt",
                    is_directory=False,
                    size=100,
                    modified=datetime.now(),
                    permissions="rw-r--r--",
                    is_hidden=False,
                )
            ],
            truncated=False,
            total_count=1,
        )

        params = {"query": "test", "explanation": "Search"}
        result = file_handler.handle_search_files(params)

        assert result.success is True
        assert "test.txt" in result.output

    def test_search_files_no_results(self, file_handler, mock_files):
        """Test file search with no results."""
        params = {"query": "nonexistent", "explanation": "Search"}
        result = file_handler.handle_search_files(params)

        assert result.success is True
        assert "no files" in result.output.lower()

    def test_list_directory_success(self, file_handler, mock_files):
        """Test successful directory listing."""
        from datetime import datetime

        mock_files.list_directory.return_value = SearchResult(
            files=[
                FileInfo(
                    path=Path("/home/user/dir"),
                    name="dir",
                    is_directory=True,
                    size=0,
                    modified=datetime.now(),
                    permissions="rwxr-xr-x",
                    is_hidden=False,
                )
            ],
            truncated=False,
            total_count=1,
        )

        params = {"path": "/home/user", "explanation": "List"}
        result = file_handler.handle_list_directory(params)

        assert result.success is True

    def test_list_directory_empty(self, file_handler, mock_files):
        """Test listing empty directory."""
        params = {"path": "/home/user/empty", "explanation": "List"}
        result = file_handler.handle_list_directory(params)

        assert result.success is True
        assert "empty" in result.output.lower()


# ===========================================================================
# SystemHandler Tests
# ===========================================================================

class TestSystemHandler:
    """Tests for SystemHandler."""

    def test_general_system_info(self, system_handler, mock_system):
        """Test getting general system info."""
        params = {"info_type": "general", "explanation": "Get info"}
        result = system_handler.handle_system_info(params)

        assert result.success is True
        mock_system.get_context.assert_called_once()

    def test_disk_info(self, system_handler, mock_system):
        """Test getting disk info."""
        params = {"info_type": "disk", "explanation": "Get disk info"}
        result = system_handler.handle_system_info(params)

        assert result.success is True

    def test_memory_info(self, system_handler, mock_system):
        """Test getting memory info."""
        params = {"info_type": "memory", "explanation": "Get memory info"}
        result = system_handler.handle_system_info(params)

        assert result.success is True

    def test_cpu_info(self, system_handler, mock_system):
        """Test getting CPU info."""
        params = {"info_type": "cpu", "explanation": "Get CPU info"}
        result = system_handler.handle_system_info(params)

        assert result.success is True
        assert "cpu" in result.output.lower()

    def test_processes_info(self, system_handler, mock_system):
        """Test getting process info."""
        params = {"info_type": "processes", "explanation": "Get processes"}
        result = system_handler.handle_system_info(params)

        assert result.success is True
        mock_system.get_running_processes.assert_called_once()


# ===========================================================================
# AppHandler Tests
# ===========================================================================

class TestAppHandler:
    """Tests for AppHandler."""

    def test_install_package(self, app_handler, mock_prompts):
        """Test package installation."""
        params = {
            "action": "install",
            "package": "htop",
            "explanation": "Install htop",
        }
        result = app_handler.handle_manage_application(params)

        assert result.success is True
        mock_prompts.confirm.assert_called()

    def test_remove_package_confirmation(self, app_handler, mock_prompts):
        """Test that package removal asks for confirmation."""
        params = {
            "action": "remove",
            "package": "htop",
            "explanation": "Remove htop",
        }
        app_handler.handle_manage_application(params)

        mock_prompts.confirm.assert_called()
        # Remove should default to False
        call_args = mock_prompts.confirm.call_args
        assert call_args[1].get("default") is False

    def test_remove_package_cancelled(self, app_handler, mock_prompts, mock_executor):
        """Test that cancelled package removal doesn't execute."""
        from aios.ui.prompts import ConfirmationResult

        mock_prompts.confirm.return_value = ConfirmationResult.NO

        params = {
            "action": "remove",
            "package": "htop",
            "explanation": "Remove htop",
        }
        result = app_handler.handle_manage_application(params)

        assert result.success is False
        mock_executor.execute.assert_not_called()

    def test_search_package(self, app_handler, mock_executor):
        """Test package search."""
        params = {
            "action": "search",
            "package": "htop",
            "explanation": "Search for htop",
        }
        app_handler.handle_manage_application(params)

        mock_executor.execute.assert_called()
        call_args = mock_executor.execute.call_args
        assert "apt-cache search" in call_args[0][0]

    def test_blocked_package_operation(self, app_handler, mock_safety):
        """Test that blocked package operations are rejected."""
        from aios.safety.guardrails import SafetyCheck, RiskLevel

        mock_safety.check_package_operation.return_value = SafetyCheck(
            is_allowed=False,
            requires_confirmation=False,
            risk_level=RiskLevel.FORBIDDEN,
            user_warning="Cannot remove system packages",
        )

        params = {
            "action": "remove",
            "package": "systemd",
            "explanation": "Remove systemd",
        }
        result = app_handler.handle_manage_application(params)

        assert result.success is False

    def test_ask_clarification(self, app_handler, mock_prompts):
        """Test asking user for clarification."""
        params = {
            "question": "Which option?",
            "options": ["Option A", "Option B"],
        }
        result = app_handler.handle_ask_clarification(params)

        assert result.success is True
        assert result.output == "user response"
        mock_prompts.ask_clarification.assert_called_once()

    def test_ask_clarification_cancelled(self, app_handler, mock_prompts):
        """Test cancelled clarification."""
        mock_prompts.ask_clarification.return_value = None

        params = {"question": "Which option?", "options": []}
        result = app_handler.handle_ask_clarification(params)

        assert result.success is False

    def test_open_application(self, app_handler, mock_executor):
        """Test opening an application."""
        params = {
            "target": "/home/user/document.pdf",
            "explanation": "Open document",
        }
        result = app_handler.handle_open_application(params)

        assert result.success is True
        mock_executor.execute.assert_called()
        call_args = mock_executor.execute.call_args
        assert "xdg-open" in call_args[0][0]


# ===========================================================================
# Path Validation Tests (Integration with real FileHandler)
# ===========================================================================

class TestPathValidation:
    """Integration tests for path validation in FileHandler."""

    def test_home_directory_allowed(self, temp_dir):
        """Test that paths within home directory are allowed."""
        from aios.executor.files import FileHandler

        # Create a file in temp_dir which acts as home
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("test content")

        handler = FileHandler()
        handler.home = Path(temp_dir)

        # Should not raise
        safe_path = handler._ensure_safe_path(str(test_file))
        assert safe_path == test_file.resolve()

    def test_temp_directory_allowed(self):
        """Test that paths within temp directory are allowed."""
        from aios.executor.files import FileHandler
        import tempfile

        handler = FileHandler()

        # Create a temp file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            # Should not raise
            safe_path = handler._ensure_safe_path(temp_path)
            # Just verify it returns a path
            assert safe_path is not None
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_system_path_rejected(self, temp_dir):
        """Test that system paths are rejected."""
        from aios.executor.files import FileHandler

        handler = FileHandler()
        handler.home = Path(temp_dir)

        # System paths should be rejected
        system_paths = ["/etc/passwd", "/usr/bin/python", "/var/log/syslog"]
        if platform.system() == "Windows":
            system_paths = ["C:\\Windows\\System32\\config", "C:\\Program Files\\test"]

        for path in system_paths:
            with pytest.raises(PermissionError) as exc_info:
                handler._ensure_safe_path(path)
            assert "outside allowed locations" in str(exc_info.value)


# ===========================================================================
# Safe Expression Evaluator Tests
# ===========================================================================

class TestSafeExpressionEvaluator:
    """Tests for the safe expression evaluator in skills."""

    def test_simple_equality(self):
        """Test simple equality comparison."""
        from aios.skills import safe_eval_condition

        context = {"status": "success", "count": 5}

        assert safe_eval_condition("context.status == 'success'", context) is True
        assert safe_eval_condition("context.count == 5", context) is True
        assert safe_eval_condition("context.status == 'failed'", context) is False

    def test_numeric_comparisons(self):
        """Test numeric comparison operators."""
        from aios.skills import safe_eval_condition

        context = {"value": 10}

        assert safe_eval_condition("context.value > 5", context) is True
        assert safe_eval_condition("context.value < 20", context) is True
        assert safe_eval_condition("context.value >= 10", context) is True
        assert safe_eval_condition("context.value <= 10", context) is True
        assert safe_eval_condition("context.value > 10", context) is False

    def test_boolean_operators(self):
        """Test boolean operators (and, or, not)."""
        from aios.skills import safe_eval_condition

        context = {"a": True, "b": False, "x": 5}

        assert safe_eval_condition("context.a and context.x > 0", context) is True
        assert safe_eval_condition("context.a or context.b", context) is True
        assert safe_eval_condition("not context.b", context) is True
        assert safe_eval_condition("context.a and context.b", context) is False

    def test_membership_operators(self):
        """Test 'in' and 'not in' operators."""
        from aios.skills import safe_eval_condition

        context = {"status": "success", "items": [1, 2, 3]}

        assert safe_eval_condition("context.status in ['success', 'completed']", context) is True
        assert safe_eval_condition("context.status not in ['failed', 'error']", context) is True
        assert safe_eval_condition("2 in context.items", context) is True

    def test_forbidden_import_rejected(self):
        """Test that import attempts are rejected."""
        from aios.skills import safe_eval_condition, SafeExpressionError

        context = {}

        with pytest.raises(SafeExpressionError) as exc_info:
            safe_eval_condition("__import__('os').system('ls')", context)
        assert "forbidden" in str(exc_info.value).lower()

    def test_forbidden_eval_rejected(self):
        """Test that eval/exec attempts are rejected."""
        from aios.skills import safe_eval_condition, SafeExpressionError

        context = {}

        with pytest.raises(SafeExpressionError):
            safe_eval_condition("eval('1+1')", context)

        with pytest.raises(SafeExpressionError):
            safe_eval_condition("exec('x=1')", context)

    def test_forbidden_dunder_rejected(self):
        """Test that __dunder__ access is rejected."""
        from aios.skills import safe_eval_condition, SafeExpressionError

        context = {}

        with pytest.raises(SafeExpressionError):
            safe_eval_condition("context.__class__.__bases__", context)

    def test_function_calls_rejected(self):
        """Test that function calls are rejected."""
        from aios.skills import safe_eval_condition, SafeExpressionError

        context = {"value": "test"}

        with pytest.raises(SafeExpressionError):
            safe_eval_condition("len(context.value)", context)

    def test_arbitrary_variable_rejected(self):
        """Test that only 'context' variable is allowed."""
        from aios.skills import safe_eval_condition, SafeExpressionError

        context = {}

        # os.system('ls') is rejected because it's a function call
        # and also because 'os' is not 'context'
        with pytest.raises(SafeExpressionError):
            safe_eval_condition("os.system('ls')", context)

        # Test direct variable access rejection
        with pytest.raises(SafeExpressionError) as exc_info:
            safe_eval_condition("unknown_var == 5", context)
        assert "only 'context' is allowed" in str(exc_info.value).lower()

    def test_missing_key_returns_none(self):
        """Test that missing keys return None (falsy)."""
        from aios.skills import safe_eval_condition

        context = {}

        # Missing key should return None which is falsy
        assert safe_eval_condition("context.missing == None", context) is True
        assert safe_eval_condition("not context.missing", context) is True

    def test_invalid_syntax_rejected(self):
        """Test that invalid syntax raises error."""
        from aios.skills import safe_eval_condition, SafeExpressionError

        context = {}

        with pytest.raises(SafeExpressionError) as exc_info:
            safe_eval_condition("context.value ==", context)
        assert "syntax" in str(exc_info.value).lower()
