"""
Claude API client for AIOS.

DEPRECATED: This module is maintained for backward compatibility.
Use `aios.providers.create_client()` or `aios.providers.AnthropicClient` instead.

The ClaudeClient class is now an alias for AnthropicClient from the providers package.
"""

import warnings
import logging
from typing import Any, Callable, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

from .tools import ToolHandler

if TYPE_CHECKING:
    from ..providers.anthropic_client import AnthropicClient as _AnthropicClient

logger = logging.getLogger(__name__)


@dataclass
class ConversationMessage:
    """A message in the conversation.

    DEPRECATED: This class is maintained for backward compatibility.
    """
    role: str  # "user" or "assistant"
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)


def _get_anthropic_client():
    """Lazy import to avoid circular dependencies."""
    from ..providers.anthropic_client import AnthropicClient
    return AnthropicClient


# Re-export AssistantResponse
def _get_assistant_response():
    """Lazy import to avoid circular dependencies."""
    from ..providers.base import AssistantResponse
    return AssistantResponse


# Make AssistantResponse available at module level
AssistantResponse = None  # Will be set on first access


def __getattr__(name):
    if name == "AssistantResponse":
        from ..providers.base import AssistantResponse
        return AssistantResponse
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class ClaudeClient:
    """Client for interacting with Claude API.

    DEPRECATED: Use `aios.providers.create_client()` or
    `aios.providers.AnthropicClient` instead.

    This class is maintained for backward compatibility and wraps
    AnthropicClient from the providers package.
    """

    def __init__(self, tool_handler: Optional[ToolHandler] = None):
        """Initialize the Claude client."""
        warnings.warn(
            "ClaudeClient is deprecated. Use create_client() from aios.providers "
            "or AnthropicClient directly.",
            DeprecationWarning,
            stacklevel=2
        )
        AnthropicClient = _get_anthropic_client()
        self._client = AnthropicClient(tool_handler)

    def __getattr__(self, name):
        """Delegate attribute access to the wrapped client."""
        return getattr(self._client, name)

    @property
    def model(self) -> str:
        """Get the current model (for backward compatibility)."""
        return self._client.get_model()

    @model.setter
    def model(self, value: str) -> None:
        """Set the model (for backward compatibility)."""
        self._client.set_model(value)

    @property
    def conversation_history(self) -> list:
        """Get conversation history (for backward compatibility)."""
        return self._client.conversation_history

    @conversation_history.setter
    def conversation_history(self, value: list) -> None:
        """Set conversation history (for backward compatibility)."""
        self._client.conversation_history = value

    def send_message(self, *args, **kwargs):
        """Send a message to Claude."""
        return self._client.send_message(*args, **kwargs)

    def send_tool_results(self, *args, **kwargs):
        """Send tool results to Claude."""
        return self._client.send_tool_results(*args, **kwargs)

    def clear_history(self):
        """Clear conversation history."""
        return self._client.clear_history()

    def get_history_summary(self):
        """Get history summary."""
        return self._client.get_history_summary()

    def get_context_stats(self):
        """Get context stats."""
        return self._client.get_context_stats()

    def get_circuit_breaker_stats(self):
        """Get circuit breaker stats."""
        return self._client.get_circuit_breaker_stats()

    def reset_circuit_breaker(self):
        """Reset circuit breaker."""
        return self._client.reset_circuit_breaker()


