"""
Anthropic Claude client for AIOS.

Handles communication with the Anthropic API and processes
tool calls from Claude's responses. Includes automatic context
window management with summarization to prevent token limit errors.
"""

import json
import logging
from typing import Any, Callable, Optional

import anthropic
from anthropic.types import Message, ToolUseBlock, TextBlock

from .base import BaseClient, AssistantResponse
from ..claude.tools import ToolHandler
from ..config import get_config
from ..errors import ErrorRecovery
from ..prompts import get_prompt_manager

logger = logging.getLogger(__name__)


# Context window management constants
DEFAULT_CONTEXT_BUDGET = 150_000  # tokens - leave room for response
SUMMARIZE_THRESHOLD = 0.75  # Trigger summarization at 75% of budget
MIN_RECENT_MESSAGES = 6  # Always keep at least this many recent messages
CHARS_PER_TOKEN = 4  # Rough estimate: 1 token ≈ 4 characters for English


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_message_tokens(message: dict) -> int:
    """Estimate tokens in a conversation message."""
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


def estimate_history_tokens(messages: list[dict]) -> int:
    """Estimate total tokens in conversation history."""
    return sum(estimate_message_tokens(msg) for msg in messages)


SUMMARIZATION_PROMPT = """Summarize the following conversation between a user and AIOS (an AI assistant for Linux).
Focus on:
1. Key actions taken (files created/modified, commands run, packages installed)
2. Important information shared (paths, configurations, decisions made)
3. Context needed for continuing the conversation

Be concise but preserve critical details. Format as a brief narrative summary.

CONVERSATION:
{conversation}

SUMMARY:"""


