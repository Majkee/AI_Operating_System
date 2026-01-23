"""
Audit logging for AIOS.

Records all actions taken by the system for:
- Security auditing
- Troubleshooting
- Undo/recovery operations
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, List
from dataclasses import dataclass, asdict
from enum import Enum
import logging


class ActionType(Enum):
    """Types of auditable actions."""
    COMMAND = "command"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    PACKAGE_INSTALL = "package_install"
    PACKAGE_REMOVE = "package_remove"
    SYSTEM_INFO = "system_info"
    SEARCH = "search"
    USER_QUERY = "user_query"
    ERROR = "error"


@dataclass
class AuditEntry:
    """A single audit log entry."""
    timestamp: str
    action_type: str
    description: str
    user: str
    success: bool
    details: dict
    session_id: Optional[str] = None
    error: Optional[str] = None
    rollback_info: Optional[dict] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> "AuditEntry":
        """Create from dictionary."""
        return cls(**data)


class AuditLogger:
    """Logs all AIOS actions for auditing."""

    def __init__(self, log_path: Optional[str] = None):
        """
        Initialize the audit logger.

        Args:
            log_path: Path to the audit log file
        """
        from ..config import get_config
        config = get_config()

        self.enabled = config.logging.enabled
        self.log_level = config.logging.level

        # Set up log path
        if log_path:
            self.log_path = Path(log_path)
        else:
            self.log_path = Path(config.logging.path).expanduser()

        # Ensure log directory exists
        if self.enabled:
            self._ensure_log_directory()

        # Set up Python logger for console output
        self._setup_logger()

        # Session tracking
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.user = os.environ.get("USER", "unknown")

        # In-memory recent entries for undo
        self._recent_entries: List[AuditEntry] = []
        self._max_recent = 100

    def _ensure_log_directory(self) -> None:
        """Ensure the log directory exists."""
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # Fall back to user directory
            self.log_path = Path.home() / ".config" / "aios" / "audit.log"
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _setup_logger(self) -> None:
        """Set up Python logger."""
        self.logger = logging.getLogger("aios.audit")

        level_map = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
        }
        self.logger.setLevel(level_map.get(self.log_level, logging.INFO))

        # Console handler for debug mode
        if self.log_level == "debug":
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s"
            ))
            self.logger.addHandler(handler)

    def log(
        self,
        action_type: ActionType,
        description: str,
        success: bool = True,
        details: Optional[dict] = None,
        error: Optional[str] = None,
        rollback_info: Optional[dict] = None
    ) -> AuditEntry:
        """
        Log an action.

        Args:
            action_type: Type of action
            description: Human-readable description
            success: Whether the action succeeded
            details: Additional details
            error: Error message if failed
            rollback_info: Information needed to undo this action

        Returns:
            The created audit entry
        """
        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            action_type=action_type.value,
            description=description,
            user=self.user,
            success=success,
            details=details or {},
            session_id=self.session_id,
            error=error,
            rollback_info=rollback_info
        )

        # Add to recent entries
        self._recent_entries.append(entry)
        if len(self._recent_entries) > self._max_recent:
            self._recent_entries.pop(0)

        # Log to console (if debug)
        if success:
            self.logger.info(f"{action_type.value}: {description}")
        else:
            self.logger.error(f"{action_type.value}: {description} - {error}")

        # Write to file
        if self.enabled:
            self._write_entry(entry)

        return entry

    def _write_entry(self, entry: AuditEntry) -> None:
        """Write an entry to the log file."""
        try:
            with open(self.log_path, "a") as f:
                f.write(entry.to_json() + "\n")
        except (PermissionError, OSError) as e:
            self.logger.warning(f"Could not write to audit log: {e}")

    def log_command(
        self,
        command: str,
        output: str,
        success: bool,
        working_dir: Optional[str] = None
    ) -> AuditEntry:
        """Log a command execution."""
        return self.log(
            action_type=ActionType.COMMAND,
            description=f"Executed: {command[:100]}",
            success=success,
            details={
                "command": command,
                "output_preview": output[:500] if output else "",
                "working_dir": working_dir
            }
        )

    def log_file_write(
        self,
        path: str,
        success: bool,
        backup_path: Optional[str] = None,
        error: Optional[str] = None
    ) -> AuditEntry:
        """Log a file write operation."""
        rollback = None
        if backup_path:
            rollback = {
                "type": "restore_backup",
                "backup_path": backup_path,
                "original_path": path
            }

        return self.log(
            action_type=ActionType.FILE_WRITE,
            description=f"Wrote file: {path}",
            success=success,
            details={"path": path, "backup_path": backup_path},
            error=error,
            rollback_info=rollback
        )

    def log_file_delete(
        self,
        path: str,
        success: bool,
        backup_path: Optional[str] = None,
        error: Optional[str] = None
    ) -> AuditEntry:
        """Log a file deletion."""
        rollback = None
        if backup_path:
            rollback = {
                "type": "restore_backup",
                "backup_path": backup_path,
                "original_path": path
            }

        return self.log(
            action_type=ActionType.FILE_DELETE,
            description=f"Deleted: {path}",
            success=success,
            details={"path": path, "backup_path": backup_path},
            error=error,
            rollback_info=rollback
        )

    def log_package_operation(
        self,
        action: str,
        package: str,
        success: bool,
        error: Optional[str] = None
    ) -> AuditEntry:
        """Log a package operation."""
        action_type = (
            ActionType.PACKAGE_INSTALL if action == "install"
            else ActionType.PACKAGE_REMOVE
        )

        return self.log(
            action_type=action_type,
            description=f"{action.capitalize()} package: {package}",
            success=success,
            details={"action": action, "package": package},
            error=error
        )

    def log_user_query(self, query: str) -> AuditEntry:
        """Log a user query."""
        return self.log(
            action_type=ActionType.USER_QUERY,
            description=f"User asked: {query[:100]}",
            success=True,
            details={"query": query}
        )

    def log_error(
        self,
        description: str,
        error: str,
        details: Optional[dict] = None
    ) -> AuditEntry:
        """Log an error."""
        return self.log(
            action_type=ActionType.ERROR,
            description=description,
            success=False,
            details=details or {},
            error=error
        )

    def get_recent_entries(
        self,
        count: int = 10,
        action_type: Optional[ActionType] = None
    ) -> List[AuditEntry]:
        """Get recent audit entries."""
        entries = self._recent_entries

        if action_type:
            entries = [e for e in entries if e.action_type == action_type.value]

        return entries[-count:]

    def get_undoable_actions(self) -> List[AuditEntry]:
        """Get actions that can be undone."""
        return [
            e for e in self._recent_entries
            if e.rollback_info and e.success
        ]

    def get_session_summary(self) -> dict:
        """Get a summary of the current session."""
        entries = [e for e in self._recent_entries if e.session_id == self.session_id]

        action_counts = {}
        for entry in entries:
            action_type = entry.action_type
            action_counts[action_type] = action_counts.get(action_type, 0) + 1

        success_count = sum(1 for e in entries if e.success)
        error_count = sum(1 for e in entries if not e.success)

        return {
            "session_id": self.session_id,
            "total_actions": len(entries),
            "successful": success_count,
            "errors": error_count,
            "action_breakdown": action_counts
        }

    def export_session_log(self, output_path: str) -> bool:
        """Export the current session's log to a file."""
        try:
            entries = [
                e for e in self._recent_entries
                if e.session_id == self.session_id
            ]

            with open(output_path, "w") as f:
                for entry in entries:
                    f.write(entry.to_json() + "\n")

            return True
        except Exception:
            return False
