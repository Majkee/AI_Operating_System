# Changelog

All notable changes to AIOS are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.10.1] - 2026-01-29

### Changed

#### Improved StreamingDisplay for Long-Running Commands
Replaced the broken Rich Live+Panel approach with a robust Progress-based display:

- **Progress bar with spinner**: Shows `⚙ Installing ansible ████████ 123 lines 0:00:15`
- **Elapsed time**: Real-time duration tracking
- **Line counter**: Shows total lines processed
- **Output storage**: Stores last 200 lines for later viewing
- **'show' command**: View last command output after completion
  - Displays output in a panel with line count
  - Shows truncation info if output exceeded storage limit
  - Clears stored output after viewing
  - Tab completion and `/show` alias supported

**Why the change**: The previous Rich `Live` + `Panel` approach caused display corruption during rapid output (e.g., apt package installations). The new Progress-based approach is rock-solid.

### Added

#### Tests
- 23 new tests in `tests/test_streaming_display.py`:
  - `TestStreamingDisplay` (11): initialization, line handling, progress updates, context manager
  - `TestLastStreamingOutput` (5): storage, retrieval, clearing
  - `TestShowCommand` (4): command recognition, output display
  - `TestShowInCommandRegistry` (3): registry entry validation

---

## [0.10.0] - 2026-01-29

### Added

#### Multi-Step Progress Awareness
Real-time progress display for multi-step tool operations:

- **`MultiStepProgress` class** in `aios/ui/terminal.py`:
  - Shows "Step X/Y: description" with spinner and progress bar
  - Only displays for operations with 2+ tool calls (single steps show clean output)
  - Completion message: "✓ Completed N operations"
  - `multi_step_progress(total)` factory method on `TerminalUI`

- **Human-readable tool descriptions** in `aios/shell.py`:
  - `_get_tool_description()` generates friendly descriptions for tool calls
  - Specific formatting for common tools (e.g., "Reading: config.yaml", "Running: ls -la...")
  - Fallback to "Tool Name" format for unknown tools
  - Long commands truncated to 40 characters

- **Integration in `_process_tool_calls()`**:
  - Tool execution loop wrapped with `MultiStepProgress` context manager
  - Progress updates before each tool execution
  - Step completion marked after each tool finishes

#### Tests
- 13 new tests in `tests/test_progress.py`:
  - `TestMultiStepProgress` (4): single-step no display, multi-step shows progress, update tracking, completion message
  - `TestTerminalUIProgressFactory` (1): factory creates progress instance
  - `TestShellToolDescriptions` (6): run_command, read_file, write_file, search_files, unknown tool fallback, long command truncation
  - `TestProcessToolCallsWithProgress` (2): single/multiple tool call progress behavior

### Changed
- `aios/shell.py` — `_process_tool_calls()` now shows progress for multi-step operations
- `aios/ui/terminal.py` — added `MultiStepProgress` class and factory method

---

## [0.9.1] - 2026-01-28

### Added

#### Usage Statistics Tracking System
New comprehensive statistics tracking for tools, recipes, and plugins:

**Session Statistics (`/stats`):**
- Tools executed count and success rate
- Recipes executed with step counts
- Average execution duration per tool
- Most used tools this session
- Total errors count
- Session duration

**All-Time Statistics (`/stats all`):**
- Aggregated stats across all sessions
- Total sessions count
- Most used tools all-time with success rates
- Most used recipes all-time
- Persistent storage in `~/.config/aios/stats/`

**New Classes:**
- `UsageStatistics` - Central stats tracker
- `ToolStats` - Per-tool statistics
- `RecipeStats` - Per-recipe statistics
- `PluginStats` - Per-plugin statistics

**Integration Points:**
- Tool execution tracked in `ToolHandler.execute()`
- Recipe execution tracked in `RecipeExecutor.execute()`
- Stats saved on session exit
- 19 new tests in `tests/test_stats.py`

## [0.9.0] - 2026-01-28

### Added

#### Claude Code Skill: Docker Management Guide
- New `/docker` skill in `.claude/skills/docker.md`
- Quick reference tables for container lifecycle, image management, Docker Compose
- Common tasks: status viewing, troubleshooting, cleanup, networking, volumes
- Docker Compose patterns and best practices
- Dockerfile best practices with multi-stage build examples
- Registry operations (Docker Hub, GHCR, private registries)
- Resource limits, health checks, debugging techniques
- Security best practices (non-root, read-only, capabilities)
- Common issues and solutions
- AIOS integration examples

