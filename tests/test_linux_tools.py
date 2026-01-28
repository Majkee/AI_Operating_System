"""
Tests for Linux-specific tool handlers.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from aios.handlers.linux import LinuxToolsHandler
from aios.claude.tools import ToolResult
from aios.executor.sandbox import CommandResult
from aios.ui.prompts import ConfirmationResult


@pytest.fixture
def linux_handler():
    """Create a LinuxToolsHandler with mocked dependencies."""
    executor = Mock()
    safety = Mock()
    audit = Mock()
    ui = Mock()
    prompts = Mock()

    handler = LinuxToolsHandler(
        executor=executor,
        safety=safety,
        audit=audit,
        ui=ui,
        prompts=prompts,
    )
    return handler


class TestManageService:
    """Tests for manage_service tool."""

    def test_service_status(self, linux_handler):
        """Test checking service status."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="● nginx.service - A high performance web server\n   Active: active (running)",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_manage_service({
            "action": "status",
            "service": "nginx",
            "explanation": "Checking nginx status"
        })

        assert result.success is True
        assert "running" in result.user_friendly_message.lower()
        linux_handler.executor.execute.assert_called_once()

    def test_service_is_active(self, linux_handler):
        """Test is-active check."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="active",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_manage_service({
            "action": "is-active",
            "service": "ssh",
            "explanation": "Checking if SSH is running"
        })

        assert result.success is True
        assert "running" in result.user_friendly_message.lower()

    def test_service_start_requires_confirmation(self, linux_handler):
        """Test that starting a service requires confirmation."""
        linux_handler.prompts.confirm_dangerous_action.return_value = ConfirmationResult.NO

        result = linux_handler.handle_manage_service({
            "action": "start",
            "service": "docker",
            "explanation": "Starting Docker"
        })

        assert result.success is False
        linux_handler.prompts.confirm_dangerous_action.assert_called_once()

    def test_invalid_service_name(self, linux_handler):
        """Test that invalid service names are rejected."""
        result = linux_handler.handle_manage_service({
            "action": "status",
            "service": "nginx; rm -rf /",
            "explanation": "Malicious attempt"
        })

        assert result.success is False
        assert "valid" in result.user_friendly_message.lower()

    def test_missing_service_name(self, linux_handler):
        """Test that missing service name is handled."""
        result = linux_handler.handle_manage_service({
            "action": "status",
            "explanation": "No service specified"
        })

        assert result.success is False


class TestManageProcess:
    """Tests for manage_process tool."""

    def test_list_processes(self, linux_handler):
        """Test listing processes."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="USER PID %CPU %MEM\nroot 1 0.1 0.2",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_manage_process({
            "action": "list",
            "sort_by": "cpu",
            "explanation": "Listing top processes"
        })

        assert result.success is True
        linux_handler.executor.execute.assert_called_once()

    def test_find_process(self, linux_handler):
        """Test finding processes by name."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="1234 /usr/bin/python3 script.py",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_manage_process({
            "action": "find",
            "name": "python",
            "explanation": "Finding Python processes"
        })

        assert result.success is True

    def test_kill_requires_confirmation(self, linux_handler):
        """Test that killing a process requires confirmation."""
        linux_handler.prompts.confirm_dangerous_action.return_value = ConfirmationResult.NO

        result = linux_handler.handle_manage_process({
            "action": "kill",
            "pid": 1234,
            "explanation": "Killing process"
        })

        assert result.success is False

    def test_kill_needs_pid_or_name(self, linux_handler):
        """Test that kill requires PID or name."""
        result = linux_handler.handle_manage_process({
            "action": "kill",
            "explanation": "Killing unknown process"
        })

        assert result.success is False


class TestNetworkDiagnostics:
    """Tests for network_diagnostics tool."""

    def test_network_status(self, linux_handler):
        """Test showing network status."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="lo UNKNOWN 127.0.0.1/8\neth0 UP 192.168.1.100/24",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_network_diagnostics({
            "action": "status",
            "explanation": "Checking network interfaces"
        })

        assert result.success is True

    def test_ping(self, linux_handler):
        """Test ping operation."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="PING google.com (142.250.72.14): 56 data bytes\n64 bytes: time=12.5 ms",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_network_diagnostics({
            "action": "ping",
            "host": "google.com",
            "count": 4,
            "explanation": "Testing connectivity"
        })

        assert result.success is True
        assert "successfully" in result.user_friendly_message.lower()

    def test_ping_invalid_host(self, linux_handler):
        """Test ping with invalid host."""
        result = linux_handler.handle_network_diagnostics({
            "action": "ping",
            "host": "google.com; rm -rf /",
            "explanation": "Malicious attempt"
        })

        assert result.success is False

    def test_check_port(self, linux_handler):
        """Test port check."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="Port 80 is OPEN",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_network_diagnostics({
            "action": "check_port",
            "host": "localhost",
            "port": 80,
            "explanation": "Checking if port 80 is open"
        })

        assert result.success is True
        assert "open" in result.user_friendly_message.lower()