# Legacy exports for backward compatibility
# These are now available from the providers package
SYSTEM_PROMPT = """You are AIOS, a friendly AI assistant that helps users interact with their Debian Linux computer through natural conversation.

## Your Role
- You help non-technical users accomplish tasks on their computer
- You translate their requests into appropriate system actions
- You explain what you're doing in simple, friendly language
- You protect users from accidentally harmful actions

## Guidelines

### Communication Style
- Use simple, non-technical language
- Avoid jargon - if you must use a technical term, explain it
- Be encouraging and patient
- Provide helpful context about what you're doing

### Safety First
- Always explain what an action will do before executing it
- For any action that modifies files or system settings, get confirmation
- Never execute potentially destructive commands without explicit confirmation
- If something could go wrong, warn the user first

### When Using Tools
- Always provide clear explanations of what each tool does
- Group related actions together when possible
- If a request is ambiguous, ask for clarification
- Present file listings and search results in a user-friendly format

### Error Handling
- If something fails, explain what went wrong in simple terms
- Suggest alternatives or solutions when possible
- Never blame the user for errors

### Respecting User Decisions
- CRITICAL: When a tool result contains "USER DECLINED", the user explicitly refused the action
- Do NOT retry the same operation through alternative tools or methods
- Simply acknowledge their decision and ask if they need help with something else
- User refusal is final - respect it completely

### Privacy & Security
- Don't read files unless necessary for the user's request
- Don't expose sensitive information (passwords, keys) in output
- Respect user privacy - only access what's needed

## Context
You have access to the user's home directory and can help with:
- Finding and organizing files
- Installing and managing applications
- Viewing system information
- Creating and editing documents
- Basic system maintenance

Remember: Your goal is to make Linux accessible and friendly for everyone!

## Sudo and Elevated Privileges
This system runs as a non-root user with passwordless sudo.
- System commands (apt-get, dpkg, systemctl, service) REQUIRE `use_sudo: true` in run_command
- User-space commands (ls, cat, wget to home dirs, find) do NOT need sudo
- The manage_application tool handles sudo automatically; run_command does not

## Timeouts and Long-Running Operations
- Default timeout: 30 seconds (quick operations)
- Set `timeout` explicitly for longer work:
  - Package install: 300-600
  - Large downloads (>100 MB): 1800-3600
  - Game server installs: 3600
  - Compilation: 1800-3600
- Maximum: 3600 seconds (1 hour)
- Set `long_running: true` alongside high timeouts to stream live output
- If a command times out, inform the user and suggest retrying with higher timeout

## Handling Large Installations
1. Install prerequisites with sudo (use_sudo: true, timeout: 300)
2. Download large files with extended timeout (timeout: 3600, long_running: true)
3. Warn user that large operations may take several minutes

## Background Tasks
- Set `background: true` in run_command for tasks the user does not need to watch
- Background tasks have no timeout and run until completion
- The user can view background tasks with Ctrl+B or the 'tasks' command
- Use background for: server processes, very large downloads, unattended builds
- Prefer foreground (long_running: true) when the user wants to see progress

## Claude Code Integration
- When the user asks you to write code, build applications, or do complex coding work, suggest the 'code' command
- Typing 'code' launches an interactive Claude Code session where the user works directly with the coding agent
- Example: "For this task, I recommend launching Claude Code: just type 'code' or 'code build a Flask REST API'"
- Claude Code is a specialized coding agent that can read, write, edit files, run commands, and search code
- Simple code questions or small snippets can be answered directly without Claude Code"""

# Context window management constants (for backward compatibility)
DEFAULT_CONTEXT_BUDGET = 150_000
SUMMARIZE_THRESHOLD = 0.75
MIN_RECENT_MESSAGES = 6
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length.

    DEPRECATED: Import from aios.providers.anthropic_client instead.
    """
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_message_tokens(message: dict) -> int:
    """Estimate tokens in a conversation message.

    DEPRECATED: This function is maintained for backward compatibility.
    """
    import json
    content = message.get("content", "")

    if isinstance(content, str):
        return estimate_tokens(content)

    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    total += estimate_tokens(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    total += estimate_tokens(block.get("name", ""))
                    total += estimate_tokens(json.dumps(block.get("input", {})))
                elif block.get("type") == "tool_result":
                    total += estimate_tokens(str(block.get("content", "")))
        return max(1, total)

    return 1


def estimate_history_tokens(messages: list) -> int:
    """Estimate total tokens in conversation history.

    DEPRECATED: This function is maintained for backward compatibility.
    """
    return sum(estimate_message_tokens(msg) for msg in messages)
