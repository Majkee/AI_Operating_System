"""
Terminal UI for AIOS.

Provides a rich, user-friendly terminal interface using the 'rich' library.
Designed to be accessible and clear for non-technical users.
"""

from typing import Optional, List, Any
from pathlib import Path

from collections import deque

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.tree import Tree
from rich.text import Text
from rich.style import Style
from rich.box import ROUNDED
from rich.live import Live

from ..config import get_config


class MultiStepProgress:
    """Display progress for multi-step operations.

    Shows "Step X/Y: description" during tool call chains,
    giving users visibility into overall operation progress.

    Usage:
        with ui.multi_step_progress(total=5) as progress:
            for i, tool in enumerate(tools):
                progress.update(i + 1, f"Running {tool['name']}...")
                # execute tool
    """

    def __init__(self, console: Console, total: int):
        self._console = console
        self._total = total
        self._current = 0
        self._description = ""
        self._progress: Optional[Progress] = None
        self._task_id = None

    def __enter__(self):
        if self._total > 1:  # Only show for multi-step operations
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}[/bold blue]"),
                BarColumn(bar_width=20),
                TextColumn("[dim]{task.percentage:>3.0f}%[/dim]"),
                console=self._console,
                transient=True,
            )
            self._progress.__enter__()
            self._task_id = self._progress.add_task(
                f"Step 0/{self._total}: Starting...",
                total=self._total,
                completed=0
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._progress is not None:
            self._progress.__exit__(exc_type, exc_val, exc_tb)
            if exc_type is None and self._total > 1:
                self._console.print(
                    f"[green]✓[/green] Completed {self._total} operations"
                )
        return False

    def update(self, step: int, description: str) -> None:
        """Update progress to show current step and description."""
        self._current = step
        self._description = description
        if self._progress is not None and self._task_id is not None:
            self._progress.update(
                self._task_id,
                description=f"Step {step}/{self._total}: {description}",
                completed=step - 1,  # Bar shows completed steps
            )

    def step_complete(self) -> None:
        """Mark the current step as complete (advances the progress bar)."""
        if self._progress is not None and self._task_id is not None:
            self._progress.update(
                self._task_id,
                completed=self._current
            )


class StreamingDisplay:
    """Progress display for streaming command output.

    Shows a spinner with progress bar and line count.
    Stores output and offers to show details after completion.
    """

    def __init__(self, console: Console, description: str = "Running...", max_lines: int = 200):
        self._console = console
        self._description = description
        self._max_lines = max_lines
        self._lines: deque = deque(maxlen=max_lines)
        self._total_lines = 0
        self._progress: Optional[Progress] = None
        self._task_id = None
        self._success = True

    def __enter__(self):
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}[/bold blue]"),
            BarColumn(bar_width=30),
            TextColumn("[dim]{task.fields[lines]} lines[/dim]"),
            TimeElapsedColumn(),
            console=self._console,
            transient=True,
        )
        self._progress.__enter__()
        self._task_id = self._progress.add_task(
            self._description,
            total=None,  # Indeterminate
            lines=0
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._progress:
            self._progress.__exit__(exc_type, exc_val, exc_tb)

        # Show completion status
        if exc_type is None:
            self._console.print(
                f"[green]✓[/green] Completed. ({self._total_lines} lines)"
            )
            # Offer to show details if there was significant output
            if self._total_lines > 5:
                self._console.print(
                    f"[dim]  Type 'show' to view output details[/dim]"
                )
                self._store_last_output()
        return False

    def _store_last_output(self) -> None:
        """Store output for later retrieval via 'show' command."""
        # Store in a module-level variable for access
        global _last_streaming_output
        _last_streaming_output = {
            "description": self._description,
            "lines": list(self._lines),
            "total": self._total_lines,
        }

    def add_line(self, line: str) -> None:
        """Add a line of output and update the progress."""
        clean_line = line.rstrip('\r\n')
        if clean_line:  # Skip empty lines
            self._lines.append(clean_line)
        self._total_lines += 1
        if self._progress and self._task_id is not None:
            self._progress.update(
                self._task_id,
                lines=self._total_lines
            )

    def get_output(self) -> str:
        """Get the stored output (last N lines)."""
        return "\n".join(self._lines)

    def mark_failed(self) -> None:
        """Mark the operation as failed."""
        self._success = False


# Module-level storage for last streaming output
_last_streaming_output: Optional[dict] = None


def get_last_streaming_output() -> Optional[dict]:
    """Get the last streaming output for 'show' command."""
    return _last_streaming_output


def clear_last_streaming_output() -> None:
    """Clear the stored streaming output."""
    global _last_streaming_output
    _last_streaming_output = None


class StreamingResponseHandler:
    """Context manager for streaming Claude responses with spinner → live Markdown transition.

    Usage:
        with ui.streaming_response() as handler:
            response = claude.send_message(input, on_text=handler.add_text)
        # After exiting, handler.streamed_text contains the full response
    """

    def __init__(self, console: Console):
        self._console = console
        self._buffer = ""
        self._spinner: Optional[Progress] = None
        self._spinner_task = None
        self._live: Optional[Live] = None
        self._header_printed = False

    def __enter__(self):
        # Start with a spinner
        self._spinner = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            console=self._console,
            transient=True
        )
        self._spinner.__enter__()
        self._spinner_task = self._spinner.add_task("Thinking...", total=None)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Clean up Live display if active
        if self._live is not None:
            self._live.__exit__(exc_type, exc_val, exc_tb)
            self._console.print()  # Add blank line after response
        # Clean up spinner if still active (no text was streamed)
        if self._spinner is not None and self._live is None:
            self._spinner.__exit__(exc_type, exc_val, exc_tb)
        return False

    def add_text(self, delta: str) -> None:
        """Add a text delta to the streaming response."""
        # On first text, transition from spinner to live Markdown
        if not self._header_printed:
            # Stop the spinner
            if self._spinner is not None:
                self._spinner.__exit__(None, None, None)
            # Print the header
            self._console.print()
            self._console.print("[bold green]AIOS:[/bold green]")
            # Start Live display
            self._live = Live(
                Markdown(""),
                console=self._console,
                refresh_per_second=12,
                transient=False
            )
            self._live.__enter__()
            self._header_printed = True

        # Append delta and update display
        self._buffer += delta
        if self._live is not None:
            self._live.update(Markdown(self._buffer))

    @property
    def streamed_text(self) -> str:
        """Return the accumulated streamed text."""
        return self._buffer


