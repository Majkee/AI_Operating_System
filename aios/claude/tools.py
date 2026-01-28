"""
Tool definitions for Claude API.

These tools define what actions Claude can take on the system.
Each tool is designed to be safe and user-friendly for non-technical users.
"""

from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ToolResult:
    """Result of a tool execution."""
    success: bool
    output: str
    error: Optional[str] = None
    requires_followup: bool = False
    user_friendly_message: str = ""


# Built-in tool definitions for Claude API
BUILTIN_TOOLS = [
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
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds. Default 30. Use 600-3600 for downloads/installs. Max 3600.",
                    "default": 30
                },
                "use_sudo": {
                    "type": "boolean",
                    "description": "Set true for commands needing root: apt-get, dpkg, systemctl, etc.",
                    "default": False
                },
                "long_running": {
                    "type": "boolean",
                    "description": "Set true for large downloads, compilations, server installs. Streams live output.",
                    "default": False
                },
                "background": {
                    "type": "boolean",
                    "description": "Start in background. Runs without timeout until done. Monitor via task browser.",
                    "default": False
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

Always explain to the user what file you're reading and why.
Set display_content to true when the user wants to SEE the file contents (e.g., "show me the file", "display the contents").""",
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
                },
                "display_content": {
                    "type": "boolean",
                    "description": "If true, display the file contents to the user. Use when user wants to see/view the file.",
                    "default": False
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
    },
    # Linux-specific tools
    {
        "name": "manage_service",
        "description": """Manage systemd services. Use this for:
- Checking service status (is nginx running?)
- Starting/stopping services
- Enabling/disabling services at boot
- Viewing service logs

Always explain what service you're managing and why.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "start", "stop", "restart", "reload", "enable", "disable", "is-active", "logs"],
                    "description": "Action to perform on the service"
                },
                "service": {
                    "type": "string",
                    "description": "Name of the systemd service (e.g., 'nginx', 'ssh', 'docker')"
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of log lines to show (for 'logs' action)",
                    "default": 50
                },
                "explanation": {
                    "type": "string",
                    "description": "What you're doing with this service (shown to user)"
                }
            },
            "required": ["action", "service", "explanation"]
        }
    },
    {
        "name": "manage_process",
        "description": """Manage system processes. Use this for:
- Listing running processes by CPU/memory usage
- Finding processes by name
- Getting process details
- Killing unresponsive processes

Use with care - killing processes can cause data loss.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "find", "kill", "info"],
                    "description": "Action to perform"
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["cpu", "memory"],
                    "description": "How to sort process list",
                    "default": "cpu"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of processes to list",
                    "default": 20
                },
                "name": {
                    "type": "string",
                    "description": "Process name to find or kill"
                },
                "pid": {
                    "type": "integer",
                    "description": "Process ID for kill or info actions"
                },
                "signal": {
                    "type": "string",
                    "enum": ["TERM", "KILL", "HUP", "INT"],
                    "description": "Signal to send when killing",
                    "default": "TERM"
                },
                "explanation": {
                    "type": "string",
                    "description": "What you're doing (shown to user)"
                }
            },
            "required": ["action", "explanation"]
        }
    },
    {
        "name": "network_diagnostics",
        "description": """Perform network diagnostics. Use this for:
- Checking network interface status
- Testing connectivity (ping)
- Viewing open ports
- Checking active connections
- DNS lookups
- Testing if a specific port is open

Helps troubleshoot network issues.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "ping", "ports", "connections", "dns", "check_port", "route"],
                    "description": "Diagnostic action to perform"
                },
                "host": {
                    "type": "string",
                    "description": "Hostname or IP for ping/dns/check_port actions"
                },
                "port": {
                    "type": "integer",
                    "description": "Port number for check_port action"
                },
                "count": {
                    "type": "integer",
                    "description": "Number of pings to send",
                    "default": 4
                },
                "state": {
                    "type": "string",
                    "description": "Connection state filter (established, listening, etc.)",
                    "default": "established"
                },
                "explanation": {
                    "type": "string",
                    "description": "What you're checking (shown to user)"
                }
            },
            "required": ["action", "explanation"]
        }
    },
    {
        "name": "view_logs",
        "description": """View system logs using journalctl. Use this for:
- Viewing recent system logs
- Checking kernel messages
- Viewing boot logs
- Checking service-specific logs
- Searching logs for errors

Essential for troubleshooting system issues.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "log_type": {
                    "type": "string",
                    "enum": ["system", "kernel", "boot", "auth", "cron"],
                    "description": "Type of logs to view. Use 'unit:servicename' for specific services.",
                    "default": "system"
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of log lines to show",
                    "default": 50
                },
                "since": {
                    "type": "string",
                    "description": "Show logs since time (e.g., '1 hour ago', 'today', '2024-01-01')"
                },
                "grep": {
                    "type": "string",
                    "description": "Filter logs by pattern (case insensitive)"
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
        "name": "archive_operations",
        "description": """Work with archive files (tar, zip, 7z). Use this for:
- Listing archive contents
- Extracting archives
- Creating archives from files/directories

Supports tar.gz, tar.bz2, tar.xz, zip, and 7z formats.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "extract", "create"],
                    "description": "Action to perform"
                },
                "archive_path": {
                    "type": "string",
                    "description": "Path to the archive file"
                },
                "destination": {
                    "type": "string",
                    "description": "Extraction destination directory",
                    "default": "."
                },
                "source_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files/directories to include in archive (for create)"
                },
                "compression": {
                    "type": "string",
                    "enum": ["gz", "bz2", "xz", "none"],
                    "description": "Compression type for tar archives",
                    "default": "gz"
                },
                "explanation": {
                    "type": "string",
                    "description": "What you're doing (shown to user)"
                }
            },
            "required": ["action", "archive_path", "explanation"]
        }
    },
    {
        "name": "manage_cron",
        "description": """Manage scheduled tasks (cron jobs). Use this for:
- Listing current cron jobs
- Adding new scheduled tasks
- Removing cron jobs
- Viewing system cron directories

Cron schedule format: minute hour day month weekday (e.g., '0 * * * *' for hourly).""",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "list_system", "add", "remove"],
                    "description": "Action to perform"
                },
                "schedule": {
                    "type": "string",
                    "description": "Cron schedule (e.g., '0 * * * *', '@daily', '@hourly')"
                },
                "command": {
                    "type": "string",
                    "description": "Command to run (for add action)"
                },
                "pattern": {
                    "type": "string",
                    "description": "Pattern to match for removal"
                },
                "explanation": {
                    "type": "string",
                    "description": "What you're scheduling (shown to user)"
                }
            },
            "required": ["action", "explanation"]
        }
    },
    {
        "name": "disk_operations",
        "description": """Check disk space and storage information. Use this for:
- Checking disk usage
- Finding large files
- Viewing directory sizes
- Listing mount points and partitions

Helps manage storage and find space issues.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["usage", "directory_size", "mounts", "partitions", "large_files"],
                    "description": "Action to perform"
                },
                "path": {
                    "type": "string",
                    "description": "Path to check",
                    "default": "/"
                },
                "depth": {
                    "type": "integer",
                    "description": "Directory depth for size analysis",
                    "default": 1
                },
                "min_size": {
                    "type": "string",
                    "description": "Minimum file size for large_files (e.g., '100M', '1G')",
                    "default": "100M"
                },
                "human_readable": {
                    "type": "boolean",
                    "description": "Show sizes in human-readable format",
                    "default": True
                },
                "explanation": {
                    "type": "string",
                    "description": "What you're checking (shown to user)"
                }
            },
            "required": ["action", "explanation"]
        }
    },
    {
        "name": "user_management",
        "description": """View user and login information. Use this for:
- Listing user accounts
- Checking current user info
- Viewing group memberships
- Checking who is logged in
- Viewing recent login history

Read-only operations for security - use run_command for user modifications.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "current", "groups", "who", "last"],
                    "description": "Action to perform"
                },
                "username": {
                    "type": "string",
                    "description": "Username to check groups for"
                },
                "count": {
                    "type": "integer",
                    "description": "Number of recent logins to show",
                    "default": 10
                },
                "explanation": {
                    "type": "string",
                    "description": "What you're checking (shown to user)"
                }
            },
            "required": ["action", "explanation"]
        }
    }
]


