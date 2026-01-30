"""
Multi-provider LLM support for AIOS.

This package provides an abstract interface for different LLM providers
(Anthropic, OpenAI, LM Studio) with a unified API.
"""

from .base import BaseClient, AssistantResponse
from .factory import create_client, get_provider_name
from .anthropic_client import AnthropicClient
from .openai_client import OpenAIClient, OpenAIError
from .lmstudio_client import LMStudioClient, LMStudioError

__all__ = [
    "BaseClient",
    "AssistantResponse",
    "create_client",
    "get_provider_name",
    "AnthropicClient",
    "OpenAIClient",
    "OpenAIError",
    "LMStudioClient",
    "LMStudioError",
]
