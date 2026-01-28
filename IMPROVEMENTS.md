# AIOS Improvement Plan

Prioritized list of critical improvements and new features, based on a thorough review of the codebase at v0.6.0.

---

## Tier 1: These actively hurt the experience right now

### 1. Streaming responses from Claude

**Impact:** Highest — single biggest UX gap.

`claude/client.py` calls `self.client.messages.create()` synchronously and waits for the full response. The user stares at a `Thinking...` spinner for 5-15 seconds seeing nothing. Every modern chat interface streams word-by-word. The Anthropic SDK supports `stream=True` natively — the response objects just need to be yielded incrementally to the UI.

**Files to modify:**
- `aios/claude/client.py` — switch to `messages.stream()`, yield text deltas
- `aios/shell.py` — consume streamed chunks, render incrementally
- `aios/ui/terminal.py` — add `print_streaming_response()` for word-by-word rendering

---

### 2. Unbounded conversation history → token limit crashes

**Impact:** Causes hard crashes in real usage after ~20-30 exchanges.

`ClaudeClient` appends every message to `conversation_history` forever. There is no summarization, truncation, or sliding window. After enough exchanges the context window is exceeded and the API returns an error.

**Solution options:**
- Sliding window that drops oldest messages beyond a token budget
- Summarization step that condenses earlier conversation into a compact summary
- Hybrid: keep last N messages verbatim, summarize everything older

**Files to modify:**
- `aios/claude/client.py` — add token counting + window management
- `aios/context/session.py` — persist summarized history

---

### 3. Apt-only package management

**Impact:** Anyone on Fedora, Arch, SUSE, or macOS can't use package management.

`_handle_manage_application` in `shell.py` (lines ~1213-1223) hardcodes `apt-get` and `apt-cache`. The system prompt tells Claude this is "Debian Linux."

**Solution:** Detect the package manager (`apt`/`dnf`/`pacman`/`zypper`/`brew`) at startup and abstract commands accordingly. Update the system prompt to reflect the detected manager.

**Files to modify:**
- New: `aios/executor/packages.py` — package manager abstraction
- `aios/shell.py` — delegate to abstraction
- `aios/claude/client.py` — dynamic system prompt section
- `aios/context/system.py` — detect package manager

---

### 4. shell.py is an 1800-line monolith

**Impact:** Every change is risky; every new feature is harder to add.

Every concern lives in one file: tool handlers, command routing, plugin wiring, cache config, session management, Claude Code integration, streaming execution.

**Solution:** Extract into focused modules:
- `aios/handlers/` — one module per tool handler group (files, commands, system, apps)
- `aios/commands/` — shell command dispatch (help, stats, sessions, plugins, etc.)
- `aios/shell.py` — reduced to orchestration only (~300 lines)

---

## Tier 2: Missing features users expect

### 5. Multi-line input

**Impact:** Users can't paste code blocks or write detailed instructions.

`prompt_toolkit` supports multi-line input (Alt+Enter or a toggle) but it's not configured. Users wanting to say "here's my error log, explain it" have to paste everything on one line.

**Files to modify:**
- `aios/shell.py` — configure `PromptSession` with `multiline=True` or Alt+Enter toggle
- `aios/ui/terminal.py` — update help text to mention the keybinding

---

### 6. Conversation export / output saving

**Impact:** No way to save a response, export a transcript, or pipe output to a file.

The audit log captures actions but not the conversation content in a usable format.

**Features to add:**
- `/save [file]` — save last response to a file
- `/export [file]` — export full session transcript as Markdown
- Support for `> file.txt` redirection syntax

**Files to modify:**
- `aios/shell.py` or new `aios/commands/export.py` — command handlers
- `aios/context/session.py` — transcript formatting
- `aios/ui/completions.py` — register new commands

---

### 7. Undo for file operations

**Impact:** Backups are created but there's no way to use them.

`write_file` creates `.bak` backups automatically, but there's no `undo` command to restore them. The backups just accumulate silently.

**Features to add:**
- `/undo` — restore the most recent backup
- `/undo list` — show available backups
- `/undo <path>` — restore a specific file's backup

**Files to modify:**
- `aios/executor/files.py` — backup tracking, restore logic
- `aios/shell.py` or new `aios/commands/undo.py` — command handler
- `aios/ui/completions.py` — register command

---

### 8. Clipboard integration

**Impact:** No way to copy Claude's response or paste content from clipboard.

**Solution:** Detect available clipboard tool (`xclip`/`xsel`/`wl-copy` on Linux, `pbcopy` on macOS, `clip.exe` on Windows/WSL) and add:
- `/copy` — copy last response to clipboard
- `/paste` — insert clipboard content as input

**Files to modify:**
- New: `aios/ui/clipboard.py` — platform-aware clipboard access
- `aios/shell.py` — command handlers
- `aios/ui/completions.py` — register commands

---

## Tier 3: Reliability & robustness

