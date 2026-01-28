"""
Main AIOS shell - the interactive conversation loop.

This is the core of AIOS, handling:
- User input
- Claude API communication
- Tool execution
- Response display
"""

import os
import sys
import subprocess
import threading
from typing import Optional, Dict, Any, List
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.key_binding import KeyBindings

from .ui.completions import AIOSCompleter, create_bottom_toolbar
from .tasks import TaskManager, TaskStatus
from .tasks.browser import TaskBrowser
from .code import CodeRunner, CodingRequestDetector

from .config import get_config, ensure_config_dirs
from .claude.client import ClaudeClient
from .claude.tools import ToolHandler, ToolResult
from .executor.sandbox import CommandExecutor, InteractiveExecutor, CommandResult
from .executor.files import FileHandler
from .context.system import SystemContextGatherer
from .context.session import SessionManager
from .safety.guardrails import SafetyGuard, RiskLevel
from .safety.audit import AuditLogger, ActionType
from .ui.terminal import TerminalUI
from .ui.prompts import ConfirmationPrompt, ConfirmationResult
from .errors import (
    ErrorBoundary,
    ErrorCategory,
    ErrorSeverity,
    ErrorContext,
    AIOSError,
    APIError,
    format_error_for_user,
    safe_execute,
    ErrorRecovery,
)
from .plugins import (
    get_plugin_manager,
    PluginManager,
    ToolDefinition,
    Recipe,
)
from .cache import (
    get_system_info_cache,
    get_tool_result_cache,
    SystemInfoCache,
    ToolResultCache,
    ToolCacheConfig,
    _generate_key,
)
from .ratelimit import (
    get_rate_limiter,
    configure_rate_limiter,
    RateLimitConfig,
    APIRateLimiter,
)
from .credentials import (
    get_credential_store,
    store_credential,
    get_credential,
    list_credentials,
)


def _update_toml_value(config_path: Path, section: str, key: str, value: str) -> None:
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
                # We left the target section without finding the key — insert before this line
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
            # Section was the last in the file — append
            # Ensure trailing newline before appending
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(new_line)
        else:
            # Section doesn't exist — append it
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(f"\n{section_header}\n")
            lines.append(new_line)

    config_path.write_text("".join(lines))


