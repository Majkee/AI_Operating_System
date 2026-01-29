"""Widget management commands for AIOS."""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..ui.terminal import TerminalUI
    from ..widgets import WidgetManager


class WidgetCommands:
    """Commands for managing welcome screen widgets."""

    def __init__(self, ui: "TerminalUI", widget_manager: "WidgetManager"):
        self.ui = ui
        self.widget_manager = widget_manager
        self.widgets_dir = Path.home() / ".config" / "aios" / "widgets"

    def handle_widgets(self, args: str = "") -> None:
        """Handle widget commands.

        Usage:
            widgets              - List all widgets
            widgets list         - List all widgets
            widgets enable NAME  - Enable a widget
            widgets disable NAME - Disable a widget
            widgets create NAME  - Create a new widget template
        """
        parts = args.split(None, 1)
        subcommand = parts[0].lower() if parts else "list"
        arg = parts[1].strip() if len(parts) > 1 else ""

        if subcommand == "list":
            self._list_widgets()
        elif subcommand == "enable":
            if not arg:
                self.ui.print_error("Usage: widgets enable <widget_name>")
                return
            self._enable_widget(arg)
        elif subcommand == "disable":
            if not arg:
                self.ui.print_error("Usage: widgets disable <widget_name>")
                return
            self._disable_widget(arg)
        elif subcommand == "create":
            if not arg:
                self.ui.print_error("Usage: widgets create <widget_name>")
                return
            self._create_widget(arg)
        elif subcommand == "reload":
            self._reload_widgets()
        else:
            self.ui.print_error(f"Unknown subcommand: {subcommand}")
            self.ui.print_info("Available: list, enable, disable, create, reload")

    def _list_widgets(self) -> None:
        """List all available widgets."""
        widgets = self.widget_manager.list_widgets()

        if not widgets:
            self.ui.print_info("No widgets available.")
            return

        self.ui.console.print("\n[bold cyan]Available Widgets[/bold cyan]\n")

        for meta in widgets:
            is_enabled = self.widget_manager.is_enabled(meta.name)
            status = "[green]enabled[/green]" if is_enabled else "[dim]disabled[/dim]"
            self.ui.console.print(f"  [cyan]{meta.name:16}[/cyan] {status}")
            self.ui.console.print(f"  [dim]{meta.description}[/dim]\n")

        self.ui.console.print("[dim]Use 'widgets enable <name>' or 'widgets disable <name>' to toggle[/dim]")

    def _enable_widget(self, name: str) -> None:
        """Enable a widget by name."""
        if self.widget_manager.enable_widget(name):
            self.ui.print_success(f"Widget '{name}' enabled.")
            self.ui.print_info("Restart AIOS or run 'clear' to see changes in welcome screen.")
        else:
            self.ui.print_error(f"Widget '{name}' not found.")
            available = [w.name for w in self.widget_manager.list_widgets()]
            if available:
                self.ui.print_info(f"Available widgets: {', '.join(available)}")

    def _disable_widget(self, name: str) -> None:
        """Disable a widget by name."""
        if self.widget_manager.disable_widget(name):
            self.ui.print_success(f"Widget '{name}' disabled.")
        else:
            if name in [w.name for w in self.widget_manager.list_widgets()]:
                self.ui.print_info(f"Widget '{name}' is already disabled.")
            else:
                self.ui.print_error(f"Widget '{name}' not found.")

    def _create_widget(self, name: str) -> None:
        """Create a new widget template."""
        from ..widgets import get_widget_template

        # Validate name
        if not name.replace('_', '').isalnum():
            self.ui.print_error("Widget name must be alphanumeric with underscores only.")
            return

        # Ensure widgets directory exists
        self.widgets_dir.mkdir(parents=True, exist_ok=True)

        # Check if already exists
        widget_path = self.widgets_dir / f"{name}.py"
        if widget_path.exists():
            self.ui.print_error(f"Widget '{name}' already exists at {widget_path}")
            return

        # Create template
        template = get_widget_template(name)
        widget_path.write_text(template)

        self.ui.print_success(f"Widget template created: {widget_path}")
        self.ui.console.print("\n[bold cyan]Next steps:[/bold cyan]")
        self.ui.console.print(f"  1. Edit the widget file: [cyan]{widget_path}[/cyan]")
        self.ui.console.print("  2. Implement the render() method")
        self.ui.console.print("  3. Run 'widgets reload' to load it")
        self.ui.console.print(f"  4. Run 'widgets enable {name}' to show it\n")

        self.ui.console.print("[bold yellow]Widget Rules:[/bold yellow]")
        self.ui.console.print("  - Max 4 lines of output")
        self.ui.console.print("  - Max 35 characters per line")
        self.ui.console.print("  - Use styles: cyan, green, yellow, red, dim, bold")
        self.ui.console.print("  - Keep render() fast (<100ms)")

    def _reload_widgets(self) -> None:
        """Reload widgets from disk."""
        loaded = self.widget_manager.load_all()
        if loaded:
            self.ui.print_success(f"Loaded {len(loaded)} widget(s): {', '.join(loaded)}")
        else:
            self.ui.print_info("No new widgets found.")
