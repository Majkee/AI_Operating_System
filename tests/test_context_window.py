"""Tests for conversation context window management."""

import pytest
from unittest.mock import Mock, MagicMock, patch

from aios.claude.client import (
    ClaudeClient,
    estimate_tokens,
    estimate_message_tokens,
    estimate_history_tokens,
    DEFAULT_CONTEXT_BUDGET,
    SUMMARIZE_THRESHOLD,
    MIN_RECENT_MESSAGES,
    CHARS_PER_TOKEN,
)


class TestTokenEstimation:
    """Test token estimation functions."""

    def test_estimate_tokens_empty(self):
        """Empty string should return minimum 1 token."""
        assert estimate_tokens("") == 1

    def test_estimate_tokens_short(self):
        """Short text estimation."""
        # "Hello" = 5 chars, should be ~1-2 tokens
        result = estimate_tokens("Hello")
        assert result >= 1

    def test_estimate_tokens_longer(self):
        """Longer text scales with length."""
        short = estimate_tokens("Hi")
        long = estimate_tokens("Hello, this is a much longer message with more content")
        assert long > short

    def test_estimate_message_tokens_string_content(self):
        """Message with string content."""
        msg = {"role": "user", "content": "Hello world"}
        tokens = estimate_message_tokens(msg)
        assert tokens > 0

    def test_estimate_message_tokens_text_block(self):
        """Message with text block list."""
        msg = {
            "role": "assistant",
            "content": [{"type": "text", "text": "Here is my response"}]
        }
        tokens = estimate_message_tokens(msg)
        assert tokens > 0

    def test_estimate_message_tokens_tool_use(self):
        """Message with tool use block."""
        msg = {
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": "tool_123",
                "name": "run_command",
                "input": {"command": "ls -la"}
            }]
        }
        tokens = estimate_message_tokens(msg)
        assert tokens > 0

    def test_estimate_message_tokens_tool_result(self):
        """Message with tool result."""
        msg = {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": "tool_123",
                "content": "file1.txt\nfile2.txt"
            }]
        }
        tokens = estimate_message_tokens(msg)
        assert tokens > 0

    def test_estimate_history_tokens_empty(self):
        """Empty history has 0 tokens."""
        assert estimate_history_tokens([]) == 0

    def test_estimate_history_tokens_multiple(self):
        """Multiple messages sum correctly."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]
        tokens = estimate_history_tokens(messages)
        individual = sum(estimate_message_tokens(m) for m in messages)
        assert tokens == individual


class TestContextWindowManagement:
    """Test context window management in ClaudeClient."""

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_client_initializes_context_fields(self, mock_anthropic, mock_get_config):
        """Client initializes context management fields."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 100000
        mock_config.api.summarize_threshold = 0.8
        mock_config.api.min_recent_messages = 8
        mock_get_config.return_value = mock_config

        client = ClaudeClient()

        assert client.context_budget == 100000
        assert client.summarize_threshold == 0.8
        assert client.min_recent_messages == 8
        assert client._conversation_summary is None
        assert client._summarized_message_count == 0

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_client_uses_default_thresholds(self, mock_anthropic, mock_get_config):
        """Client falls back to defaults when config values missing."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        # Don't set context_budget, summarize_threshold, min_recent_messages
        del mock_config.api.context_budget
        del mock_config.api.summarize_threshold
        del mock_config.api.min_recent_messages
        mock_get_config.return_value = mock_config

        client = ClaudeClient()

        assert client.context_budget == DEFAULT_CONTEXT_BUDGET
        assert client.summarize_threshold == SUMMARIZE_THRESHOLD
        assert client.min_recent_messages == MIN_RECENT_MESSAGES

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_get_context_usage(self, mock_anthropic, mock_get_config):
        """Test context usage calculation."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 1000
        mock_config.api.summarize_threshold = SUMMARIZE_THRESHOLD
        mock_config.api.min_recent_messages = MIN_RECENT_MESSAGES
        mock_get_config.return_value = mock_config

        client = ClaudeClient()
        client.conversation_history = [
            {"role": "user", "content": "x" * 400},  # ~100 tokens
        ]

        tokens, percentage = client._get_context_usage()
        assert tokens > 0
        assert 0 < percentage < 1

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_needs_summarization_false_when_under_threshold(self, mock_anthropic, mock_get_config):
        """No summarization needed when under threshold."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 100000
        mock_config.api.summarize_threshold = SUMMARIZE_THRESHOLD
        mock_config.api.min_recent_messages = MIN_RECENT_MESSAGES
        mock_get_config.return_value = mock_config

        client = ClaudeClient()
        client.conversation_history = [
            {"role": "user", "content": "Hello"},
        ]

        assert not client._needs_summarization()

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_needs_summarization_true_when_over_threshold(self, mock_anthropic, mock_get_config):
        """Summarization needed when over threshold."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 100  # Very small budget
        mock_config.api.summarize_threshold = SUMMARIZE_THRESHOLD
        mock_config.api.min_recent_messages = MIN_RECENT_MESSAGES
        mock_get_config.return_value = mock_config

        client = ClaudeClient()
        # Add enough messages to exceed 75% of 100 tokens
        client.conversation_history = [
            {"role": "user", "content": "x" * 400},  # ~100 tokens, well over budget
        ]

        assert client._needs_summarization()

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_clear_history_clears_summary(self, mock_anthropic, mock_get_config):
        """Clear history also clears summary state."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 100000
        mock_config.api.summarize_threshold = SUMMARIZE_THRESHOLD
        mock_config.api.min_recent_messages = MIN_RECENT_MESSAGES
        mock_get_config.return_value = mock_config

        client = ClaudeClient()
        client.conversation_history = [{"role": "user", "content": "test"}]
        client._conversation_summary = "Previous summary"
        client._summarized_message_count = 10

        client.clear_history()

        assert client.conversation_history == []
        assert client._conversation_summary is None
        assert client._summarized_message_count == 0

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_get_context_stats(self, mock_anthropic, mock_get_config):
        """Test context stats method."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 100000
        mock_config.api.summarize_threshold = SUMMARIZE_THRESHOLD
        mock_config.api.min_recent_messages = MIN_RECENT_MESSAGES
        mock_get_config.return_value = mock_config

        client = ClaudeClient()
        client.conversation_history = [{"role": "user", "content": "test"}]
        client._summarized_message_count = 5

        stats = client.get_context_stats()

        assert "tokens_used" in stats
        assert "token_budget" in stats
        assert "usage_percentage" in stats
        assert "active_messages" in stats
        assert stats["active_messages"] == 1
        assert stats["summarized_messages"] == 5
        assert stats["has_summary"] is False


