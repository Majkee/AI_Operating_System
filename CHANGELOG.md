# Changelog

All notable changes to AIOS are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
