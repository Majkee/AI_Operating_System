"""
Main AIOS shell - the interactive conversation loop.

This is the core of AIOS, handling:
- User input
- Claude API communication
- Tool execution
- Response display
"""

from typing import Optional, Dict, Any
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
from .executor.sandbox import CommandExecutor, InteractiveExecutor
from .executor.files import FileHandler
from .context.system import SystemContextGatherer
from .context.session import SessionManager
from .safety.guardrails import SafetyGuard
from .safety.audit import AuditLogger, ActionType
from .ui.terminal import TerminalUI, get_last_streaming_output, clear_last_streaming_output
from .ui.prompts import ConfirmationPrompt, ConfirmationResult
from .errors import (
    ErrorBoundary,
    format_error_for_user,
)
from .skills import (
    get_skill_manager,
    ToolDefinition,
    Recipe,
)
from .cache import (
    get_system_info_cache,
    get_tool_result_cache,
    ToolCacheConfig,
    _generate_key,
)
from .ratelimit import (
    get_rate_limiter,
    configure_rate_limiter,
    RateLimitConfig,
)

# Import refactored modules
from .handlers import CommandHandler, FileToolHandler, SystemHandler, AppHandler, LinuxToolsHandler
from .commands import DisplayCommands, ConfigCommands, SessionCommands, CodeCommands


