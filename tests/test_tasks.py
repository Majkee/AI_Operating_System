"""Tests for background task management."""

import os
import sys
import time
import subprocess
import threading
from unittest.mock import MagicMock, patch

import pytest

from aios.tasks.models import BackgroundTask, TaskStatus
from aios.tasks.manager import TaskManager
from aios.ui.completions import COMMAND_REGISTRY, create_bottom_toolbar

IS_WINDOWS = sys.platform == "win32"
skip_on_windows = pytest.mark.skipif(IS_WINDOWS, reason="Test not compatible with Windows")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_process(poll_return=None, pid=12345):
    """Create a mock subprocess.Popen."""
    proc = MagicMock(spec=subprocess.Popen)
    proc.poll.return_value = poll_return
    proc.pid = pid
    proc.stdout = iter([])
    proc.kill = MagicMock()
    proc.terminate = MagicMock()
    proc.wait = MagicMock()
    return proc


def _make_task(task_id=1, poll_return=None, command="echo test", description="Test"):
    """Create a BackgroundTask with a mock process."""
    proc = _make_mock_process(poll_return)
    thread = threading.Thread(target=lambda: None, daemon=True)
    return BackgroundTask(
        task_id=task_id,
        command=command,
        description=description,
        process=proc,
        reader_thread=thread,
    )


# ===========================================================================
# TestBackgroundTask
# ===========================================================================

class TestBackgroundTask:
    """Tests for the BackgroundTask dataclass."""

    def test_task_creation(self):
        task = _make_task()
        assert task.task_id == 1
        assert task.command == "echo test"
        assert task.description == "Test"
        assert task.status == TaskStatus.RUNNING
        assert task.is_alive is True
        assert task.elapsed >= 0

    def test_status_completed(self):
        task = _make_task(poll_return=0)
        assert task.status == TaskStatus.COMPLETED
        assert task.is_alive is False
        assert task.return_code == 0

    def test_status_failed(self):
        task = _make_task(poll_return=1)
        assert task.status == TaskStatus.FAILED
        assert task.is_alive is False
        assert task.return_code == 1

    def test_output_with_callback(self):
        task = _make_task()
        callback = MagicMock()
        task.attach_display(callback)
        task.add_output_line("hello")
        callback.assert_called_once_with("hello")
        assert task.get_output() == ["hello"]

    def test_output_without_callback(self):
        task = _make_task()
        task.add_output_line("hello")
        assert task.get_output() == ["hello"]

    def test_detach_display(self):
        task = _make_task()
        callback = MagicMock()
        task.attach_display(callback)
        task.detach_display()
        task.add_output_line("line")
        callback.assert_not_called()
        assert task.get_output() == ["line"]

    def test_get_output_last_n(self):
        task = _make_task()
        for i in range(10):
            task.add_output_line(f"line{i}")
        last3 = task.get_output(last_n=3)
        assert last3 == ["line7", "line8", "line9"]

    def test_get_output_last_n_exceeds(self):
        task = _make_task()
        task.add_output_line("a")
        task.add_output_line("b")
        assert task.get_output(last_n=10) == ["a", "b"]

    @skip_on_windows
    def test_kill_real_process(self):
        """Kill a real sleep subprocess."""
        proc = subprocess.Popen(
            "sleep 60",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            universal_newlines=True,
        )
        thread = threading.Thread(target=lambda: None, daemon=True)
        task = BackgroundTask(
            task_id=99,
            command="sleep 60",
            description="sleeper",
            process=proc,
            reader_thread=thread,
        )
        assert task.is_alive is True
        task.kill()
        proc.wait(timeout=5)
        assert task.status == TaskStatus.KILLED

    def test_notified_flag(self):
        task = _make_task()
        assert task.notified is False
        task.mark_notified()
        assert task.notified is True

    def test_callback_exception_does_not_propagate(self):
        """A failing callback should not raise from add_output_line."""
        task = _make_task()
        task.attach_display(MagicMock(side_effect=RuntimeError("boom")))
        task.add_output_line("safe")  # should not raise
        assert task.get_output() == ["safe"]


# ===========================================================================
# TestTaskManager
# ===========================================================================

