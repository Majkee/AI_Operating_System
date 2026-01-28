"""
Plugin system for AIOS.

Provides:
- Plugin discovery and loading
- Plugin lifecycle management
- Custom tool registration
- Recipe/workflow system
"""

import ast
import logging
import operator
import os
import re
import sys
import json
import importlib
import importlib.util
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, Union
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Safe Expression Evaluator - replaces dangerous eval() for recipe conditions
# ---------------------------------------------------------------------------

# Forbidden patterns that could indicate code injection attempts
FORBIDDEN_PATTERNS = re.compile(
    r'(__\w+__|import|eval|exec|compile|open|globals|locals|vars|'
    r'getattr|setattr|delattr|hasattr|type|isinstance|issubclass|'
    r'callable|classmethod|staticmethod|property|super|'
    r'breakpoint|input|print|exit|quit|help|license|credits|copyright)',
    re.IGNORECASE
)

# Supported comparison operators
SAFE_OPERATORS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}

# Supported boolean operators
BOOL_OPERATORS = {
    ast.And: lambda vals: all(vals),
    ast.Or: lambda vals: any(vals),
}


class SafeExpressionError(Exception):
    """Raised when an expression cannot be safely evaluated."""
    pass


class SafeExpressionEvaluator:
    """
    Safely evaluate simple boolean expressions without using eval().

    Supports:
    - Simple comparisons: context.key == value, context.key > 5
    - Boolean operators: and, or, not
    - Literal values: strings, numbers, booleans, None, lists
    - Context variable access: context.key, context['key']

    Rejects:
    - Function calls
    - Attribute access on non-context objects
    - Any potentially dangerous operations

    Example valid expressions:
    - "context.status == 'success'"
    - "context.count > 0 and context.enabled"
    - "context.value in [1, 2, 3]"
    - "not context.skip"
    """

    def __init__(self, context: Dict[str, Any]):
        self.context = context

    def evaluate(self, expression: str) -> bool:
        """
        Safely evaluate a boolean expression.

        Args:
            expression: A simple boolean expression string

        Returns:
            The boolean result of the expression

        Raises:
            SafeExpressionError: If the expression is invalid or unsafe
        """
        # Check for forbidden patterns first
        if FORBIDDEN_PATTERNS.search(expression):
            raise SafeExpressionError(
                f"Expression contains forbidden operation: {expression}"
            )

        try:
            tree = ast.parse(expression, mode='eval')
        except SyntaxError as e:
            raise SafeExpressionError(f"Invalid expression syntax: {e}")

        try:
            result = self._eval_node(tree.body)
            return bool(result)
        except SafeExpressionError:
            raise
        except Exception as e:
            raise SafeExpressionError(f"Failed to evaluate expression: {e}")

    def _eval_node(self, node: ast.AST) -> Any:
        """Recursively evaluate an AST node."""

        # Literal values
        if isinstance(node, ast.Constant):
            return node.value

        # For Python 3.7 compatibility (Num, Str, etc. are deprecated but may exist)
        if isinstance(node, ast.Num):  # type: ignore
            return node.n  # type: ignore
        if isinstance(node, ast.Str):  # type: ignore
            return node.s  # type: ignore
        if isinstance(node, ast.NameConstant):  # type: ignore
            return node.value  # type: ignore

        # List literals
        if isinstance(node, ast.List):
            return [self._eval_node(elt) for elt in node.elts]

        # Tuple literals
        if isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elt) for elt in node.elts)

        # Dict literals
        if isinstance(node, ast.Dict):
            keys = [self._eval_node(k) if k else None for k in node.keys]
            values = [self._eval_node(v) for v in node.values]
            return dict(zip(keys, values))

        # Name lookup (only 'context' is allowed)
        if isinstance(node, ast.Name):
            if node.id == 'context':
                return self.context
            elif node.id in ('True', 'False', 'None'):
                return {'True': True, 'False': False, 'None': None}[node.id]
            else:
                raise SafeExpressionError(
                    f"Unknown variable '{node.id}'. Only 'context' is allowed."
                )

        # Attribute access (only on context)
        if isinstance(node, ast.Attribute):
            obj = self._eval_node(node.value)
            if obj is not self.context:
                raise SafeExpressionError(
                    f"Attribute access only allowed on 'context', not on {type(obj).__name__}"
                )
            return self.context.get(node.attr)

        # Subscript access (context['key'] or context[0])
        if isinstance(node, ast.Subscript):
            obj = self._eval_node(node.value)
            if obj is not self.context and not isinstance(obj, (list, tuple, dict)):
                raise SafeExpressionError(
                    f"Subscript access only allowed on context or literals"
                )
            key = self._eval_node(node.slice)
            if isinstance(obj, dict):
                return obj.get(key)
            return obj[key]

        # Comparison operators
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                op_type = type(op)
                if op_type not in SAFE_OPERATORS:
                    raise SafeExpressionError(f"Unsupported comparison operator: {op_type.__name__}")
                right = self._eval_node(comparator)
                if not SAFE_OPERATORS[op_type](left, right):
                    return False
                left = right
            return True

        # Boolean operators (and, or)
        if isinstance(node, ast.BoolOp):
            op_type = type(node.op)
            if op_type not in BOOL_OPERATORS:
                raise SafeExpressionError(f"Unsupported boolean operator: {op_type.__name__}")
            values = [self._eval_node(v) for v in node.values]
            return BOOL_OPERATORS[op_type](values)

        # Unary operators (not, -)
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            if isinstance(node.op, ast.Not):
                return not operand
            elif isinstance(node.op, ast.USub):
                return -operand
            elif isinstance(node.op, ast.UAdd):
                return +operand
            else:
                raise SafeExpressionError(f"Unsupported unary operator: {type(node.op).__name__}")

        # Binary operators (+, -, *, /)
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            elif isinstance(node.op, ast.Sub):
                return left - right
            elif isinstance(node.op, ast.Mult):
                return left * right
            elif isinstance(node.op, ast.Div):
                return left / right
            elif isinstance(node.op, ast.Mod):
                return left % right
            else:
                raise SafeExpressionError(f"Unsupported binary operator: {type(node.op).__name__}")

        # IfExp (ternary: a if condition else b)
        if isinstance(node, ast.IfExp):
            test = self._eval_node(node.test)
            if test:
                return self._eval_node(node.body)
            return self._eval_node(node.orelse)

        # Reject everything else (function calls, lambdas, etc.)
        raise SafeExpressionError(
            f"Unsupported expression type: {type(node).__name__}. "
            f"Only simple comparisons and boolean operators are allowed."
        )


