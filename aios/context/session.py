"""
Session and conversation management for AIOS.

Handles:
- Conversation history
- Session persistence
- User preferences within session
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """A conversation message."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class SessionState:
    """Current session state."""
    session_id: str
    started_at: str
    working_directory: str
    messages: List[Message] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    context_variables: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "working_directory": self.working_directory,
            "messages": [asdict(m) for m in self.messages],
            "preferences": self.preferences,
            "context_variables": self.context_variables
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SessionState":
        """Create from dictionary."""
        messages = [Message(**m) for m in data.get("messages", [])]
        return cls(
            session_id=data["session_id"],
            started_at=data["started_at"],
            working_directory=data.get("working_directory", str(Path.home())),
            messages=messages,
            preferences=data.get("preferences", {}),
            context_variables=data.get("context_variables", {})
        )


class SessionManager:
    """Manages conversation sessions."""

    def __init__(self, history_path: Optional[str] = None):
        """
        Initialize the session manager.

        Args:
            history_path: Path to store session history
        """
        from ..config import get_config
        config = get_config()

        if history_path:
            self.history_path = Path(history_path).expanduser()
        else:
            self.history_path = Path(config.session.history_path).expanduser()

        self.save_history = config.session.save_history
        self.max_history = config.session.max_history

        # Ensure history directory exists
        self.history_path.mkdir(parents=True, exist_ok=True)

        # Current session
        self._session: Optional[SessionState] = None

    def start_session(self) -> SessionState:
        """Start a new session."""
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        self._session = SessionState(
            session_id=session_id,
            started_at=datetime.now().isoformat(),
            working_directory=os.getcwd()
        )

        return self._session

    def get_session(self) -> SessionState:
        """Get the current session, creating one if needed."""
        if self._session is None:
            self._session = self.start_session()
        return self._session

    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None) -> Message:
        """
        Add a message to the current session.

        Args:
            role: "user" or "assistant"
            content: Message content
            metadata: Optional metadata

        Returns:
            The created message
        """
        session = self.get_session()

        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )

        session.messages.append(message)

        # Trim if over limit
        if len(session.messages) > self.max_history:
            session.messages = session.messages[-self.max_history:]

        return message

    def get_recent_messages(self, count: int = 10) -> List[Message]:
        """Get recent messages from the session."""
        session = self.get_session()
        return session.messages[-count:]

    def get_conversation_context(self, max_messages: int = 20) -> str:
        """
        Get conversation context for Claude.

        Returns recent conversation formatted for context.
        """
        messages = self.get_recent_messages(max_messages)

        if not messages:
            return ""

        lines = ["Recent conversation:"]
        for msg in messages:
            role = "User" if msg.role == "user" else "AIOS"
            preview = msg.content[:200]
            if len(msg.content) > 200:
                preview += "..."
            lines.append(f"{role}: {preview}")

        return "\n".join(lines)

    def set_preference(self, key: str, value: Any) -> None:
        """Set a session preference."""
        session = self.get_session()
        session.preferences[key] = value

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a session preference."""
        session = self.get_session()
        return session.preferences.get(key, default)

    def set_context_variable(self, key: str, value: Any) -> None:
        """Set a context variable (e.g., 'last_file', 'current_project')."""
        session = self.get_session()
        session.context_variables[key] = value

    def get_context_variable(self, key: str, default: Any = None) -> Any:
        """Get a context variable."""
        session = self.get_session()
        return session.context_variables.get(key, default)

    def update_working_directory(self, path: str) -> None:
        """Update the current working directory."""
        session = self.get_session()
        session.working_directory = path

    def save_session(self) -> bool:
        """Save the current session to disk."""
        if not self.save_history or not self._session:
            return False

        try:
            session_file = self.history_path / f"session_{self._session.session_id}.json"
            with open(session_file, "w") as f:
                json.dump(self._session.to_dict(), f, indent=2)
            return True
        except (OSError, IOError, TypeError, ValueError) as e:
            logger.warning(f"Failed to save session: {e}")
            return False

    def load_session(self, session_id: str) -> Optional[SessionState]:
        """Load a session from disk."""
        try:
            session_file = self.history_path / f"session_{session_id}.json"
            if not session_file.exists():
                return None

            with open(session_file, "r") as f:
                data = json.load(f)
                self._session = SessionState.from_dict(data)
                return self._session
        except (OSError, IOError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to load session {session_id}: {e}")
            return None

    def list_sessions(self, limit: int = 10) -> List[Dict[str, str]]:
        """List recent sessions."""
        sessions = []

        for session_file in sorted(
            self.history_path.glob("session_*.json"),
            reverse=True
        )[:limit]:
            try:
                with open(session_file, "r") as f:
                    data = json.load(f)
                    sessions.append({
                        "session_id": data["session_id"],
                        "started_at": data["started_at"],
                        "message_count": len(data.get("messages", []))
                    })
            except (OSError, IOError, json.JSONDecodeError, KeyError) as e:
                logger.debug(f"Skipping corrupt session file {session_file}: {e}")
                continue

        return sessions

    def clear_session(self) -> None:
        """Clear the current session."""
        if self._session:
            self._session.messages = []
            self._session.context_variables = {}

    def end_session(self) -> None:
        """End and save the current session."""
        self.save_session()
        self._session = None

    def get_session_summary(self) -> Dict[str, Any]:
        """Get a summary of the current session."""
        session = self.get_session()

        user_messages = sum(1 for m in session.messages if m.role == "user")
        assistant_messages = sum(1 for m in session.messages if m.role == "assistant")

        return {
            "session_id": session.session_id,
            "started_at": session.started_at,
            "working_directory": session.working_directory,
            "total_messages": len(session.messages),
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
            "preferences": list(session.preferences.keys()),
            "context_variables": list(session.context_variables.keys())
        }


class ConversationBuffer:
    """
    Manages conversation history for Claude API.

    Handles the specific format required by the Claude API
    and manages context window limits.
    """

    def __init__(self, max_messages: int = 50):
        """
        Initialize the conversation buffer.

        Args:
            max_messages: Maximum messages to keep in buffer
        """
        self.max_messages = max_messages
        self._messages: List[Dict[str, Any]] = []

    def add_user_message(self, content: str) -> None:
        """Add a user message."""
        self._messages.append({
            "role": "user",
            "content": content
        })
        self._trim()

    def add_assistant_message(self, content: Any) -> None:
        """
        Add an assistant message.

        Content can be a string or list of content blocks.
        """
        self._messages.append({
            "role": "assistant",
            "content": content
        })
        self._trim()

    def add_tool_result(self, tool_use_id: str, content: str, is_error: bool = False) -> None:
        """Add a tool result message."""
        self._messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content,
                "is_error": is_error
            }]
        })
        self._trim()

    def get_messages(self) -> List[Dict[str, Any]]:
        """Get all messages in Claude API format."""
        return self._messages.copy()

    def clear(self) -> None:
        """Clear all messages."""
        self._messages = []

    def _trim(self) -> None:
        """Trim messages to max limit."""
        if len(self._messages) > self.max_messages:
            # Keep first message (often important) and recent messages
            self._messages = [self._messages[0]] + self._messages[-(self.max_messages - 1):]

    def get_summary(self) -> str:
        """Get a text summary of the conversation."""
        lines = []
        for msg in self._messages[-10:]:
            role = msg["role"].capitalize()
            content = msg["content"]
            if isinstance(content, str):
                preview = content[:100] + "..." if len(content) > 100 else content
                lines.append(f"{role}: {preview}")
            else:
                lines.append(f"{role}: [structured content]")
        return "\n".join(lines)
