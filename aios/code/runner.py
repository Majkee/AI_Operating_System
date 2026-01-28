"""
Claude Code interactive runner for AIOS.

Launches ``claude`` as a direct interactive subprocess, handing off
stdin/stdout/stderr so the user gets a native Claude Code terminal session.
AIOS blocks until the user exits.
"""

import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class LaunchResult:
    """Result of launching an interactive Claude Code session."""
    success: bool
    return_code: int = 0
    error: Optional[str] = None
    session_id: Optional[str] = None


@dataclass
class CodeSession:
    """Metadata about a Claude Code session."""
    session_id: str
    created_at: float = field(default_factory=time.time)
    working_directory: str = ""
    prompt_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "working_directory": self.working_directory,
            "prompt_summary": self.prompt_summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CodeSession":
        return cls(
            session_id=str(data.get("session_id", "")),
            created_at=float(data.get("created_at", 0.0)),
            working_directory=str(data.get("working_directory", "")),
            prompt_summary=str(data.get("prompt_summary", "")),
        )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class CodeRunner:
    """Manages interactive Claude Code sessions."""

    def __init__(self, config=None):
        self._config = config
        self._sessions_dir = Path.home() / ".config" / "aios" / "code_sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._sessions_cache: Optional[List[CodeSession]] = None

    # ---- availability ----

    def is_available(self) -> bool:
        """Return True if the ``claude`` CLI is on PATH."""
        return shutil.which("claude") is not None

    @staticmethod
    def get_install_instructions() -> str:
        return (
            "Claude Code CLI is not installed.\n"
            "Install it with:  npm install -g @anthropic-ai/claude-code\n"
            "More info: https://docs.anthropic.com/en/docs/claude-code"
        )

    # ---- auth env ----

    def _resolve_auth_env(self, auth_mode: Optional[str] = None) -> Dict[str, str]:
        """Build an environment dict based on *auth_mode*.

        * ``"api_key"``      -- sets ANTHROPIC_API_KEY from AIOS config / env
        * ``"subscription"`` -- removes ANTHROPIC_API_KEY so claude falls back
                                to the user's paid subscription login
        * ``None``           -- inherits the current environment as-is
        """
        env = os.environ.copy()

        if auth_mode == "api_key":
            from ..config import get_config
            cfg = get_config()
            api_key = cfg.api.api_key or os.environ.get("ANTHROPIC_API_KEY")
            if api_key:
                env["ANTHROPIC_API_KEY"] = api_key

        elif auth_mode == "subscription":
            # Remove the key so claude uses the user's subscription
            env.pop("ANTHROPIC_API_KEY", None)

        return env

    # ---- interactive launch ----

    def launch_interactive(
        self,
        prompt: Optional[str] = None,
        working_directory: Optional[str] = None,
        session_id: Optional[str] = None,
        auth_mode: Optional[str] = None,
    ) -> LaunchResult:
        """Launch Claude Code as an interactive terminal session.

        Hands off stdin/stdout/stderr completely -- the user interacts
        directly with ``claude``.  AIOS blocks until the session ends.
        """
        if not self.is_available():
            return LaunchResult(
                success=False,
                return_code=-1,
                error=self.get_install_instructions(),
            )

        cmd: List[str] = ["claude"]

        if session_id:
            cmd.extend(["--resume", session_id])

        if prompt:
            cmd.append("--")
            cmd.append(prompt)

        cwd = working_directory or str(Path.home())
        env = self._resolve_auth_env(auth_mode)

        # Generate a session ID for tracking if one wasn't provided
        effective_session_id = session_id or str(uuid.uuid4())

        try:
            completed = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
            )
            return_code = completed.returncode
            success = return_code == 0
        except FileNotFoundError:
            return LaunchResult(
                success=False,
                return_code=-1,
                error=self.get_install_instructions(),
            )
        except KeyboardInterrupt:
            return LaunchResult(success=True, return_code=0, session_id=effective_session_id)
        except Exception as e:
            return LaunchResult(success=False, return_code=-1, error=str(e))

        # Always persist session metadata
        self._save_session(CodeSession(
            session_id=effective_session_id,
            working_directory=cwd,
            prompt_summary=(prompt or "interactive")[:100],
        ))

        return LaunchResult(success=success, return_code=return_code, session_id=effective_session_id)

    # ---- session persistence ----

    def _save_session(self, session: CodeSession) -> None:
        path = self._sessions_dir / f"{session.session_id}.json"
        try:
            with open(path, "w") as f:
                json.dump(session.to_dict(), f)
            self._sessions_cache = None  # invalidate
        except Exception as e:
            logger.warning("Failed to save session %s: %s", session.session_id, e)

    def get_sessions(self, limit: int = 20) -> List[CodeSession]:
        """Return recent sessions, newest first."""
        if self._sessions_cache is not None:
            return self._sessions_cache[:limit]

        sessions: List[CodeSession] = []
        for p in self._sessions_dir.glob("*.json"):
            try:
                with open(p) as f:
                    data = json.load(f)
                sessions.append(CodeSession.from_dict(data))
            except Exception as e:
                logger.warning("Skipping corrupt session file %s: %s", p.name, e)

        sessions.sort(key=lambda s: s.created_at, reverse=True)
        self._sessions_cache = sessions
        return sessions[:limit]

    def get_session(self, session_id: str) -> Optional[CodeSession]:
        """Return a specific session by ID."""
        path = self._sessions_dir / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            return CodeSession.from_dict(data)
        except Exception:
            return None
