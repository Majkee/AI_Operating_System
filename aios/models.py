"""
Available LLM models for AIOS.

This module provides a list of available models from different providers
(Anthropic, OpenAI, LM Studio) with their descriptions and metadata
to help users choose the right model for their needs.
"""

from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "ModelInfo",
    "AVAILABLE_MODELS",
    "ANTHROPIC_MODELS",
    "OPENAI_MODELS",
    "LM_STUDIO_MODELS",
    "get_model_by_id",
    "list_models",
    "get_models_by_provider",
    "get_default_model",
    "get_default_model_for_provider",
    "is_gpt5_model",
    "is_reasoning_model",
    "is_small_model",
    "supports_verbosity",
]


@dataclass
class ModelInfo:
    """Information about an LLM model."""
    id: str
    name: str
    description: str
    speed: str  # "fast", "medium", "slow"
    cost: str  # "low", "medium", "high", "free"
    use_cases: list[str] = field(default_factory=list)
    provider: str = "anthropic"  # "anthropic", "openai", "lm_studio"
    note: Optional[str] = None  # Warning or note about model limitations


# Available Anthropic Claude models
ANTHROPIC_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="claude-haiku-4-5",
        name="Claude Haiku 4.5",
        description="Latest small model - fastest and most cost-efficient",
        speed="fast",
        cost="low",
        provider="anthropic",
        use_cases=[
            "Real-time, low-latency applications",
            "Multi-agent systems",
            "Budget-conscious applications",
            "Quick responses and simple tasks"
        ]
    ),
    ModelInfo(
        id="claude-sonnet-4-5-20250929",
        name="Claude Sonnet 4.5",
        description="Balanced performance and speed - recommended for most tasks",
        speed="medium",
        cost="medium",
        provider="anthropic",
        use_cases=[
            "General-purpose tasks",
            "Complex reasoning",
            "Code generation and analysis",
            "Balanced performance needs"
        ]
    ),
    ModelInfo(
        id="claude-opus-4-20250514",
        name="Claude Opus 4",
        description="Most capable model - best for complex tasks",
        speed="slow",
        cost="high",
        provider="anthropic",
        use_cases=[
            "Complex problem solving",
            "Advanced code generation",
            "Deep analysis and research",
            "Maximum capability needs"
        ]
    ),
]

# Available OpenAI GPT models (GPT-5.2 family - latest)
OPENAI_MODELS: list[ModelInfo] = [
    # GPT-5.2 Family (Latest flagship models)
    ModelInfo(
        id="gpt-5.2",
        name="GPT-5.2",
        description="Best general-purpose model for complex reasoning and agentic tasks",
        speed="medium",
        cost="high",
        provider="openai",
        use_cases=[
            "Complex reasoning",
            "Multi-step agentic tasks",
            "Code generation",
            "Broad world knowledge"
        ]
    ),
    ModelInfo(
        id="gpt-5.2-pro",
        name="GPT-5.2 Pro",
        description="Uses more compute for tough problems requiring harder thinking",
        speed="slow",
        cost="high",
        provider="openai",
        use_cases=[
            "Hard problems",
            "Deep analysis",
            "Research tasks",
            "Extended reasoning"
        ]
    ),
    ModelInfo(
        id="gpt-5.2-codex",
        name="GPT-5.2 Codex",
        description="Coding-optimized for agentic workflows and development tasks",
        speed="medium",
        cost="high",
        provider="openai",
        use_cases=[
            "Agentic coding",
            "Full-spectrum coding tasks",
            "Interactive development",
            "Code review and debugging"
        ]
    ),
    ModelInfo(
        id="gpt-5-mini",
        name="GPT-5 Mini",
        description="Cost-optimized reasoning and chat - balances speed, cost, and capability",
        speed="fast",
        cost="medium",
        provider="openai",
        use_cases=[
            "General chat",
            "Quick reasoning tasks",
            "Cost-sensitive applications",
            "Balanced performance"
        ],
        note="⚠️ Smaller model - may not use tools reliably (no progress bars, simplified confirmations)"
    ),
    ModelInfo(
        id="gpt-5-nano",
        name="GPT-5 Nano",
        description="High-throughput for simple instruction-following or classification",
        speed="fast",
        cost="low",
        provider="openai",
        use_cases=[
            "Simple tasks",
            "Classification",
            "High volume requests",
            "Low latency needs"
        ],
        note="⚠️ Smallest model - limited tool usage, best for simple Q&A only"
    ),
    # Legacy models (still supported)
    ModelInfo(
        id="gpt-4o",
        name="GPT-4o (Legacy)",
        description="Previous flagship model - consider upgrading to GPT-5.2",
        speed="medium",
        cost="medium",
        provider="openai",
        use_cases=[
            "Complex reasoning",
            "Multi-step tasks",
            "Code generation",
            "Broad knowledge tasks"
        ]
    ),
    ModelInfo(
        id="gpt-4o-mini",
        name="GPT-4o Mini (Legacy)",
        description="Previous cost-optimized model - consider upgrading to GPT-5 Mini",
        speed="fast",
        cost="low",
        provider="openai",
        use_cases=[
            "General chat",
            "Quick tasks",
            "Cost-sensitive applications",
            "Balanced performance"
        ],
        note="⚠️ Smaller model - may not use tools reliably (no progress bars, simplified confirmations)"
    ),
]

