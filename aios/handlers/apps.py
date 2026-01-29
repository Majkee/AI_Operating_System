"""
Application management handler for AIOS.

Handles manage_application, open_application, and ask_clarification tools.
"""

import shlex
from typing import Dict, Any, Callable
from pathlib import Path

from ..claude.tools import ToolResult
from ..executor.sandbox import CommandExecutor, CommandResult
from ..safety.guardrails import SafetyGuard
from ..safety.audit import AuditLogger, ActionType
from ..ui.terminal import TerminalUI
from ..ui.prompts import ConfirmationPrompt, ConfirmationResult


class AppHandler:
    """Handler for application management tools."""

    def __init__(
        self,
        executor: CommandExecutor,
        safety: SafetyGuard,
        audit: AuditLogger,
        ui: TerminalUI,
        prompts: ConfirmationPrompt,
        streaming_executor: Callable[[str, str, int, str], CommandResult],
    ):
        self.executor = executor
        self.safety = safety
        self.audit = audit
        self.ui = ui
        self.prompts = prompts
        self._execute_streaming = streaming_executor

    def handle_manage_application(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the manage_application tool."""
        action = params.get("action", "")
        package = params.get("package", "")
        explanation = params.get("explanation", f"{action.capitalize()} {package}")

        # Safety check
        safety_check = self.safety.check_package_operation(action, package)

        if not safety_check.is_allowed:
            return ToolResult(
                success=False,
                output="",
                error=safety_check.user_warning,
                user_friendly_message=safety_check.user_warning or ""
            )

        self.ui.print_executing(explanation)

        # Always confirm package operations
        result = self.prompts.confirm(
            f"{action.capitalize()} {package}?",
            default=(action != "remove"),
            warning=safety_check.user_warning
        )
        if result != ConfirmationResult.YES:
            return ToolResult(
                success=False,
                output="",
                error=f"USER DECLINED: The user chose not to {action} {package}. Do not retry or attempt alternative methods.",
                user_friendly_message="Okay, cancelled.",
                user_cancelled=True,
            )

        # Check if sudo is available
        sudo_available = self.executor.check_command_exists("sudo")
        sudo_prefix = "sudo " if sudo_available else ""

        # Build command based on action
        if action == "install":
            # Update package cache first, then install
            command = f"{sudo_prefix}apt-get update -qq && {sudo_prefix}apt-get install -y {package}"
        elif action == "remove":
            command = f"{sudo_prefix}apt-get remove -y {package}"
        elif action == "update":
            command = f"{sudo_prefix}apt-get update && {sudo_prefix}apt-get upgrade -y"
        elif action == "search":
            # Search doesn't need sudo
            command = f"apt-cache search {package}"
        else:
            return ToolResult(success=False, output="", error="Unknown action")

        # Execute with extended timeout and streaming for package operations
        self.ui.print_info("Running package operation (this may take a moment)...")
        if action in ("install", "update"):
            cmd_result = self._execute_streaming(
                command, None, 600, f"{action.capitalize()}ing {package}"
            )
        else:
            cmd_result = self.executor.execute(command, timeout=300)

        self.audit.log_package_operation(action, package, cmd_result.success)

        # Provide helpful error messages
        if not cmd_result.success:
            error_msg = cmd_result.stderr or cmd_result.error_message or "Unknown error"
            if "Permission denied" in error_msg or "not permitted" in error_msg:
                user_msg = "Permission denied. The system may not allow package installations."
            elif "Unable to locate package" in error_msg:
                user_msg = f"Package '{package}' was not found. Check the package name and try again."
            elif "Could not get lock" in error_msg:
                user_msg = "Another package manager is running. Please wait and try again."
            else:
                user_msg = f"Failed to {action} {package}."
            return ToolResult(
                success=False,
                output=cmd_result.output,
                error=error_msg,
                user_friendly_message=user_msg
            )

        return ToolResult(
            success=True,
            output=cmd_result.output,
            user_friendly_message=f"Successfully {action}ed {package}!"
        )

    def handle_ask_clarification(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the ask_clarification tool."""
        question = params.get("question", "")
        options = params.get("options", [])
        context = params.get("context")

        response = self.prompts.ask_clarification(question, options, context)

        if response is None:
            return ToolResult(
                success=False,
                output="",
                user_friendly_message="Cancelled"
            )

        return ToolResult(
            success=True,
            output=response,
            requires_followup=True,
            user_friendly_message=""
        )

    def handle_open_application(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the open_application tool."""
        target = params.get("target", "")
        explanation = params.get("explanation", f"Opening {target}")

        self.ui.print_executing(explanation)

        # Use xdg-open on Linux
        command = f"xdg-open {shlex.quote(target)}"
        cmd_result = self.executor.execute(command, timeout=5)

        return ToolResult(
            success=cmd_result.success,
            output="",
            user_friendly_message=f"Opened {Path(target).name}" if cmd_result.success else "Couldn't open that"
        )
