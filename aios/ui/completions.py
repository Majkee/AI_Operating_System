"""
Tab-completion and contextual help for the AIOS shell.

Provides:
- COMMAND_REGISTRY: single source of truth for all shell commands
- AIOSCompleter: custom prompt_toolkit Completer for commands and session IDs
- create_bottom_toolbar: dynamic toolbar factory showing contextual hints
"""

from typing import Callable, Iterable, List, Optional

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

COMMAND_REGISTRY = [
    {
        "name": "exit",
        "aliases": ["quit", "bye", "goodbye"],
        "help": "Exit the AIOS shell",
        "has_arg": False,
    },
    {
        "name": "help",
        "aliases": [],
        "help": "Show available commands and usage",
        "has_arg": False,
    },
    {
        "name": "clear",
        "aliases": [],
        "help": "Clear the terminal screen",
        "has_arg": False,
    },
    {
        "name": "history",
        "aliases": [],
        "help": "Show conversation history for this session",
        "has_arg": False,
    },
    {
        "name": "plugins",
        "aliases": ["/plugins"],
        "help": "List loaded plugins and their tools",
        "has_arg": False,
    },
    {
        "name": "recipes",
        "aliases": ["/recipes"],
        "help": "List available automation recipes",
        "has_arg": False,
    },
    {
        "name": "tools",
        "aliases": ["/tools"],
        "help": "List all available tools (built-in and plugin)",
        "has_arg": False,
    },
    {
        "name": "stats",
        "aliases": ["/stats"],
        "help": "Show session statistics and API usage",
        "has_arg": False,
    },
    {
        "name": "credentials",
        "aliases": ["/credentials"],
        "help": "Manage stored credentials for plugins",
        "has_arg": False,
    },
    {
        "name": "sessions",
        "aliases": ["/sessions"],
        "help": "List previous sessions",
        "has_arg": False,
    },
    {
        "name": "resume",
        "aliases": ["/resume"],
        "help": "Resume a previous session by ID",
        "has_arg": True,
    },
    {
        "name": "tasks",
        "aliases": ["/tasks"],
        "help": "View and manage background tasks (also Ctrl+B)",
        "has_arg": False,
    },
    {
        "name": "model",
        "aliases": ["/model"],
        "help": "Change or view the current Claude model",
        "has_arg": True,
    },
    {
        "name": "code",
        "aliases": ["/code"],
        "help": "Launch Claude Code (optionally with an initial prompt)",
        "has_arg": True,
    },
    {
        "name": "code-continue",
        "aliases": ["/code-continue"],
        "help": "Continue a previous Claude Code session",
        "has_arg": True,
    },
    {
        "name": "code-sessions",
        "aliases": ["/code-sessions"],
        "help": "List previous Claude Code sessions",
        "has_arg": False,
    },
]


def _all_command_names() -> List[str]:
    """Return every command name and alias."""
    names: List[str] = []
    for entry in COMMAND_REGISTRY:
        names.append(entry["name"])
        names.extend(entry["aliases"])
    return names


def _find_entry(name: str):
    """Find the registry entry for a command name or alias."""
    lower = name.lower()
    for entry in COMMAND_REGISTRY:
        if entry["name"] == lower or lower in entry["aliases"]:
            return entry
    return None


# ---------------------------------------------------------------------------
# Completer
# ---------------------------------------------------------------------------

