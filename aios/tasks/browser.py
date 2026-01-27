"""
Interactive task browser.

Displays a Rich table of background tasks and provides an action menu
for viewing output, attaching to live output, killing, and removing tasks.
"""

from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.box import ROUNDED

from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.completion import WordCompleter

from .models import BackgroundTask, TaskStatus
from .manager import TaskManager


def _format_elapsed(seconds: float) -> str:
    """Format seconds into a human-friendly string."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


_STATUS_STYLE = {
    TaskStatus.RUNNING: "[bold cyan]RUNNING[/bold cyan]",
    TaskStatus.COMPLETED: "[bold green]COMPLETED[/bold green]",
    TaskStatus.FAILED: "[bold red]FAILED[/bold red]",
    TaskStatus.KILLED: "[bold yellow]KILLED[/bold yellow]",
}


class TaskBrowser:
    """Interactive terminal UI for browsing background tasks."""

    def __init__(self, task_manager: TaskManager, console: Console):
        self._tm = task_manager
        self._console = console

    # -- Public entry point ---------------------------------------------------

    def show(self) -> None:
        """Run the interactive browser loop until the user exits."""
        while True:
            tasks = self._tm.list_tasks(include_finished=True)

            # Mark any unnotified completions as seen
            for t in self._tm.get_unnotified_completions():
                t.mark_notified()

            # Render table
            self._print_table(tasks)

            if not tasks:
                self._console.print("[dim]No background tasks.[/dim]\n")
                return

            # Action prompt
            self._console.print(
                "[dim]Actions:[/dim]  "
                "[bold]v[/bold] <id> view  "
                "[bold]a[/bold] <id> attach  "
                "[bold]k[/bold] <id> kill  "
                "[bold]t[/bold] <id> terminate  "
                "[bold]r[/bold] <id> remove  "
                "[bold]b[/bold] back"
            )

            valid_ids = [str(t.task_id) for t in tasks]
            actions = ["v", "a", "k", "t", "r", "b"]
            completer = WordCompleter(actions + valid_ids)

            try:
                raw = pt_prompt("tasks> ", completer=completer).strip()
            except (KeyboardInterrupt, EOFError):
                break

            if not raw or raw.lower() == "b":
                break

            self._dispatch(raw, tasks)

    # -- Internal helpers -----------------------------------------------------

    def _print_table(self, tasks: list[BackgroundTask]) -> None:
        table = Table(
            title="Background Tasks",
            box=ROUNDED,
            show_lines=True,
        )
        table.add_column("ID", style="bold", width=4)
        table.add_column("Status", width=12)
        table.add_column("Description")
        table.add_column("Elapsed", justify="right", width=10)
        table.add_column("Lines", justify="right", width=7)
        table.add_column("Command", style="dim", max_width=40, no_wrap=True)

        for t in tasks:
            table.add_row(
                str(t.task_id),
                _STATUS_STYLE.get(t.status, str(t.status.value)),
                t.description,
                _format_elapsed(t.elapsed),
                str(len(t.output_buffer)),
                t.command[:40],
            )

        self._console.print()
        self._console.print(table)
        self._console.print()

    def _dispatch(self, raw: str, tasks: list[BackgroundTask]) -> None:
        parts = raw.split(None, 1)
        action = parts[0].lower()
        task_id_str = parts[1] if len(parts) > 1 else ""

        if action == "b":
            return

        task = self._resolve_task(task_id_str)
        if task is None:
            self._console.print("[red]Invalid task ID.[/red]")
            return

        if action == "v":
            self._view(task)
        elif action == "a":
            self._attach(task)
        elif action == "k":
            self._kill(task)
        elif action == "t":
            self._terminate(task)
        elif action == "r":
            self._remove(task)
        else:
            self._console.print(f"[red]Unknown action: {action}[/red]")

    def _resolve_task(self, id_str: str) -> Optional[BackgroundTask]:
        try:
            tid = int(id_str)
        except (ValueError, TypeError):
            return None
        return self._tm.get_task(tid)

    # -- Actions --------------------------------------------------------------

    def _view(self, task: BackgroundTask) -> None:
        """Show last 200 lines of output."""
        lines = task.get_output(last_n=200)
        body = "\n".join(lines) if lines else "[dim]No output yet.[/dim]"
        panel = Panel(
            body,
            title=f"Task #{task.task_id} — {task.description}",
            border_style="blue",
            box=ROUNDED,
        )
        self._console.print(panel)

    def _attach(self, task: BackgroundTask) -> None:
        """Attach to live output of a running task."""
        if not task.is_alive:
            self._console.print("[yellow]Task is not running. Use 'v' to view output.[/yellow]")
            return

        self._console.print(
            f"[dim]Attached to task #{task.task_id}. Press Ctrl+C to detach.[/dim]"
        )

        from collections import deque

        display_buf: deque = deque(maxlen=12)

        # Seed with recent lines
        for line in task.get_output(last_n=12):
            display_buf.append(line)

        def _on_line(line: str) -> None:
            display_buf.append(line)

        task.attach_display(_on_line)

        try:
            with Live(
                self._render_attach(display_buf, task),
                console=self._console,
                transient=True,
                refresh_per_second=8,
            ) as live:
                while task.is_alive:
                    live.update(self._render_attach(display_buf, task))
                    task.reader_thread.join(timeout=0.15)
                # Final update after process finishes
                live.update(self._render_attach(display_buf, task))
        except KeyboardInterrupt:
            pass
        finally:
            task.detach_display()

        self._console.print("[dim]Detached.[/dim]")

    @staticmethod
    def _render_attach(buf, task: BackgroundTask) -> Panel:
        body = "\n".join(buf) if buf else "[dim]Waiting for output...[/dim]"
        status = _STATUS_STYLE.get(task.status, task.status.value)
        return Panel(
            body,
            title=f"Task #{task.task_id} — {task.description} [{status}]",
            border_style="cyan",
            box=ROUNDED,
        )

    def _kill(self, task: BackgroundTask) -> None:
        if not task.is_alive:
            self._console.print("[yellow]Task already finished.[/yellow]")
            return
        task.kill()
        self._console.print(f"[green]Task #{task.task_id} killed.[/green]")

    def _terminate(self, task: BackgroundTask) -> None:
        if not task.is_alive:
            self._console.print("[yellow]Task already finished.[/yellow]")
            return
        task.terminate()
        self._console.print(
            f"[green]Sent SIGTERM to task #{task.task_id}.[/green]"
        )

    def _remove(self, task: BackgroundTask) -> None:
        if self._tm.remove_task(task.task_id):
            self._console.print(
                f"[green]Task #{task.task_id} removed.[/green]"
            )
        else:
            self._console.print(
                "[yellow]Cannot remove a running task. Kill it first.[/yellow]"
            )