#### Example Recipes (10 New Built-in Recipes)
New workflow recipes that demonstrate the recipe system and use the new Linux tools:

| Recipe | Trigger | Description |
|--------|---------|-------------|
| `web_server_status` | "check web server" | Check nginx/apache status and listening ports |
| `docker_cleanup` | "clean docker" | Show Docker disk usage and prune unused resources |
| `security_audit` | "security check" | Review logins, open ports, and auth failures |
| `network_troubleshoot` | "no internet" | Step-by-step network connectivity diagnosis |
| `service_restart` | "restart service" | Interactive service restart with status checks |
| `log_investigation` | "check logs" | Search system, kernel, and boot logs for errors |
| `process_cleanup` | "system slow" | Find CPU/memory hungry processes |
| `cron_setup` | "scheduled tasks" | View user and system cron jobs |
| `disk_analysis` | "disk full" | Detailed disk usage analysis and large file finder |

#### Ansible Integration in Docker Image
- Added Ansible Core 2.15+ to Docker image
- Pre-installed network automation collections:
  - `ansible.netcommon` - Network common utilities
  - `cisco.ios` - Cisco IOS devices
  - `junipernetworks.junos` - Juniper devices
  - `arista.eos` - Arista switches
- Added SSH client and sshpass for device connectivity
- Included `paramiko`, `netaddr`, `jmespath` Python packages
- Ansible environment pre-configured (host key checking disabled, YAML output)
- Plugins directory (`plugins/`) copied to `/etc/aios/plugins/`
- SSH and Ansible directories created with proper permissions

**Docker run example for Ansible:**
```bash
docker run -it \
  -e ANTHROPIC_API_KEY=sk-... \
  -v ~/.ssh:/home/aios/.ssh:ro \
  -v ./inventory:/home/aios/inventory:ro \
  aios
```

#### Linux Tools Suite (8 New Tools)
Dedicated tools for common Linux operations, providing better structure and user feedback than generic `run_command`:

1. **`manage_service`** - Systemd service management
   - Check service status (`status`, `is-active`)
   - Control services (`start`, `stop`, `restart`, `reload`)
   - Enable/disable at boot (`enable`, `disable`)
   - View service logs (`logs`)

2. **`manage_process`** - Process management
   - List processes sorted by CPU or memory (`list`)
   - Find processes by name (`find`)
   - Get process details (`info`)
   - Kill processes by PID or name (`kill`) with signal options

3. **`network_diagnostics`** - Network troubleshooting
   - View network interfaces (`status`)
   - Test connectivity (`ping`)
   - Check listening ports (`ports`)
   - View active connections (`connections`)
   - DNS lookup (`dns`)
   - Test specific port (`check_port`)
   - View routing table (`route`)

4. **`view_logs`** - System log viewing via journalctl
   - System, kernel, boot, auth, cron logs
   - Service-specific logs
   - Time filtering (`since`)
   - Pattern search (`grep`)

5. **`archive_operations`** - Archive file handling
   - List contents (`list`)
   - Extract archives (`extract`)
   - Create archives (`create`)
   - Supports tar.gz, tar.bz2, tar.xz, zip, 7z

6. **`manage_cron`** - Scheduled task management
   - List user cron jobs (`list`)
   - List system cron directories (`list_system`)
   - Add new cron jobs (`add`)
   - Remove cron jobs by pattern (`remove`)

7. **`disk_operations`** - Storage information
   - Check disk usage (`usage`)
   - Analyze directory sizes (`directory_size`)
   - View mount points (`mounts`)
   - List partitions (`partitions`)
   - Find large files (`large_files`)

8. **`user_management`** - User information (read-only)
   - List user accounts (`list`)
   - Get current user info (`current`)
   - View group memberships (`groups`)
   - Check logged in users (`who`)
   - View recent logins (`last`)

#### Implementation Details
- New `LinuxToolsHandler` class in `aios/handlers/linux.py`
- 28 new tests in `tests/test_linux_tools.py`
- Safety confirmations for dangerous operations (service control, process kill, archive extract, cron modifications)
- Input validation to prevent command injection
- User-friendly output messages

