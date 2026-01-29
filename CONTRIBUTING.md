# Contributing to AIOS

Thank you for your interest in contributing to AIOS! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for everyone.

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/Majkee/AI_Operating_System/issues)
2. If not, create a new issue with:
   - Clear, descriptive title
   - Steps to reproduce
   - Expected vs actual behavior
   - System information (OS, Python version, AIOS version)
   - Relevant logs or error messages

### Suggesting Features

1. Check existing issues and discussions for similar ideas
2. Open a new issue with the `enhancement` label
3. Describe:
   - The problem you're trying to solve
   - Your proposed solution
   - Alternative approaches you've considered

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`pytest tests/`)
5. Commit with clear messages (`git commit -m 'Add amazing feature'`)
6. Push to your fork (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Git
- An Anthropic API key (for testing)

### Local Development

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/AI_Operating_System.git
cd AI_Operating_System

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"

# Set up your API key
export ANTHROPIC_API_KEY="your-key-here"

# Run AIOS
aios
```

### Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=aios --cov-report=html

# Run specific test file
pytest tests/test_safety.py -v
```

### Code Style

We follow these conventions:

- **Python Style**: PEP 8 with 100 character line limit
- **Type Hints**: Use type hints for all function signatures
- **Docstrings**: Google-style docstrings for public functions
- **Imports**: Group as stdlib, third-party, local; alphabetize within groups

Example:

```python
def process_command(
    command: str,
    timeout: int = 30,
    require_confirmation: bool = True
) -> CommandResult:
    """Process and execute a shell command safely.

    Args:
        command: The shell command to execute.
        timeout: Maximum execution time in seconds.
        require_confirmation: Whether to prompt user for dangerous commands.

    Returns:
        CommandResult containing output, errors, and execution metadata.

    Raises:
        CommandBlockedError: If command matches forbidden patterns.
        TimeoutError: If command exceeds timeout limit.
    """
    ...
```

### Project Structure

```
aios/
├── aios/                 # Main application code
│   ├── main.py          # CLI entry point
│   ├── shell.py         # Interactive shell loop
│   ├── config.py        # Configuration management
│   ├── claude/          # Claude API integration
│   ├── executor/        # Command execution
│   ├── context/         # System and session context
│   ├── safety/          # Security guardrails
│   └── ui/              # Terminal interface
├── config/              # Default configuration
├── tests/               # Test suite
├── Dockerfile           # Container definition
└── docker-compose.yml   # Container orchestration
```

### Adding New Tools

To add a new tool that Claude can use:

1. Define the tool schema in `aios/claude/tools.py`:

```python
{
    "name": "my_new_tool",
    "description": "What this tool does (be specific for Claude)",
    "input_schema": {
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "What this parameter is for"
            }
        },
        "required": ["param1"]
    }
}
```

2. Implement the handler in the appropriate executor module
3. Register the handler in the tool registry
4. Add tests for the new tool
5. Update documentation

### Commit Messages

Use clear, descriptive commit messages:

- `feat: Add new file search tool`
- `fix: Handle timeout in command execution`
- `docs: Update installation instructions`
- `test: Add tests for guardrails module`
- `refactor: Simplify session management`

## Areas for Contribution

### Good First Issues

Look for issues labeled `good first issue` - these are suitable for newcomers.

### Current Priorities

- Expanding test coverage
- Improving error messages
- Adding new safety patterns
- Documentation improvements
- Performance optimizations

### Feature Ideas

- Skill system for community tools
- Web-based interface
- Multi-language support
- Voice input integration
- Custom command aliases

## Questions?

- Open a [Discussion](https://github.com/Majkee/AI_Operating_System/discussions) for general questions
- Check existing issues for similar problems
- Review the README and documentation first

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
