"""
System context gatherer for AIOS.

Collects information about the current system state to provide
context to Claude for better decision-making.
"""

import os
import platform
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


@dataclass
class DiskInfo:
    """Information about disk usage."""
    path: str
    total_gb: float
    used_gb: float
    free_gb: float
    percent_used: float

    def to_user_friendly(self) -> str:
        """Get user-friendly description."""
        return (
            f"{self.path}: {self.free_gb:.1f} GB free of {self.total_gb:.1f} GB "
            f"({100 - self.percent_used:.0f}% available)"
        )


@dataclass
class MemoryInfo:
    """Information about memory usage."""
    total_gb: float
    available_gb: float
    percent_used: float

    def to_user_friendly(self) -> str:
        """Get user-friendly description."""
        return (
            f"{self.available_gb:.1f} GB available of {self.total_gb:.1f} GB "
            f"({100 - self.percent_used:.0f}% free)"
        )


@dataclass
class ProcessInfo:
    """Information about a running process."""
    name: str
    pid: int
    cpu_percent: float
    memory_percent: float
    status: str


@dataclass
class SystemContext:
    """Current system context."""
    # Basic info
    hostname: str = ""
    username: str = ""
    home_directory: str = ""
    current_directory: str = ""

    # System info
    os_name: str = ""
    os_version: str = ""
    kernel_version: str = ""
    architecture: str = ""

    # Resources
    disk_info: List[DiskInfo] = field(default_factory=list)
    memory_info: Optional[MemoryInfo] = None
    cpu_count: int = 0
    cpu_percent: float = 0.0

    # Environment
    desktop_environment: Optional[str] = None
    shell: str = ""
    terminal: Optional[str] = None

    # Timestamp
    timestamp: str = ""

    def to_summary(self) -> str:
        """Get a summary suitable for Claude's context."""
        lines = [
            f"User: {self.username}",
            f"Home: {self.home_directory}",
            f"Current directory: {self.current_directory}",
            f"OS: {self.os_name} {self.os_version}",
        ]

        if self.memory_info:
            lines.append(f"Memory: {self.memory_info.to_user_friendly()}")

        if self.disk_info:
            main_disk = self.disk_info[0]
            lines.append(f"Disk: {main_disk.to_user_friendly()}")

        if self.desktop_environment:
            lines.append(f"Desktop: {self.desktop_environment}")

        return "\n".join(lines)