## [0.8.14] - 2026-01-28

### Fixed

#### GitHub Actions CI Fixes
- **Docker workflow**: Added `load: true` to buildx so image is available for `docker run` test
- **Snap workflow**: Replaced deprecated `architectures` with `platforms` for core24 base
- **Test matrix**: Removed Python 3.14 (not yet released)
- **YAML test**: Skip `test_all_playbooks_valid_yaml` if PyYAML not installed

### Changed
- Updated snap version to 0.8.13
- Removed Python 3.14 from classifiers in pyproject.toml

## [0.8.13] - 2026-01-28

### Added

#### Claude Code Skill: Documentation and Versioning Guide
- New `/docs` skill in `.claude/skills/docs.md`
- Explains semantic versioning conventions (MAJOR.MINOR.PATCH)
- Documents changelog format following Keep a Changelog
- Provides templates for changelog entries
- Includes release checklist and commit message format
- Quick reference for common versioning tasks

## [0.8.12] - 2026-01-28

### Added

#### Double-Tap Tab Shows All Commands
- Pressing Tab on empty input now displays all available commands with their descriptions
- Updated bottom toolbar hint: "Tab Tab show all commands"
- Enhanced discoverability of shell commands for new users

## [0.8.11] - 2026-01-28

### Security

#### Critical: Safe Expression Evaluator for Recipe Conditions
- **BREAKING**: Replaced dangerous `eval()` in `aios/plugins.py:412` with safe AST-based expression evaluator
- New `SafeExpressionEvaluator` class supports only safe operations:
  - Simple comparisons: `==`, `!=`, `<`, `>`, `<=`, `>=`, `in`, `not in`
  - Boolean operators: `and`, `or`, `not`
  - Context variable access: `context.key`, `context['key']`
  - Literal values: strings, numbers, booleans, None, lists, tuples, dicts
- Rejects dangerous patterns: `import`, `eval`, `exec`, `__dunder__`, function calls
- `SafeExpressionError` exception for invalid/unsafe expressions
- `safe_eval_condition()` helper function

#### Path Traversal Protection
- `FileHandler._ensure_safe_path()` now **rejects** paths outside allowed roots (was: warn only)
- Platform-aware temp directory detection (Windows: `%TEMP%`, Linux: `/tmp`)
- All file tool handlers (`handle_read_file`, `handle_write_file`, `handle_search_files`, `handle_list_directory`) catch and handle `PermissionError`
- Proper logging of access denied attempts

### Added

#### Comprehensive Handler Tests
- New `tests/test_handlers.py` with 46 tests covering:
  - `TestCommandHandler` (8): simple execution, sudo, timeout, blocked commands, confirmation, background tasks, streaming
  - `TestFileToolHandler` (11): read/write/search/list with success, errors, permission denied
  - `TestSystemHandler` (5): general/disk/memory/cpu/processes info
  - `TestAppHandler` (8): install/remove/search packages, clarification, open application
  - `TestPathValidation` (3): home directory, temp directory, system path rejection
  - `TestSafeExpressionEvaluator` (11): equality, comparisons, boolean ops, membership, forbidden patterns

### Changed

#### Exception Handling Improvements
- Replaced 19 bare `except Exception:` handlers with specific exception types
- Added logging throughout codebase for better debugging:
  - `aios/ui/completions.py` — session fetcher errors
  - `aios/shell.py` — session ID fetching
  - `aios/context/session.py` — save/load/list sessions
  - `aios/main.py` — config file reading
  - `aios/tasks/models.py` — display callback errors
  - `aios/safety/audit.py` — audit export
  - `aios/commands/sessions.py`, `aios/commands/code.py` — date parsing
  - `aios/commands/display.py` — credential listing
  - `aios/config.py` — first login check
  - `aios/code/runner.py` — session loading
  - `aios/executor/files.py` — file info retrieval
  - `aios/handlers/commands.py` — streaming display callback

### Fixed
- `tests/test_plugins.py::TestRecipeExecutor::test_execute_with_condition` updated to use safe expression syntax

### Tests
- Total tests: 490 passed, 10 skipped
- New handler tests: 46

---

## [0.8.10] - 2026-01-28

### Added

