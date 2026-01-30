"""
Centralized prompt management for AIOS.

Provides a single source of truth for all LLM provider system prompts
with configurable sections that can be enabled/disabled.
"""

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import PromptsConfig


@dataclass
class PromptSection:
    """A configurable section of the system prompt."""
    key: str                    # Unique identifier (role, communication, safety, etc.)
    title: str                  # Display name
    content: str                # Prompt text
    enabled: bool = True        # Whether section is active


# Default prompt sections - these form the complete system prompt
DEFAULT_SECTIONS = [
    PromptSection(
        key="role",
        title="Role Definition",
        content="""You are AIOS, a friendly AI assistant that helps users interact with their Linux computer through natural conversation.

## Your Role
- You help non-technical users accomplish tasks on their computer
- You translate their requests into appropriate system actions
- You explain what you're doing in simple, friendly language
- You protect users from accidentally harmful actions"""
    ),
    PromptSection(
        key="communication",
        title="Communication Style",
        content="""## Communication Style
- Use simple, non-technical language
- Avoid jargon - if you must use a technical term, explain it
- Be encouraging and patient
- Provide helpful context about what you're doing
- Use emojis to make responses friendly and approachable"""
    ),
    PromptSection(
        key="safety",
        title="Safety Guidelines",
        content="""## Safety First
- Always explain what an action will do before executing it
- For any action that modifies files or system settings, get confirmation
- Never execute potentially destructive commands without explicit confirmation
- If something could go wrong, warn the user first"""
    ),
    PromptSection(
        key="tools",
        title="Tool Usage Guidelines",
        content="""## When Using Tools
- Always provide clear explanations of what each tool does
- Group related actions together when possible
- If a request is ambiguous, ask for clarification
- Present file listings and search results in a user-friendly format"""
    ),
    PromptSection(
        key="errors",
        title="Error Handling",
        content="""## Error Handling
- If something fails, explain what went wrong in simple terms
- Suggest alternatives or solutions when possible
- Never blame the user for errors"""
    ),
    PromptSection(
        key="user_decisions",
        title="Respecting User Decisions",
        content="""## Respecting User Decisions
- CRITICAL: When a tool result contains "USER DECLINED", the user explicitly refused the action
- Do NOT retry the same operation through alternative tools or methods
- Do NOT attempt workarounds like using run_command instead of manage_application
- Simply acknowledge their decision and ask if they need help with something else
- User refusal is final - respect it completely"""
    ),
    PromptSection(
        key="privacy",
        title="Privacy & Security",
        content="""## Privacy & Security
- Don't read files unless necessary for the user's request
- Don't expose sensitive information (passwords, keys) in output
- Respect user privacy - only access what's needed"""
    ),
    PromptSection(
        key="context",
        title="System Context",
        content="""## Context
You have access to the user's home directory and can help with:
- Finding and organizing files
- Installing and managing applications
- Viewing system information
- Creating and editing documents
- Basic system maintenance

Remember: Your goal is to make Linux accessible and friendly for everyone!"""
    ),
    PromptSection(
        key="sudo",
        title="Sudo and Privileges",
        content="""## Sudo and Elevated Privileges
This system runs as a non-root user with passwordless sudo.
- System commands (apt-get, dpkg, systemctl, service) REQUIRE `use_sudo: true` in run_command
- User-space commands (ls, cat, wget to home dirs, find) do NOT need sudo
- The manage_application tool handles sudo automatically; run_command does not"""
    ),
    PromptSection(
        key="timeouts",
        title="Timeouts and Long-Running Operations",
        content="""## Timeouts and Long-Running Operations
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
3. Warn user that large operations may take several minutes"""
    ),
    PromptSection(
        key="background",
        title="Background Tasks",
        content="""## Background Tasks
- Set `background: true` in run_command for tasks the user does not need to watch
- Background tasks have no timeout and run until completion
- The user can view background tasks with Ctrl+B or the 'tasks' command
- Use background for: server processes, very large downloads, unattended builds
- Prefer foreground (long_running: true) when the user wants to see progress"""
    ),
    PromptSection(
        key="claude_code",
        title="Claude Code Integration",
        content="""## Claude Code Integration
- When the user asks you to write code, build applications, or do complex coding work, suggest the 'code' command
- Typing 'code' launches an interactive Claude Code session where the user works directly with the coding agent
- Example: "For this task, I recommend launching Claude Code: just type 'code' or 'code build a Flask REST API'"
- Claude Code is a specialized coding agent that can read, write, edit files, run commands, and search code
- Simple code questions or small snippets can be answered directly without Claude Code"""
    ),
]


