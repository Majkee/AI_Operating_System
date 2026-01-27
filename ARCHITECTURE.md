# AIOS Architecture

This document describes the internal architecture of AIOS for contributors and maintainers.

## Overview

AIOS follows a layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                        User Interface                        │
│                    (ui/terminal.py, prompts.py)              │
├─────────────────────────────────────────────────────────────┤
│                      Shell Controller                        │
│                         (shell.py)                           │
├──────────────────────┬──────────────────────────────────────┤
│   Claude Integration │         Safety Layer                  │
│  (claude/client.py,  │    (safety/guardrails.py,            │
│      tools.py)       │         audit.py)                     │
├──────────────────────┴──────────────────────────────────────┤
│                      Execution Layer                         │
│              (executor/sandbox.py, files.py)                 │
├──────────────────────┬──────────────────────────────────────┤
│    Context Layer      │       Support Systems                │
│  (context/system.py,  │  (cache.py, ratelimit.py,           │
│    session.py)        │   plugins.py, credentials.py)        │
├──────────────────────┴──────────────────────────────────────┤
│                    Configuration                             │
│                 (config.py, errors.py)                        │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### Entry Point (`main.py`)

Handles CLI argument parsing and initialization:
- `--setup`: Run interactive configuration wizard
- `--version`: Display version information
- Single command mode: `aios "your command"`
- Interactive mode: `aios`

### Shell Controller (`shell.py`)

The main orchestration layer that:
- Manages the conversation loop
- Coordinates between Claude and tool execution
- Handles user input, special commands, and output
- Maintains session state
- Integrates caching, rate limiting, plugins, and credentials

Key class: `AIOSShell`
- `run()`: Main interaction loop
- `_handle_user_input()`: Process input, dispatch commands or send to Claude
- `_process_tool_calls()`: Dispatch tool calls to appropriate handlers
- `_load_plugins()`: Discover and register plugin tools
- `_check_rate_limit()`: Pre-call rate limit checks
- `_show_sessions()`: List previous sessions
- `_resume_session()`: Load and continue a previous session

### Claude Integration (`claude/`)

#### `client.py`
Manages communication with the Anthropic API:
- Message formatting with system context
- Streaming response handling
- Tool result submission
- Error handling and retries
- Dynamic tool list from `ToolHandler`

Key class: `ClaudeClient`
- `send_message()`: Send user message with conversation history
- `send_tool_results()`: Return tool execution results to Claude

#### `tools.py`
Defines the tools available to Claude and manages dynamic tool registration:

**Built-in Tools:**

| Tool | Purpose |
|------|---------|
| `run_command` | Execute shell commands |
| `read_file` | Read file contents (with optional display) |
| `write_file` | Create/modify files |
| `search_files` | Find files by name or content |
| `list_directory` | Browse directory contents |
| `get_system_info` | Retrieve system metrics |
| `manage_application` | Install/remove packages |
| `ask_clarification` | Request user input |
| `open_application` | Launch applications |

Each tool has:
- JSON schema for parameters
- Handler function for execution
- User-friendly result formatting

Key class: `ToolHandler`
- `register()`: Register a handler for a built-in tool
- `register_tool()`: Register a complete tool with definition and handler (used by plugins)
- `execute()`: Dispatch tool calls to handlers
- `get_all_tools()`: Get all tool definitions (built-in + plugin)
- `get_plugin_tools()`: Get only plugin-registered tools

### Safety Layer (`safety/`)

#### `guardrails.py`
Command filtering and risk assessment:

```python
Risk Levels:
- SAFE: No restrictions
- MODERATE: Flagged, explained to user
- DANGEROUS: Requires explicit confirmation
- FORBIDDEN: Always blocked
```

Pattern categories:
- `FORBIDDEN_PATTERNS`: Never allowed (rm -rf /, mkfs, etc.)
- `DANGEROUS_PATTERNS`: Require confirmation
- `MODERATE_PATTERNS`: Informational warning
- `CRITICAL_PACKAGES`: Protected from removal