class ToolHandler:
    """Handles tool execution and result formatting."""

    def __init__(self):
        self._handlers: dict[str, Callable] = {}
        self._tool_definitions: List[Dict[str, Any]] = []
        self._cache = None

    def set_cache(self, cache) -> None:
        """Attach a ToolResultCache so execute() can check/store results."""
        self._cache = cache

    def register(self, tool_name: str, handler: Callable) -> None:
        """Register a handler function for a tool."""
        self._handlers[tool_name] = handler

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable,
        requires_confirmation: bool = False
    ) -> None:
        """Register a complete tool with definition and handler."""
        # Register the handler
        self._handlers[name] = handler

        # Add tool definition
        self._tool_definitions.append({
            "name": name,
            "description": description,
            "input_schema": input_schema
        })

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> ToolResult:
        """Execute a tool and return the result."""
        from ..stats import get_usage_stats

        if tool_name not in self._handlers:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown tool: {tool_name}",
                user_friendly_message=f"I don't know how to do that yet."
            )

        # Cache lookup
        if self._cache is not None:
            cached = self._cache.get(tool_name, tool_input)
            if cached is not None:
                return cached

        # Track execution statistics
        stats = get_usage_stats()
        start_time = stats.record_tool_start(tool_name)

        try:
            handler = self._handlers[tool_name]
            result = handler(tool_input)
        except Exception as e:
            result = ToolResult(
                success=False,
                output="",
                error=str(e),
                user_friendly_message=f"Something went wrong: {str(e)}"
            )

        # Record stats
        stats.record_tool_end(
            tool_name,
            start_time,
            success=result.success,
            error=result.error
        )

        # Cache store + invalidation (no-ops for non-cacheable tools)
        if self._cache is not None:
            self._cache.set(tool_name, tool_input, result)
            self._cache.process_invalidations(tool_name, tool_input)

        return result

    def get_tool_names(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._handlers.keys())

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Get all tool definitions (built-in + registered)."""
        return BUILTIN_TOOLS + self._tool_definitions

    def get_plugin_tools(self) -> List[Dict[str, Any]]:
        """Get only plugin-registered tool definitions."""
        return self._tool_definitions.copy()


# Legacy alias for backwards compatibility
TOOLS = BUILTIN_TOOLS
