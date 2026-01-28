# AIOS - AI-powered Operating System Interface

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/aiosys.svg)](https://pypi.org/project/aiosys/)
[![Docker Hub](https://img.shields.io/docker/v/majkee/aios?label=docker%20hub)](https://hub.docker.com/r/majkee/aios)
[![Tests](https://img.shields.io/badge/tests-454%20passed-brightgreen.svg)](#testing)
[![Code style: PEP8](https://img.shields.io/badge/code%20style-pep8-green.svg)](https://www.python.org/dev/peps/pep-0008/)

**Talk to your Linux system in plain English.** AIOS is a natural language interface powered by Claude that makes Linux accessible to everyone -- no command line experience required.

```
You: Show me what's taking up space on my disk
AIOS: I found these large directories in your home folder:
      - Downloads: 12.4 GB (847 files)
      - .cache: 3.2 GB
      - Documents/Projects: 2.1 GB
      Would you like me to help clean up any of these?
```

## Why AIOS?

- **No Learning Curve**: Just describe what you want in plain English
- **Safe by Design**: Built-in guardrails prevent dangerous operations
- **Explains Everything**: Understand what's happening on your system
- **Extensible**: Plugin system for custom tools and workflows
- **Respects Privacy**: Runs locally, your conversations stay on your machine

## Installation

### One-liner (Linux / macOS)

```bash
curl -fsSL https://raw.githubusercontent.com/Majkee/AI_Operating_System/master/install.sh | bash
```

Creates a virtual environment at `~/.local/share/aios`, installs from PyPI, and symlinks `aios` into `~/.local/bin`.

### pip (PyPI)

```bash
pip install aiosys
aios --setup
```

### Docker

```bash
# Docker Hub
docker pull majkee/aios
docker run -it -e ANTHROPIC_API_KEY="your-key" majkee/aios

# — or — GitHub Container Registry
docker pull ghcr.io/majkee/ai_operating_system
docker run -it -e ANTHROPIC_API_KEY="your-key" ghcr.io/majkee/ai_operating_system
```

### From source

```bash
git clone https://github.com/Majkee/AI_Operating_System.git
cd AI_Operating_System
pip install -e .
export ANTHROPIC_API_KEY="your-api-key"
aios
```

### Uninstall

| Method | Command |
|--------|---------|
| pip | `pip uninstall aiosys` |
| One-liner | `rm -rf ~/.local/share/aios ~/.local/bin/aios` |
| Docker | `docker rmi majkee/aios` |
| Snap | `sudo snap remove aios` |

## What Can AIOS Do?

### File Management
```
"Find all my PDF files"
"Organize my Downloads folder by file type"
"Show me files I modified today"
"Display the contents of config.yaml"
```

### System Information
```
"How much disk space do I have?"
"What's using all my memory?"
"Show me running processes"
"Is my system up to date?"
```

### Software Management
```
"Install VS Code"
"What programs do I have installed?"
"Update all my software"
"Remove applications I don't use"
```

### Getting Help
```
"How do I connect to WiFi?"
"What's the command to extract a zip file?"
"Explain what this error means: [paste error]"
```

## Features

### Safety First

AIOS includes multiple protection layers:

- **Forbidden Operations**: Catastrophic commands are always blocked
- **Confirmation Prompts**: Risky operations require your approval
- **Automatic Backups**: Files are backed up before changes
- **Audit Logging**: All actions are recorded for review

### Plugin System

Extend AIOS with custom tools and workflows:

- Drop plugins into `~/.config/aios/plugins/`
- Plugins can register tools that Claude can use
- Define recipes for multi-step automated workflows
- Full lifecycle hooks for session-aware plugins

### Caching & Performance

Intelligent caching reduces redundant operations:

- Tool results cached at the execution layer with per-tool TTLs
- Automatic invalidation rules (e.g. `write_file` invalidates `read_file`)
- System info cached for Claude's prompt context
- LRU eviction with configurable limits

### Rate Limiting

Built-in API rate limiting protects your usage:

- Token bucket for smooth request pacing
- Sliding window for fixed-window limits
- Approaching-limit warnings

### Session Persistence

Continue where you left off:

- Sessions auto-saved on exit
- Browse previous sessions with `/sessions`
- Resume any session with `resume <id>`
- Conversation history restored on resume

### Credential Management

Secure storage for passwords and API keys:

- Encrypted with Fernet (AES-128-CBC)
- Master password with PBKDF2 key derivation
- Plugin integration for secure access

### Background Tasks

Run commands in the background and manage them interactively:

- **Background execution**: `run_command` accepts `background: true` — starts without timeout, runs until done
- **Ctrl+C to background**: during any streaming command, Ctrl+C offers to background the running process instead of killing it
- **Task browser**: press **Ctrl+B** or type `tasks` to open an interactive browser — view output, attach to live output, kill, terminate, or remove tasks
- **Toolbar indicators**: bottom toolbar shows running/finished task counts and Ctrl+B hint
- **Completion notifications**: finished tasks are announced before each prompt

### Claude Code Integration

Launch interactive Claude Code sessions directly from AIOS:

- **Interactive sessions**: type `code` to open a full Claude Code terminal — AIOS hands off stdin/stdout and blocks until you exit
- **Prompt passthrough**: `code build a REST API` launches Claude Code with an initial prompt
- **Session resume**: `code-continue <id>` resumes a previous coding session
- **Auth chooser**: on first use, pick between your API key or your paid Claude subscription
- **Auto-detection**: coding requests are automatically routed to Claude Code (configurable sensitivity)

### Sudo, Timeouts & Streaming

Built-in support for privileged and long-running operations:

- **Sudo integration**: `run_command` accepts `use_sudo` — automatically prefixes `sudo` and warns the user
- **Configurable timeouts**: Per-command `timeout` up to 3600s (1 hour) for large downloads and installs
- **Live streaming output**: `long_running` flag streams real-time progress in a compact live display
- **Smart guidance**: System prompt teaches Claude when to use sudo, how to set timeouts, and when to stream

### Streaming Responses

Real-time response streaming for a modern chat experience:

- **Word-by-word streaming**: Watch responses appear as Claude thinks
- **Smooth transitions**: Spinner → live Markdown rendering
- **Configurable**: Disable via `config` menu or config file
- **No latency penalty**: Same API, better UX

### Context Window Management

Automatic conversation history management prevents token limit crashes:

- **Token budget tracking**: Monitors context usage as percentage of budget
- **Automatic summarization**: When nearing limit, older messages are summarized
- **Summary preservation**: Key details from earlier conversation retained
- **Configurable budget**: Adjust `context_budget` for different needs
- **Graceful fallback**: Falls back to truncation if summarization fails

### Beautiful Interface

- Rich, colorful terminal output with syntax highlighting
- File content display with language detection
- Progress indicators and live streaming display for long operations
- Clear, friendly error messages

### Flexible Configuration

Customize AIOS behavior via `~/.config/aios/config.toml`:

```toml
[api]
model = "claude-sonnet-4-5-20250929"    # Claude model to use

[ui]
show_technical_details = false  # Show underlying commands
use_colors = true               # Colorful output

[safety]
require_confirmation = true     # Confirm risky operations
```

## Commands

### General

| Command | Description |
|---------|-------------|
| `exit` / `quit` | Leave AIOS |
| `help` | Show help information |
| `clear` | Clear the screen |
| `history` | Show session history |

### Configuration

| Command | Description |
|---------|-------------|
| `config` / `/config` | Interactive settings menu |
| `model` / `/model` | List available AI models |
| `model <id>` | Switch to a different model |

### Plugins & Tools

| Command | Description |
|---------|-------------|
| `plugins` / `/plugins` | List loaded plugins |
| `tools` / `/tools` | List all available tools |
| `recipes` / `/recipes` | List available recipes |
| `stats` / `/stats` | Show session statistics |

### Background Tasks

| Command | Description |
|---------|-------------|
| `tasks` / `/tasks` | View and manage background tasks |
| **Ctrl+B** | Open task browser (from anywhere) |

### Sessions & Credentials

| Command | Description |
|---------|-------------|
| `sessions` / `/sessions` | List previous sessions |
| `resume <id>` | Resume a previous session |
| `credentials` / `/credentials` | List stored credentials |

### Claude Code

| Command | Description |
|---------|-------------|
| `code` | Launch interactive Claude Code session |
| `code <task>` | Launch Claude Code with an initial prompt |
| `code-continue <id>` | Resume a previous code session |
| `code-sessions` | List previous code sessions |

## Architecture

```
aios/
├── claude/        # AI integration (Claude API client, tool definitions)
├── code/          # Claude Code integration (interactive runner, detector)
├── executor/      # Safe command execution (sandboxing, file operations)
├── safety/        # Security (guardrails, audit logging)
├── context/       # State management (system info, session tracking)
├── tasks/         # Background task management (models, manager, browser)
├── ui/            # Interface (terminal rendering, user prompts, completions)
├── data/          # Bundled default configuration
├── cache.py       # LRU cache, system info cache, tool result cache
├── ratelimit.py   # Token bucket + sliding window rate limiting
├── plugins.py     # Plugin system (loading, tools, recipes)
├── credentials.py # Encrypted credential storage
├── models.py      # Available Claude model definitions
├── errors.py      # Error handling and recovery
├── config.py      # Configuration management
├── shell.py       # Main interactive shell
└── main.py        # CLI entry point
```

## Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Internal architecture and component design |
| [PLUGINS.md](PLUGINS.md) | Plugin system: creating tools, recipes, lifecycle hooks |
| [CACHING.md](CACHING.md) | Caching system: LRU cache, system cache, tool result cache |
| [RATELIMIT.md](RATELIMIT.md) | Rate limiting: token bucket, sliding window, configuration |
| [SESSIONS.md](SESSIONS.md) | Session management: persistence, resume, history |
| [CREDENTIALS.md](CREDENTIALS.md) | Credential management: encryption, storage, plugin usage |
| [CI.md](CI.md) | CI/CD pipeline: tests, linting, security scans, Docker |
| [SECURITY.md](SECURITY.md) | Security policy: reporting, features, limitations |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines: setup, code style, testing |
| [CHANGELOG.md](CHANGELOG.md) | Version history and release notes |

### Plugin Documentation

| Document | Description |
|----------|-------------|
| [plugins/README.md](plugins/README.md) | Plugin directory overview and quick start |
| [plugins/ANSIBLE_NETWORK.md](plugins/ANSIBLE_NETWORK.md) | Ansible Network plugin reference |

## Requirements

- **OS**: Debian-based Linux (Ubuntu, Debian, Linux Mint, etc.)
- **Python**: 3.10 or higher
- **API Key**: [Anthropic API key](https://console.anthropic.com/)

## Configuration

Configuration is loaded from (in order of priority):

1. Environment variables (`ANTHROPIC_API_KEY`, `AIOS_*`)
2. User config: `~/.config/aios/config.toml`
3. System config: `/etc/aios/config.toml`
4. Default config (bundled)

### Full Configuration Reference

```toml
[api]
api_key = ""                    # Anthropic API key (prefer env var)
model = "claude-sonnet-4-5-20250929"     # Model to use
max_tokens = 4096               # Max response tokens
streaming = true                # Stream responses word-by-word
context_budget = 150000         # Max tokens for conversation history
summarize_threshold = 0.75      # Summarize at 75% of context budget (0.5-0.95)
min_recent_messages = 6         # Keep this many recent messages verbatim (2-20)

[safety]
require_confirmation = true     # Confirm dangerous actions
# blocked_patterns = [...]      # Custom patterns to block
# dangerous_patterns = [...]    # Custom patterns requiring confirmation

[ui]
show_technical_details = false  # Show commands being run
use_colors = true               # Use colored output
show_commands = true            # Show what's being executed

[logging]
enabled = true                  # Enable audit logging
path = "/var/log/aios/audit.log"
level = "info"

[session]
save_history = true             # Save conversation history
max_history = 1000              # Maximum history entries

[executor]
default_timeout = 30            # Default command timeout (seconds)
max_timeout = 3600              # Maximum allowed timeout (1 hour)

[code]
enabled = true                  # Enable Claude Code integration
auto_detect = true              # Auto-detect coding requests
auto_detect_sensitivity = "moderate"  # high, moderate, low
# auth_mode = "api_key"         # or "subscription" (prompt on first use if unset)
```

## Testing

AIOS has a comprehensive test suite with 454 tests covering all major systems.

```bash
# Install test dependencies
pip install pytest pytest-cov pytest-asyncio

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=aios --cov-report=term-missing

# Run specific test modules
pytest tests/test_cache.py -v
pytest tests/test_plugins.py -v
pytest tests/test_ratelimit.py -v
```

### Test Coverage

| Module | Tests |
|--------|-------|
| Ansible Plugin | 42 |
| Caching | 35 |
| Claude Code Integration | 42 |
| Configuration | 15 |
| Error Handling | 43 |
| File Operations | 32 |
| Plugin System | 28 |
| Rate Limiting | 33 |
| Safety Guardrails | 22 |
| Sandbox / Executor | 20 |
| Session Management | 18 |
| Sudo / Timeout / Streaming | 18 |
| Background Tasks | 33 |
| Tab Completions | 27 |
| Streaming | 16 |
| Context Window | 30 |

CI runs automatically on every push and PR. See [CI.md](CI.md) for details.

## Docker Usage

### Pull from registries

```bash
# Docker Hub
docker pull majkee/aios
docker run -it -e ANTHROPIC_API_KEY="your-key" majkee/aios

# GitHub Container Registry
docker pull ghcr.io/majkee/ai_operating_system
docker run -it -e ANTHROPIC_API_KEY="your-key" ghcr.io/majkee/ai_operating_system
```

### Build locally / docker-compose

```bash
# Start AIOS
docker-compose up --build

# Run in background
docker-compose up -d --build

# Connect to running instance
docker-compose exec aios aios

# Stop AIOS
docker-compose down

# View logs
docker-compose logs -f
```

### Volumes

- `aios-config`: Persists your configuration
- `./workspace`: Host directory mounted at `/workspace` for file operations

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Quick Start for Contributors

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/AI_Operating_System.git
cd AI_Operating_System

# Set up development environment
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Check formatting
black --check aios/
isort --check-only aios/
```

## Security

AIOS takes security seriously. See [SECURITY.md](SECURITY.md) for:

- How to report vulnerabilities
- Security features and limitations
- Best practices for safe usage

## Roadmap

- [x] Plugin system for community tools
- [x] Caching for improved performance
- [x] Rate limiting for API protection
- [x] Session persistence and resume
- [x] Credential management
- [x] CI/CD pipeline
- [x] Sudo support, configurable timeouts, and live streaming output
- [x] Background tasks with interactive browser and Ctrl+C-to-background
- [x] PyPI package, install script, Docker Hub, and Snap distribution
- [x] Claude Code interactive integration with auth chooser
- [x] Streaming responses with real-time Markdown rendering
- [x] Interactive configuration menu
- [x] Context window management with automatic summarization
- [ ] Web-based interface option
- [ ] Multi-language support
- [ ] Voice input integration
- [ ] Custom command aliases
- [ ] Improved offline capabilities

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- Powered by [Claude](https://anthropic.com) from Anthropic
- Terminal UI by [Rich](https://github.com/Textualize/rich)
- Input handling by [prompt-toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit)
- Encryption by [cryptography](https://github.com/pyca/cryptography)

---

**Made with care for humans who just want their computer to work.**