Key class: `SafetyGuard`
- `check_command()`: Assess command risk level
- `check_file_write()`: Assess file write risk
- `check_package_operation()`: Assess package operation risk

#### `audit.py`
Comprehensive action logging:
- Command execution records
- File operation tracking
- User confirmations
- Error logging

Key class: `AuditLogger`
- `log()`: General action logging
- `log_command()`: Record command execution
- `log_file_write()`: Record file changes
- `log_user_query()`: Record user inputs
- `log_package_operation()`: Record package operations

### Execution Layer (`executor/`)

#### `sandbox.py`
Safe command execution environment:
- Process isolation (separate process group)
- Timeout enforcement
- Output capture and size limits
- Environment sanitization

Key class: `CommandExecutor`
- `execute()`: Run command with safety constraints
- `check_command_exists()`: Verify command availability

Configuration:
- `DEFAULT_TIMEOUT`: 30 seconds
- `MAX_TIMEOUT`: 300 seconds
- `MAX_OUTPUT_SIZE`: 10MB

#### `files.py`
Safe file operations:
- Path validation and sandboxing
- Automatic backup creation
- Size limit enforcement
- Binary file detection

Key class: `FileHandler`
- `read_file()`: Safe file reading with limits
- `write_file()`: Write with backup
- `search_files()`: Find files with result limits
- `list_directory()`: List directory contents

### Context Layer (`context/`)

#### `system.py`
System state collection:
- Disk usage statistics
- Memory information
- CPU metrics
- Running processes
- Network interfaces

Key class: `SystemContextGatherer`
- `get_context()`: Comprehensive system overview
- `get_running_processes()`: Top processes by CPU

#### `session.py`
Conversation session management:
- Message history tracking
- Session persistence (JSON files)
- Session listing and resume
- Per-session preferences and context variables

Key classes:
- `SessionManager`: Full session lifecycle management
  - `start_session()`: Create new session
  - `save_session()`: Persist to disk
  - `load_session()`: Restore previous session
  - `list_sessions()`: Browse saved sessions
- `ConversationBuffer`: Claude API message format management
  - `add_user_message()`: Add user message
  - `add_assistant_message()`: Add assistant response
  - `add_tool_result()`: Add tool execution result

## Support Systems

### Plugin System (`plugins.py`)

Dynamic plugin loading and management:

```
Plugin Discovery:
1. Scan ~/.config/aios/plugins/
2. Scan /etc/aios/plugins/
3. Import Python files containing PluginBase subclasses
4. Call on_load() lifecycle hook
5. Register tools with ToolHandler
```

Key classes:
- `PluginBase`: Abstract base class for plugins
- `PluginManager`: Discovery, loading, lifecycle management
- `ToolDefinition`: Schema for plugin-provided tools
- `Recipe`: Multi-step workflow definition

Lifecycle hooks:
- `on_load()`: Plugin initialization
- `on_unload()`: Plugin cleanup
- `on_session_start()`: Session begin notification
- `on_session_end()`: Session end notification

See [PLUGINS.md](PLUGINS.md) for full documentation.

### Caching System (`cache.py`)

Multi-level caching for performance:

| Cache | Purpose | Default TTL |
|-------|---------|-------------|
| `LRUCache` | General-purpose cache | 300s |
| `SystemInfoCache` | System metrics | 15-120s by type |
| `QueryCache` | Informational Claude responses | 600s |

Features:
- Thread-safe LRU eviction
- Type-specific TTLs for system info (CPU: 15s, memory: 30s, disk: 60s)
- Intelligent query cacheability detection
- `@cached` decorator for function-level caching
- Cache statistics tracking (hits, misses, hit rate)

See [CACHING.md](CACHING.md) for full documentation.

### Rate Limiting (`ratelimit.py`)

API usage protection:

| Algorithm | Purpose |
|-----------|---------|
| `TokenBucket` | Smooth request rate limiting |
| `SlidingWindowCounter` | Fixed-window rate limits |
| `APIRateLimiter` | Combined limiter for API calls |

Configurable limits:
- Requests per minute (default: 50)
- Requests per hour (default: 500)
- Tokens per minute (default: 100,000)

