"""
Claude Code integration commands for AIOS.

Handles launching, resuming, and managing Claude Code sessions.
"""

from typing import Optional, Any, TYPE_CHECKING
from pathlib import Path

from .config import update_toml_value

if TYPE_CHECKING:
    from ..code import CodeRunner
    from ..safety.audit import AuditLogger
    from ..ui.terminal import TerminalUI


class CodeCommands:
    """Commands for Claude Code integration."""

    def __init__(
        self,
        ui: "TerminalUI",
        code_runner: "CodeRunner",
        audit: "AuditLogger",
        config: Any,
    ):
        self.ui = ui
        self.code_runner = code_runner
        self.audit = audit
        self.config = config
        self._code_available: Optional[bool] = None  # Lazy check

    def run_code_task(self, prompt: Optional[str] = None, session_id: Optional[str] = None) -> None:
        """Launch an interactive Claude Code session."""
        from ..safety.audit import ActionType

        # Lazy availability check
        if self._code_available is None:
            self._code_available = self.code_runner.is_available()

        if not self._code_available:
            self.ui.print_error("Claude Code is not available.")
            self.ui.print_info(self.code_runner.get_install_instructions())
            self.ui.print_info("[dim]If you install it during this session, restart AIOS to detect it.[/dim]")
            return

        # Ensure auth mode is chosen
        self._ensure_code_auth_mode()

        code_cfg = getattr(self.config, 'code', None)
        cwd = None
        if code_cfg and code_cfg.default_working_directory:
            cwd = code_cfg.default_working_directory
        if cwd is None:
            cwd = str(Path.home())

        auth_mode = code_cfg.auth_mode if code_cfg else None

        self.ui.console.print()
        self.ui.print_info("Launching Claude Code...")
        self.ui.print_info("[dim]You'll return to AIOS when you exit.[/dim]")
        self.ui.console.print()

        result = self.code_runner.launch_interactive(
            prompt=prompt,
            working_directory=cwd,
            session_id=session_id,
            auth_mode=auth_mode,
        )

        self.ui.console.print()
        if result.success:
            self.ui.print_success("Claude Code session ended.")
        else:
            self.ui.print_error(result.error or "Claude Code session failed.")

        if result.session_id:
            self.ui.print_info(f"[dim]Session ID: {result.session_id}[/dim]")

        # Audit
        self.audit.log(
            ActionType.COMMAND,
            f"Code session: {(prompt or 'interactive')[:80]}",
            success=result.success,
            details={"session_id": result.session_id or session_id},
        )

    def _ensure_code_auth_mode(self) -> None:
        """Prompt the user to choose an auth mode if not already set."""
        code_cfg = getattr(self.config, 'code', None)
        if code_cfg and code_cfg.auth_mode:
            return

        self.ui.console.print()
        self.ui.console.print("[bold cyan]Claude Code Authentication[/bold cyan]")
        self.ui.console.print()
        self.ui.console.print("  [cyan]1.[/cyan] API Key — use your ANTHROPIC_API_KEY")
        self.ui.console.print("  [cyan]2.[/cyan] Subscription — use your paid Claude subscription login")
        self.ui.console.print()

        try:
            choice = input("Choose auth mode (1 or 2) [1]: ").strip()
        except (KeyboardInterrupt, EOFError):
            choice = "1"

        auth_mode = "subscription" if choice == "2" else "api_key"

        # Save to user config
        self._save_code_auth_mode(auth_mode)

        # Update in-memory config
        if code_cfg:
            code_cfg.auth_mode = auth_mode

        self.ui.print_success(f"Auth mode set to: {auth_mode}")

    def _save_code_auth_mode(self, auth_mode: str) -> None:
        """Persist auth_mode to the user config file."""
        config_file = Path.home() / ".config" / "aios" / "config.toml"
        try:
            update_toml_value(config_file, "code", "auth_mode", f'"{auth_mode}"')
        except Exception as e:
            self.ui.print_warning(f"Could not save auth mode to config: {e}")

    def continue_code_session(self, args: str) -> None:
        """Continue a previous Claude Code session."""
        parts = args.split(None, 1)
        if not parts:
            self.ui.print_info("Usage: code-continue <session_id> [prompt]")
            return

        sid = parts[0]
        prompt = parts[1] if len(parts) > 1 else None

        session = self.code_runner.get_session(sid)
        if session is None:
            self.ui.print_error(f"Code session '{sid}' not found.")
            self.ui.print_info("Use 'code-sessions' to list available sessions.")
            return

        self.ui.print_info(f"Resuming code session: {sid}")
        self.run_code_task(prompt=prompt, session_id=sid)

    def show_code_sessions(self) -> None:
        """Display previous Claude Code sessions."""
        sessions = self.code_runner.get_sessions(limit=20)

        if not sessions:
            self.ui.print_info("No previous code sessions found.")
            self.ui.print_info("Use 'code <task>' to start a coding session.")
            return

        from datetime import datetime
        from rich.table import Table
        from rich.box import ROUNDED

        table = Table(title="Claude Code Sessions", box=ROUNDED)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Date", style="dim")
        table.add_column("Task", max_width=40)
        table.add_column("Directory", style="dim", max_width=30)

        for sess in sessions:
            try:
                dt = datetime.fromtimestamp(sess.created_at)
                formatted_date = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError, OSError):
                # Fallback for invalid timestamps
                formatted_date = "?"

            table.add_row(
                sess.session_id,
                formatted_date,
                sess.prompt_summary[:40],
                sess.working_directory,
            )

        self.ui.console.print()
        self.ui.console.print(table)
        self.ui.console.print()
        self.ui.print_info("Use 'code-continue <id> <prompt>' to resume a session.")
