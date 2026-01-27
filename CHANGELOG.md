# Changelog

All notable changes to AIOS are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-01-27

### Added

#### Background Tasks
- `background` parameter on `run_command` tool — starts commands without timeout, runs until done
- `TaskStatus` enum (`RUNNING`, `COMPLETED`, `FAILED`, `KILLED`) and `BackgroundTask` dataclass with thread-safe output buffer
- `TaskManager` — thread-safe registry for creating, adopting, listing, killing, and cleaning up background tasks
- `TaskBrowser` — interactive Rich table UI with actions: view output, attach to live output, kill, terminate, remove
- **Ctrl+C to background**: during any streaming command, pressing Ctrl+C offers "Background this task? [y/N]:" to adopt the running process
- **Ctrl+B key binding**: opens the task browser from anywhere in the shell
- `tasks` / `/tasks` shell command: opens the task browser
- Bottom toolbar shows running/finished task counts and Ctrl+B hint when tasks exist
- Completion notifications: finished background tasks are announced before each prompt
- System prompt "Background Tasks" section teaches Claude when to use `background: true`
- `_execute_streaming()` rewritten to create `Popen` directly, enabling process adoption on Ctrl+C
- All running background tasks killed during shell shutdown (`cleanup()`)

#### Tests
- 33 new tests in `tests/test_tasks.py`:
  - `TestBackgroundTask` (11): creation, status transitions, output with/without callback, detach display, get_output last_n, kill real process, notified flag, callback exception safety
  - `TestTaskManager` (11): create, ID increments, adopt, get, running count, unnotified completions, kill, remove finished/refused, cleanup, list excludes finished
  - `TestToolbarIntegration` (6): tasks in registry, entry has no arg, toolbar with no tasks/running/finished counts, backward compatibility
  - `TestToolSchema` (2): background param exists and not required
  - `TestSystemPrompt` (1): prompt mentions background
  - `TestIntegration` (2): background starts task, tasks command opens browser

### Changed
- `aios/shell.py` — imports `TaskManager`, `TaskBrowser`, `subprocess`, `threading`, `KeyBindings`; adds `task_manager` to init; Ctrl+B key binding; completion notifications in main loop; Ctrl+B sentinel handling; `tasks` command handler; `background` branch in `_handle_run_command`; `_execute_streaming()` rewritten with direct `Popen` and Ctrl+C-to-background flow; `cleanup()` on exit
- `aios/ui/completions.py` — `tasks` entry added to `COMMAND_REGISTRY`; toolbar refactored into `_compute_left_toolbar()` helper; `create_bottom_toolbar()` accepts optional `task_manager` for right-side task counts + Ctrl+B hint
- `aios/claude/tools.py` — `run_command` schema gains `background` property (boolean, optional)
- `aios/claude/client.py` — `SYSTEM_PROMPT` expanded with "Background Tasks" section
- `tests/test_shell_sudo.py` — `_make_shell_stub` adds `task_manager`; `test_long_running_uses_streaming` updated to mock `Popen` directly (matches new `_execute_streaming` implementation)

---

## [0.3.0] - 2026-01-27

### Added

#### Sudo Support
- `use_sudo` parameter on `run_command` tool — automatically prepends `sudo` when set
- Prevents double-prefixing when command already starts with `sudo`
- User warning displayed when elevated privileges are used
- `sudo` pattern added to safety guardrails as moderate (explained, not blocked)
- System prompt teaches Claude when and how to use `use_sudo`

#### Configurable Timeouts
- `timeout` parameter on `run_command` tool (default 30, max 3600 seconds)
- `ExecutorConfig` model in configuration (`default_timeout`, `max_timeout`)
- `[executor]` section in `config/default.toml` for user-customizable defaults
- `MAX_TIMEOUT` raised from 300 to 3600 seconds (1 hour) for large operations
- `CommandExecutor` reads timeout limits from config at initialization
- User info message shown when timeout exceeds 60 seconds
- Helpful timeout-exceeded message with retry suggestion

#### Live Streaming Output
- `long_running` parameter on `run_command` tool — streams real-time output
- `StreamingDisplay` class with Rich `Live` panel showing last 8 output lines
- `print_streaming_output()` method on `TerminalUI`
- `InteractiveExecutor.execute_streaming()` rewritten with threaded output reading
- Daemon thread reads stdout; main thread enforces timeout via `join(timeout=)`
- Process group kill (`killpg`) on timeout with partial output preserved
- `env` parameter support for environment variable propagation
- `manage_application` install/update actions now use streaming (timeout 600)
- `_execute_streaming()` helper in shell for unified streaming integration

#### System Prompt Guidance
- "Sudo and Elevated Privileges" section — when to use `use_sudo`
- "Timeouts and Long-Running Operations" section — recommended values by task type
- "Handling Large Installations" section — step-by-step approach for big installs

#### Executor Exports
- `InteractiveExecutor` exported from `aios.executor` package `__all__`

#### Tests
- 18 new tests in `tests/test_shell_sudo.py`:
  - Sudo prepending, double-prefix prevention, no-sudo default
  - Custom timeout passing, timeout info display for >60s
  - Streaming executor delegation, standard executor fallback
  - Timeout expiry message with value
  - `ExecutorConfig` defaults and presence in `AIOSConfig`
  - Tool schema validation (timeout, use_sudo, long_running present and optional)
  - Safety guard sudo detection as moderate
  - System prompt content verification