class AnthropicClient(BaseClient):
    """Client for interacting with Anthropic Claude API."""

    def __init__(self, tool_handler: Optional[ToolHandler] = None):
        """Initialize the Anthropic client."""
        config = get_config()

        if not config.api.api_key:
            raise ValueError(
                "No API key found. Please set AIOS_API_KEY or ANTHROPIC_API_KEY "
                "environment variable, or add api_key to your config file."
            )

        self.client = anthropic.Anthropic(api_key=config.api.api_key)
        self.model = config.api.model
        self.max_tokens = config.api.max_tokens
        self.tool_handler = tool_handler or ToolHandler()
        self.conversation_history: list[dict] = []

        # Context window management
        self.context_budget = getattr(config.api, 'context_budget', DEFAULT_CONTEXT_BUDGET)
        self.summarize_threshold = getattr(config.api, 'summarize_threshold', SUMMARIZE_THRESHOLD)
        self.min_recent_messages = getattr(config.api, 'min_recent_messages', MIN_RECENT_MESSAGES)
        self._conversation_summary: Optional[str] = None
        self._summarized_message_count: int = 0

        # Retry and circuit breaker configuration
        self._circuit_breaker = ErrorRecovery.get_circuit_breaker(
            name="anthropic_api",
            failure_threshold=5,
            recovery_timeout=60.0
        )
        self._retry_config = {
            "max_attempts": 3,
            "base_delay": 1.0,
            "max_delay": 30.0,
            "jitter": True,
        }
        self._retryable_exceptions = (
            anthropic.APIConnectionError,
            anthropic.RateLimitError,
            anthropic.InternalServerError,
            ConnectionError,
            TimeoutError,
        )

    def get_model(self) -> str:
        """Get the current model ID."""
        return self.model

    def set_model(self, model: str) -> None:
        """Set the model to use."""
        self.model = model

    def _build_messages(self, user_input: str) -> list[dict]:
        """Build the messages list for the API call."""
        messages = self.conversation_history.copy()
        messages.append({"role": "user", "content": user_input})
        return messages

    def _get_context_usage(self) -> tuple[int, float]:
        """Get current context usage in tokens and percentage."""
        tokens = estimate_history_tokens(self.conversation_history)
        percentage = tokens / self.context_budget if self.context_budget > 0 else 0
        return tokens, percentage

    def _needs_summarization(self) -> bool:
        """Check if conversation history needs summarization."""
        tokens, percentage = self._get_context_usage()
        return percentage >= self.summarize_threshold

    def _format_messages_for_summary(self, messages: list[dict]) -> str:
        """Format messages into readable text for summarization."""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")

            if isinstance(content, str):
                lines.append(f"{role}: {content}")
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            parts.append(f"[Used tool: {block.get('name')}]")
                        elif block.get("type") == "tool_result":
                            result = str(block.get("content", ""))[:200]
                            parts.append(f"[Tool result: {result}...]")
                if parts:
                    lines.append(f"{role}: {' '.join(parts)}")

        return "\n".join(lines)

    def _summarize_history(self) -> None:
        """Summarize older messages to reduce context size."""
        if len(self.conversation_history) <= self.min_recent_messages:
            return

        messages_to_keep = self.min_recent_messages
        messages_to_summarize = self.conversation_history[:-messages_to_keep]

        if not messages_to_summarize:
            return

        conversation_text = self._format_messages_for_summary(messages_to_summarize)

        if self._conversation_summary:
            conversation_text = f"PREVIOUS SUMMARY:\n{self._conversation_summary}\n\nNEW MESSAGES:\n{conversation_text}"

        try:
            summary_response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": SUMMARIZATION_PROMPT.format(conversation=conversation_text)
                }]
            )

            summary_text = ""
            for block in summary_response.content:
                if hasattr(block, 'text'):
                    summary_text += block.text

            if summary_text:
                self._conversation_summary = summary_text.strip()
                self._summarized_message_count += len(messages_to_summarize)
                self.conversation_history = self.conversation_history[-messages_to_keep:]

                logger.info(
                    f"Summarized {len(messages_to_summarize)} messages. "
                    f"History now has {len(self.conversation_history)} messages."
                )

        except Exception as e:
            logger.warning(f"Summarization failed, truncating history: {e}")
            self.conversation_history = self.conversation_history[-messages_to_keep:]

    def _maybe_manage_context(self) -> None:
        """Check context usage and summarize if needed."""
        if self._needs_summarization():
            logger.info("Context window threshold reached, summarizing history...")
            self._summarize_history()

    def _build_system_prompt(self, system_context: Optional[str] = None) -> str:
        """Build system prompt with optional context and conversation summary."""
        pm = get_prompt_manager()
        return pm.build_prompt(
            provider="anthropic",
            system_context=system_context,
            summary=self._conversation_summary
        )

    def _store_assistant_history(self, response: AssistantResponse) -> None:
        """Store assistant response in conversation history."""
        assistant_content = []
        if response.text:
            assistant_content.append({
                "type": "text",
                "text": response.text
            })
        for tool_call in response.tool_calls:
            assistant_content.append({
                "type": "tool_use",
                "id": tool_call["id"],
                "name": tool_call["name"],
                "input": tool_call["input"]
            })
        self.conversation_history.append({
            "role": "assistant",
            "content": assistant_content
        })

    def _stream_request(
        self,
        system: str,
        messages: list,
        on_text: Callable[[str], None]
    ) -> Message:
        """Make a streaming API request, invoking callback for each text delta."""
        with self.client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=self.tool_handler.get_all_tools(),
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                on_text(text)
            return stream.get_final_message()

    def _make_api_call(
        self,
        system: str,
        messages: list,
        on_text: Optional[Callable[[str], None]] = None
    ) -> Message:
        """Make an API call with retry and circuit breaker."""
        def api_call() -> Message:
            if on_text is not None:
                return self._stream_request(system, messages, on_text)
            else:
                return self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system,
                    tools=self.tool_handler.get_all_tools(),
                    messages=messages
                )

        def on_retry(attempt: int, exc: Exception) -> None:
            logger.warning(
                f"API call failed (attempt {attempt}), retrying: {type(exc).__name__}: {exc}"
            )

        result = ErrorRecovery.retry(
            func=api_call,
            max_attempts=self._retry_config["max_attempts"],
            base_delay=self._retry_config["base_delay"],
            max_delay=self._retry_config["max_delay"],
            jitter=self._retry_config["jitter"],
            circuit_breaker=self._circuit_breaker,
            retryable_exceptions=self._retryable_exceptions,
            on_retry=on_retry
        )

        if result.is_err:
            error = result.error
            if error.original_exception:
                raise error.original_exception
            raise RuntimeError(error.technical_message)

        return result.unwrap()

    def _process_response(self, response: Message) -> AssistantResponse:
        """Process Claude's response and extract text and tool calls."""
        text_parts = []
        tool_calls = []
        pending_confirmations = []

        for block in response.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ToolUseBlock):
                tool_call = {
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                }
                tool_calls.append(tool_call)

                tool_input = block.input
                if isinstance(tool_input, dict) and tool_input.get("requires_confirmation", False):
                    pending_confirmations.append(tool_call)

        return AssistantResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            is_complete=(response.stop_reason == "end_turn"),
            requires_action=(response.stop_reason == "tool_use"),
            pending_confirmations=pending_confirmations
        )

    def send_message(
        self,
        user_input: str,
        system_context: Optional[str] = None,
        on_text: Optional[Callable[[str], None]] = None
    ) -> AssistantResponse:
        """Send a message to Claude and get a response."""
        self._maybe_manage_context()

        messages = self._build_messages(user_input)
        system = self._build_system_prompt(system_context)

        response = self._make_api_call(system, messages, on_text)

        self.conversation_history.append({
            "role": "user",
            "content": user_input
        })

        assistant_response = self._process_response(response)
        self._store_assistant_history(assistant_response)

        return assistant_response

    def send_tool_results(
        self,
        tool_results: list[dict[str, Any]],
        system_context: Optional[str] = None,
        on_text: Optional[Callable[[str], None]] = None
    ) -> AssistantResponse:
        """Send tool execution results back to Claude."""
        self._maybe_manage_context()

        tool_result_content = []
        for result in tool_results:
            tool_result_content.append({
                "type": "tool_result",
                "tool_use_id": result["tool_use_id"],
                "content": result["content"],
                "is_error": result.get("is_error", False)
            })

        self.conversation_history.append({
            "role": "user",
            "content": tool_result_content
        })

        system = self._build_system_prompt(system_context)

        response = self._make_api_call(system, self.conversation_history, on_text)

        assistant_response = self._process_response(response)
        self._store_assistant_history(assistant_response)

        return assistant_response

    def clear_history(self) -> None:
        """Clear the conversation history and summary."""
        self.conversation_history = []
        self._conversation_summary = None
        self._summarized_message_count = 0

    def get_history_summary(self) -> str:
        """Get a summary of the conversation history."""
        if not self.conversation_history and not self._conversation_summary:
            return "No conversation history."

        summary_parts = []

        tokens, percentage = self._get_context_usage()
        summary_parts.append(f"Context usage: {tokens:,} tokens ({percentage:.1%} of budget)")

        if self._summarized_message_count > 0:
            summary_parts.append(f"Summarized messages: {self._summarized_message_count}")

        summary_parts.append(f"Active messages: {len(self.conversation_history)}")
        summary_parts.append("")

        for msg in self.conversation_history[-10:]:
            role = msg["role"].capitalize()
            content = msg["content"]
            if isinstance(content, str):
                preview = content[:100] + "..." if len(content) > 100 else content
                summary_parts.append(f"{role}: {preview}")
            elif isinstance(content, list):
                types = [c.get("type", "unknown") for c in content]
                summary_parts.append(f"{role}: [{', '.join(types)}]")

        return "\n".join(summary_parts)

    def get_context_stats(self) -> dict[str, Any]:
        """Get detailed context window statistics."""
        tokens, percentage = self._get_context_usage()
        return {
            "tokens_used": tokens,
            "token_budget": self.context_budget,
            "usage_percentage": percentage,
            "active_messages": len(self.conversation_history),
            "summarized_messages": self._summarized_message_count,
            "has_summary": self._conversation_summary is not None,
            "summarize_threshold": self.summarize_threshold,
            "min_recent_messages": self.min_recent_messages,
        }

    def get_circuit_breaker_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics for monitoring."""
        return self._circuit_breaker.get_stats()

    def reset_circuit_breaker(self) -> None:
        """Reset the circuit breaker to closed state."""
        self._circuit_breaker.reset()
        logger.info("Circuit breaker reset to closed state")
