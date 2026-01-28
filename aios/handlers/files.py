"""
File operations handler for AIOS.

Handles read_file, write_file, search_files, and list_directory tools.
"""

import logging
from typing import Dict, Any
from pathlib import Path

from ..claude.tools import ToolResult
from ..executor.files import FileHandler
from ..safety.guardrails import SafetyGuard
from ..safety.audit import AuditLogger, ActionType
from ..ui.terminal import TerminalUI
from ..ui.prompts import ConfirmationPrompt, ConfirmationResult

logger = logging.getLogger(__name__)


class FileToolHandler:
    """Handler for file operation tools."""

    def __init__(
        self,
        files: FileHandler,
        safety: SafetyGuard,
        audit: AuditLogger,
        ui: TerminalUI,
        prompts: ConfirmationPrompt,
    ):
        self.files = files
        self.safety = safety
        self.audit = audit
        self.ui = ui
        self.prompts = prompts

    def handle_read_file(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the read_file tool."""
        path = params.get("path", "")
        explanation = params.get("explanation", "Reading a file")
        display_content = params.get("display_content", False)

        self.ui.print_executing(explanation)

        try:
            result = self.files.read_file(path)
        except PermissionError as e:
            logger.warning(f"Permission denied reading file: {path}")
            self.audit.log(
                ActionType.FILE_READ,
                f"Read denied: {path}",
                success=False,
                details={"path": path, "error": str(e)}
            )
            return ToolResult(
                success=False,
                output="",
                error=str(e),
                user_friendly_message=f"Access denied: {e}"
            )

        self.audit.log(
            ActionType.FILE_READ,
            f"Read: {path}",
            success=result.success,
            details={"path": path}
        )

        # Display file content to user if requested
        if result.success and display_content and result.data:
            filename = Path(path).name
            self.ui.print_file_content(result.data, filename)

        return ToolResult(
            success=result.success,
            output=result.data or "",
            error=result.error,
            user_friendly_message=result.message if result.success else result.error or ""
        )

    def handle_write_file(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the write_file tool."""
        path = params.get("path", "")
        content = params.get("content", "")
        explanation = params.get("explanation", "Writing to a file")
        requires_confirmation = params.get("requires_confirmation", True)
        create_backup = params.get("create_backup", True)

        # Safety check
        safety_check = self.safety.check_file_write(path)

        self.ui.print_executing(explanation)

        # Confirmation
        if requires_confirmation or safety_check.requires_confirmation:
            result = self.prompts.confirm(
                f"Save changes to {Path(path).name}?",
                default=True,
                warning=safety_check.user_warning
            )
            if result != ConfirmationResult.YES:
                return ToolResult(
                    success=False,
                    output="",
                    user_friendly_message="Okay, I won't save those changes."
                )

        # Write file
        try:
            file_result = self.files.write_file(path, content, create_backup)
        except PermissionError as e:
            logger.warning(f"Permission denied writing file: {path}")
            self.audit.log_file_write(path, False, None, str(e))
            return ToolResult(
                success=False,
                output="",
                error=str(e),
                user_friendly_message=f"Access denied: {e}"
            )

        # Log
        self.audit.log_file_write(
            path,
            file_result.success,
            str(file_result.backup_path) if file_result.backup_path else None,
            file_result.error
        )

        return ToolResult(
            success=file_result.success,
            output="",
            error=file_result.error,
            user_friendly_message=file_result.message if file_result.success else file_result.error or ""
        )

    def handle_search_files(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the search_files tool."""
        query = params.get("query", "")
        location = params.get("location")
        search_type = params.get("search_type", "filename")
        explanation = params.get("explanation", "Searching for files")

        self.ui.print_executing(explanation)

        try:
            result = self.files.search_files(query, location, search_type)
        except PermissionError as e:
            logger.warning(f"Permission denied searching files in: {location}")
            self.audit.log(
                ActionType.SEARCH,
                f"Search denied: {query}",
                success=False,
                details={"query": query, "location": location, "error": str(e)}
            )
            return ToolResult(
                success=False,
                output="",
                error=str(e),
                user_friendly_message=f"Access denied: {e}"
            )

        self.audit.log(
            ActionType.SEARCH,
            f"Searched for: {query}",
            success=True,
            details={"query": query, "results": len(result.files)}
        )

        if not result.files:
            return ToolResult(
                success=True,
                output="No files found matching your search.",
                user_friendly_message="I didn't find any files matching that."
            )

        # Format results
        file_list = []
        for f in result.files[:20]:
            file_list.append(f"{f.to_user_friendly()} - {f.path}")

        output = "\n".join(file_list)
        if result.truncated:
            output += f"\n\n(Showing first 20 of {result.total_count} results)"

        return ToolResult(
            success=True,
            output=output,
            user_friendly_message=f"Found {len(result.files)} file(s)"
        )

    def handle_list_directory(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the list_directory tool."""
        path = params.get("path")
        show_hidden = params.get("show_hidden", False)
        explanation = params.get("explanation", "Listing directory contents")

        self.ui.print_executing(explanation)

        try:
            result = self.files.list_directory(path, show_hidden)
        except PermissionError as e:
            logger.warning(f"Permission denied listing directory: {path}")
            return ToolResult(
                success=False,
                output="",
                error=str(e),
                user_friendly_message=f"Access denied: {e}"
            )

        if not result.files:
            return ToolResult(
                success=True,
                output="This folder is empty.",
                user_friendly_message="The folder is empty."
            )

        # Format results
        file_list = [f.to_user_friendly() for f in result.files]
        output = "\n".join(file_list)

        return ToolResult(
            success=True,
            output=output,
            user_friendly_message=f"Found {len(result.files)} item(s)"
        )
