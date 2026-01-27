"""Tests for the Claude Code integration module."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from aios.code.detector import CodingRequestDetector
from aios.code.runner import CodeRunner, CodeSession, LaunchResult
from aios.config import AIOSConfig, CodeConfig
from aios.ui.completions import COMMAND_REGISTRY


# ---------------------------------------------------------------------------
# CodingRequestDetector
# ---------------------------------------------------------------------------

class TestCodingRequestDetector:
    """Tests for the regex-based coding request detector."""

    def test_strong_match_script(self):
        d = CodingRequestDetector(sensitivity="moderate")
        assert d.is_coding_request("write a Python script to parse CSV files")

    def test_strong_match_app(self):
        d = CodingRequestDetector(sensitivity="moderate")
        assert d.is_coding_request("build a Flask app with login")

    def test_strong_match_refactor(self):
        d = CodingRequestDetector(sensitivity="moderate")
        assert d.is_coding_request("refactor this code to use async/await")

    def test_strong_match_implement(self):
        d = CodingRequestDetector(sensitivity="moderate")
        assert d.is_coding_request("implement a feature for user authentication")

    def test_strong_match_scaffold(self):
        d = CodingRequestDetector(sensitivity="moderate")
        assert d.is_coding_request("set up a project with React and TypeScript")

    def test_moderate_match_coding(self):
        d = CodingRequestDetector(sensitivity="moderate")
        assert d.is_coding_request("help me with coding in Python and npm install")

    def test_no_match_general(self):
        d = CodingRequestDetector(sensitivity="moderate")
        assert not d.is_coding_request("what time is it")

    def test_no_match_system(self):
        d = CodingRequestDetector(sensitivity="moderate")
        assert not d.is_coding_request("show disk space")

    def test_sensitivity_high(self):
        d = CodingRequestDetector(sensitivity="high")
        # Moderate keywords alone should NOT trigger at high sensitivity
        assert not d.is_coding_request("help with coding")
        # But strong patterns should
        assert d.is_coding_request("write a Python script to sort files")

    def test_sensitivity_low(self):
        d = CodingRequestDetector(sensitivity="low")
        # Even single moderate keyword should trigger at low sensitivity
        assert d.is_coding_request("help with coding")

    def test_score_range(self):
        d = CodingRequestDetector(sensitivity="moderate")
        score = d.score("write a Python script and run npm install")
        assert 0.0 <= score <= 3.0

    def test_score_zero(self):
        d = CodingRequestDetector(sensitivity="moderate")
        assert d.score("hello world how are you") == 0.0

    def test_describe_match(self):
        d = CodingRequestDetector(sensitivity="moderate")
        desc = d.describe_match("write a Python script")
        assert desc  # non-empty
        assert "match" in desc.lower() or "keyword" in desc.lower()

    def test_describe_no_match(self):
        d = CodingRequestDetector(sensitivity="moderate")
        desc = d.describe_match("what is the weather")
        assert desc == ""


# ---------------------------------------------------------------------------
# LaunchResult
# ---------------------------------------------------------------------------

class TestLaunchResult:
    """Tests for LaunchResult dataclass."""

    def test_launch_result_defaults(self):
        result = LaunchResult(success=True)
        assert result.success is True
        assert result.return_code == 0
        assert result.error is None

    def test_launch_result_error(self):
        result = LaunchResult(success=False, return_code=1, error="something broke")
        assert not result.success
        assert result.return_code == 1
        assert result.error == "something broke"


# ---------------------------------------------------------------------------
# CodeSession
# ---------------------------------------------------------------------------

class TestCodeSession:
    """Tests for CodeSession dataclass."""

    def test_session_creation(self):
        sess = CodeSession(session_id="abc123", working_directory="/home/user")
        assert sess.session_id == "abc123"
        assert sess.created_at > 0

    def test_to_dict_from_dict(self):
        original = CodeSession(
            session_id="test-id",
            working_directory="/tmp",
            prompt_summary="build an API",
        )
        d = original.to_dict()
        restored = CodeSession.from_dict(d)
        assert restored.session_id == original.session_id
        assert restored.working_directory == original.working_directory
        assert restored.prompt_summary == original.prompt_summary

    def test_to_dict_no_event_count(self):
        """event_count was removed — ensure it's not in the dict."""
        sess = CodeSession(session_id="x")
        d = sess.to_dict()
        assert "event_count" not in d


# ---------------------------------------------------------------------------
# CodeRunner
# ---------------------------------------------------------------------------

