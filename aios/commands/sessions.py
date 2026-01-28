"""
Session commands for AIOS.

Handles session listing, resumption, and history restoration.
"""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..context.session import SessionManager
    from ..claude.client import ClaudeClient
    from ..ui.terminal import TerminalUI


class SessionCommands:
    """Commands for session management."""

    def __init__(
        self,
        ui: "TerminalUI",
        session_manager: "SessionManager",
    ):
        self.ui = ui
        self.session = session_manager

    def show_sessions(self) -> None:
        """Display previous sessions."""
        sessions = self.session.list_sessions(limit=10)

        if not sessions:
            self.ui.print_info("No previous sessions found.")
            return

        self.ui.console.print("\n[bold cyan]Previous Sessions[/bold cyan]\n")

        for sess in sessions:
            session_id = sess['session_id']
            started = sess['started_at']
            msg_count = sess['message_count']

            # Format the date nicely
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(started)
                formatted_date = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError, AttributeError):
                # Fallback for malformed date strings
                formatted_date = started[:16] if started else "?"

            self.ui.console.print(
                f"  [green]●[/green] [bold]{session_id}[/bold]"
            )
            self.ui.console.print(
                f"    [dim]Started: {formatted_date} | Messages: {msg_count}[/dim]"
            )

        self.ui.console.print()
        self.ui.print_info("Use 'resume <session_id>' to continue a previous session.")

    def resume_session(self, session_id: str, claude: Optional["ClaudeClient"] = None) -> None:
        """Resume a previous session."""
        # Try to load the session
        loaded_session = self.session.load_session(session_id)

        if loaded_session is None:
            self.ui.print_error(f"Session '{session_id}' not found.")
            self.ui.print_info("Use '/sessions' to list available sessions.")
            return

        self.ui.print_success(f"Resumed session: {session_id}")

        # Show session info
        msg_count = len(loaded_session.messages)
        self.ui.print_info(f"Session has {msg_count} message(s) in history.")

        # Show recent conversation context
        if msg_count > 0:
            self.ui.console.print("\n[bold]Recent conversation:[/bold]")
            recent_messages = loaded_session.messages[-5:]  # Last 5 messages
            for msg in recent_messages:
                role = "[cyan]You[/cyan]" if msg.role == "user" else "[green]AIOS[/green]"
                preview = msg.content[:100]
                if len(msg.content) > 100:
                    preview += "..."
                self.ui.console.print(f"  {role}: {preview}")
            self.ui.console.print()

        # Restore Claude conversation history if available
        if claude and msg_count > 0:
            self._restore_claude_history(loaded_session.messages, claude)
            self.ui.print_info("Conversation history restored.")

    def _restore_claude_history(self, messages, claude: "ClaudeClient") -> None:
        """Restore Claude conversation history from session messages."""
        # Clear current conversation history
        claude.clear_history()

        # Add messages to conversation history
        for msg in messages[-20:]:  # Keep last 20 messages for context
            if msg.role == "user":
                claude.conversation_history.append({
                    "role": "user",
                    "content": msg.content,
                })
            elif msg.role == "assistant":
                claude.conversation_history.append({
                    "role": "assistant",
                    "content": msg.content,
                })