class TerminalUI:
    """Rich terminal interface for AIOS."""

    def __init__(self):
        """Initialize the terminal UI."""
        config = get_config()
        self.console = Console(
            force_terminal=True,
            color_system="auto" if config.ui.use_colors else None
        )
        self.show_technical = config.ui.show_technical_details
        self.show_commands = config.ui.show_commands

    def print_welcome(
        self,
        version: str = "",
        skills_count: int = 0,
        tools_count: int = 0,
        recipes_count: int = 0,
        recent_commands: Optional[List[str]] = None,
    ) -> None:
        """Print enhanced welcome message with system info."""
        from rich.console import Group
        from .. import __version__
        ver = version or __version__

        # === LEFT COLUMN: Logo, info, shortcuts, recent ===
        left = Text()

        # ASCII art logo
        left.append(" ╔═╗", style="bold cyan")
        left.append("╦", style="bold blue")
        left.append("╔═╗", style="bold cyan")
        left.append("╔═╗", style="bold green")
        left.append(f"  v{ver}\n", style="dim")
        left.append(" ╠═╣", style="bold cyan")
        left.append("║", style="bold blue")
        left.append("║ ║", style="bold cyan")
        left.append("╚═╗", style="bold green")
        left.append("  AI-powered OS Interface\n", style="dim")
        left.append(" ╩ ╩", style="bold cyan")
        left.append("╩", style="bold blue")
        left.append("╚═╝", style="bold cyan")
        left.append("╚═╝\n\n", style="bold green")

        # Skills info
        if skills_count > 0 or tools_count > 0:
            left.append(" + ", style="cyan")
            parts = []
            if skills_count > 0:
                parts.append(f"{skills_count} skill{'s' if skills_count != 1 else ''}")
            if tools_count > 0:
                parts.append(f"{tools_count} tools")
            if recipes_count > 0:
                parts.append(f"{recipes_count} recipes")
            left.append(" / ".join(parts) + "\n\n", style="white")

        # Keyboard shortcuts
        left.append(" Shortcuts\n", style="bold yellow")
        left.append(" Ctrl+R ", style="cyan")
        left.append("history search\n", style="dim")
        left.append(" Ctrl+B ", style="cyan")
        left.append("background tasks\n", style="dim")
        left.append(" Tab    ", style="cyan")
        left.append("auto-complete\n", style="dim")
        left.append(" Esc+En ", style="cyan")
        left.append("multi-line submit\n", style="dim")

        # Recent commands
        if recent_commands:
            left.append("\n", style="")
            left.append(" Recent\n", style="bold yellow")
            for cmd in recent_commands[:4]:
                display_cmd = cmd[:24] + ".." if len(cmd) > 24 else cmd
                left.append(f" > {display_cmd}\n", style="dim")

        # === RIGHT COLUMN: Examples ===
        right = Text()
        right.append(" What can AIOS do?\n\n", style="bold yellow")

        examples = [
            ("cyan", "Files & Folders", [
                "Show my recent downloads",
                "Find large files over 1GB",
                "Organize my Documents",
            ]),
            ("green", "System", [
                "What's using my disk?",
                "Show running processes",
                "Check system performance",
            ]),
            ("yellow", "Tasks", [
                "Install VS Code",
                "Update all packages",
                "Clean up temp files",
            ]),
            ("magenta", "Info", [
                "What's my IP address?",
                "Show network connections",
                "List USB devices",
            ]),
        ]

        for color, category, items in examples:
            right.append(" * ", style=f"bold {color}")
            right.append(f"{category}\n", style="bold white")
            for item in items:
                right.append("   - ", style="dim")
                right.append(f"{item}\n", style="dim")
            right.append("\n", style="")

        # === BOTTOM: Popular commands (full width) ===
        bottom = Text()

        commands = ["help", "skills", "stats", "history", "sessions", "config", "exit"]

        bottom.append("  ", style="")
        for i, cmd in enumerate(commands):
            bottom.append(cmd, style="cyan")
            if i < len(commands) - 1:
                bottom.append("  ", style="dim")
        bottom.append("\n", style="")

        # Build two-column layout with separator using Table
        layout = Table.grid(expand=True)
        layout.add_column(ratio=1)
        layout.add_column(width=3)  # Separator column
        layout.add_column(ratio=1)

        # Create vertical separator
        sep = Text()
        for _ in range(22):
            sep.append(" | \n", style="dim blue")

        layout.add_row(left, sep, right)

        # Create the panel with columns and bottom section
        welcome = Panel(
            Group(layout, bottom),
            border_style="blue",
            box=ROUNDED,
            padding=(0, 1),
        )
        self.console.print(welcome)
        self.console.print()

    def print_prompt(self) -> None:
        """Print the input prompt."""
        self.console.print("[bold cyan]You:[/bold cyan] ", end="")

    def print_response(self, text: str) -> None:
        """Print an assistant response."""
        self.console.print()
        self.console.print("[bold green]AIOS:[/bold green]")
        # Render as markdown for nice formatting
        self.console.print(Markdown(text))
        self.console.print()

    def print_thinking(self, message: str = "Thinking...") -> Progress:
        """Show a thinking indicator. Returns Progress for context manager use."""
        return Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            console=self.console,
            transient=True
        )

    def print_executing(self, description: str) -> None:
        """Show what's being executed."""
        if self.show_commands:
            self.console.print(f"[dim]⚙️  {description}[/dim]")

    def print_command(self, command: str) -> None:
        """Show the actual command being run (if technical mode enabled)."""
        if self.show_technical:
            self.console.print(Panel(
                Syntax(command, "bash", theme="monokai"),
                title="Command",
                border_style="dim"
            ))

    def print_success(self, message: str) -> None:
        """Print a success message."""
        self.console.print(f"[green]✓[/green] {message}")

    def print_error(self, message: str, technical_details: Optional[str] = None) -> None:
        """Print an error message."""
        self.console.print(f"[red]✗[/red] {message}")
        if technical_details and self.show_technical:
            self.console.print(f"[dim]{technical_details}[/dim]")

    def print_warning(self, message: str) -> None:
        """Print a warning message."""
        self.console.print(f"[yellow]⚠[/yellow] {message}")

    def print_info(self, message: str) -> None:
        """Print an info message."""
        self.console.print(f"[blue]ℹ[/blue] {message}")

    def print_file_list(
        self,
        files: List[Any],
        title: Optional[str] = None,
        show_details: bool = False
    ) -> None:
        """Print a list of files."""
        if not files:
            self.console.print("[dim]No files found[/dim]")
            return

        if show_details:
            table = Table(title=title, box=ROUNDED)
            table.add_column("Name", style="cyan")
            table.add_column("Size", justify="right")
            table.add_column("Modified", style="dim")

            for f in files:
                icon = "📁" if f.is_directory else self._get_file_icon(f.mime_type)
                name = f"{icon} {f.name}"
                size = self._format_size(f.size) if not f.is_directory else ""
                modified = f.modified.strftime("%Y-%m-%d %H:%M")
                table.add_row(name, size, modified)

            self.console.print(table)
        else:
            # Simple grid layout
            items = []
            for f in files:
                icon = "📁" if f.is_directory else self._get_file_icon(f.mime_type)
                items.append(f"{icon} {f.name}")

            # Print in columns
            self.console.print()
            for item in items:
                self.console.print(f"  {item}")
            self.console.print()

    def print_file_tree(self, path: str, files: List[Any], max_depth: int = 2) -> None:
        """Print files as a tree structure."""
        tree = Tree(f"📁 {Path(path).name}")

        for f in files[:20]:  # Limit display
            icon = "📁" if f.is_directory else self._get_file_icon(f.mime_type)
            tree.add(f"{icon} {f.name}")

        if len(files) > 20:
            tree.add(f"[dim]... and {len(files) - 20} more[/dim]")

        self.console.print(tree)

    def print_system_info(self, info: dict) -> None:
        """Print system information in a nice format."""
        table = Table(title="System Information", box=ROUNDED)
        table.add_column("", style="cyan", width=20)
        table.add_column("")

        for key, value in info.items():
            table.add_row(key, str(value))

        self.console.print(table)

    def print_confirmation_request(
        self,
        action: str,
        details: Optional[str] = None,
        warning: Optional[str] = None
    ) -> None:
        """Print a confirmation request."""
        content = f"[bold]{action}[/bold]"
        if details:
            content += f"\n\n{details}"
        if warning:
            content += f"\n\n[yellow]⚠ {warning}[/yellow]"

        panel = Panel(
            content,
            title="Confirm Action",
            border_style="yellow",
            box=ROUNDED
        )
        self.console.print(panel)

    def print_options(self, options: List[str], prompt: str = "Choose an option:") -> None:
        """Print a list of options for the user to choose from."""
        self.console.print(f"\n{prompt}")
        for i, option in enumerate(options, 1):
            self.console.print(f"  [cyan]{i}.[/cyan] {option}")
        self.console.print()

    def print_code(self, code: str, language: str = "python") -> None:
        """Print code with syntax highlighting."""
        self.console.print(Syntax(code, language, theme="monokai", line_numbers=True))

    def print_streaming_output(self, description: str = "Running...") -> StreamingDisplay:
        """Return a StreamingDisplay context manager for live output."""
        return StreamingDisplay(self.console, description)

    def multi_step_progress(self, total: int) -> MultiStepProgress:
        """Return a MultiStepProgress context manager for multi-step operations."""
        return MultiStepProgress(self.console, total)

    def streaming_response(self) -> StreamingResponseHandler:
        """Return a StreamingResponseHandler for streaming Claude responses."""
        return StreamingResponseHandler(self.console)

    def print_output(self, output: str, title: Optional[str] = None) -> None:
        """Print command output."""
        if not output.strip():
            return

        if title:
            panel = Panel(output, title=title, border_style="dim")
            self.console.print(panel)
        else:
            self.console.print(output)

    def print_file_content(
        self,
        content: str,
        filename: str,
        language: Optional[str] = None,
        line_numbers: bool = True
    ) -> None:
        """Print file content with syntax highlighting."""
        if not content:
            self.console.print("[dim]File is empty[/dim]")
            return

        # Auto-detect language from filename
        if language is None:
            ext = Path(filename).suffix.lower()
            language_map = {
                '.py': 'python',
                '.js': 'javascript',
                '.ts': 'typescript',
                '.json': 'json',
                '.yaml': 'yaml',
                '.yml': 'yaml',
                '.xml': 'xml',
                '.html': 'html',
                '.css': 'css',
                '.sh': 'bash',
                '.bash': 'bash',
                '.zsh': 'bash',
                '.md': 'markdown',
                '.sql': 'sql',
                '.rs': 'rust',
                '.go': 'go',
                '.java': 'java',
                '.c': 'c',
                '.cpp': 'cpp',
                '.h': 'c',
                '.hpp': 'cpp',
                '.rb': 'ruby',
                '.php': 'php',
                '.ini': 'ini',
                '.toml': 'toml',
                '.cfg': 'ini',
                '.conf': 'ini',
            }
            language = language_map.get(ext, 'text')

        # Use syntax highlighting for code files
        if language != 'text':
            syntax = Syntax(
                content,
                language,
                theme="monokai",
                line_numbers=line_numbers,
                word_wrap=True
            )
            panel = Panel(
                syntax,
                title=f"📄 {filename}",
                border_style="blue",
                box=ROUNDED
            )
        else:
            # Plain text - just show in a panel
            panel = Panel(
                content,
                title=f"📄 {filename}",
                border_style="dim",
                box=ROUNDED
            )

        self.console.print(panel)

    def print_help(self) -> None:
        """Print help information."""
        help_text = """
## Getting Help

Just talk to me naturally! Here are some things you can ask:

### File Management
- "Show me my Documents folder"
- "Find all my photos"
- "Create a new folder called Projects"
- "Display the contents of config.yaml"

### System Information
- "How much disk space do I have?"
- "What's using my memory?"
- "Show me what's running"

### Applications
- "I need to edit a PDF"
- "Install a text editor"
- "What can I use to play music?"

### Maintenance
- "Update my system"
- "Clean up old files"
- "My computer is running slow"

## Commands

- **exit** / **quit** - Leave AIOS
- **clear** - Clear the screen
- **history** - Show session history
- **help** - Show this message
- **multiline** / **ml** - Toggle multi-line input mode
- **show** - View last command output details

## Keyboard Shortcuts

- **Ctrl+R** - Search command history
- **Ctrl+B** - Open background task browser
- **Tab** - Auto-complete commands
- **Esc+Enter** - Submit in multi-line mode

## Configuration

- **config** - Interactive settings menu
- **model** - List available AI models
- **model <id>** - Switch to a different model

## Skill Commands

- **skills** - List loaded skills
- **tools** - List available tools
- **recipes** - List available recipes/workflows
- **stats** - Show session statistics
- **credentials** - List stored credentials

## Session Commands

- **sessions** - List previous sessions
- **resume <id>** - Resume a previous session

## Coding Tasks

- **code** - Launch Claude Code interactive session
- **code <task>** - Launch Claude Code with an initial prompt
- **code-continue <id>** - Resume a previous code session
- **code-sessions** - List previous code sessions

Examples:
- "code" (opens interactive Claude Code)
- "code build a REST API with Flask"
- "code-continue abc123"

## Recipes

Say trigger phrases to run pre-built workflows:
- "network health check" - Check all network devices
- "backup network configs" - Backup device configurations
- "clean up disk" - Find large files and free space
"""
        self.console.print(Markdown(help_text))

    def clear_screen(self) -> None:
        """Clear the terminal screen."""
        self.console.clear()

    def _get_file_icon(self, mime_type: Optional[str]) -> str:
        """Get an appropriate icon for a file type."""
        if not mime_type:
            return "📄"

        if mime_type.startswith("image/"):
            return "🖼️"
        elif mime_type.startswith("video/"):
            return "🎬"
        elif mime_type.startswith("audio/"):
            return "🎵"
        elif mime_type.startswith("text/"):
            return "📝"
        elif "pdf" in mime_type:
            return "📕"
        elif "zip" in mime_type or "archive" in mime_type:
            return "📦"
        elif "spreadsheet" in mime_type or "excel" in mime_type:
            return "📊"
        elif "presentation" in mime_type or "powerpoint" in mime_type:
            return "📽️"
        elif "document" in mime_type or "word" in mime_type:
            return "📄"
        else:
            return "📄"

    def _format_size(self, size: int) -> str:
        """Format file size in human-readable form."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