class TestCodeRunner:
    """Tests for the CodeRunner interactive launcher."""

    def test_is_available_true(self):
        with patch("shutil.which", return_value="/usr/bin/claude"):
            runner = CodeRunner()
            assert runner.is_available()

    def test_is_available_false(self):
        with patch("shutil.which", return_value=None):
            runner = CodeRunner()
            assert not runner.is_available()

    def test_get_install_instructions(self):
        instructions = CodeRunner.get_install_instructions()
        assert "npm install" in instructions
        assert "claude-code" in instructions

    def test_launch_not_available(self):
        """launch_interactive returns error when CLI missing."""
        with patch("shutil.which", return_value=None):
            runner = CodeRunner()
            result = runner.launch_interactive(prompt="test")
            assert not result.success
            assert result.error is not None
            assert "not installed" in result.error.lower()

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_launch_builds_correct_command(self, _which, mock_run):
        """Verify command is ['claude', 'prompt'] for a simple prompt."""
        mock_run.return_value = MagicMock(returncode=0)
        runner = CodeRunner()
        runner.launch_interactive(prompt="build a REST API")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["claude", "build a REST API"]

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_launch_bare_interactive(self, _which, mock_run):
        """Verify bare launch is just ['claude']."""
        mock_run.return_value = MagicMock(returncode=0)
        runner = CodeRunner()
        runner.launch_interactive()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["claude"]

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_launch_with_resume(self, _which, mock_run):
        """Verify resume adds ['--resume', 'id']."""
        mock_run.return_value = MagicMock(returncode=0)
        runner = CodeRunner()
        runner.launch_interactive(session_id="sess-abc")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["claude", "--resume", "sess-abc"]

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_launch_with_resume_and_prompt(self, _which, mock_run):
        """Verify resume + prompt produces ['claude', '--resume', 'id', 'prompt']."""
        mock_run.return_value = MagicMock(returncode=0)
        runner = CodeRunner()
        runner.launch_interactive(prompt="add tests", session_id="sess-abc")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["claude", "--resume", "sess-abc", "add tests"]

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_launch_success(self, _which, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        runner = CodeRunner()
        result = runner.launch_interactive()
        assert result.success
        assert result.return_code == 0

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_launch_nonzero_exit(self, _which, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        runner = CodeRunner()
        result = runner.launch_interactive()
        assert not result.success
        assert result.return_code == 1

    def test_resolve_auth_env_api_key(self):
        """api_key mode should set ANTHROPIC_API_KEY in env."""
        runner = CodeRunner()
        with patch("aios.config.get_config") as mock_cfg:
            mock_cfg.return_value.api.api_key = "sk-test-123"
            env = runner._resolve_auth_env("api_key")
        assert env.get("ANTHROPIC_API_KEY") == "sk-test-123"

    def test_resolve_auth_env_subscription(self):
        """subscription mode should remove ANTHROPIC_API_KEY from env."""
        runner = CodeRunner()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-existing"}):
            env = runner._resolve_auth_env("subscription")
        assert "ANTHROPIC_API_KEY" not in env

    def test_resolve_auth_env_none(self):
        """None mode inherits env as-is."""
        runner = CodeRunner()
        env = runner._resolve_auth_env(None)
        # Should be a copy of the current env
        assert isinstance(env, dict)

    def test_session_persistence(self):
        """Test that sessions can be saved and loaded."""
        with tempfile.TemporaryDirectory() as tmp:
            runner = CodeRunner()
            runner._sessions_dir = Path(tmp)

            session = CodeSession(
                session_id="test-persist",
                working_directory="/home",
                prompt_summary="test",
            )
            runner._save_session(session)

            loaded = runner.get_session("test-persist")
            assert loaded is not None
            assert loaded.session_id == "test-persist"

    def test_get_sessions_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = CodeRunner()
            runner._sessions_dir = Path(tmp)
            assert runner.get_sessions() == []


# ---------------------------------------------------------------------------
# CodeConfig
# ---------------------------------------------------------------------------

class TestCodeConfig:
    """Tests for the code configuration model."""

    def test_code_config_defaults(self):
        cfg = CodeConfig()
        assert cfg.enabled is True
        assert cfg.auto_detect is True
        assert cfg.max_turns == 50
        assert cfg.auto_detect_sensitivity == "moderate"
        assert cfg.allowed_tools is None
        assert cfg.default_working_directory is None

    def test_code_config_auth_mode_default(self):
        cfg = CodeConfig()
        assert cfg.auth_mode is None

    def test_code_config_auth_mode_set(self):
        cfg = CodeConfig(auth_mode="subscription")
        assert cfg.auth_mode == "subscription"

    def test_code_config_in_aios_config(self):
        cfg = AIOSConfig()
        assert hasattr(cfg, "code")
        assert isinstance(cfg.code, CodeConfig)
        assert cfg.code.enabled is True


# ---------------------------------------------------------------------------
# Command Registry
# ---------------------------------------------------------------------------

class TestCommandRegistry:
    """Tests for command registration."""

    def test_code_in_registry(self):
        names = [e["name"] for e in COMMAND_REGISTRY]
        assert "code" in names

    def test_code_continue_in_registry(self):
        names = [e["name"] for e in COMMAND_REGISTRY]
        assert "code-continue" in names

    def test_code_sessions_in_registry(self):
        names = [e["name"] for e in COMMAND_REGISTRY]
        assert "code-sessions" in names


# ---------------------------------------------------------------------------
# Integration: system prompt
# ---------------------------------------------------------------------------

class TestSystemPromptIntegration:
    """Verify system prompt includes Claude Code guidance."""

    def test_system_prompt_mentions_code(self):
        from aios.claude.client import SYSTEM_PROMPT

        assert "Claude Code" in SYSTEM_PROMPT
        assert "code" in SYSTEM_PROMPT.lower()
