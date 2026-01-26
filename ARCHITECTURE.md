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
├─────────────────────────────────────────────────────────────┤
│                      Context Layer                           │
│              (context/system.py, session.py)                 │
├─────────────────────────────────────────────────────────────┤
│                    Configuration                             │
│                      (config.py)                             │
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
- Handles user input and output
- Maintains session state

Key class: `AIOSShell`
- `run()`: Main interaction loop
- `process_message()`: Send message to Claude and handle response
- `execute_tool()`: Dispatch tool calls to appropriate handlers

### Claude Integration (`claude/`)

#### `client.py`
Manages communication with the Anthropic API:
- Message formatting with system context
- Streaming response handling
- Tool result submission
- Error handling and retries

Key class: `ClaudeClient`
- `send_message()`: Send user message with conversation history
- `submit_tool_result()`: Return tool execution results to Claude

#### `tools.py`
Defines the tools available to Claude:

| Tool | Purpose |
|------|---------|
| `run_command` | Execute shell commands |
| `read_file` | Read file contents |
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

Key class: `Guardrails`
- `check_command()`: Assess command risk level
- `is_safe()`: Quick safety check
- `get_explanation()`: User-friendly risk explanation

#### `audit.py`
Comprehensive action logging:
- Command execution records
- File operation tracking
- User confirmations
- Error logging

Key class: `AuditLogger`
- `log_command()`: Record command execution
- `log_file_operation()`: Record file changes
- `get_recent_entries()`: Retrieve audit history

### Execution Layer (`executor/`)

#### `sandbox.py`
Safe command execution environment:
- Process isolation (separate process group)
- Timeout enforcement
- Output capture and size limits
- Environment sanitization

Key class: `Sandbox`
- `execute()`: Run command with safety constraints
- `execute_with_sudo()`: Elevated execution with confirmation

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

Key class: `FileOperations`
- `read_file()`: Safe file reading with limits
- `write_file()`: Write with backup
- `search_files()`: Find files with result limits

Configuration:
- `MAX_FILE_SIZE`: 10MB for reads
- `MAX_SEARCH_RESULTS`: 100 files
- `BACKUP_DIR`: `.aios_backups/`

### Context Layer (`context/`)

#### `system.py`
System state collection:
- Disk usage statistics
- Memory information
- CPU metrics
- Running processes
- Network interfaces

Key class: `SystemContext`
- `get_summary()`: Comprehensive system overview
- `get_disk_info()`: Storage details
- `get_memory_info()`: RAM usage

#### `session.py`
Conversation session management:
- Message history tracking
- Session persistence (JSON)
- Statistics collection
- Action summaries

Key class: `Session`
- `add_message()`: Append to conversation
- `save()`: Persist to disk
- `load()`: Restore previous session
- `get_summary()`: Session statistics

### Configuration (`config.py`)

Hierarchical configuration system using Pydantic:

```
Priority (highest to lowest):
1. Environment variables (ANTHROPIC_API_KEY, AIOS_*)
2. User config (~/.config/aios/config.toml)
3. System config (/etc/aios/config.toml)
4. Default config (bundled)
```

Key class: `Config`
Sections:
- `api`: Model settings, token limits
- `safety`: Confirmation requirements, patterns
- `ui`: Colors, verbosity, display options
- `logging`: Audit log configuration
- `session`: History settings

### User Interface (`ui/`)

#### `terminal.py`
Rich terminal rendering:
- Colorized output
- Progress indicators
- Formatted tables
- Error display

Key class: `Terminal`
- `print_response()`: Display Claude's response
- `print_error()`: Formatted error messages
- `show_progress()`: Spinner/progress bar

#### `prompts.py`
User interaction handling:
- Confirmation dialogs
- Input collection
- Choice menus

Key functions:
- `confirm()`: Yes/no prompts
- `prompt()`: Text input
- `choose()`: Multiple choice

## Data Flow

### User Request Flow

```
1. User Input
   └─> shell.py: process_message()
       └─> claude/client.py: send_message()
           └─> Anthropic API
               └─> Response with tool_use

2. Tool Execution
   └─> shell.py: execute_tool()
       └─> safety/guardrails.py: check_command()
           └─> [FORBIDDEN] Block and explain
           └─> [DANGEROUS] Request confirmation
           └─> [SAFE/MODERATE] Proceed
       └─> executor/sandbox.py: execute()
           └─> Command output

3. Result Return
   └─> claude/client.py: submit_tool_result()
       └─> Claude processes result
           └─> Final response to user
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

### Adding a New Tool

1. Define schema in `claude/tools.py`:
```python
TOOLS.append({
    "name": "my_tool",
    "description": "What it does",
    "input_schema": {...}
})
```

2. Implement handler:
```python
def handle_my_tool(params: dict) -> ToolResult:
    # Implementation
    return ToolResult(success=True, output="...", message="...")
```

3. Register in tool dispatcher (shell.py)

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

class Config(BaseModel):
    my_section: MySection = MySection()
```

## Testing Strategy

### Unit Tests
- `tests/test_safety.py`: Guardrail pattern matching
- Future: Individual component tests

### Integration Tests
- Tool execution with mocked Claude
- End-to-end conversation flows

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
- Lazy loading of system context
- Output size limits prevent memory bloat
- Command timeouts prevent hanging

### Future Improvements
- Response caching for repeated queries
- Parallel tool execution
- Incremental context updates
- Conversation summarization for long sessions

## Security Model

### Trust Boundaries
1. **User Input**: Untrusted, validated before processing
2. **Claude Responses**: Semi-trusted, tool calls validated
3. **System Commands**: Executed in sandbox with restrictions
4. **File Access**: Limited to allowed paths

### Defense in Depth
1. Pattern matching (guardrails)
2. User confirmation (prompts)
3. Execution isolation (sandbox)
4. Audit logging (audit)

## Dependencies

| Package | Purpose |
|---------|---------|
| `anthropic` | Claude API client |
| `rich` | Terminal formatting |
| `prompt-toolkit` | Input handling |
| `toml` | Configuration parsing |
| `pydantic` | Data validation |
| `psutil` | System metrics |
