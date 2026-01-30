"""
Reusable context window management with summarization.

Provides automatic conversation summarization when context windows
get too full. Can be used by any LLM provider client.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# Default configuration
DEFAULT_CONTEXT_BUDGET = 150000  # tokens
DEFAULT_SUMMARIZE_THRESHOLD = 0.75  # 75% of budget
DEFAULT_MIN_RECENT_MESSAGES = 6  # Keep at least this many recent messages


@dataclass
class ContextStats:
    """Statistics about context usage."""
    total_tokens: int = 0
    message_count: int = 0
    summarized_message_count: int = 0
    has_summary: bool = False
    budget_used_percentage: float = 0.0
    token_budget: int = DEFAULT_CONTEXT_BUDGET


@dataclass
class Message:
    """A conversation message."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {"role": self.role, "content": self.content, **self.metadata}


class TokenCounter(ABC):
    """Abstract interface for counting tokens."""

    @abstractmethod
    def count(self, text: str) -> int:
        """Count tokens in text."""
        pass


class SimpleTokenCounter(TokenCounter):
    """Simple token counter using character-based estimation.

    Uses ~4 characters per token as a rough estimate.
    This is conservative and works across different models.
    """

    def __init__(self, chars_per_token: float = 4.0):
        self.chars_per_token = chars_per_token

    def count(self, text: str) -> int:
        """Estimate token count from text length."""
        return int(len(text) / self.chars_per_token)


# Type for summarization function
SummarizeFn = Callable[[str], str]


