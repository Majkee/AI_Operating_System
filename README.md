# AIOS - AI-powered Operating System Interface

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/tests-268%20passed-brightgreen.svg)](#testing)
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

## Quick Start

### Using Docker (Recommended)

```bash
# Clone and enter the directory
git clone https://github.com/Majkee/AI_Operating_System.git
cd AI_Operating_System

# Set up your API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Run AIOS
docker-compose up --build
```

### Using pip

```bash
# Clone and install
git clone https://github.com/Majkee/AI_Operating_System.git
cd AI_Operating_System
pip install -e .

# Configure
export ANTHROPIC_API_KEY="your-api-key"

# Run
aios
```

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

- System info cached with type-specific TTLs
- Informational query responses cached
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

### Beautiful Interface

- Rich, colorful terminal output with syntax highlighting
- File content display with language detection
- Progress indicators for long operations
- Clear, friendly error messages

### Flexible Configuration

Customize AIOS behavior via `~/.config/aios/config.toml`:

```toml
[api]
model = "claude-sonnet-4-20250514"    # Claude model to use

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

### Plugins & Tools

| Command | Description |
|---------|-------------|
| `plugins` / `/plugins` | List loaded plugins |
| `tools` / `/tools` | List all available tools |
| `recipes` / `/recipes` | List available recipes |
| `stats` / `/stats` | Show session statistics |

### Sessions & Credentials

| Command | Description |
|---------|-------------|
| `sessions` / `/sessions` | List previous sessions |
| `resume <id>` | Resume a previous session |
| `credentials` / `/credentials` | List stored credentials |

## Architecture

```
aios/
├── claude/        # AI integration (Claude API client, tool definitions)
├── executor/      # Safe command execution (sandboxing, file operations)
├── safety/        # Security (guardrails, audit logging)
├── context/       # State management (system info, session tracking)
├── ui/            # Interface (terminal rendering, user prompts)
├── cache.py       # LRU cache, system info cache, query cache
├── ratelimit.py   # Token bucket + sliding window rate limiting
├── plugins.py     # Plugin system (loading, tools, recipes)
├── credentials.py # Encrypted credential storage
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
| [CACHING.md](CACHING.md) | Caching system: LRU cache, system cache, query cache |
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
model = "claude-sonnet-4-20250514"     # Model to use
max_tokens = 4096               # Max response tokens

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
```

## Testing

AIOS has a comprehensive test suite with 268 tests covering all major systems.

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
| Caching | 30 |
| Configuration | 15 |
| Error Handling | 43 |
| File Operations | 32 |
| Plugin System | 28 |
| Rate Limiting | 33 |
| Safety Guardrails | 22 |
| Session Management | 18 |

CI runs automatically on every push and PR. See [CI.md](CI.md) for details.

## Docker Usage

### Basic Commands

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