class TestTaskManager:
    """Tests for the TaskManager class."""

    @skip_on_windows
    def test_create_task(self):
        tm = TaskManager()
        task = tm.create_task("echo hi", "greeting")
        assert task.task_id == 1
        assert task in tm.list_tasks()
        # Give it a moment to finish
        task.reader_thread.join(timeout=5)
        task.process.wait(timeout=5)

    @skip_on_windows
    def test_id_increments(self):
        tm = TaskManager()
        t1 = tm.create_task("echo 1", "first")
        t2 = tm.create_task("echo 2", "second")
        assert t2.task_id == t1.task_id + 1
        t1.reader_thread.join(timeout=5)
        t2.reader_thread.join(timeout=5)
        t1.process.wait(timeout=5)
        t2.process.wait(timeout=5)

    def test_adopt_task(self):
        tm = TaskManager()
        proc = _make_mock_process(poll_return=None)
        thread = threading.Thread(target=lambda: None, daemon=True)
        task = tm.adopt_task("cmd", "adopted", proc, thread, ["line1"])
        assert task in tm.list_tasks()
        assert task.get_output() == ["line1"]

    def test_get_task(self):
        tm = TaskManager()
        proc = _make_mock_process()
        thread = threading.Thread(target=lambda: None, daemon=True)
        task = tm.adopt_task("cmd", "desc", proc, thread, [])
        assert tm.get_task(task.task_id) is task
        assert tm.get_task(9999) is None

    def test_running_count(self):
        tm = TaskManager()
        # Two "running" tasks (poll returns None)
        for _ in range(2):
            proc = _make_mock_process(poll_return=None)
            thread = threading.Thread(target=lambda: None, daemon=True)
            tm.adopt_task("cmd", "d", proc, thread, [])
        # One "finished" task
        proc = _make_mock_process(poll_return=0)
        thread = threading.Thread(target=lambda: None, daemon=True)
        tm.adopt_task("cmd", "d", proc, thread, [])
        assert tm.running_count() == 2

    def test_unnotified_completions(self):
        tm = TaskManager()
        proc = _make_mock_process(poll_return=0)
        thread = threading.Thread(target=lambda: None, daemon=True)
        task = tm.adopt_task("cmd", "d", proc, thread, [])
        assert len(tm.get_unnotified_completions()) == 1
        task.mark_notified()
        assert len(tm.get_unnotified_completions()) == 0

    def test_kill_task(self):
        tm = TaskManager()
        proc = _make_mock_process(poll_return=None)
        thread = threading.Thread(target=lambda: None, daemon=True)
        task = tm.adopt_task("cmd", "d", proc, thread, [])
        assert tm.kill_task(task.task_id) is True
        assert task.status == TaskStatus.KILLED
        assert tm.kill_task(9999) is False

    def test_remove_finished(self):
        tm = TaskManager()
        # Finished task — removable
        proc = _make_mock_process(poll_return=0)
        thread = threading.Thread(target=lambda: None, daemon=True)
        task = tm.adopt_task("cmd", "d", proc, thread, [])
        assert tm.remove_task(task.task_id) is True
        assert tm.get_task(task.task_id) is None

    def test_remove_running_refused(self):
        tm = TaskManager()
        proc = _make_mock_process(poll_return=None)
        thread = threading.Thread(target=lambda: None, daemon=True)
        task = tm.adopt_task("cmd", "d", proc, thread, [])
        assert tm.remove_task(task.task_id) is False
        assert tm.get_task(task.task_id) is task

    def test_cleanup(self):
        tm = TaskManager()
        procs = []
        for _ in range(3):
            proc = _make_mock_process(poll_return=None)
            thread = threading.Thread(target=lambda: None, daemon=True)
            tm.adopt_task("cmd", "d", proc, thread, [])
            procs.append(proc)
        tm.cleanup()
        for t in tm.list_tasks():
            assert t.status == TaskStatus.KILLED

    def test_list_tasks_excludes_finished(self):
        tm = TaskManager()
        proc_running = _make_mock_process(poll_return=None)
        proc_done = _make_mock_process(poll_return=0)
        t1 = threading.Thread(target=lambda: None, daemon=True)
        t2 = threading.Thread(target=lambda: None, daemon=True)
        tm.adopt_task("cmd", "running", proc_running, t1, [])
        tm.adopt_task("cmd", "done", proc_done, t2, [])
        running_only = tm.list_tasks(include_finished=False)
        assert len(running_only) == 1
        assert running_only[0].description == "running"


# ===========================================================================
# TestToolbarIntegration
# ===========================================================================

