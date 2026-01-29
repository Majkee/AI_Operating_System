"""
Widget system for AIOS welcome screen.

Provides customizable widgets that display in the welcome screen's left column,
below the shortcuts section. Users can enable built-in widgets or create custom ones.
"""

import importlib.util
import logging
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import psutil

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WidgetMetadata:
    """Metadata for a widget."""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    refresh_seconds: int = 0  # 0 = static, >0 = live refresh interval


@dataclass
class WidgetOutput:
    """Output from a widget's render method."""
    lines: List[Tuple[str, str]] = field(default_factory=list)  # (text, style) tuples
    title: Optional[str] = None


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class WidgetBase(ABC):
    """Base class for AIOS widgets.

    Widgets are small display components that render in the welcome screen.
    They should be fast to render (<100ms) and produce max 4 lines of output.

    Example:
        class MyWidget(WidgetBase):
            @property
            def metadata(self) -> WidgetMetadata:
                return WidgetMetadata(
                    name="my_widget",
                    description="Shows something useful",
                )

            def render(self) -> WidgetOutput:
                return WidgetOutput(lines=[
                    ("Status: OK", "green"),
                ])
    """

    @property
    @abstractmethod
    def metadata(self) -> WidgetMetadata:
        """Return widget metadata."""
        pass

    @abstractmethod
    def render(self) -> WidgetOutput:
        """Render widget content.

        Returns:
            WidgetOutput with max 4 lines, each max 35 chars.
            Use Rich styles: cyan, green, yellow, red, dim, bold
        """
        pass

    def on_load(self) -> None:
        """Called when widget is loaded."""
        pass

    def on_unload(self) -> None:
        """Called when widget is unloaded."""
        pass


# ---------------------------------------------------------------------------
# Built-in widgets
# ---------------------------------------------------------------------------

class CPUMemoryWidget(WidgetBase):
    """Displays CPU and memory usage bars."""

    @property
    def metadata(self) -> WidgetMetadata:
        return WidgetMetadata(
            name="cpu_memory",
            description="CPU and memory usage bars",
            author="AIOS",
        )

    def render(self) -> WidgetOutput:
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            mem_percent = memory.percent

            # Create progress bars (20 chars wide)
            cpu_filled = int(cpu_percent / 5)
            mem_filled = int(mem_percent / 5)

            cpu_bar = "#" * cpu_filled + "-" * (20 - cpu_filled)
            mem_bar = "#" * mem_filled + "-" * (20 - mem_filled)

            # Color based on usage
            cpu_style = "green" if cpu_percent < 70 else ("yellow" if cpu_percent < 90 else "red")
            mem_style = "green" if mem_percent < 70 else ("yellow" if mem_percent < 90 else "red")

            return WidgetOutput(lines=[
                (f"CPU:    [{cpu_bar}] {cpu_percent:3.0f}%", cpu_style),
                (f"Memory: [{mem_bar}] {mem_percent:3.0f}%", mem_style),
            ])
        except Exception:
            return WidgetOutput(lines=[
                ("CPU:    [unavailable]", "dim"),
                ("Memory: [unavailable]", "dim"),
            ])


class ProcessStatusWidget(WidgetBase):
    """Displays status of important system processes."""

    PROCESSES = ["nginx", "docker", "postgresql", "redis"]

    @property
    def metadata(self) -> WidgetMetadata:
        return WidgetMetadata(
            name="process_status",
            description="Status of important services",
            author="AIOS",
        )

    def _check_process(self, name: str) -> Tuple[bool, bool]:
        """Check if process is running and installed.

        Returns:
            (is_running, is_installed)
        """
        # Check if installed
        is_installed = shutil.which(name) is not None

        # Check if running
        is_running = False
        for proc in psutil.process_iter(['name']):
            try:
                if name.lower() in proc.info['name'].lower():
                    is_running = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return is_running, is_installed

    def render(self) -> WidgetOutput:
        lines = []
        for proc_name in self.PROCESSES[:4]:  # Max 4 lines
            try:
                is_running, is_installed = self._check_process(proc_name)
                if is_running:
                    lines.append((f"{proc_name:12} running", "green"))
                elif is_installed:
                    lines.append((f"{proc_name:12} stopped", "yellow"))
                else:
                    lines.append((f"{proc_name:12} not installed", "dim"))
            except Exception:
                lines.append((f"{proc_name:12} unknown", "dim"))

        return WidgetOutput(lines=lines)


