# AIOS - AI-powered Operating System Interface

AIOS is a natural language interface for Linux that lets you interact with your computer through conversation. Powered by Claude, it translates your requests into system actions, making Linux accessible to everyone.

## Features

- **Natural Language Interface**: Just tell AIOS what you want to do
- **File Management**: Find, organize, create, and edit files through conversation
- **System Information**: Check disk space, memory, running processes
- **Application Management**: Install, remove, and update software
- **Safety First**: Built-in guardrails prevent dangerous operations
- **Non-Technical Friendly**: Designed for users who aren't Linux experts

## Installation

### Prerequisites

- Debian-based Linux (Ubuntu, Debian, Linux Mint, etc.)
- Python 3.10 or higher
- An Anthropic API key

### Quick Install

```bash
# Clone the repository
git clone https://github.com/your-org/aios.git
cd aios

# Install dependencies
pip install -e .

# Run setup wizard
aios --setup
```

### Manual Configuration

Create `~/.config/aios/config.toml`:

```toml
[api]
api_key = "your-anthropic-api-key"

[ui]
show_technical_details = false
use_colors = true
```

Or set the environment variable:

```bash
export ANTHROPIC_API_KEY="your-api-key"
```

## Usage

### Interactive Mode

```bash
aios
```

Then just talk naturally:

```
You: Show me what's in my Documents folder
AIOS: I found 15 items in your Documents folder...

You: Find all my photos
AIOS: I found 3 folders with photos...

You: How much disk space do I have?
AIOS: You have 45.2 GB free of 256 GB (82% available)

You: Install a program to edit images
AIOS: I recommend GIMP for image editing. Would you like me to install it?
```

### Single Command Mode

```bash
aios "check my disk space"
```

### Commands

- `exit` / `quit` - Leave AIOS
- `help` - Show help
- `clear` - Clear screen
- `history` - Show session history

## Safety Features

AIOS includes multiple safety layers:

1. **Blocked Commands**: Dangerous system commands are never executed
2. **Confirmations**: Risky operations require explicit approval
3. **Backups**: File modifications create automatic backups
4. **Audit Logging**: All actions are logged for review

## Configuration

Configuration files are loaded in this order (later overrides earlier):

1. `/etc/aios/config.toml` (system-wide)
2. `~/.config/aios/config.toml` (user)
3. Environment variables (`AIOS_*`)

### Configuration Options

```toml
[api]
api_key = ""                    # Anthropic API key
model = "claude-sonnet-4-20250514"     # Model to use
max_tokens = 4096               # Max response tokens

[safety]
require_confirmation = true     # Confirm dangerous actions
blocked_patterns = [...]        # Regex patterns to block
dangerous_patterns = [...]      # Patterns requiring confirmation

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

## Development

### Project Structure

```
aios/
├── aios/
│   ├── __init__.py
│   ├── main.py           # Entry point
│   ├── shell.py          # Main interactive loop
│   ├── config.py         # Configuration management
│   ├── claude/           # Claude API integration
│   │   ├── client.py     # API client
│   │   └── tools.py      # Tool definitions
│   ├── executor/         # Command execution
│   │   ├── sandbox.py    # Sandboxed execution
│   │   └── files.py      # File operations
│   ├── context/          # Context management
│   │   ├── system.py     # System state
│   │   └── session.py    # Session management
│   ├── safety/           # Safety features
│   │   ├── guardrails.py # Command filtering
│   │   └── audit.py      # Audit logging
│   └── ui/               # User interface
│       ├── terminal.py   # Rich terminal output
│       └── prompts.py    # User prompts
├── config/
│   └── default.toml      # Default configuration
├── tests/
├── setup.py
└── requirements.txt
```

### Running Tests

```bash
pytest tests/
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- Powered by [Claude](https://anthropic.com) from Anthropic
- Built with [Rich](https://github.com/Textualize/rich) for beautiful terminal output
- Uses [prompt-toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) for input handling