class AIOSCompleter(Completer):
    """Tab-completer for AIOS shell commands.

    Only activates on single-word inputs that look like command prefixes.
    For ``resume``/``/resume`` followed by a space, dynamically fetches
    session IDs via *session_fetcher*.
    """

    def __init__(
        self,
        session_fetcher: Optional[Callable[[], List[str]]] = None,
        code_session_fetcher: Optional[Callable[[], List[str]]] = None,
    ):
        self._session_fetcher = session_fetcher
        self._code_session_fetcher = code_session_fetcher

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        text = document.text_before_cursor

        # --- Dynamic session-ID completion for "resume <prefix>" ---
        lower = text.lower()
        if lower.startswith("resume ") or lower.startswith("/resume "):
            prefix = text.split(" ", 1)[1]
            yield from self._session_completions(prefix)
            return

        # --- Dynamic session-ID completion for "code-continue <prefix>" ---
        if lower.startswith("code-continue ") or lower.startswith("/code-continue "):
            prefix = text.split(" ", 1)[1]
            yield from self._code_session_completions(prefix)
            return

        # --- Only complete single-word (no spaces) command prefixes ---
        if " " in text:
            return

        word = text.lower()

        # Don't complete on empty input
        if not word:
            return

        for entry in COMMAND_REGISTRY:
            # Match the primary name
            if entry["name"].startswith(word):
                yield Completion(
                    entry["name"],
                    start_position=-len(text),
                    display_meta=entry["help"],
                )
            # Match aliases (e.g. /plugins)
            for alias in entry["aliases"]:
                if alias.startswith(word) and alias != entry["name"]:
                    yield Completion(
                        alias,
                        start_position=-len(text),
                        display_meta=entry["help"],
                    )

    # ------------------------------------------------------------------

    def _session_completions(self, prefix: str) -> Iterable[Completion]:
        if self._session_fetcher is None:
            return
        try:
            session_ids = self._session_fetcher()
        except Exception:
            return
        for sid in session_ids:
            if sid.lower().startswith(prefix.lower()):
                yield Completion(
                    sid,
                    start_position=-len(prefix),
                    display_meta="session",
                )

    def _code_session_completions(self, prefix: str) -> Iterable[Completion]:
        if self._code_session_fetcher is None:
            return
        try:
            session_ids = self._code_session_fetcher()
        except Exception:
            return
        for sid in session_ids:
            if sid.lower().startswith(prefix.lower()):
                yield Completion(
                    sid,
                    start_position=-len(prefix),
                    display_meta="code session",
                )


# ---------------------------------------------------------------------------
# Bottom toolbar
# ---------------------------------------------------------------------------

def _compute_left_toolbar(text: str) -> str:
    """Return the left-side toolbar HTML string based on current input text."""
    if not text:
        return (
            "<b>Tab</b> command completion · "
            "Type a command or ask anything"
        )

    lower = text.lower()

    # Exact command match – show its help
    entry = _find_entry(lower)
    if entry:
        return f"<b>{entry['name']}</b>: {entry['help']}"

    # "resume " with no ID yet
    if lower in ("resume", "/resume") or lower.endswith("resume "):
        return (
            "<b>resume</b>: Enter a session ID · "
            "Press <b>Tab</b> to see available sessions"
        )

    # Partial match – list matching commands
    matches = []
    for e in COMMAND_REGISTRY:
        if e["name"].startswith(lower):
            matches.append(e["name"])
        for alias in e["aliases"]:
            if alias.startswith(lower):
                matches.append(alias)

    if matches:
        joined = ", ".join(matches[:5])
        return f"Matches: <b>{joined}</b> · Press <b>Tab</b> to complete"

    # Free-form text – likely a natural-language query
    return "Press <b>Enter</b> to send to AI assistant"


def create_bottom_toolbar(prompt_session, task_manager=None):
    """Return a callable suitable for ``PromptSession.prompt(bottom_toolbar=...)``.

    The toolbar text updates dynamically based on the current input buffer.
    When *task_manager* is provided, running/finished task counts and a
    Ctrl+B hint are shown on the right side of the toolbar.
    """

    def _toolbar():
        buf = prompt_session.app.current_buffer
        text = buf.text.strip() if buf else ""
        left = _compute_left_toolbar(text)

        right = ""
        if task_manager is not None:
            running = task_manager.running_count()
            unnotified = len(task_manager.get_unnotified_completions())
            parts = []
            if running > 0:
                parts.append(
                    f"<b>{running}</b> task{'s' if running != 1 else ''} running"
                )
            if unnotified > 0:
                parts.append(f"<b>{unnotified}</b> finished")
            if parts:
                right = " | ".join(parts) + " · <b>Ctrl+B</b> tasks"
            elif task_manager.list_tasks():
                right = "<b>Ctrl+B</b> tasks"

        if right:
            return HTML(f"{left}  ·  {right}")
        return HTML(left)

    return _toolbar
