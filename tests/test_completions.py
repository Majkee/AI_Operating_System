"""Tests for the AIOS shell tab-completion and toolbar."""

from unittest.mock import MagicMock

import pytest
from prompt_toolkit.document import Document

from aios.ui.completions import (
    AIOSCompleter,
    COMMAND_REGISTRY,
    create_bottom_toolbar,
    _find_entry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_completions(completer, text):
    """Return a list of Completion objects for the given input text."""
    doc = Document(text, len(text))
    return list(completer.get_completions(doc, None))


def _completion_texts(completions):
    """Extract just the completion text strings."""
    return [c.text for c in completions]


# ---------------------------------------------------------------------------
# Registry sanity checks
# ---------------------------------------------------------------------------

class TestCommandRegistry:
    def test_registry_not_empty(self):
        assert len(COMMAND_REGISTRY) > 0

    def test_all_entries_have_required_keys(self):
        for entry in COMMAND_REGISTRY:
            assert "name" in entry
            assert "aliases" in entry
            assert "help" in entry
            assert "has_arg" in entry

    def test_all_entries_have_nonempty_help(self):
        for entry in COMMAND_REGISTRY:
            assert entry["help"], f"{entry['name']} has empty help text"

    def test_expected_commands_present(self):
        names = {e["name"] for e in COMMAND_REGISTRY}
        expected = {
            "exit", "help", "clear", "history",
            "plugins", "recipes", "tools", "stats",
            "credentials", "sessions", "resume",
        }
        assert expected.issubset(names)

    def test_find_entry_by_name(self):
        entry = _find_entry("help")
        assert entry is not None
        assert entry["name"] == "help"

    def test_find_entry_by_alias(self):
        entry = _find_entry("/plugins")
        assert entry is not None
        assert entry["name"] == "plugins"

    def test_find_entry_missing(self):
        assert _find_entry("nonexistent_command") is None


# ---------------------------------------------------------------------------
# AIOSCompleter tests
# ---------------------------------------------------------------------------

class TestAIOSCompleter:
    @pytest.fixture
    def completer(self):
        return AIOSCompleter()

    def test_empty_input_shows_all_commands(self, completer):
        """Double-tap Tab on empty input shows all commands with descriptions."""
        completions = _get_completions(completer, "")
        texts = _completion_texts(completions)
        # Should return all primary command names
        expected_commands = {entry["name"] for entry in COMMAND_REGISTRY}
        assert set(texts) == expected_commands
        # All completions should have help text as display_meta
        for c in completions:
            assert c.display_meta is not None

    def test_partial_match_he(self, completer):
        texts = _completion_texts(_get_completions(completer, "he"))
        assert "help" in texts
        # "history" starts with "hi", not "he"
        assert "history" not in texts

    def test_partial_match_hi(self, completer):
        texts = _completion_texts(_get_completions(completer, "hi"))
        assert "history" in texts
        assert "help" not in texts

    def test_slash_prefix(self, completer):
        texts = _completion_texts(_get_completions(completer, "/pl"))
        assert "/plugins" in texts

    def test_full_command_match(self, completer):
        texts = _completion_texts(_get_completions(completer, "help"))
        assert "help" in texts

    def test_no_completions_for_natural_language(self, completer):
        assert _get_completions(completer, "show me files") == []

    def test_no_completions_for_sentence_with_space(self, completer):
        assert _get_completions(completer, "he llo") == []

    def test_case_insensitive(self, completer):
        texts = _completion_texts(_get_completions(completer, "HE"))
        assert "help" in texts

    def test_all_completions_have_display_meta(self, completer):
        completions = _get_completions(completer, "e")
        for c in completions:
            assert c.display_meta is not None

    def test_resume_session_completions(self):
        fetcher = lambda: ["sess-abc-123", "sess-def-456"]
        completer = AIOSCompleter(session_fetcher=fetcher)
        texts = _completion_texts(_get_completions(completer, "resume sess-a"))
        assert "sess-abc-123" in texts
        assert "sess-def-456" not in texts

    def test_resume_slash_prefix_session_completions(self):
        fetcher = lambda: ["sess-abc-123", "sess-def-456"]
        completer = AIOSCompleter(session_fetcher=fetcher)
        texts = _completion_texts(_get_completions(completer, "/resume sess"))
        assert "sess-abc-123" in texts
        assert "sess-def-456" in texts

    def test_resume_no_fetcher(self):
        completer = AIOSCompleter(session_fetcher=None)
        completions = _get_completions(completer, "resume x")
        assert completions == []

    def test_resume_fetcher_error(self):
        def bad_fetcher():
            raise RuntimeError("disk error")

        completer = AIOSCompleter(session_fetcher=bad_fetcher)
        completions = _get_completions(completer, "resume x")
        assert completions == []

    def test_no_duplicate_completions_for_primary_and_alias(self, completer):
        """If user types 'plugins', both 'plugins' (name) and '/plugins' (alias)
        should NOT both appear – only the matching one should."""
        texts = _completion_texts(_get_completions(completer, "plugins"))
        assert "plugins" in texts
        # /plugins doesn't start with "plugins" so should not appear
        assert "/plugins" not in texts


# ---------------------------------------------------------------------------
# Bottom toolbar tests
# ---------------------------------------------------------------------------

class TestBottomToolbar:
    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.app.current_buffer.text = ""
        return session

    def _toolbar_text(self, session, text):
        """Set buffer text and call the toolbar factory."""
        session.app.current_buffer.text = text
        toolbar_fn = create_bottom_toolbar(session)
        result = toolbar_fn()
        # result is an HTML object; convert to string for assertion
        return str(result)

    def test_empty_input(self, mock_session):
        html = self._toolbar_text(mock_session, "")
        assert "Tab" in html
        assert "command" in html.lower()

    def test_exact_command(self, mock_session):
        html = self._toolbar_text(mock_session, "help")
        assert "help" in html.lower()

    def test_resume_hint(self, mock_session):
        html = self._toolbar_text(mock_session, "resume ")
        assert "session" in html.lower()

    def test_partial_match(self, mock_session):
        html = self._toolbar_text(mock_session, "he")
        assert "help" in html.lower()

    def test_freeform_text(self, mock_session):
        html = self._toolbar_text(mock_session, "show me my files please")
        assert "Enter" in html

    def test_slash_exact_command(self, mock_session):
        html = self._toolbar_text(mock_session, "/plugins")
        assert "plugins" in html.lower()
