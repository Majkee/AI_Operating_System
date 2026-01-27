"""
Sandboxed command executor for AIOS.

Provides safe execution of shell commands with:
- Timeout limits
- Resource constraints
- Output capture
- Error handling
"""

import os
import subprocess
import shlex
import threading
import time
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

from ..config import get_config


@dataclass
class CommandResult:
    """Result of a command execution."""
    success: bool
    stdout: str
    stderr: str
    return_code: int
    timed_out: bool = False
    error_message: Optional[str] = None

    @property
    def output(self) -> str:
        """Get combined output, preferring stdout."""
        if self.stdout:
            return self.stdout
        return self.stderr

    def to_user_friendly(self) -> str:
        """Convert to user-friendly message."""
        if self.timed_out:
            return "The command took too long and was stopped."
        if self.success:
            if self.stdout:
                return self.stdout
            return "Done!"
        if self.error_message:
            return self.error_message
        if self.stderr:
            return f"There was a problem: {self.stderr}"
        return f"Command failed with code {self.return_code}"


class CommandExecutor:
    """Executes shell commands safely."""

    # Default timeout in seconds
    DEFAULT_TIMEOUT = 30

    # Maximum timeout allowed
    MAX_TIMEOUT = 3600

    # Maximum output size (10MB)
    MAX_OUTPUT_SIZE = 10 * 1024 * 1024

    def __init__(self):
        """Initialize the executor."""
        self.config = get_config()
        self.default_cwd = Path.home()

        # Apply executor config overrides if present
        executor_cfg = getattr(self.config, 'executor', None)
        if executor_cfg is not None:
            dt = getattr(executor_cfg, 'default_timeout', None)
            mt = getattr(executor_cfg, 'max_timeout', None)
            if isinstance(dt, int):
                self.DEFAULT_TIMEOUT = dt
            if isinstance(mt, int):
                self.MAX_TIMEOUT = mt

    def execute(
        self,
        command: str,
        working_directory: Optional[str] = None,
        timeout: Optional[int] = None,
        env: Optional[dict] = None
    ) -> CommandResult:
        """
        Execute a shell command safely.

        Args:
            command: The shell command to execute
            working_directory: Directory to run command in (defaults to home)
            timeout: Maximum execution time in seconds
            env: Additional environment variables

        Returns:
            CommandResult with output and status
        """
        # Set working directory
        cwd = Path(working_directory) if working_directory else self.default_cwd
        if not cwd.exists():
            return CommandResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error_message=f"Directory not found: {cwd}"
            )

        # Set timeout
        if timeout is None:
            timeout = self.DEFAULT_TIMEOUT
        timeout = min(timeout, self.MAX_TIMEOUT)

        # Build environment
        process_env = os.environ.copy()
        if env:
            process_env.update(env)

        # Add safe PATH
        process_env["PATH"] = "/usr/local/bin:/usr/bin:/bin:" + process_env.get("PATH", "")

        try:
            # Execute command
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(cwd),
                env=process_env,
                # Don't inherit file descriptors
                close_fds=True,
                # Start in new process group for clean termination
                start_new_session=True
            )

            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Kill the process group
                os.killpg(os.getpgid(process.pid), 9)
                process.wait()
                return CommandResult(
                    success=False,
                    stdout="",
                    stderr="",
                    return_code=-1,
                    timed_out=True
                )

            # Decode output
            stdout_str = stdout.decode("utf-8", errors="replace")[:self.MAX_OUTPUT_SIZE]
            stderr_str = stderr.decode("utf-8", errors="replace")[:self.MAX_OUTPUT_SIZE]

            return CommandResult(
                success=(process.returncode == 0),
                stdout=stdout_str,
                stderr=stderr_str,
                return_code=process.returncode
            )

        except FileNotFoundError:
            return CommandResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error_message="Command not found"
            )
        except PermissionError:
            return CommandResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error_message="Permission denied"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error_message=f"Error: {str(e)}"
            )

    def execute_with_sudo(
        self,
        command: str,
        password: Optional[str] = None,
        working_directory: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> CommandResult:
        """
        Execute a command with sudo privileges.

        Note: This requires proper sudo configuration.
        For security, prefer passwordless sudo for specific commands.
        """
        # Extend timeout for sudo commands
        if timeout is None:
            timeout = self.DEFAULT_TIMEOUT * 2

        if password:
            # Use sudo with password from stdin
            full_command = f"echo {shlex.quote(password)} | sudo -S {command}"
        else:
            # Assume passwordless sudo is configured
            full_command = f"sudo {command}"

        return self.execute(
            full_command,
            working_directory=working_directory,
            timeout=timeout
        )

    def check_command_exists(self, command: str) -> bool:
        """Check if a command is available on the system."""
        result = self.execute(f"which {shlex.quote(command)}", timeout=5)
        return result.success

    def get_command_info(self, command: str) -> Optional[str]:
        """Get description of a command using --help or man."""
        # Try --help first
        result = self.execute(f"{shlex.quote(command)} --help 2>&1 | head -5", timeout=5)
        if result.success and result.stdout:
            return result.stdout

        # Fall back to whatis
        result = self.execute(f"whatis {shlex.quote(command)} 2>/dev/null", timeout=5)
        if result.success and result.stdout:
            return result.stdout

        return None


class InteractiveExecutor:
    """
    Executor for interactive or streaming commands.

    Used for commands that produce ongoing output or require interaction.
    """

    def __init__(self):
        """Initialize the interactive executor."""
        self.config = get_config()
        self.default_cwd = Path.home()

    def execute_streaming(
        self,
        command: str,
        working_directory: Optional[str] = None,
        on_output: Optional[callable] = None,
        timeout: Optional[int] = None,
        env: Optional[dict] = None
    ) -> CommandResult:
        """
        Execute a command and stream output line by line.

        Uses a daemon thread to read output so the main thread can
        enforce the timeout properly even when the subprocess blocks.

        Args:
            command: The shell command to execute
            working_directory: Directory to run command in
            on_output: Callback function for each line of output
            timeout: Maximum execution time in seconds
            env: Additional environment variables

        Returns:
            CommandResult with final status
        """
        cwd = Path(working_directory) if working_directory else self.default_cwd
        timeout = timeout or 60

        # Build environment
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        process_env["PATH"] = "/usr/local/bin:/usr/bin:/bin:" + process_env.get("PATH", "")

        output_lines = []

        def _read_output(proc):
            """Read stdout in a background thread."""
            try:
                for line in proc.stdout:
                    output_lines.append(line)
                    if on_output:
                        on_output(line.rstrip())
            except (ValueError, OSError):
                # Pipe closed or process killed
                pass

        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(cwd),
                env=process_env,
                bufsize=1,
                universal_newlines=True,
                start_new_session=True
            )

            reader_thread = threading.Thread(
                target=_read_output, args=(process,), daemon=True
            )
            reader_thread.start()

            # Wait for the reader thread (which blocks until EOF or timeout)
            reader_thread.join(timeout=timeout)

            if reader_thread.is_alive():
                # Timeout expired — kill the process group
                try:
                    os.killpg(os.getpgid(process.pid), 9)
                except (ProcessLookupError, OSError):
                    process.kill()
                process.wait()
                return CommandResult(
                    success=False,
                    stdout="".join(output_lines),
                    stderr="",
                    return_code=-1,
                    timed_out=True
                )

            # Process finished within timeout
            process.wait()

            return CommandResult(
                success=(process.returncode == 0),
                stdout="".join(output_lines),
                stderr="",
                return_code=process.returncode
            )

        except Exception as e:
            return CommandResult(
                success=False,
                stdout="".join(output_lines) if output_lines else "",
                stderr="",
                return_code=-1,
                error_message=str(e)
            )
