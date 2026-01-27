# AIOS Session Management

AIOS provides a session persistence system that saves conversation history and allows you to resume previous sessions.

## Overview

The session system provides:
- **Automatic Saving**: Sessions are saved to disk when you exit
- **Session History**: Browse and list previous sessions
- **Session Resume**: Continue where you left off with full conversation context
- **Context Variables**: Persistent state within a session (e.g., last file, current project)
- **Preferences**: Per-session user preferences

## How It Works

### Session Lifecycle

```
Start AIOS
    │
    ▼
┌──────────────┐
│ start_session │──── New session created with unique ID
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Conversation │──── Messages stored, context tracked
│    Loop      │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ end_session  │──── Session saved to ~/.config/aios/history/
└──────────────┘
```

Each session is assigned an ID based on the timestamp (e.g., `20260127_143022`) and stored as a JSON file.

### Storage Location

Sessions are saved to:
```
~/.config/aios/history/session_<session_id>.json
```

### Session Data

Each session stores:

| Field | Description |
|-------|-------------|
| `session_id` | Unique identifier (timestamp-based) |
| `started_at` | ISO timestamp of session start |
| `working_directory` | Current working directory |
| `messages` | Full conversation history (user + assistant) |
| `preferences` | Per-session user preferences |
| `context_variables` | Dynamic state variables |

## Shell Commands

### List Previous Sessions

```
sessions
```
or
```
/sessions
```

Shows the last 10 sessions with their ID, start time, and message count:

```
Previous Sessions

  ● 20260127_143022
    Started: 2026-01-27 14:30 | Messages: 24

  ● 20260126_091500
    Started: 2026-01-26 09:15 | Messages: 12

  ● 20260125_170800
    Started: 2026-01-25 17:08 | Messages: 8

Use 'resume <session_id>' to continue a previous session.
```

### Resume a Session

```
resume 20260127_143022
```
or
```
/resume 20260127_143022
```

This will:
1. Load the saved session from disk
2. Display recent conversation context (last 5 messages)
3. Restore Claude's conversation history (last 20 messages)
4. Continue the session from where you left off

```
✓ Resumed session: 20260127_143022
ℹ Session has 24 message(s) in history.

Recent conversation:
  You: Show me my disk usage
  AIOS: Here's your disk usage breakdown...
  You: Clean up the Downloads folder
  AIOS: I'll help you clean up. Found 3 large files...
  You: Delete the temporary files
```

## Configuration

Configure session behavior in `~/.config/aios/config.toml`:

```toml
[session]
save_history = true      # Enable/disable session saving
max_history = 1000       # Maximum messages per session
history_path = "~/.config/aios/history"  # Storage location
```

## Python API

### SessionManager

```python
from aios.context.session import SessionManager

manager = SessionManager()

# Start a new session
session = manager.start_session()
print(session.session_id)  # "20260127_143022"

# Add messages
manager.add_message("user", "Hello!")
manager.add_message("assistant", "Hi! How can I help?")

# Get recent messages
recent = manager.get_recent_messages(count=10)

# Session preferences
manager.set_preference("verbose", True)
verbose = manager.get_preference("verbose")  # True

# Context variables (track state)
manager.set_context_variable("last_file", "/home/user/report.pdf")
last = manager.get_context_variable("last_file")

# Save and load sessions
manager.save_session()
manager.load_session("20260127_143022")

# List previous sessions
sessions = manager.list_sessions(limit=10)
for s in sessions:
    print(f"{s['session_id']}: {s['message_count']} messages")
```

### ConversationBuffer

Manages the Claude API message format:

```python
from aios.context.session import ConversationBuffer

buffer = ConversationBuffer(max_messages=50)

# Add messages in Claude API format
buffer.add_user_message("What files are in my home directory?")
buffer.add_assistant_message("Let me check...")
buffer.add_tool_result(tool_use_id="abc123", content="file1.txt\nfile2.pdf")

# Get messages for Claude API
messages = buffer.get_messages()

# Get text summary
summary = buffer.get_summary()
```

## Session File Format

Sessions are stored as JSON:

```json
{
  "session_id": "20260127_143022",
  "started_at": "2026-01-27T14:30:22.123456",
  "working_directory": "/home/user",
  "messages": [
    {
      "role": "user",
      "content": "Show me my disk usage",
      "timestamp": "2026-01-27T14:30:45.789",
      "metadata": {}
    },
    {
      "role": "assistant",
      "content": "Here's your disk usage...",
      "timestamp": "2026-01-27T14:30:48.123",
      "metadata": {}
    }
  ],
  "preferences": {
    "verbose": true
  },
  "context_variables": {
    "last_file": "/home/user/report.pdf"
  }
}
```

## Best Practices

1. **Session IDs**: Use the `/sessions` command to find valid session IDs before resuming
2. **History Limits**: The `max_history` setting prevents unbounded memory growth. Default is 1000 messages per session
3. **Context Variables**: Use context variables to track state across tool calls within a session (e.g., "last file opened", "current project directory")
4. **Disk Usage**: Old session files accumulate in the history directory. Periodically clean up old sessions if disk space is a concern
