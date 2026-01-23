"""Tests for safety guardrails."""

import pytest
from aios.safety.guardrails import SafetyGuard, RiskLevel


class TestSafetyGuard:
    """Test the SafetyGuard class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.guard = SafetyGuard()

    def test_safe_commands(self):
        """Test that safe commands are allowed."""
        safe_commands = [
            "ls",
            "pwd",
            "cat file.txt",
            "echo hello",
            "date",
            "whoami",
        ]

        for cmd in safe_commands:
            result = self.guard.check_command(cmd)
            assert result.is_allowed, f"Command should be allowed: {cmd}"
            assert result.risk_level == RiskLevel.SAFE

    def test_forbidden_commands(self):
        """Test that forbidden commands are blocked."""
        forbidden_commands = [
            "rm -rf /",
            "rm -rf /*",
            "mkfs.ext4 /dev/sda",
            "dd if=/dev/zero of=/dev/sda",
            "> /dev/sda",
            ":(){ :|:& };:",
        ]

        for cmd in forbidden_commands:
            result = self.guard.check_command(cmd)
            assert not result.is_allowed, f"Command should be forbidden: {cmd}"
            assert result.risk_level == RiskLevel.FORBIDDEN

    def test_dangerous_commands(self):
        """Test that dangerous commands require confirmation."""
        dangerous_commands = [
            "rm -rf ~/Downloads",
            "chmod 777 /tmp/file",
            "shutdown now",
            "reboot",
            "apt remove firefox",
        ]

        for cmd in dangerous_commands:
            result = self.guard.check_command(cmd)
            assert result.is_allowed, f"Command should be allowed with confirmation: {cmd}"
            assert result.risk_level == RiskLevel.DANGEROUS
            assert result.requires_confirmation

    def test_moderate_commands(self):
        """Test that moderate commands are flagged but allowed."""
        moderate_commands = [
            "apt install vim",
            "pip install requests",
            "wget https://example.com/file.txt",
            "git clone https://github.com/user/repo",
        ]

        for cmd in moderate_commands:
            result = self.guard.check_command(cmd)
            assert result.is_allowed, f"Command should be allowed: {cmd}"
            assert result.risk_level == RiskLevel.MODERATE


class TestPackageOperations:
    """Test package operation safety checks."""

    def setup_method(self):
        """Set up test fixtures."""
        self.guard = SafetyGuard()

    def test_install_allowed(self):
        """Test that package installation is allowed."""
        result = self.guard.check_package_operation("install", "vim")
        assert result.is_allowed
        assert result.risk_level == RiskLevel.MODERATE

    def test_remove_requires_confirmation(self):
        """Test that package removal requires confirmation."""
        result = self.guard.check_package_operation("remove", "firefox")
        assert result.is_allowed
        assert result.requires_confirmation

    def test_critical_packages_blocked(self):
        """Test that removing critical packages is blocked."""
        critical_packages = ["apt", "dpkg", "systemd", "libc6", "linux-image"]

        for pkg in critical_packages:
            result = self.guard.check_package_operation("remove", pkg)
            assert not result.is_allowed, f"Removing {pkg} should be blocked"