#### Context Window Management
- Automatic conversation history management to prevent token limit crashes
- `estimate_tokens()`, `estimate_message_tokens()`, `estimate_history_tokens()` — token counting functions using character-based heuristic (4 chars ≈ 1 token)
- `_get_context_usage()` — returns current token count and percentage of budget
- `_needs_summarization()` — checks if context exceeds threshold (configurable, default 75% of budget)
- `_summarize_history()` — uses Claude to create concise summary of older messages, keeps recent messages verbatim
- `_maybe_manage_context()` — called before each API request to trigger summarization if needed
- `_conversation_summary` field — stores summary of older conversation
- `_summarized_message_count` — tracks how many messages have been summarized
- `get_context_stats()` — returns detailed context window statistics including all config values
- Summary included in system prompt as "Earlier Conversation Summary" section

#### Configurable Summarization Settings
- `context_budget` config option under `[api]` section (default: 150000 tokens)
- `summarize_threshold` config option (default: 0.75) — trigger summarization at this percentage of budget (0.5-0.95)
- `min_recent_messages` config option (default: 6) — always keep this many recent messages verbatim (2-20)
- Interactive config menu includes all three settings with dropdown selections
- Settings available via `config` command: context budget (free input), summarize threshold (50%-90% dropdown), min recent messages (2-20 dropdown)

#### Constants (Defaults)
- `DEFAULT_CONTEXT_BUDGET = 150000` — conservative limit leaving room for response
- `SUMMARIZE_THRESHOLD = 0.75` — trigger summarization at 75% of budget
- `MIN_RECENT_MESSAGES = 6` — always keep at least 6 recent messages verbatim
- `CHARS_PER_TOKEN = 4` — estimation ratio for English text

#### Tests
- 30 tests in `tests/test_context_window.py`:
  - `TestTokenEstimation` (9): empty/short/long text, string/text-block/tool-use/tool-result messages, empty/multiple history
  - `TestContextWindowManagement` (7): initialization, default thresholds fallback, get_context_usage, needs_summarization true/false, clear_history, get_context_stats
  - `TestSummarization` (5): format_messages, keeps_recent_messages, sets_summary, handles_failure, skipped_when_few
  - `TestSystemPromptWithSummary` (2): includes/excludes summary
  - `TestConfigDefaults` (6): has context_budget/custom, has summarize_threshold/custom, has min_recent_messages/custom
  - `TestContextStatsIncludesConfig` (1): stats include min_recent_messages

### Changed
- `aios/claude/client.py` — added logging import; added token estimation functions and constants; `ClaudeClient.__init__` initializes context management fields from config; `_build_system_prompt()` includes conversation summary; `send_message()` and `send_tool_results()` call `_maybe_manage_context()`; `clear_history()` also clears summary; `get_history_summary()` includes context stats; `_summarize_history()` uses `self.min_recent_messages` from config
- `aios/config.py` — `APIConfig` gains `context_budget: int = 150000`, `summarize_threshold: float = 0.75`, `min_recent_messages: int = 6` fields
- `aios/data/default.toml` — added `context_budget`, `summarize_threshold`, `min_recent_messages` under `[api]`
- `aios/shell.py` — interactive config menu includes context_budget (int), summarize_threshold (choice dropdown), min_recent_messages (choice dropdown)
- `tests/test_streaming.py` — updated mocks to include all new config fields
- `README.md` — updated config reference with new summarization options, test count updated to 454

---

## [0.7.0] - 2026-01-28

### Added

#### Streaming Responses
- Real-time word-by-word streaming of Claude's responses for a modern chat experience
- `StreamingResponseHandler` context manager in `aios/ui/terminal.py` — manages spinner → live Markdown transition
- `_stream_request()` method in `ClaudeClient` using `client.messages.stream()` API
- `on_text` callback parameter on `send_message()` and `send_tool_results()` methods
- `streaming` config option under `[api]` section (default: `true`)
- Smooth visual transition: spinner while waiting, then live-updating Markdown as text arrives
- Configurable: disable streaming via config for debugging or slow terminals

#### Interactive Configuration Menu
- `config` / `/config` command opens an interactive settings menu
- Table display of all configurable settings with current values
- Number-based selection to change any setting
- Boolean settings show ON/OFF toggle menu
- Model selection shows dropdown of all available models with descriptions (speed, cost)
- Numeric settings prompt for input with validation
- Changes saved immediately to `~/.config/aios/config.toml`
- Settings take effect immediately without restart

