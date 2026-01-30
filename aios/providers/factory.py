"""
Provider factory for creating LLM clients.

Creates the appropriate client based on configuration settings,
supporting Anthropic, OpenAI, and LM Studio providers.
"""

import logging
from typing import Optional

from .base import BaseClient
from .anthropic_client import AnthropicClient
from .openai_client import OpenAIClient
from .lmstudio_client import LMStudioClient
from ..claude.tools import ToolHandler
from ..config import get_config

logger = logging.getLogger(__name__)


def create_client(
    tool_handler: Optional[ToolHandler] = None,
    provider: Optional[str] = None
) -> BaseClient:
    """Create the appropriate LLM client based on configuration.

    Args:
        tool_handler: Optional ToolHandler to pass to the client
        provider: Optional provider override (defaults to config value)

    Returns:
        A BaseClient implementation for the specified provider

    Raises:
        ValueError: If the provider is unknown or misconfigured
    """
    config = get_config()

    # Get provider from argument, config, or default
    if provider is None:
        provider = getattr(config.api, 'provider', 'anthropic')

    provider = provider.lower()

    logger.info(f"Creating LLM client for provider: {provider}")

    if provider == "anthropic":
        return AnthropicClient(tool_handler)

    elif provider == "openai":
        return OpenAIClient(tool_handler)

    elif provider in ("lm_studio", "lmstudio", "local"):
        return LMStudioClient(tool_handler)

    else:
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Supported providers: anthropic, openai, lm_studio"
        )


def get_provider_name(client: BaseClient) -> str:
    """Get the provider name for a client instance.

    Args:
        client: A BaseClient implementation

    Returns:
        The provider name string
    """
    if isinstance(client, AnthropicClient):
        return "anthropic"
    elif isinstance(client, OpenAIClient):
        return "openai"
    elif isinstance(client, LMStudioClient):
        return "lm_studio"
    else:
        return "unknown"
