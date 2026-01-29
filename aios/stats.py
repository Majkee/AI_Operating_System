"""
Usage statistics tracking for AIOS.

Tracks execution counts, success rates, and timing for:
- Tools
- Recipes
- Skills
"""

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict


@dataclass
class ToolStats:
    """Statistics for a single tool."""
    name: str
    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_duration_ms: float = 0.0
    last_executed: Optional[str] = None
    last_error: Optional[str] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.execution_count == 0:
            return 0.0
        return (self.success_count / self.execution_count) * 100

    @property
    def avg_duration_ms(self) -> float:
        """Calculate average execution duration."""
        if self.execution_count == 0:
            return 0.0
        return self.total_duration_ms / self.execution_count

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_duration_ms": self.total_duration_ms,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "success_rate": round(self.success_rate, 1),
            "last_executed": self.last_executed,
            "last_error": self.last_error,
        }


@dataclass
class RecipeStats:
    """Statistics for a single recipe."""
    name: str
    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_steps_executed: int = 0
    total_duration_ms: float = 0.0
    last_executed: Optional[str] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.execution_count == 0:
            return 0.0
        return (self.success_count / self.execution_count) * 100

    @property
    def avg_duration_ms(self) -> float:
        """Calculate average execution duration."""
        if self.execution_count == 0:
            return 0.0
        return self.total_duration_ms / self.execution_count

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_steps_executed": self.total_steps_executed,
            "total_duration_ms": self.total_duration_ms,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "success_rate": round(self.success_rate, 1),
            "last_executed": self.last_executed,
        }


@dataclass
class SkillStats:
    """Statistics for a skill."""
    name: str
    tools_provided: int = 0
    recipes_provided: int = 0
    tool_executions: int = 0
    recipe_executions: int = 0
    loaded_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "tools_provided": self.tools_provided,
            "recipes_provided": self.recipes_provided,
            "tool_executions": self.tool_executions,
            "recipe_executions": self.recipe_executions,
            "loaded_at": self.loaded_at,
        }


# Backwards compatibility alias
PluginStats = SkillStats


