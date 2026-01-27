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
from typing import Optional, Dict, Any
from pathlib import Path

from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

from .config import get_config, ensure_config_dirs
from .claude.client import ClaudeClient
from .claude.tools import ToolHandler, ToolResult
from .executor.sandbox import CommandExecutor, CommandResult
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
    get_query_cache,
    SystemInfoCache,
    QueryCache,
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
        self.query_cache = get_query_cache()

        # Initialize rate limiting
        self.rate_limiter = get_rate_limiter()
        self._configure_rate_limiter()

        # Initialize Claude client (may fail if no API key)
        self.claude: Optional[ClaudeClient] = None

        # Session state
        self.running = False

        # Command history
        history_path = Path.home() / ".config" / "aios" / "command_history"
        self.history = FileHistory(str(history_path))

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
        sys_cache_stats = self.system_cache.stats
        for info_type, stats in sys_cache_stats.items():
            if stats.get('hits', 0) > 0 or stats.get('misses', 0) > 0:
                hit_rate = stats['hits'] / (stats['hits'] + stats['misses']) * 100 if (stats['hits'] + stats['misses']) > 0 else 0
                self.ui.console.print(f"  {info_type}: {hit_rate:.0f}% hit rate ({stats['hits']} hits, {stats['misses']} misses)")

        # Plugin stats
        plugins = self.plugin_manager.list_plugins()
        tools = self.plugin_manager.get_all_tools()
        recipes = self.plugin_manager.get_all_recipes()
        self.ui.console.print("\n[bold]Plugins:[/bold]")
        self.ui.console.print(f"  Loaded: {len(plugins)}")
        self.ui.console.print(f"  Tools: {len(tools)}")
        self.ui.console.print(f"  Recipes: {len(recipes)}")

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

        # Clear current conversation buffer
        self.claude.conversation.clear()

        # Add messages to conversation buffer
        for msg in messages[-20:]:  # Keep last 20 messages for context
            if msg.role == "user":
                self.claude.conversation.add_user_message(msg.content)
            elif msg.role == "assistant":
                self.claude.conversation.add_assistant_message(msg.content)

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

        # Execute
        cmd_result = self.executor.execute(command, working_directory=working_dir)

        # Log
        self.audit.log_command(
            command,
            cmd_result.output,
            cmd_result.success,
            working_dir
        )

        return ToolResult(
            success=cmd_result.success,
            output=cmd_result.output,
            error=cmd_result.error_message,
            user_friendly_message=cmd_result.to_user_friendly()
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
        """Handle the get_system_info tool with caching."""
        info_type = params.get("info_type", "general")
        explanation = params.get("explanation", "Getting system information")

        self.ui.print_executing(explanation)

        def fetch_system_info():
            """Fetch fresh system information."""
            return self.system.get_context(force_refresh=True)

        def fetch_processes():
            """Fetch process information."""
            return self.system.get_running_processes(10)

        # Use cached data when available
        if info_type == "disk":
            output = self.system_cache.get_or_compute(
                "disk",
                lambda: self._format_disk_info(fetch_system_info())
            )

        elif info_type == "memory":
            output = self.system_cache.get_or_compute(
                "memory",
                lambda: self._format_memory_info(fetch_system_info())
            )

        elif info_type == "cpu":
            output = self.system_cache.get_or_compute(
                "cpu",
                lambda: self._format_cpu_info(fetch_system_info())
            )

        elif info_type == "processes":
            output = self.system_cache.get_or_compute(
                "processes",
                lambda: self._format_processes_info(fetch_processes())
            )

        else:  # general
            output = self.system_cache.get_or_compute(
                "general",
                lambda: fetch_system_info().to_summary()
            )

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

        # Execute with extended timeout for package operations
        self.ui.print_info(f"Running package operation (this may take a moment)...")
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
        command = f"xdg-open {target}"
        cmd_result = self.executor.execute(command, timeout=5)

        return ToolResult(
            success=cmd_result.success,
            output="",
            user_friendly_message=f"Opened {Path(target).name}" if cmd_result.success else "Couldn't open that"
        )

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

        if lower_input in ("credentials", "/credentials"):
            self._show_credentials()
            return True

        if lower_input in ("sessions", "/sessions"):
            self._show_sessions()
            return True

        if lower_input.startswith("resume ") or lower_input.startswith("/resume "):
            session_id = user_input.split(" ", 1)[1].strip()
            self._resume_session(session_id)
            return True

        if not user_input.strip():
            return True

        # Check rate limit before making API call
        if not self._check_rate_limit():
            return True

        # Check query cache for informational queries
        cached_response = None
        if self.query_cache.is_cacheable(user_input):
            cached_response = self.query_cache.get(user_input)
            if cached_response:
                self.ui.print_response(cached_response)
                return True

        # Log user query
        self.audit.log_user_query(user_input)
        self.session.add_message("user", user_input)

        # Get system context (now cached)
        system_context = self.system_cache.get_or_compute(
            "general",
            lambda: self.system.get_context().to_summary()
        )

        # Send to Claude with progress indicator and error recovery
        with self.ui.print_thinking() as progress:
            task = progress.add_task("Thinking...", total=None)

            # Use retry for API calls (network issues may be transient)
            def send_to_claude():
                return self.claude.send_message(user_input, system_context)

            result = ErrorRecovery.retry(
                send_to_claude,
                max_attempts=2,
                on_retry=lambda attempt, exc: self.ui.print_info(
                    f"Retrying... (attempt {attempt + 1})"
                )
            )

            # Record API usage
            self._record_api_usage()

            if result.is_err:
                error_msg = result.error.user_message if result.error else "Unknown error"
                self.ui.print_error(f"Error communicating with Claude: {error_msg}")
                if result.error and result.error.suggested_action:
                    self.ui.print_info(f"Suggestion: {result.error.suggested_action}")
                return True

            response = result.value

        # Process response
        if response.text:
            self.ui.print_response(response.text)
            self.session.add_message("assistant", response.text)

            # Cache informational responses (no tool calls = pure info)
            if not response.tool_calls and self.query_cache.is_cacheable(user_input):
                self.query_cache.set(user_input, response.text)

        # Handle tool calls
        while response.tool_calls:
            tool_results = self._process_tool_calls(response.tool_calls)

            # Record API usage for tool result calls
            self._record_api_usage()

            # Send results back to Claude
            with self.ui.print_thinking() as progress:
                task = progress.add_task("Thinking...", total=None)
                response = self.claude.send_tool_results(tool_results, system_context)

            # Show any text response
            if response.text:
                self.ui.print_response(response.text)
                self.session.add_message("assistant", response.text)

        return True

    def run(self) -> int:
        """
        Run the main AIOS loop.

        Returns:
            Exit code (0 for success)
        """
        # Initialize Claude client
        try:
            self.claude = ClaudeClient(self.tool_handler)
        except ValueError as e:
            self.ui.print_error(str(e))
            self.ui.print_info("Please set ANTHROPIC_API_KEY or add it to your config file.")
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
                # Get user input
                user_input = prompt(
                    "You: ",
                    history=self.history,
                    auto_suggest=AutoSuggestFromHistory(),
                ).strip()

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
        self._notify_plugins_session_end()
        self.session.end_session()
        return 0