# LM Studio local models
LM_STUDIO_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
        name="Qwen 2.5 Coder 7B",
        description="Local coding model via LM Studio",
        speed="fast",
        cost="free",
        provider="lm_studio",
        use_cases=[
            "Local/private coding",
            "Offline use",
            "Code assistance",
            "Privacy-focused tasks"
        ],
        note="⚠️ Local model - limited tool usage, may not follow AIOS workflows correctly"
    ),
    ModelInfo(
        id="lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF",
        name="Llama 3.1 8B",
        description="Local general-purpose model",
        speed="fast",
        cost="free",
        provider="lm_studio",
        use_cases=[
            "General chat",
            "Local/private use",
            "Offline assistance",
            "Privacy-focused tasks"
        ],
        note="⚠️ Local model - limited tool usage, may not follow AIOS workflows correctly"
    ),
]

# Combined list of all available models
AVAILABLE_MODELS: list[ModelInfo] = ANTHROPIC_MODELS + OPENAI_MODELS + LM_STUDIO_MODELS


def get_model_by_id(model_id: str) -> Optional[ModelInfo]:
    """Get model information by ID."""
    for model in AVAILABLE_MODELS:
        if model.id == model_id:
            return model
    return None


def list_models() -> list[ModelInfo]:
    """Get list of all available models."""
    return AVAILABLE_MODELS.copy()


def get_models_by_provider(provider: str) -> list[ModelInfo]:
    """Get list of models for a specific provider.

    Args:
        provider: Provider name (anthropic, openai, lm_studio)

    Returns:
        List of models for that provider
    """
    provider = provider.lower()
    return [m for m in AVAILABLE_MODELS if m.provider == provider]


def get_default_model() -> str:
    """Get the default model ID (Anthropic Claude Sonnet)."""
    return "claude-sonnet-4-5-20250929"


def get_default_model_for_provider(provider: str) -> str:
    """Get the default model ID for a specific provider.

    Args:
        provider: Provider name (anthropic, openai, lm_studio)

    Returns:
        Default model ID for that provider
    """
    provider = provider.lower()
    defaults = {
        "anthropic": "claude-sonnet-4-5-20250929",
        "openai": "gpt-5.2",  # Latest GPT-5.2 family flagship
        "lm_studio": "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
    }
    return defaults.get(provider, "claude-sonnet-4-5-20250929")


def is_gpt5_model(model_id: str) -> bool:
    """Check if the model is a GPT-5.x family model.

    GPT-5.x models support advanced features like reasoning effort and verbosity.

    Args:
        model_id: The model ID to check

    Returns:
        True if this is a GPT-5.x family model
    """
    return model_id.startswith("gpt-5")


def is_reasoning_model(model_id: str) -> bool:
    """Check if the model supports reasoning effort parameter.

    Models that support reasoning:
    - GPT-5.x family (gpt-5.2, gpt-5.2-pro, gpt-5-mini, etc.)
    - o-series models (o1, o3, o3-mini, o4-mini, etc.)

    Args:
        model_id: The model ID to check

    Returns:
        True if this model supports reasoning effort
    """
    # GPT-5.x family
    if model_id.startswith("gpt-5"):
        return True
    # o-series reasoning models (o1, o3, o3-mini, o4-mini, etc.)
    if model_id.startswith("o1") or model_id.startswith("o3") or model_id.startswith("o4"):
        return True
    return False


def supports_verbosity(model_id: str) -> bool:
    """Check if the model supports verbosity parameter.

    Currently only GPT-5.x models support the verbosity parameter.

    Args:
        model_id: The model ID to check

    Returns:
        True if this model supports verbosity
    """
    return model_id.startswith("gpt-5")


def is_small_model(model_id: str) -> bool:
    """Check if this is a smaller model with limited tool usage capabilities.

    Smaller models may not reliably:
    - Use tools when they should (outputting text instead)
    - Set optional parameters like long_running, requires_confirmation
    - Follow complex multi-step workflows

    Args:
        model_id: The model ID to check

    Returns:
        True if this model has known limitations for AIOS workflows
    """
    model = get_model_by_id(model_id)
    if model and model.note:
        return True
    # Also check by pattern for unknown models
    small_patterns = ["mini", "nano", "small", "tiny", "7b", "8b", "3b"]
    model_lower = model_id.lower()
    return any(p in model_lower for p in small_patterns)
