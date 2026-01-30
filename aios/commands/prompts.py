"""
Prompts command for viewing and customizing system prompts.

This is a power user feature that allows advanced users to view
and modify the system prompts that control AIOS behavior.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.box import ROUNDED

if TYPE_CHECKING:
    from ..ui.terminal import TerminalUI
    from ..prompts import PromptManager


POWER_USER_WARNING = """
[bold yellow]WARNING: POWER USER FEATURE[/bold yellow]

System prompts control how AIOS behaves. Modifying them may:
- Break expected functionality
- Cause safety features to malfunction
- Lead to unexpected or harmful behavior

Only proceed if you understand the implications.
"""


class PromptsCommands:
    """Commands for managing system prompts."""

    def __init__(self, ui: "TerminalUI"):
        """Initialize prompts commands.

        Args:
            ui: Terminal UI instance for output
        """
        self.ui = ui
        self.console = ui.console

    def _get_prompt_manager(self) -> "PromptManager":
        """Get the global prompt manager instance."""
        from ..prompts import get_prompt_manager
        return get_prompt_manager()

    def handle_prompts(self, args: str = "") -> bool:
        """Handle /prompts command with subcommands.

        Subcommands:
            (none)      - View current full system prompt
            view <key>  - View a specific section
            sections    - List all sections with enabled/disabled status
            enable <key>  - Enable a disabled section
            disable <key> - Disable a section
            reset       - Reset all sections to defaults
            help        - Show help for prompts command

        Args:
            args: Command arguments

        Returns:
            True to continue shell loop
        """
        parts = args.strip().split(maxsplit=1)
        subcommand = parts[0] if parts else ""
        subargs = parts[1] if len(parts) > 1 else ""

        if not subcommand or subcommand == "view":
            return self._view_prompts(subargs)
        elif subcommand == "sections":
            return self._list_sections()
        elif subcommand == "enable":
            return self._enable_section(subargs)
        elif subcommand == "disable":
            return self._disable_section(subargs)
        elif subcommand == "reset":
            return self._reset_prompts()
        elif subcommand == "help":
            return self._show_help()
        else:
            self.ui.print_error(f"Unknown subcommand: {subcommand}")
            self.ui.print_info("Use '/prompts help' for available commands.")
            return True

    def _view_prompts(self, section_key: str = "") -> bool:
        """View full prompt or a specific section.

        Args:
            section_key: Optional section key to view

        Returns:
            True to continue shell loop
        """
        pm = self._get_prompt_manager()

        if section_key:
            # View specific section
            section = pm.get_section(section_key)
            if not section:
                self.ui.print_error(f"Section '{section_key}' not found.")
                self.ui.print_info("Use '/prompts sections' to see available sections.")
                return True

            status = "[green]enabled[/green]" if section.enabled else "[red]disabled[/red]"
            self.console.print(Panel(
                section.content,
                title=f"[bold]{section.title}[/bold] ({section.key}) - {status}",
                border_style="blue",
                box=ROUNDED,
            ))
        else:
            # View full prompt
            prompt = pm.build_prompt()
            enabled, total = pm.get_enabled_count()

            self.console.print(Panel(
                Syntax(prompt, "markdown", theme="monokai", word_wrap=True),
                title=f"[bold]Full System Prompt[/bold] ({enabled}/{total} sections enabled)",
                border_style="blue",
                box=ROUNDED,
            ))

            # Show token estimate
            token_estimate = len(prompt) // 4  # Rough estimate
            self.console.print(f"\n[dim]Estimated tokens: ~{token_estimate:,}[/dim]")

        return True

    def _list_sections(self) -> bool:
        """List all sections with their status.

        Returns:
            True to continue shell loop
        """
        pm = self._get_prompt_manager()

        table = Table(
            title="System Prompt Sections",
            box=ROUNDED,
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Key", style="bold")
        table.add_column("Title")
        table.add_column("Status")
        table.add_column("Size", justify="right")

        for section in pm.list_sections():
            status = "[green]enabled[/green]" if section.enabled else "[red]disabled[/red]"
            size = f"{len(section.content):,} chars"
            table.add_row(section.key, section.title, status, size)

        self.console.print(table)

        enabled, total = pm.get_enabled_count()
        self.console.print(f"\n[dim]{enabled} of {total} sections enabled[/dim]")
        self.console.print("[dim]Use '/prompts view <key>' to view a section[/dim]")

        return True

    def _enable_section(self, section_key: str) -> bool:
        """Enable a section.

        Args:
            section_key: Section key to enable

        Returns:
            True to continue shell loop
        """
        if not section_key:
            self.ui.print_error("Please specify a section key.")
            self.ui.print_info("Use '/prompts sections' to see available sections.")
            return True

        pm = self._get_prompt_manager()
        section = pm.get_section(section_key)

        if not section:
            self.ui.print_error(f"Section '{section_key}' not found.")
            self.ui.print_info("Use '/prompts sections' to see available sections.")
            return True

        if section.enabled:
            self.ui.print_info(f"Section '{section_key}' is already enabled.")
            return True

        # Show warning and confirm
        self.console.print(POWER_USER_WARNING)
        self.console.print(f"[bold]Enabling section:[/bold] {section.title} ({section_key})")

        from prompt_toolkit import prompt
        try:
            confirm = prompt("Enable this section? (y/n) [n]: ").strip().lower()
            if confirm not in ('y', 'yes'):
                self.ui.print_info("Cancelled.")
                return True
        except (KeyboardInterrupt, EOFError):
            self.console.print()
            self.ui.print_info("Cancelled.")
            return True

        # Enable the section
        pm.enable_section(section_key)
        self._save_prompts_config(pm)
        self.ui.print_success(f"Section '{section_key}' enabled.")
        self.ui.print_info("[dim]Changes take effect on next API call.[/dim]")

        return True

    def _disable_section(self, section_key: str) -> bool:
        """Disable a section.

        Args:
            section_key: Section key to disable

        Returns:
            True to continue shell loop
        """
        if not section_key:
            self.ui.print_error("Please specify a section key.")
            self.ui.print_info("Use '/prompts sections' to see available sections.")
            return True

        pm = self._get_prompt_manager()
        section = pm.get_section(section_key)

        if not section:
            self.ui.print_error(f"Section '{section_key}' not found.")
            self.ui.print_info("Use '/prompts sections' to see available sections.")
            return True

        if not section.enabled:
            self.ui.print_info(f"Section '{section_key}' is already disabled.")
            return True

        # Show warning and confirm
        self.console.print(POWER_USER_WARNING)
        self.console.print(f"[bold]Disabling section:[/bold] {section.title} ({section_key})")
        self.console.print(f"\n[yellow]This section contains:[/yellow]")
        self.console.print(Panel(
            section.content[:500] + ("..." if len(section.content) > 500 else ""),
            border_style="yellow",
        ))

        # Extra warning for critical sections
        critical_sections = {'role', 'safety', 'user_decisions', 'privacy'}
        if section_key in critical_sections:
            self.console.print(
                f"\n[bold red]CRITICAL:[/bold red] The '{section_key}' section is essential "
                f"for proper AIOS operation. Disabling it is strongly discouraged."
            )

        from prompt_toolkit import prompt
        try:
            confirm = prompt("Disable this section? (type 'disable' to confirm): ").strip().lower()
            if confirm != 'disable':
                self.ui.print_info("Cancelled.")
                return True
        except (KeyboardInterrupt, EOFError):
            self.console.print()
            self.ui.print_info("Cancelled.")
            return True

        # Disable the section
        pm.disable_section(section_key)
        self._save_prompts_config(pm)
        self.ui.print_success(f"Section '{section_key}' disabled.")
        self.ui.print_info("[dim]Changes take effect on next API call.[/dim]")

        return True

    def _reset_prompts(self) -> bool:
        """Reset all sections to defaults.

        Returns:
            True to continue shell loop
        """
        pm = self._get_prompt_manager()
        disabled_keys = pm.get_disabled_keys()

        if not disabled_keys:
            self.ui.print_info("All sections are already enabled (default state).")
            return True

        # Show warning and confirm
        self.console.print(POWER_USER_WARNING)
        self.console.print(f"[bold]Resetting to defaults[/bold]")
        self.console.print(f"\nCurrently disabled sections: {', '.join(disabled_keys)}")

        from prompt_toolkit import prompt
        try:
            confirm = prompt("Reset all sections to enabled? (y/n) [n]: ").strip().lower()
            if confirm not in ('y', 'yes'):
                self.ui.print_info("Cancelled.")
                return True
        except (KeyboardInterrupt, EOFError):
            self.console.print()
            self.ui.print_info("Cancelled.")
            return True

        # Reset all sections
        pm.reset()
        self._save_prompts_config(pm)
        self.ui.print_success("All sections reset to enabled.")
        self.ui.print_info("[dim]Changes take effect on next API call.[/dim]")

        return True

    def _save_prompts_config(self, pm: "PromptManager") -> None:
        """Save prompts configuration to user config file.

        Args:
            pm: PromptManager with current state
        """
        from .config import update_toml_value

        disabled_keys = pm.get_disabled_keys()
        user_config = Path.home() / ".config" / "aios" / "config.toml"

        try:
            update_toml_value(user_config, "prompts", "disabled_sections", disabled_keys)
        except Exception as e:
            self.ui.print_warning(f"Could not save config: {e}")
            self.ui.print_info("Changes will be lost when AIOS restarts.")

    def _show_help(self) -> bool:
        """Show help for prompts command.

        Returns:
            True to continue shell loop
        """
        help_text = """
