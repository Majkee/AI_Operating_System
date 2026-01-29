"""
Claude API client for AIOS.

Handles communication with the Anthropic API and processes
tool calls from Claude's responses. Includes automatic context
window management with summarization to prevent token limit errors.
"""

import json
import logging
from typing import Any, Callable, Optional
from dataclasses import dataclass, field

import anthropic
from anthropic.types import Message, ToolUseBlock, TextBlock

from .tools import ToolHandler, ToolResult
from ..config import get_config
from ..errors import ErrorRecovery, CircuitBreaker

logger = logging.getLogger(__name__)


@dataclass
class ConversationMessage:
    """A message in the conversation."""
    role: str  # "user" or "assistant"
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)


@dataclass
class AssistantResponse:
    """Response from the assistant."""
    text: str
    tool_calls: list[dict[str, Any]]
    is_complete: bool
    requires_action: bool = False
    pending_confirmations: list[dict] = field(default_factory=list)


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


# Context window management constants
# Claude models have different context windows:
# - claude-sonnet-4: 200k tokens
# - claude-opus-4: 200k tokens
# - claude-haiku: 200k tokens
# We use conservative limits to leave room for system prompt, tools, and response

DEFAULT_CONTEXT_BUDGET = 150_000  # tokens - leave room for response
SUMMARIZE_THRESHOLD = 0.75  # Trigger summarization at 75% of budget
MIN_RECENT_MESSAGES = 6  # Always keep at least this many recent messages
CHARS_PER_TOKEN = 4  # Rough estimate: 1 token ≈ 4 characters for English


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length.

    This is a rough heuristic. For English text, ~4 characters per token
    is a reasonable approximation. JSON/structured content may vary.
    """
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_message_tokens(message: dict) -> int:
    """Estimate tokens in a conversation message."""
    content = message.get("content", "")

    if isinstance(content, str):
        return estimate_tokens(content)

    # List content (tool use, tool results, etc.)
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                # Text block
                if block.get("type") == "text":
                    total += estimate_tokens(block.get("text", ""))
                # Tool use block - include name and JSON input
                elif block.get("type") == "tool_use":
                    total += estimate_tokens(block.get("name", ""))
                    total += estimate_tokens(json.dumps(block.get("input", {})))
                # Tool result
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


class ClaudeClient:
    """Client for interacting with Claude API."""

    def __init__(self, tool_handler: Optional[ToolHandler] = None):
        """Initialize the Claude client."""
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
        self._summarized_message_count: int = 0  # How many messages were summarized

        # Retry and circuit breaker configuration
        self._circuit_breaker = ErrorRecovery.get_circuit_breaker(
            name="claude_api",
            failure_threshold=5,
            recovery_timeout=60.0
        )
        self._retry_config = {
            "max_attempts": 3,
            "base_delay": 1.0,
            "max_delay": 30.0,
            "jitter": True,
        }
        # Exceptions that should trigger retry (network/transient errors)
        self._retryable_exceptions = (
            anthropic.APIConnectionError,
            anthropic.RateLimitError,
            anthropic.InternalServerError,
            ConnectionError,
            TimeoutError,
        )

    def _build_messages(self, user_input: str) -> list[dict]:
        """Build the messages list for the API call."""
        messages = self.conversation_history.copy()
        messages.append({"role": "user", "content": user_input})
        return messages

    def _get_context_usage(self) -> tuple[int, float]:
        """Get current context usage in tokens and percentage.

        Returns:
            Tuple of (tokens_used, percentage_of_budget)
        """
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
        """Summarize older messages to reduce context size.

        Keeps the most recent messages verbatim and summarizes older ones.
        The summary is stored and prepended to future API calls.
        """
        if len(self.conversation_history) <= self.min_recent_messages:
            return  # Not enough messages to summarize

        # Determine how many messages to summarize
        # Keep at least min_recent_messages, summarize the rest
        messages_to_keep = self.min_recent_messages
        messages_to_summarize = self.conversation_history[:-messages_to_keep]

        if not messages_to_summarize:
            return

        # Format messages for summarization
        conversation_text = self._format_messages_for_summary(messages_to_summarize)

        # Include previous summary if exists
        if self._conversation_summary:
            conversation_text = f"PREVIOUS SUMMARY:\n{self._conversation_summary}\n\nNEW MESSAGES:\n{conversation_text}"

        try:
            # Call Claude to create summary (using a smaller, faster model if available)
            summary_response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,  # Summaries should be concise
                messages=[{
                    "role": "user",
                    "content": SUMMARIZATION_PROMPT.format(conversation=conversation_text)
                }]
            )

            # Extract summary text
            summary_text = ""
            for block in summary_response.content:
                # Use duck-typing for testability
                if hasattr(block, 'text'):
                    summary_text += block.text

            if summary_text:
                self._conversation_summary = summary_text.strip()
                self._summarized_message_count += len(messages_to_summarize)

                # Keep only recent messages
                self.conversation_history = self.conversation_history[-messages_to_keep:]

                logger.info(
                    f"Summarized {len(messages_to_summarize)} messages. "
                    f"History now has {len(self.conversation_history)} messages."
                )

        except Exception as e:
            # If summarization fails, fall back to simple truncation
            logger.warning(f"Summarization failed, truncating history: {e}")
            self.conversation_history = self.conversation_history[-messages_to_keep:]

    def _maybe_manage_context(self) -> None:
        """Check context usage and summarize if needed."""
        if self._needs_summarization():
            logger.info("Context window threshold reached, summarizing history...")
            self._summarize_history()

    def _build_system_prompt(self, system_context: Optional[str] = None) -> str:
        """Build system prompt with optional context and conversation summary."""
        prompt = SYSTEM_PROMPT

        # Add conversation summary if we've summarized older messages
        if self._conversation_summary:
            prompt += f"\n\n## Earlier Conversation Summary\n{self._conversation_summary}"

        # Add current system context
        if system_context:
            prompt += f"\n\n## Current System Context\n{system_context}"

        return prompt

    def _store_assistant_history(self, response: "AssistantResponse") -> None:
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
    ) -> "Message":
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
    ) -> "Message":
        """
        Make an API call with retry and circuit breaker.

        Args:
            system: System prompt
            messages: Conversation messages
            on_text: Optional callback for streaming

        Returns:
            API response message

        Raises:
            Exception: If all retries fail or circuit breaker is open
        """
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
            # Re-raise as exception for callers to handle
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

                # Check if this tool requires confirmation
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
        """Send a message to Claude and get a response.

        Args:
            user_input: The user's message
            system_context: Optional system context to append to prompt
            on_text: Optional callback for streaming text deltas. When provided,
                     uses streaming API; when None, uses blocking API.

        Returns:
            AssistantResponse with text and any tool calls

        Note:
            Uses exponential backoff with jitter for transient failures.
            Circuit breaker prevents hammering the API after repeated failures.
        """
        # Check and manage context window before making request
        self._maybe_manage_context()

        messages = self._build_messages(user_input)
        system = self._build_system_prompt(system_context)

        # Make API request with retry and circuit breaker
        response = self._make_api_call(system, messages, on_text)

        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_input
        })

        # Process and store assistant response
        assistant_response = self._process_response(response)
        self._store_assistant_history(assistant_response)

        return assistant_response

    def send_tool_results(
        self,
        tool_results: list[dict[str, Any]],
        system_context: Optional[str] = None,
        on_text: Optional[Callable[[str], None]] = None
    ) -> AssistantResponse:
        """Send tool execution results back to Claude.

        Args:
            tool_results: List of tool execution results
            system_context: Optional system context to append to prompt
            on_text: Optional callback for streaming text deltas. When provided,
                     uses streaming API; when None, uses blocking API.

        Returns:
            AssistantResponse with text and any tool calls

        Note:
            Uses exponential backoff with jitter for transient failures.
            Circuit breaker prevents hammering the API after repeated failures.
        """
        # Check and manage context window before making request
        self._maybe_manage_context()

        # Add tool results to conversation
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

        # Make API request with retry and circuit breaker
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

        # Show context usage stats
        tokens, percentage = self._get_context_usage()
        summary_parts.append(f"Context usage: {tokens:,} tokens ({percentage:.1%} of budget)")

        if self._summarized_message_count > 0:
            summary_parts.append(f"Summarized messages: {self._summarized_message_count}")

        summary_parts.append(f"Active messages: {len(self.conversation_history)}")
        summary_parts.append("")

        # Show recent messages
        for msg in self.conversation_history[-10:]:  # Last 10 messages
            role = msg["role"].capitalize()
            content = msg["content"]
            if isinstance(content, str):
                preview = content[:100] + "..." if len(content) > 100 else content
                summary_parts.append(f"{role}: {preview}")
            elif isinstance(content, list):
                # Tool use or tool result
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
