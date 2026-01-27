"""
Terminal UI for AIOS.

Provides a rich, user-friendly terminal interface using the 'rich' library.
Designed to be accessible and clear for non-technical users.
"""

from typing import Optional, List, Any
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.tree import Tree
from rich.text import Text
from rich.style import Style
from rich.box import ROUNDED

from ..config import get_config


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

    def print_welcome(self) -> None:
        """Print welcome message."""
        welcome = Panel(
            "[bold green]Welcome to AIOS[/bold green]\n\n"
            "I'm your AI assistant. Just tell me what you'd like to do!\n\n"
            "[dim]Examples:[/dim]\n"
            "  • \"Show me my photos\"\n"
            "  • \"What's using up my disk space?\"\n"
            "  • \"Help me organize my Downloads folder\"\n\n"
            "[dim]Type 'exit' or 'quit' to leave, 'help' for more options[/dim]",
            title="🖥️  AIOS",
            border_style="blue",
            box=ROUNDED
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

## Plugin Commands

- **plugins** - List loaded plugins
- **tools** - List available tools
- **recipes** - List available recipes/workflows
- **stats** - Show session statistics
- **credentials** - List stored credentials

## Session Commands

- **sessions** - List previous sessions
- **resume <id>** - Resume a previous session

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
