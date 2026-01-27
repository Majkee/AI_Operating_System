"""
Task manager — thread-safe registry of background tasks.

Handles creating, adopting, listing, killing, and cleaning up
BackgroundTask instances.
"""

import os
import sys
import subprocess
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .models import BackgroundTask, TaskStatus


class TaskManager:
    """Thread-safe registry of all background tasks."""

    def __init__(self):
        self._tasks: Dict[int, BackgroundTask] = {}
        self._next_id: int = 1
        self._lock = threading.Lock()

    # -- Creation -------------------------------------------------------------

    def create_task(
        self,
        command: str,
        description: str,
        working_directory: Optional[str] = None,
        env: Optional[dict] = None,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> BackgroundTask:
        """Create and start a new background task.

        Args:
            command: Shell command to run.
            description: Human-friendly label.
            working_directory: Working directory for the subprocess.
            env: Extra environment variables.
            on_output: Optional callback invoked for each output line
                       (e.g. a live display hook).

        Returns:
            The newly created BackgroundTask.
        """
        cwd = Path(working_directory) if working_directory else Path.home()

        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        if sys.platform != "win32":
            process_env["PATH"] = (
                "/usr/local/bin:/usr/bin:/bin:" + process_env.get("PATH", "")
            )

        popen_kwargs = dict(
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(cwd),
            env=process_env,
            bufsize=1,
            universal_newlines=True,
        )
        if sys.platform != "win32":
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(command, **popen_kwargs)

        with self._lock:
            task_id = self._next_id
            self._next_id += 1

        task = BackgroundTask(
            task_id=task_id,
            command=command,
            description=description,
            process=process,
            reader_thread=threading.Thread(target=lambda: None, daemon=True),
        )

        if on_output is not None:
            task.attach_display(on_output)

        # Start a daemon reader thread
        def _reader():
            try:
                for line in process.stdout:
                    task.add_output_line(line.rstrip("\n\r"))
            except (ValueError, OSError):
                pass

        reader = threading.Thread(target=_reader, daemon=True)
        reader.start()
        task.reader_thread = reader

        with self._lock:
            self._tasks[task_id] = task

        return task

    def adopt_task(
        self,
        command: str,
        description: str,
        process: subprocess.Popen,
        reader_thread: threading.Thread,
        output_buffer: List[str],
    ) -> BackgroundTask:
        """Wrap an already-running process into a managed BackgroundTask.

        Used by the Ctrl+C-to-background flow.
        """
        with self._lock:
            task_id = self._next_id
            self._next_id += 1

        task = BackgroundTask(
            task_id=task_id,
            command=command,
            description=description,
            process=process,
            reader_thread=reader_thread,
            output_buffer=list(output_buffer),
        )
        # No display callback — it runs silently in the background

        with self._lock:
            self._tasks[task_id] = task

        return task

    # -- Queries --------------------------------------------------------------

    def get_task(self, task_id: int) -> Optional[BackgroundTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, include_finished: bool = True) -> List[BackgroundTask]:
        with self._lock:
            tasks = list(self._tasks.values())
        if not include_finished:
            tasks = [t for t in tasks if t.is_alive]
        return tasks

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._tasks.values() if t.is_alive)

    def get_unnotified_completions(self) -> List[BackgroundTask]:
        """Return tasks that finished but haven't been shown to the user."""
        with self._lock:
            return [
                t
                for t in self._tasks.values()
                if not t.is_alive and not t.notified
            ]

    # -- Lifecycle ------------------------------------------------------------

    def kill_task(self, task_id: int) -> bool:
        task = self.get_task(task_id)
        if task is None:
            return False
        task.kill()
        return True

    def terminate_task(self, task_id: int) -> bool:
        task = self.get_task(task_id)
        if task is None:
            return False
        task.terminate()
        return True

    def remove_task(self, task_id: int) -> bool:
        """Remove a finished task from the registry. Refuses running tasks."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if task.is_alive:
                return False
            del self._tasks[task_id]
            return True

    def cleanup(self) -> None:
        """Kill all running tasks. Called during shell shutdown."""
        with self._lock:
            tasks = list(self._tasks.values())
        for task in tasks:
            if task.is_alive:
                task.kill()
