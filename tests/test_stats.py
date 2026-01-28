"""
Tests for usage statistics tracking.
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from aios.stats import (
    UsageStatistics,
    ToolStats,
    RecipeStats,
    PluginStats,
    get_usage_stats,
    reset_usage_stats,
)


@pytest.fixture
def temp_stats_dir():
    """Create a temporary directory for stats storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def stats(temp_stats_dir):
    """Create a UsageStatistics instance with temp storage."""
    return UsageStatistics(stats_dir=temp_stats_dir)


class TestToolStats:
    """Tests for ToolStats dataclass."""

    def test_initial_state(self):
        """Test initial stats values."""
        stats = ToolStats(name="test_tool")
        assert stats.execution_count == 0
        assert stats.success_count == 0
        assert stats.failure_count == 0
        assert stats.success_rate == 0.0
        assert stats.avg_duration_ms == 0.0

    def test_success_rate_calculation(self):
        """Test success rate is calculated correctly."""
        stats = ToolStats(
            name="test_tool",
            execution_count=10,
            success_count=8,
            failure_count=2,
        )
        assert stats.success_rate == 80.0

    def test_avg_duration_calculation(self):
        """Test average duration is calculated correctly."""
        stats = ToolStats(
            name="test_tool",
            execution_count=5,
            total_duration_ms=500.0,
        )
        assert stats.avg_duration_ms == 100.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = ToolStats(
            name="test_tool",
            execution_count=10,
            success_count=8,
            failure_count=2,
            total_duration_ms=1000.0,
        )
        d = stats.to_dict()
        assert d["name"] == "test_tool"
        assert d["execution_count"] == 10
        assert d["success_rate"] == 80.0
        assert d["avg_duration_ms"] == 100.0


class TestRecipeStats:
    """Tests for RecipeStats dataclass."""

    def test_initial_state(self):
        """Test initial stats values."""
        stats = RecipeStats(name="test_recipe")
        assert stats.execution_count == 0
        assert stats.success_rate == 0.0

    def test_success_rate_calculation(self):
        """Test success rate is calculated correctly."""
        stats = RecipeStats(
            name="test_recipe",
            execution_count=5,
            success_count=4,
            failure_count=1,
        )
        assert stats.success_rate == 80.0


