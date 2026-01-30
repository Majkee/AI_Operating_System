"""Claude API integration and tool definitions.

DEPRECATED: For new code, use the aios.providers package instead.
This module is maintained for backward compatibility.

Example (new way):
    from aios.providers import create_client, BaseClient
    client = create_client(tool_handler)

Example (old way - deprecated):
    from aios.claude import ClaudeClient
    client = ClaudeClient(tool_handler)
"""

from .tools import TOOLS, ToolHandler


def __getattr__(name):
    """Lazy import to avoid circular imports."""
    if name == "ClaudeClient":
        from .client import ClaudeClient
        return ClaudeClient
    elif name == "AssistantResponse":
        from ..providers.base import AssistantResponse
        return AssistantResponse
    elif name == "create_client":
        from ..providers import create_client
        return create_client
    elif name == "BaseClient":
        from ..providers import BaseClient
        return BaseClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Legacy exports (deprecated)
    "ClaudeClient",
    "TOOLS",
    "ToolHandler",
    "AssistantResponse",
    # New exports (preferred)
    "create_client",
    "BaseClient",
]
