"""
Safety guardrails for AIOS.

Protects users from potentially dangerous operations by:
- Detecting dangerous commands
- Blocking forbidden operations
- Requiring confirmation for risky actions
- Providing safe alternatives
"""

import re
from enum import Enum
from typing import Optional, List, Tuple
from dataclasses import dataclass

from ..config import get_config


class RiskLevel(Enum):
    """Risk level of an operation."""
    SAFE = "safe"           # Can execute immediately
    MODERATE = "moderate"   # Should explain what it does
    DANGEROUS = "dangerous" # Requires explicit confirmation
    FORBIDDEN = "forbidden" # Never allowed


@dataclass
class SafetyCheck:
    """Result of a safety check."""
    risk_level: RiskLevel
    is_allowed: bool
    reason: Optional[str] = None
    user_warning: Optional[str] = None
    safe_alternative: Optional[str] = None
    requires_confirmation: bool = False


class SafetyGuard:
    """Guards against dangerous operations."""

    # Commands that are always blocked
    FORBIDDEN_PATTERNS = [
        (r"rm\s+(-[rf]+\s+)?/\s*$", "Deleting the entire system"),
        (r"rm\s+-rf\s+/\*", "Deleting all files on the system"),
        (r"mkfs\.", "Formatting a disk"),
        (r"dd\s+.*of=/dev/[hs]d", "Overwriting disk contents"),
        (r">\s*/dev/sd[a-z]", "Destroying disk data"),
        (r":\(\)\{\s*:\|:&\s*\};:", "Fork bomb - crashes the system"),
        (r"chmod\s+-R\s+777\s+/", "Making all system files insecure"),
        (r"chown\s+-R\s+.*\s+/\s*$", "Changing ownership of system files"),
        (r"wget.*\|\s*sh", "Running untrusted code from internet"),
        (r"curl.*\|\s*sh", "Running untrusted code from internet"),
        (r"wget.*\|\s*bash", "Running untrusted code from internet"),
        (r"curl.*\|\s*bash", "Running untrusted code from internet"),
    ]

    # Commands that require explicit confirmation
    DANGEROUS_PATTERNS = [
        (r"rm\s+-rf", "Deleting files permanently", "Move to trash instead?"),
        (r"rm\s+-r", "Deleting folder and contents", "Move to trash instead?"),
        (r"rm\s+", "Deleting files", None),
        (r"chmod\s+777", "Making files accessible to everyone", None),
        (r"chmod\s+-R", "Changing permissions on many files", None),
        (r"chown", "Changing file ownership", None),
        (r"shutdown", "Shutting down the computer", None),
        (r"reboot", "Restarting the computer", None),
        (r"systemctl\s+stop", "Stopping a system service", None),
        (r"systemctl\s+disable", "Disabling a system service", None),
        (r"apt\s+remove", "Removing software", None),
        (r"apt\s+purge", "Completely removing software and settings", None),
        (r"apt-get\s+remove", "Removing software", None),
        (r"apt-get\s+purge", "Completely removing software and settings", None),
        (r"dpkg\s+--purge", "Completely removing software", None),
        (r"kill\s+-9", "Force stopping a program", None),
        (r"killall", "Stopping all instances of a program", None),
        (r"mv\s+.*\s+/", "Moving files to system directories", None),
        (r"cp\s+.*\s+/", "Copying files to system directories", None),
        (r">\s*~", "Overwriting a file in home directory", None),
        (r"passwd", "Changing password", None),
        (r"sudo\s+su", "Becoming administrator", None),
        (r"visudo", "Editing administrator settings", None),
    ]

    # Commands that should be explained but are generally safe
    MODERATE_PATTERNS = [
        (r"apt\s+install", "Installing software"),
        (r"apt\s+update", "Updating package lists"),
        (r"apt\s+upgrade", "Upgrading installed software"),
        (r"apt-get\s+install", "Installing software"),
        (r"pip\s+install", "Installing Python packages"),
        (r"npm\s+install", "Installing Node.js packages"),
        (r"git\s+clone", "Downloading a code repository"),
        (r"wget", "Downloading a file"),
        (r"curl", "Downloading/sending data"),
        (r"mv\s+", "Moving/renaming files"),
        (r"cp\s+", "Copying files"),
        (r"mkdir", "Creating folders"),
        (r"touch", "Creating empty files"),
        (r"nano|vim|vi|emacs", "Opening text editor"),
    ]

    def __init__(self):
        """Initialize the safety guard."""
        self.config = get_config()
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for efficiency."""
        self._forbidden = [
            (re.compile(pattern, re.IGNORECASE), reason)
            for pattern, reason in self.FORBIDDEN_PATTERNS
        ]

        # Add config-based blocked patterns
        for pattern in self.config.safety.blocked_patterns:
            try:
                self._forbidden.append(
                    (re.compile(pattern, re.IGNORECASE), "Blocked by configuration")
                )
            except re.error:
                pass

        self._dangerous = [
            (re.compile(pattern, re.IGNORECASE), reason, alt)
            for pattern, reason, alt in self.DANGEROUS_PATTERNS
        ]

        # Add config-based dangerous patterns
        for pattern in self.config.safety.dangerous_patterns:
            try:
                self._dangerous.append(
                    (re.compile(pattern, re.IGNORECASE), "Requires confirmation", None)
                )
            except re.error:
                pass

        self._moderate = [
            (re.compile(pattern, re.IGNORECASE), reason)
            for pattern, reason in self.MODERATE_PATTERNS
        ]

    def check_command(self, command: str) -> SafetyCheck:
        """
        Check if a command is safe to execute.

        Args:
            command: The shell command to check

        Returns:
            SafetyCheck with risk assessment
        """
        # Check forbidden patterns first
        for pattern, reason in self._forbidden:
            if pattern.search(command):
                return SafetyCheck(
                    risk_level=RiskLevel.FORBIDDEN,
                    is_allowed=False,
                    reason=reason,
                    user_warning=f"I can't do that - it would {reason.lower()}. "
                                 "This action is blocked for your safety."
                )

        # Check dangerous patterns
        for pattern, reason, alternative in self._dangerous:
            if pattern.search(command):
                warning = f"This will {reason.lower()}. Are you sure?"
                if alternative:
                    warning += f" ({alternative})"

                return SafetyCheck(
                    risk_level=RiskLevel.DANGEROUS,
                    is_allowed=True,
                    reason=reason,
                    user_warning=warning,
                    safe_alternative=alternative,
                    requires_confirmation=self.config.safety.require_confirmation
                )

        # Check moderate patterns
        for pattern, reason in self._moderate:
            if pattern.search(command):
                return SafetyCheck(
                    risk_level=RiskLevel.MODERATE,
                    is_allowed=True,
                    reason=reason,
                    requires_confirmation=False
                )

        # Default: safe
        return SafetyCheck(
            risk_level=RiskLevel.SAFE,
            is_allowed=True
        )

    def check_file_write(self, path: str) -> SafetyCheck:
        """Check if writing to a file path is safe."""
        # System directories
        system_paths = [
            "/etc", "/usr", "/bin", "/sbin", "/lib", "/boot",
            "/root", "/var", "/opt", "/sys", "/proc", "/dev"
        ]

        for sys_path in system_paths:
            if path.startswith(sys_path):
                return SafetyCheck(
                    risk_level=RiskLevel.DANGEROUS,
                    is_allowed=True,
                    reason="Writing to system directory",
                    user_warning=f"This will modify a system file. "
                                 "Incorrect changes could affect your computer.",
                    requires_confirmation=True
                )

        # Config files
        if "/.config/" in path or path.startswith("/home") and "/." in path:
            return SafetyCheck(
                risk_level=RiskLevel.MODERATE,
                is_allowed=True,
                reason="Writing to configuration file",
                requires_confirmation=False
            )

        return SafetyCheck(
            risk_level=RiskLevel.SAFE,
            is_allowed=True
        )

    def check_file_delete(self, path: str) -> SafetyCheck:
        """Check if deleting a file is safe."""
        # Always require confirmation for delete
        return SafetyCheck(
            risk_level=RiskLevel.DANGEROUS,
            is_allowed=True,
            reason="Deleting file",
            user_warning=f"This will permanently delete the file. "
                         "A backup will be created just in case.",
            requires_confirmation=True
        )

    def check_package_operation(
        self,
        action: str,
        package: str
    ) -> SafetyCheck:
        """Check if a package operation is safe."""
        if action == "remove":
            # Check for critical packages
            critical = ["apt", "dpkg", "systemd", "libc", "linux-image", "grub"]
            for crit in critical:
                if crit in package.lower():
                    return SafetyCheck(
                        risk_level=RiskLevel.FORBIDDEN,
                        is_allowed=False,
                        reason="Removing critical system component",
                        user_warning=f"I can't remove {package} - it's essential "
                                     "for your computer to work."
                    )

            return SafetyCheck(
                risk_level=RiskLevel.DANGEROUS,
                is_allowed=True,
                reason=f"Removing {package}",
                user_warning=f"This will remove {package} from your computer.",
                requires_confirmation=True
            )

        elif action == "install":
            return SafetyCheck(
                risk_level=RiskLevel.MODERATE,
                is_allowed=True,
                reason=f"Installing {package}",
                requires_confirmation=False
            )

        return SafetyCheck(
            risk_level=RiskLevel.SAFE,
            is_allowed=True
        )

    def get_safe_alternative(self, command: str) -> Optional[str]:
        """Suggest a safer alternative for a command."""
        # rm -> trash
        if re.match(r"rm\s+", command):
            # Extract files
            files = re.sub(r"rm\s+(-[rf]+\s+)?", "", command)
            return f"gio trash {files}"

        # chmod 777 -> more restrictive
        if "chmod 777" in command:
            return command.replace("777", "755")

        return None

    def explain_command(self, command: str) -> str:
        """Get a user-friendly explanation of what a command does."""
        explanations = {
            r"^ls": "List files in a directory",
            r"^cd": "Change to a different directory",
            r"^pwd": "Show current directory",
            r"^cat": "Display file contents",
            r"^cp": "Copy files",
            r"^mv": "Move or rename files",
            r"^rm": "Delete files",
            r"^mkdir": "Create a new folder",
            r"^touch": "Create an empty file",
            r"^chmod": "Change file permissions",
            r"^chown": "Change file ownership",
            r"^apt\s+install": "Install software",
            r"^apt\s+update": "Check for software updates",
            r"^apt\s+upgrade": "Install available updates",
            r"^apt\s+remove": "Uninstall software",
            r"^grep": "Search for text in files",
            r"^find": "Search for files",
            r"^df": "Show disk space",
            r"^du": "Show folder sizes",
            r"^ps": "Show running programs",
            r"^top|^htop": "Show system activity",
            r"^kill": "Stop a running program",
            r"^sudo": "Run as administrator",
            r"^apt-get": "Package management",
            r"^dpkg": "Package management",
            r"^systemctl": "Manage system services",
            r"^journalctl": "View system logs",
        }

        for pattern, explanation in explanations.items():
            if re.match(pattern, command):
                return explanation

        return "Execute a system command"
