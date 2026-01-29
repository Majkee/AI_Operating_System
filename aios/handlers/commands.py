"""
Command execution handler for AIOS.

Handles the run_command tool including streaming execution and background tasks.
"""

import logging
import os
import sys
import subprocess
import threading
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

from ..claude.tools import ToolResult
from ..executor.sandbox import CommandExecutor, CommandResult
from ..safety.guardrails import SafetyGuard
from ..safety.audit import AuditLogger, ActionType
from ..ui.terminal import TerminalUI
from ..ui.prompts import ConfirmationPrompt, ConfirmationResult
from ..tasks import TaskManager


class CommandHandler:
    """Handler for command execution tools."""

    def __init__(
        self,
        executor: CommandExecutor,
        safety: SafetyGuard,
        audit: AuditLogger,
        ui: TerminalUI,
        prompts: ConfirmationPrompt,
        task_manager: TaskManager,
    ):
        self.executor = executor
        self.safety = safety
        self.audit = audit
        self.ui = ui
        self.prompts = prompts
        self.task_manager = task_manager

    def handle_run_command(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the run_command tool."""
        command = params.get("command", "")
        explanation = params.get("explanation", "Running a command")
        requires_confirmation = params.get("requires_confirmation", False)
        working_dir = params.get("working_directory")
        use_sudo = params.get("use_sudo", False)
        timeout = params.get("timeout")
        long_running = params.get("long_running", False)
        background = params.get("background", False)

        # Prepend sudo if requested and not already present
        if use_sudo and not command.lstrip().startswith("sudo "):
            command = f"sudo {command}"

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

        # Inform the user about elevated privileges
        if use_sudo:
            self.ui.print_warning("This command requires administrator privileges (sudo).")

        # Inform about long timeout
        if timeout and timeout > 60:
            minutes = (timeout + 59) // 60
            self.ui.print_info(f"This operation may take up to {minutes} minute(s).")

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
                    error=f"USER DECLINED: The user chose not to run this command. Do not retry or attempt alternative methods.",
                    user_friendly_message="Okay, I won't do that.",
                    user_cancelled=True,
                )

        # Show command in technical mode
        self.ui.print_command(command)

        # Background execution - no timeout, runs until done
        if background:
            self.ui.print_info(f"Starting in background: {explanation}")
            task = self.task_manager.create_task(
                command, explanation, working_dir
            )
            self.ui.print_success(
                f"Background task #{task.task_id} started. Ctrl+B to view."
            )
            return ToolResult(
                success=True,
                output=f"Task started in background (ID: {task.task_id})",
                user_friendly_message=(
                    f"Started background task #{task.task_id}"
                ),
            )

        # Execute - streaming or standard
        if long_running:
            cmd_result = self._execute_streaming(
                command, working_dir, timeout or 300, explanation
            )
        else:
            cmd_result = self.executor.execute(
                command, working_directory=working_dir, timeout=timeout
            )

        # Log
        self.audit.log_command(
            command,
            cmd_result.output,
            cmd_result.success,
            working_dir
        )

        # Provide helpful timeout message
        if cmd_result.timed_out:
            effective_timeout = timeout or self.executor.DEFAULT_TIMEOUT
            return ToolResult(
                success=False,
                output=cmd_result.stdout,
                error="Command timed out",
                user_friendly_message=(
                    f"The command timed out after {effective_timeout} seconds. "
                    "You can retry with a higher timeout value."
                )
            )

        return ToolResult(
            success=cmd_result.success,
            output=cmd_result.output,
            error=cmd_result.error_message,
            user_friendly_message=cmd_result.to_user_friendly()
        )

    def _execute_streaming(
        self,
        command: str,
        working_dir: Optional[str],
        timeout: int,
        description: str,
    ) -> CommandResult:
        """Execute a command with live streaming output.

        If the user presses Ctrl+C during execution, they are offered the
        option to background the still-running process rather than killing it.
        """
        cwd = Path(working_dir) if working_dir else Path.home()

        process_env = os.environ.copy()
        if sys.platform != "win32":
            process_env["PATH"] = (
                "/usr/local/bin:/usr/bin:/bin:" + process_env.get("PATH", "")
            )

        popen_kwargs: Dict[str, Any] = dict(
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(cwd),
            env=process_env,
            bufsize=1,
            universal_newlines=True,
        )
        if sys.platform != "win32":
            popen_kwargs["start_new_session"] = True

        output_lines: List[str] = []

        try:
            process = subprocess.Popen(command, **popen_kwargs)
        except Exception as e:
            return CommandResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error_message=str(e),
            )

        def _reader():
            try:
                for line in process.stdout:
                    stripped = line.rstrip("\n\r")
                    output_lines.append(stripped)
                    if display_callback[0] is not None:
                        try:
                            display_callback[0](stripped)
                        except (TypeError, ValueError, RuntimeError) as e:
                            # Display callback failed - log but don't stop reading
                            logger.debug(f"Display callback failed: {e}")
            except (ValueError, OSError):
                pass

        # Mutable container so the reader thread can see callback changes
        display_callback: List[Any] = [None]

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()

        try:
            with self.ui.print_streaming_output(description) as display:
                display_callback[0] = display.add_line
                reader_thread.join(timeout=timeout)
        except KeyboardInterrupt:
            # Offer to background the still-running process
            display_callback[0] = None  # detach live display
            if process.poll() is None:
                try:
                    answer = input("\nBackground this task? [y/N]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    answer = "n"

                if answer == "y":
                    task = self.task_manager.adopt_task(
                        command=command,
                        description=description,
                        process=process,
                        reader_thread=reader_thread,
                        output_buffer=list(output_lines),
                    )
                    self.ui.print_success(
                        f"Backgrounded as task #{task.task_id}. Ctrl+B to view."
                    )
                    return CommandResult(
                        success=True,
                        stdout="".join(
                            ln + "\n" for ln in output_lines
                        ),
                        stderr="",
                        return_code=-1,
                        error_message="Backgrounded by user",
                    )
                else:
                    # Kill the process
                    try:
                        if sys.platform != "win32":
                            os.killpg(os.getpgid(process.pid), 9)
                        else:
                            process.kill()
                    except (ProcessLookupError, OSError):
                        pass
                    process.wait()
                    return CommandResult(
                        success=False,
                        stdout="".join(ln + "\n" for ln in output_lines),
                        stderr="",
                        return_code=-1,
                        error_message="Cancelled by user",
                    )
            else:
                # Process already finished during the interrupt -
                # fall through to normal completion / process.wait() below.
                pass

        # Check if the reader timed out
        if reader_thread.is_alive():
            try:
                if sys.platform != "win32":
                    os.killpg(os.getpgid(process.pid), 9)
                else:
                    process.kill()
            except (ProcessLookupError, OSError):
                pass
            process.wait()
            return CommandResult(
                success=False,
                stdout="".join(ln + "\n" for ln in output_lines),
                stderr="",
                return_code=-1,
                timed_out=True,
            )

        # Normal completion
        process.wait()
        return CommandResult(
            success=(process.returncode == 0),
            stdout="".join(ln + "\n" for ln in output_lines),
            stderr="",
            return_code=process.returncode,
        )
