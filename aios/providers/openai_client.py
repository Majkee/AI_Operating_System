"""
OpenAI client for AIOS using the Responses API.

Handles communication with OpenAI's Responses API for GPT models.
Uses the new Responses API (client.responses.create()) which is
recommended over the older Chat Completions API.

Supports GPT-5.2 family models with features:
- Reasoning effort: none, low, medium, high, xhigh
- Verbosity: low, medium, high
- Response chaining via previous_response_id
- Function calling with strict mode
"""

import json
import logging
import os
from typing import Any, Callable, Literal, Optional

from openai import OpenAI
from openai import (
    APIError,
    APIConnectionError,
    RateLimitError,
    AuthenticationError,
    BadRequestError,
    APITimeoutError,
)

from .base import BaseClient, AssistantResponse
from .context_manager import ContextManager, create_summarization_prompt
from ..models import is_gpt5_model, is_reasoning_model, supports_verbosity


class OpenAIError(Exception):
    """Custom exception for OpenAI-related errors with user-friendly messages."""

    def __init__(self, message: str, error_code: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.error_code = error_code
        self.original_error = original_error
        self.user_message = message


def handle_openai_error(error: Exception) -> OpenAIError:
    """Convert OpenAI SDK errors to user-friendly OpenAIError."""
    if isinstance(error, AuthenticationError):
        return OpenAIError(
            "Invalid OpenAI API key. Please check your API key in config or OPENAI_API_KEY environment variable.",
            error_code="AUTH_ERROR",
            original_error=error
        )
    elif isinstance(error, RateLimitError):
        error_msg = str(error).lower()
        if "insufficient_quota" in error_msg:
            return OpenAIError(
                "OpenAI quota exceeded. Please add credits at https://platform.openai.com/settings/organization/billing",
                error_code="QUOTA_EXCEEDED",
                original_error=error
            )
        if "tokens per" in error_msg:
            return OpenAIError(
                "OpenAI token rate limit reached. Please wait a moment and try again.",
                error_code="TOKEN_RATE_LIMIT",
                original_error=error
            )
        return OpenAIError(
            "OpenAI rate limit reached. Please wait a moment and try again.",
            error_code="RATE_LIMIT",
            original_error=error
        )
    elif isinstance(error, APIConnectionError):
        return OpenAIError(
            "Cannot connect to OpenAI. Please check your internet connection.",
            error_code="CONNECTION_ERROR",
            original_error=error
        )
    elif isinstance(error, APITimeoutError):
        return OpenAIError(
            "OpenAI request timed out. Please try again.",
            error_code="TIMEOUT",
            original_error=error
        )
    elif isinstance(error, BadRequestError):
        error_msg = str(error).lower()
        original_msg = str(error)

        # Check for context length exceeded
        if "context_length_exceeded" in error_msg or "maximum context length" in error_msg:
            return OpenAIError(
                "Conversation too long for this model. Consider starting a new conversation or use /clear.",
                error_code="CONTEXT_LENGTH_EXCEEDED",
                original_error=error
            )

        # Check for invalid model
        if "model" in error_msg and ("not found" in error_msg or "does not exist" in error_msg):
            return OpenAIError(
                "Invalid model specified. Please check the model name in your config.",
                error_code="INVALID_MODEL",
                original_error=error
            )

        # Check for invalid function schema
        if "schema" in error_msg or "function" in error_msg:
            return OpenAIError(
                f"Invalid function schema: {original_msg[:200]}",
                error_code="INVALID_SCHEMA",
                original_error=error
            )

        # Check for content policy violation
        if "content" in error_msg and "policy" in error_msg:
            return OpenAIError(
                "Request rejected due to content policy. Please rephrase your request.",
                error_code="CONTENT_POLICY",
                original_error=error
            )

        return OpenAIError(
            f"Invalid request to OpenAI: {original_msg[:200]}",
            error_code="BAD_REQUEST",
            original_error=error
        )
    elif isinstance(error, APIError):
        error_msg = str(error).lower()
        original_msg = str(error)

        # Check for server overload
        if "overloaded" in error_msg or "503" in error_msg:
            return OpenAIError(
                "OpenAI servers are currently overloaded. Please try again later.",
                error_code="SERVER_OVERLOADED",
                original_error=error
            )

        return OpenAIError(
            f"OpenAI API error: {original_msg[:200]}",
            error_code="API_ERROR",
            original_error=error
        )
    else:
        return OpenAIError(
            f"Unexpected error: {str(error)[:200]}",
            error_code="UNKNOWN_ERROR",
            original_error=error
        )
from .tool_converters import (
    convert_tools_for_openai,
    convert_openai_tool_calls,
    build_openai_tool_results,
)
from ..claude.tools import ToolHandler
from ..config import get_config

logger = logging.getLogger(__name__)


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
- Use emojis to make responses friendly and approachable (👋 📁 📦 ✅ ⚠️ etc.)

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

## Timeouts and Long-Running Operations
- Default timeout: 30 seconds (quick operations)
- Set `timeout` explicitly for longer work (package install: 300-600, large downloads: 1800-3600)
- Maximum: 3600 seconds (1 hour)
- Set `long_running: true` alongside high timeouts to stream live output

## Background Tasks
- Set `background: true` in run_command for tasks the user does not need to watch
- Background tasks have no timeout and run until completion"""


class OpenAIClient(BaseClient):
    """Client for OpenAI Responses API.

    Uses the new Responses API which provides better tool handling
    and response chaining through previous_response_id.

    Supports GPT-5.2 family features:
    - Reasoning effort: Controls how many reasoning tokens the model generates
    - Verbosity: Controls output length and detail level
    - Response chaining: Maintains conversation context efficiently
    """

    # GPT-5.2 reasoning effort levels
    REASONING_EFFORTS = ("none", "low", "medium", "high", "xhigh")
    # GPT-5.2 verbosity levels
    VERBOSITY_LEVELS = ("low", "medium", "high")

    def __init__(self, tool_handler: Optional[ToolHandler] = None):
        """Initialize the OpenAI client."""
        config = get_config()

        api_key = getattr(config.api, 'openai_api_key', None) or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "No OpenAI API key found. Please set OPENAI_API_KEY environment variable "
                "or add openai_api_key to your config file."
            )

        # OpenAI client always uses the official API endpoint
        # (base_url is only for LM Studio which uses Chat Completions API)
        self.client = OpenAI(api_key=api_key)
        self.model = config.api.model
        self.max_tokens = config.api.max_tokens
        self.tool_handler = tool_handler or ToolHandler()

        # Response chaining for multi-turn conversations
        self._last_response_id: Optional[str] = None
        self._instructions: Optional[str] = None

        # GPT-5.2 specific settings
        # Reasoning effort: none (default for 5.2), low, medium, high, xhigh
        self._reasoning_effort: Optional[str] = None  # None = use model default
        # Verbosity: low, medium (default), high
        self._verbosity: Optional[str] = None  # None = use model default (medium)

        # Parallel tool calls configuration
        self._parallel_tool_calls: bool = config.api.parallel_tool_calls

        # Context manager for conversation tracking and summarization
        self._context_manager = ContextManager(
            summarize_fn=self._summarize_conversation,
            context_budget=getattr(config.api, 'context_budget', 150000),
            summarize_threshold=getattr(config.api, 'summarize_threshold', 0.75),
            min_recent_messages=getattr(config.api, 'min_recent_messages', 6),
        )

    def set_reasoning_effort(
        self,
        effort: Optional[Literal["none", "low", "medium", "high", "xhigh"]]
    ) -> None:
        """Set reasoning effort for GPT-5.2+ and o-series models.

        Controls how many reasoning tokens the model generates before producing a response.
        - none: Lowest latency, minimal reasoning (default for GPT-5.2)
        - low: Minimal reasoning
        - medium: Moderate reasoning
        - high: Thorough reasoning
        - xhigh: Maximum reasoning (GPT-5.2+ only)

        Args:
            effort: Reasoning effort level or None for model default

        Raises:
            ValueError: If effort level is invalid
        """
        if effort is not None and effort not in self.REASONING_EFFORTS:
            raise ValueError(f"Invalid reasoning effort: {effort}. Valid: {self.REASONING_EFFORTS}")
        if effort is not None and not self._supports_reasoning():
            logger.warning(
                f"Model '{self.model}' may not support reasoning effort. "
                f"Supported models: GPT-5.x family, o-series (o1, o3, o4)."
            )
        self._reasoning_effort = effort

    def set_verbosity(
        self,
        verbosity: Optional[Literal["low", "medium", "high"]]
    ) -> None:
        """Set verbosity for GPT-5.2+ models.

        Controls how many output tokens are generated.
        - low: Concise answers, minimal commentary
        - medium: Balanced (default)
        - high: Thorough explanations, detailed code

        Note: Only GPT-5.x models support the verbosity parameter.

        Args:
            verbosity: Verbosity level or None for model default

        Raises:
            ValueError: If verbosity level is invalid
        """
        if verbosity is not None and verbosity not in self.VERBOSITY_LEVELS:
            raise ValueError(f"Invalid verbosity: {verbosity}. Valid: {self.VERBOSITY_LEVELS}")
        if verbosity is not None and not self._supports_verbosity():
            logger.warning(
                f"Model '{self.model}' does not support verbosity parameter. "
                f"Only GPT-5.x models support this feature."
            )
        self._verbosity = verbosity

    def _is_gpt5_model(self) -> bool:
        """Check if current model is GPT-5.x family."""
        return is_gpt5_model(self.model)

    def _supports_reasoning(self) -> bool:
        """Check if current model supports reasoning effort parameter."""
        return is_reasoning_model(self.model)

    def _supports_verbosity(self) -> bool:
        """Check if current model supports verbosity parameter."""
        return supports_verbosity(self.model)

    def _summarize_conversation(self, conversation_text: str) -> str:
        """Summarize conversation text using the OpenAI model.

        This is called by the ContextManager when summarization is needed.

        Args:
            conversation_text: Formatted conversation to summarize

        Returns:
            Summary of the conversation
        """
        prompt = create_summarization_prompt(conversation_text)

        try:
            # Use a simple request without response chaining for summarization
            response = self.client.responses.create(
                model=self.model,
                input=[{"role": "user", "content": prompt}],
                max_output_tokens=1000,  # Summaries should be concise
            )

            # Extract text from response
            if hasattr(response, 'output_text') and response.output_text:
                return response.output_text

            # Fallback extraction
            for item in response.output:
                if hasattr(item, 'type') and item.type == "message":
                    if hasattr(item, 'content'):
                        for content_block in item.content:
                            if hasattr(content_block, 'text'):
                                return content_block.text

            return "Summary generation failed."

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            raise

    def get_model(self) -> str:
        """Get the current model ID."""
        return self.model

    def set_model(self, model: str) -> None:
        """Set the model to use."""
        self.model = model

    def _build_system_prompt(self, system_context: Optional[str] = None) -> str:
        """Build system prompt with optional context and conversation summary."""
        prompt = SYSTEM_PROMPT

        # Include conversation summary if available
        if self._context_manager.summary:
            prompt += f"\n\n## Previous Conversation Summary\n{self._context_manager.summary}"

        if system_context:
            prompt += f"\n\n## Current System Context\n{system_context}"

        return prompt

    def _build_request_params(
        self,
        input_items: list,
        tools: list,
    ) -> dict[str, Any]:
        """Build request parameters for OpenAI Responses API.

        Includes GPT-5.2 specific parameters when applicable.
        """
        params: dict[str, Any] = {
            "model": self.model,
            "instructions": self._instructions,
            "input": input_items,
            "max_output_tokens": self.max_tokens,
            "previous_response_id": self._last_response_id,
        }

        # Only add tools if we have any
        if tools:
            params["tools"] = tools
            # Allow parallel tool calls if configured
            params["parallel_tool_calls"] = self._parallel_tool_calls

        # Add reasoning parameters for models that support it (GPT-5.x, o-series)
        if self._reasoning_effort is not None and self._supports_reasoning():
            params["reasoning"] = {"effort": self._reasoning_effort}

        # Add verbosity for models that support it (GPT-5.x only)
        if self._verbosity is not None and self._supports_verbosity():
            params["text"] = {"verbosity": self._verbosity}

        return params

    def send_message(
        self,
        user_input: str,
        system_context: Optional[str] = None,
        on_text: Optional[Callable[[str], None]] = None
    ) -> AssistantResponse:
        """Send a message to OpenAI and get a response."""
        # Track user message in context manager
        self._context_manager.add_message("user", user_input)

        # Check if summarization is needed before making the request
        if self._context_manager.check_and_summarize():
            # If we summarized, break the response chain to start fresh
            # The summary is now included in the system prompt
            self._last_response_id = None
            logger.info("Context summarized, starting new response chain")

        self._instructions = self._build_system_prompt(system_context)
        tools = convert_tools_for_openai(self.tool_handler.get_all_tools())

        # Build input - user message
        input_items = [{"role": "user", "content": user_input}]

        try:
            if on_text:  # Streaming
                response = self._stream_request(input_items, tools, on_text)
            else:
                params = self._build_request_params(input_items, tools)
                response = self.client.responses.create(**params)
                self._last_response_id = response.id
                response = self._process_response(response)

            # Track assistant response in context manager
            if response.text:
                self._context_manager.add_message("assistant", response.text)

            return response

        except OpenAIError as e:
            # Handle context length exceeded by auto-summarizing
            if e.error_code == "CONTEXT_LENGTH_EXCEEDED":
                logger.warning("Context length exceeded, forcing summarization...")
                if self._context_manager.summarize():
                    self._last_response_id = None
                    # Retry the request
                    return self.send_message(user_input, system_context, on_text)
            raise  # Re-raise if not recoverable
        except (APIError, APIConnectionError, RateLimitError, AuthenticationError, BadRequestError, APITimeoutError) as e:
            logger.error(f"OpenAI API error [{type(e).__name__}]: {e}")
            raise handle_openai_error(e)
        except Exception as e:
            logger.error(f"Unexpected OpenAI error: {e}")
            raise handle_openai_error(e)

    def _stream_request(
        self,
        input_items: list,
        tools: list,
        on_text: Callable[[str], None]
    ) -> AssistantResponse:
        """Make a streaming request to OpenAI Responses API."""
        try:
            params = self._build_request_params(input_items, tools)
            params["stream"] = True
            stream = self.client.responses.create(**params)

            content = ""
            function_calls = []

            for event in stream:
                # Handle different event types
                if hasattr(event, 'type'):
                    if event.type == 'response.output_text.delta':
                        delta = getattr(event, 'delta', '')
                        if delta:
                            content += delta
                            on_text(delta)
                    elif event.type == 'response.completed':
                        # Final response with all data
                        if hasattr(event, 'response') and event.response:
                            self._last_response_id = event.response.id
                            for item in event.response.output:
                                if hasattr(item, 'type') and item.type == "function_call":
                                    function_calls.append({
                                        "id": item.call_id,
                                        "name": item.name,
                                        "input": json.loads(item.arguments) if isinstance(item.arguments, str) else item.arguments
                                    })

            return AssistantResponse(
                text=content,
                tool_calls=function_calls,
                is_complete=(len(function_calls) == 0),
                requires_action=(len(function_calls) > 0)
            )

        except OpenAIError:
            raise  # Already handled, re-raise
        except (APIError, APIConnectionError, RateLimitError, AuthenticationError, BadRequestError, APITimeoutError) as e:
            logger.error(f"OpenAI streaming error [{type(e).__name__}]: {e}")
            raise handle_openai_error(e)
        except Exception as e:
            logger.error(f"Unexpected OpenAI streaming error: {e}")
            raise handle_openai_error(e)

    def _process_response(self, response) -> AssistantResponse:
        """Process OpenAI Responses API response."""
        # Extract text from output
        text = ""
        if hasattr(response, 'output_text') and response.output_text:
            text = response.output_text
        elif hasattr(response, 'output'):
            for item in response.output:
                if hasattr(item, 'type') and item.type == "message":
                    if hasattr(item, 'content'):
                        for content_block in item.content:
                            if hasattr(content_block, 'text'):
                                text += content_block.text

        # Extract function calls
        function_calls = []
        if hasattr(response, 'output'):
            function_calls = convert_openai_tool_calls(response.output)

        return AssistantResponse(
            text=text,
            tool_calls=function_calls,
            is_complete=(len(function_calls) == 0),
            requires_action=(len(function_calls) > 0)
        )

    def send_tool_results(
        self,
        tool_results: list[dict[str, Any]],
        system_context: Optional[str] = None,
        on_text: Optional[Callable[[str], None]] = None
    ) -> AssistantResponse:
        """Send tool execution results back to OpenAI."""
        # Track tool results in context manager
        for result in tool_results:
            tool_id = result.get("tool_use_id", "unknown")
            content = result.get("content", "")
            if isinstance(content, dict):
                content = json.dumps(content)
            self._context_manager.add_message("tool", content, tool_call_id=tool_id)

        # Build function_call_output items
        input_items = build_openai_tool_results(tool_results)

        tools = convert_tools_for_openai(self.tool_handler.get_all_tools())

        try:
            if on_text:  # Streaming
                response = self._stream_request(input_items, tools, on_text)
            else:
                # Use previous_response_id to chain responses
                params = self._build_request_params(input_items, tools)
                response = self.client.responses.create(**params)
                self._last_response_id = response.id
                response = self._process_response(response)

            # Track assistant response in context manager
            if response.text:
                self._context_manager.add_message("assistant", response.text)

            return response

        except OpenAIError:
            raise  # Already handled, re-raise
        except (APIError, APIConnectionError, RateLimitError, AuthenticationError, BadRequestError, APITimeoutError) as e:
            logger.error(f"OpenAI API error sending tool results [{type(e).__name__}]: {e}")
            raise handle_openai_error(e)
        except Exception as e:
            logger.error(f"Unexpected OpenAI error sending tool results: {e}")
            raise handle_openai_error(e)

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self._last_response_id = None
        self._context_manager.clear()

    def get_history_summary(self) -> str:
        """Get a summary of the conversation history."""
        context_stats = self._context_manager.get_stats()

        if context_stats.message_count == 0 and not context_stats.has_summary:
            return "No conversation history."

        parts = [
            f"Messages: {context_stats.message_count}",
            f"Response chaining: {'Active' if self._last_response_id else 'Not active'}",
            f"Context usage: ~{context_stats.total_tokens:,} tokens ({context_stats.budget_used_percentage:.1%})",
        ]

        if context_stats.summarized_message_count > 0:
            parts.append(f"Summarized: {context_stats.summarized_message_count} messages")

        if context_stats.has_summary:
            parts.append("Has conversation summary: Yes")

        return "\n".join(parts)

    def get_context_stats(self) -> dict[str, Any]:
        """Get context statistics."""
        context_stats = self._context_manager.get_stats()

        stats = {
            "message_count": context_stats.message_count,
            "has_response_chain": self._last_response_id is not None,
            "provider": "openai",
            "model": self.model,
            "is_gpt5_model": self._is_gpt5_model(),
            "supports_reasoning": self._supports_reasoning(),
            "supports_verbosity": self._supports_verbosity(),
            "token_usage": context_stats.total_tokens,
            "token_budget": context_stats.token_budget,
            "budget_used_percentage": context_stats.budget_used_percentage,
            "summarized_messages": context_stats.summarized_message_count,
            "has_summary": context_stats.has_summary,
        }

        # Add reasoning stats if supported
        if self._supports_reasoning():
            stats["reasoning_effort"] = self._reasoning_effort or "none (default)"

        # Add verbosity stats if supported
        if self._supports_verbosity():
            stats["verbosity"] = self._verbosity or "medium (default)"

        return stats