[bold cyan]System Prompts Management[/bold cyan]

System prompts control how AIOS behaves. This is a [bold yellow]power user feature[/bold yellow]
that allows you to view and customize the prompts sent to the AI.

[bold]Commands:[/bold]
  /prompts              View the full current system prompt
  /prompts view <key>   View a specific prompt section
  /prompts sections     List all sections with their status
  /prompts enable <key> Enable a disabled section
  /prompts disable <key> Disable a section (with confirmation)
  /prompts reset        Reset all sections to defaults
  /prompts help         Show this help message

[bold]Section Keys:[/bold]
  role           Core AIOS identity and role definition
  communication  Communication style guidelines
  safety         Safety-first behavior rules
  tools          Tool usage guidelines
  errors         Error handling behavior
  user_decisions Respecting user decisions
  privacy        Privacy and security guidelines
  context        System context and capabilities
  sudo           Sudo and privilege handling
  timeouts       Timeout and long-running operation handling
  background     Background task behavior
  claude_code    Claude Code integration guidance

[bold yellow]Warning:[/bold yellow] Disabling critical sections (role, safety, user_decisions, privacy)
may cause unexpected or unsafe behavior. Only modify if you understand the implications.

[bold]Examples:[/bold]
  /prompts sections        # List all sections
  /prompts view safety     # View the safety section
  /prompts disable background  # Disable background tasks section
  /prompts reset           # Restore all defaults
"""
        self.console.print(Panel(
            help_text,
            title="[bold]Prompts Command Help[/bold]",
            border_style="cyan",
            box=ROUNDED,
        ))

        return True
