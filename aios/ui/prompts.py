"""
User prompts and confirmations for AIOS.

Provides user-friendly prompts for:
- Confirmations before dangerous actions
- Multiple choice selections
- Text input
"""

from typing import Optional, List, Tuple
from enum import Enum

from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.validation import Validator, ValidationError
from prompt_toolkit.styles import Style
from rich.console import Console

from ..config import get_config


class ConfirmationResult(Enum):
    """Result of a confirmation prompt."""
    YES = "yes"
    NO = "no"
    CANCELLED = "cancelled"


class YesNoValidator(Validator):
    """Validator for yes/no input."""

    def validate(self, document):
        text = document.text.lower().strip()
        if text and text not in ("y", "yes", "n", "no", ""):
            raise ValidationError(
                message="Please enter 'yes' or 'no' (or just press Enter for default)"
            )


class ConfirmationPrompt:
    """Handles user confirmations and prompts."""

    def __init__(self):
        """Initialize the prompt handler."""
        config = get_config()
        self.console = Console()

        # Style for prompts
        self.style = Style.from_dict({
            "prompt": "bold cyan",
            "warning": "bold yellow",
        })

    def confirm(
        self,
        message: str,
        default: bool = False,
        warning: Optional[str] = None
    ) -> ConfirmationResult:
        """
        Ask for yes/no confirmation.

        Args:
            message: The question to ask
            default: Default value if user just presses Enter
            warning: Optional warning to show

        Returns:
            ConfirmationResult
        """
        if warning:
            self.console.print(f"[yellow]⚠ {warning}[/yellow]")

        default_str = "Y/n" if default else "y/N"
        prompt_text = f"{message} [{default_str}]: "

        try:
            response = prompt(
                prompt_text,
                validator=YesNoValidator(),
                validate_while_typing=False
            ).lower().strip()

            if not response:
                return ConfirmationResult.YES if default else ConfirmationResult.NO
            elif response in ("y", "yes"):
                return ConfirmationResult.YES
            else:
                return ConfirmationResult.NO

        except KeyboardInterrupt:
            self.console.print("\n[dim]Cancelled[/dim]")
            return ConfirmationResult.CANCELLED
        except EOFError:
            return ConfirmationResult.CANCELLED

    def confirm_dangerous_action(
        self,
        action: str,
        details: str,
        alternative: Optional[str] = None
    ) -> ConfirmationResult:
        """
        Confirm a potentially dangerous action.

        Args:
            action: Description of the action
            details: Details about what will happen
            alternative: Optional safer alternative to suggest

        Returns:
            ConfirmationResult
        """
        self.console.print()
        self.console.print(f"[bold yellow]⚠ Warning[/bold yellow]")
        self.console.print(f"[bold]{action}[/bold]")
        self.console.print(f"  {details}")

        if alternative:
            self.console.print(f"\n[dim]Tip: {alternative}[/dim]")

        self.console.print()

        return self.confirm("Are you sure you want to continue?", default=False)

    def choose(
        self,
        message: str,
        options: List[str],
        default: int = 0,
        allow_cancel: bool = True
    ) -> Optional[int]:
        """
        Let user choose from a list of options.

        Args:
            message: The prompt message
            options: List of options to choose from
            default: Default option index (0-based)
            allow_cancel: Whether to allow cancellation

        Returns:
            Selected option index, or None if cancelled
        """
        self.console.print(f"\n{message}")

        for i, option in enumerate(options):
            marker = "→" if i == default else " "
            self.console.print(f"  {marker} [cyan]{i + 1}.[/cyan] {option}")

        if allow_cancel:
            self.console.print(f"  [dim]  0. Cancel[/dim]")

        # Build completer
        valid_choices = [str(i) for i in range(1, len(options) + 1)]
        if allow_cancel:
            valid_choices.append("0")
        completer = WordCompleter(valid_choices)

        while True:
            try:
                response = prompt(
                    f"Enter choice (1-{len(options)}): ",
                    completer=completer
                ).strip()

                if not response:
                    return default

                choice = int(response)

                if choice == 0 and allow_cancel:
                    return None
                elif 1 <= choice <= len(options):
                    return choice - 1
                else:
                    self.console.print("[red]Invalid choice. Try again.[/red]")

            except ValueError:
                self.console.print("[red]Please enter a number.[/red]")
            except KeyboardInterrupt:
                self.console.print("\n[dim]Cancelled[/dim]")
                return None
            except EOFError:
                return None

    def get_input(
        self,
        message: str,
        default: Optional[str] = None,
        completer_words: Optional[List[str]] = None,
        multiline: bool = False
    ) -> Optional[str]:
        """
        Get text input from user.

        Args:
            message: The prompt message
            default: Default value
            completer_words: Words for auto-completion
            multiline: Allow multiline input

        Returns:
            User input, or None if cancelled
        """
        prompt_text = message
        if default:
            prompt_text += f" [{default}]"
        prompt_text += ": "

        completer = WordCompleter(completer_words) if completer_words else None

        try:
            response = prompt(
                prompt_text,
                completer=completer,
                multiline=multiline
            ).strip()

            if not response and default:
                return default
            return response if response else None

        except KeyboardInterrupt:
            self.console.print("\n[dim]Cancelled[/dim]")
            return None
        except EOFError:
            return None

    def get_path(
        self,
        message: str,
        default: Optional[str] = None,
        must_exist: bool = False
    ) -> Optional[str]:
        """
        Get a file path from user with path completion.

        Args:
            message: The prompt message
            default: Default path
            must_exist: Whether the path must exist

        Returns:
            Path string, or None if cancelled
        """
        from prompt_toolkit.completion import PathCompleter

        prompt_text = message
        if default:
            prompt_text += f" [{default}]"
        prompt_text += ": "

        completer = PathCompleter(expanduser=True)

        try:
            while True:
                response = prompt(
                    prompt_text,
                    completer=completer
                ).strip()

                if not response and default:
                    response = default

                if not response:
                    return None

                # Expand user
                from pathlib import Path
                path = Path(response).expanduser()

                if must_exist and not path.exists():
                    self.console.print(f"[red]Path not found: {path}[/red]")
                    continue

                return str(path)

        except KeyboardInterrupt:
            self.console.print("\n[dim]Cancelled[/dim]")
            return None
        except EOFError:
            return None

    def ask_clarification(
        self,
        question: str,
        options: Optional[List[str]] = None,
        context: Optional[str] = None
    ) -> Optional[str]:
        """
        Ask for clarification from the user.

        Args:
            question: The clarification question
            options: Optional list of choices
            context: Optional context to show

        Returns:
            User's response
        """
        if context:
            self.console.print(f"\n[dim]{context}[/dim]")

        if options:
            choice = self.choose(question, options, allow_cancel=True)
            if choice is None:
                return None
            return options[choice]
        else:
            return self.get_input(question)

    def show_options_with_descriptions(
        self,
        message: str,
        options: List[Tuple[str, str]]
    ) -> Optional[int]:
        """
        Show options with descriptions.

        Args:
            message: The prompt message
            options: List of (option, description) tuples

        Returns:
            Selected option index, or None if cancelled
        """
        self.console.print(f"\n{message}\n")

        for i, (option, description) in enumerate(options):
            self.console.print(f"  [cyan]{i + 1}.[/cyan] [bold]{option}[/bold]")
            self.console.print(f"      [dim]{description}[/dim]")

        self.console.print(f"  [dim]0. Cancel[/dim]\n")

        while True:
            try:
                response = prompt("Your choice: ").strip()

                if not response:
                    continue

                choice = int(response)

                if choice == 0:
                    return None
                elif 1 <= choice <= len(options):
                    return choice - 1
                else:
                    self.console.print("[red]Invalid choice.[/red]")

            except ValueError:
                self.console.print("[red]Please enter a number.[/red]")
            except KeyboardInterrupt:
                return None
            except EOFError:
                return None
