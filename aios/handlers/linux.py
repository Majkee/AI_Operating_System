"""
Linux-specific tool handlers for AIOS.

Provides dedicated tools for common Linux operations:
- Service management (systemd)
- Process management
- Network diagnostics
- Log viewing
- Archive operations
- Cron job management
"""

import re
import shlex
from typing import Dict, Any, Optional, List

from ..claude.tools import ToolResult
from ..executor.sandbox import CommandExecutor
from ..safety.guardrails import SafetyGuard
from ..safety.audit import AuditLogger, ActionType
from ..ui.terminal import TerminalUI
from ..ui.prompts import ConfirmationPrompt, ConfirmationResult


class LinuxToolsHandler:
    """Handler for Linux-specific tools."""

    def __init__(
        self,
        executor: CommandExecutor,
        safety: SafetyGuard,
        audit: AuditLogger,
        ui: TerminalUI,
        prompts: ConfirmationPrompt,
    ):
        self.executor = executor
        self.safety = safety
        self.audit = audit
        self.ui = ui
        self.prompts = prompts

    # =========================================================================
    # Service Management (systemd)
    # =========================================================================

    def handle_manage_service(self, params: Dict[str, Any]) -> ToolResult:
        """Handle systemd service management."""
        action = params.get("action", "status")
        service = params.get("service", "")
        explanation = params.get("explanation", f"Managing service: {service}")

        if not service:
            return ToolResult(
                success=False,
                output="",
                error="Service name is required",
                user_friendly_message="I need to know which service to manage."
            )

        # Validate service name (alphanumeric, dash, underscore, dot)
        if not re.match(r'^[\w\-\.@]+$', service):
            return ToolResult(
                success=False,
                output="",
                error="Invalid service name",
                user_friendly_message="That doesn't look like a valid service name."
            )

        self.ui.print_executing(explanation)

        # Build command based on action
        if action == "status":
            cmd = f"systemctl status {service} --no-pager"
            needs_sudo = False
        elif action == "is-active":
            cmd = f"systemctl is-active {service}"
            needs_sudo = False
        elif action == "logs":
            lines = params.get("lines", 50)
            cmd = f"journalctl -u {service} -n {lines} --no-pager"
            needs_sudo = False
        elif action in ("start", "stop", "restart", "reload", "enable", "disable"):
            cmd = f"sudo systemctl {action} {service}"
            needs_sudo = True

            # Confirm dangerous actions
            result = self.prompts.confirm_dangerous_action(
                explanation,
                f"This will {action} the {service} service.",
                None
            )
            if result != ConfirmationResult.YES:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"USER DECLINED: The user chose not to {action} the {service} service. Do not retry or attempt alternative methods.",
                    user_friendly_message="Okay, I won't do that.",
                    user_cancelled=True,
                )
        else:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown action: {action}",
                user_friendly_message=f"I don't know how to '{action}' a service."
            )

        self.ui.print_command(cmd)
        cmd_result = self.executor.execute(cmd, timeout=30)

        self.audit.log(
            ActionType.COMMAND,
            f"Service {action}: {service}",
            success=cmd_result.success
        )

        # Format user-friendly output
        if action == "status":
            user_msg = self._format_service_status(service, cmd_result.output)
        elif action == "is-active":
            is_active = "active" in cmd_result.output.lower()
            user_msg = f"The {service} service is {'running' if is_active else 'not running'}."
        elif action == "logs":
            user_msg = f"Recent logs for {service}:"
        else:
            user_msg = f"Service {service} has been {action}ed." if cmd_result.success else f"Failed to {action} {service}."

        return ToolResult(
            success=cmd_result.success,
            output=cmd_result.output,
            error=cmd_result.error_message,
            user_friendly_message=user_msg
        )

    def _format_service_status(self, service: str, output: str) -> str:
        """Format service status in user-friendly way."""
        lines = output.split('\n')
        status = "unknown"
        for line in lines:
            if 'Active:' in line:
                if 'running' in line.lower():
                    status = "running"
                elif 'inactive' in line.lower() or 'dead' in line.lower():
                    status = "stopped"
                elif 'failed' in line.lower():
                    status = "failed"
                break
        return f"Service {service} is {status}."

    # =========================================================================
    # Process Management
    # =========================================================================

    def handle_manage_process(self, params: Dict[str, Any]) -> ToolResult:
        """Handle process management."""
        action = params.get("action", "list")
        explanation = params.get("explanation", "Managing processes")

        self.ui.print_executing(explanation)

        if action == "list":
            sort_by = params.get("sort_by", "cpu")
            limit = params.get("limit", 20)

            if sort_by == "memory":
                cmd = f"ps aux --sort=-%mem | head -n {limit + 1}"
            else:  # cpu
                cmd = f"ps aux --sort=-%cpu | head -n {limit + 1}"

            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message=f"Top {limit} processes by {sort_by} usage:"
            )

        elif action == "find":
            name = params.get("name", "")
            if not name:
                return ToolResult(
                    success=False,
                    output="",
                    error="Process name required",
                    user_friendly_message="I need a process name to search for."
                )

            cmd = f"pgrep -a -f {shlex.quote(name)} | head -20"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            if not cmd_result.output.strip():
                return ToolResult(
                    success=True,
                    output="",
                    user_friendly_message=f"No processes found matching '{name}'."
                )

            return ToolResult(
                success=True,
                output=cmd_result.output,
                user_friendly_message=f"Processes matching '{name}':"
            )

        elif action == "kill":
            pid = params.get("pid")
            name = params.get("name")
            signal = params.get("signal", "TERM")

            if not pid and not name:
                return ToolResult(
                    success=False,
                    output="",
                    error="PID or process name required",
                    user_friendly_message="I need either a PID or process name to kill."
                )

            # Confirm before killing
            target = f"PID {pid}" if pid else f"processes matching '{name}'"
            result = self.prompts.confirm_dangerous_action(
                explanation,
                f"This will send {signal} signal to {target}.",
                None
            )
            if result != ConfirmationResult.YES:
                return ToolResult(
                    success=False,
                    output="",
                    error="USER DECLINED: The user chose not to kill this process. Do not retry or attempt alternative methods.",
                    user_friendly_message="Okay, I won't kill that process.",
                    user_cancelled=True,
                )

            if pid:
                cmd = f"kill -{signal} {pid}"
            else:
                cmd = f"pkill -{signal} -f {shlex.quote(name)}"

            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            self.audit.log(
                ActionType.COMMAND,
                f"Process kill: {target}",
                success=cmd_result.success
            )

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                error=cmd_result.error_message,
                user_friendly_message=f"Sent {signal} signal to {target}."
            )

        elif action == "info":
            pid = params.get("pid")
            if not pid:
                return ToolResult(
                    success=False,
                    output="",
                    error="PID required",
                    user_friendly_message="I need a PID to get process info."
                )

            cmd = f"ps -p {pid} -o pid,ppid,user,%cpu,%mem,stat,start,time,comm --no-headers"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                error=cmd_result.error_message,
                user_friendly_message=f"Process info for PID {pid}:"
            )

        return ToolResult(
            success=False,
            output="",
            error=f"Unknown action: {action}",
            user_friendly_message=f"I don't know how to '{action}' processes."
        )

    # =========================================================================
    # Network Diagnostics
    # =========================================================================

    def handle_network_diagnostics(self, params: Dict[str, Any]) -> ToolResult:
        """Handle network diagnostic operations."""
        action = params.get("action", "status")
        explanation = params.get("explanation", "Running network diagnostics")

        self.ui.print_executing(explanation)

        if action == "status":
            # Show network interfaces and their status
            cmd = "ip -br addr show"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message="Network interfaces:"
            )

        elif action == "ping":
            host = params.get("host", "")
            count = params.get("count", 4)

            if not host:
                return ToolResult(
                    success=False,
                    output="",
                    error="Host required",
                    user_friendly_message="I need a hostname or IP to ping."
                )

            # Validate host (basic check)
            if not re.match(r'^[\w\.\-]+$', host):
                return ToolResult(
                    success=False,
                    output="",
                    error="Invalid host",
                    user_friendly_message="That doesn't look like a valid hostname."
                )

            cmd = f"ping -c {count} {host}"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=30)

            # Parse ping result
            if cmd_result.success:
                user_msg = f"Successfully pinged {host}."
            else:
                user_msg = f"Could not reach {host}."

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                error=cmd_result.error_message,
                user_friendly_message=user_msg
            )

        elif action == "ports":
            # Show listening ports
            cmd = "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message="Listening ports:"
            )

        elif action == "connections":
            # Show active connections
            state = params.get("state", "established")
            cmd = f"ss -tn state {state} 2>/dev/null || netstat -tn 2>/dev/null | grep -i {state}"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message=f"Active {state} connections:"
            )

        elif action == "dns":
            host = params.get("host", "")
            if not host:
                return ToolResult(
                    success=False,
                    output="",
                    error="Host required",
                    user_friendly_message="I need a hostname to look up."
                )

            cmd = f"nslookup {host} 2>/dev/null || host {host} 2>/dev/null || dig +short {host}"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=15)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                error=cmd_result.error_message,
                user_friendly_message=f"DNS lookup for {host}:"
            )

        elif action == "check_port":
            host = params.get("host", "localhost")
            port = params.get("port")

            if not port:
                return ToolResult(
                    success=False,
                    output="",
                    error="Port required",
                    user_friendly_message="I need a port number to check."
                )

            # Use nc (netcat) or bash tcp check
            cmd = f"(echo >/dev/tcp/{host}/{port}) 2>/dev/null && echo 'Port {port} is OPEN' || echo 'Port {port} is CLOSED'"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            is_open = "OPEN" in cmd_result.output
            return ToolResult(
                success=True,
                output=cmd_result.output,
                user_friendly_message=f"Port {port} on {host} is {'open' if is_open else 'closed'}."
            )

        elif action == "route":
            cmd = "ip route show"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message="Routing table:"
            )

        return ToolResult(
            success=False,
            output="",
            error=f"Unknown action: {action}",
            user_friendly_message=f"I don't know how to do '{action}' for network diagnostics."
        )

    # =========================================================================
    # Log Management
    # =========================================================================

    def handle_view_logs(self, params: Dict[str, Any]) -> ToolResult:
        """Handle system log viewing."""
        log_type = params.get("log_type", "system")
        lines = params.get("lines", 50)
        since = params.get("since")  # e.g., "1 hour ago", "today"
        grep = params.get("grep")  # filter pattern
        explanation = params.get("explanation", f"Viewing {log_type} logs")

        self.ui.print_executing(explanation)

        # Build journalctl command
        cmd_parts = ["journalctl", "--no-pager", f"-n {lines}"]

        if log_type == "system":
            pass  # default system journal
        elif log_type == "kernel":
            cmd_parts.append("-k")
        elif log_type == "boot":
            cmd_parts.append("-b")
        elif log_type == "auth":
            cmd_parts.append("SYSLOG_FACILITY=10")  # auth facility
        elif log_type == "cron":
            cmd_parts.append("SYSLOG_IDENTIFIER=cron")
        elif log_type.startswith("unit:"):
            unit = log_type.split(":", 1)[1]
            cmd_parts.append(f"-u {unit}")
        else:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown log type: {log_type}",
                user_friendly_message="I don't recognize that log type."
            )

        if since:
            cmd_parts.append(f'--since="{since}"')

        cmd = " ".join(cmd_parts)

        if grep:
            cmd += f" | grep -i {shlex.quote(grep)}"

        self.ui.print_command(cmd)
        cmd_result = self.executor.execute(cmd, timeout=30)

        self.audit.log(
            ActionType.COMMAND,
            f"View logs: {log_type}",
            success=cmd_result.success
        )

        return ToolResult(
            success=cmd_result.success,
            output=cmd_result.output,
            error=cmd_result.error_message,
            user_friendly_message=f"Recent {log_type} logs:"
        )

    # =========================================================================
    # Archive Operations
    # =========================================================================

    def handle_archive_operations(self, params: Dict[str, Any]) -> ToolResult:
        """Handle archive create/extract operations."""
        action = params.get("action", "list")
        archive_path = params.get("archive_path", "")
        explanation = params.get("explanation", "Working with archive")

        if not archive_path:
            return ToolResult(
                success=False,
                output="",
                error="Archive path required",
                user_friendly_message="I need to know which archive to work with."
            )

        self.ui.print_executing(explanation)

        # Detect archive type
        archive_lower = archive_path.lower()
        if archive_lower.endswith('.tar.gz') or archive_lower.endswith('.tgz'):
            archive_type = "tar.gz"
        elif archive_lower.endswith('.tar.bz2') or archive_lower.endswith('.tbz2'):
            archive_type = "tar.bz2"
        elif archive_lower.endswith('.tar.xz') or archive_lower.endswith('.txz'):
            archive_type = "tar.xz"
        elif archive_lower.endswith('.tar'):
            archive_type = "tar"
        elif archive_lower.endswith('.zip'):
            archive_type = "zip"
        elif archive_lower.endswith('.7z'):
            archive_type = "7z"
        else:
            archive_type = "unknown"

        if action == "list":
            if archive_type.startswith("tar"):
                cmd = f"tar -tvf {shlex.quote(archive_path)}"
            elif archive_type == "zip":
                cmd = f"unzip -l {shlex.quote(archive_path)}"
            elif archive_type == "7z":
                cmd = f"7z l {shlex.quote(archive_path)}"
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported archive type",
                    user_friendly_message="I don't know how to read that archive format."
                )

            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=60)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                error=cmd_result.error_message,
                user_friendly_message=f"Contents of {archive_path}:"
            )

        elif action == "extract":
            destination = params.get("destination", ".")

            # Confirm extraction
            result = self.prompts.confirm_dangerous_action(
                explanation,
                f"This will extract files to {destination}",
                None
            )
            if result != ConfirmationResult.YES:
                return ToolResult(
                    success=False,
                    output="",
                    error="USER DECLINED: The user chose not to extract this archive. Do not retry or attempt alternative methods.",
                    user_friendly_message="Okay, I won't extract that.",
                    user_cancelled=True,
                )

            if archive_type == "tar.gz":
                cmd = f"tar -xzvf {shlex.quote(archive_path)} -C {shlex.quote(destination)}"
            elif archive_type == "tar.bz2":
                cmd = f"tar -xjvf {shlex.quote(archive_path)} -C {shlex.quote(destination)}"
            elif archive_type == "tar.xz":
                cmd = f"tar -xJvf {shlex.quote(archive_path)} -C {shlex.quote(destination)}"
            elif archive_type == "tar":
                cmd = f"tar -xvf {shlex.quote(archive_path)} -C {shlex.quote(destination)}"
            elif archive_type == "zip":
                cmd = f"unzip -o {shlex.quote(archive_path)} -d {shlex.quote(destination)}"
            elif archive_type == "7z":
                cmd = f"7z x {shlex.quote(archive_path)} -o{shlex.quote(destination)}"
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error="Unsupported archive type",
                    user_friendly_message="I don't know how to extract that archive format."
                )

            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=300)

            self.audit.log(
                ActionType.FILE_WRITE,
                f"Extract archive: {archive_path}",
                success=cmd_result.success
            )

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                error=cmd_result.error_message,
                user_friendly_message=f"Extracted {archive_path} to {destination}."
            )

        elif action == "create":
            source_paths = params.get("source_paths", [])
            compression = params.get("compression", "gz")

            if not source_paths:
                return ToolResult(
                    success=False,
                    output="",
                    error="Source paths required",
                    user_friendly_message="I need to know what files to archive."
                )

            sources = " ".join(shlex.quote(p) for p in source_paths)

            if archive_type == "zip" or archive_path.endswith('.zip'):
                cmd = f"zip -r {shlex.quote(archive_path)} {sources}"
            elif archive_type == "7z" or archive_path.endswith('.7z'):
                cmd = f"7z a {shlex.quote(archive_path)} {sources}"
            else:
                # Default to tar with compression
                if compression == "gz":
                    cmd = f"tar -czvf {shlex.quote(archive_path)} {sources}"
                elif compression == "bz2":
                    cmd = f"tar -cjvf {shlex.quote(archive_path)} {sources}"
                elif compression == "xz":
                    cmd = f"tar -cJvf {shlex.quote(archive_path)} {sources}"
                else:
                    cmd = f"tar -cvf {shlex.quote(archive_path)} {sources}"

            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=600)

            self.audit.log(
                ActionType.FILE_WRITE,
                f"Create archive: {archive_path}",
                success=cmd_result.success
            )

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                error=cmd_result.error_message,
                user_friendly_message=f"Created archive {archive_path}."
            )

        return ToolResult(
            success=False,
            output="",
            error=f"Unknown action: {action}",
            user_friendly_message=f"I don't know how to '{action}' archives."
        )

    # =========================================================================
    # Cron Job Management
    # =========================================================================

    def handle_manage_cron(self, params: Dict[str, Any]) -> ToolResult:
        """Handle cron job management."""
        action = params.get("action", "list")
        explanation = params.get("explanation", "Managing cron jobs")

        self.ui.print_executing(explanation)

        if action == "list":
            # List user's crontab
            cmd = "crontab -l 2>/dev/null || echo 'No crontab for current user'"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=True,
                output=cmd_result.output,
                user_friendly_message="Current cron jobs:"
            )

        elif action == "list_system":
            # List system cron jobs
            cmd = "ls -la /etc/cron.d/ /etc/cron.daily/ /etc/cron.hourly/ /etc/cron.weekly/ /etc/cron.monthly/ 2>/dev/null"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=True,
                output=cmd_result.output,
                user_friendly_message="System cron directories:"
            )

        elif action == "add":
            schedule = params.get("schedule", "")
            command = params.get("command", "")

            if not schedule or not command:
                return ToolResult(
                    success=False,
                    output="",
                    error="Schedule and command required",
                    user_friendly_message="I need both a schedule and a command to add a cron job."
                )

            # Validate schedule format (basic check)
            schedule_parts = schedule.split()
            if len(schedule_parts) != 5:
                # Allow special strings like @daily, @hourly, etc.
                if not schedule.startswith('@'):
                    return ToolResult(
                        success=False,
                        output="",
                        error="Invalid schedule format",
                        user_friendly_message="Cron schedule should be in format: minute hour day month weekday (e.g., '0 * * * *')"
                    )

            # Confirm before adding
            result = self.prompts.confirm_dangerous_action(
                explanation,
                f"This will add a cron job: {schedule} {command}",
                None
            )
            if result != ConfirmationResult.YES:
                return ToolResult(
                    success=False,
                    output="",
                    error="USER DECLINED: The user chose not to add this cron job. Do not retry or attempt alternative methods.",
                    user_friendly_message="Okay, I won't add that cron job.",
                    user_cancelled=True,
                )

            # Add to crontab (preserving existing)
            cron_line = f"{schedule} {command}"
            cmd = f'(crontab -l 2>/dev/null; echo "{cron_line}") | crontab -'
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            self.audit.log(
                ActionType.COMMAND,
                f"Add cron job: {cron_line}",
                success=cmd_result.success
            )

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                error=cmd_result.error_message,
                user_friendly_message=f"Added cron job: {schedule} {command}"
            )

        elif action == "remove":
            pattern = params.get("pattern", "")

            if not pattern:
                return ToolResult(
                    success=False,
                    output="",
                    error="Pattern required",
                    user_friendly_message="I need to know which cron job to remove (provide a pattern to match)."
                )

            # Confirm before removing
            result = self.prompts.confirm_dangerous_action(
                explanation,
                f"This will remove cron jobs matching: {pattern}",
                None
            )
            if result != ConfirmationResult.YES:
                return ToolResult(
                    success=False,
                    output="",
                    error="USER DECLINED: The user chose not to remove cron jobs. Do not retry or attempt alternative methods.",
                    user_friendly_message="Okay, I won't remove any cron jobs.",
                    user_cancelled=True,
                )

            # Remove matching lines from crontab
            cmd = f'crontab -l 2>/dev/null | grep -v {shlex.quote(pattern)} | crontab -'
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            self.audit.log(
                ActionType.COMMAND,
                f"Remove cron jobs matching: {pattern}",
                success=cmd_result.success
            )

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                error=cmd_result.error_message,
                user_friendly_message=f"Removed cron jobs matching '{pattern}'."
            )

        return ToolResult(
            success=False,
            output="",
            error=f"Unknown action: {action}",
            user_friendly_message=f"I don't know how to '{action}' cron jobs."
        )

    # =========================================================================
    # Disk Operations
    # =========================================================================

    def handle_disk_operations(self, params: Dict[str, Any]) -> ToolResult:
        """Handle disk usage and mount operations."""
        action = params.get("action", "usage")
        explanation = params.get("explanation", "Checking disk information")

        self.ui.print_executing(explanation)

        if action == "usage":
            path = params.get("path", "/")
            human_readable = params.get("human_readable", True)

            flag = "-h" if human_readable else ""
            cmd = f"df {flag} {shlex.quote(path)}"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message=f"Disk usage for {path}:"
            )

        elif action == "directory_size":
            path = params.get("path", ".")
            depth = params.get("depth", 1)

            cmd = f"du -h --max-depth={depth} {shlex.quote(path)} 2>/dev/null | sort -hr | head -20"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=60)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message=f"Directory sizes in {path}:"
            )

        elif action == "mounts":
            cmd = "findmnt -t nosysfs,nodevfs,notmpfs,noproc --output=TARGET,SOURCE,FSTYPE,SIZE,USED,AVAIL,USE%"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message="Mounted filesystems:"
            )

        elif action == "partitions":
            cmd = "lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,LABEL"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message="Disk partitions:"
            )

        elif action == "large_files":
            path = params.get("path", "/")
            min_size = params.get("min_size", "100M")

            cmd = f"find {shlex.quote(path)} -type f -size +{min_size} -exec ls -lh {{}} \\; 2>/dev/null | sort -k5 -hr | head -20"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=120)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message=f"Large files (>{min_size}) in {path}:"
            )

        return ToolResult(
            success=False,
            output="",
            error=f"Unknown action: {action}",
            user_friendly_message=f"I don't know how to do '{action}' for disk operations."
        )

    # =========================================================================
    # User Management
    # =========================================================================

    def handle_user_management(self, params: Dict[str, Any]) -> ToolResult:
        """Handle user and group operations."""
        action = params.get("action", "list")
        explanation = params.get("explanation", "Managing users")

        self.ui.print_executing(explanation)

        if action == "list":
            # List human users (UID >= 1000)
            cmd = "awk -F: '$3 >= 1000 && $3 < 65534 {print $1, $3, $4, $6, $7}' /etc/passwd"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message="User accounts:"
            )

        elif action == "current":
            cmd = "id && groups"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message="Current user info:"
            )

        elif action == "groups":
            username = params.get("username")
            if username:
                cmd = f"groups {shlex.quote(username)}"
            else:
                cmd = "groups"

            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message="Group memberships:"
            )

        elif action == "who":
            cmd = "who -a"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message="Logged in users:"
            )

        elif action == "last":
            count = params.get("count", 10)
            cmd = f"last -n {count}"
            self.ui.print_command(cmd)
            cmd_result = self.executor.execute(cmd, timeout=10)

            return ToolResult(
                success=cmd_result.success,
                output=cmd_result.output,
                user_friendly_message="Recent logins:"
            )

        return ToolResult(
            success=False,
            output="",
            error=f"Unknown action: {action}",
            user_friendly_message=f"I don't know how to '{action}' for user management."
        )