def safe_eval_condition(expression: str, context: Dict[str, Any]) -> bool:
    """
    Safely evaluate a recipe condition expression.

    This is a safe replacement for eval() that only allows simple
    boolean expressions with context variable access.

    Args:
        expression: The condition expression to evaluate
        context: The recipe execution context

    Returns:
        True if the condition is met, False otherwise

    Raises:
        SafeExpressionError: If the expression is invalid or unsafe
    """
    evaluator = SafeExpressionEvaluator(context)
    return evaluator.evaluate(expression)


@dataclass
class ToolDefinition:
    """Definition of a tool that can be registered with Claude."""
    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], Any]
    requires_confirmation: bool = False
    category: str = "custom"


@dataclass
class RecipeStep:
    """A single step in a recipe workflow."""
    description: str
    tool_name: str
    tool_params: dict
    condition: Optional[str] = None  # Python expression to evaluate
    on_success: Optional[str] = None  # Next step name
    on_failure: Optional[str] = None  # Step name on failure


@dataclass
class Recipe:
    """
    A pre-defined workflow for common tasks.

    Recipes are sequences of tool calls that accomplish a specific goal.
    """
    name: str
    description: str
    trigger_phrases: List[str]
    steps: List[RecipeStep]
    category: str = "general"
    author: str = "system"
    version: str = "1.0.0"

    def matches(self, user_input: str) -> bool:
        """Check if user input matches this recipe's trigger phrases."""
        input_lower = user_input.lower()
        return any(phrase.lower() in input_lower for phrase in self.trigger_phrases)


@dataclass
class PluginMetadata:
    """Metadata about a plugin."""
    name: str
    version: str
    description: str
    author: str
    homepage: Optional[str] = None
    license: str = "MIT"
    dependencies: List[str] = field(default_factory=list)
    min_aios_version: str = "0.1.0"