#### Helper Methods (Code Quality)
- `_build_system_prompt()` — deduplicated system prompt construction
- `_store_assistant_history()` — deduplicated conversation history storage

#### Tests
- 16 new tests in `tests/test_streaming.py`:
  - `TestClaudeClientHelpers` (5): `_build_system_prompt` with/without context, `_store_assistant_history` text-only/tool-calls/mixed
  - `TestStreamingResponseHandler` (5): spinner start, no-text exit, first-text transition, text accumulation, live display updates
  - `TestAPIConfigStreaming` (2): default true, can be disabled
  - `TestSendMessageStreaming` (2): no `on_text` uses `create()`, with `on_text` uses `stream()`
  - `TestSendToolResultsStreaming` (2): same streaming/blocking branch tests

### Changed
- `aios/claude/client.py` — added `Callable` import; added helper methods; `send_message()` and `send_tool_results()` accept optional `on_text` callback for streaming
- `aios/ui/terminal.py` — added `StreamingResponseHandler` class; added `streaming_response()` factory method to `TerminalUI`; updated help text
- `aios/shell.py` — `_handle_user_input()` uses `streaming_response()` handler; replaced `ErrorRecovery.retry` with try/except for streaming compatibility; added `_interactive_config()` method
- `aios/config.py` — `APIConfig` gains `streaming: bool = True` field
- `aios/data/default.toml` — added `streaming = true` under `[api]`
- `config/default.toml` — added `streaming = true` under `[api]`
- `aios/ui/completions.py` — added `config` to command registry

### Removed
- `config set <key> <value>` command-line syntax (replaced by interactive menu)

---

## [0.6.0] - 2026-01-28

### Added

#### Tool Result Cache
- `ToolCacheConfig` dataclass for per-tool cache configuration (cacheable flag, TTL, key_params)
- `ToolResultCache` class that caches raw `ToolResult` objects at the tool execution layer — expensive operations (subprocess calls, psutil, file I/O) are skipped on cache hits while Claude still generates fresh prose responses
- `get_tool_result_cache()` global singleton accessor
- `ToolHandler.set_cache()` method to attach a `ToolResultCache` to the tool handler
- Cache check before handler invocation and cache store + invalidation after, integrated into `ToolHandler.execute()`
- Per-tool configurations: `get_system_info` (30s), `read_file` (300s), `list_directory` (60s), `search_files` (60s)
- Invalidation rules: `write_file` invalidates `read_file` (specific path), `list_directory` (all), `search_files` (all); `manage_application` invalidates `get_system_info`; `run_command` wipes all cacheable tools
- `explanation` parameter excluded from cache keys so rephrased requests hit the same entry
- Tool Result Cache stats in the `stats` command output (hit rate, entries, evictions)

#### Tests
- 9 tests in `TestToolResultCache`: unconfigured tool, store/retrieve, failure exclusion, TTL expiry, explanation exclusion, specific-key invalidation, wipe-all invalidation, stats tracking, clear
- `TestGlobalCaches.test_get_tool_result_cache` singleton test

### Changed
- `aios/cache.py` — replaced `QueryCache` with `ToolResultCache` and `ToolCacheConfig`; updated module docstring and imports
- `aios/claude/tools.py` — `ToolHandler` gains `_cache` field and `set_cache()` method; `execute()` adds cache lookup/store/invalidation around handler calls
- `aios/shell.py` — imports `get_tool_result_cache`, `ToolResultCache`, `ToolCacheConfig`, `_generate_key` instead of `get_query_cache`, `QueryCache`; `__init__` creates `self.tool_cache` and calls `_configure_tool_cache()` + `tool_handler.set_cache()`; new `_configure_tool_cache()` method with per-tool configs and invalidation rules; `_handle_system_info` simplified (no more `system_cache.get_or_compute` wrappers — caching is transparent via `ToolHandler.execute()`); `_handle_user_input` no longer checks/stores query cache; `_show_stats` displays tool result cache stats instead of query cache stats
- `tests/test_cache.py` — `TestQueryCache` replaced by `TestToolResultCache`; `TestGlobalCaches` updated
- `tests/test_tasks.py` — mock reference updated from `get_query_cache` to `get_tool_result_cache`
- `CACHING.md` — "Query Cache" section replaced with "Tool Result Cache" documentation
- `ARCHITECTURE.md` — caching table, ToolHandler API, data flow diagram, and performance section updated
- `README.md` — cache.py description, caching feature section, and CACHING.md link text updated
- `MANUAL_TESTS.md` — version bumped; Query Cache manual tests replaced with Tool Result Cache tests

