"""Tests for session management."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from aios.context.session import (
    Message,
    SessionState,
    SessionManager,
    ConversationBuffer,
)


class TestMessage:
    """Test Message dataclass."""

    def test_message_creation(self):
        """Test creating a message."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp != ""
        assert msg.metadata == {}

    def test_message_with_metadata(self):
        """Test creating a message with metadata."""
        msg = Message(
            role="assistant",
            content="Response",
            metadata={"tool_used": "search"}
        )
        assert msg.metadata["tool_used"] == "search"

    def test_message_auto_timestamp(self):
        """Test that timestamp is auto-generated."""
        msg = Message(role="user", content="Test")
        # Verify it's a valid ISO format
        datetime.fromisoformat(msg.timestamp)

    def test_message_custom_timestamp(self):
        """Test message with custom timestamp."""
        custom_time = "2024-01-01T12:00:00"
        msg = Message(role="user", content="Test", timestamp=custom_time)
        assert msg.timestamp == custom_time


class TestSessionState:
    """Test SessionState dataclass."""

    def test_session_state_creation(self):
        """Test creating a session state."""
        state = SessionState(
            session_id="test123",
            started_at="2024-01-01T12:00:00",
            working_directory="/home/test"
        )
        assert state.session_id == "test123"
        assert state.messages == []
        assert state.preferences == {}

    def test_session_state_to_dict(self):
        """Test converting session state to dictionary."""
        state = SessionState(
            session_id="test123",
            started_at="2024-01-01T12:00:00",
            working_directory="/home/test",
            messages=[Message(role="user", content="Hi")],
            preferences={"theme": "dark"}
        )
        result = state.to_dict()
        assert result["session_id"] == "test123"
        assert len(result["messages"]) == 1
        assert result["preferences"]["theme"] == "dark"

    def test_session_state_from_dict(self):
        """Test creating session state from dictionary."""
        data = {
            "session_id": "test456",
            "started_at": "2024-01-01T12:00:00",
            "working_directory": "/home/test",
            "messages": [
                {"role": "user", "content": "Hello", "timestamp": "2024-01-01T12:00:00", "metadata": {}}
            ],
            "preferences": {"lang": "en"}
        }
        state = SessionState.from_dict(data)
        assert state.session_id == "test456"
        assert len(state.messages) == 1
        assert state.messages[0].content == "Hello"