See [RATELIMIT.md](RATELIMIT.md) for full documentation.

### Credential Management (`credentials.py`)

Encrypted credential storage:

```
Master Password → PBKDF2 (480K iterations) → AES Key → Fernet Encryption
```

Key classes:
- `CredentialStore`: Encrypted storage operations
- `Credential`: Single credential data model

Features:
- Fernet encryption (AES-128-CBC + HMAC-SHA256)
- PBKDF2-HMAC-SHA256 key derivation
- File permissions `0600`
- Global convenience functions

See [CREDENTIALS.md](CREDENTIALS.md) for full documentation.

### Error Handling (`errors.py`)

Structured error handling and recovery:

Key classes:
- `AIOSError`: Base exception with category, severity, and recovery suggestions
- `APIError`: Claude API-specific errors
- `ErrorBoundary`: Context manager for catching and handling errors
- `ErrorRecovery`: Retry logic with configurable attempts

Error categories: `SYSTEM`, `API`, `CONFIGURATION`, `FILE`, `PERMISSION`, `NETWORK`

### Configuration (`config.py`)

Hierarchical configuration system using Pydantic:

```
Priority (highest to lowest):
1. Environment variables (ANTHROPIC_API_KEY, AIOS_*)
2. User config (~/.config/aios/config.toml)
3. System config (/etc/aios/config.toml)
4. Default config (bundled)
```

Sections:
- `api`: Model settings, token limits
- `safety`: Confirmation requirements, patterns
- `ui`: Colors, verbosity, display options
- `logging`: Audit log configuration
- `session`: History settings

### User Interface (`ui/`)

#### `terminal.py`
Rich terminal rendering:
- Colorized output with Markdown support
- Syntax-highlighted file content display
- Progress indicators (spinners)
- Formatted tables and trees
- System info display

Key class: `TerminalUI`
- `print_response()`: Display Claude's response as Markdown
- `print_file_content()`: Syntax-highlighted file display with language detection
- `print_error()`, `print_success()`, `print_warning()`, `print_info()`: Status messages
- `print_help()`: Full help display
- `print_system_info()`: Formatted system information table

#### `prompts.py`
User interaction handling:
- Confirmation dialogs
- Input collection
- Choice menus

Key class: `ConfirmationPrompt`
- `confirm()`: Yes/no prompts
- `confirm_dangerous_action()`: Enhanced confirmation with warnings
- `ask_clarification()`: Text input with optional choices

## Data Flow

### User Request Flow

```
1. User Input
   └─> shell.py: _handle_user_input()
       ├─> Check rate limit (_check_rate_limit())
       ├─> Check query cache (query_cache.get())
       └─> claude/client.py: send_message()
           └─> Anthropic API
               └─> Response with tool_use

2. Tool Execution
   └─> shell.py: _process_tool_calls()
       └─> tool_handler.execute()
           └─> safety/guardrails.py: check_command()
               └─> [FORBIDDEN] Block and explain
               └─> [DANGEROUS] Request confirmation
               └─> [SAFE/MODERATE] Proceed
           └─> executor/sandbox.py: execute()
               └─> Command output

3. Result Return
   └─> claude/client.py: send_tool_results()
       └─> Claude processes result
           └─> Final response to user
               └─> Cache response if informational
```

### Session Flow

```
Start AIOS
├─> Load plugins (_load_plugins())
├─> Initialize caches + rate limiter
├─> Start session (session.start_session())
├─> Notify plugins (on_session_start)
│
├── Conversation Loop ──┐
│   ├─> Process input   │
│   ├─> Add to session  │
│   └─> (repeat) ───────┘
│
├─> Notify plugins (on_session_end)
└─> Save session (session.end_session())
```

### Configuration Loading

```
1. Load default.toml (bundled)
2. Merge /etc/aios/config.toml (if exists)
3. Merge ~/.config/aios/config.toml (if exists)
4. Override with AIOS_* environment variables
5. Apply ANTHROPIC_API_KEY if set
```

## Extension Points

