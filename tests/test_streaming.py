"""Tests for streaming response functionality."""

import pytest
from unittest.mock import Mock, MagicMock, patch

from aios.config import APIConfig
from aios.providers.anthropic_client import AnthropicClient, SYSTEM_PROMPT
from aios.providers.base import AssistantResponse
from aios.ui.terminal import StreamingResponseHandler


class TestClaudeClientHelpers:
    """Test helper methods in AnthropicClient."""

    def test_build_system_prompt_without_context(self):
        """Test _build_system_prompt returns base prompt when no context."""
        with patch.object(AnthropicClient, '__init__', lambda x, y=None: None):
            client = AnthropicClient()
            client.tool_handler = Mock()
            client._conversation_summary = None  # Required for new context management
            result = client._build_system_prompt()
            assert result == SYSTEM_PROMPT

    def test_build_system_prompt_with_context(self):
        """Test _build_system_prompt appends context."""
        with patch.object(AnthropicClient, '__init__', lambda x, y=None: None):
            client = AnthropicClient()
            client.tool_handler = Mock()
            client._conversation_summary = None  # Required for new context management
            context = "User is on Debian 12"
            result = client._build_system_prompt(context)
            assert SYSTEM_PROMPT in result
            assert "## Current System Context" in result
            assert context in result

    def test_store_assistant_history_text_only(self):
        """Test _store_assistant_history with text-only response."""
        with patch.object(AnthropicClient, '__init__', lambda x, y=None: None):
            client = AnthropicClient()
            client.conversation_history = []

            response = AssistantResponse(
                text="Hello, how can I help?",
                tool_calls=[],
                is_complete=True
            )
            client._store_assistant_history(response)

            assert len(client.conversation_history) == 1
            msg = client.conversation_history[0]
            assert msg["role"] == "assistant"
            assert len(msg["content"]) == 1
            assert msg["content"][0]["type"] == "text"
            assert msg["content"][0]["text"] == "Hello, how can I help?"

    def test_store_assistant_history_tool_calls(self):
        """Test _store_assistant_history with tool calls."""
        with patch.object(AnthropicClient, '__init__', lambda x, y=None: None):
            client = AnthropicClient()
            client.conversation_history = []

            response = AssistantResponse(
                text="",
                tool_calls=[
                    {"id": "tool_1", "name": "run_command", "input": {"command": "ls"}}
                ],
                is_complete=False
            )
            client._store_assistant_history(response)

            assert len(client.conversation_history) == 1
            msg = client.conversation_history[0]
            assert msg["role"] == "assistant"
            assert len(msg["content"]) == 1
            assert msg["content"][0]["type"] == "tool_use"
            assert msg["content"][0]["id"] == "tool_1"

    def test_store_assistant_history_mixed(self):
        """Test _store_assistant_history with text and tool calls."""
        with patch.object(AnthropicClient, '__init__', lambda x, y=None: None):
            client = AnthropicClient()
            client.conversation_history = []

            response = AssistantResponse(
                text="Let me check that for you.",
                tool_calls=[
                    {"id": "tool_1", "name": "list_directory", "input": {"path": "/tmp"}}
                ],
                is_complete=False
            )
            client._store_assistant_history(response)

            assert len(client.conversation_history) == 1
            msg = client.conversation_history[0]
            assert len(msg["content"]) == 2
            assert msg["content"][0]["type"] == "text"
            assert msg["content"][1]["type"] == "tool_use"


class TestStreamingResponseHandler:
    """Test StreamingResponseHandler context manager."""

    def test_handler_starts_with_spinner(self):
        """Test handler starts with a spinner on entry."""
        console = Mock()
        handler = StreamingResponseHandler(console)

        with patch('aios.ui.terminal.Progress') as MockProgress:
            mock_progress = MagicMock()
            MockProgress.return_value = mock_progress

            with handler:
                # Spinner should be started
                MockProgress.assert_called_once()
                mock_progress.__enter__.assert_called_once()
                mock_progress.add_task.assert_called_with("Thinking...", total=None)

    def test_handler_no_text_exits_spinner(self):
        """Test handler exits spinner cleanly when no text streamed."""
        console = Mock()
        handler = StreamingResponseHandler(console)

        with patch('aios.ui.terminal.Progress') as MockProgress:
            mock_progress = MagicMock()
            MockProgress.return_value = mock_progress

            with handler:
                pass  # No add_text called

            # Spinner should exit
            mock_progress.__exit__.assert_called()

        # No text was streamed
        assert handler.streamed_text == ""

    def test_handler_first_text_transitions_to_live(self):
        """Test first add_text() stops spinner and starts Live."""
        console = Mock()
        handler = StreamingResponseHandler(console)

        with patch('aios.ui.terminal.Progress') as MockProgress, \
             patch('aios.ui.terminal.Live') as MockLive:
            mock_progress = MagicMock()
            mock_live = MagicMock()
            MockProgress.return_value = mock_progress
            MockLive.return_value = mock_live

            with handler:
                handler.add_text("Hello")

                # Spinner should be stopped
                mock_progress.__exit__.assert_called()
                # Header should be printed
                assert console.print.call_count >= 2  # newline and header
                # Live should be started
                MockLive.assert_called_once()
                mock_live.__enter__.assert_called_once()

    def test_handler_accumulates_text(self):
        """Test add_text accumulates all deltas."""
        console = Mock()
        handler = StreamingResponseHandler(console)

        with patch('aios.ui.terminal.Progress'), \
             patch('aios.ui.terminal.Live') as MockLive:
            mock_live = MagicMock()
            MockLive.return_value = mock_live

            with handler:
                handler.add_text("Hel")
                handler.add_text("lo ")
                handler.add_text("world!")

            assert handler.streamed_text == "Hello world!"

    def test_handler_updates_live_display(self):
        """Test add_text updates Live display."""
        console = Mock()
        handler = StreamingResponseHandler(console)

        with patch('aios.ui.terminal.Progress'), \
             patch('aios.ui.terminal.Live') as MockLive, \
             patch('aios.ui.terminal.Markdown') as MockMarkdown:
            mock_live = MagicMock()
            MockLive.return_value = mock_live

            with handler:
                handler.add_text("Hello")
                handler.add_text(" world")

            # Live.update should be called for each delta
            assert mock_live.update.call_count == 2