class ContextManager:
    """Manages conversation context with automatic summarization.

    This class handles:
    - Tracking conversation history
    - Estimating token usage
    - Triggering summarization when needed
    - Maintaining recent messages while summarizing older ones

    Usage:
        # Create with a summarization function
        def my_summarize(text: str) -> str:
            return llm.summarize(text)

        manager = ContextManager(
            summarize_fn=my_summarize,
            context_budget=150000,
            summarize_threshold=0.75,
        )

        # Add messages
        manager.add_message("user", "Hello")
        manager.add_message("assistant", "Hi there!")

        # Check and summarize if needed
        manager.check_and_summarize()

        # Get messages for API call
        messages = manager.get_messages()
    """

    def __init__(
        self,
        summarize_fn: Optional[SummarizeFn] = None,
        context_budget: int = DEFAULT_CONTEXT_BUDGET,
        summarize_threshold: float = DEFAULT_SUMMARIZE_THRESHOLD,
        min_recent_messages: int = DEFAULT_MIN_RECENT_MESSAGES,
        token_counter: Optional[TokenCounter] = None,
    ):
        """Initialize the context manager.

        Args:
            summarize_fn: Function that takes conversation text and returns a summary.
                         If None, summarization is disabled.
            context_budget: Maximum tokens allowed in context.
            summarize_threshold: Trigger summarization at this percentage (0.0-1.0).
            min_recent_messages: Always keep at least this many recent messages.
            token_counter: Custom token counter. Defaults to SimpleTokenCounter.
        """
        self.summarize_fn = summarize_fn
        self.context_budget = context_budget
        self.summarize_threshold = summarize_threshold
        self.min_recent_messages = min_recent_messages
        self.token_counter = token_counter or SimpleTokenCounter()

        # Conversation state
        self._messages: list[Message] = []
        self._summary: Optional[str] = None
        self._summarized_message_count: int = 0
        self._total_tokens: int = 0

    def add_message(self, role: str, content: str, **metadata) -> None:
        """Add a message to the conversation.

        Args:
            role: Message role (user, assistant, system, tool)
            content: Message content
            **metadata: Additional metadata (tool_call_id, etc.)
        """
        message = Message(role=role, content=content, metadata=metadata)
        self._messages.append(message)
        self._update_token_count()

    def add_messages(self, messages: list[dict[str, Any]]) -> None:
        """Add multiple messages at once.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
        """
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            metadata = {k: v for k, v in msg.items() if k not in ("role", "content")}
            self.add_message(role, content, **metadata)

    def _update_token_count(self) -> None:
        """Update the total token count estimate."""
        total = 0
        if self._summary:
            total += self.token_counter.count(self._summary)
        for msg in self._messages:
            total += self.token_counter.count(msg.content)
            # Add some overhead for role and formatting
            total += 10
        self._total_tokens = total

    def get_token_usage(self) -> tuple[int, float]:
        """Get current token usage.

        Returns:
            Tuple of (total_tokens, percentage_of_budget)
        """
        percentage = self._total_tokens / self.context_budget if self.context_budget > 0 else 0
        return self._total_tokens, percentage

    def needs_summarization(self) -> bool:
        """Check if conversation needs summarization."""
        if self.summarize_fn is None:
            return False
        _, percentage = self.get_token_usage()
        return percentage >= self.summarize_threshold

    def _format_messages_for_summary(self, messages: list[Message]) -> str:
        """Format messages into readable text for summarization."""
        lines = []
        for msg in messages:
            role = msg.role.upper()
            content = msg.content

            # Handle tool results
            if msg.role == "tool":
                tool_id = msg.metadata.get("tool_call_id", "unknown")
                lines.append(f"TOOL RESULT ({tool_id}):\n{content}")
            else:
                lines.append(f"{role}:\n{content}")

        return "\n\n---\n\n".join(lines)

    def summarize(self) -> bool:
        """Summarize older messages to free up context space.

        Returns:
            True if summarization was performed, False otherwise.
        """
        if self.summarize_fn is None:
            logger.warning("Cannot summarize: no summarize_fn provided")
            return False

        # Keep recent messages
        messages_to_keep = min(self.min_recent_messages, len(self._messages))
        messages_to_summarize = self._messages[:-messages_to_keep] if messages_to_keep > 0 else self._messages

        if not messages_to_summarize:
            logger.debug("No messages to summarize")
            return False

        # Prepare content for summarization
        conversation_text = self._format_messages_for_summary(messages_to_summarize)

        # Include existing summary if present
        if self._summary:
            conversation_text = f"PREVIOUS SUMMARY:\n{self._summary}\n\n---\n\nNEW CONVERSATION:\n{conversation_text}"

        try:
            # Generate new summary
            new_summary = self.summarize_fn(conversation_text)

            # Update state
            self._summary = new_summary
            self._summarized_message_count += len(messages_to_summarize)

            # Keep only recent messages
            if messages_to_keep > 0:
                self._messages = self._messages[-messages_to_keep:]
            else:
                self._messages = []

            self._update_token_count()

            logger.info(
                f"Summarized {len(messages_to_summarize)} messages. "
                f"New context size: {self._total_tokens} tokens"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to summarize conversation: {e}")
            return False

    def check_and_summarize(self) -> bool:
        """Check if summarization is needed and perform it.

        Returns:
            True if summarization was performed, False otherwise.
        """
        if self.needs_summarization():
            logger.info("Context window threshold reached, summarizing history...")
            return self.summarize()
        return False

    def get_messages(self) -> list[dict[str, Any]]:
        """Get all messages including summary as system message.

        Returns:
            List of message dicts ready for API calls.
        """
        messages = []

        # Include summary as a system message if present
        if self._summary:
            messages.append({
                "role": "system",
                "content": f"[CONVERSATION SUMMARY]\n{self._summary}\n[END SUMMARY]"
            })

        # Add regular messages
        for msg in self._messages:
            messages.append(msg.to_dict())

        return messages

    def get_messages_for_anthropic(self) -> tuple[Optional[str], list[dict[str, Any]]]:
        """Get messages in Anthropic format (separate summary from messages).

        Returns:
            Tuple of (summary_text or None, list of messages)
        """
        messages = [msg.to_dict() for msg in self._messages]
        return self._summary, messages

    def clear(self) -> None:
        """Clear all conversation history and summary."""
        self._messages = []
        self._summary = None
        self._summarized_message_count = 0
        self._total_tokens = 0

    def get_stats(self) -> ContextStats:
        """Get context statistics."""
        tokens, percentage = self.get_token_usage()
        return ContextStats(
            total_tokens=tokens,
            message_count=len(self._messages),
            summarized_message_count=self._summarized_message_count,
            has_summary=self._summary is not None,
            budget_used_percentage=percentage,
            token_budget=self.context_budget,
        )

    def get_history_summary(self) -> str:
        """Get a human-readable summary of context state."""
        stats = self.get_stats()
        parts = [
            f"Messages: {stats.message_count}",
            f"Tokens: ~{stats.total_tokens:,} / {stats.token_budget:,} ({stats.budget_used_percentage:.1%})",
        ]

        if stats.summarized_message_count > 0:
            parts.append(f"Summarized: {stats.summarized_message_count} messages")

        if stats.has_summary:
            parts.append("Has conversation summary: Yes")

        return "\n".join(parts)

    @property
    def summary(self) -> Optional[str]:
        """Get the current conversation summary."""
        return self._summary

    @property
    def message_count(self) -> int:
        """Get the number of active messages."""
        return len(self._messages)

    @property
    def summarized_message_count(self) -> int:
        """Get the count of summarized messages."""
        return self._summarized_message_count


# Summarization prompt template
SUMMARIZATION_PROMPT = """Please provide a concise summary of the following conversation.
Focus on:
1. Key decisions made
2. Important information shared
3. Tasks completed or in progress
4. Any relevant context for continuing the conversation

Keep the summary factual and under 500 words.

CONVERSATION:
{conversation}

SUMMARY:"""


def create_summarization_prompt(conversation_text: str) -> str:
    """Create a summarization prompt from conversation text.

    Args:
        conversation_text: The formatted conversation to summarize.

    Returns:
        Complete prompt for summarization.
    """
    return SUMMARIZATION_PROMPT.format(conversation=conversation_text)
