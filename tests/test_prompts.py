"""Tests for the centralized prompts management module."""

import pytest

from aios.prompts import (
    PromptSection,
    PromptManager,
    DEFAULT_SECTIONS,
    get_prompt_manager,
    reset_prompt_manager,
)
from aios.config import PromptsConfig


class TestPromptSection:
    """Test PromptSection dataclass."""

    def test_create_section(self):
        """Test creating a prompt section."""
        section = PromptSection(
            key="test",
            title="Test Section",
            content="This is test content."
        )
        assert section.key == "test"
        assert section.title == "Test Section"
        assert section.content == "This is test content."
        assert section.enabled is True  # Default

    def test_section_disabled(self):
        """Test creating a disabled section."""
        section = PromptSection(
            key="test",
            title="Test Section",
            content="This is test content.",
            enabled=False
        )
        assert section.enabled is False


class TestDefaultSections:
    """Test default prompt sections."""

    def test_default_sections_exist(self):
        """Test that default sections are defined."""
        assert len(DEFAULT_SECTIONS) > 0

    def test_default_sections_have_required_keys(self):
        """Test that all default sections have required fields."""
        required_keys = {
            "role", "communication", "safety", "tools", "errors",
            "user_decisions", "privacy", "context", "sudo", "timeouts",
            "background", "claude_code"
        }
        actual_keys = {s.key for s in DEFAULT_SECTIONS}
        assert required_keys == actual_keys

    def test_all_sections_have_content(self):
        """Test that all sections have non-empty content."""
        for section in DEFAULT_SECTIONS:
            assert section.key, "Section must have a key"
            assert section.title, "Section must have a title"
            assert section.content, "Section must have content"
            assert len(section.content) > 10, f"Section {section.key} has very short content"


class TestPromptManager:
    """Test PromptManager class."""

    def test_init_default(self):
        """Test initializing with defaults."""
        pm = PromptManager()
        assert len(pm.sections) == len(DEFAULT_SECTIONS)
        enabled, total = pm.get_enabled_count()
        assert enabled == total

    def test_init_with_config(self):
        """Test initializing with disabled sections config."""
        config = PromptsConfig(disabled_sections=["background", "claude_code"])
        pm = PromptManager(config)

        background = pm.get_section("background")
        assert background is not None
        assert background.enabled is False

        claude_code = pm.get_section("claude_code")
        assert claude_code is not None
        assert claude_code.enabled is False

        # Other sections should still be enabled
        role = pm.get_section("role")
        assert role is not None
        assert role.enabled is True

    def test_build_prompt_basic(self):
        """Test building a basic prompt."""
        pm = PromptManager()
        prompt = pm.build_prompt()

        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "AIOS" in prompt
        assert "Your Role" in prompt

    def test_build_prompt_with_context(self):
        """Test building prompt with system context."""
        pm = PromptManager()
        prompt = pm.build_prompt(system_context="OS: Linux")

        assert "Current System Context" in prompt
        assert "OS: Linux" in prompt

    def test_build_prompt_with_summary(self):
        """Test building prompt with conversation summary."""
        pm = PromptManager()
        prompt = pm.build_prompt(summary="User asked about files")

        assert "Earlier Conversation Summary" in prompt
        assert "User asked about files" in prompt

    def test_build_prompt_excludes_disabled(self):
        """Test that disabled sections are excluded from prompt."""
        config = PromptsConfig(disabled_sections=["claude_code"])
        pm = PromptManager(config)
        prompt = pm.build_prompt()

        # The claude_code section content should not be in the prompt
        assert "Claude Code Integration" not in prompt
        # But other sections should be present
        assert "Your Role" in prompt

    def test_list_sections(self):
        """Test listing all sections."""
        pm = PromptManager()
        sections = pm.list_sections()

        assert len(sections) == len(DEFAULT_SECTIONS)
        for section in sections:
            assert isinstance(section, PromptSection)

    def test_get_section_exists(self):
        """Test getting an existing section."""
        pm = PromptManager()
        section = pm.get_section("role")

        assert section is not None
        assert section.key == "role"
        assert section.title == "Role Definition"

    def test_get_section_not_exists(self):
        """Test getting a non-existent section."""
        pm = PromptManager()
        section = pm.get_section("nonexistent")

        assert section is None

    def test_enable_section(self):
        """Test enabling a section."""
        config = PromptsConfig(disabled_sections=["background"])
        pm = PromptManager(config)

        # Should be disabled initially
        section = pm.get_section("background")
        assert section.enabled is False

        # Enable it
        result = pm.enable_section("background")
        assert result is True
        assert section.enabled is True

    def test_enable_nonexistent_section(self):
        """Test enabling a non-existent section."""
        pm = PromptManager()
        result = pm.enable_section("nonexistent")
        assert result is False

    def test_disable_section(self):
        """Test disabling a section."""
        pm = PromptManager()

        # Should be enabled initially
        section = pm.get_section("background")
        assert section.enabled is True

        # Disable it
        result = pm.disable_section("background")
        assert result is True
        assert section.enabled is False

    def test_disable_nonexistent_section(self):
        """Test disabling a non-existent section."""
        pm = PromptManager()
        result = pm.disable_section("nonexistent")
        assert result is False

    def test_reset(self):
        """Test resetting all sections to defaults."""
        config = PromptsConfig(disabled_sections=["background", "claude_code", "timeouts"])
        pm = PromptManager(config)

        # Verify some are disabled
        enabled_before, total = pm.get_enabled_count()
        assert enabled_before < total

        # Reset
        pm.reset()

        # All should be enabled now
        enabled_after, total = pm.get_enabled_count()
        assert enabled_after == total

    def test_get_enabled_count(self):
        """Test getting enabled/total count."""
        config = PromptsConfig(disabled_sections=["background", "claude_code"])
        pm = PromptManager(config)

        enabled, total = pm.get_enabled_count()
        assert enabled == total - 2

    def test_get_disabled_keys(self):
        """Test getting list of disabled section keys."""
        config = PromptsConfig(disabled_sections=["background", "claude_code"])
        pm = PromptManager(config)

        disabled = pm.get_disabled_keys()
        assert set(disabled) == {"background", "claude_code"}

    def test_get_disabled_keys_empty(self):
        """Test getting disabled keys when none are disabled."""
        pm = PromptManager()
        disabled = pm.get_disabled_keys()
        assert disabled == []


