"""
Display commands for AIOS.

Handles plugins, recipes, tools, credentials, and stats display.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..plugins import PluginManager
    from ..cache import SystemInfoCache, ToolResultCache
    from ..ratelimit import APIRateLimiter
    from ..ui.terminal import TerminalUI
    from ..credentials import get_credential, list_credentials


class DisplayCommands:
    """Commands for displaying information."""

    def __init__(
        self,
        ui: "TerminalUI",
        plugin_manager: "PluginManager",
        rate_limiter: "APIRateLimiter",
        system_cache: "SystemInfoCache",
        tool_cache: "ToolResultCache",
    ):
        self.ui = ui
        self.plugin_manager = plugin_manager
        self.rate_limiter = rate_limiter
        self.system_cache = system_cache
        self.tool_cache = tool_cache

    def show_plugins(self) -> None:
        """Display loaded plugins."""
        plugins = self.plugin_manager.list_plugins()

        if not plugins:
            self.ui.print_info("No plugins loaded.")
            self.ui.print_info("Place plugins in ~/.config/aios/plugins/")
            return

        self.ui.console.print("\n[bold cyan]Loaded Plugins[/bold cyan]\n")

        for plugin in plugins:
            tools = self.plugin_manager.get_all_tools()
            plugin_tools = [t for t in tools.values()
                          if hasattr(t, 'category') and t.category == plugin.name]
            tool_count = len(plugin_tools)

            self.ui.console.print(
                f"  [green]●[/green] [bold]{plugin.name}[/bold] v{plugin.version}"
            )
            self.ui.console.print(f"    {plugin.description}")
            self.ui.console.print(f"    [dim]Tools: {tool_count} | Author: {plugin.author}[/dim]")
            self.ui.console.print()

    def show_recipes(self) -> None:
        """Display available recipes."""
        recipes = self.plugin_manager.get_all_recipes()

        if not recipes:
            self.ui.print_info("No recipes available.")
            return

        self.ui.console.print("\n[bold cyan]Available Recipes[/bold cyan]\n")

        for name, recipe in recipes.items():
            triggers = ", ".join(f'"{t}"' for t in recipe.trigger_phrases[:2])
            self.ui.console.print(f"  [green]●[/green] [bold]{name}[/bold]")
            self.ui.console.print(f"    {recipe.description}")
            self.ui.console.print(f"    [dim]Triggers: {triggers}[/dim]")
            self.ui.console.print(f"    [dim]Steps: {len(recipe.steps)}[/dim]")
            self.ui.console.print()

        self.ui.print_info("Say a trigger phrase to run a recipe.")

    def show_tools(self, tool_handler) -> None:
        """Display available tools."""
        # Get built-in tools
        builtin_tools = tool_handler.get_tool_names()

        # Get plugin tools
        plugin_tools = self.plugin_manager.get_all_tools()

        self.ui.console.print("\n[bold cyan]Available Tools[/bold cyan]\n")

        self.ui.console.print("[bold]Built-in Tools:[/bold]")
        for tool_name in sorted(builtin_tools):
            if tool_name not in plugin_tools:
                self.ui.console.print(f"  [dim]●[/dim] {tool_name}")

        if plugin_tools:
            self.ui.console.print("\n[bold]Plugin Tools:[/bold]")
            for name, tool in sorted(plugin_tools.items()):
                confirm = "[yellow]⚠[/yellow]" if tool.requires_confirmation else "[dim]●[/dim]"
                self.ui.console.print(f"  {confirm} {name}")
                self.ui.console.print(f"      [dim]{tool.description[:60]}...[/dim]")

        self.ui.console.print()

    def show_credentials(self) -> None:
        """Display stored credentials (names only, not values)."""
        from ..credentials import get_credential, list_credentials

        try:
            creds = list_credentials()
        except (OSError, IOError, ValueError, KeyError, RuntimeError):
            # Credential store may not be initialized or accessible
            self.ui.print_info("Credential store not initialized.")
            self.ui.print_info("Credentials will be requested when needed by plugins.")
            return

        if not creds:
            self.ui.print_info("No stored credentials.")
            self.ui.print_info("Credentials will be requested when needed by plugins.")
            return

        self.ui.console.print("\n[bold cyan]Stored Credentials[/bold cyan]\n")

        for name in sorted(creds):
            cred = get_credential(name)
            if cred:
                details = []
                if cred.username:
                    details.append(f"user: {cred.username}")
                if cred.password:
                    details.append("password: ****")
                if cred.api_key:
                    details.append("api_key: ****")
                if cred.extra:
                    details.append(f"extra: {len(cred.extra)} fields")

                detail_str = ", ".join(details) if details else "empty"
                self.ui.console.print(f"  [green]●[/green] [bold]{name}[/bold]")
                self.ui.console.print(f"    [dim]{detail_str}[/dim]")

        self.ui.console.print()
        self.ui.print_info("Use 'credential add <name>' or 'credential delete <name>' to manage.")

    def show_stats(self) -> None:
        """Display session and system stats."""
        from ..stats import get_usage_stats

        self.ui.console.print("\n[bold cyan]Session Statistics[/bold cyan]\n")

        # Usage statistics
        usage_stats = get_usage_stats()
        session_summary = usage_stats.get_session_summary()

        self.ui.console.print("[bold]Usage This Session:[/bold]")
        self.ui.console.print(f"  Duration: {session_summary['duration_minutes']} minutes")
        self.ui.console.print(f"  Tools executed: {session_summary['total_tool_executions']}")
        self.ui.console.print(f"  Recipes executed: {session_summary['total_recipe_executions']}")
        self.ui.console.print(f"  Errors: {session_summary['total_errors']}")

        # Top tools this session
        top_tools = usage_stats.get_top_tools(5)
        if top_tools:
            self.ui.console.print("\n[bold]Most Used Tools (This Session):[/bold]")
            for tool in top_tools:
                rate = f"{tool.success_rate:.0f}%" if tool.execution_count > 0 else "N/A"
                avg_ms = f"{tool.avg_duration_ms:.0f}ms" if tool.execution_count > 0 else "N/A"
                self.ui.console.print(
                    f"  {tool.name}: {tool.execution_count}x "
                    f"[dim](success: {rate}, avg: {avg_ms})[/dim]"
                )

        # Recipe stats this session
        recipe_stats = usage_stats.get_all_recipe_stats()
        if recipe_stats:
            self.ui.console.print("\n[bold]Recipes Executed (This Session):[/bold]")
            for name, stats in recipe_stats.items():
                rate = f"{stats.success_rate:.0f}%" if stats.execution_count > 0 else "N/A"
                self.ui.console.print(
                    f"  {name}: {stats.execution_count}x "
                    f"[dim](success: {rate}, steps: {stats.total_steps_executed})[/dim]"
                )

        # Rate limiter stats
        rl_stats = self.rate_limiter.stats
        self.ui.console.print("\n[bold]API Usage:[/bold]")
        self.ui.console.print(f"  Requests this session: {rl_stats['total_requests']}")
        self.ui.console.print(f"  Tokens used: {rl_stats['total_tokens_used']}")
        self.ui.console.print(f"  Requests remaining (minute): {rl_stats.get('requests_remaining_minute', 'N/A')}")

        # Cache stats
        self.ui.console.print("\n[bold]Cache Performance:[/bold]")
        has_cache_stats = False

        # Tool result cache stats
        tc_stats = self.tool_cache.stats
        tc_hits = tc_stats.get('hits', 0)
        tc_misses = tc_stats.get('misses', 0)
        if tc_hits > 0 or tc_misses > 0:
            has_cache_stats = True
            tc_total = tc_hits + tc_misses
            tc_rate = tc_hits / tc_total * 100 if tc_total > 0 else 0
            self.ui.console.print("  Tool Result Cache:")
            self.ui.console.print(f"    Hit rate: {tc_rate:.0f}% ({tc_hits} hits, {tc_misses} misses)")
            self.ui.console.print(f"    Entries: {tc_stats.get('size', 0)}/{tc_stats.get('max_size', 200)}")
            self.ui.console.print(f"    Evictions: {tc_stats.get('evictions', 0)}")

        # System context cache stats
        sys_cache_stats = self.system_cache.stats
        for info_type, stats in sys_cache_stats.items():
            if stats.get('hits', 0) > 0 or stats.get('misses', 0) > 0:
                has_cache_stats = True
                hit_rate = stats['hits'] / (stats['hits'] + stats['misses']) * 100 if (stats['hits'] + stats['misses']) > 0 else 0
                self.ui.console.print(f"  system/{info_type}: {hit_rate:.0f}% hit rate ({stats['hits']} hits, {stats['misses']} misses)")

        if not has_cache_stats:
            self.ui.console.print("  [dim]No cache activity yet[/dim]")

        # Plugin stats
        plugins = self.plugin_manager.list_plugins()
        tools = self.plugin_manager.get_all_tools()
        recipes = self.plugin_manager.get_all_recipes()
        self.ui.console.print("\n[bold]Plugins:[/bold]")
        self.ui.console.print(f"  Loaded: {len(plugins)}")
        self.ui.console.print(f"  Tools: {len(tools)}")
        self.ui.console.print(f"  Recipes: {len(recipes)}")

        self.ui.console.print()
        self.ui.print_info("Use '/stats all' for all-time statistics")

    def show_stats_alltime(self) -> None:
        """Display all-time aggregate statistics."""
        from ..stats import get_usage_stats

        usage_stats = get_usage_stats()
        aggregate = usage_stats.get_aggregate_stats()

        self.ui.console.print("\n[bold cyan]All-Time Statistics[/bold cyan]\n")

        self.ui.console.print("[bold]Overview:[/bold]")
        self.ui.console.print(f"  Total sessions: {aggregate['total_sessions']}")
        self.ui.console.print(f"  Total tool executions: {aggregate['total_tool_executions']}")
        self.ui.console.print(f"  Total recipe executions: {aggregate['total_recipe_executions']}")
        if aggregate['first_session']:
            self.ui.console.print(f"  First session: {aggregate['first_session'][:10]}")
        if aggregate['last_updated']:
            self.ui.console.print(f"  Last updated: {aggregate['last_updated'][:19]}")

        # Top tools all-time
        top_tools = usage_stats.get_top_tools_alltime(10)
        if top_tools:
            self.ui.console.print("\n[bold]Most Used Tools (All-Time):[/bold]")
            for tool in top_tools:
                self.ui.console.print(
                    f"  {tool['name']}: {tool['execution_count']}x "
                    f"[dim](success: {tool['success_rate']:.0f}%)[/dim]"
                )

        # Top recipes all-time
        top_recipes = usage_stats.get_top_recipes_alltime(10)
        if top_recipes:
            self.ui.console.print("\n[bold]Most Used Recipes (All-Time):[/bold]")
            for recipe in top_recipes:
                self.ui.console.print(
                    f"  {recipe['name']}: {recipe['execution_count']}x "
                    f"[dim](success: {recipe['success_rate']:.0f}%)[/dim]"
                )

        self.ui.console.print()
