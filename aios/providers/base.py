"""
Base client interface for LLM providers.

Defines the abstract base class that all provider clients must implement,
ensuring consistent behavior across Anthropic, OpenAI, and LM Studio.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class AssistantResponse:
    """Unified response format for all providers."""
    text: str
    tool_calls: list[dict[str, Any]]  # [{id, name, input}, ...]
    is_complete: bool
    requires_action: bool = False
    pending_confirmations: list[dict] = field(default_factory=list)


class BaseClient(ABC):
    """Abstract base class for LLM provider clients.

    All provider implementations must inherit from this class and
    implement the required methods for sending messages, handling
    tool results, and managing conversation history.
    """

    @abstractmethod
    def send_message(
        self,
        user_input: str,
        system_context: Optional[str] = None,
        on_text: Optional[Callable[[str], None]] = None
    ) -> AssistantResponse:
        """Send a message to the LLM and get a response.

        Args:
            user_input: The user's message
            system_context: Optional system context to append to prompt
            on_text: Optional callback for streaming text deltas

        Returns:
            AssistantResponse with text and any tool calls
        """
        ...

    @abstractmethod
    def send_tool_results(
        self,
        tool_results: list[dict[str, Any]],
        system_context: Optional[str] = None,
        on_text: Optional[Callable[[str], None]] = None
    ) -> AssistantResponse:
        """Send tool execution results back to the LLM.

        Args:
            tool_results: List of tool execution results
            system_context: Optional system context to append to prompt
            on_text: Optional callback for streaming text deltas

        Returns:
            AssistantResponse with text and any tool calls
        """
        ...

    @abstractmethod
    def clear_history(self) -> None:
        """Clear the conversation history."""
        ...

    @abstractmethod
    def get_model(self) -> str:
        """Get the current model ID."""
        ...

    @abstractmethod
    def set_model(self, model: str) -> None:
        """Set the model to use.

        Args:
            model: The model ID to use
        """
        ...

    def get_history_summary(self) -> str:
        """Get a summary of the conversation history.

        Default implementation returns a simple message.
        Providers can override for more detailed summaries.
        """
        return "Conversation history tracking varies by provider."

    def get_context_stats(self) -> dict[str, Any]:
        """Get detailed context window statistics.

        Default implementation returns empty stats.
        Providers can override for detailed metrics.
        """
        return {}

    def get_circuit_breaker_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics for monitoring.

        Default implementation returns empty stats.
        Providers can override if they use circuit breakers.
        """
        return {}

    def reset_circuit_breaker(self) -> None:
        """Reset the circuit breaker to closed state.

        Default implementation is a no-op.
        Providers can override if they use circuit breakers.
        """
        pass