class TestGlobalPromptManager:
    """Test global prompt manager functions."""

    def test_get_prompt_manager_returns_instance(self):
        """Test that get_prompt_manager returns a PromptManager."""
        reset_prompt_manager()  # Start fresh
        pm = get_prompt_manager()
        assert isinstance(pm, PromptManager)

    def test_get_prompt_manager_singleton(self):
        """Test that get_prompt_manager returns the same instance."""
        reset_prompt_manager()  # Start fresh
        pm1 = get_prompt_manager()
        pm2 = get_prompt_manager()
        assert pm1 is pm2

    def test_reset_prompt_manager(self):
        """Test that reset_prompt_manager clears the instance."""
        pm1 = get_prompt_manager()
        reset_prompt_manager()
        pm2 = get_prompt_manager()
        # After reset, should be a new instance
        assert pm1 is not pm2


class TestPromptIntegration:
    """Integration tests for prompt system."""

    def test_prompt_contains_all_critical_sections(self):
        """Test that prompt contains critical behavior sections."""
        pm = PromptManager()
        prompt = pm.build_prompt()

        # Critical sections that must be present
        assert "Safety First" in prompt or "safety" in prompt.lower()
        assert "USER DECLINED" in prompt  # User decision handling
        assert "Privacy" in prompt or "privacy" in prompt.lower()

    def test_prompt_provider_agnostic(self):
        """Test that prompts work for all providers."""
        pm = PromptManager()

        # All providers should get the same base prompt
        anthropic_prompt = pm.build_prompt(provider="anthropic")
        openai_prompt = pm.build_prompt(provider="openai")
        lmstudio_prompt = pm.build_prompt(provider="lm_studio")

        # Currently all providers use the same prompt structure
        assert anthropic_prompt == openai_prompt == lmstudio_prompt

    def test_prompt_token_estimate(self):
        """Test that prompt stays within reasonable token limits."""
        pm = PromptManager()
        prompt = pm.build_prompt()

        # Rough estimate: 4 chars per token
        estimated_tokens = len(prompt) // 4

        # Prompt should be under 10k tokens (leaving room for conversation)
        assert estimated_tokens < 10000, f"Prompt too large: ~{estimated_tokens} tokens"
