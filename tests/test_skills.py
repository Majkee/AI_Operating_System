"""Tests for skill system."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aios.skills import (
    ToolDefinition,
    RecipeStep,
    Recipe,
    SkillMetadata,
    SkillBase,
    LoadedSkill,
    SkillManager,
    RecipeExecutor,
    BUILTIN_RECIPES,
    get_skill_manager,
    create_simple_skill,
)


class TestToolDefinition:
    """Test ToolDefinition dataclass."""

    def test_creation(self):
        """Test creating a tool definition."""
        handler = MagicMock(return_value={"result": "ok"})
        tool = ToolDefinition(
            name="my_tool",
            description="Does something",
            input_schema={"type": "object"},
            handler=handler
        )
        assert tool.name == "my_tool"
        assert tool.requires_confirmation is False
        assert tool.category == "custom"

    def test_with_confirmation(self):
        """Test tool requiring confirmation."""
        tool = ToolDefinition(
            name="dangerous_tool",
            description="Does something dangerous",
            input_schema={},
            handler=MagicMock(),
            requires_confirmation=True
        )
        assert tool.requires_confirmation is True


class TestRecipeStep:
    """Test RecipeStep dataclass."""

    def test_creation(self):
        """Test creating a recipe step."""
        step = RecipeStep(
            description="Check disk",
            tool_name="get_system_info",
            tool_params={"info_type": "disk"}
        )
        assert step.description == "Check disk"
        assert step.tool_name == "get_system_info"
        assert step.condition is None

    def test_with_condition(self):
        """Test step with condition."""
        step = RecipeStep(
            description="Conditional step",
            tool_name="some_tool",
            tool_params={},
            condition="context.get('proceed', False)"
        )
        assert step.condition is not None


class TestRecipe:
    """Test Recipe dataclass."""

    def test_creation(self):
        """Test creating a recipe."""
        recipe = Recipe(
            name="test_recipe",
            description="A test recipe",
            trigger_phrases=["do the thing", "run test"],
            steps=[
                RecipeStep(
                    description="Step 1",
                    tool_name="tool1",
                    tool_params={}
                )
            ]
        )
        assert recipe.name == "test_recipe"
        assert len(recipe.steps) == 1

    def test_matches_trigger(self):
        """Test matching trigger phrases."""
        recipe = Recipe(
            name="test",
            description="Test",
            trigger_phrases=["clean up disk", "free space"],
            steps=[]
        )
        assert recipe.matches("please clean up disk") is True
        assert recipe.matches("can you free space?") is True
        assert recipe.matches("list files") is False

    def test_matches_case_insensitive(self):
        """Test trigger matching is case insensitive."""
        recipe = Recipe(
            name="test",
            description="Test",
            trigger_phrases=["Clean Disk"],
            steps=[]
        )
        assert recipe.matches("clean disk") is True
        assert recipe.matches("CLEAN DISK") is True


class TestSkillMetadata:
    """Test SkillMetadata dataclass."""

    def test_creation(self):
        """Test creating skill metadata."""
        metadata = SkillMetadata(
            name="my-skill",
            version="1.0.0",
            description="My skill",
            author="Test Author"
        )
        assert metadata.name == "my-skill"
        assert metadata.license == "MIT"  # Default
        assert metadata.dependencies == []


class TestSkillBase:
    """Test SkillBase class."""

    def test_subclass_must_implement_metadata(self):
        """Test that subclass must implement metadata."""
        class IncompleteSkill(SkillBase):
            pass

        with pytest.raises(TypeError):
            IncompleteSkill()

    def test_default_methods(self):
        """Test default method implementations."""
        class MinimalSkill(SkillBase):
            @property
            def metadata(self):
                return SkillMetadata(
                    name="minimal",
                    version="1.0",
                    description="Minimal",
                    author="test"
                )

        skill = MinimalSkill()
        assert skill.get_tools() == []
        assert skill.get_recipes() == []
        # Lifecycle methods should not raise
        skill.on_load()
        skill.on_unload()
        skill.on_session_start()
        skill.on_session_end()


class TestSkillManager:
    """Test SkillManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = SkillManager(skill_dirs=[Path(self.temp_dir)])

    def teardown_method(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_empty_discover(self):
        """Test discovering skills in empty directory."""
        skills = self.manager.discover_skills()
        assert len(skills) == 0

    def test_discover_py_file(self):
        """Test discovering a Python file skill."""
        skill_file = Path(self.temp_dir) / "test_skill.py"
        skill_file.write_text("""
from aios.skills import SkillBase, SkillMetadata

class TestSkill(SkillBase):
    @property
    def metadata(self):
        return SkillMetadata(
            name="test-skill",
            version="1.0.0",
            description="Test skill",
            author="test"
        )
""")
        skills = self.manager.discover_skills()
        assert len(skills) == 1

    def test_list_skills_empty(self):
        """Test listing skills when none loaded."""
        skills = self.manager.list_skills()
        assert len(skills) == 0

    def test_get_all_tools_empty(self):
        """Test getting tools when none registered."""
        tools = self.manager.get_all_tools()
        assert len(tools) == 0

    def test_builtin_recipes(self):
        """Test that builtin recipes are registered."""
        # Use global manager which has builtin recipes
        manager = get_skill_manager()
        recipes = manager.get_all_recipes()
        assert len(recipes) > 0
        assert "disk_cleanup" in recipes

    def test_find_matching_recipe(self):
        """Test finding a matching recipe."""
        # Create a manager with a test recipe
        manager = SkillManager(skill_dirs=[])
        test_recipe = Recipe(
            name="test_recipe",
            description="Test",
            trigger_phrases=["clean disk", "cleanup"],
            steps=[]
        )
        manager._recipes["test_recipe"] = test_recipe

        recipe = manager.find_matching_recipe("please clean disk now")
        assert recipe is not None
        assert recipe.name == "test_recipe"

    def test_find_no_matching_recipe(self):
        """Test when no recipe matches."""
        manager = SkillManager(skill_dirs=[])
        test_recipe = Recipe(
            name="test_recipe",
            description="Test",
            trigger_phrases=["specific trigger"],
            steps=[]
        )
        manager._recipes["test_recipe"] = test_recipe

        recipe = manager.find_matching_recipe("completely different query")
        assert recipe is None


class TestRecipeExecutor:
    """Test RecipeExecutor class."""

    def test_execute_simple_recipe(self):
        """Test executing a simple recipe."""
        results = []

        def tool_executor(name, params):
            results.append((name, params))
            return {"success": True}

        recipe = Recipe(
            name="test",
            description="Test",
            trigger_phrases=[],
            steps=[
                RecipeStep(
                    description="Step 1",
                    tool_name="tool1",
                    tool_params={"key": "value"}
                ),
                RecipeStep(
                    description="Step 2",
                    tool_name="tool2",
                    tool_params={}
                )
            ]
        )

        executor = RecipeExecutor(tool_executor)
        context = executor.execute(recipe)

        assert len(results) == 2
        assert results[0] == ("tool1", {"key": "value"})
        assert results[1] == ("tool2", {})
        assert len(context["_results"]) == 2

    def test_execute_with_condition(self):
        """Test executing recipe with conditions."""
        results = []

        def tool_executor(name, params):
            results.append(name)
            return {"success": True}

        recipe = Recipe(
            name="test",
            description="Test",
            trigger_phrases=[],
            steps=[
                RecipeStep(
                    description="Always runs",
                    tool_name="tool1",
                    tool_params={}
                ),
                RecipeStep(
                    description="Conditional",
                    tool_name="tool2",
                    tool_params={},
                    # Use safe expression syntax (no function calls)
                    condition="context.run_step2 == True"
                )
            ]
        )

        executor = RecipeExecutor(tool_executor)

        # Without flag, step2 should not run
        context = executor.execute(recipe)
        assert results == ["tool1"]

        results.clear()

        # With flag, step2 should run
        context = executor.execute(recipe, initial_context={"run_step2": True})
        assert results == ["tool1", "tool2"]

    def test_execute_with_callback(self):
        """Test step callback during execution."""
        steps_reported = []

        def tool_executor(name, params):
            return {}

        def on_step(step, num):
            steps_reported.append((step.description, num))

        recipe = Recipe(
            name="test",
            description="Test",
            trigger_phrases=[],
            steps=[
                RecipeStep(description="First", tool_name="t1", tool_params={}),
                RecipeStep(description="Second", tool_name="t2", tool_params={})
            ]
        )

        executor = RecipeExecutor(tool_executor)
        executor.execute(recipe, on_step=on_step)

        assert steps_reported == [("First", 0), ("Second", 1)]

    def test_param_interpolation(self):
        """Test parameter interpolation from context."""
        captured_params = []

        def tool_executor(name, params):
            captured_params.append(params)
            return {}

        recipe = Recipe(
            name="test",
            description="Test",
            trigger_phrases=[],
            steps=[
                RecipeStep(
                    description="Interpolated",
                    tool_name="tool",
                    tool_params={"path": "$user_path", "static": "value"}
                )
            ]
        )

        executor = RecipeExecutor(tool_executor)
        executor.execute(recipe, initial_context={"user_path": "/home/user"})

        assert captured_params[0]["path"] == "/home/user"
        assert captured_params[0]["static"] == "value"


class TestBuiltinRecipes:
    """Test built-in recipes."""

    def test_disk_cleanup_exists(self):
        """Test disk_cleanup recipe exists."""
        names = [r.name for r in BUILTIN_RECIPES]
        assert "disk_cleanup" in names

    def test_system_health_exists(self):
        """Test system_health recipe exists."""
        names = [r.name for r in BUILTIN_RECIPES]
        assert "system_health" in names

    def test_recipes_have_steps(self):
        """Test all recipes have at least one step."""
        for recipe in BUILTIN_RECIPES:
            assert len(recipe.steps) > 0, f"Recipe {recipe.name} has no steps"

    def test_recipes_have_triggers(self):
        """Test all recipes have trigger phrases."""
        for recipe in BUILTIN_RECIPES:
            assert len(recipe.trigger_phrases) > 0, f"Recipe {recipe.name} has no triggers"


class TestCreateSimpleSkill:
    """Test create_simple_skill factory."""

    def test_creates_skill_class(self):
        """Test factory creates a skill class."""
        SkillClass = create_simple_skill(
            name="simple",
            version="1.0",
            description="Simple skill"
        )
        assert issubclass(SkillClass, SkillBase)

        skill = SkillClass()
        assert skill.metadata.name == "simple"

    def test_with_tools(self):
        """Test factory with tools."""
        tool = ToolDefinition(
            name="my_tool",
            description="My tool",
            input_schema={},
            handler=MagicMock()
        )

        SkillClass = create_simple_skill(
            name="with-tools",
            version="1.0",
            description="Skill with tools",
            tools=[tool]
        )

        skill = SkillClass()
        tools = skill.get_tools()
        assert len(tools) == 1
        assert tools[0].name == "my_tool"

    def test_with_recipes(self):
        """Test factory with recipes."""
        recipe = Recipe(
            name="my_recipe",
            description="My recipe",
            trigger_phrases=["do my thing"],
            steps=[]
        )

        SkillClass = create_simple_skill(
            name="with-recipes",
            version="1.0",
            description="Skill with recipes",
            recipes=[recipe]
        )

        skill = SkillClass()
        recipes = skill.get_recipes()
        assert len(recipes) == 1
        assert recipes[0].name == "my_recipe"