### Removed
- `QueryCache` class — fragile pattern-based matching of user queries to cache Claude's prose responses
- `_query_cache` global and `get_query_cache()` accessor
- Query cache lookup/store in `_handle_user_input` and `response_parts` accumulator
- `TestQueryCache` test class (5 tests) and `test_get_query_cache` test

---

## [0.5.0] - 2026-01-27

### Added

#### Claude Code Interactive Sessions
- `code` command (bare) launches an interactive Claude Code terminal session — AIOS hands off stdin/stdout/stderr and blocks until the user exits
- `code <task>` launches Claude Code with an initial prompt passed as a positional argument
- `code-continue <id>` resumes a previous session via `--resume`
- `code-continue <id> <prompt>` resumes with an optional prompt
- `LaunchResult` dataclass (`success`, `return_code`, `error`) replaces the old `CodeRunResult`

#### Auth Mode Chooser
- `auth_mode` field on `CodeConfig` (`"api_key"` | `"subscription"` | `None`)
- On first `code` invocation, user is prompted to choose between API key and paid subscription
- Choice is persisted to `~/.config/aios/config.toml` under `[code] auth_mode`
- `_resolve_auth_env()` builds the subprocess environment: sets `ANTHROPIC_API_KEY` for api_key mode, removes it for subscription mode

#### Tests
- 42 tests in `tests/test_code.py`:
  - `TestLaunchResult` (2): defaults, error fields
  - `TestCodeSession` (3): creation, round-trip serialization, no event_count in dict
  - `TestCodeRunner` (14): availability, install instructions, launch not available, correct command for prompt/bare/resume/resume+prompt, success/nonzero exit, auth env api_key/subscription/none, session persistence, empty sessions
  - `TestCodeConfig` (4): defaults, auth_mode default/set, in AIOSConfig
  - `TestCommandRegistry` (3): code/code-continue/code-sessions in registry
  - `TestSystemPromptIntegration` (1): prompt mentions Claude Code
  - `TestCodingRequestDetector` (14): unchanged from v0.4.0

### Changed
- `aios/code/runner.py` — rewritten: removed `CodeEvent`, `CodeRunResult`, NDJSON parsing, threading; added `LaunchResult`, `_resolve_auth_env()`, `launch_interactive()` using `subprocess.run()` with no pipe redirection; `CodeSession` no longer has `event_count`
- `aios/code/__init__.py` — exports `LaunchResult` instead of `CodeRunResult` and `CodeEvent`
- `aios/config.py` — `CodeConfig` gains `auth_mode: Optional[str]` field
- `aios/shell.py` — removed `CodeStreamingDisplay`/`CodeOutputFormatter` imports; rewrote `_run_code_task()` to accept optional prompt, call `_ensure_code_auth_mode()`, then `launch_interactive()`; added `_ensure_code_auth_mode()` and `_save_code_auth_mode()`; bare `code` now launches interactive session; auto-detection calls `_run_code_task(prompt=...)` instead of wrapping; `_show_code_sessions()` table no longer has "Events" column
- `aios/ui/terminal.py` — help text updated: `code` described as interactive session launcher
- `aios/ui/completions.py` — `code` entry help updated to "Launch Claude Code (optionally with an initial prompt)"
- `aios/claude/client.py` — system prompt updated to describe `code` as an interactive session launch
- `config/default.toml` — added commented `auth_mode` under `[code]`
- `aios/data/default.toml` — added commented `auth_mode` under `[code]`

### Removed
- `aios/code/formatter.py` — deleted entirely (Claude Code owns the terminal now)
- `CodeEvent` dataclass — no longer needed without NDJSON parsing
- `CodeRunResult` dataclass — replaced by `LaunchResult`
- `_build_command()`, `_parse_event()`, `run()` methods — replaced by `launch_interactive()`
- `event_count` field from `CodeSession`
- NDJSON stream parsing and threading logic from runner

---

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