class AIOSShell:
    """The main AIOS interactive shell."""

    def __init__(self):
        """Initialize the AIOS shell."""
        # Ensure config directories exist
        ensure_config_dirs()

        # Load configuration
        self.config = get_config()

        # Initialize components
        self.ui = TerminalUI()
        self.prompts = ConfirmationPrompt()
        self.safety = SafetyGuard()
        self.executor = CommandExecutor()
        self.streaming_executor = InteractiveExecutor()
        self.task_manager = TaskManager()
        self.code_runner = CodeRunner(config=getattr(self.config, 'code', None))
        self._code_detector = CodingRequestDetector(
            sensitivity=getattr(
                getattr(self.config, 'code', None),
                'auto_detect_sensitivity', 'moderate'
            )
        )
        self._code_available: Optional[bool] = None  # Lazy check
        self.files = FileHandler()
        self.system = SystemContextGatherer()
        self.session = SessionManager()
        self.audit = AuditLogger()

        # Initialize tool handler with our implementations
        self.tool_handler = ToolHandler()
        self._register_tools()

        # Initialize plugin system
        self.plugin_manager = get_plugin_manager()
        self._load_plugins()

        # Initialize caching
        self.system_cache = get_system_info_cache()
        self.tool_cache = get_tool_result_cache()
        self._configure_tool_cache()
        self.tool_handler.set_cache(self.tool_cache)

        # Initialize rate limiting
        self.rate_limiter = get_rate_limiter()
        self._configure_rate_limiter()

        # Initialize Claude client (may fail if no API key)
        self.claude: Optional[ClaudeClient] = None

        # Session state
        self.running = False

        # Command history and prompt session
        history_path = Path.home() / ".config" / "aios" / "command_history"
        self.history = FileHistory(str(history_path))
        self.completer = AIOSCompleter(
            session_fetcher=self._get_session_ids,
            code_session_fetcher=self._get_code_session_ids,
        )

        # Key bindings
        kb = KeyBindings()

        @kb.add('c-b')
        def _open_tasks(event):
            event.current_buffer.text = ''
            event.app.exit(result='\x02')

        self._key_bindings = kb

        self._prompt_session = PromptSession(
            history=self.history,
            auto_suggest=AutoSuggestFromHistory(),
            completer=self.completer,
            complete_while_typing=False,
            key_bindings=self._key_bindings,
        )

    def _register_tools(self) -> None:
        """Register built-in tool handlers."""
        self.tool_handler.register("run_command", self._handle_run_command)
        self.tool_handler.register("read_file", self._handle_read_file)
        self.tool_handler.register("write_file", self._handle_write_file)
        self.tool_handler.register("search_files", self._handle_search_files)
        self.tool_handler.register("list_directory", self._handle_list_directory)
        self.tool_handler.register("get_system_info", self._handle_system_info)
        self.tool_handler.register("manage_application", self._handle_manage_application)
        self.tool_handler.register("ask_clarification", self._handle_ask_clarification)
        self.tool_handler.register("open_application", self._handle_open_application)

    def _load_plugins(self) -> None:
        """Load plugins and register their tools."""
        # Discover and load all plugins
        try:
            loaded_plugins = self.plugin_manager.load_all()
            if loaded_plugins:
                self.ui.print_info(f"Loaded {len(loaded_plugins)} plugin(s)")

            # Register plugin tools
            for tool in self.plugin_manager.get_all_tools().values():
                self._register_plugin_tool(tool)

        except Exception as e:
            self.ui.print_warning(f"Failed to load some plugins: {e}")

    def _register_plugin_tool(self, tool: ToolDefinition) -> None:
        """Register a plugin tool with the tool handler."""
        # Create a wrapper that handles plugin tool execution
        def plugin_tool_handler(params: Dict[str, Any]) -> ToolResult:
            # Handle confirmation if required
            if tool.requires_confirmation:
                explanation = params.get("explanation", f"Running {tool.name}")
                result = self.prompts.confirm(
                    f"Allow {tool.name}?",
                    default=True,
                    warning=f"This plugin tool wants to: {explanation}"
                )
                if result != ConfirmationResult.YES:
                    return ToolResult(
                        success=False,
                        output="",
                        user_friendly_message="Okay, cancelled."
                    )

            # Execute the plugin tool handler
            try:
                result = tool.handler(params)

                # Convert plugin result format to ToolResult
                if isinstance(result, dict):
                    return ToolResult(
                        success=result.get("success", True),
                        output=result.get("output", ""),
                        error=result.get("error"),
                        user_friendly_message=result.get("message", "")
                    )
                else:
                    return ToolResult(
                        success=True,
                        output=str(result),
                        user_friendly_message=""
                    )

            except Exception as e:
                return ToolResult(
                    success=False,
                    output="",
                    error=str(e),
                    user_friendly_message=f"Plugin tool failed: {e}"
                )

        # Register the tool with its full definition
        self.tool_handler.register_tool(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
            handler=plugin_tool_handler,
            requires_confirmation=tool.requires_confirmation
        )

    def _get_matching_recipe(self, user_input: str) -> Optional[Recipe]:
        """Check if user input matches any recipe."""
        return self.plugin_manager.find_matching_recipe(user_input)

    def _notify_plugins_session_start(self) -> None:
        """Notify all plugins that a session has started."""
        for plugin_meta in self.plugin_manager.list_plugins():
            try:
                plugin = self.plugin_manager._plugins.get(plugin_meta.name)
                if plugin and hasattr(plugin.instance, 'on_session_start'):
                    plugin.instance.on_session_start()
            except Exception as e:
                self.ui.print_warning(f"Plugin {plugin_meta.name} session start failed: {e}")

    def _notify_plugins_session_end(self) -> None:
        """Notify all plugins that a session is ending."""
        for plugin_meta in self.plugin_manager.list_plugins():
            try:
                plugin = self.plugin_manager._plugins.get(plugin_meta.name)
                if plugin and hasattr(plugin.instance, 'on_session_end'):
                    plugin.instance.on_session_end()
            except Exception as e:
                self.ui.print_warning(f"Plugin {plugin_meta.name} session end failed: {e}")

    def _configure_rate_limiter(self) -> None:
        """Configure rate limiter from config."""
        # Use config values or defaults
        config = RateLimitConfig(
            requests_per_minute=getattr(self.config.api, 'requests_per_minute', 50),
            requests_per_hour=getattr(self.config.api, 'requests_per_hour', 500),
            tokens_per_minute=getattr(self.config.api, 'tokens_per_minute', 100000),
        )
        configure_rate_limiter(config)

    def _configure_tool_cache(self) -> None:
        """Configure per-tool caching and invalidation rules."""
        tc = self.tool_cache

        # --- cacheable tools ---
        tc.configure_tool("get_system_info", ToolCacheConfig(
            cacheable=True, ttl=30.0, key_params=["info_type"],
        ))
        tc.configure_tool("read_file", ToolCacheConfig(
            cacheable=True, ttl=300.0, key_params=["path"],
        ))
        tc.configure_tool("list_directory", ToolCacheConfig(
            cacheable=True, ttl=60.0, key_params=["path", "show_hidden"],
        ))
        tc.configure_tool("search_files", ToolCacheConfig(
            cacheable=True, ttl=60.0,
            key_params=["query", "location", "search_type"],
        ))

        # --- invalidation rules ---
        # write_file -> read_file (specific key for the same path)
        tc.add_invalidation_rule(
            "write_file", "read_file",
            key_transform=lambda inp: _generate_key(
                "read_file", (), {"path": inp.get("path")},
            ),
        )
        # write_file -> wipe list_directory & search_files
        tc.add_invalidation_rule("write_file", "list_directory")
        tc.add_invalidation_rule("write_file", "search_files")

        # manage_application -> wipe get_system_info
        tc.add_invalidation_rule("manage_application", "get_system_info")

        # run_command can do anything -> wipe all cacheable tools
        for tool in ("get_system_info", "read_file", "list_directory", "search_files"):
            tc.add_invalidation_rule("run_command", tool)

    def _get_session_ids(self) -> list:
        """Return recent session IDs for tab completion."""
        try:
            sessions = self.session.list_sessions(limit=20)
            return [s["session_id"] for s in sessions]
        except Exception:
            return []

    def _get_code_session_ids(self) -> list:
        """Return recent code session IDs for tab completion."""
        try:
            sessions = self.code_runner.get_sessions(limit=20)
            return [s.session_id for s in sessions]
        except Exception:
            return []

    def _show_plugins(self) -> None:
        """Display loaded plugins."""
        plugins = self.plugin_manager.list_plugins()

        if not plugins:
            self.ui.print_info("No plugins loaded.")
            self.ui.print_info("Place plugins in ~/.config/aios/plugins/")
            return

        self.ui.console.print("\n[bold cyan]Loaded Plugins[/bold cyan]\n")

        for plugin in plugins:
            tools = self.plugin_manager.get_all_tools()
            plugin_tools = [t for t in tools.values()
                          if hasattr(t, 'category') and t.category == plugin.name]
            tool_count = len(plugin_tools)

            self.ui.console.print(
                f"  [green]●[/green] [bold]{plugin.name}[/bold] v{plugin.version}"
            )
            self.ui.console.print(f"    {plugin.description}")
            self.ui.console.print(f"    [dim]Tools: {tool_count} | Author: {plugin.author}[/dim]")
            self.ui.console.print()

    def _show_recipes(self) -> None:
        """Display available recipes."""
        recipes = self.plugin_manager.get_all_recipes()

        if not recipes:
            self.ui.print_info("No recipes available.")
            return

        self.ui.console.print("\n[bold cyan]Available Recipes[/bold cyan]\n")

        for name, recipe in recipes.items():
            triggers = ", ".join(f'"{t}"' for t in recipe.trigger_phrases[:2])
            self.ui.console.print(f"  [green]●[/green] [bold]{name}[/bold]")
            self.ui.console.print(f"    {recipe.description}")
            self.ui.console.print(f"    [dim]Triggers: {triggers}[/dim]")
            self.ui.console.print(f"    [dim]Steps: {len(recipe.steps)}[/dim]")
            self.ui.console.print()

        self.ui.print_info("Say a trigger phrase to run a recipe.")

    def _show_tools(self) -> None:
        """Display available tools."""
        # Get built-in tools
        builtin_tools = self.tool_handler.get_tool_names()

        # Get plugin tools
        plugin_tools = self.plugin_manager.get_all_tools()

        self.ui.console.print("\n[bold cyan]Available Tools[/bold cyan]\n")

        self.ui.console.print("[bold]Built-in Tools:[/bold]")
        for tool_name in sorted(builtin_tools):
            if tool_name not in plugin_tools:
                self.ui.console.print(f"  [dim]●[/dim] {tool_name}")

        if plugin_tools:
            self.ui.console.print("\n[bold]Plugin Tools:[/bold]")
            for name, tool in sorted(plugin_tools.items()):
                confirm = "[yellow]⚠[/yellow]" if tool.requires_confirmation else "[dim]●[/dim]"
                self.ui.console.print(f"  {confirm} {name}")
                self.ui.console.print(f"      [dim]{tool.description[:60]}...[/dim]")

        self.ui.console.print()

    def _show_credentials(self) -> None:
        """Display stored credentials (names only, not values)."""
        try:
            creds = list_credentials()
        except Exception:
            self.ui.print_info("Credential store not initialized.")
            self.ui.print_info("Credentials will be requested when needed by plugins.")
            return

        if not creds:
            self.ui.print_info("No stored credentials.")
            self.ui.print_info("Credentials will be requested when needed by plugins.")
            return

        self.ui.console.print("\n[bold cyan]Stored Credentials[/bold cyan]\n")

        for name in sorted(creds):
            cred = get_credential(name)
            if cred:
                details = []
                if cred.username:
                    details.append(f"user: {cred.username}")
                if cred.password:
                    details.append("password: ****")
                if cred.api_key:
                    details.append("api_key: ****")
                if cred.extra:
                    details.append(f"extra: {len(cred.extra)} fields")

                detail_str = ", ".join(details) if details else "empty"
                self.ui.console.print(f"  [green]●[/green] [bold]{name}[/bold]")
                self.ui.console.print(f"    [dim]{detail_str}[/dim]")

        self.ui.console.print()
        self.ui.print_info("Use 'credential add <name>' or 'credential delete <name>' to manage.")

    def _show_stats(self) -> None:
        """Display session and system stats."""
        self.ui.console.print("\n[bold cyan]Session Statistics[/bold cyan]\n")

        # Rate limiter stats
        rl_stats = self.rate_limiter.stats
        self.ui.console.print("[bold]API Usage:[/bold]")
        self.ui.console.print(f"  Requests this session: {rl_stats['total_requests']}")
        self.ui.console.print(f"  Tokens used: {rl_stats['total_tokens_used']}")
        self.ui.console.print(f"  Requests remaining (minute): {rl_stats.get('requests_remaining_minute', 'N/A')}")

        # Cache stats
        self.ui.console.print("\n[bold]Cache Performance:[/bold]")
        has_cache_stats = False

        # Tool result cache stats
        tc_stats = self.tool_cache.stats
        tc_hits = tc_stats.get('hits', 0)
        tc_misses = tc_stats.get('misses', 0)
        if tc_hits > 0 or tc_misses > 0:
            has_cache_stats = True
            tc_total = tc_hits + tc_misses
            tc_rate = tc_hits / tc_total * 100 if tc_total > 0 else 0
            self.ui.console.print(f"  Tool Result Cache:")
            self.ui.console.print(f"    Hit rate: {tc_rate:.0f}% ({tc_hits} hits, {tc_misses} misses)")
            self.ui.console.print(f"    Entries: {tc_stats.get('size', 0)}/{tc_stats.get('max_size', 200)}")
            self.ui.console.print(f"    Evictions: {tc_stats.get('evictions', 0)}")

        # System context cache stats
        sys_cache_stats = self.system_cache.stats
        for info_type, stats in sys_cache_stats.items():
            if stats.get('hits', 0) > 0 or stats.get('misses', 0) > 0:
                has_cache_stats = True
                hit_rate = stats['hits'] / (stats['hits'] + stats['misses']) * 100 if (stats['hits'] + stats['misses']) > 0 else 0
                self.ui.console.print(f"  system/{info_type}: {hit_rate:.0f}% hit rate ({stats['hits']} hits, {stats['misses']} misses)")

        if not has_cache_stats:
            self.ui.console.print("  [dim]No cache activity yet[/dim]")

        # Plugin stats
        plugins = self.plugin_manager.list_plugins()
        tools = self.plugin_manager.get_all_tools()
        recipes = self.plugin_manager.get_all_recipes()
        self.ui.console.print("\n[bold]Plugins:[/bold]")
        self.ui.console.print(f"  Loaded: {len(plugins)}")
        self.ui.console.print(f"  Tools: {len(tools)}")
        self.ui.console.print(f"  Recipes: {len(recipes)}")

        self.ui.console.print()

    def _interactive_config(self) -> None:
        """Interactive configuration menu."""
        from rich.table import Table
        from rich.box import ROUNDED
        from prompt_toolkit import prompt
        from prompt_toolkit.completion import WordCompleter
        from .models import AVAILABLE_MODELS, get_model_by_id
        from .config import reset_config

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
                            toml_value = f'"{new_value}"'
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
                        if new_value < 100 or new_value > 100000:
                            self.ui.print_error("Value must be between 100 and 100000")
                            continue
                        toml_value = str(new_value)
                    except ValueError:
                        self.ui.print_error("Invalid number")
                        continue

                # Save the new value
                if new_value is not None and toml_value is not None:
                    config_file = Path.home() / ".config" / "aios" / "config.toml"
                    try:
                        _update_toml_value(config_file, section, config_key, toml_value)
                    except Exception as e:
                        self.ui.print_error(f"Failed to save: {e}")
                        continue

                    # Reload config
                    reset_config()
                    self.config = get_config()

                    # Apply immediate changes
                    if key == "api.model" and self.claude:
                        self.claude.model = new_value
                        self.claude.clear_history()
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

    def _show_models(self) -> None:
        """Display available models and current selection."""
        from .models import AVAILABLE_MODELS, get_model_by_id
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

        for idx, model in enumerate(AVAILABLE_MODELS, 1):
            speed_emoji = "⚡" if model.speed == "fast" else "⏱️" if model.speed == "medium" else "🐌"
            cost_emoji = "💰" if model.cost == "low" else "💵" if model.cost == "medium" else "💸"
            is_current = model.id == current_model_id
            status = "[green]● Current[/green]" if is_current else "[dim]Available[/dim]"

            table.add_row(
                str(idx),
                model.name,
                f"{speed_emoji} {model.speed}",
                f"{cost_emoji} {model.cost}",
                status
            )

        self.ui.console.print(table)
        self.ui.console.print(f"\n[bold]Current model:[/bold] [cyan]{current_model_info.name if current_model_info else current_model_id}[/cyan]")
        self.ui.console.print(f"[dim]To change model, use: [cyan]model <number>[/cyan] or [cyan]model <model-id>[/cyan][/dim]\n")

    def _change_model(self, model_arg: str) -> None:
        """Change the current model."""
        from .models import AVAILABLE_MODELS, get_model_by_id
        from .config import reset_config

        if not model_arg:
            self._show_models()
            return

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
            return

        # Update config file (preserves comments and formatting)
        config_file = Path.home() / ".config" / "aios" / "config.toml"
        try:
            _update_toml_value(config_file, "api", "model", f'"{selected_model.id}"')
        except Exception as e:
            self.ui.print_error(f"Failed to save config: {e}")
            return

        # Reload config
        reset_config()
        self.config = get_config()

        # Update Claude client model
        if self.claude:
            self.claude.model = selected_model.id
            # Clear conversation history when changing models
            self.claude.clear_history()
            self.ui.print_info(f"[green]✓[/green] Model changed to [bold]{selected_model.name}[/bold]")
            self.ui.print_info("[dim]Conversation history cleared for new model[/dim]")
        else:
            self.ui.print_info(f"[green]✓[/green] Model set to [bold]{selected_model.name}[/bold]")
            self.ui.print_info("[dim]Model will be used when Claude client is initialized[/dim]")

        self.ui.console.print()

    def _show_sessions(self) -> None:
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
            except Exception:
                formatted_date = started[:16]

            self.ui.console.print(
                f"  [green]●[/green] [bold]{session_id}[/bold]"
            )
            self.ui.console.print(
                f"    [dim]Started: {formatted_date} | Messages: {msg_count}[/dim]"
            )

        self.ui.console.print()
        self.ui.print_info("Use 'resume <session_id>' to continue a previous session.")

    def _resume_session(self, session_id: str) -> None:
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
        if self.claude and msg_count > 0:
            self._restore_claude_history(loaded_session.messages)
            self.ui.print_info("Conversation history restored.")

    def _restore_claude_history(self, messages) -> None:
        """Restore Claude conversation history from session messages."""
        if not self.claude:
            return

        # Clear current conversation history
        self.claude.clear_history()

        # Add messages to conversation history
        for msg in messages[-20:]:  # Keep last 20 messages for context
            if msg.role == "user":
                self.claude.conversation_history.append({
                    "role": "user",
                    "content": msg.content,
                })
            elif msg.role == "assistant":
                self.claude.conversation_history.append({
                    "role": "assistant",
                    "content": msg.content,
                })

    def _check_rate_limit(self) -> bool:
        """Check rate limit before API call. Returns True if allowed."""
        status = self.rate_limiter.check()
        if status.is_limited:
            self.ui.print_warning(
                f"Rate limited. Please wait {status.wait_time:.1f}s before next request."
            )
            return False

        # Warn if approaching limits
        if status.requests_remaining < 5:
            self.ui.print_warning(
                f"Approaching rate limit: {status.requests_remaining} requests remaining this minute."
            )
        return True

    def _record_api_usage(self, tokens_used: int = 0) -> None:
        """Record API usage for rate limiting."""
        self.rate_limiter.acquire(blocking=False)
        if tokens_used > 0:
            self.rate_limiter.record_tokens(tokens_used)

    def _handle_run_command(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the run_command tool."""
        command = params.get("command", "")
        explanation = params.get("explanation", "Running a command")
        requires_confirmation = params.get("requires_confirmation", False)
        working_dir = params.get("working_directory")
        use_sudo = params.get("use_sudo", False)
        timeout = params.get("timeout")
        long_running = params.get("long_running", False)
        background = params.get("background", False)

        # Prepend sudo if requested and not already present
        if use_sudo and not command.lstrip().startswith("sudo "):
            command = f"sudo {command}"

        # Safety check
        safety_check = self.safety.check_command(command)

        if not safety_check.is_allowed:
            self.audit.log(
                ActionType.COMMAND,
                f"Blocked: {command}",
                success=False,
                error=safety_check.reason
            )
            return ToolResult(
                success=False,
                output="",
                error=safety_check.user_warning,
                user_friendly_message=safety_check.user_warning or "This action is not allowed."
            )

        # Show what we're doing
        self.ui.print_executing(explanation)

        # Inform the user about elevated privileges
        if use_sudo:
            self.ui.print_warning("This command requires administrator privileges (sudo).")

        # Inform about long timeout
        if timeout and timeout > 60:
            minutes = (timeout + 59) // 60
            self.ui.print_info(f"This operation may take up to {minutes} minute(s).")

        # Confirmation for dangerous commands
        if safety_check.requires_confirmation or requires_confirmation:
            result = self.prompts.confirm_dangerous_action(
                explanation,
                safety_check.user_warning or "This action may modify your system.",
                safety_check.safe_alternative
            )
            if result != ConfirmationResult.YES:
                return ToolResult(
                    success=False,
                    output="",
                    user_friendly_message="Okay, I won't do that."
                )

        # Show command in technical mode
        self.ui.print_command(command)

        # Background execution — no timeout, runs until done
        if background:
            self.ui.print_info(f"Starting in background: {explanation}")
            task = self.task_manager.create_task(
                command, explanation, working_dir
            )
            self.ui.print_success(
                f"Background task #{task.task_id} started. Ctrl+B to view."
            )
            return ToolResult(
                success=True,
                output=f"Task started in background (ID: {task.task_id})",
                user_friendly_message=(
                    f"Started background task #{task.task_id}"
                ),
            )

        # Execute — streaming or standard
        if long_running:
            cmd_result = self._execute_streaming(
                command, working_dir, timeout or 300, explanation
            )
        else:
            cmd_result = self.executor.execute(
                command, working_directory=working_dir, timeout=timeout
            )

        # Log
        self.audit.log_command(
            command,
            cmd_result.output,
            cmd_result.success,
            working_dir
        )

        # Provide helpful timeout message
        if cmd_result.timed_out:
            effective_timeout = timeout or self.executor.DEFAULT_TIMEOUT
            return ToolResult(
                success=False,
                output=cmd_result.stdout,
                error="Command timed out",
                user_friendly_message=(
                    f"The command timed out after {effective_timeout} seconds. "
                    "You can retry with a higher timeout value."
                )
            )

        return ToolResult(
            success=cmd_result.success,
            output=cmd_result.output,
            error=cmd_result.error_message,
            user_friendly_message=cmd_result.to_user_friendly()
        )

    def _execute_streaming(
        self,
        command: str,
        working_dir: Optional[str],
        timeout: int,
        description: str,
    ) -> CommandResult:
        """Execute a command with live streaming output.

        If the user presses Ctrl+C during execution, they are offered the
        option to background the still-running process rather than killing it.
        """
        cwd = Path(working_dir) if working_dir else Path.home()

        process_env = os.environ.copy()
        if sys.platform != "win32":
            process_env["PATH"] = (
                "/usr/local/bin:/usr/bin:/bin:" + process_env.get("PATH", "")
            )

        popen_kwargs: Dict[str, Any] = dict(
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(cwd),
            env=process_env,
            bufsize=1,
            universal_newlines=True,
        )
        if sys.platform != "win32":
            popen_kwargs["start_new_session"] = True

        output_lines: List[str] = []

        try:
            process = subprocess.Popen(command, **popen_kwargs)
        except Exception as e:
            return CommandResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error_message=str(e),
            )

        def _reader():
            try:
                for line in process.stdout:
                    stripped = line.rstrip("\n\r")
                    output_lines.append(stripped)
                    if display_callback[0] is not None:
                        try:
                            display_callback[0](stripped)
                        except Exception:
                            pass
            except (ValueError, OSError):
                pass

        # Mutable container so the reader thread can see callback changes
        display_callback: List[Any] = [None]

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()

        try:
            with self.ui.print_streaming_output(description) as display:
                display_callback[0] = display.add_line
                reader_thread.join(timeout=timeout)
        except KeyboardInterrupt:
            # Offer to background the still-running process
            display_callback[0] = None  # detach live display
            if process.poll() is None:
                try:
                    answer = input("\nBackground this task? [y/N]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    answer = "n"

                if answer == "y":
                    task = self.task_manager.adopt_task(
                        command=command,
                        description=description,
                        process=process,
                        reader_thread=reader_thread,
                        output_buffer=list(output_lines),
                    )
                    self.ui.print_success(
                        f"Backgrounded as task #{task.task_id}. Ctrl+B to view."
                    )
                    return CommandResult(
                        success=True,
                        stdout="".join(
                            ln + "\n" for ln in output_lines
                        ),
                        stderr="",
                        return_code=-1,
                        error_message="Backgrounded by user",
                    )
                else:
                    # Kill the process
                    try:
                        if sys.platform != "win32":
                            os.killpg(os.getpgid(process.pid), 9)
                        else:
                            process.kill()
                    except (ProcessLookupError, OSError):
                        pass
                    process.wait()
                    return CommandResult(
                        success=False,
                        stdout="".join(ln + "\n" for ln in output_lines),
                        stderr="",
                        return_code=-1,
                        error_message="Cancelled by user",
                    )
            else:
                # Process already finished during the interrupt —
                # fall through to normal completion / process.wait() below.
                pass

        # Check if the reader timed out
        if reader_thread.is_alive():
            try:
                if sys.platform != "win32":
                    os.killpg(os.getpgid(process.pid), 9)
                else:
                    process.kill()
            except (ProcessLookupError, OSError):
                pass
            process.wait()
            return CommandResult(
                success=False,
                stdout="".join(ln + "\n" for ln in output_lines),
                stderr="",
                return_code=-1,
                timed_out=True,
            )

        # Normal completion
        process.wait()
        return CommandResult(
            success=(process.returncode == 0),
            stdout="".join(ln + "\n" for ln in output_lines),
            stderr="",
            return_code=process.returncode,
        )

    def _handle_read_file(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the read_file tool."""
        path = params.get("path", "")
        explanation = params.get("explanation", "Reading a file")
        display_content = params.get("display_content", False)

        self.ui.print_executing(explanation)

        result = self.files.read_file(path)

        self.audit.log(
            ActionType.FILE_READ,
            f"Read: {path}",
            success=result.success,
            details={"path": path}
        )

        # Display file content to user if requested
        if result.success and display_content and result.data:
            filename = Path(path).name
            self.ui.print_file_content(result.data, filename)

        return ToolResult(
            success=result.success,
            output=result.data or "",
            error=result.error,
            user_friendly_message=result.message if result.success else result.error or ""
        )

    def _handle_write_file(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the write_file tool."""
        path = params.get("path", "")
        content = params.get("content", "")
        explanation = params.get("explanation", "Writing to a file")
        requires_confirmation = params.get("requires_confirmation", True)
        create_backup = params.get("create_backup", True)

        # Safety check
        safety_check = self.safety.check_file_write(path)

        self.ui.print_executing(explanation)

        # Confirmation
        if requires_confirmation or safety_check.requires_confirmation:
            result = self.prompts.confirm(
                f"Save changes to {Path(path).name}?",
                default=True,
                warning=safety_check.user_warning
            )
            if result != ConfirmationResult.YES:
                return ToolResult(
                    success=False,
                    output="",
                    user_friendly_message="Okay, I won't save those changes."
                )

        # Write file
        file_result = self.files.write_file(path, content, create_backup)

        # Log
        self.audit.log_file_write(
            path,
            file_result.success,
            str(file_result.backup_path) if file_result.backup_path else None,
            file_result.error
        )

        return ToolResult(
            success=file_result.success,
            output="",
            error=file_result.error,
            user_friendly_message=file_result.message if file_result.success else file_result.error or ""
        )

    def _handle_search_files(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the search_files tool."""
        query = params.get("query", "")
        location = params.get("location")
        search_type = params.get("search_type", "filename")
        explanation = params.get("explanation", "Searching for files")

        self.ui.print_executing(explanation)

        result = self.files.search_files(query, location, search_type)

        self.audit.log(
            ActionType.SEARCH,
            f"Searched for: {query}",
            success=True,
            details={"query": query, "results": len(result.files)}
        )

        if not result.files:
            return ToolResult(
                success=True,
                output="No files found matching your search.",
                user_friendly_message="I didn't find any files matching that."
            )

        # Format results
        file_list = []
        for f in result.files[:20]:
            file_list.append(f"{f.to_user_friendly()} - {f.path}")

        output = "\n".join(file_list)
        if result.truncated:
            output += f"\n\n(Showing first 20 of {result.total_count} results)"

        return ToolResult(
            success=True,
            output=output,
            user_friendly_message=f"Found {len(result.files)} file(s)"
        )

    def _handle_list_directory(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the list_directory tool."""
        path = params.get("path")
        show_hidden = params.get("show_hidden", False)
        explanation = params.get("explanation", "Listing directory contents")

        self.ui.print_executing(explanation)

        result = self.files.list_directory(path, show_hidden)

        if not result.files:
            return ToolResult(
                success=True,
                output="This folder is empty.",
                user_friendly_message="The folder is empty."
            )

        # Format results
        file_list = [f.to_user_friendly() for f in result.files]
        output = "\n".join(file_list)

        return ToolResult(
            success=True,
            output=output,
            user_friendly_message=f"Found {len(result.files)} item(s)"
        )

    def _handle_system_info(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the get_system_info tool.

        Caching is handled transparently by ToolHandler.execute().
        """
        info_type = params.get("info_type", "general")
        explanation = params.get("explanation", "Getting system information")

        self.ui.print_executing(explanation)

        context = self.system.get_context(force_refresh=True)

        if info_type == "disk":
            output = self._format_disk_info(context)
        elif info_type == "memory":
            output = self._format_memory_info(context)
        elif info_type == "cpu":
            output = self._format_cpu_info(context)
        elif info_type == "processes":
            processes = self.system.get_running_processes(10)
            output = self._format_processes_info(processes)
        else:  # general
            output = context.to_summary()

        self.audit.log(
            ActionType.SYSTEM_INFO,
            f"Retrieved {info_type} info",
            success=True
        )

        return ToolResult(success=True, output=output, user_friendly_message="")

    def _format_disk_info(self, context) -> str:
        """Format disk information."""
        if not context.disk_info:
            return "Disk information not available"
        return "\n".join(d.to_user_friendly() for d in context.disk_info)

    def _format_memory_info(self, context) -> str:
        """Format memory information."""
        if not context.memory_info:
            return "Memory information not available"
        return context.memory_info.to_user_friendly()

    def _format_cpu_info(self, context) -> str:
        """Format CPU information."""
        return f"CPU: {context.cpu_count} cores, {context.cpu_percent:.1f}% usage"

    def _format_processes_info(self, processes) -> str:
        """Format processes information."""
        if not processes:
            return "Process information not available"
        lines = ["Top processes by CPU usage:"]
        for p in processes:
            lines.append(f"  {p.name}: CPU {p.cpu_percent:.1f}%, Memory {p.memory_percent:.1f}%")
        return "\n".join(lines)

    def _handle_manage_application(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the manage_application tool."""
        action = params.get("action", "")
        package = params.get("package", "")
        explanation = params.get("explanation", f"{action.capitalize()} {package}")

        # Safety check
        safety_check = self.safety.check_package_operation(action, package)

        if not safety_check.is_allowed:
            return ToolResult(
                success=False,
                output="",
                error=safety_check.user_warning,
                user_friendly_message=safety_check.user_warning or ""
            )

        self.ui.print_executing(explanation)

        # Always confirm package operations
        result = self.prompts.confirm(
            f"{action.capitalize()} {package}?",
            default=(action != "remove"),
            warning=safety_check.user_warning
        )
        if result != ConfirmationResult.YES:
            return ToolResult(
                success=False,
                output="",
                user_friendly_message="Okay, cancelled."
            )

        # Check if sudo is available
        sudo_available = self.executor.check_command_exists("sudo")
        sudo_prefix = "sudo " if sudo_available else ""

        # Build command based on action
        if action == "install":
            # Update package cache first, then install
            command = f"{sudo_prefix}apt-get update -qq && {sudo_prefix}apt-get install -y {package}"
        elif action == "remove":
            command = f"{sudo_prefix}apt-get remove -y {package}"
        elif action == "update":
            command = f"{sudo_prefix}apt-get update && {sudo_prefix}apt-get upgrade -y"
        elif action == "search":
            # Search doesn't need sudo
            command = f"apt-cache search {package}"
        else:
            return ToolResult(success=False, output="", error="Unknown action")

        # Execute with extended timeout and streaming for package operations
        self.ui.print_info(f"Running package operation (this may take a moment)...")
        if action in ("install", "update"):
            cmd_result = self._execute_streaming(
                command, None, 600, f"{action.capitalize()}ing {package}"
            )
        else:
            cmd_result = self.executor.execute(command, timeout=300)

        self.audit.log_package_operation(action, package, cmd_result.success)

        # Provide helpful error messages
        if not cmd_result.success:
            error_msg = cmd_result.stderr or cmd_result.error_message or "Unknown error"
            if "Permission denied" in error_msg or "not permitted" in error_msg:
                user_msg = "Permission denied. The system may not allow package installations."
            elif "Unable to locate package" in error_msg:
                user_msg = f"Package '{package}' was not found. Check the package name and try again."
            elif "Could not get lock" in error_msg:
                user_msg = "Another package manager is running. Please wait and try again."
            else:
                user_msg = f"Failed to {action} {package}."
            return ToolResult(
                success=False,
                output=cmd_result.output,
                error=error_msg,
                user_friendly_message=user_msg
            )

        return ToolResult(
            success=True,
            output=cmd_result.output,
            user_friendly_message=f"Successfully {action}ed {package}!"
        )

    def _handle_ask_clarification(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the ask_clarification tool."""
        question = params.get("question", "")
        options = params.get("options", [])
        context = params.get("context")

        response = self.prompts.ask_clarification(question, options, context)

        if response is None:
            return ToolResult(
                success=False,
                output="",
                user_friendly_message="Cancelled"
            )

        return ToolResult(
            success=True,
            output=response,
            requires_followup=True,
            user_friendly_message=""
        )

    def _handle_open_application(self, params: Dict[str, Any]) -> ToolResult:
        """Handle the open_application tool."""
        target = params.get("target", "")
        explanation = params.get("explanation", f"Opening {target}")

        self.ui.print_executing(explanation)

        # Use xdg-open on Linux
        import shlex
        command = f"xdg-open {shlex.quote(target)}"
        cmd_result = self.executor.execute(command, timeout=5)

        return ToolResult(
            success=cmd_result.success,
            output="",
            user_friendly_message=f"Opened {Path(target).name}" if cmd_result.success else "Couldn't open that"
        )

    # ---- Claude Code integration ----

    def _run_code_task(self, prompt: Optional[str] = None, session_id: Optional[str] = None) -> None:
        """Launch an interactive Claude Code session."""
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
            _update_toml_value(config_file, "code", "auth_mode", f'"{auth_mode}"')
        except Exception as e:
            self.ui.print_warning(f"Could not save auth mode to config: {e}")

    def _continue_code_session(self, args: str) -> None:
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
        self._run_code_task(prompt=prompt, session_id=sid)

    def _show_code_sessions(self) -> None:
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
            except Exception:
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

    def _process_tool_calls(self, tool_calls: list) -> list:
        """Process tool calls and return results."""
        results = []

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_input = tool_call["input"]
            tool_id = tool_call["id"]

            # Execute the tool
            result = self.tool_handler.execute(tool_name, tool_input)

            # Format for Claude
            content = result.output if result.success else f"Error: {result.error}"

            results.append({
                "tool_use_id": tool_id,
                "content": content,
                "is_error": not result.success
            })

            # Show user-friendly message if any
            if result.user_friendly_message:
                if result.success:
                    self.ui.print_success(result.user_friendly_message)
                else:
                    self.ui.print_error(result.user_friendly_message)

        return results

    def _handle_user_input(self, user_input: str) -> bool:
        """
        Handle user input and return whether to continue.

        Returns:
            True to continue the loop, False to exit
        """
        # Handle special commands
        lower_input = user_input.lower().strip()

        if lower_input in ("exit", "quit", "bye", "goodbye"):
            self.ui.print_info("Goodbye! See you next time.")
            return False

        if lower_input == "help":
            self.ui.print_help()
            return True

        if lower_input == "clear":
            self.ui.clear_screen()
            return True

        if lower_input == "history":
            summary = self.session.get_session_summary()
            self.ui.print_system_info(summary)
            return True

        if lower_input in ("plugins", "/plugins"):
            self._show_plugins()
            return True

        if lower_input in ("recipes", "/recipes"):
            self._show_recipes()
            return True

        if lower_input in ("tools", "/tools"):
            self._show_tools()
            return True

        if lower_input in ("stats", "/stats"):
            self._show_stats()
            return True

        if lower_input in ("config", "/config"):
            self._interactive_config()
            return True

        if lower_input in ("credentials", "/credentials"):
            self._show_credentials()
            return True

        if lower_input in ("sessions", "/sessions"):
            self._show_sessions()
            return True

        if lower_input in ("tasks", "/tasks"):
            TaskBrowser(self.task_manager, self.ui.console).show()
            return True

        if lower_input.startswith("model ") or lower_input.startswith("/model "):
            model_arg = user_input.split(" ", 1)[1].strip() if " " in user_input else ""
            self._change_model(model_arg)
            return True

        if lower_input in ("model", "/model"):
            self._show_models()
            return True

        if lower_input.startswith("resume ") or lower_input.startswith("/resume "):
            session_id = user_input.split(" ", 1)[1].strip()
            self._resume_session(session_id)
            return True

        # Claude Code commands — order matters: code-sessions and code-continue before code
        if lower_input in ("code-sessions", "/code-sessions"):
            self._show_code_sessions()
            return True

        if lower_input.startswith("code-continue ") or lower_input.startswith("/code-continue "):
            args = user_input.split(" ", 1)[1].strip()
            self._continue_code_session(args)
            return True

        if lower_input.startswith("code ") or lower_input.startswith("/code "):
            prompt = user_input.split(" ", 1)[1].strip()
            if prompt:
                self._run_code_task(prompt=prompt)
            else:
                self._run_code_task()
            return True

        if lower_input in ("code", "/code"):
            self._run_code_task()
            return True

        if not user_input.strip():
            return True

        # Auto-detect coding requests
        code_cfg = getattr(self.config, 'code', None)
        if (code_cfg and code_cfg.enabled and code_cfg.auto_detect
                and self._code_detector.is_coding_request(user_input)):
            self.ui.print_info("This looks like a coding task. Routing to Claude Code...")
            self.ui.print_info("[dim]Tip: Use 'code' for explicit mode, or set auto_detect = false in config.[/dim]")
            self._run_code_task(prompt=user_input)
            return True

        # Check rate limit before making API call
        if not self._check_rate_limit():
            return True

        # Log user query
        self.audit.log_user_query(user_input)
        self.session.add_message("user", user_input)

        # Get system context (now cached)
        system_context = self.system_cache.get_or_compute(
            "general",
            lambda: self.system.get_context().to_summary()
        )

        # Send to Claude with streaming (if enabled) or blocking request
        use_streaming = getattr(self.config.api, 'streaming', True)

        with self.ui.streaming_response() as handler:
            try:
                on_text = handler.add_text if use_streaming else None
                response = self.claude.send_message(user_input, system_context, on_text=on_text)
            except Exception as exc:
                self.ui.print_error(f"Error communicating with Claude: {exc}")
                return True

        # Record API usage
        self._record_api_usage()

        # Process response - streamed text was already displayed, non-streamed needs print
        if handler.streamed_text:
            self.session.add_message("assistant", handler.streamed_text)
        elif response.text:
            self.ui.print_response(response.text)
            self.session.add_message("assistant", response.text)

        # Handle tool calls
        while response.tool_calls:
            tool_results = self._process_tool_calls(response.tool_calls)

            # Send results back to Claude with streaming
            with self.ui.streaming_response() as handler:
                try:
                    on_text = handler.add_text if use_streaming else None
                    response = self.claude.send_tool_results(tool_results, system_context, on_text=on_text)
                except Exception as exc:
                    self.ui.print_error(f"Error communicating with Claude: {exc}")
                    return True

            # Record API usage for tool result calls
            self._record_api_usage()

            # Show any text response - streamed text was already displayed
            if handler.streamed_text:
                self.session.add_message("assistant", handler.streamed_text)
            elif response.text:
                self.ui.print_response(response.text)
                self.session.add_message("assistant", response.text)

        return True

    def run(self) -> int:
        """
        Run the main AIOS loop.

        Returns:
            Exit code (0 for success)
        """
        # Check if this is first login and run setup wizard if needed
        from .config import is_first_login
        from .main import run_setup
        
        if is_first_login():
            self.ui.console.print("\n[bold yellow]Welcome to AIOS![/bold yellow]")
            self.ui.console.print("It looks like this is your first time using AIOS.")
            self.ui.console.print("Let's run the setup wizard to configure your system.\n")
            
            try:
                from prompt_toolkit import prompt
                run_wizard_input = prompt("Would you like to run the setup wizard now? (y/n) [y]: ").strip().lower()
                run_wizard = run_wizard_input in ('', 'y', 'yes')
                if run_wizard:
                    # Reset config to pick up any changes
                    from .config import reset_config
                    reset_config()
                    
                    setup_result = run_setup()
                    if setup_result != 0:
                        return setup_result
                    
                    # Reload config after setup
                    reset_config()
                    self.config = get_config()
                else:
                    self.ui.console.print("\n[yellow]You can run the setup wizard later with: [cyan]aios --setup[/cyan][/yellow]")
                    self.ui.console.print("[yellow]Or configure manually in [cyan]~/.config/aios/config.toml[/cyan][/yellow]\n")
            except (KeyboardInterrupt, EOFError):
                self.ui.console.print("\n[yellow]Setup cancelled. You can run it later with: [cyan]aios --setup[/cyan][/yellow]\n")
        
        # Initialize Claude client
        try:
            self.claude = ClaudeClient(self.tool_handler)
        except ValueError as e:
            self.ui.print_error(str(e))
            self.ui.print_info("Please set ANTHROPIC_API_KEY or add it to your config file.")
            self.ui.print_info("You can run the setup wizard with: [cyan]aios --setup[/cyan]")
            return 1

        # Start session
        self.session.start_session()
        self.running = True

        # Notify plugins of session start
        self._notify_plugins_session_start()

        # Show welcome
        self.ui.clear_screen()
        self.ui.print_welcome()

        # Show loaded plugins info
        plugin_count = len(self.plugin_manager.list_plugins())
        if plugin_count > 0:
            tool_count = len(self.plugin_manager.get_all_tools())
            recipe_count = len(self.plugin_manager.get_all_recipes())
            self.ui.print_info(
                f"Plugins: {plugin_count} loaded, {tool_count} tools, {recipe_count} recipes available"
            )

        # Main loop
        while self.running:
            try:
                # Show completion notifications for background tasks
                for done_task in self.task_manager.get_unnotified_completions():
                    word = (
                        "completed"
                        if done_task.status == TaskStatus.COMPLETED
                        else "failed"
                    )
                    self.ui.print_info(
                        f"Background task #{done_task.task_id} "
                        f"({done_task.description}) {word}."
                    )
                    done_task.mark_notified()

                # Get user input
                user_input = self._prompt_session.prompt(
                    "You: ",
                    bottom_toolbar=create_bottom_toolbar(
                        self._prompt_session, self.task_manager
                    ),
                ).strip()

                # Handle Ctrl+B sentinel
                if user_input == '\x02':
                    TaskBrowser(self.task_manager, self.ui.console).show()
                    continue

                # Process input with error boundary
                with ErrorBoundary(
                    "process_user_input",
                    show_technical_details=self.config.ui.show_technical_details
                ) as boundary:
                    self.running = self._handle_user_input(user_input)

                # Handle any errors that occurred during processing
                if boundary.has_error:
                    error_ctx = boundary.error_context
                    self.ui.print_error(format_error_for_user(error_ctx))

                    # Log the error
                    self.audit.log(
                        ActionType.COMMAND,
                        f"Error: {error_ctx.operation}",
                        success=False,
                        error=error_ctx.technical_message
                    )

                    # If error is not recoverable, stop the loop
                    if not error_ctx.recoverable:
                        self.ui.print_error("A critical error occurred. Exiting.")
                        self.running = False

            except KeyboardInterrupt:
                self.ui.print_info("\nUse 'exit' to quit, or Ctrl+D")
                continue
            except EOFError:
                self.ui.print_info("\nGoodbye!")
                break

        # Cleanup
        self.task_manager.cleanup()
        self._notify_plugins_session_end()
        self.session.end_session()
        return 0
