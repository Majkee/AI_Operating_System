"""
Tool definitions for Claude API.

These tools define what actions Claude can take on the system.
Each tool is designed to be safe and user-friendly for non-technical users.
"""

from typing import Any, Callable, Optional
from dataclasses import dataclass


@dataclass
class ToolResult:
    """Result of a tool execution."""
    success: bool
    output: str
    error: Optional[str] = None
    requires_followup: bool = False
    user_friendly_message: str = ""


# Tool definitions for Claude API
TOOLS = [
    {
        "name": "run_command",
        "description": """Execute a shell command on the system. Use this for system operations like:
- Listing files and directories
- Checking system status
- Installing or updating software
- Managing processes

IMPORTANT: Always provide a clear, non-technical explanation of what the command does.
For dangerous operations, set requires_confirmation to true.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                },
                "explanation": {
                    "type": "string",
                    "description": "A friendly, non-technical explanation of what this command does (shown to user)"
                },
                "requires_confirmation": {
                    "type": "boolean",
                    "description": "Whether to ask user for confirmation before running",
                    "default": False
                },
                "working_directory": {
                    "type": "string",
                    "description": "Directory to run the command in (defaults to user's home)"
                }
            },
            "required": ["command", "explanation"]
        }
    },
    {
        "name": "read_file",
        "description": """Read the contents of a file. Use this to:
- View configuration files
- Read documents
- Check file contents before modifying

Always explain to the user what file you're reading and why.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to read"
                },
                "explanation": {
                    "type": "string",
                    "description": "Why you're reading this file (shown to user)"
                }
            },
            "required": ["path", "explanation"]
        }
    },
    {
        "name": "write_file",
        "description": """Create or modify a file. Use this to:
- Create new documents
- Edit configuration files
- Save user's work

IMPORTANT: Always explain what changes you're making and why.
Set requires_confirmation to true for important files.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to write"
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file"
                },
                "explanation": {
                    "type": "string",
                    "description": "What you're creating/changing and why (shown to user)"
                },
                "requires_confirmation": {
                    "type": "boolean",
                    "description": "Whether to ask user for confirmation before writing",
                    "default": True
                },
                "create_backup": {
                    "type": "boolean",
                    "description": "Whether to create a backup of existing file",
                    "default": True
                }
            },
            "required": ["path", "content", "explanation"]
        }
    },
    {
        "name": "search_files",
        "description": """Search for files by name or content. Use this to:
- Find files the user is looking for
- Locate configuration files
- Search for specific content in files

Provide helpful context about search results.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for (filename pattern or content)"
                },
                "location": {
                    "type": "string",
                    "description": "Directory to search in (defaults to home directory)"
                },
                "search_type": {
                    "type": "string",
                    "enum": ["filename", "content"],
                    "description": "Whether to search file names or file contents",
                    "default": "filename"
                },
                "explanation": {
                    "type": "string",
                    "description": "What you're searching for and why (shown to user)"
                }
            },
            "required": ["query", "explanation"]
        }
    },
    {
        "name": "list_directory",
        "description": """List contents of a directory. Use this to:
- Show files in a folder
- Help user navigate their files
- Explore the file system

Present results in a user-friendly format.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list (defaults to home directory)"
                },
                "show_hidden": {
                    "type": "boolean",
                    "description": "Whether to show hidden files",
                    "default": False
                },
                "explanation": {
                    "type": "string",
                    "description": "What you're looking for (shown to user)"
                }
            },
            "required": ["explanation"]
        }
    },
    {
        "name": "get_system_info",
        "description": """Get information about the system. Use this for:
- Checking available disk space
- Viewing memory usage
- Getting system specifications
- Checking running processes

Always translate technical info into user-friendly language.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "info_type": {
                    "type": "string",
                    "enum": ["disk", "memory", "cpu", "processes", "network", "general"],
                    "description": "What type of system information to get"
                },
                "explanation": {
                    "type": "string",
                    "description": "Why you need this information (shown to user)"
                }
            },
            "required": ["info_type", "explanation"]
        }
    },
    {
        "name": "manage_application",
        "description": """Install, remove, or update applications. Use this when user wants to:
- Install new software
- Remove unwanted applications
- Update their system or apps

Always explain what will be installed/removed and ask for confirmation.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["install", "remove", "update", "search"],
                    "description": "What action to take"
                },
                "package": {
                    "type": "string",
                    "description": "Name of the application/package"
                },
                "explanation": {
                    "type": "string",
                    "description": "What this application does and why user might want it (shown to user)"
                }
            },
            "required": ["action", "package", "explanation"]
        }
    },
    {
        "name": "ask_clarification",
        "description": """Ask the user for clarification when their request is ambiguous. Use this when:
- You need more information to proceed
- There are multiple ways to interpret the request
- You want to confirm before taking action

Be friendly and provide helpful options when possible.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user"
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of choices to present"
                },
                "context": {
                    "type": "string",
                    "description": "Additional context to help the user understand"
                }
            },
            "required": ["question"]
        }
    },
    {
        "name": "open_application",
        "description": """Open an application or file with its default application. Use this when user wants to:
- Open a document
- Launch an application
- View an image or video

Provide feedback about what's being opened.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Path to file or name of application to open"
                },
                "explanation": {
                    "type": "string",
                    "description": "What you're opening (shown to user)"
                }
            },
            "required": ["target", "explanation"]
        }
    }
]


class ToolHandler:
    """Handles tool execution and result formatting."""

    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, tool_name: str, handler: Callable) -> None:
        """Register a handler function for a tool."""
        self._handlers[tool_name] = handler

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> ToolResult:
        """Execute a tool and return the result."""
        if tool_name not in self._handlers:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown tool: {tool_name}",
                user_friendly_message=f"I don't know how to do that yet."
            )

        try:
            handler = self._handlers[tool_name]
            return handler(tool_input)
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
                user_friendly_message=f"Something went wrong: {str(e)}"
            )

    def get_tool_names(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._handlers.keys())