class PluginBase(ABC):
    """
    Base class for AIOS plugins.

    Plugins can:
    - Register custom tools
    - Define recipes/workflows
    - Hook into AIOS events
    """

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        pass

    def get_tools(self) -> List[ToolDefinition]:
        """
        Return list of tools provided by this plugin.

        Override this method to register custom tools.
        """
        return []

    def get_recipes(self) -> List[Recipe]:
        """
        Return list of recipes provided by this plugin.

        Override this method to register workflows.
        """
        return []

    def on_load(self) -> None:
        """Called when plugin is loaded."""
        pass

    def on_unload(self) -> None:
        """Called when plugin is unloaded."""
        pass

    def on_session_start(self) -> None:
        """Called when a new AIOS session starts."""
        pass

    def on_session_end(self) -> None:
        """Called when an AIOS session ends."""
        pass


@dataclass
class LoadedPlugin:
    """A loaded plugin instance."""
    instance: PluginBase
    metadata: PluginMetadata
    path: Path
    enabled: bool = True


class PluginManager:
    """
    Manages plugin discovery, loading, and lifecycle.
    """

    # Default plugin directories
    DEFAULT_PLUGIN_DIRS = [
        Path.home() / ".config" / "aios" / "plugins",
        Path("/etc/aios/plugins"),
    ]

    def __init__(self, plugin_dirs: Optional[List[Path]] = None):
        """
        Initialize the plugin manager.

        Args:
            plugin_dirs: List of directories to search for plugins
        """
        self.plugin_dirs = plugin_dirs or self.DEFAULT_PLUGIN_DIRS
        self._plugins: Dict[str, LoadedPlugin] = {}
        self._tools: Dict[str, ToolDefinition] = {}
        self._recipes: Dict[str, Recipe] = {}

    def discover_plugins(self) -> List[Path]:
        """
        Discover available plugins.

        Returns:
            List of paths to plugin modules/packages
        """
        discovered = []

        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                continue

            # Look for Python files
            for py_file in plugin_dir.glob("*.py"):
                if not py_file.name.startswith("_"):
                    discovered.append(py_file)

            # Look for packages (directories with __init__.py)
            for subdir in plugin_dir.iterdir():
                if subdir.is_dir() and (subdir / "__init__.py").exists():
                    discovered.append(subdir)

        return discovered

    def load_plugin(self, path: Path) -> Optional[LoadedPlugin]:
        """
        Load a plugin from a path.

        Args:
            path: Path to plugin module or package

        Returns:
            LoadedPlugin if successful, None otherwise
        """
        try:
            # Determine module name
            if path.is_file():
                module_name = f"aios_plugin_{path.stem}"
                spec = importlib.util.spec_from_file_location(module_name, path)
            else:
                module_name = f"aios_plugin_{path.name}"
                spec = importlib.util.spec_from_file_location(
                    module_name,
                    path / "__init__.py",
                    submodule_search_locations=[str(path)]
                )

            if spec is None or spec.loader is None:
                return None

            # Load the module
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Find plugin class
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, PluginBase) and
                    attr is not PluginBase):
                    plugin_class = attr
                    break

            if plugin_class is None:
                return None

            # Instantiate plugin
            instance = plugin_class()
            metadata = instance.metadata

            # Call on_load hook
            instance.on_load()

            # Register tools and recipes
            for tool in instance.get_tools():
                self._tools[tool.name] = tool

            for recipe in instance.get_recipes():
                self._recipes[recipe.name] = recipe

            loaded = LoadedPlugin(
                instance=instance,
                metadata=metadata,
                path=path,
                enabled=True
            )

            self._plugins[metadata.name] = loaded
            return loaded

        except Exception as e:
            # Log error but don't crash
            print(f"Failed to load plugin from {path}: {e}")
            return None

    def load_all(self) -> List[LoadedPlugin]:
        """
        Discover and load all plugins.

        Returns:
            List of successfully loaded plugins
        """
        loaded = []
        for path in self.discover_plugins():
            plugin = self.load_plugin(path)
            if plugin:
                loaded.append(plugin)
        return loaded

    def unload_plugin(self, name: str) -> bool:
        """
        Unload a plugin by name.

        Args:
            name: Plugin name

        Returns:
            True if unloaded, False if not found
        """
        if name not in self._plugins:
            return False

        plugin = self._plugins[name]

        # Call on_unload hook
        plugin.instance.on_unload()

        # Remove tools and recipes
        for tool in plugin.instance.get_tools():
            self._tools.pop(tool.name, None)

        for recipe in plugin.instance.get_recipes():
            self._recipes.pop(recipe.name, None)

        del self._plugins[name]
        return True

    def enable_plugin(self, name: str) -> bool:
        """Enable a loaded plugin."""
        if name in self._plugins:
            self._plugins[name].enabled = True
            return True
        return False

    def disable_plugin(self, name: str) -> bool:
        """Disable a loaded plugin."""
        if name in self._plugins:
            self._plugins[name].enabled = False
            return True
        return False

    def get_plugin(self, name: str) -> Optional[LoadedPlugin]:
        """Get a loaded plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> List[PluginMetadata]:
        """List all loaded plugins."""
        return [p.metadata for p in self._plugins.values()]

    def get_all_tools(self) -> Dict[str, ToolDefinition]:
        """Get all registered tools from plugins."""
        return {
            name: tool for name, tool in self._tools.items()
            if self._is_tool_enabled(name)
        }

    def get_all_recipes(self) -> Dict[str, Recipe]:
        """Get all registered recipes from plugins."""
        return dict(self._recipes)

    def find_matching_recipe(self, user_input: str) -> Optional[Recipe]:
        """
        Find a recipe that matches the user's input.

        Args:
            user_input: User's message

        Returns:
            Matching recipe or None
        """
        for recipe in self._recipes.values():
            if recipe.matches(user_input):
                return recipe
        return None

    def _is_tool_enabled(self, tool_name: str) -> bool:
        """Check if a tool's plugin is enabled."""
        for plugin in self._plugins.values():
            for tool in plugin.instance.get_tools():
                if tool.name == tool_name:
                    return plugin.enabled
        return True

    def session_started(self) -> None:
        """Notify all plugins that a session has started."""
        for plugin in self._plugins.values():
            if plugin.enabled:
                plugin.instance.on_session_start()

    def session_ended(self) -> None:
        """Notify all plugins that a session has ended."""
        for plugin in self._plugins.values():
            if plugin.enabled:
                plugin.instance.on_session_end()


