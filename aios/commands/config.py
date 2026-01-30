"""
Configuration commands for AIOS.

Handles interactive config menu, model selection, and TOML updates.
"""

from typing import Optional, Any, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from ..ui.terminal import TerminalUI
    from ..providers.base import BaseClient


def update_toml_value(config_path: Path, section: str, key: str, value: str) -> None:
    """Update a single key in a TOML config file, preserving comments and formatting.

    *value* must already be a TOML-formatted literal (e.g. ``'"api_key"'`` for
    a string, ``'true'`` for a boolean).
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        config_path.write_text(f"[{section}]\n{key} = {value}\n")
        return

    lines = config_path.read_text().splitlines(keepends=True)
    section_header = f"[{section}]"
    in_section = False
    key_found = False
    insert_idx: Optional[int] = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Detect section headers
        if stripped.startswith("[") and not stripped.startswith("[["):
            if in_section and not key_found:
                # We left the target section without finding the key - insert before this line
                insert_idx = i
                break
            in_section = stripped == section_header
            continue
        if in_section:
            # Match key = ... (allowing whitespace)
            if stripped.startswith(f"{key} ") or stripped.startswith(f"{key}="):
                lines[i] = f"{key} = {value}\n"
                key_found = True
                break

    if not key_found:
        new_line = f"{key} = {value}\n"
        if insert_idx is not None:
            # Insert at end of the target section (before the next section header)
            lines.insert(insert_idx, new_line)
        elif in_section:
            # Section was the last in the file - append
            # Ensure trailing newline before appending
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(new_line)
        else:
            # Section doesn't exist - append it
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(f"\n{section_header}\n")
            lines.append(new_line)

    config_path.write_text("".join(lines))


class ConfigCommands:
    """Commands for configuration management."""

    def __init__(self, ui: "TerminalUI", config: Any):
        self.ui = ui
        self.config = config

    def interactive_config(self, client: Optional["BaseClient"] = None) -> None:
        """Interactive configuration menu."""
        from rich.table import Table
        from rich.box import ROUNDED
        from prompt_toolkit import prompt
        from ..models import AVAILABLE_MODELS, get_model_by_id
        from ..config import reset_config, get_config

        # Define all configurable settings
        # Format: (key, section, config_key, type, description, options_func)
        # options_func returns list of (value, label) for selection, or None for free input
        settings = [
            ("api.streaming", "api", "streaming", "bool",
             "Stream responses word-by-word", None),
            ("api.model", "api", "model", "choice",
             "AI model to use",
             lambda: [(m.id, f"{m.name} ({m.speed}, {m.cost} cost)") for m in AVAILABLE_MODELS]),
            ("api.max_tokens", "api", "max_tokens", "int",
             "Max tokens per response (100-100000)", None),
            ("api.context_budget", "api", "context_budget", "int",
             "Max tokens for history (50000-200000)", None),
            ("api.summarize_threshold", "api", "summarize_threshold", "choice",
             "Summarize at % of context budget",
             lambda: [
                 (0.5, "50% (aggressive)"),
                 (0.6, "60%"),
                 (0.7, "70%"),
                 (0.75, "75% (default)"),
                 (0.8, "80%"),
                 (0.85, "85%"),
                 (0.9, "90% (conservative)"),
             ]),
            ("api.min_recent_messages", "api", "min_recent_messages", "choice",
             "Keep recent messages unsummarized",
             lambda: [
                 (2, "2 messages (minimal)"),
                 (4, "4 messages"),
                 (6, "6 messages (default)"),
                 (8, "8 messages"),
                 (10, "10 messages"),
                 (15, "15 messages"),
                 (20, "20 messages (max context)"),
             ]),
            ("ui.show_technical_details", "ui", "show_technical_details", "bool",
             "Show technical details and commands", None),
            ("ui.show_commands", "ui", "show_commands", "bool",
             "Show commands being executed", None),
            ("ui.use_colors", "ui", "use_colors", "bool",
             "Use colors in terminal output", None),
            ("safety.require_confirmation", "safety", "require_confirmation", "bool",
             "Require confirmation for dangerous commands", None),
            ("code.enabled", "code", "enabled", "bool",
             "Enable Claude Code integration", None),
            ("code.auto_detect", "code", "auto_detect", "bool",
             "Auto-detect and route coding requests", None),
        ]

        def get_current_value(key: str):
            """Get current value for a setting."""
            parts = key.split(".")
            obj = self.config
            for part in parts:
                obj = getattr(obj, part)
            return obj

        def format_value(value, value_type: str) -> str:
            """Format a value for display."""
            if value_type == "bool":
                return "[green]ON[/green]" if value else "[red]OFF[/red]"
            return str(value)

        while True:
            # Display current settings
            self.ui.console.print("\n[bold cyan]Configuration Settings[/bold cyan]\n")

            table = Table(box=ROUNDED, show_header=True, header_style="bold")
            table.add_column("#", style="dim", width=3)
            table.add_column("Setting", style="cyan")
            table.add_column("Value", width=20)
            table.add_column("Description", style="dim")

            for i, (key, section, config_key, value_type, description, _) in enumerate(settings, 1):
                current = get_current_value(key)
                value_str = format_value(current, value_type)
                table.add_row(str(i), key, value_str, description)

            self.ui.console.print(table)
            self.ui.console.print()
            self.ui.console.print("[dim]Enter number to change setting, or 0 to exit[/dim]")

            # Get user selection
            try:
                choice_str = prompt("Select setting: ").strip()
                if not choice_str or choice_str == "0":
                    break

                choice = int(choice_str)
                if choice < 1 or choice > len(settings):
                    self.ui.print_error("Invalid selection")
                    continue

                # Get the selected setting
                key, section, config_key, value_type, description, options_func = settings[choice - 1]
                current_value = get_current_value(key)

                self.ui.console.print(f"\n[bold]Changing: {key}[/bold]")
                self.ui.console.print(f"[dim]Current value: {current_value}[/dim]\n")

                new_value = None
                toml_value = None

                if value_type == "bool":
                    # Toggle or select true/false
                    self.ui.console.print("  [cyan]1.[/cyan] ON (true)")
                    self.ui.console.print("  [cyan]2.[/cyan] OFF (false)")
                    self.ui.console.print("  [dim]0. Cancel[/dim]\n")

                    bool_choice = prompt("Select: ").strip()
                    if bool_choice == "1":
                        new_value = True
                        toml_value = "true"
                    elif bool_choice == "2":
                        new_value = False
                        toml_value = "false"
                    else:
                        self.ui.print_info("Cancelled")
                        continue

                elif value_type == "choice" and options_func:
                    # Show options from the function
                    options = options_func()
                    for i, (val, label) in enumerate(options, 1):
                        marker = "[green]>[/green]" if val == current_value else " "
                        self.ui.console.print(f"  {marker} [cyan]{i}.[/cyan] {label}")
                    self.ui.console.print("  [dim]0. Cancel[/dim]\n")

                    opt_choice = prompt("Select: ").strip()
                    if opt_choice == "0" or not opt_choice:
                        self.ui.print_info("Cancelled")
                        continue

                    try:
                        opt_idx = int(opt_choice) - 1
                        if 0 <= opt_idx < len(options):
                            new_value = options[opt_idx][0]
                            # Format TOML value based on type
                            if isinstance(new_value, str):
                                toml_value = f'"{new_value}"'
                            else:
                                toml_value = str(new_value)
                        else:
                            self.ui.print_error("Invalid selection")
                            continue
                    except ValueError:
                        self.ui.print_error("Invalid selection")
                        continue

                elif value_type == "int":
                    # Free input with validation
                    int_input = prompt(f"Enter value (100-100000) [{current_value}]: ").strip()
                    if not int_input:
                        self.ui.print_info("Cancelled")
                        continue

                    try:
                        new_value = int(int_input)
                        if new_value < 100 or new_value > 200000:
                            self.ui.print_error("Value must be between 100 and 200000")
                            continue
                        toml_value = str(new_value)
                    except ValueError:
                        self.ui.print_error("Invalid number")
                        continue

                # Save the new value
                if new_value is not None and toml_value is not None:
                    config_file = Path.home() / ".config" / "aios" / "config.toml"
                    try:
                        update_toml_value(config_file, section, config_key, toml_value)
                    except Exception as e:
                        self.ui.print_error(f"Failed to save: {e}")
                        continue

                    # Reload config
                    reset_config()
                    self.config = get_config()

                    # Apply immediate changes
                    if key == "api.model" and client:
                        client.set_model(new_value)
                        client.clear_history()
                        self.ui.print_info("[dim]Conversation history cleared[/dim]")

                    if key == "ui.show_technical_details":
                        self.ui.show_technical = new_value

                    if key == "ui.show_commands":
                        self.ui.show_commands = new_value

                    self.ui.print_success(f"Set {key} = {new_value}")

            except KeyboardInterrupt:
                self.ui.console.print()
                break
            except EOFError:
                break
            except ValueError:
                self.ui.print_error("Please enter a number")
                continue

        self.ui.console.print()

    def show_models(self) -> None:
        """Display available models and current selection."""
        from ..models import AVAILABLE_MODELS, get_model_by_id
        from rich.table import Table

        self.ui.console.print("\n[bold cyan]Available Models[/bold cyan]\n")

        # Get current model info
        current_model_id = self.config.api.model
        current_model_info = get_model_by_id(current_model_id)

        # Create table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=3)
        table.add_column("Model", style="bold")
        table.add_column("Speed", width=10)
        table.add_column("Cost", width=10)
        table.add_column("Status", width=12)

        models_with_notes = []

        for idx, model in enumerate(AVAILABLE_MODELS, 1):
            speed_emoji = "⚡" if model.speed == "fast" else "⏱️" if model.speed == "medium" else "🐌"
            cost_emoji = "💰" if model.cost == "low" else "💵" if model.cost == "medium" else "💸"
            is_current = model.id == current_model_id
            status = "[green]● Current[/green]" if is_current else "[dim]Available[/dim]"

            # Add marker for models with limitations
            name_display = model.name
            if model.note:
                name_display = f"{model.name} [yellow]*[/yellow]"
                models_with_notes.append((idx, model))

            table.add_row(
                str(idx),
                name_display,
                f"{speed_emoji} {model.speed}",
                f"{cost_emoji} {model.cost}",
                status
            )

        self.ui.console.print(table)

        # Show notes for models with limitations
        if models_with_notes:
            self.ui.console.print()
            self.ui.console.print("[yellow]*[/yellow] [dim]These models have known limitations:[/dim]")
            for idx, model in models_with_notes:
                self.ui.console.print(f"  [dim]{idx}. {model.name}:[/dim] [yellow]{model.note}[/yellow]")

        self.ui.console.print(f"\n[bold]Current model:[/bold] [cyan]{current_model_info.name if current_model_info else current_model_id}[/cyan]")

        # Show warning if current model has limitations
        if current_model_info and current_model_info.note:
            self.ui.console.print(f"[yellow]{current_model_info.note}[/yellow]")

        self.ui.console.print("[dim]To change model, use: [cyan]model <number>[/cyan] or [cyan]model <model-id>[/cyan][/dim]\n")

    def change_model(self, model_arg: str, client: Optional["BaseClient"] = None) -> Optional[str]:
        """Change the current model.

        Args:
            model_arg: Model ID, number, or name to switch to
            client: Current LLM client (will be updated if same provider)

        Returns:
            New provider name if provider changed and client needs recreation,
            None otherwise.
        """
        from ..models import AVAILABLE_MODELS, get_model_by_id
        from ..config import reset_config, get_config
        from ..providers import get_provider_name

        if not model_arg:
            self.show_models()
            return None

        # Try to parse as number first
        selected_model = None
        try:
            model_num = int(model_arg)
            if 1 <= model_num <= len(AVAILABLE_MODELS):
                selected_model = AVAILABLE_MODELS[model_num - 1]
        except ValueError:
            # Not a number, try as model ID
            selected_model = get_model_by_id(model_arg)
            if not selected_model:
                # Try case-insensitive match
                model_arg_lower = model_arg.lower()
                for model in AVAILABLE_MODELS:
                    if model.id.lower() == model_arg_lower or model.name.lower() == model_arg_lower:
                        selected_model = model
                        break

        if not selected_model:
            self.ui.print_error(f"Invalid model: {model_arg}")
            self.ui.print_info("Use 'model' to see available models")
            return None

        # Check if provider needs to change
        current_provider = getattr(self.config.api, 'provider', 'anthropic')
        new_provider = selected_model.provider
        provider_changed = current_provider != new_provider

        # Update config file (preserves comments and formatting)
        config_file = Path.home() / ".config" / "aios" / "config.toml"
        try:
            update_toml_value(config_file, "api", "model", f'"{selected_model.id}"')
            if provider_changed:
                update_toml_value(config_file, "api", "provider", f'"{new_provider}"')
        except Exception as e:
            self.ui.print_error(f"Failed to save config: {e}")
            return None

        # Reload config
        reset_config()
        self.config = get_config()

        # If provider changed, we need to create a new client
        if provider_changed:
            self.ui.print_info(f"[green]✓[/green] Switched to [bold]{selected_model.name}[/bold] ({new_provider} provider)")
            self.ui.print_info("[dim]Conversation history cleared for new provider[/dim]")
            # Show warning for models with limitations
            if selected_model.note:
                self.ui.console.print(f"[yellow]{selected_model.note}[/yellow]")
            self.ui.console.print()
            return new_provider

        # Same provider - just update the model on existing client
        if client:
            client.set_model(selected_model.id)
            # Clear conversation history when changing models
            client.clear_history()
            self.ui.print_info(f"[green]✓[/green] Model changed to [bold]{selected_model.name}[/bold]")
            self.ui.print_info("[dim]Conversation history cleared for new model[/dim]")
        else:
            self.ui.print_info(f"[green]✓[/green] Model set to [bold]{selected_model.name}[/bold]")
            self.ui.print_info("[dim]Model will be used when LLM client is initialized[/dim]")

        # Show warning for models with limitations
        if selected_model.note:
            self.ui.console.print(f"[yellow]{selected_model.note}[/yellow]")

        self.ui.console.print()
        return None
