"""Tests for the reusable ContextManager component."""

import pytest

from aios.providers.context_manager import (
    ContextManager,
    ContextStats,
    SimpleTokenCounter,
    Message,
    create_summarization_prompt,
)


class TestSimpleTokenCounter:
    """Tests for SimpleTokenCounter."""

    def test_count_empty_string(self):
        counter = SimpleTokenCounter()
        assert counter.count("") == 0

    def test_count_short_string(self):
        counter = SimpleTokenCounter(chars_per_token=4.0)
        # "hello" = 5 chars / 4 = 1.25 -> 1 token
        assert counter.count("hello") == 1

    def test_count_longer_string(self):
        counter = SimpleTokenCounter(chars_per_token=4.0)
        # 100 chars / 4 = 25 tokens
        assert counter.count("a" * 100) == 25

    def test_custom_chars_per_token(self):
        counter = SimpleTokenCounter(chars_per_token=2.0)
        # 10 chars / 2 = 5 tokens
        assert counter.count("a" * 10) == 5


class TestMessage:
    """Tests for Message dataclass."""

    def test_message_creation(self):
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.metadata == {}

    def test_message_with_metadata(self):
        msg = Message(role="tool", content="result", metadata={"tool_call_id": "123"})
        assert msg.metadata["tool_call_id"] == "123"

    def test_to_dict(self):
        msg = Message(role="user", content="Hello")
        d = msg.to_dict()
        assert d == {"role": "user", "content": "Hello"}

    def test_to_dict_with_metadata(self):
        msg = Message(role="tool", content="result", metadata={"tool_call_id": "123"})
        d = msg.to_dict()
        assert d == {"role": "tool", "content": "result", "tool_call_id": "123"}