class UsageStatistics:
    """
    Centralized usage statistics tracker.

    Tracks:
    - Tool execution counts, success rates, durations
    - Recipe execution counts and step completions
    - Skill usage
    - Session-level aggregates

    Stats are persisted to disk and can be aggregated across sessions.
    """

    def __init__(self, stats_dir: Optional[Path] = None):
        """Initialize usage statistics tracker.

        Args:
            stats_dir: Directory for stats persistence. Defaults to ~/.config/aios/stats/
        """
        if stats_dir is None:
            stats_dir = Path.home() / ".config" / "aios" / "stats"
        self._stats_dir = stats_dir
        self._stats_dir.mkdir(parents=True, exist_ok=True)

        # Session tracking
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_start = datetime.now()

        # Tool statistics
        self._tool_stats: Dict[str, ToolStats] = {}

        # Recipe statistics
        self._recipe_stats: Dict[str, RecipeStats] = {}

        # Skill statistics
        self._skill_stats: Dict[str, SkillStats] = {}

        # Mapping of tools to skills (for attribution)
        self._tool_to_skill: Dict[str, str] = {}
        self._recipe_to_skill: Dict[str, str] = {}

        # Session totals
        self._total_tool_executions = 0
        self._total_recipe_executions = 0
        self._total_errors = 0

        # Load aggregate stats
        self._aggregate_stats = self._load_aggregate_stats()

    # =========================================================================
    # Tool Statistics
    # =========================================================================

    def record_tool_start(self, tool_name: str) -> float:
        """Record the start of a tool execution.

        Args:
            tool_name: Name of the tool being executed.

        Returns:
            Start timestamp for duration calculation.
        """
        return time.time()

    def record_tool_end(
        self,
        tool_name: str,
        start_time: float,
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """Record the end of a tool execution.

        Args:
            tool_name: Name of the tool.
            start_time: Timestamp from record_tool_start().
            success: Whether execution succeeded.
            error: Error message if failed.
        """
        duration_ms = (time.time() - start_time) * 1000

        if tool_name not in self._tool_stats:
            self._tool_stats[tool_name] = ToolStats(name=tool_name)

        stats = self._tool_stats[tool_name]
        stats.execution_count += 1
        stats.total_duration_ms += duration_ms
        stats.last_executed = datetime.now().isoformat()

        if success:
            stats.success_count += 1
        else:
            stats.failure_count += 1
            stats.last_error = error
            self._total_errors += 1

        self._total_tool_executions += 1

        # Attribute to skill if known
        if tool_name in self._tool_to_skill:
            skill_name = self._tool_to_skill[tool_name]
            if skill_name in self._skill_stats:
                self._skill_stats[skill_name].tool_executions += 1

    def get_tool_stats(self, tool_name: str) -> Optional[ToolStats]:
        """Get statistics for a specific tool."""
        return self._tool_stats.get(tool_name)

    def get_all_tool_stats(self) -> Dict[str, ToolStats]:
        """Get statistics for all tools."""
        return self._tool_stats.copy()

    def get_top_tools(self, limit: int = 10) -> List[ToolStats]:
        """Get the most frequently used tools."""
        sorted_tools = sorted(
            self._tool_stats.values(),
            key=lambda t: t.execution_count,
            reverse=True
        )
        return sorted_tools[:limit]

    # =========================================================================
    # Recipe Statistics
    # =========================================================================

    def record_recipe_start(self, recipe_name: str) -> float:
        """Record the start of a recipe execution.

        Args:
            recipe_name: Name of the recipe being executed.

        Returns:
            Start timestamp for duration calculation.
        """
        return time.time()

    def record_recipe_end(
        self,
        recipe_name: str,
        start_time: float,
        success: bool,
        steps_executed: int = 0
    ) -> None:
        """Record the end of a recipe execution.

        Args:
            recipe_name: Name of the recipe.
            start_time: Timestamp from record_recipe_start().
            success: Whether all steps succeeded.
            steps_executed: Number of steps that were executed.
        """
        duration_ms = (time.time() - start_time) * 1000

        if recipe_name not in self._recipe_stats:
            self._recipe_stats[recipe_name] = RecipeStats(name=recipe_name)

        stats = self._recipe_stats[recipe_name]
        stats.execution_count += 1
        stats.total_duration_ms += duration_ms
        stats.total_steps_executed += steps_executed
        stats.last_executed = datetime.now().isoformat()

        if success:
            stats.success_count += 1
        else:
            stats.failure_count += 1
            self._total_errors += 1

        self._total_recipe_executions += 1

        # Attribute to skill if known
        if recipe_name in self._recipe_to_skill:
            skill_name = self._recipe_to_skill[recipe_name]
            if skill_name in self._skill_stats:
                self._skill_stats[skill_name].recipe_executions += 1

    def get_recipe_stats(self, recipe_name: str) -> Optional[RecipeStats]:
        """Get statistics for a specific recipe."""
        return self._recipe_stats.get(recipe_name)

    def get_all_recipe_stats(self) -> Dict[str, RecipeStats]:
        """Get statistics for all recipes."""
        return self._recipe_stats.copy()

    # =========================================================================
    # Skill Statistics
    # =========================================================================

    def register_skill(
        self,
        skill_name: str,
        tools: List[str],
        recipes: List[str]
    ) -> None:
        """Register a skill and its provided tools/recipes.

        Args:
            skill_name: Name of the skill.
            tools: List of tool names provided by the skill.
            recipes: List of recipe names provided by the skill.
        """
        self._skill_stats[skill_name] = SkillStats(
            name=skill_name,
            tools_provided=len(tools),
            recipes_provided=len(recipes),
            loaded_at=datetime.now().isoformat()
        )

        # Map tools and recipes to skill for attribution
        for tool in tools:
            self._tool_to_skill[tool] = skill_name
        for recipe in recipes:
            self._recipe_to_skill[recipe] = skill_name

    def get_skill_stats(self, skill_name: str) -> Optional[SkillStats]:
        """Get statistics for a specific skill."""
        return self._skill_stats.get(skill_name)

    def get_all_skill_stats(self) -> Dict[str, SkillStats]:
        """Get statistics for all skills."""
        return self._skill_stats.copy()

    # Backwards compatibility aliases
    def register_plugin(self, plugin_name: str, tools: List[str], recipes: List[str]) -> None:
        """Alias for register_skill (backwards compatibility)."""
        return self.register_skill(plugin_name, tools, recipes)

    def get_plugin_stats(self, plugin_name: str) -> Optional[SkillStats]:
        """Alias for get_skill_stats (backwards compatibility)."""
        return self.get_skill_stats(plugin_name)

    def get_all_plugin_stats(self) -> Dict[str, SkillStats]:
        """Alias for get_all_skill_stats (backwards compatibility)."""
        return self.get_all_skill_stats()

    # =========================================================================
    # Session Statistics
    # =========================================================================

    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary statistics for the current session."""
        duration = datetime.now() - self._session_start
        duration_minutes = duration.total_seconds() / 60

        return {
            "session_id": self._session_id,
            "started_at": self._session_start.isoformat(),
            "duration_minutes": round(duration_minutes, 1),
            "total_tool_executions": self._total_tool_executions,
            "total_recipe_executions": self._total_recipe_executions,
            "total_errors": self._total_errors,
            "unique_tools_used": len(self._tool_stats),
            "unique_recipes_used": len(self._recipe_stats),
            "skills_active": len(self._skill_stats),
        }

    # =========================================================================
    # Aggregate Statistics (All-Time)
    # =========================================================================

    def _load_aggregate_stats(self) -> Dict[str, Any]:
        """Load aggregate statistics from disk."""
        aggregate_file = self._stats_dir / "aggregate.json"
        if aggregate_file.exists():
            try:
                with open(aggregate_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "total_sessions": 0,
            "total_tool_executions": 0,
            "total_recipe_executions": 0,
            "tools": {},
            "recipes": {},
            "first_session": None,
            "last_updated": None,
        }

    def _save_aggregate_stats(self) -> None:
        """Save aggregate statistics to disk."""
        aggregate_file = self._stats_dir / "aggregate.json"
        try:
            with open(aggregate_file, "w") as f:
                json.dump(self._aggregate_stats, f, indent=2)
        except IOError:
            pass

    def save_session_stats(self) -> None:
        """Save current session stats and update aggregates."""
        # Save session-specific stats
        session_file = self._stats_dir / f"session_{self._session_id}.json"
        session_data = {
            "session": self.get_session_summary(),
            "tools": {name: stats.to_dict() for name, stats in self._tool_stats.items()},
            "recipes": {name: stats.to_dict() for name, stats in self._recipe_stats.items()},
            "skills": {name: stats.to_dict() for name, stats in self._skill_stats.items()},
        }
        try:
            with open(session_file, "w") as f:
                json.dump(session_data, f, indent=2)
        except IOError:
            pass

        # Update aggregate stats
        self._aggregate_stats["total_sessions"] += 1
        self._aggregate_stats["total_tool_executions"] += self._total_tool_executions
        self._aggregate_stats["total_recipe_executions"] += self._total_recipe_executions
        self._aggregate_stats["last_updated"] = datetime.now().isoformat()

        if self._aggregate_stats["first_session"] is None:
            self._aggregate_stats["first_session"] = self._session_start.isoformat()

        # Merge tool stats into aggregate
        for name, stats in self._tool_stats.items():
            if name not in self._aggregate_stats["tools"]:
                self._aggregate_stats["tools"][name] = {
                    "execution_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                }
            agg = self._aggregate_stats["tools"][name]
            agg["execution_count"] += stats.execution_count
            agg["success_count"] += stats.success_count
            agg["failure_count"] += stats.failure_count

        # Merge recipe stats into aggregate
        for name, stats in self._recipe_stats.items():
            if name not in self._aggregate_stats["recipes"]:
                self._aggregate_stats["recipes"][name] = {
                    "execution_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                }
            agg = self._aggregate_stats["recipes"][name]
            agg["execution_count"] += stats.execution_count
            agg["success_count"] += stats.success_count
            agg["failure_count"] += stats.failure_count

        self._save_aggregate_stats()

    def get_aggregate_stats(self) -> Dict[str, Any]:
        """Get all-time aggregate statistics."""
        # Calculate success rates for aggregate stats
        tools_with_rates = {}
        for name, stats in self._aggregate_stats.get("tools", {}).items():
            count = stats.get("execution_count", 0)
            success = stats.get("success_count", 0)
            rate = (success / count * 100) if count > 0 else 0.0
            tools_with_rates[name] = {
                **stats,
                "success_rate": round(rate, 1)
            }

        recipes_with_rates = {}
        for name, stats in self._aggregate_stats.get("recipes", {}).items():
            count = stats.get("execution_count", 0)
            success = stats.get("success_count", 0)
            rate = (success / count * 100) if count > 0 else 0.0
            recipes_with_rates[name] = {
                **stats,
                "success_rate": round(rate, 1)
            }

        return {
            "total_sessions": self._aggregate_stats.get("total_sessions", 0),
            "total_tool_executions": self._aggregate_stats.get("total_tool_executions", 0),
            "total_recipe_executions": self._aggregate_stats.get("total_recipe_executions", 0),
            "first_session": self._aggregate_stats.get("first_session"),
            "last_updated": self._aggregate_stats.get("last_updated"),
            "tools": tools_with_rates,
            "recipes": recipes_with_rates,
        }

    def get_top_tools_alltime(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most frequently used tools across all sessions."""
        tools = self._aggregate_stats.get("tools", {})
        sorted_tools = sorted(
            tools.items(),
            key=lambda x: x[1].get("execution_count", 0),
            reverse=True
        )
        result = []
        for name, stats in sorted_tools[:limit]:
            count = stats.get("execution_count", 0)
            success = stats.get("success_count", 0)
            rate = (success / count * 100) if count > 0 else 0.0
            result.append({
                "name": name,
                "execution_count": count,
                "success_rate": round(rate, 1),
            })
        return result

    def get_top_recipes_alltime(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most frequently used recipes across all sessions."""
        recipes = self._aggregate_stats.get("recipes", {})
        sorted_recipes = sorted(
            recipes.items(),
            key=lambda x: x[1].get("execution_count", 0),
            reverse=True
        )
        result = []
        for name, stats in sorted_recipes[:limit]:
            count = stats.get("execution_count", 0)
            success = stats.get("success_count", 0)
            rate = (success / count * 100) if count > 0 else 0.0
            result.append({
                "name": name,
                "execution_count": count,
                "success_rate": round(rate, 1),
            })
        return result


# Global instance
_usage_stats: Optional[UsageStatistics] = None


def get_usage_stats() -> UsageStatistics:
    """Get the global usage statistics instance."""
    global _usage_stats
    if _usage_stats is None:
        _usage_stats = UsageStatistics()
    return _usage_stats


def reset_usage_stats() -> None:
    """Reset the global usage statistics instance (for testing)."""
    global _usage_stats
    _usage_stats = None
