"""
System information handler for AIOS.

Handles the get_system_info tool.
"""

from typing import Dict, Any

from ..claude.tools import ToolResult
from ..context.system import SystemContextGatherer
from ..safety.audit import AuditLogger, ActionType
from ..ui.terminal import TerminalUI


class SystemHandler:
    """Handler for system information tools."""

    def __init__(
        self,
        system: SystemContextGatherer,
        audit: AuditLogger,
        ui: TerminalUI,
    ):
        self.system = system
        self.audit = audit
        self.ui = ui

    def handle_system_info(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the get_system_info tool.

        Caching is handled transparently by ToolHandler.execute().
        """
        info_type = params.get("info_type", "general")
        explanation = params.get("explanation", "Getting system information")

        self.ui.print_executing(explanation)

        context = self.system.get_context(force_refresh=True)

        if info_type == "disk":
            output = self._format_disk_info(context)
        elif info_type == "memory":
            output = self._format_memory_info(context)
        elif info_type == "cpu":
            output = self._format_cpu_info(context)
        elif info_type == "processes":
            processes = self.system.get_running_processes(10)
            output = self._format_processes_info(processes)
        else:  # general
            output = context.to_summary()

        self.audit.log(
            ActionType.SYSTEM_INFO,
            f"Retrieved {info_type} info",
            success=True
        )

        return ToolResult(success=True, output=output, user_friendly_message="")

    def _format_disk_info(self, context) -> str:
        """Format disk information."""
        if not context.disk_info:
            return "Disk information not available"
        return "\n".join(d.to_user_friendly() for d in context.disk_info)

    def _format_memory_info(self, context) -> str:
        """Format memory information."""
        if not context.memory_info:
            return "Memory information not available"
        return context.memory_info.to_user_friendly()

    def _format_cpu_info(self, context) -> str:
        """Format CPU information."""
        return f"CPU: {context.cpu_count} cores, {context.cpu_percent:.1f}% usage"

    def _format_processes_info(self, processes) -> str:
        """Format processes information."""
        if not processes:
            return "Process information not available"
        lines = ["Top processes by CPU usage:"]
        for p in processes:
            lines.append(f"  {p.name}: CPU {p.cpu_percent:.1f}%, Memory {p.memory_percent:.1f}%")
        return "\n".join(lines)