class TestContextManager:
    """Tests for ContextManager."""

    def test_init_defaults(self):
        manager = ContextManager()
        assert manager.context_budget == 150000
        assert manager.summarize_threshold == 0.75
        assert manager.min_recent_messages == 6

    def test_init_custom_values(self):
        manager = ContextManager(
            context_budget=50000,
            summarize_threshold=0.5,
            min_recent_messages=3,
        )
        assert manager.context_budget == 50000
        assert manager.summarize_threshold == 0.5
        assert manager.min_recent_messages == 3

    def test_add_message(self):
        manager = ContextManager()
        manager.add_message("user", "Hello")
        assert manager.message_count == 1

    def test_add_multiple_messages(self):
        manager = ContextManager()
        manager.add_message("user", "Hello")
        manager.add_message("assistant", "Hi there!")
        manager.add_message("user", "How are you?")
        assert manager.message_count == 3

    def test_add_messages_batch(self):
        manager = ContextManager()
        manager.add_messages([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ])
        assert manager.message_count == 2

    def test_get_messages(self):
        manager = ContextManager()
        manager.add_message("user", "Hello")
        manager.add_message("assistant", "Hi!")

        messages = manager.get_messages()
        assert len(messages) == 2
        assert messages[0] == {"role": "user", "content": "Hello"}
        assert messages[1] == {"role": "assistant", "content": "Hi!"}

    def test_get_token_usage(self):
        manager = ContextManager()
        manager.add_message("user", "Hello world")  # ~11 chars = ~3 tokens + 10 overhead = ~13

        tokens, percentage = manager.get_token_usage()
        assert tokens > 0
        assert 0 <= percentage <= 1

    def test_needs_summarization_false(self):
        manager = ContextManager(summarize_fn=lambda x: "summary")
        manager.add_message("user", "Hello")
        assert not manager.needs_summarization()

    def test_needs_summarization_true(self):
        # Create a manager with small budget
        manager = ContextManager(
            summarize_fn=lambda x: "summary",
            context_budget=100,
            summarize_threshold=0.5,
        )
        # Add enough content to exceed threshold
        manager.add_message("user", "x" * 200)  # ~50 tokens, > 50% of 100
        assert manager.needs_summarization()

    def test_needs_summarization_no_fn(self):
        """Without summarize_fn, should never need summarization."""
        manager = ContextManager(
            summarize_fn=None,
            context_budget=100,
        )
        manager.add_message("user", "x" * 500)
        assert not manager.needs_summarization()

    def test_summarize_basic(self):
        summaries_called = []

        def mock_summarize(text):
            summaries_called.append(text)
            return "This is a summary"

        manager = ContextManager(
            summarize_fn=mock_summarize,
            min_recent_messages=2,
        )

        # Add messages
        manager.add_message("user", "Message 1")
        manager.add_message("assistant", "Response 1")
        manager.add_message("user", "Message 2")
        manager.add_message("assistant", "Response 2")
        manager.add_message("user", "Message 3")

        # Summarize
        result = manager.summarize()

        assert result is True
        assert len(summaries_called) == 1
        assert manager.summary == "This is a summary"
        assert manager.message_count == 2  # Only recent messages kept
        assert manager.summarized_message_count == 3  # 3 messages summarized

    def test_summarize_no_fn(self):
        manager = ContextManager(summarize_fn=None)
        manager.add_message("user", "Hello")

        result = manager.summarize()
        assert result is False

    def test_summarize_no_messages(self):
        manager = ContextManager(
            summarize_fn=lambda x: "summary",
            min_recent_messages=10,
        )
        manager.add_message("user", "Hello")

        # Only 1 message, need 10 recent, so nothing to summarize
        result = manager.summarize()
        assert result is False

    def test_check_and_summarize(self):
        manager = ContextManager(
            summarize_fn=lambda x: "summary",
            context_budget=100,
            summarize_threshold=0.3,
            min_recent_messages=2,
        )

        # Add enough content
        manager.add_message("user", "x" * 100)
        manager.add_message("assistant", "y" * 100)
        manager.add_message("user", "z" * 100)

        result = manager.check_and_summarize()
        assert result is True
        assert manager.summary == "summary"

    def test_clear(self):
        manager = ContextManager(summarize_fn=lambda x: "summary")
        manager.add_message("user", "Hello")
        manager.summarize()

        manager.clear()

        assert manager.message_count == 0
        assert manager.summary is None
        assert manager.summarized_message_count == 0

    def test_get_stats(self):
        manager = ContextManager()
        manager.add_message("user", "Hello")
        manager.add_message("assistant", "Hi!")

        stats = manager.get_stats()

        assert isinstance(stats, ContextStats)
        assert stats.message_count == 2
        assert stats.total_tokens > 0
        assert stats.summarized_message_count == 0
        assert stats.has_summary is False

    def test_get_history_summary(self):
        manager = ContextManager()
        manager.add_message("user", "Hello")

        summary = manager.get_history_summary()

        assert "Messages: 1" in summary
        assert "Tokens:" in summary

    def test_messages_with_summary_prefix(self):
        """When summary exists, it should be included as system message."""
        manager = ContextManager(
            summarize_fn=lambda x: "Previous conversation summary",
            min_recent_messages=1,
        )

        manager.add_message("user", "First")
        manager.add_message("assistant", "Response")
        manager.add_message("user", "Second")

        # Force summarization
        manager.summarize()

        messages = manager.get_messages()

        # First message should be system with summary
        assert messages[0]["role"] == "system"
        assert "CONVERSATION SUMMARY" in messages[0]["content"]
        assert "Previous conversation summary" in messages[0]["content"]

    def test_get_messages_for_anthropic(self):
        manager = ContextManager(
            summarize_fn=lambda x: "summary",
            min_recent_messages=1,
        )

        manager.add_message("user", "First")
        manager.add_message("user", "Second")
        manager.summarize()

        summary, messages = manager.get_messages_for_anthropic()

        assert summary == "summary"
        assert len(messages) == 1  # Only recent messages


class TestCreateSummarizationPrompt:
    """Tests for create_summarization_prompt."""

    def test_creates_prompt(self):
        prompt = create_summarization_prompt("User: Hello\nAssistant: Hi!")

        assert "User: Hello" in prompt
        assert "Assistant: Hi!" in prompt
        assert "summary" in prompt.lower()

    def test_includes_instructions(self):
        prompt = create_summarization_prompt("conversation")

        assert "concise" in prompt.lower() or "summary" in prompt.lower()