### Adding a New Tool (Built-in)

1. Define schema in `claude/tools.py` by adding to `BUILTIN_TOOLS`:
```python
BUILTIN_TOOLS.append({
    "name": "my_tool",
    "description": "What it does",
    "input_schema": {...}
})
```

2. Implement handler in `shell.py`:
```python
def _handle_my_tool(self, params: dict) -> ToolResult:
    # Implementation
    return ToolResult(success=True, output="...", user_friendly_message="...")
```

3. Register in `_register_tools()`:
```python
self.tool_handler.register("my_tool", self._handle_my_tool)
```

### Adding a Tool via Plugin

Create a plugin file in `~/.config/aios/plugins/`:
```python
from aios.plugins import PluginBase, ToolDefinition

class MyPlugin(PluginBase):
    def get_tools(self):
        return [ToolDefinition(
            name="my_tool",
            description="What it does",
            input_schema={...},
            handler=self._handle_my_tool
        )]
```

See [PLUGINS.md](PLUGINS.md) for full plugin development guide.

### Adding Safety Patterns

In `safety/guardrails.py`:
```python
DANGEROUS_PATTERNS.append(r"your-pattern-here")
```

### Custom Configuration

Add to config classes in `config.py`:
```python
class MySection(BaseModel):
    my_option: str = "default"

class AIOSConfig(BaseModel):
    my_section: MySection = MySection()
```

## Testing Strategy

### Unit Tests (268 tests)

| Test File | Module | Tests |
|-----------|--------|-------|
| `test_ansible_plugin.py` | Ansible plugin | 42 |
| `test_cache.py` | Caching system | 30 |
| `test_config.py` | Configuration | 15 |
| `test_errors.py` | Error handling | 43 |
| `test_files.py` | File operations | 32 |
| `test_plugins.py` | Plugin system | 28 |
| `test_ratelimit.py` | Rate limiting | 33 |
| `test_safety.py` | Safety guardrails | 22 |
| `test_session.py` | Session management | 18 |
| `test_sandbox.py` | Command execution | 5+ |

### CI/CD Pipeline

GitHub Actions runs on every push and PR:
- Multi-Python testing (3.10, 3.11, 3.12)
- Code coverage with Codecov
- Linting (Black, isort, flake8)
- Security scanning (Bandit, Safety)
- Docker build verification

See [CI.md](CI.md) for full CI/CD documentation.

### Manual Testing
```bash
# Run with verbose output
AIOS_UI_SHOW_TECHNICAL_DETAILS=true aios

# Test specific scenarios
aios "list files in /tmp"
aios "show disk usage"
```

## Performance Considerations

### Current Optimizations
- **LRU caching** for system info with type-specific TTLs
- **Query caching** for informational Claude responses
- **Rate limiting** prevents API overuse
- **Lazy loading** of system context
- **Output size limits** prevent memory bloat
- **Command timeouts** prevent hanging
- **pip dependency caching** in CI builds

### Future Improvements
- Parallel tool execution
- Incremental context updates
- Conversation summarization for long sessions
- Plugin-level caching support

## Security Model

### Trust Boundaries
1. **User Input**: Untrusted, validated before processing
2. **Claude Responses**: Semi-trusted, tool calls validated
3. **System Commands**: Executed in sandbox with restrictions
4. **File Access**: Limited to allowed paths
5. **Credentials**: Encrypted at rest, decrypted only in memory
6. **Plugin Code**: Trusted (user-installed), but tool calls confirmed if flagged

### Defense in Depth
1. Pattern matching (guardrails)
2. User confirmation (prompts)
3. Execution isolation (sandbox)
4. Audit logging (audit)
5. Credential encryption (credentials)
6. Rate limiting (ratelimit)

## Dependencies

| Package | Purpose |
|---------|---------|
| `anthropic` | Claude API client |
| `rich` | Terminal formatting |
| `prompt-toolkit` | Input handling |
| `toml` | Configuration parsing |
| `pydantic` | Data validation |
| `psutil` | System metrics |
| `cryptography` | Credential encryption |
