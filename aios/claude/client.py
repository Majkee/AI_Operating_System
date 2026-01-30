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
AssistantResponse = None  # Will be set on first access via __getattr__


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
# SYSTEM_PROMPT is now managed centrally by aios.prompts.PromptManager
# For dynamic prompt access, use: from aios.prompts import get_prompt_manager
# This constant is kept for backward compatibility but may be removed in future versions
SYSTEM_PROMPT = None  # Will be populated lazily on first access


def __getattr__(name):
    if name == "AssistantResponse":
        from ..providers.base import AssistantResponse
        return AssistantResponse
    if name == "SYSTEM_PROMPT":
        # Lazy load to avoid circular imports
        from ..prompts import get_prompt_manager
        return get_prompt_manager().build_prompt()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

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