class AIOSShell:
    """The main AIOS interactive shell."""

    def __init__(self):
        """Initialize the AIOS shell."""
        # Ensure config directories exist
        ensure_config_dirs()

        # Load configuration
        self.config = get_config()

        # Initialize core components
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
        self.files = FileHandler()
        self.system = SystemContextGatherer()
        self.session = SessionManager()
        self.audit = AuditLogger()

        # Initialize tool handler
        self.tool_handler = ToolHandler()

        # Initialize skill system
        self.skill_manager = get_skill_manager()
        self._load_skills()

        # Initialize caching
        self.system_cache = get_system_info_cache()
        self.tool_cache = get_tool_result_cache()
        self._configure_tool_cache()
        self.tool_handler.set_cache(self.tool_cache)

        # Initialize rate limiting
        self.rate_limiter = get_rate_limiter()
        self._configure_rate_limiter()

        # Initialize handlers
        self._init_handlers()

        # Register tools after handlers are initialized
        self._register_tools()

        # Initialize commands
        self._init_commands()

        # Initialize Claude client (may fail if no API key)
        self.claude: Optional[ClaudeClient] = None

        # Session state
        self.running = False

        # Setup prompt session
        self._setup_prompt_session()

    def _init_handlers(self) -> None:
        """Initialize tool handlers."""
        self.cmd_handler = CommandHandler(
            executor=self.executor,
            safety=self.safety,
            audit=self.audit,
            ui=self.ui,
            prompts=self.prompts,
            task_manager=self.task_manager,
        )

        self.file_handler = FileToolHandler(
            files=self.files,
            safety=self.safety,
            audit=self.audit,
            ui=self.ui,
            prompts=self.prompts,
        )

        self.system_handler = SystemHandler(
            system=self.system,
            audit=self.audit,
            ui=self.ui,
        )

        self.app_handler = AppHandler(
            executor=self.executor,
            safety=self.safety,
            audit=self.audit,
            ui=self.ui,
            prompts=self.prompts,
            streaming_executor=self.cmd_handler._execute_streaming,
        )

        self.linux_handler = LinuxToolsHandler(
            executor=self.executor,
            safety=self.safety,
            audit=self.audit,
            ui=self.ui,
            prompts=self.prompts,
        )

    def _init_commands(self) -> None:
        """Initialize shell commands."""
        self.display_cmds = DisplayCommands(
            ui=self.ui,
            skill_manager=self.skill_manager,
            rate_limiter=self.rate_limiter,
            system_cache=self.system_cache,
            tool_cache=self.tool_cache,
        )

        self.config_cmds = ConfigCommands(
            ui=self.ui,
            config=self.config,
        )

        self.session_cmds = SessionCommands(
            ui=self.ui,
            session_manager=self.session,
        )

        self.code_cmds = CodeCommands(
            ui=self.ui,
            code_runner=self.code_runner,
            audit=self.audit,
            config=self.config,
        )

    def _setup_prompt_session(self) -> None:
        """Setup prompt toolkit session."""
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
        self.tool_handler.register("run_command", self.cmd_handler.handle_run_command)
        self.tool_handler.register("read_file", self.file_handler.handle_read_file)
        self.tool_handler.register("write_file", self.file_handler.handle_write_file)
        self.tool_handler.register("search_files", self.file_handler.handle_search_files)
        self.tool_handler.register("list_directory", self.file_handler.handle_list_directory)
        self.tool_handler.register("get_system_info", self.system_handler.handle_system_info)
        self.tool_handler.register("manage_application", self.app_handler.handle_manage_application)
        self.tool_handler.register("ask_clarification", self.app_handler.handle_ask_clarification)
        self.tool_handler.register("open_application", self.app_handler.handle_open_application)

        # Linux-specific tools
        self.tool_handler.register("manage_service", self.linux_handler.handle_manage_service)
        self.tool_handler.register("manage_process", self.linux_handler.handle_manage_process)
        self.tool_handler.register("network_diagnostics", self.linux_handler.handle_network_diagnostics)
        self.tool_handler.register("view_logs", self.linux_handler.handle_view_logs)
        self.tool_handler.register("archive_operations", self.linux_handler.handle_archive_operations)
        self.tool_handler.register("manage_cron", self.linux_handler.handle_manage_cron)
        self.tool_handler.register("disk_operations", self.linux_handler.handle_disk_operations)
        self.tool_handler.register("user_management", self.linux_handler.handle_user_management)

    def _load_skills(self) -> None:
        """Load skills and register their tools."""
        try:
            loaded_skills = self.skill_manager.load_all()
            if loaded_skills:
                self.ui.print_info(f"Loaded {len(loaded_skills)} skill(s)")

            # Register skill tools
            for tool in self.skill_manager.get_all_tools().values():
                self._register_skill_tool(tool)

        except Exception as e:
            self.ui.print_warning(f"Failed to load some skills: {e}")

    def _register_skill_tool(self, tool: ToolDefinition) -> None:
        """Register a skill tool with the tool handler."""
        def skill_tool_handler(params: Dict[str, Any]) -> ToolResult:
            if tool.requires_confirmation:
                explanation = params.get("explanation", f"Running {tool.name}")
                result = self.prompts.confirm(
                    f"Allow {tool.name}?",
                    default=True,
                    warning=f"This skill tool wants to: {explanation}"
                )
                if result != ConfirmationResult.YES:
                    return ToolResult(
                        success=False,
                        output="",
                        user_friendly_message="Okay, cancelled."
                    )

            try:
                result = tool.handler(params)
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
                    user_friendly_message=f"Skill tool failed: {e}"
                )

        self.tool_handler.register_tool(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
            handler=skill_tool_handler,
            requires_confirmation=tool.requires_confirmation
        )

    def _configure_rate_limiter(self) -> None:
        """Configure rate limiter from config."""
        config = RateLimitConfig(
            requests_per_minute=getattr(self.config.api, 'requests_per_minute', 50),
            requests_per_hour=getattr(self.config.api, 'requests_per_hour', 500),
            tokens_per_minute=getattr(self.config.api, 'tokens_per_minute', 100000),
        )
        configure_rate_limiter(config)

    def _configure_tool_cache(self) -> None:
        """Configure per-tool caching and invalidation rules."""
        tc = self.tool_cache

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

        tc.add_invalidation_rule(
            "write_file", "read_file",
            key_transform=lambda inp: _generate_key(
                "read_file", (), {"path": inp.get("path")},
            ),
        )
        tc.add_invalidation_rule("write_file", "list_directory")
        tc.add_invalidation_rule("write_file", "search_files")
        tc.add_invalidation_rule("manage_application", "get_system_info")

        for tool in ("get_system_info", "read_file", "list_directory", "search_files"):
            tc.add_invalidation_rule("run_command", tool)

    def _get_session_ids(self) -> list:
        """Return recent session IDs for tab completion."""
        try:
            sessions = self.session.list_sessions(limit=20)
            return [s["session_id"] for s in sessions]
        except (OSError, IOError, KeyError, ValueError) as e:
            # Graceful degradation for tab completion
            return []

    def _get_code_session_ids(self) -> list:
        """Return recent code session IDs for tab completion."""
        try:
            sessions = self.code_runner.get_sessions(limit=20)
            return [s.session_id for s in sessions]
        except (OSError, IOError, AttributeError, ValueError) as e:
            # Graceful degradation for tab completion
            return []

    def _notify_skills_session_start(self) -> None:
        """Notify all skills that a session has started."""
        for skill_meta in self.skill_manager.list_skills():
            try:
                skill = self.skill_manager._skills.get(skill_meta.name)
                if skill and hasattr(skill.instance, 'on_session_start'):
                    skill.instance.on_session_start()
            except Exception as e:
                self.ui.print_warning(f"Skill {skill_meta.name} session start failed: {e}")

    def _notify_skills_session_end(self) -> None:
        """Notify all skills that a session is ending."""
        for skill_meta in self.skill_manager.list_skills():
            try:
                skill = self.skill_manager._skills.get(skill_meta.name)
                if skill and hasattr(skill.instance, 'on_session_end'):
                    skill.instance.on_session_end()
            except Exception as e:
                self.ui.print_warning(f"Skill {skill_meta.name} session end failed: {e}")

    def _check_rate_limit(self) -> bool:
        """Check rate limit before API call. Returns True if allowed."""
        status = self.rate_limiter.check()
        if status.is_limited:
            self.ui.print_warning(
                f"Rate limited. Please wait {status.wait_time:.1f}s before next request."
            )
            return False
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

    def _show_last_output(self) -> None:
        """Show the last streaming command output."""
        output_data = get_last_streaming_output()
        if output_data is None:
            self.ui.print_info("No recent command output to show.")
            return

        lines = output_data.get("lines", [])
        total = output_data.get("total", 0)
        description = output_data.get("description", "Command")

        if not lines:
            self.ui.print_info("No output was captured.")
            return

        # Show output in a panel
        from rich.panel import Panel
        from rich.box import ROUNDED

        # Show how many lines we're displaying vs total
        if len(lines) < total:
            title = f"📋 {description} (last {len(lines)} of {total} lines)"
        else:
            title = f"📋 {description} ({total} lines)"

        content = "\n".join(lines)
        self.ui.console.print(Panel(
            content,
            title=title,
            border_style="blue",
            box=ROUNDED,
        ))

        # Clear after showing
        clear_last_streaming_output()

    def _get_tool_description(self, tool_name: str, tool_input: dict) -> str:
        """Generate a human-readable description for a tool call."""
        descriptions = {
            "run_command": lambda i: f"Running: {i.get('command', 'command')[:40]}...",
            "read_file": lambda i: f"Reading: {Path(i.get('path', '')).name}",
            "write_file": lambda i: f"Writing: {Path(i.get('path', '')).name}",
            "search_files": lambda i: f"Searching for: {i.get('query', 'files')}",
            "list_directory": lambda i: f"Listing: {Path(i.get('path', '')).name or 'directory'}",
            "get_system_info": lambda i: f"Getting {i.get('info_type', 'system')} info",
            "manage_application": lambda i: f"{i.get('action', 'Managing').title()} app",
            "archive_operations": lambda i: f"{i.get('operation', 'Archive').title()} operation",
            "disk_operations": lambda i: f"Disk: {i.get('operation', 'operation')}",
        }
        if tool_name in descriptions:
            try:
                return descriptions[tool_name](tool_input)
            except Exception:
                pass
        # Fallback: format tool name nicely
        return tool_name.replace("_", " ").title()

    def _process_tool_calls(self, tool_calls: list) -> list:
        """Process tool calls and return results."""
        results = []
        total = len(tool_calls)

        with self.ui.multi_step_progress(total) as progress:
            for idx, tool_call in enumerate(tool_calls, 1):
                tool_name = tool_call["name"]
                tool_input = tool_call["input"]
                tool_id = tool_call["id"]

                # Update progress with human-readable description
                description = self._get_tool_description(tool_name, tool_input)
                progress.update(idx, description)

                result = self.tool_handler.execute(tool_name, tool_input)

                content = result.output if result.success else f"Error: {result.error}"

                results.append({
                    "tool_use_id": tool_id,
                    "content": content,
                    "is_error": not result.success
                })

                # Mark step complete (advances progress bar)
                progress.step_complete()

                if result.user_friendly_message:
                    if result.success:
                        self.ui.print_success(result.user_friendly_message)
                    else:
                        self.ui.print_error(result.user_friendly_message)

        return results

    def _handle_user_input(self, user_input: str) -> bool:
        """Handle user input and return whether to continue."""
        lower_input = user_input.lower().strip()

        # Exit commands
        if lower_input in ("exit", "quit", "bye", "goodbye"):
            self._save_session_stats()
            self.ui.print_info("Goodbye! See you next time.")
            return False

        # Shell commands
        if lower_input == "help":
            self.ui.print_help()
            return True

        if lower_input == "clear":
            self.ui.clear_screen()
            return True

        if lower_input in ("show", "/show"):
            self._show_last_output()
            return True

        if lower_input == "history":
            summary = self.session.get_session_summary()
            self.ui.print_system_info(summary)
            return True

        if lower_input in ("skills", "/skills"):
            self.display_cmds.show_skills()
            return True

        if lower_input in ("recipes", "/recipes"):
            self.display_cmds.show_recipes()
            return True

        if lower_input in ("tools", "/tools"):
            self.display_cmds.show_tools(self.tool_handler)
            return True

        if lower_input in ("stats", "/stats"):
            self.display_cmds.show_stats()
            return True

        if lower_input in ("stats all", "/stats all"):
            self.display_cmds.show_stats_alltime()
            return True

        if lower_input in ("config", "/config"):
            self.config_cmds.interactive_config(self.claude)
            return True

        if lower_input in ("credentials", "/credentials"):
            self.display_cmds.show_credentials()
            return True

        if lower_input in ("sessions", "/sessions"):
            self.session_cmds.show_sessions()
            return True

        if lower_input in ("tasks", "/tasks"):
            TaskBrowser(self.task_manager, self.ui.console).show()
            return True

        if lower_input.startswith("model ") or lower_input.startswith("/model "):
            model_arg = user_input.split(" ", 1)[1].strip() if " " in user_input else ""
            self.config_cmds.change_model(model_arg, self.claude)
            return True

        if lower_input in ("model", "/model"):
            self.config_cmds.show_models()
            return True

        if lower_input.startswith("resume ") or lower_input.startswith("/resume "):
            session_id = user_input.split(" ", 1)[1].strip()
            self.session_cmds.resume_session(session_id, self.claude)
            return True

        # Claude Code commands
        if lower_input in ("code-sessions", "/code-sessions"):
            self.code_cmds.show_code_sessions()
            return True

        if lower_input.startswith("code-continue ") or lower_input.startswith("/code-continue "):
            args = user_input.split(" ", 1)[1].strip()
            self.code_cmds.continue_code_session(args)
            return True

        if lower_input.startswith("code ") or lower_input.startswith("/code "):
            prompt = user_input.split(" ", 1)[1].strip()
            if prompt:
                self.code_cmds.run_code_task(prompt=prompt)
            else:
                self.code_cmds.run_code_task()
            return True

        if lower_input in ("code", "/code"):
            self.code_cmds.run_code_task()
            return True

        if not user_input.strip():
            return True

        # Auto-detect coding requests
        code_cfg = getattr(self.config, 'code', None)
        if (code_cfg and code_cfg.enabled and code_cfg.auto_detect
                and self._code_detector.is_coding_request(user_input)):
            self.ui.print_info("This looks like a coding task. Routing to Claude Code...")
            self.ui.print_info("[dim]Tip: Use 'code' for explicit mode, or set auto_detect = false in config.[/dim]")
            self.code_cmds.run_code_task(prompt=user_input)
            return True

        # Rate limit check
        if not self._check_rate_limit():
            return True

        # Log and send to Claude
        self.audit.log_user_query(user_input)
        self.session.add_message("user", user_input)

        system_context = self.system_cache.get_or_compute(
            "general",
            lambda: self.system.get_context().to_summary()
        )

        use_streaming = getattr(self.config.api, 'streaming', True)

        with self.ui.streaming_response() as handler:
            try:
                on_text = handler.add_text if use_streaming else None
                response = self.claude.send_message(user_input, system_context, on_text=on_text)
            except Exception as exc:
                self.ui.print_error(f"Error communicating with Claude: {exc}")
                return True

        self._record_api_usage()

        if handler.streamed_text:
            self.session.add_message("assistant", handler.streamed_text)
        elif response.text:
            self.ui.print_response(response.text)
            self.session.add_message("assistant", response.text)

        # Handle tool calls
        while response.tool_calls:
            tool_results = self._process_tool_calls(response.tool_calls)

            with self.ui.streaming_response() as handler:
                try:
                    on_text = handler.add_text if use_streaming else None
                    response = self.claude.send_tool_results(tool_results, system_context, on_text=on_text)
                except Exception as exc:
                    self.ui.print_error(f"Error communicating with Claude: {exc}")
                    return True

            self._record_api_usage()

            if handler.streamed_text:
                self.session.add_message("assistant", handler.streamed_text)
            elif response.text:
                self.ui.print_response(response.text)
                self.session.add_message("assistant", response.text)

        return True

    def run(self) -> int:
        """Run the main AIOS loop."""
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
                    from .config import reset_config
                    reset_config()

                    setup_result = run_setup()
                    if setup_result != 0:
                        return setup_result

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
        self._notify_skills_session_start()

        # Show welcome
        self.ui.clear_screen()
        self.ui.print_welcome()

        # Show loaded skills info
        skill_count = len(self.skill_manager.list_skills())
        if skill_count > 0:
            tool_count = len(self.skill_manager.get_all_tools())
            recipe_count = len(self.skill_manager.get_all_recipes())
            self.ui.print_info(
                f"Skills: {skill_count} loaded, {tool_count} tools, {recipe_count} recipes available"
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

                if boundary.has_error:
                    error_ctx = boundary.error_context
                    self.ui.print_error(format_error_for_user(error_ctx))

                    self.audit.log(
                        ActionType.COMMAND,
                        f"Error: {error_ctx.operation}",
                        success=False,
                        error=error_ctx.technical_message
                    )

                    if not error_ctx.recoverable:
                        self.ui.print_error("A critical error occurred. Exiting.")
                        self.running = False

            except KeyboardInterrupt:
                self.ui.print_info("\nUse 'exit' to quit, or Ctrl+D")
                continue
            except EOFError:
                self._save_session_stats()
                self.ui.print_info("\nGoodbye!")
                break

        # Cleanup
        self.task_manager.cleanup()
        self._notify_skills_session_end()
        self._save_session_stats()
        self.session.end_session()
        return 0

    def _save_session_stats(self) -> None:
        """Save usage statistics for the current session."""
        try:
            from .stats import get_usage_stats
            stats = get_usage_stats()
            stats.save_session_stats()
        except Exception:
            # Don't fail exit if stats can't be saved
            pass