class TasksWidget(WidgetBase):
    """Displays background task summary."""

    def __init__(self, task_manager=None):
        self._task_manager = task_manager

    def set_task_manager(self, task_manager) -> None:
        """Set the task manager reference."""
        self._task_manager = task_manager

    @property
    def metadata(self) -> WidgetMetadata:
        return WidgetMetadata(
            name="tasks",
            description="Background task summary",
            author="AIOS",
        )

    def render(self) -> WidgetOutput:
        if self._task_manager is None:
            return WidgetOutput(lines=[
                ("Tasks: no task manager", "dim"),
            ])

        try:
            running = self._task_manager.running_count()
            completed = len(self._task_manager.get_unnotified_completions())
            total = len(self._task_manager.list_tasks())

            if total == 0:
                return WidgetOutput(lines=[
                    ("Tasks: none active", "dim"),
                ])

            parts = []
            if running > 0:
                parts.append(f"{running} running")
            if completed > 0:
                parts.append(f"{completed} completed")

            status = ", ".join(parts) if parts else "idle"
            style = "cyan" if running > 0 else ("green" if completed > 0 else "dim")

            return WidgetOutput(lines=[
                (f"Tasks: {status}", style),
            ])
        except Exception:
            return WidgetOutput(lines=[
                ("Tasks: error", "red"),
            ])


class DiskWidget(WidgetBase):
    """Displays disk usage summary."""

    @property
    def metadata(self) -> WidgetMetadata:
        return WidgetMetadata(
            name="disk",
            description="Disk usage summary",
            author="AIOS",
        )

    def render(self) -> WidgetOutput:
        try:
            usage = psutil.disk_usage('/')
            percent = usage.percent
            used_gb = usage.used / (1024**3)
            total_gb = usage.total / (1024**3)

            # Progress bar
            filled = int(percent / 5)
            bar = "#" * filled + "-" * (20 - filled)

            style = "green" if percent < 70 else ("yellow" if percent < 90 else "red")

            return WidgetOutput(lines=[
                (f"Disk:   [{bar}] {percent:.0f}%", style),
                (f"        {used_gb:.1f}GB / {total_gb:.1f}GB", "dim"),
            ])
        except Exception:
            return WidgetOutput(lines=[
                ("Disk: [unavailable]", "dim"),
            ])


class NetworkWidget(WidgetBase):
    """Displays network connection status."""

    @property
    def metadata(self) -> WidgetMetadata:
        return WidgetMetadata(
            name="network",
            description="Network connection status",
            author="AIOS",
        )

    def render(self) -> WidgetOutput:
        try:
            # Get network interfaces
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()

            lines = []
            for iface, addresses in list(addrs.items())[:2]:  # Max 2 interfaces
                if iface.startswith('lo'):
                    continue

                is_up = stats.get(iface, None)
                if is_up and is_up.isup:
                    # Get IPv4 address
                    ipv4 = None
                    for addr in addresses:
                        if addr.family.name == 'AF_INET':
                            ipv4 = addr.address
                            break

                    if ipv4:
                        iface_short = iface[:8]
                        lines.append((f"{iface_short:8} {ipv4}", "green"))
                    else:
                        lines.append((f"{iface[:8]:8} no IPv4", "yellow"))

            if not lines:
                lines.append(("Network: no connection", "red"))

            return WidgetOutput(lines=lines[:2])
        except Exception:
            return WidgetOutput(lines=[
                ("Network: [error]", "dim"),
            ])


# ---------------------------------------------------------------------------
# Widget Manager
# ---------------------------------------------------------------------------

