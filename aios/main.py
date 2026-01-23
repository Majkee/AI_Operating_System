"""
AIOS main entry point.

This module provides the CLI interface for launching AIOS.
"""

import sys
import argparse
from pathlib import Path


def main():
    """Main entry point for AIOS."""
    parser = argparse.ArgumentParser(
        description="AIOS - AI-powered Operating System Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  aios                    Start interactive session
  aios --version          Show version
  aios --setup            Run first-time setup
  aios "show my files"    Run a single command

For more information, visit: https://github.com/your-org/aios
        """
    )

    parser.add_argument(
        "--version", "-v",
        action="store_true",
        help="Show version information"
    )

    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run first-time setup wizard"
    )

    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (show technical details)"
    )

    parser.add_argument(
        "command",
        nargs="*",
        help="Optional command to run (non-interactive mode)"
    )

    args = parser.parse_args()

    # Handle version
    if args.version:
        from . import __version__
        print(f"AIOS version {__version__}")
        return 0

    # Handle setup
    if args.setup:
        return run_setup()

    # Set debug mode
    if args.debug:
        import os
        os.environ["AIOS_DEBUG"] = "1"

    # Handle single command mode
    if args.command:
        return run_single_command(" ".join(args.command))

    # Run interactive shell
    from .shell import AIOSShell
    shell = AIOSShell()
    return shell.run()


def run_setup():
    """Run first-time setup wizard."""
    from rich.console import Console
    from rich.panel import Panel
    from prompt_toolkit import prompt

    console = Console()

    console.print(Panel(
        "[bold green]AIOS Setup Wizard[/bold green]\n\n"
        "Let's get AIOS configured for your system.",
        border_style="green"
    ))

    # Check for API key
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        console.print("\n[yellow]No API key found.[/yellow]")
        console.print("You'll need an Anthropic API key to use AIOS.")
        console.print("Get one at: https://console.anthropic.com/\n")

        try:
            api_key = prompt("Enter your API key (or press Enter to skip): ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\nSetup cancelled.")
            return 1

        if api_key:
            # Save to user config
            config_dir = Path.home() / ".config" / "aios"
            config_dir.mkdir(parents=True, exist_ok=True)

            config_file = config_dir / "config.toml"
            with open(config_file, "w") as f:
                f.write(f'[api]\napi_key = "{api_key}"\n')

            console.print(f"[green]✓[/green] API key saved to {config_file}")
        else:
            console.print("[dim]Skipped. Set ANTHROPIC_API_KEY environment variable later.[/dim]")

    else:
        console.print("[green]✓[/green] API key found in environment")

    # Create directories
    dirs_to_create = [
        Path.home() / ".config" / "aios",
        Path.home() / ".config" / "aios" / "history",
    ]

    for d in dirs_to_create:
        d.mkdir(parents=True, exist_ok=True)

    console.print("[green]✓[/green] Configuration directories created")

    # Done
    console.print(Panel(
        "[bold green]Setup complete![/bold green]\n\n"
        "Run [cyan]aios[/cyan] to start your AI assistant.",
        border_style="green"
    ))

    return 0


def run_single_command(command: str) -> int:
    """Run a single command and exit."""
    from .shell import AIOSShell

    shell = AIOSShell()

    try:
        shell.claude = __import__("aios.claude.client", fromlist=["ClaudeClient"]).ClaudeClient(
            shell.tool_handler
        )
    except ValueError as e:
        shell.ui.print_error(str(e))
        return 1

    # Process the command
    shell._handle_user_input(command)
    return 0


if __name__ == "__main__":
    sys.exit(main())
