"""
AIOS main entry point.

This module provides the CLI interface for launching AIOS.
"""

import sys
import os
import argparse
import webbrowser
from pathlib import Path
from typing import Optional


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

For more information, visit: https://github.com/Majkee/AI_Operating_System
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
        os.environ["AIOS_DEBUG"] = "1"

    # Handle single command mode
    if args.command:
        return run_single_command(" ".join(args.command))

    # Run interactive shell
    from .shell import AIOSShell
    shell = AIOSShell()
    return shell.run()


def _check_api_key() -> tuple[Optional[str], str]:
    """
    Check for API key in various locations.
    
    Returns:
        Tuple of (api_key, source) where source describes where it was found.
    """
    # Check environment variables
    api_key = os.environ.get("AIOS_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return api_key, "environment variable"

    # Check .env file in current directory
    env_file = Path(".env")
    if env_file.exists():
        try:
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#"):
                        continue
                    if "ANTHROPIC_API_KEY" in line or "AIOS_API_KEY" in line:
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            key_value = parts[1].strip().strip('"').strip("'")
                            if key_value and key_value != "your-api-key-here":
                                return key_value, ".env file"
        except Exception:
            pass

    # Check user config file
    config_file = Path.home() / ".config" / "aios" / "config.toml"
    if config_file.exists():
        try:
            if sys.version_info >= (3, 11):
                import tomllib
            else:
                import tomli as tomllib

            with open(config_file, "rb") as f:
                config_data = tomllib.load(f)
                api_key = config_data.get("api", {}).get("api_key")
                if api_key:
                    return api_key, "config file"
        except Exception:
            pass
    
    return None, ""


def run_setup():
    """Run first-time setup wizard."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from prompt_toolkit import prompt
    from .models import AVAILABLE_MODELS, get_default_model

    console = Console()

    console.print(Panel(
        "[bold green]AIOS Setup Wizard[/bold green]\n\n"
        "Let's get AIOS configured for your system.",
        border_style="green"
    ))

    # Check for API key
    api_key, key_source = _check_api_key()

    if not api_key:
        console.print("\n[yellow]⚠ No API key found[/yellow]")
        console.print("\nYou'll need an Anthropic API key to use AIOS.")
        console.print("\n[bold]Where to get your API key:[/bold]")
        console.print("  • Visit: [cyan]https://console.anthropic.com/[/cyan]")
        console.print("  • Sign up or log in to your Anthropic account")
        console.print("  • Navigate to API Keys section")
        console.print("  • Create a new API key")
        
        try:
            open_browser_input = prompt("Would you like to open the API key page in your browser? (y/n) [n]: ").strip().lower()
            if open_browser_input in ('y', 'yes'):
                console.print("[dim]Opening browser...[/dim]")
                webbrowser.open("https://console.anthropic.com/")
        except (KeyboardInterrupt, EOFError):
            pass

        console.print("\n[bold]You can set your API key in one of these ways:[/bold]")
        console.print("  1. Environment variable: [cyan]ANTHROPIC_API_KEY[/cyan] or [cyan]AIOS_API_KEY[/cyan]")
        console.print("  2. .env file: Create a [cyan].env[/cyan] file with [cyan]ANTHROPIC_API_KEY=your-key[/cyan]")
        console.print("  3. Config file: We'll save it to your config file now\n")

        try:
            api_key = prompt("Enter your API key (or press Enter to skip): ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\nSetup cancelled.")
            return 1

        if not api_key:
            console.print("[yellow]⚠ Skipped. You'll need to set your API key before using AIOS.[/yellow]")
            console.print("\nYou can set it later by:")
            console.print("  • Running [cyan]aios --setup[/cyan] again")
            console.print("  • Setting [cyan]ANTHROPIC_API_KEY[/cyan] environment variable")
            console.print("  • Adding it to [cyan]~/.config/aios/config.toml[/cyan]")
    else:
        console.print(f"\n[green]✓[/green] API key found in [cyan]{key_source}[/cyan]")
        console.print("[dim]Your API key is ready to use![/dim]\n")

    # Model selection
    console.print("\n[bold]Choose your Claude model:[/bold]\n")
    
    # Create a table showing available models
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Model", style="bold")
    table.add_column("Speed", width=10)
    table.add_column("Cost", width=10)
    table.add_column("Description", style="dim")
    
    for idx, model in enumerate(AVAILABLE_MODELS, 1):
        speed_emoji = "⚡" if model.speed == "fast" else "⏱️" if model.speed == "medium" else "🐌"
        cost_emoji = "💰" if model.cost == "low" else "💵" if model.cost == "medium" else "💸"
        table.add_row(
            str(idx),
            model.name,
            f"{speed_emoji} {model.speed}",
            f"{cost_emoji} {model.cost}",
            model.description
        )
    
    console.print(table)
    console.print()

    default_model = get_default_model()
    default_idx = next((i for i, m in enumerate(AVAILABLE_MODELS, 1) if m.id == default_model), 1)

    try:
        model_choice = prompt(
            f"Select model (1-{len(AVAILABLE_MODELS)}) [default: {default_idx}]: "
        ).strip()
        
        if not model_choice:
            model_choice = str(default_idx)
        
        model_idx = int(model_choice) - 1
        if 0 <= model_idx < len(AVAILABLE_MODELS):
            selected_model = AVAILABLE_MODELS[model_idx]
            console.print(f"[green]✓[/green] Selected: [bold]{selected_model.name}[/bold]")
        else:
            console.print(f"[yellow]Invalid choice, using default: {AVAILABLE_MODELS[default_idx - 1].name}[/yellow]")
            selected_model = AVAILABLE_MODELS[default_idx - 1]
    except (ValueError, KeyboardInterrupt, EOFError):
        console.print(f"[yellow]Using default model: {AVAILABLE_MODELS[default_idx - 1].name}[/yellow]")
        selected_model = AVAILABLE_MODELS[default_idx - 1]

    # Save configuration
    config_dir = Path.home() / ".config" / "aios"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.toml"

    # Read existing config if it exists
    config_content = {}
    if config_file.exists():
        try:
            if sys.version_info >= (3, 11):
                import tomllib
            else:
                import tomli as tomllib

            with open(config_file, "rb") as f:
                config_content = tomllib.load(f)
        except Exception:
            pass

    # Update config
    if "api" not in config_content:
        config_content["api"] = {}
    
    if api_key:
        config_content["api"]["api_key"] = api_key
    config_content["api"]["model"] = selected_model.id
    
    # Mark setup as complete
    config_content["setup_complete"] = True

    # Write config file
    try:
        import tomli_w
        with open(config_file, "wb") as f:
            tomli_w.dump(config_content, f)
        console.print(f"[green]✓[/green] Configuration saved to {config_file}")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save config: {e}")
        return 1

    # Create directories
    dirs_to_create = [
        config_dir,
        config_dir / "history",
    ]

    for d in dirs_to_create:
        d.mkdir(parents=True, exist_ok=True)

    console.print("[green]✓[/green] Configuration directories created")

    # Done
    console.print(Panel(
        "[bold green]Setup complete![/bold green]\n\n"
        f"Model: [cyan]{selected_model.name}[/cyan]\n"
        f"API Key: [cyan]{'Configured' if api_key else 'Not set - please configure before use'}[/cyan]\n\n"
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
