"""
Background task data models.

Defines the BackgroundTask dataclass and TaskStatus enum used by the
task manager to track long-running shell processes.
"""

import os
import sys
import time
import threading
import subprocess
from enum import Enum
from typing import Callable, List, Optional
from dataclasses import dataclass, field


class TaskStatus(Enum):
    """Status of a background task."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


@dataclass
class BackgroundTask:
    """A shell command running (or finished) in the background.

    Thread-safety: *output_buffer* is guarded by *_output_lock*.
    All public methods that touch the buffer acquire this lock.
    """

    task_id: int
    command: str
    description: str
    process: subprocess.Popen
    reader_thread: threading.Thread
    created_at: float = field(default_factory=time.time)
    output_buffer: List[str] = field(default_factory=list)

    # Private fields
    _display_callback: Optional[Callable[[str], None]] = field(
        default=None, repr=False
    )
    _status: TaskStatus = field(default=TaskStatus.RUNNING, repr=False)
    _return_code: Optional[int] = field(default=None, repr=False)
    _notified: bool = field(default=False, repr=False)
    _output_lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False
    )

    # -- Status ---------------------------------------------------------------

    @property
    def status(self) -> TaskStatus:
        """Lazily poll the subprocess and update *_status*."""
        if self._status == TaskStatus.RUNNING:
            rc = self.process.poll()
            if rc is not None:
                self._return_code = rc
                self._status = (
                    TaskStatus.COMPLETED if rc == 0 else TaskStatus.FAILED
                )
        return self._status

    @property
    def return_code(self) -> Optional[int]:
        """Return code of the subprocess (None while running)."""
        # Trigger a status poll to ensure _return_code is fresh
        _ = self.status
        return self._return_code

    @property
    def is_alive(self) -> bool:
        return self.status == TaskStatus.RUNNING

    @property
    def elapsed(self) -> float:
        """Seconds since the task was created."""
        return time.time() - self.created_at

    @property
    def notified(self) -> bool:
        return self._notified

    # -- Output ---------------------------------------------------------------

    def add_output_line(self, line: str) -> None:
        """Append a line to the buffer and forward to any display callback."""
        with self._output_lock:
            self.output_buffer.append(line)
        cb = self._display_callback
        if cb is not None:
            try:
                cb(line)
            except Exception:
                pass

    def attach_display(self, callback: Callable[[str], None]) -> None:
        """Attach a live display callback."""
        self._display_callback = callback

    def detach_display(self) -> None:
        """Detach the live display callback."""
        self._display_callback = None

    def get_output(self, last_n: Optional[int] = None) -> List[str]:
        """Return output lines (optionally the last *last_n*)."""
        with self._output_lock:
            if last_n is None:
                return list(self.output_buffer)
            return list(self.output_buffer[-last_n:])

    # -- Lifecycle ------------------------------------------------------------

    def kill(self) -> None:
        """SIGKILL the process (or TerminateProcess on Windows)."""
        try:
            if sys.platform != "win32":
                os.killpg(os.getpgid(self.process.pid), 9)
            else:
                self.process.kill()
        except (ProcessLookupError, OSError):
            pass
        self._status = TaskStatus.KILLED
        self._return_code = -9

    def terminate(self) -> None:
        """SIGTERM the process (or TerminateProcess on Windows)."""
        try:
            if sys.platform != "win32":
                os.killpg(os.getpgid(self.process.pid), 15)
            else:
                self.process.terminate()
        except (ProcessLookupError, OSError):
            pass

    def mark_notified(self) -> None:
        """Mark this task's completion as having been shown to the user."""
        self._notified = True