class TestAPIConfigStreaming:
    """Test streaming config default."""

    def test_streaming_default_true(self):
        """Test APIConfig.streaming defaults to True."""
        config = APIConfig()
        assert config.streaming is True

    def test_streaming_can_be_disabled(self):
        """Test streaming can be set to False."""
        config = APIConfig(streaming=False)
        assert config.streaming is False


class TestSendMessageStreaming:
    """Test send_message with streaming parameter."""

    @patch('aios.providers.anthropic_client.get_config')
    @patch('aios.providers.anthropic_client.anthropic.Anthropic')
    def test_send_message_no_on_text_uses_create(self, mock_anthropic_class, mock_get_config):
        """Test send_message without on_text uses messages.create."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 150000
        mock_config.api.summarize_threshold = 0.75
        mock_config.api.min_recent_messages = 6
        mock_get_config.return_value = mock_config

        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        mock_response = Mock()
        mock_response.content = []
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_response

        client = AnthropicClient()
        client.send_message("Hello")

        # Should use create, not stream
        mock_client.messages.create.assert_called_once()
        mock_client.messages.stream.assert_not_called()

    @patch('aios.providers.anthropic_client.get_config')
    @patch('aios.providers.anthropic_client.anthropic.Anthropic')
    def test_send_message_with_on_text_uses_stream(self, mock_anthropic_class, mock_get_config):
        """Test send_message with on_text uses messages.stream."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 150000
        mock_config.api.summarize_threshold = 0.75
        mock_config.api.min_recent_messages = 6
        mock_get_config.return_value = mock_config

        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        # Setup streaming mock
        mock_stream = MagicMock()
        mock_stream.__enter__ = Mock(return_value=mock_stream)
        mock_stream.__exit__ = Mock(return_value=False)
        mock_stream.text_stream = ["Hel", "lo"]
        mock_final = Mock()
        mock_final.content = []
        mock_final.stop_reason = "end_turn"
        mock_stream.get_final_message.return_value = mock_final
        mock_client.messages.stream.return_value = mock_stream

        client = AnthropicClient()
        callback = Mock()
        client.send_message("Hello", on_text=callback)

        # Should use stream, not create
        mock_client.messages.stream.assert_called_once()
        mock_client.messages.create.assert_not_called()

        # Callback should be called for each delta
        assert callback.call_count == 2
        callback.assert_any_call("Hel")
        callback.assert_any_call("lo")


class TestSendToolResultsStreaming:
    """Test send_tool_results with streaming parameter."""

    @patch('aios.providers.anthropic_client.get_config')
    @patch('aios.providers.anthropic_client.anthropic.Anthropic')
    def test_send_tool_results_no_on_text_uses_create(self, mock_anthropic_class, mock_get_config):
        """Test send_tool_results without on_text uses messages.create."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 150000
        mock_config.api.summarize_threshold = 0.75
        mock_config.api.min_recent_messages = 6
        mock_get_config.return_value = mock_config

        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        mock_response = Mock()
        mock_response.content = []
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_response

        client = AnthropicClient()
        tool_results = [{"tool_use_id": "1", "content": "done"}]
        client.send_tool_results(tool_results)

        # Should use create, not stream
        mock_client.messages.create.assert_called_once()
        mock_client.messages.stream.assert_not_called()

    @patch('aios.providers.anthropic_client.get_config')
    @patch('aios.providers.anthropic_client.anthropic.Anthropic')
    def test_send_tool_results_with_on_text_uses_stream(self, mock_anthropic_class, mock_get_config):
        """Test send_tool_results with on_text uses messages.stream."""
        mock_config = Mock()
        mock_config.api.api_key = "test-key"
        mock_config.api.model = "claude-test"
        mock_config.api.max_tokens = 1000
        mock_config.api.context_budget = 150000
        mock_config.api.summarize_threshold = 0.75
        mock_config.api.min_recent_messages = 6
        mock_get_config.return_value = mock_config

        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        # Setup streaming mock
        mock_stream = MagicMock()
        mock_stream.__enter__ = Mock(return_value=mock_stream)
        mock_stream.__exit__ = Mock(return_value=False)
        mock_stream.text_stream = ["Result: ", "success"]
        mock_final = Mock()
        mock_final.content = []
        mock_final.stop_reason = "end_turn"
        mock_stream.get_final_message.return_value = mock_final
        mock_client.messages.stream.return_value = mock_stream

        client = AnthropicClient()
        callback = Mock()
        tool_results = [{"tool_use_id": "1", "content": "done"}]
        client.send_tool_results(tool_results, on_text=callback)

        # Should use stream, not create
        mock_client.messages.stream.assert_called_once()
        # Callback should be called for each delta
        assert callback.call_count == 2
