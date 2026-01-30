"""
LM Studio client for AIOS using Chat Completions API.

Handles communication with LM Studio and other OpenAI-compatible
local inference servers. Uses the Chat Completions API which is
what LM Studio and most local servers implement.

Note: Local models may have limited or no support for tool calling.
"""

import json
import logging
import os
from typing import Any, Callable, Optional

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


class LMStudioError(Exception):
    """Custom exception for LM Studio-related errors with user-friendly messages."""

    def __init__(self, message: str, error_code: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.error_code = error_code
        self.original_error = original_error
        self.user_message = message


def handle_lmstudio_error(error: Exception) -> LMStudioError:
    """Convert OpenAI SDK errors to user-friendly LMStudioError."""
    if isinstance(error, APIConnectionError):
        return LMStudioError(
            "Cannot connect to LM Studio. Is the server running at the configured URL?",
            error_code="CONNECTION_ERROR",
            original_error=error
        )
    elif isinstance(error, APITimeoutError):
        return LMStudioError(
            "LM Studio request timed out. The model may be loading or processing. Try again.",
            error_code="TIMEOUT",
            original_error=error
        )
    elif isinstance(error, BadRequestError):
        error_msg = str(error)
        if "model" in error_msg.lower():
            return LMStudioError(
                "Model not found in LM Studio. Make sure the model is loaded.",
                error_code="MODEL_NOT_FOUND",
                original_error=error
            )
        return LMStudioError(
            f"Invalid request to LM Studio: {error_msg[:200]}",
            error_code="BAD_REQUEST",
            original_error=error
        )
    elif isinstance(error, APIError):
        return LMStudioError(
            f"LM Studio API error: {str(error)[:200]}",
            error_code="API_ERROR",
            original_error=error
        )
    else:
        return LMStudioError(
            f"LM Studio error: {str(error)[:200]}",
            error_code="UNKNOWN_ERROR",
            original_error=error
        )
from .tool_converters import (
    convert_tools_for_chat_completions,
    convert_chat_completions_tool_calls,
    build_chat_completions_tool_results,
)
from ..claude.tools import ToolHandler
from ..config import get_config

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are AIOS, a friendly AI assistant that helps users interact with their Linux computer through natural conversation.

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

### Safety First
- Always explain what an action will do before executing it
- For any action that modifies files or system settings, get confirmation
- Never execute potentially destructive commands without explicit confirmation

### Error Handling
- If something fails, explain what went wrong in simple terms
- Suggest alternatives or solutions when possible
- Never blame the user for errors

## Context
You have access to the user's home directory and can help with:
- Finding and organizing files
- Installing and managing applications
- Viewing system information
- Creating and editing documents
- Basic system maintenance

Remember: Your goal is to make Linux accessible and friendly for everyone!"""


class LMStudioClient(BaseClient):
    """Client for LM Studio and other OpenAI-compatible local servers.

    Uses the Chat Completions API which is what local inference
    servers typically implement. Tool calling support varies by model.
    """

    def __init__(self, tool_handler: Optional[ToolHandler] = None):
        """Initialize the LM Studio client."""
        config = get_config()

        # LM Studio typically doesn't need a real API key
        api_key = getattr(config.api, 'openai_api_key', None) or os.environ.get("OPENAI_API_KEY", "lm-studio")

        # Default to localhost:1234 which is LM Studio's default
        base_url = getattr(config.api, 'openai_base_url', None) or os.environ.get("AIOS_OPENAI_BASE_URL", "http://localhost:1234/v1")

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=120.0,  # Local models can be slow to start
        )
        self.model = config.api.model
        self.max_tokens = config.api.max_tokens
        self.tool_handler = tool_handler or ToolHandler()

        # Track if we've detected tool support
        self._tools_supported: Optional[bool] = None

        # Context manager for conversation tracking and summarization
        self._context_manager = ContextManager(
            summarize_fn=self._summarize_conversation,
            context_budget=getattr(config.api, 'context_budget', 32000),  # Local models often have smaller contexts
            summarize_threshold=getattr(config.api, 'summarize_threshold', 0.75),
            min_recent_messages=getattr(config.api, 'min_recent_messages', 6),
        )

    def get_model(self) -> str:
        """Get the current model ID."""
        return self.model

    def set_model(self, model: str) -> None:
        """Set the model to use."""
        self.model = model
        # Reset tool support detection when model changes
        self._tools_supported = None

    def _build_system_prompt(self, system_context: Optional[str] = None) -> str:
        """Build system prompt with optional context and conversation summary."""
        prompt = SYSTEM_PROMPT

        # Include conversation summary if available
        if self._context_manager.summary:
            prompt += f"\n\n## Previous Conversation Summary\n{self._context_manager.summary}"

        if system_context:
            prompt += f"\n\n## Current System Context\n{system_context}"

        return prompt

    def _summarize_conversation(self, conversation_text: str) -> str:
        """Summarize conversation text using the local model.

        This is called by the ContextManager when summarization is needed.

        Args:
            conversation_text: Formatted conversation to summarize

        Returns:
            Summary of the conversation
        """
        prompt = create_summarization_prompt(conversation_text)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,  # Summaries should be concise
            )

            return response.choices[0].message.content or "Summary generation failed."

        except Exception as e:
            logger.error(f"Failed to generate summary with local model: {e}")
            raise

    def _try_with_tools(self, messages: list[dict], system_prompt: str) -> tuple[Any, bool]:
        """Try to make a request with tool support.

        Returns:
            Tuple of (response, tools_supported)
        """
        tools = convert_tools_for_chat_completions(self.tool_handler.get_all_tools())

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_prompt}] + messages,
                tools=tools if tools else None,
                max_tokens=self.max_tokens,
            )
            return response, True
        except Exception as e:
            # If tools not supported, retry without them
            error_str = str(e).lower()
            if "tool" in error_str or "function" in error_str or "unsupported" in error_str:
                logger.info(f"Tool calling not supported by {self.model}, falling back to text-only mode")
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system_prompt}] + messages,
                    max_tokens=self.max_tokens,
                )
                return response, False
            raise

    def send_message(
        self,
        user_input: str,
        system_context: Optional[str] = None,
        on_text: Optional[Callable[[str], None]] = None
    ) -> AssistantResponse:
        """Send a message to LM Studio and get a response."""
        # Track user message in context manager
        self._context_manager.add_message("user", user_input)

        # Check if summarization is needed
        self._context_manager.check_and_summarize()

        system_prompt = self._build_system_prompt(system_context)

        # Get messages from context manager (excludes summarized messages)
        messages = self._context_manager.get_messages()

        try:
            if on_text:
                response = self._stream_request(messages, system_prompt, on_text)
            else:
                # Try with tools if we haven't determined support yet
                if self._tools_supported is None or self._tools_supported:
                    api_response, self._tools_supported = self._try_with_tools(messages, system_prompt)
                else:
                    # We know tools aren't supported
                    api_response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "system", "content": system_prompt}] + messages,
                        max_tokens=self.max_tokens,
                    )

                response = self._process_response(api_response.choices[0].message)

            # Track assistant response in context manager
            if response.text:
                self._context_manager.add_message("assistant", response.text)

            return response

        except LMStudioError:
            raise  # Already handled, re-raise
        except (APIError, APIConnectionError, RateLimitError, AuthenticationError, BadRequestError, APITimeoutError) as e:
            logger.error(f"LM Studio API error [{type(e).__name__}]: {e}")
            raise handle_lmstudio_error(e)
        except Exception as e:
            logger.error(f"Unexpected LM Studio error: {e}")
            raise handle_lmstudio_error(e)

    def _stream_request(
        self,
        messages: list[dict],
        system_prompt: str,
        on_text: Callable[[str], None]
    ) -> AssistantResponse:
        """Make a streaming request to LM Studio."""
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_prompt}] + messages,
                max_tokens=self.max_tokens,
                stream=True,
            )

            content = ""
            tool_calls_data = []

            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta

                    # Handle text content
                    if delta.content:
                        content += delta.content
                        on_text(delta.content)

                    # Handle tool calls (if supported)
                    if hasattr(delta, 'tool_calls') and delta.tool_calls:
                        for tc in delta.tool_calls:
                            # Accumulate tool call data
                            while len(tool_calls_data) <= tc.index:
                                tool_calls_data.append({"id": "", "name": "", "arguments": ""})

                            if tc.id:
                                tool_calls_data[tc.index]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_data[tc.index]["name"] = tc.function.name
                                if tc.function.arguments:
                                    tool_calls_data[tc.index]["arguments"] += tc.function.arguments

            # Process accumulated tool calls
            tool_calls = []
            for tc_data in tool_calls_data:
                if tc_data["id"] and tc_data["name"]:
                    try:
                        args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append({
                        "id": tc_data["id"],
                        "name": tc_data["name"],
                        "input": args
                    })

            return AssistantResponse(
                text=content,
                tool_calls=tool_calls,
                is_complete=(len(tool_calls) == 0),
                requires_action=(len(tool_calls) > 0)
            )

        except LMStudioError:
            raise  # Already handled, re-raise
        except (APIError, APIConnectionError, RateLimitError, AuthenticationError, BadRequestError, APITimeoutError) as e:
            logger.error(f"LM Studio streaming error [{type(e).__name__}]: {e}")
            raise handle_lmstudio_error(e)
        except Exception as e:
            logger.error(f"Unexpected LM Studio streaming error: {e}")
            raise handle_lmstudio_error(e)

    def _process_response(self, message) -> AssistantResponse:
        """Process a Chat Completions response message."""
        content = message.content or ""

        # Extract tool calls if present
        tool_calls = []
        if hasattr(message, 'tool_calls') and message.tool_calls:
            tool_calls = convert_chat_completions_tool_calls(message.tool_calls)

        return AssistantResponse(
            text=content,
            tool_calls=tool_calls,
            is_complete=(len(tool_calls) == 0),
            requires_action=(len(tool_calls) > 0)
        )

    def send_tool_results(
        self,
        tool_results: list[dict[str, Any]],
        system_context: Optional[str] = None,
        on_text: Optional[Callable[[str], None]] = None
    ) -> AssistantResponse:
        """Send tool execution results back to LM Studio."""
        # Track tool results in context manager
        for result in tool_results:
            tool_id = result.get("tool_use_id", "unknown")
            content = result.get("content", "")
            if isinstance(content, dict):
                content = json.dumps(content)
            self._context_manager.add_message("tool", content, tool_call_id=tool_id)

        system_prompt = self._build_system_prompt(system_context)
        messages = self._context_manager.get_messages()

        # Build tool result messages for the API (different format)
        tool_messages = build_chat_completions_tool_results(tool_results)

        try:
            if on_text:
                response = self._stream_request(messages + tool_messages, system_prompt, on_text)
            else:
                # Tools are required for tool results
                tools = convert_tools_for_chat_completions(self.tool_handler.get_all_tools())

                api_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system_prompt}] + messages + tool_messages,
                    tools=tools if tools else None,
                    max_tokens=self.max_tokens,
                )

                response = self._process_response(api_response.choices[0].message)

            # Track assistant response in context manager
            if response.text:
                self._context_manager.add_message("assistant", response.text)

            return response

        except LMStudioError:
            raise  # Already handled, re-raise
        except (APIError, APIConnectionError, RateLimitError, AuthenticationError, BadRequestError, APITimeoutError) as e:
            logger.error(f"LM Studio API error sending tool results [{type(e).__name__}]: {e}")
            raise handle_lmstudio_error(e)
        except Exception as e:
            logger.error(f"Unexpected LM Studio error sending tool results: {e}")
            raise handle_lmstudio_error(e)

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self._context_manager.clear()

    def get_history_summary(self) -> str:
        """Get a summary of the conversation history."""
        context_stats = self._context_manager.get_stats()

        if context_stats.message_count == 0 and not context_stats.has_summary:
            return "No conversation history."

        parts = [
            f"Messages: {context_stats.message_count}",
            f"Tool support: {'Yes' if self._tools_supported else 'No' if self._tools_supported is False else 'Unknown'}",
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

        return {
            "message_count": context_stats.message_count,
            "tools_supported": self._tools_supported,
            "provider": "lm_studio",
            "model": self.model,
            "token_usage": context_stats.total_tokens,
            "token_budget": context_stats.token_budget,
            "budget_used_percentage": context_stats.budget_used_percentage,
            "summarized_messages": context_stats.summarized_message_count,
            "has_summary": context_stats.has_summary,
        }