class SystemContextGatherer:
    """Gathers system context information."""

    def __init__(self):
        """Initialize the gatherer."""
        self._cached_context: Optional[SystemContext] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 60  # Cache for 1 minute

    def get_context(self, force_refresh: bool = False) -> SystemContext:
        """
        Get current system context.

        Args:
            force_refresh: Force refresh of cached data

        Returns:
            SystemContext with current system state
        """
        now = datetime.now()

        # Return cached if still valid
        if (
            not force_refresh
            and self._cached_context
            and self._cache_time
            and (now - self._cache_time).seconds < self._cache_ttl_seconds
        ):
            # Update current directory (changes frequently)
            self._cached_context.current_directory = os.getcwd()
            return self._cached_context

        # Gather fresh context
        context = SystemContext(
            hostname=platform.node(),
            username=os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
            home_directory=str(Path.home()),
            current_directory=os.getcwd(),
            os_name=self._get_os_name(),
            os_version=self._get_os_version(),
            kernel_version=platform.release(),
            architecture=platform.machine(),
            cpu_count=os.cpu_count() or 1,
            shell=os.environ.get("SHELL", "/bin/bash"),
            terminal=os.environ.get("TERM"),
            desktop_environment=self._get_desktop_environment(),
            timestamp=now.isoformat()
        )

        # Get resource info if psutil available
        if PSUTIL_AVAILABLE:
            context.disk_info = self._get_disk_info()
            context.memory_info = self._get_memory_info()
            context.cpu_percent = psutil.cpu_percent(interval=0.1)

        self._cached_context = context
        self._cache_time = now

        return context

    def _get_os_name(self) -> str:
        """Get the OS name."""
        if platform.system() == "Linux":
            # Try to get distro name
            try:
                with open("/etc/os-release") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            return line.split("=")[1].strip().strip('"')
            except FileNotFoundError:
                pass
            return "Linux"
        return platform.system()

    def _get_os_version(self) -> str:
        """Get the OS version."""
        if platform.system() == "Linux":
            try:
                with open("/etc/os-release") as f:
                    for line in f:
                        if line.startswith("VERSION_ID="):
                            return line.split("=")[1].strip().strip('"')
            except FileNotFoundError:
                pass
        return platform.version()

    def _get_desktop_environment(self) -> Optional[str]:
        """Get the desktop environment name."""
        de = os.environ.get("XDG_CURRENT_DESKTOP")
        if de:
            return de

        session = os.environ.get("DESKTOP_SESSION")
        if session:
            return session

        # Check for common DEs
        if os.environ.get("GNOME_DESKTOP_SESSION_ID"):
            return "GNOME"
        if os.environ.get("KDE_FULL_SESSION"):
            return "KDE"

        return None

    def _get_disk_info(self) -> List[DiskInfo]:
        """Get disk usage information."""
        if not PSUTIL_AVAILABLE:
            return []

        disks = []
        partitions = psutil.disk_partitions()

        for partition in partitions:
            # Skip virtual filesystems
            if partition.fstype in ("squashfs", "tmpfs", "devtmpfs"):
                continue

            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append(DiskInfo(
                    path=partition.mountpoint,
                    total_gb=usage.total / (1024 ** 3),
                    used_gb=usage.used / (1024 ** 3),
                    free_gb=usage.free / (1024 ** 3),
                    percent_used=usage.percent
                ))
            except PermissionError:
                continue

        return disks

    def _get_memory_info(self) -> Optional[MemoryInfo]:
        """Get memory usage information."""
        if not PSUTIL_AVAILABLE:
            return None

        mem = psutil.virtual_memory()
        return MemoryInfo(
            total_gb=mem.total / (1024 ** 3),
            available_gb=mem.available / (1024 ** 3),
            percent_used=mem.percent
        )

    def get_running_processes(
        self,
        limit: int = 10,
        sort_by: str = "cpu"
    ) -> List[ProcessInfo]:
        """
        Get list of running processes.

        Args:
            limit: Maximum number of processes to return
            sort_by: Sort by "cpu" or "memory"

        Returns:
            List of ProcessInfo
        """
        if not PSUTIL_AVAILABLE:
            return []

        processes = []
        for proc in psutil.process_iter(["name", "pid", "cpu_percent", "memory_percent", "status"]):
            try:
                info = proc.info
                processes.append(ProcessInfo(
                    name=info["name"],
                    pid=info["pid"],
                    cpu_percent=info["cpu_percent"] or 0.0,
                    memory_percent=info["memory_percent"] or 0.0,
                    status=info["status"]
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sort
        if sort_by == "cpu":
            processes.sort(key=lambda p: p.cpu_percent, reverse=True)
        else:
            processes.sort(key=lambda p: p.memory_percent, reverse=True)

        return processes[:limit]

    def get_system_summary(self) -> str:
        """Get a brief system summary for display."""
        context = self.get_context()

        lines = [
            f"📍 {context.current_directory}",
            f"💻 {context.os_name}",
        ]

        if context.memory_info:
            mem_pct = 100 - context.memory_info.percent_used
            lines.append(f"🧠 {mem_pct:.0f}% memory free")

        if context.disk_info:
            disk = context.disk_info[0]
            lines.append(f"💾 {disk.free_gb:.1f} GB free")

        return " | ".join(lines)

    def check_system_health(self) -> Dict[str, Any]:
        """Check overall system health."""
        context = self.get_context()
        issues = []
        status = "good"

        # Check memory
        if context.memory_info:
            if context.memory_info.percent_used > 90:
                issues.append("Memory is almost full")
                status = "warning"
            elif context.memory_info.percent_used > 95:
                issues.append("Memory is critically low")
                status = "critical"

        # Check disk
        for disk in context.disk_info:
            if disk.percent_used > 90:
                issues.append(f"Disk {disk.path} is almost full")
                status = "warning"
            elif disk.percent_used > 95:
                issues.append(f"Disk {disk.path} is critically full")
                status = "critical"

        return {
            "status": status,
            "issues": issues,
            "summary": context.to_summary()
        }
