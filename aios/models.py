"""
Available Anthropic Claude models for AIOS.

This module provides a list of available models with their descriptions
and metadata to help users choose the right model for their needs.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelInfo:
    """Information about an Anthropic model."""
    id: str
    name: str
    description: str
    speed: str  # "fast", "medium", "slow"
    cost: str  # "low", "medium", "high"
    use_cases: list[str]


# Available Anthropic models
AVAILABLE_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="claude-haiku-4-5",
        name="Claude Haiku 4.5",
        description="Latest small model - fastest and most cost-efficient",
        speed="fast",
        cost="low",
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
        use_cases=[
            "Complex problem solving",
            "Advanced code generation",
            "Deep analysis and research",
            "Maximum capability needs"
        ]
    ),
]


def get_model_by_id(model_id: str) -> Optional[ModelInfo]:
    """Get model information by ID."""
    for model in AVAILABLE_MODELS:
        if model.id == model_id:
            return model
    return None


def list_models() -> list[ModelInfo]:
    """Get list of all available models."""
    return AVAILABLE_MODELS.copy()


def get_default_model() -> str:
    """Get the default model ID."""
    return "claude-sonnet-4-5-20250929"