class PromptManager:
    """Manages system prompts for all LLM providers.

    Provides a centralized way to build and customize system prompts
    with configurable sections that can be enabled/disabled.
    """

    def __init__(self, config: Optional["PromptsConfig"] = None):
        """Initialize the prompt manager.

        Args:
            config: Optional prompts configuration with disabled sections.
        """
        # Create a deep copy of default sections
        self.sections = [
            PromptSection(
                key=s.key,
                title=s.title,
                content=s.content,
                enabled=s.enabled
            )
            for s in DEFAULT_SECTIONS
        ]

        # Apply configuration if provided
        if config:
            self._apply_config(config)

    def _apply_config(self, config: "PromptsConfig") -> None:
        """Apply configuration to sections."""
        disabled = set(config.disabled_sections)
        for section in self.sections:
            if section.key in disabled:
                section.enabled = False

    def build_prompt(
        self,
        provider: str = "anthropic",
        system_context: Optional[str] = None,
        summary: Optional[str] = None
    ) -> str:
        """Build complete system prompt for a provider.

        Args:
            provider: LLM provider name (anthropic, openai, lm_studio)
            system_context: Optional current system context to include
            summary: Optional conversation summary to include

        Returns:
            Complete system prompt string
        """
        # Gather enabled sections
        parts = [s.content for s in self.sections if s.enabled]
        prompt = "\n\n".join(parts)

        # Add conversation summary if available
        if summary:
            prompt += f"\n\n## Earlier Conversation Summary\n{summary}"

        # Add system context if available
        if system_context:
            prompt += f"\n\n## Current System Context\n{system_context}"

        return prompt

    def list_sections(self) -> list[PromptSection]:
        """List all sections.

        Returns:
            List of all prompt sections
        """
        return self.sections

    def get_section(self, key: str) -> Optional[PromptSection]:
        """Get a section by key.

        Args:
            key: Section key to find

        Returns:
            PromptSection if found, None otherwise
        """
        for section in self.sections:
            if section.key == key:
                return section
        return None

    def enable_section(self, key: str) -> bool:
        """Enable a section by key.

        Args:
            key: Section key to enable

        Returns:
            True if section was found and enabled, False otherwise
        """
        section = self.get_section(key)
        if section:
            section.enabled = True
            return True
        return False

    def disable_section(self, key: str) -> bool:
        """Disable a section by key.

        Args:
            key: Section key to disable

        Returns:
            True if section was found and disabled, False otherwise
        """
        section = self.get_section(key)
        if section:
            section.enabled = False
            return True
        return False

    def reset(self) -> None:
        """Reset all sections to default enabled state."""
        for section in self.sections:
            section.enabled = True

    def get_enabled_count(self) -> tuple[int, int]:
        """Get count of enabled sections and total sections.

        Returns:
            Tuple of (enabled_count, total_count)
        """
        enabled = sum(1 for s in self.sections if s.enabled)
        return enabled, len(self.sections)

    def get_disabled_keys(self) -> list[str]:
        """Get list of disabled section keys.

        Returns:
            List of keys for disabled sections
        """
        return [s.key for s in self.sections if not s.enabled]


# Global prompt manager instance (lazy initialization)
_prompt_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    """Get the global prompt manager instance.

    Creates a new instance with configuration on first call.

    Returns:
        Global PromptManager instance
    """
    global _prompt_manager
    if _prompt_manager is None:
        from .config import get_config
        config = get_config()
        prompts_config = getattr(config, 'prompts', None)
        _prompt_manager = PromptManager(prompts_config)
    return _prompt_manager


def reset_prompt_manager() -> None:
    """Reset the global prompt manager (useful for testing or reloading config)."""
    global _prompt_manager
    _prompt_manager = None
