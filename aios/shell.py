"""
Main AIOS shell - the interactive conversation loop.

This is the core of AIOS, handling:
- User input
- Claude API communication
- Tool execution
- Response display
"""

import os
import sys
from typing import Optional, Dict, Any
from pathlib import Path

from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

from .config import get_config, ensure_config_dirs
from .claude.client import ClaudeClient
from .claude.tools import ToolHandler, ToolResult
from .executor.sandbox import CommandExecutor, CommandResult
from .executor.files import FileHandler
from .context.system import SystemContextGatherer
from .context.session import SessionManager
from .safety.guardrails import SafetyGuard, RiskLevel
from .safety.audit import AuditLogger, ActionType
from .ui.terminal import TerminalUI
from .ui.prompts import ConfirmationPrompt, ConfirmationResult
from .errors import (
    ErrorBoundary,
    ErrorCategory,
    ErrorSeverity,
    ErrorContext,
    AIOSError,
    APIError,
    format_error_for_user,
    safe_execute,
    ErrorRecovery,
)


class AIOSShell:
    """The main AIOS interactive shell."""

    def __init__(self):
        """Initialize the AIOS shell."""
        # Ensure config directories exist
        ensure_config_dirs()

        # Load configuration
        self.config = get_config()

        # Initialize components
        self.ui = TerminalUI()
        self.prompts = ConfirmationPrompt()
        self.safety = SafetyGuard()
        self.executor = CommandExecutor()
        self.files = FileHandler()
        self.system = SystemContextGatherer()
        self.session = SessionManager()
        self.audit = AuditLogger()

        # Initialize tool handler with our implementations
        self.tool_handler = ToolHandler()
        self._register_tools()

        # Initialize Claude client (may fail if no API key)
        self.claude: Optional[ClaudeClient] = None

        # Session state
        self.running = False

        # Command history
        history_path = Path.home() / ".config" / "aios" / "command_history"
        self.history = FileHistory(str(history_path))

    def _register_tools(self) -> None:
        """Register tool handlers."""
        self.tool_handler.register("run_command", self._handle_run_command)
        self.tool_handler.register("read_file", self._handle_read_file)
        self.tool_handler.register("write_file", self._handle_write_file)
        self.tool_handler.register("search_files", self._handle_search_files)
        self.tool_handler.register("list_directory", self._handle_list_directory)
        self.tool_handler.register("get_system_info", self._handle_system_info)
        self.tool_handler.register("manage_application", self._handle_manage_application)
        self.tool_handler.register("ask_clarification", self._handle_ask_clarification)
        self.tool_handler.register("open_application", self._handle_open_application)

    def _handle_run_command(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the run_command tool."""
        command = params.get("command", "")
        explanation = params.get("explanation", "Running a command")
        requires_confirmation = params.get("requires_confirmation", False)
        working_dir = params.get("working_directory")

        # Safety check
        safety_check = self.safety.check_command(command)

        if not safety_check.is_allowed:
            self.audit.log(
                ActionType.COMMAND,
                f"Blocked: {command}",
                success=False,
                error=safety_check.reason
            )
            return ToolResult(
                success=False,
                output="",
                error=safety_check.user_warning,
                user_friendly_message=safety_check.user_warning or "This action is not allowed."
            )

        # Show what we're doing
        self.ui.print_executing(explanation)

        # Confirmation for dangerous commands
        if safety_check.requires_confirmation or requires_confirmation:
            result = self.prompts.confirm_dangerous_action(
                explanation,
                safety_check.user_warning or "This action may modify your system.",
                safety_check.safe_alternative
            )
            if result != ConfirmationResult.YES:
                return ToolResult(
                    success=False,
                    output="",
                    user_friendly_message="Okay, I won't do that."
                )

        # Show command in technical mode
        self.ui.print_command(command)

        # Execute
        cmd_result = self.executor.execute(command, working_directory=working_dir)

        # Log
        self.audit.log_command(
            command,
            cmd_result.output,
            cmd_result.success,
            working_dir
        )

        return ToolResult(
            success=cmd_result.success,
            output=cmd_result.output,
            error=cmd_result.error_message,
            user_friendly_message=cmd_result.to_user_friendly()
        )

    def _handle_read_file(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the read_file tool."""
        path = params.get("path", "")
        explanation = params.get("explanation", "Reading a file")

        self.ui.print_executing(explanation)

        result = self.files.read_file(path)

        self.audit.log(
            ActionType.FILE_READ,
            f"Read: {path}",
            success=result.success,
            details={"path": path}
        )

        return ToolResult(
            success=result.success,
            output=result.data or "",
            error=result.error,
            user_friendly_message=result.message if result.success else result.error or ""
        )

    def _handle_write_file(self, params: Dict[str, Any]) -> ToolResult:
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
        file_result = self.files.write_file(path, content, create_backup)

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

    def _handle_search_files(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the search_files tool."""
        query = params.get("query", "")
        location = params.get("location")
        search_type = params.get("search_type", "filename")
        explanation = params.get("explanation", "Searching for files")

        self.ui.print_executing(explanation)

        result = self.files.search_files(query, location, search_type)

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

    def _handle_list_directory(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the list_directory tool."""
        path = params.get("path")
        show_hidden = params.get("show_hidden", False)
        explanation = params.get("explanation", "Listing directory contents")

        self.ui.print_executing(explanation)

        result = self.files.list_directory(path, show_hidden)

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

    def _handle_system_info(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the get_system_info tool."""
        info_type = params.get("info_type", "general")
        explanation = params.get("explanation", "Getting system information")

        self.ui.print_executing(explanation)

        context = self.system.get_context(force_refresh=True)

        if info_type == "disk":
            if not context.disk_info:
                return ToolResult(success=True, output="Disk information not available")
            output = "\n".join(d.to_user_friendly() for d in context.disk_info)

        elif info_type == "memory":
            if not context.memory_info:
                return ToolResult(success=True, output="Memory information not available")
            output = context.memory_info.to_user_friendly()

        elif info_type == "cpu":
            output = f"CPU: {context.cpu_count} cores, {context.cpu_percent:.1f}% usage"

        elif info_type == "processes":
            processes = self.system.get_running_processes(10)
            if not processes:
                output = "Process information not available"
            else:
                lines = ["Top processes by CPU usage:"]
                for p in processes:
                    lines.append(f"  {p.name}: CPU {p.cpu_percent:.1f}%, Memory {p.memory_percent:.1f}%")
                output = "\n".join(lines)

        else:  # general
            output = context.to_summary()

        self.audit.log(
            ActionType.SYSTEM_INFO,
            f"Retrieved {info_type} info",
            success=True
        )

        return ToolResult(success=True, output=output, user_friendly_message="")

    def _handle_manage_application(self, params: Dict[str, Any]) -> ToolResult:
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
                user_friendly_message="Okay, cancelled."
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

        # Execute with extended timeout for package operations
        self.ui.print_info(f"Running package operation (this may take a moment)...")
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

    def _handle_ask_clarification(self, params: Dict[str, Any]) -> ToolResult:
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

    def _handle_open_application(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the open_application tool."""
        target = params.get("target", "")
        explanation = params.get("explanation", f"Opening {target}")

        self.ui.print_executing(explanation)

        # Use xdg-open on Linux
        command = f"xdg-open {target}"
        cmd_result = self.executor.execute(command, timeout=5)

        return ToolResult(
            success=cmd_result.success,
            output="",
            user_friendly_message=f"Opened {Path(target).name}" if cmd_result.success else "Couldn't open that"
        )

    def _process_tool_calls(self, tool_calls: list) -> list:
        """Process tool calls and return results."""
        results = []

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_input = tool_call["input"]
            tool_id = tool_call["id"]

            # Execute the tool
            result = self.tool_handler.execute(tool_name, tool_input)

            # Format for Claude
            content = result.output if result.success else f"Error: {result.error}"

            results.append({
                "tool_use_id": tool_id,
                "content": content,
                "is_error": not result.success
            })

            # Show user-friendly message if any
            if result.user_friendly_message:
                if result.success:
                    self.ui.print_success(result.user_friendly_message)
                else:
                    self.ui.print_error(result.user_friendly_message)

        return results

    def _handle_user_input(self, user_input: str) -> bool:
        """
        Handle user input and return whether to continue.

        Returns:
            True to continue the loop, False to exit
        """
        # Handle special commands
        lower_input = user_input.lower().strip()

        if lower_input in ("exit", "quit", "bye", "goodbye"):
            self.ui.print_info("Goodbye! See you next time.")
            return False

        if lower_input == "help":
            self.ui.print_help()
            return True

        if lower_input == "clear":
            self.ui.clear_screen()
            return True

        if lower_input == "history":
            summary = self.session.get_session_summary()
            self.ui.print_system_info(summary)
            return True

        if not user_input.strip():
            return True

        # Log user query
        self.audit.log_user_query(user_input)
        self.session.add_message("user", user_input)

        # Get system context
        system_context = self.system.get_context().to_summary()

        # Send to Claude with progress indicator and error recovery
        with self.ui.print_thinking() as progress:
            task = progress.add_task("Thinking...", total=None)

            # Use retry for API calls (network issues may be transient)
            def send_to_claude():
                return self.claude.send_message(user_input, system_context)

            result = ErrorRecovery.retry(
                send_to_claude,
                max_attempts=2,
                on_retry=lambda attempt, exc: self.ui.print_info(
                    f"Retrying... (attempt {attempt + 1})"
                )
            )

            if result.is_err:
                error_msg = result.error.user_message if result.error else "Unknown error"
                self.ui.print_error(f"Error communicating with Claude: {error_msg}")
                if result.error and result.error.suggested_action:
                    self.ui.print_info(f"Suggestion: {result.error.suggested_action}")
                return True

            response = result.value

        # Process response
        if response.text:
            self.ui.print_response(response.text)
            self.session.add_message("assistant", response.text)

        # Handle tool calls
        while response.tool_calls:
            tool_results = self._process_tool_calls(response.tool_calls)

            # Send results back to Claude
            with self.ui.print_thinking() as progress:
                task = progress.add_task("Thinking...", total=None)
                response = self.claude.send_tool_results(tool_results, system_context)

            # Show any text response
            if response.text:
                self.ui.print_response(response.text)
                self.session.add_message("assistant", response.text)

        return True

    def run(self) -> int:
        """
        Run the main AIOS loop.

        Returns:
            Exit code (0 for success)
        """
        # Initialize Claude client
        try:
            self.claude = ClaudeClient(self.tool_handler)
        except ValueError as e:
            self.ui.print_error(str(e))
            self.ui.print_info("Please set ANTHROPIC_API_KEY or add it to your config file.")
            return 1

        # Start session
        self.session.start_session()
        self.running = True

        # Show welcome
        self.ui.clear_screen()
        self.ui.print_welcome()

        # Main loop
        while self.running:
            try:
                # Get user input
                user_input = prompt(
                    "You: ",
                    history=self.history,
                    auto_suggest=AutoSuggestFromHistory(),
                ).strip()

                # Process input with error boundary
                with ErrorBoundary(
                    "process_user_input",
                    show_technical_details=self.config.ui.show_technical_details
                ) as boundary:
                    self.running = self._handle_user_input(user_input)

                # Handle any errors that occurred during processing
                if boundary.has_error:
                    error_ctx = boundary.error_context
                    self.ui.print_error(format_error_for_user(error_ctx))

                    # Log the error
                    self.audit.log(
                        ActionType.COMMAND,
                        f"Error: {error_ctx.operation}",
                        success=False,
                        error=error_ctx.technical_message
                    )

                    # If error is not recoverable, stop the loop
                    if not error_ctx.recoverable:
                        self.ui.print_error("A critical error occurred. Exiting.")
                        self.running = False

            except KeyboardInterrupt:
                self.ui.print_info("\nUse 'exit' to quit, or Ctrl+D")
                continue
            except EOFError:
                self.ui.print_info("\nGoodbye!")
                break

        # Cleanup
        self.session.end_session()
        return 0
