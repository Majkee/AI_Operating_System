"""
Claude API client for AIOS.

Handles communication with the Anthropic API and processes
tool calls from Claude's responses.
"""

from typing import Any, Optional
from dataclasses import dataclass, field

import anthropic
from anthropic.types import Message, ToolUseBlock, TextBlock

from .tools import ToolHandler, ToolResult
from ..config import get_config


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
- Prefer foreground (long_running: true) when the user wants to see progress"""


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

    def _build_messages(self, user_input: str) -> list[dict]:
        """Build the messages list for the API call."""
        messages = self.conversation_history.copy()
        messages.append({"role": "user", "content": user_input})
        return messages

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
        system_context: Optional[str] = None
    ) -> AssistantResponse:
        """Send a message to Claude and get a response."""
        messages = self._build_messages(user_input)

        # Build system prompt with optional context
        system = SYSTEM_PROMPT
        if system_context:
            system = f"{SYSTEM_PROMPT}\n\n## Current System Context\n{system_context}"

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=self.tool_handler.get_all_tools(),
            messages=messages
        )

        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_input
        })

        # Process and store assistant response
        assistant_response = self._process_response(response)

        # Build assistant message content for history
        assistant_content = []
        if assistant_response.text:
            assistant_content.append({
                "type": "text",
                "text": assistant_response.text
            })
        for tool_call in assistant_response.tool_calls:
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

        return assistant_response

    def send_tool_results(
        self,
        tool_results: list[dict[str, Any]],
        system_context: Optional[str] = None
    ) -> AssistantResponse:
        """Send tool execution results back to Claude."""
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

        # Build system prompt
        system = SYSTEM_PROMPT
        if system_context:
            system = f"{SYSTEM_PROMPT}\n\n## Current System Context\n{system_context}"

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=self.tool_handler.get_all_tools(),
            messages=self.conversation_history
        )

        assistant_response = self._process_response(response)

        # Store assistant response
        assistant_content = []
        if assistant_response.text:
            assistant_content.append({
                "type": "text",
                "text": assistant_response.text
            })
        for tool_call in assistant_response.tool_calls:
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

        return assistant_response

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self.conversation_history = []

    def get_history_summary(self) -> str:
        """Get a summary of the conversation history."""
        if not self.conversation_history:
            return "No conversation history."

        summary_parts = []
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
