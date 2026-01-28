# AIOS Plugin System

AIOS supports plugins that extend its functionality with custom tools and workflows.

## Overview

Plugins can:
- Add new tools that Claude can use
- Define recipes (pre-built workflows) for common tasks
- Hook into AIOS lifecycle events

## Plugin Locations

AIOS looks for plugins in these directories:

1. `~/.config/aios/plugins/` (user plugins)
2. `/etc/aios/plugins/` (system-wide plugins)

## Creating a Plugin

### Basic Plugin Structure

Create a Python file in the plugins directory:

```python
# ~/.config/aios/plugins/my_plugin.py

from aios.plugins import PluginBase, PluginMetadata, ToolDefinition

class MyPlugin(PluginBase):
    @property
    def metadata(self):
        return PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            description="My custom AIOS plugin",
            author="Your Name",
            homepage="https://github.com/you/my-plugin",  # optional
            license="MIT"  # optional, defaults to MIT
        )

    def get_tools(self):
        """Return list of tools this plugin provides."""
        return [
            ToolDefinition(
                name="my_custom_tool",
                description="Does something useful that Claude can invoke",
                input_schema={
                    "type": "object",
                    "properties": {
                        "param1": {
                            "type": "string",
                            "description": "First parameter"
                        },
                        "param2": {
                            "type": "integer",
                            "description": "Second parameter"
                        }
                    },
                    "required": ["param1"]
                },
                handler=self.handle_my_tool,
                requires_confirmation=False,  # Set True for dangerous operations
                category="utilities"
            )
        ]

    def handle_my_tool(self, params):
        """Handle tool invocation from Claude."""
        param1 = params.get("param1")
        param2 = params.get("param2", 0)

        # Do something useful
        result = f"Processed {param1} with value {param2}"

        return {
            "success": True,
            "output": result,
            "message": "Operation completed successfully"
        }
```

### Plugin Lifecycle Hooks

```python
class MyPlugin(PluginBase):
    # ... metadata and tools ...

    def on_load(self):
        """Called when plugin is loaded."""
        print("Plugin loaded!")
        # Initialize resources, connections, etc.

    def on_unload(self):
        """Called when plugin is unloaded."""
        print("Plugin unloading...")
        # Clean up resources

    def on_session_start(self):
        """Called when user starts an AIOS session."""
        pass

    def on_session_end(self):
        """Called when user ends an AIOS session."""
        pass
```

### Quick Plugin Creation

For simple plugins, use the factory function:

```python
from aios.plugins import create_simple_plugin, ToolDefinition

def my_handler(params):
    return {"success": True, "output": "Hello!"}

MyPlugin = create_simple_plugin(
    name="simple-plugin",
    version="1.0.0",
    description="A simple plugin",
    tools=[
        ToolDefinition(
            name="say_hello",
            description="Says hello",
            input_schema={"type": "object", "properties": {}},
            handler=my_handler
        )
    ]
)
```

## Creating Recipes

Recipes are pre-defined workflows that run multiple tools in sequence.

```python
from aios.plugins import PluginBase, Recipe, RecipeStep

class MyPlugin(PluginBase):
    # ... metadata ...

    def get_recipes(self):
        return [
            Recipe(
                name="morning_report",
                description="Generate a morning system report",
                trigger_phrases=[
                    "morning report",
                    "daily status",
                    "how is my system today"
                ],
                steps=[
                    RecipeStep(
                        description="Check disk space",
                        tool_name="get_system_info",
                        tool_params={"info_type": "disk"}
                    ),
                    RecipeStep(
                        description="Check memory usage",
                        tool_name="get_system_info",
                        tool_params={"info_type": "memory"}
                    ),
                    RecipeStep(
                        description="List recent downloads",
                        tool_name="list_directory",
                        tool_params={"path": "~/Downloads"}
                    )
                ],
                category="monitoring",
                author="Your Name"
            )
        ]
```

### Conditional Steps

Steps can have conditions that determine whether they run:

```python
RecipeStep(
    description="Clean cache if disk usage > 80%",
    tool_name="run_command",
    tool_params={
        "command": "rm -rf ~/.cache/thumbnails/*",
        "requires_confirmation": True
    },
    condition="context.get('disk_usage_percent', 0) > 80"
)
```

### Parameter Interpolation

Use `$variable_name` to reference context variables:

```python
RecipeStep(
    description="Backup the selected folder",
    tool_name="run_command",
    tool_params={
        "command": "tar -czf backup.tar.gz $selected_folder"
    }
)
```

## Built-in Recipes

AIOS includes these recipes out of the box:

| Recipe | Triggers | Description |
|--------|----------|-------------|
| `disk_cleanup` | "clean up disk", "free space", "disk is full" | Find large files and cache directories |
| `system_health` | "system health", "system status", "check my computer" | Check disk, memory, CPU, and processes |
| `find_duplicates` | "find duplicates", "duplicate files" | Find potential duplicate files by size |
| `backup_documents` | "backup documents", "backup my files" | Create compressed backup of Documents |

## Plugin Package Structure

For complex plugins, use a package structure:

```
~/.config/aios/plugins/
└── my_plugin/
    ├── __init__.py      # Plugin class definition
    ├── tools.py         # Tool handlers
    ├── recipes.py       # Recipe definitions
    └── utils.py         # Helper functions
```