class TestToolbarIntegration:
    """Tests for the toolbar and command registry updates."""

    def test_tasks_in_registry(self):
        names = [e["name"] for e in COMMAND_REGISTRY]
        assert "tasks" in names

    def test_tasks_entry_has_no_arg(self):
        entry = next(e for e in COMMAND_REGISTRY if e["name"] == "tasks")
        assert entry["has_arg"] is False
        assert "/tasks" in entry["aliases"]

    def test_toolbar_no_tasks(self):
        session = MagicMock()
        session.app.current_buffer.text = ""
        toolbar_fn = create_bottom_toolbar(session, task_manager=None)
        result = toolbar_fn()
        # Should not include task info
        assert "task" not in str(result).lower() or "Ctrl+B" not in str(result)

    def test_toolbar_running_count(self):
        session = MagicMock()
        session.app.current_buffer.text = ""
        tm = MagicMock()
        tm.running_count.return_value = 2
        tm.get_unnotified_completions.return_value = []
        tm.list_tasks.return_value = [1, 2]
        toolbar_fn = create_bottom_toolbar(session, task_manager=tm)
        result = str(toolbar_fn())
        assert "2" in result
        assert "running" in result

    def test_toolbar_finished_count(self):
        session = MagicMock()
        session.app.current_buffer.text = ""
        tm = MagicMock()
        tm.running_count.return_value = 0
        tm.get_unnotified_completions.return_value = [MagicMock()]
        tm.list_tasks.return_value = [1]
        toolbar_fn = create_bottom_toolbar(session, task_manager=tm)
        result = str(toolbar_fn())
        assert "finished" in result

    def test_toolbar_backward_compatible(self):
        """Passing no task_manager should work identically to before."""
        session = MagicMock()
        session.app.current_buffer.text = ""
        toolbar_fn = create_bottom_toolbar(session)
        result = toolbar_fn()
        # Should still produce something
        assert result is not None


# ===========================================================================
# TestToolSchema
# ===========================================================================

class TestToolSchema:
    """Tests for the run_command tool schema update."""

    def test_background_param_exists(self):
        from aios.claude.tools import BUILTIN_TOOLS
        run_cmd = next(t for t in BUILTIN_TOOLS if t["name"] == "run_command")
        props = run_cmd["input_schema"]["properties"]
        assert "background" in props
        assert props["background"]["type"] == "boolean"

    def test_background_not_required(self):
        from aios.claude.tools import BUILTIN_TOOLS
        run_cmd = next(t for t in BUILTIN_TOOLS if t["name"] == "run_command")
        required = run_cmd["input_schema"]["required"]
        assert "background" not in required


# ===========================================================================
# TestSystemPrompt
# ===========================================================================

class TestSystemPrompt:
    """Test that the system prompt mentions background tasks."""

    def test_system_prompt_mentions_background(self):
        from aios.claude.client import SYSTEM_PROMPT
        assert "background" in SYSTEM_PROMPT.lower()
        assert "Ctrl+B" in SYSTEM_PROMPT


# ===========================================================================
# TestIntegration
# ===========================================================================

class TestIntegration:
    """Integration tests for background task handling in the shell."""

    def _make_shell(self, mock_config):
        """Create an AIOSShell with mocked dependencies."""
        with patch("aios.shell.get_config", return_value=mock_config), \
             patch("aios.shell.ensure_config_dirs"), \
             patch("aios.shell.SafetyGuard") as MockGuard, \
             patch("aios.shell.CommandExecutor"), \
             patch("aios.shell.InteractiveExecutor"), \
             patch("aios.shell.FileHandler"), \
             patch("aios.shell.SystemContextGatherer"), \
             patch("aios.shell.SessionManager"), \
             patch("aios.shell.AuditLogger"), \
             patch("aios.shell.get_plugin_manager"), \
             patch("aios.shell.get_system_info_cache"), \
             patch("aios.shell.get_query_cache"), \
             patch("aios.shell.get_rate_limiter"), \
             patch("aios.shell.configure_rate_limiter"), \
             patch("aios.shell.PromptSession"), \
             patch("aios.shell.FileHistory"):

            # Configure the safety guard mock
            guard_instance = MockGuard.return_value
            check_result = MagicMock()
            check_result.is_allowed = True
            check_result.requires_confirmation = False
            check_result.user_warning = None
            check_result.safe_alternative = None
            guard_instance.check_command.return_value = check_result

            from aios.shell import AIOSShell
            shell = AIOSShell()
            shell.ui = MagicMock()
            shell.prompts = MagicMock()
            shell.audit = MagicMock()
            return shell

    def test_background_starts_task(self, mock_config):
        """_handle_run_command with background=True creates a task."""
        shell = self._make_shell(mock_config)
        params = {
            "command": "echo hello",
            "explanation": "Echoing",
            "background": True,
        }
        result = shell._handle_run_command(params)
        assert result.success is True
        assert "background" in result.output.lower() or "Background" in result.output
        tasks = shell.task_manager.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].command == "echo hello"
        # Cleanup
        shell.task_manager.cleanup()

    def test_tasks_command_opens_browser(self, mock_config):
        """The 'tasks' command should be recognised."""
        shell = self._make_shell(mock_config)
        with patch("aios.shell.TaskBrowser") as MockBrowser:
            result = shell._handle_user_input("tasks")
            MockBrowser.assert_called_once()
            assert result is True