### Changed
- `aios/claude/tools.py` — `run_command` schema gains `timeout`, `use_sudo`, `long_running` properties
- `aios/claude/client.py` — `SYSTEM_PROMPT` expanded with sudo/timeout/long-running guidance
- `aios/executor/sandbox.py` — `MAX_TIMEOUT` 300 → 3600; `CommandExecutor` reads config; `InteractiveExecutor.execute_streaming()` rewritten with threading
- `aios/executor/__init__.py` — exports `InteractiveExecutor`
- `aios/ui/terminal.py` — added `StreamingDisplay` class and `print_streaming_output()` method
- `aios/config.py` — added `ExecutorConfig` model and `executor` field on `AIOSConfig`
- `config/default.toml` — added `[executor]` section
- `aios/safety/guardrails.py` — added `sudo` to `MODERATE_PATTERNS`
- `aios/shell.py` — imports `InteractiveExecutor`; `_handle_run_command` supports sudo/timeout/streaming; added `_execute_streaming()`; `_handle_manage_application` uses streaming for install/update
- `tests/conftest.py` — `mock_config` fixture includes `executor` fields
- `tests/test_sandbox.py` — `MAX_TIMEOUT` assertion updated from 300 to 3600

## [0.2.0] - 2026-01-27

### Added

#### Plugin System
- Dynamic plugin loading from `~/.config/aios/plugins/` and `/etc/aios/plugins/`
- `PluginBase` class for creating custom plugins
- Plugin lifecycle hooks: `on_load`, `on_unload`, `on_session_start`, `on_session_end`
- `ToolDefinition` for registering custom tools with Claude
- `Recipe` system for pre-built multi-step workflows with trigger phrases
- `PluginManager` for discovering, loading, and managing plugins
- `/plugins` command to list loaded plugins
- `/tools` command to list all available tools (built-in + plugin)
- `/recipes` command to list available recipes
- Example Ansible Network plugin with 10 tools, 4 recipes, and 5 built-in playbooks

#### Caching System
- LRU cache with configurable size limits and TTL expiration
- `SystemInfoCache` with type-specific TTLs (disk: 60s, memory: 30s, CPU: 15s, etc.)
- `QueryCache` for caching informational Claude responses
- `@cached` decorator for easy function-level caching
- Thread-safe implementation with cache statistics tracking
- Integrated into shell for system info queries and informational responses

#### Rate Limiting
- Token Bucket algorithm for smooth request rate control
- Sliding Window Counter for fixed-window rate limits
- `APIRateLimiter` combining both strategies
- Configurable limits: requests per minute/hour, tokens per minute
- Shell integration with pre-call checks and approaching-limit warnings
- `/stats` command showing API usage and rate limit status
- `@rate_limited` decorator for function-level limiting

#### Session Persistence
- Automatic session saving on exit
- `/sessions` command to list previous sessions (last 10)
- `resume <session_id>` command to continue previous sessions
- Claude conversation history restoration on resume
- Recent conversation preview when resuming
- Per-session preferences and context variables

#### Credential Management
- Encrypted credential storage using Fernet (AES-128-CBC + HMAC-SHA256)
- Master password protection with PBKDF2-HMAC-SHA256 (480,000 iterations)
- `/credentials` command to list stored credentials (values hidden)
- `store_credential()`, `get_credential()`, `delete_credential()` API
- Plugin integration for secure credential access
- File permissions set to `0600` (owner-only)

#### CI/CD Pipeline
- GitHub Actions workflow for automated testing
- Multi-Python version matrix (3.10, 3.11, 3.12)
- Code coverage with Codecov integration
- Linting: Black, isort, flake8
- Security scanning: Bandit (static analysis), Safety (dependency audit)
- Docker build verification
- Pip dependency caching for faster builds

#### Shell Commands
- `/plugins` - List loaded plugins
- `/tools` - List all available tools
- `/recipes` - List available recipes
- `/stats` - Show session and system statistics
- `/credentials` - List stored credentials
- `/sessions` - List previous sessions
- `resume <id>` - Resume a previous session

#### Documentation
- `PLUGINS.md` - Plugin system guide
- `CACHING.md` - Caching system documentation
- `RATELIMIT.md` - Rate limiting documentation
- `SESSIONS.md` - Session management guide
- `CREDENTIALS.md` - Credential management guide
- `CI.md` - CI/CD pipeline documentation
- `CHANGELOG.md` - This changelog
- `plugins/ANSIBLE_NETWORK.md` - Ansible plugin documentation

### Changed
- `tools.py` - Renamed `TOOLS` to `BUILTIN_TOOLS`, added `ToolHandler` with dynamic tool registration via `register_tool()` and `get_all_tools()`
- `client.py` - Uses dynamic tool list from `ToolHandler` instead of static `TOOLS`
- `shell.py` - Integrated caching, rate limiting, plugins, credentials, and session commands
- `terminal.py` - Added `print_file_content()` with syntax highlighting, updated help text with all new commands
- `read_file` tool - Added `display_content` parameter to show file contents to users
- `requirements.txt` - Added `cryptography>=41.0.0` dependency

### Fixed
- File contents not displayed to user when using `read_file` tool with "show me" requests

## [0.1.0] - 2026-01-20

### Added
- Initial release
- Natural language interface for Linux systems via Claude API
- Core tools: `run_command`, `read_file`, `write_file`, `search_files`, `list_directory`, `get_system_info`, `manage_application`, `ask_clarification`, `open_application`
- Safety guardrails with forbidden/dangerous command patterns
- Confirmation prompts for risky operations
- Automatic file backups before modifications
- Audit logging of all actions
- Sandboxed command execution with timeouts
- Rich terminal UI with syntax highlighting
- Session management with conversation history
- TOML-based configuration with environment variable overrides
- Docker and Docker Compose support
- Interactive setup wizard (`aios --setup`)
- Single command mode (`aios "your command"`)
- Architecture documentation (`ARCHITECTURE.md`)
- Contributing guidelines (`CONTRIBUTING.md`)
- Security policy (`SECURITY.md`)