class RecipeExecutor:
    """
    Executes recipe workflows.
    """

    def __init__(self, tool_executor: Callable[[str, dict], Any]):
        """
        Initialize recipe executor.

        Args:
            tool_executor: Function to execute tools (name, params) -> result
        """
        self.tool_executor = tool_executor
        self._context: Dict[str, Any] = {}

    def execute(
        self,
        recipe: Recipe,
        initial_context: Optional[Dict[str, Any]] = None,
        on_step: Optional[Callable[[RecipeStep, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Execute a recipe.

        Args:
            recipe: Recipe to execute
            initial_context: Initial context variables
            on_step: Callback for each step (step, step_number)

        Returns:
            Final context with all results
        """
        self._context = initial_context or {}
        self._context["_recipe"] = recipe.name
        self._context["_results"] = []

        for i, step in enumerate(recipe.steps):
            # Notify callback
            if on_step:
                on_step(step, i)

            # Check condition using safe expression evaluator (no eval())
            if step.condition:
                try:
                    if not safe_eval_condition(step.condition, self._context):
                        logger.debug(f"Recipe step {i} skipped: condition not met")
                        continue
                except SafeExpressionError as e:
                    logger.warning(f"Recipe step {i} condition failed: {e}")
                    self._context["_results"].append({
                        "step": i,
                        "tool": step.tool_name,
                        "success": False,
                        "error": f"Condition evaluation failed: {e}"
                    })
                    continue

            # Execute step
            try:
                # Interpolate params with context
                params = self._interpolate_params(step.tool_params)
                result = self.tool_executor(step.tool_name, params)

                self._context["_results"].append({
                    "step": i,
                    "tool": step.tool_name,
                    "success": True,
                    "result": result
                })
                self._context[f"step_{i}_result"] = result

            except Exception as e:
                self._context["_results"].append({
                    "step": i,
                    "tool": step.tool_name,
                    "success": False,
                    "error": str(e)
                })

        return self._context

    def _interpolate_params(self, params: dict) -> dict:
        """Interpolate context variables into params."""
        result = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("$"):
                var_name = value[1:]
                result[key] = self._context.get(var_name, value)
            elif isinstance(value, dict):
                result[key] = self._interpolate_params(value)
            else:
                result[key] = value
        return result


# Built-in recipes
BUILTIN_RECIPES = [
    Recipe(
        name="disk_cleanup",
        description="Find and optionally remove large files to free disk space",
        trigger_phrases=[
            "clean up disk",
            "free disk space",
            "disk is full",
            "running out of space"
        ],
        steps=[
            RecipeStep(
                description="Check current disk usage",
                tool_name="get_system_info",
                tool_params={"info_type": "disk"}
            ),
            RecipeStep(
                description="Find large files in Downloads",
                tool_name="search_files",
                tool_params={
                    "query": "*",
                    "location": "~/Downloads",
                    "search_type": "filename"
                }
            ),
            RecipeStep(
                description="Find cache directories",
                tool_name="run_command",
                tool_params={
                    "command": "du -sh ~/.cache/* 2>/dev/null | sort -rh | head -10",
                    "explanation": "Finding largest cache directories"
                }
            )
        ],
        category="maintenance"
    ),
    Recipe(
        name="system_health",
        description="Check overall system health and status",
        trigger_phrases=[
            "system health",
            "how is my system",
            "system status",
            "check my computer"
        ],
        steps=[
            RecipeStep(
                description="Check disk usage",
                tool_name="get_system_info",
                tool_params={"info_type": "disk"}
            ),
            RecipeStep(
                description="Check memory usage",
                tool_name="get_system_info",
                tool_params={"info_type": "memory"}
            ),
            RecipeStep(
                description="Check CPU usage",
                tool_name="get_system_info",
                tool_params={"info_type": "cpu"}
            ),
            RecipeStep(
                description="Check running processes",
                tool_name="get_system_info",
                tool_params={"info_type": "processes"}
            )
        ],
        category="monitoring"
    ),
    Recipe(
        name="find_duplicates",
        description="Find duplicate files in a directory",
        trigger_phrases=[
            "find duplicates",
            "duplicate files",
            "same files",
            "remove duplicates"
        ],
        steps=[
            RecipeStep(
                description="Find files by size to identify potential duplicates",
                tool_name="run_command",
                tool_params={
                    "command": "find ~ -type f -size +1M -exec ls -lh {} \\; 2>/dev/null | sort -k5 -rh | head -50",
                    "explanation": "Looking for large files that might be duplicates"
                }
            )
        ],
        category="organization"
    ),
    Recipe(
        name="backup_documents",
        description="Create a backup of important documents",
        trigger_phrases=[
            "backup documents",
            "backup my files",
            "save my documents",
            "create backup"
        ],
        steps=[
            RecipeStep(
                description="List documents to backup",
                tool_name="list_directory",
                tool_params={"path": "~/Documents"}
            ),
            RecipeStep(
                description="Create backup archive",
                tool_name="run_command",
                tool_params={
                    "command": "tar -czvf ~/Documents_backup_$(date +%Y%m%d).tar.gz ~/Documents",
                    "explanation": "Creating compressed backup of Documents folder",
                    "requires_confirmation": True
                }
            )
        ],
        category="backup"
    )
]


# Global plugin manager instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager instance."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
        # Register built-in recipes
        for recipe in BUILTIN_RECIPES:
            _plugin_manager._recipes[recipe.name] = recipe
    return _plugin_manager


def create_simple_plugin(
    name: str,
    version: str,
    description: str,
    tools: Optional[List[ToolDefinition]] = None,
    recipes: Optional[List[Recipe]] = None
) -> Type[PluginBase]:
    """
    Factory function to create a simple plugin class.

    Useful for quick plugin creation without subclassing.

    Example:
        MyPlugin = create_simple_plugin(
            name="my-plugin",
            version="1.0.0",
            description="My custom plugin",
            tools=[
                ToolDefinition(
                    name="my_tool",
                    description="Does something",
                    input_schema={...},
                    handler=my_handler
                )
            ]
        )
    """
    _tools = tools or []
    _recipes = recipes or []

    class SimplePlugin(PluginBase):
        @property
        def metadata(self) -> PluginMetadata:
            return PluginMetadata(
                name=name,
                version=version,
                description=description,
                author="user"
            )

        def get_tools(self) -> List[ToolDefinition]:
            return _tools

        def get_recipes(self) -> List[Recipe]:
            return _recipes

    return SimplePlugin