class TestViewLogs:
    """Tests for view_logs tool."""

    def test_view_system_logs(self, linux_handler):
        """Test viewing system logs."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="Jan 15 10:00:00 host systemd[1]: Started Service.",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_view_logs({
            "log_type": "system",
            "lines": 50,
            "explanation": "Viewing system logs"
        })

        assert result.success is True

    def test_view_kernel_logs(self, linux_handler):
        """Test viewing kernel logs."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="[    0.000000] Linux version 5.15.0",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_view_logs({
            "log_type": "kernel",
            "explanation": "Viewing kernel messages"
        })

        assert result.success is True

    def test_view_logs_with_filter(self, linux_handler):
        """Test filtering logs."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="error: something went wrong",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_view_logs({
            "log_type": "system",
            "grep": "error",
            "explanation": "Searching for errors"
        })

        assert result.success is True


class TestArchiveOperations:
    """Tests for archive_operations tool."""

    def test_list_tar_archive(self, linux_handler):
        """Test listing tar archive contents."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="-rw-r--r-- user/group 1234 2024-01-15 file.txt",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_archive_operations({
            "action": "list",
            "archive_path": "/tmp/backup.tar.gz",
            "explanation": "Listing archive contents"
        })

        assert result.success is True

    def test_extract_requires_confirmation(self, linux_handler):
        """Test that extraction requires confirmation."""
        linux_handler.prompts.confirm_dangerous_action.return_value = ConfirmationResult.NO

        result = linux_handler.handle_archive_operations({
            "action": "extract",
            "archive_path": "/tmp/backup.tar.gz",
            "destination": "/home/user",
            "explanation": "Extracting backup"
        })

        assert result.success is False

    def test_missing_archive_path(self, linux_handler):
        """Test missing archive path."""
        result = linux_handler.handle_archive_operations({
            "action": "list",
            "explanation": "No archive specified"
        })

        assert result.success is False


class TestManageCron:
    """Tests for manage_cron tool."""

    def test_list_cron_jobs(self, linux_handler):
        """Test listing cron jobs."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="0 * * * * /usr/bin/backup.sh",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_manage_cron({
            "action": "list",
            "explanation": "Listing cron jobs"
        })

        assert result.success is True

    def test_add_cron_requires_confirmation(self, linux_handler):
        """Test that adding cron requires confirmation."""
        linux_handler.prompts.confirm_dangerous_action.return_value = ConfirmationResult.NO

        result = linux_handler.handle_manage_cron({
            "action": "add",
            "schedule": "0 * * * *",
            "command": "/usr/bin/backup.sh",
            "explanation": "Adding hourly backup"
        })

        assert result.success is False

    def test_add_cron_invalid_schedule(self, linux_handler):
        """Test invalid cron schedule."""
        result = linux_handler.handle_manage_cron({
            "action": "add",
            "schedule": "invalid",
            "command": "/usr/bin/backup.sh",
            "explanation": "Adding job with bad schedule"
        })

        assert result.success is False


class TestDiskOperations:
    """Tests for disk_operations tool."""

    def test_disk_usage(self, linux_handler):
        """Test checking disk usage."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="Filesystem Size Used Avail Use% Mounted on\n/dev/sda1 100G 50G 50G 50% /",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_disk_operations({
            "action": "usage",
            "path": "/",
            "explanation": "Checking disk space"
        })

        assert result.success is True

    def test_directory_size(self, linux_handler):
        """Test checking directory sizes."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="100M\t/home/user/downloads",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_disk_operations({
            "action": "directory_size",
            "path": "/home/user",
            "explanation": "Finding large directories"
        })

        assert result.success is True

    def test_list_partitions(self, linux_handler):
        """Test listing partitions."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="NAME SIZE TYPE FSTYPE MOUNTPOINT\nsda 500G disk\nsda1 500G part ext4 /",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_disk_operations({
            "action": "partitions",
            "explanation": "Listing disk partitions"
        })

        assert result.success is True


class TestUserManagement:
    """Tests for user_management tool."""

    def test_list_users(self, linux_handler):
        """Test listing users."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="user 1000 1000 /home/user /bin/bash",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_user_management({
            "action": "list",
            "explanation": "Listing user accounts"
        })

        assert result.success is True

    def test_current_user(self, linux_handler):
        """Test getting current user info."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="uid=1000(user) gid=1000(user) groups=1000(user),27(sudo)",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_user_management({
            "action": "current",
            "explanation": "Getting current user info"
        })

        assert result.success is True

    def test_recent_logins(self, linux_handler):
        """Test viewing recent logins."""
        linux_handler.executor.execute.return_value = CommandResult(
            success=True,
            stdout="user pts/0 192.168.1.10 Mon Jan 15 10:00 still logged in",
            stderr="",
            return_code=0,
        )

        result = linux_handler.handle_user_management({
            "action": "last",
            "count": 10,
            "explanation": "Viewing recent logins"
        })

        assert result.success is True