### 9. Exponential backoff and circuit breaker

**Impact:** Network issues and rate limits cause immediate failures.

`ErrorRecovery.retry` in `errors.py` does 2 attempts with no delay between them. Repeated failures hammer the API.

**Solution:**
- Add exponential backoff with jitter to `ErrorRecovery.retry`
- Add circuit breaker pattern: after N consecutive failures, back off for a cooldown period before retrying
- Apply to `ClaudeClient.send_message()` and `send_tool_results()`

**Files to modify:**
- `aios/errors.py` — enhanced retry with backoff + circuit breaker
- `aios/claude/client.py` — wrap API calls with retry

---

### 10. Hardcoded POSIX assumptions break on Windows

**Impact:** Tool is installable via pip on any OS but crashes on Windows.

Affected areas:
- `executor/sandbox.py` — `start_new_session=True`, `os.killpg()`, POSIX signals
- `context/system.py` — reads `/etc/os-release`
- `safety/guardrails.py` — patterns assume Unix commands
- Config paths assume `/etc/aios`, `/var/log/aios`

**Solution:** Platform-aware abstractions or explicit platform gating in `pyproject.toml`. At minimum, graceful error messages instead of crashes.

---

### 11. Audit log path assumes root access

**Impact:** Non-root users can't write to `/var/log/aios/audit.log`.

`config.py` defaults `log_path` to `/var/log/aios/audit.log`. Regular users get permission errors on startup.

**Fix:** Default to `~/.local/share/aios/audit.log` or `~/.config/aios/audit.log`. Keep `/var/log/aios` as an option for system-wide installs.

**Files to modify:**
- `aios/config.py` — change default
- `aios/data/default.toml` — update default path
- `config/default.toml` — update default path

---

## Tier 4: Features that would make it genuinely enjoyable

### 12. Richer Markdown rendering of Claude responses

`TerminalUI.print_response()` already renders Markdown via Rich, but could be enhanced:
- Syntax-highlighted inline code (not just fenced blocks)
- Clickable file paths (using Rich's link support or OSC 8)
- Collapsible sections for long output

**Files to modify:**
- `aios/ui/terminal.py` — enhance Markdown rendering pipeline

---

### 13. Command history search (Ctrl+R)

`prompt_toolkit` supports reverse history search out of the box but it's not enabled. Users familiar with shell Ctrl+R expect this to work.

**Files to modify:**
- `aios/shell.py` — enable `enable_history_search=True` on `PromptSession`

---

### 14. Configurable system prompt

The system prompt is hardcoded in `client.py`. Power users should be able to customize Claude's persona, add domain-specific instructions, or change the tone.

**Solution:** Add a `system_prompt_extra` config field that appends to the default prompt. Optionally support a `~/.config/aios/system_prompt.md` file.

**Files to modify:**
- `aios/config.py` — add field
- `aios/claude/client.py` — append custom content to system prompt
- `aios/data/default.toml` — document the option

---

### 15. File attachment / image support

Claude's API supports vision (images). A `/attach image.png` command that sends an image for Claude to analyze (screenshots, error dialogs, diagrams) would be a differentiator for non-technical users who can't describe what they see.

**Files to modify:**
- `aios/claude/client.py` — support image content blocks in messages
- `aios/shell.py` — `/attach` command handler
- `aios/ui/completions.py` — register command with file path completion

---

### 16. Progress awareness for multi-step operations

When Claude chains multiple tool calls (e.g. "organize my downloads" triggers 10+ file operations), the user sees individual tool results but no overall progress. A "Step 3/7: Moving PDFs..." display would help.

**Files to modify:**
- `aios/shell.py` — track tool call sequence within a single response
- `aios/ui/terminal.py` — step counter display

---

## Recommended implementation order

| Priority | Item | Rationale |
|----------|------|-----------|
| 1 | Streaming responses (#1) | Biggest UX win, lowest risk |
| 2 | Conversation history management (#2) | Prevents crashes in real usage |
| 3 | shell.py decomposition (#4) | Makes everything else easier to build |
| 4 | Multi-line input (#5) | Small change, big usability gain |
| 5 | Package manager abstraction (#3) | Expands the user base significantly |
| 6 | Configurable system prompt (#14) | Low effort, high customization value |
| 7 | Exponential backoff (#9) | Reliability improvement |
| 8 | Undo command (#7) | Completes an existing half-built feature |
| 9 | Conversation export (#6) | Users need to save useful responses |
| 10 | Ctrl+R history search (#13) | One-line config change |
| 11 | Clipboard integration (#8) | Quality-of-life feature |
| 12 | Audit log path fix (#11) | Quick config fix |
| 13 | Image support (#15) | Differentiator for non-technical users |
| 14 | Richer rendering (#12) | Polish |
| 15 | Progress display (#16) | Polish |
| 16 | Windows/macOS support (#10) | Large scope, lower priority |