class WidgetManager:
    """Manages widget discovery, loading, and rendering."""

    def __init__(self):
        self._widgets: Dict[str, WidgetBase] = {}
        self._enabled: Set[str] = set()
        self._builtin: Set[str] = set()
        self._widget_dirs = [
            Path.home() / ".config" / "aios" / "widgets",
            Path("/etc/aios/widgets"),
        ]

    def register_builtin(self, widget: WidgetBase) -> None:
        """Register a built-in widget."""
        name = widget.metadata.name
        self._widgets[name] = widget
        self._builtin.add(name)
        logger.debug(f"Registered built-in widget: {name}")

    def discover_widgets(self) -> List[Path]:
        """Discover widget files in widget directories."""
        found = []
        for widget_dir in self._widget_dirs:
            if not widget_dir.exists():
                continue

            # Single Python files
            for path in widget_dir.glob("*.py"):
                if not path.name.startswith("_"):
                    found.append(path)

            # Package directories with __init__.py
            for path in widget_dir.iterdir():
                if path.is_dir() and (path / "__init__.py").exists():
                    found.append(path)

        return found

    def load_widget(self, path: Path) -> Optional[WidgetBase]:
        """Load a widget from a file or package."""
        try:
            if path.is_file():
                module_name = f"aios_widget_{path.stem}"
                spec = importlib.util.spec_from_file_location(module_name, path)
            else:
                module_name = f"aios_widget_{path.name}"
                init_path = path / "__init__.py"
                spec = importlib.util.spec_from_file_location(module_name, init_path)

            if spec is None or spec.loader is None:
                logger.warning(f"Cannot load widget from {path}")
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find WidgetBase subclass
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, WidgetBase) and
                    attr is not WidgetBase):
                    widget = attr()
                    name = widget.metadata.name
                    self._widgets[name] = widget
                    widget.on_load()
                    logger.info(f"Loaded widget: {name} from {path}")
                    return widget

            logger.warning(f"No WidgetBase subclass found in {path}")
            return None

        except Exception as e:
            logger.error(f"Failed to load widget from {path}: {e}")
            return None

    def load_all(self) -> List[str]:
        """Discover and load all widgets."""
        loaded = []
        for path in self.discover_widgets():
            widget = self.load_widget(path)
            if widget:
                loaded.append(widget.metadata.name)
        return loaded

    def unload_widget(self, name: str) -> bool:
        """Unload a widget by name."""
        if name in self._builtin:
            logger.warning(f"Cannot unload built-in widget: {name}")
            return False

        if name in self._widgets:
            try:
                self._widgets[name].on_unload()
            except Exception as e:
                logger.warning(f"Error in widget on_unload: {e}")
            del self._widgets[name]
            self._enabled.discard(name)
            return True
        return False

    def enable_widget(self, name: str) -> bool:
        """Enable a widget by name."""
        if name in self._widgets:
            self._enabled.add(name)
            return True
        return False

    def disable_widget(self, name: str) -> bool:
        """Disable a widget by name."""
        if name in self._enabled:
            self._enabled.discard(name)
            return True
        return False

    def is_enabled(self, name: str) -> bool:
        """Check if a widget is enabled."""
        return name in self._enabled

    def get_widget(self, name: str) -> Optional[WidgetBase]:
        """Get a widget by name."""
        return self._widgets.get(name)

    def list_widgets(self) -> List[WidgetMetadata]:
        """List all available widgets."""
        return [w.metadata for w in self._widgets.values()]

    def get_enabled_widgets(self) -> List[WidgetBase]:
        """Get all enabled widgets in order."""
        return [self._widgets[name] for name in self._enabled if name in self._widgets]

    def render_all(self) -> List[WidgetOutput]:
        """Render all enabled widgets."""
        outputs = []
        for widget in self.get_enabled_widgets():
            try:
                output = widget.render()
                outputs.append(output)
            except Exception as e:
                logger.warning(f"Widget {widget.metadata.name} render failed: {e}")
        return outputs

    def set_enabled_from_config(self, enabled_list: List[str]) -> None:
        """Set enabled widgets from config list."""
        self._enabled = set(name for name in enabled_list if name in self._widgets)

    def get_enabled_names(self) -> List[str]:
        """Get list of enabled widget names."""
        return list(self._enabled)


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

_widget_manager: Optional[WidgetManager] = None


def get_widget_manager() -> WidgetManager:
    """Get the global widget manager instance."""
    global _widget_manager
    if _widget_manager is None:
        _widget_manager = WidgetManager()
        # Register built-in widgets
        _widget_manager.register_builtin(CPUMemoryWidget())
        _widget_manager.register_builtin(ProcessStatusWidget())
        _widget_manager.register_builtin(TasksWidget())
        _widget_manager.register_builtin(DiskWidget())
        _widget_manager.register_builtin(NetworkWidget())
    return _widget_manager


# ---------------------------------------------------------------------------
# Widget template for creation
# ---------------------------------------------------------------------------

WIDGET_TEMPLATE = '''"""
Widget: {name}
Description: {description}

Created by AIOS widget system.
"""
from aios.widgets import WidgetBase, WidgetMetadata, WidgetOutput


class {class_name}Widget(WidgetBase):
    """Custom widget: {description}"""

    @property
    def metadata(self) -> WidgetMetadata:
        return WidgetMetadata(
            name="{name}",
            description="{description}",
            version="1.0.0",
            author="User",
            refresh_seconds=0,  # 0=static, >0=refresh interval in seconds
        )

    def render(self) -> WidgetOutput:
        """Render the widget content.

        Rules:
        - Max 4 lines of output
        - Max 35 characters per line
        - Use Rich styles: cyan, green, yellow, red, dim, bold
        - Handle exceptions gracefully
        - Keep render() fast (<100ms)
        """
        # TODO: Implement your widget logic here
        return WidgetOutput(lines=[
            ("Widget: {name}", "cyan"),
            ("Status: OK", "green"),
        ])
'''


def get_widget_template(name: str, description: str = "") -> str:
    """Get a widget template with the given name."""
    # Convert name to class name (snake_case to PascalCase)
    class_name = ''.join(word.capitalize() for word in name.split('_'))
    return WIDGET_TEMPLATE.format(
        name=name,
        description=description or f"Custom widget {name}",
        class_name=class_name,
    )