**`__init__.py`:**
```python
from aios.plugins import PluginBase, PluginMetadata
from .tools import get_tools
from .recipes import get_recipes

class MyPlugin(PluginBase):
    @property
    def metadata(self):
        return PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            description="My plugin package",
            author="Your Name"
        )

    def get_tools(self):
        return get_tools()

    def get_recipes(self):
        return get_recipes()
```

## Tool Definition Reference

### ToolDefinition Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | str | Yes | Unique tool identifier (snake_case) |
| `description` | str | Yes | What the tool does (shown to Claude) |
| `input_schema` | dict | Yes | JSON Schema for parameters |
| `handler` | callable | Yes | Function to handle invocation |
| `requires_confirmation` | bool | No | Prompt user before running (default: False) |
| `category` | str | No | Tool category (default: "custom") |

### Input Schema Example

```python
input_schema = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "Path to the file"
        },
        "options": {
            "type": "object",
            "properties": {
                "recursive": {"type": "boolean"},
                "max_depth": {"type": "integer"}
            }
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["file_path"]
}
```

### Handler Return Format

```python
def my_handler(params):
    # Success
    return {
        "success": True,
        "output": "Raw output for Claude to process",
        "message": "User-friendly message to display"
    }

    # Failure
    return {
        "success": False,
        "error": "What went wrong",
        "message": "User-friendly error message"
    }
```

## Plugin Manager API

### Loading Plugins Programmatically

```python
from aios.plugins import PluginManager

manager = PluginManager()

# Discover and load all plugins
loaded = manager.load_all()
print(f"Loaded {len(loaded)} plugins")

# Load a specific plugin
plugin = manager.load_plugin(Path("~/.config/aios/plugins/my_plugin.py"))

# List loaded plugins
for metadata in manager.list_plugins():
    print(f"{metadata.name} v{metadata.version}")

# Get all tools from plugins
tools = manager.get_all_tools()

# Get all recipes
recipes = manager.get_all_recipes()

# Find recipe matching user input
recipe = manager.find_matching_recipe("clean up my disk")
```

### Enabling/Disabling Plugins

```python
manager.disable_plugin("my-plugin")  # Temporarily disable
manager.enable_plugin("my-plugin")   # Re-enable
manager.unload_plugin("my-plugin")   # Fully unload
```

## Example Plugins

### Weather Plugin

```python
import requests
from aios.plugins import PluginBase, PluginMetadata, ToolDefinition

class WeatherPlugin(PluginBase):
    @property
    def metadata(self):
        return PluginMetadata(
            name="weather",
            version="1.0.0",
            description="Get weather information",
            author="AIOS Community"
        )

    def get_tools(self):
        return [
            ToolDefinition(
                name="get_weather",
                description="Get current weather for a location",
                input_schema={
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name or zip code"
                        }
                    },
                    "required": ["location"]
                },
                handler=self.get_weather
            )
        ]

    def get_weather(self, params):
        location = params["location"]
        # Call weather API...
        return {
            "success": True,
            "output": f"Weather in {location}: 72°F, Sunny",
            "message": f"Current weather for {location}"
        }
```

### Notes Plugin

```python
from pathlib import Path
from aios.plugins import PluginBase, PluginMetadata, ToolDefinition

class NotesPlugin(PluginBase):
    NOTES_DIR = Path.home() / ".aios_notes"

    @property
    def metadata(self):
        return PluginMetadata(
            name="notes",
            version="1.0.0",
            description="Quick notes management",
            author="AIOS Community"
        )

    def on_load(self):
        self.NOTES_DIR.mkdir(exist_ok=True)

    def get_tools(self):
        return [
            ToolDefinition(
                name="save_note",
                description="Save a quick note",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["title", "content"]
                },
                handler=self.save_note
            ),
            ToolDefinition(
                name="list_notes",
                description="List all saved notes",
                input_schema={"type": "object", "properties": {}},
                handler=self.list_notes
            )
        ]

    def save_note(self, params):
        title = params["title"]
        content = params["content"]
        note_path = self.NOTES_DIR / f"{title}.txt"
        note_path.write_text(content)
        return {"success": True, "message": f"Saved note: {title}"}

    def list_notes(self, params):
        notes = list(self.NOTES_DIR.glob("*.txt"))
        output = "\n".join(n.stem for n in notes)
        return {"success": True, "output": output or "No notes found"}
```

## Best Practices

1. **Use descriptive tool names** - Claude uses the name and description to decide when to use your tool

2. **Validate input** - Don't trust that params match your schema; validate in your handler

3. **Handle errors gracefully** - Return error info rather than raising exceptions

4. **Use `requires_confirmation`** - For any operation that modifies files or system state

5. **Keep tools focused** - One tool should do one thing well

6. **Document your schema** - Use the `description` field in properties

7. **Test your plugins** - Create unit tests for your handlers

## Troubleshooting

### Plugin not loading

1. Check the file is in a plugin directory
2. Verify the class inherits from `PluginBase`
3. Check for syntax errors: `python -m py_compile your_plugin.py`

### Tool not appearing

1. Verify `get_tools()` returns a list
2. Check tool name is unique
3. Ensure plugin is enabled

### Recipe not triggering

1. Check trigger phrases are lowercase
2. Verify the phrase appears in user input
3. Test with `recipe.matches("user input")`

## Contributing Plugins

Share your plugins with the community:

1. Create a GitHub repository
2. Include installation instructions
3. Add to the AIOS plugin registry (coming soon)