class TestUsageStatistics:
    """Tests for UsageStatistics class."""

    def test_tool_execution_tracking(self, stats):
        """Test tool execution is tracked correctly."""
        start = stats.record_tool_start("run_command")
        stats.record_tool_end("run_command", start, success=True)

        tool_stats = stats.get_tool_stats("run_command")
        assert tool_stats is not None
        assert tool_stats.execution_count == 1
        assert tool_stats.success_count == 1
        assert tool_stats.failure_count == 0

    def test_tool_failure_tracking(self, stats):
        """Test tool failure is tracked correctly."""
        start = stats.record_tool_start("run_command")
        stats.record_tool_end("run_command", start, success=False, error="Test error")

        tool_stats = stats.get_tool_stats("run_command")
        assert tool_stats.failure_count == 1
        assert tool_stats.last_error == "Test error"

    def test_multiple_tool_executions(self, stats):
        """Test multiple executions are accumulated."""
        for _ in range(5):
            start = stats.record_tool_start("read_file")
            stats.record_tool_end("read_file", start, success=True)

        tool_stats = stats.get_tool_stats("read_file")
        assert tool_stats.execution_count == 5
        assert tool_stats.success_count == 5

    def test_recipe_execution_tracking(self, stats):
        """Test recipe execution is tracked correctly."""
        start = stats.record_recipe_start("disk_cleanup")
        stats.record_recipe_end("disk_cleanup", start, success=True, steps_executed=3)

        recipe_stats = stats.get_recipe_stats("disk_cleanup")
        assert recipe_stats is not None
        assert recipe_stats.execution_count == 1
        assert recipe_stats.success_count == 1
        assert recipe_stats.total_steps_executed == 3

    def test_recipe_failure_tracking(self, stats):
        """Test recipe failure is tracked correctly."""
        start = stats.record_recipe_start("disk_cleanup")
        stats.record_recipe_end("disk_cleanup", start, success=False, steps_executed=2)

        recipe_stats = stats.get_recipe_stats("disk_cleanup")
        assert recipe_stats.failure_count == 1
        assert recipe_stats.total_steps_executed == 2

    def test_plugin_registration(self, stats):
        """Test plugin registration tracks tools and recipes."""
        stats.register_plugin(
            "test-plugin",
            tools=["tool1", "tool2"],
            recipes=["recipe1"],
        )

        plugin_stats = stats.get_plugin_stats("test-plugin")
        assert plugin_stats is not None
        assert plugin_stats.tools_provided == 2
        assert plugin_stats.recipes_provided == 1

    def test_plugin_tool_attribution(self, stats):
        """Test tool executions are attributed to plugins."""
        stats.register_plugin(
            "my-plugin",
            tools=["custom_tool"],
            recipes=[],
        )

        start = stats.record_tool_start("custom_tool")
        stats.record_tool_end("custom_tool", start, success=True)

        plugin_stats = stats.get_plugin_stats("my-plugin")
        assert plugin_stats.tool_executions == 1

    def test_session_summary(self, stats):
        """Test session summary includes all metrics."""
        # Execute some tools
        for _ in range(3):
            start = stats.record_tool_start("run_command")
            stats.record_tool_end("run_command", start, success=True)

        start = stats.record_tool_start("read_file")
        stats.record_tool_end("read_file", start, success=False, error="err")

        # Execute a recipe
        start = stats.record_recipe_start("test_recipe")
        stats.record_recipe_end("test_recipe", start, success=True, steps_executed=2)

        summary = stats.get_session_summary()
        assert summary["total_tool_executions"] == 4
        assert summary["total_recipe_executions"] == 1
        assert summary["total_errors"] == 1
        assert summary["unique_tools_used"] == 2
        assert summary["unique_recipes_used"] == 1

    def test_top_tools(self, stats):
        """Test top tools are sorted by execution count."""
        # Execute tools with different frequencies
        for _ in range(10):
            start = stats.record_tool_start("popular_tool")
            stats.record_tool_end("popular_tool", start, success=True)

        for _ in range(3):
            start = stats.record_tool_start("less_popular")
            stats.record_tool_end("less_popular", start, success=True)

        top_tools = stats.get_top_tools(2)
        assert len(top_tools) == 2
        assert top_tools[0].name == "popular_tool"
        assert top_tools[0].execution_count == 10
        assert top_tools[1].name == "less_popular"
        assert top_tools[1].execution_count == 3

    def test_save_and_load_session_stats(self, temp_stats_dir):
        """Test session stats are persisted correctly."""
        stats = UsageStatistics(stats_dir=temp_stats_dir)

        # Generate some stats
        start = stats.record_tool_start("test_tool")
        stats.record_tool_end("test_tool", start, success=True)

        stats.save_session_stats()

        # Check session file exists
        session_files = list(temp_stats_dir.glob("session_*.json"))
        assert len(session_files) == 1

        # Verify content
        with open(session_files[0]) as f:
            data = json.load(f)
        assert "session" in data
        assert "tools" in data
        assert "test_tool" in data["tools"]

    def test_aggregate_stats_persistence(self, temp_stats_dir):
        """Test aggregate stats accumulate across sessions."""
        # First session
        stats1 = UsageStatistics(stats_dir=temp_stats_dir)
        for _ in range(5):
            start = stats1.record_tool_start("run_command")
            stats1.record_tool_end("run_command", start, success=True)
        stats1.save_session_stats()

        # Second session (new instance)
        stats2 = UsageStatistics(stats_dir=temp_stats_dir)
        for _ in range(3):
            start = stats2.record_tool_start("run_command")
            stats2.record_tool_end("run_command", start, success=True)
        stats2.save_session_stats()

        # Check aggregate
        aggregate = stats2.get_aggregate_stats()
        assert aggregate["total_sessions"] == 2
        assert aggregate["total_tool_executions"] == 8
        assert aggregate["tools"]["run_command"]["execution_count"] == 8


class TestGlobalInstance:
    """Tests for global stats instance."""

    def test_get_usage_stats_singleton(self):
        """Test get_usage_stats returns same instance."""
        reset_usage_stats()
        stats1 = get_usage_stats()
        stats2 = get_usage_stats()
        assert stats1 is stats2

    def test_reset_usage_stats(self):
        """Test reset creates new instance."""
        reset_usage_stats()
        stats1 = get_usage_stats()

        # Add some data
        start = stats1.record_tool_start("test")
        stats1.record_tool_end("test", start, success=True)

        reset_usage_stats()
        stats2 = get_usage_stats()

        assert stats1 is not stats2
        assert stats2.get_tool_stats("test") is None