class TestSessionManager:
    """Test SessionManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        # Mock the config
        self.mock_config = MagicMock()
        self.mock_config.session.history_path = self.temp_dir
        self.mock_config.session.save_history = True
        self.mock_config.session.max_history = 100

    def teardown_method(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_manager(self):
        """Create a SessionManager with mocked config."""
        with patch("aios.config.get_config", return_value=self.mock_config):
            return SessionManager(history_path=self.temp_dir)

    def test_start_session(self):
        """Test starting a new session."""
        with patch("aios.config.get_config", return_value=self.mock_config):
            manager = SessionManager(history_path=self.temp_dir)
            session = manager.start_session()
            assert session is not None
            assert session.session_id != ""
            assert session.started_at != ""

    def test_get_session_creates_if_needed(self):
        """Test get_session creates a session if none exists."""
        with patch("aios.config.get_config", return_value=self.mock_config):
            manager = SessionManager(history_path=self.temp_dir)
            session = manager.get_session()
            assert session is not None

    def test_add_message(self):
        """Test adding messages to session."""
        with patch("aios.config.get_config", return_value=self.mock_config):
            manager = SessionManager(history_path=self.temp_dir)
            manager.start_session()

            msg = manager.add_message("user", "Hello")
            assert msg.role == "user"
            assert msg.content == "Hello"

            session = manager.get_session()
            assert len(session.messages) == 1

    def test_add_message_with_metadata(self):
        """Test adding message with metadata."""
        with patch("aios.config.get_config", return_value=self.mock_config):
            manager = SessionManager(history_path=self.temp_dir)
            manager.start_session()

            msg = manager.add_message("assistant", "Response", {"tool": "search"})
            assert msg.metadata["tool"] == "search"

    def test_message_trimming(self):
        """Test that messages are trimmed when over limit."""
        self.mock_config.session.max_history = 5
        with patch("aios.config.get_config", return_value=self.mock_config):
            manager = SessionManager(history_path=self.temp_dir)
            manager.start_session()

            for i in range(10):
                manager.add_message("user", f"Message {i}")

            session = manager.get_session()
            assert len(session.messages) == 5

    def test_get_recent_messages(self):
        """Test getting recent messages."""
        with patch("aios.config.get_config", return_value=self.mock_config):
            manager = SessionManager(history_path=self.temp_dir)
            manager.start_session()

            for i in range(20):
                manager.add_message("user", f"Message {i}")

            recent = manager.get_recent_messages(5)
            assert len(recent) == 5
            assert recent[-1].content == "Message 19"

    def test_set_and_get_preference(self):
        """Test setting and getting preferences."""
        with patch("aios.config.get_config", return_value=self.mock_config):
            manager = SessionManager(history_path=self.temp_dir)
            manager.start_session()

            manager.set_preference("theme", "dark")
            assert manager.get_preference("theme") == "dark"
            assert manager.get_preference("unknown", "default") == "default"

    def test_set_and_get_context_variable(self):
        """Test setting and getting context variables."""
        with patch("aios.config.get_config", return_value=self.mock_config):
            manager = SessionManager(history_path=self.temp_dir)
            manager.start_session()

            manager.set_context_variable("last_file", "/home/test.txt")
            assert manager.get_context_variable("last_file") == "/home/test.txt"

    def test_save_and_load_session(self):
        """Test saving and loading a session."""
        with patch("aios.config.get_config", return_value=self.mock_config):
            manager = SessionManager(history_path=self.temp_dir)
            session = manager.start_session()
            session_id = session.session_id

            manager.add_message("user", "Test message")
            manager.set_preference("key", "value")
            manager.save_session()

            # Create new manager and load
            manager2 = SessionManager(history_path=self.temp_dir)
            loaded = manager2.load_session(session_id)

            assert loaded is not None
            assert loaded.session_id == session_id
            assert len(loaded.messages) == 1
            assert loaded.preferences["key"] == "value"

    def test_list_sessions(self):
        """Test listing saved sessions."""
        import time
        with patch("aios.config.get_config", return_value=self.mock_config):
            manager = SessionManager(history_path=self.temp_dir)

            # Create and save multiple sessions with unique IDs
            for i in range(3):
                manager.start_session()
                # Manually set unique session_id to avoid timestamp collision
                manager._session.session_id = f"session_{i}"
                manager.add_message("user", f"Message {i}")
                manager.save_session()
                manager._session = None  # Reset to create new session

            sessions = manager.list_sessions()
            assert len(sessions) == 3

    def test_clear_session(self):
        """Test clearing current session."""
        with patch("aios.config.get_config", return_value=self.mock_config):
            manager = SessionManager(history_path=self.temp_dir)
            manager.start_session()
            manager.add_message("user", "Test")
            manager.set_context_variable("var", "value")

            manager.clear_session()

            session = manager.get_session()
            assert len(session.messages) == 0
            assert len(session.context_variables) == 0

    def test_get_session_summary(self):
        """Test getting session summary."""
        with patch("aios.config.get_config", return_value=self.mock_config):
            manager = SessionManager(history_path=self.temp_dir)
            manager.start_session()
            manager.add_message("user", "User msg")
            manager.add_message("assistant", "Assistant msg")
            manager.add_message("user", "Another user msg")

            summary = manager.get_session_summary()
            assert summary["total_messages"] == 3
            assert summary["user_messages"] == 2
            assert summary["assistant_messages"] == 1


class TestConversationBuffer:
    """Test ConversationBuffer class."""

    def test_add_user_message(self):
        """Test adding user message."""
        buffer = ConversationBuffer()
        buffer.add_user_message("Hello")

        messages = buffer.get_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"

    def test_add_assistant_message(self):
        """Test adding assistant message."""
        buffer = ConversationBuffer()
        buffer.add_assistant_message("Hi there!")

        messages = buffer.get_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"

    def test_add_tool_result(self):
        """Test adding tool result."""
        buffer = ConversationBuffer()
        buffer.add_tool_result("tool123", "Result data", is_error=False)

        messages = buffer.get_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"][0]["type"] == "tool_result"
        assert messages[0]["content"][0]["tool_use_id"] == "tool123"

    def test_add_tool_result_error(self):
        """Test adding tool result with error."""
        buffer = ConversationBuffer()
        buffer.add_tool_result("tool456", "Error message", is_error=True)

        messages = buffer.get_messages()
        assert messages[0]["content"][0]["is_error"] is True

    def test_trim_messages(self):
        """Test that messages are trimmed to max limit."""
        buffer = ConversationBuffer(max_messages=5)

        for i in range(10):
            buffer.add_user_message(f"Message {i}")

        messages = buffer.get_messages()
        # Should keep first message + last 4
        assert len(messages) == 5
        assert messages[0]["content"] == "Message 0"  # First preserved

    def test_clear_messages(self):
        """Test clearing all messages."""
        buffer = ConversationBuffer()
        buffer.add_user_message("Test")
        buffer.add_assistant_message("Response")

        buffer.clear()

        assert len(buffer.get_messages()) == 0

    def test_get_summary(self):
        """Test getting conversation summary."""
        buffer = ConversationBuffer()
        buffer.add_user_message("Hello")
        buffer.add_assistant_message("Hi!")

        summary = buffer.get_summary()
        assert "User:" in summary
        assert "Assistant:" in summary

    def test_get_messages_returns_copy(self):
        """Test that get_messages returns a copy."""
        buffer = ConversationBuffer()
        buffer.add_user_message("Test")

        messages = buffer.get_messages()
        messages.clear()

        assert len(buffer.get_messages()) == 1