class TestSummarization:
    """Test conversation summarization."""

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_format_messages_for_summary(self, mock_anthropic, mock_get_config):
        """Test message formatting for summarization."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 100000
        mock_config.api.summarize_threshold = SUMMARIZE_THRESHOLD
        mock_config.api.min_recent_messages = MIN_RECENT_MESSAGES
        mock_get_config.return_value = mock_config

        client = ClaudeClient()

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        formatted = client._format_messages_for_summary(messages)

        assert "USER: Hello" in formatted
        assert "ASSISTANT: Hi there!" in formatted

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_summarize_history_keeps_recent_messages(self, mock_anthropic, mock_get_config):
        """Summarization keeps recent messages intact."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 100000
        mock_config.api.summarize_threshold = SUMMARIZE_THRESHOLD
        mock_config.api.min_recent_messages = 6  # Explicit value for test
        mock_get_config.return_value = mock_config

        # Create mock for the API client
        mock_api_client = Mock()
        mock_text_block = Mock()
        mock_text_block.text = "Summary of conversation"
        # Make it pass isinstance check
        type(mock_text_block).__name__ = 'TextBlock'
        mock_response = Mock()
        mock_response.content = [mock_text_block]
        mock_api_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_api_client

        client = ClaudeClient()

        # Add 10 messages
        client.conversation_history = [
            {"role": "user", "content": f"Message {i}"} for i in range(10)
        ]

        client._summarize_history()

        # Should keep min_recent_messages (configured as 6)
        assert len(client.conversation_history) == 6
        # Last messages should be preserved
        assert client.conversation_history[-1]["content"] == "Message 9"

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_summarize_history_sets_summary(self, mock_anthropic, mock_get_config):
        """Summarization creates and stores summary."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 100000
        mock_config.api.summarize_threshold = SUMMARIZE_THRESHOLD
        mock_config.api.min_recent_messages = MIN_RECENT_MESSAGES
        mock_get_config.return_value = mock_config

        # Create mock for the API client
        mock_api_client = Mock()
        mock_text_block = Mock()
        mock_text_block.text = "This is the summary"
        # Make it pass isinstance check
        type(mock_text_block).__name__ = 'TextBlock'
        mock_response = Mock()
        mock_response.content = [mock_text_block]
        mock_api_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_api_client

        client = ClaudeClient()
        client.conversation_history = [
            {"role": "user", "content": f"Message {i}"} for i in range(10)
        ]

        client._summarize_history()

        assert client._conversation_summary == "This is the summary"
        assert client._summarized_message_count > 0

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_summarize_history_handles_failure(self, mock_anthropic, mock_get_config):
        """Summarization falls back to truncation on failure."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 100000
        mock_config.api.summarize_threshold = SUMMARIZE_THRESHOLD
        mock_config.api.min_recent_messages = 6  # Explicit value
        mock_get_config.return_value = mock_config

        mock_client = Mock()
        mock_client.messages.create.side_effect = Exception("API Error")
        mock_anthropic.return_value = mock_client

        client = ClaudeClient()
        client.conversation_history = [
            {"role": "user", "content": f"Message {i}"} for i in range(10)
        ]

        # Should not raise, should fall back to truncation
        client._summarize_history()

        # History should be truncated to min_recent_messages
        assert len(client.conversation_history) == 6

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_summarize_skipped_when_few_messages(self, mock_anthropic, mock_get_config):
        """Summarization skipped when not enough messages."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 100000
        mock_config.api.summarize_threshold = SUMMARIZE_THRESHOLD
        mock_config.api.min_recent_messages = MIN_RECENT_MESSAGES
        mock_get_config.return_value = mock_config

        client = ClaudeClient()
        client.conversation_history = [
            {"role": "user", "content": "Hello"},
        ]

        original_count = len(client.conversation_history)
        client._summarize_history()

        # Should not change when too few messages
        assert len(client.conversation_history) == original_count


class TestSystemPromptWithSummary:
    """Test system prompt includes summary when available."""

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_system_prompt_includes_summary(self, mock_anthropic, mock_get_config):
        """System prompt includes conversation summary."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 100000
        mock_config.api.summarize_threshold = SUMMARIZE_THRESHOLD
        mock_config.api.min_recent_messages = MIN_RECENT_MESSAGES
        mock_get_config.return_value = mock_config

        client = ClaudeClient()
        client._conversation_summary = "User asked about disk space. Found 50GB free."

        prompt = client._build_system_prompt()

        assert "Earlier Conversation Summary" in prompt
        assert "disk space" in prompt

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_system_prompt_without_summary(self, mock_anthropic, mock_get_config):
        """System prompt works without summary."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 100000
        mock_config.api.summarize_threshold = SUMMARIZE_THRESHOLD
        mock_config.api.min_recent_messages = MIN_RECENT_MESSAGES
        mock_get_config.return_value = mock_config

        client = ClaudeClient()

        prompt = client._build_system_prompt()

        assert "Earlier Conversation Summary" not in prompt
        assert "AIOS" in prompt  # Basic system prompt content


class TestConfigDefaults:
    """Test context budget config defaults."""

    def test_api_config_has_context_budget(self):
        """APIConfig has context_budget field."""
        from aios.config import APIConfig

        config = APIConfig()
        assert hasattr(config, 'context_budget')
        assert config.context_budget == 150000

    def test_api_config_custom_context_budget(self):
        """APIConfig accepts custom context_budget."""
        from aios.config import APIConfig

        config = APIConfig(context_budget=50000)
        assert config.context_budget == 50000

    def test_api_config_has_summarize_threshold(self):
        """APIConfig has summarize_threshold field."""
        from aios.config import APIConfig

        config = APIConfig()
        assert hasattr(config, 'summarize_threshold')
        assert config.summarize_threshold == 0.75

    def test_api_config_custom_summarize_threshold(self):
        """APIConfig accepts custom summarize_threshold."""
        from aios.config import APIConfig

        config = APIConfig(summarize_threshold=0.9)
        assert config.summarize_threshold == 0.9

    def test_api_config_has_min_recent_messages(self):
        """APIConfig has min_recent_messages field."""
        from aios.config import APIConfig

        config = APIConfig()
        assert hasattr(config, 'min_recent_messages')
        assert config.min_recent_messages == 6

    def test_api_config_custom_min_recent_messages(self):
        """APIConfig accepts custom min_recent_messages."""
        from aios.config import APIConfig

        config = APIConfig(min_recent_messages=10)
        assert config.min_recent_messages == 10


class TestContextStatsIncludesConfig:
    """Test context stats include new config values."""

    @patch('aios.claude.client.get_config')
    @patch('aios.claude.client.anthropic.Anthropic')
    def test_context_stats_includes_min_recent_messages(self, mock_anthropic, mock_get_config):
        """Context stats include min_recent_messages."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 100000
        mock_config.api.summarize_threshold = 0.8
        mock_config.api.min_recent_messages = 10
        mock_get_config.return_value = mock_config

        client = ClaudeClient()
        stats = client.get_context_stats()

        assert "min_recent_messages" in stats
        assert stats["min_recent_messages"] == 10
        assert stats["summarize_threshold"] == 0.8
