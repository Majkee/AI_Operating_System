# AIOS Improvement Plan

Prioritized list of critical improvements and new features, based on a thorough review of the codebase at v0.6.0.

---

## Implementation Status Summary

| # | Feature | Status | Version | Notes |
|---|---------|--------|---------|-------|
| 1 | Streaming responses from Claude | **DONE** | v0.7.0 | Word-by-word streaming with live Markdown |
| 2 | Context window management | **DONE** | v0.9.0 | Auto-summarization, token budgets |
| 3 | Multi-platform package management | TODO | - | Still apt-only |
| 4 | shell.py decomposition | **DONE** | v0.9.0 | 1800→794 lines, handlers/ + commands/ |
| 5 | Multi-line input | **DONE** | v0.10.5 | Toggle mode, Esc+Enter to submit |
| 6 | Conversation export | TODO | - | |
| 7 | Undo for file operations | TODO | - | |
| 8 | Clipboard integration | TODO | - | |
| 9 | Exponential backoff & circuit breaker | **DONE** | v0.10.3 | Retry with jitter, circuit breaker |
| 10 | Windows/macOS support | PARTIAL | - | Some fixes, still POSIX-heavy |
| 11 | Audit log path fix | **DONE** | v0.10.2 | Now uses ~/.config/aios/logs/ |
| 12 | Richer Markdown rendering | TODO | - | |
| 13 | Ctrl+R history search | **DONE** | v0.10.5 | enable_history_search=True |
| 14 | Configurable system prompt | TODO | - | |
| 15 | File/image attachment | TODO | - | |
| 16 | Multi-step progress awareness | **DONE** | v0.10.0 | Step X/Y display for tool chains |

### Progress

- **Completed:** 8/16 (50%)
- **Remaining:** 8/16 (50%)

### Completed Features (Tier 1-4)
- Streaming responses (biggest UX win)
- Context window management (prevents crashes)
- shell.py decomposition (maintainability)
- Exponential backoff & circuit breaker (reliability)
- Audit log path fix (non-root users)
- Multi-step progress awareness (polish)
- Multi-line input (usability)
- Ctrl+R history search (usability)

### High Priority Remaining
- Package manager abstraction (#3) — expands user base
- Configurable system prompt (#14) — low effort, high value

---

## Tier 1: These actively hurt the experience right now

### 1. Streaming responses from Claude

> **STATUS: IMPLEMENTED in v0.7.0**

**Impact:** Highest — single biggest UX gap.

`claude/client.py` calls `self.client.messages.create()` synchronously and waits for the full response. The user stares at a `Thinking...` spinner for 5-15 seconds seeing nothing. Every modern chat interface streams word-by-word. The Anthropic SDK supports `stream=True` natively — the response objects just need to be yielded incrementally to the UI.

**Implementation:**
- `aios/claude/client.py` — `_stream_request()` method using `messages.stream()`
- `aios/ui/terminal.py` — `StreamingResponseHandler` for spinner → live Markdown transition
- `aios/config.py` — `api.streaming` toggle (default: true)

---

### 2. Unbounded conversation history → token limit crashes

> **STATUS: IMPLEMENTED in v0.9.0**

**Impact:** Causes hard crashes in real usage after ~20-30 exchanges.

`ClaudeClient` appends every message to `conversation_history` forever. There is no summarization, truncation, or sliding window. After enough exchanges the context window is exceeded and the API returns an error.

**Implementation:**
- Token counting with `estimate_tokens()` and `estimate_history_tokens()`
- Automatic summarization when reaching `summarize_threshold` (default: 75%)
- Configurable `context_budget` (default: 150,000 tokens)
- `min_recent_messages` kept verbatim (default: 6)
- Summary prepended to system prompt for context continuity

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

> **STATUS: IMPLEMENTED in v0.9.0**

**Impact:** Every change is risky; every new feature is harder to add.

Every concern lives in one file: tool handlers, command routing, plugin wiring, cache config, session management, Claude Code integration, streaming execution.

**Implementation:**
- `aios/shell.py` reduced from ~1800 to 794 lines (56% reduction)
- `aios/handlers/` — tool handler modules:
  - `apps.py` — application management
  - `commands.py` — command execution
  - `files.py` — file operations
  - `linux.py` — Linux system tools (35KB, largest handler)
  - `system.py` — system information
- `aios/commands/` — shell command dispatch:
  - `code.py` — Claude Code integration
  - `config.py` — configuration management
  - `display.py` — display/output commands
  - `sessions.py` — session management

---

## Tier 2: Missing features users expect

### 5. Multi-line input

> **STATUS: IMPLEMENTED in v0.10.5**

**Impact:** Users can't paste code blocks or write detailed instructions.

`prompt_toolkit` supports multi-line input (Alt+Enter or a toggle) but it's not configured. Users wanting to say "here's my error log, explain it" have to paste everything on one line.

**Implementation:**
- `aios/shell.py` — `_multiline_mode` toggle, `Condition` filter for dynamic multiline
- `aios/shell.py` — `escape+enter` key binding for submission in multi-line mode
- `aios/shell.py` — `multiline`, `/multiline`, `ml`, `/ml` command handler
- `aios/ui/completions.py` — added multiline to `COMMAND_REGISTRY`
- `aios/ui/terminal.py` — added Keyboard Shortcuts section to help text

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

> **STATUS: IMPLEMENTED in v0.10.3**

**Impact:** Network issues and rate limits cause immediate failures.

`ErrorRecovery.retry` in `errors.py` does 2 attempts with no delay between them. Repeated failures hammer the API.

**Implementation:**
- `calculate_backoff()` — exponential growth (1s → 2s → 4s...) with ±25% jitter
- `CircuitBreaker` class — CLOSED/OPEN/HALF_OPEN states, configurable threshold
- `ErrorRecovery.retry()` — enhanced with `base_delay`, `max_delay`, `jitter`, `circuit_breaker` params
- `ClaudeClient._make_api_call()` — wraps all API calls with retry + circuit breaker
- Retries on transient errors: `APIConnectionError`, `RateLimitError`, `InternalServerError`
- `get_circuit_breaker_stats()` and `reset_circuit_breaker()` for monitoring

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

> **STATUS: IMPLEMENTED in v0.10.2**

**Impact:** Non-root users can't write to `/var/log/aios/audit.log`.

`config.py` defaults `log_path` to `/var/log/aios/audit.log`. Regular users get permission errors on startup.

**Implementation:**
- Default changed to `~/.config/aios/logs/audit.log`
- Path expands `~` to user home directory
- Directory created automatically if missing
- Fallback to same location on permission errors

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

> **STATUS: IMPLEMENTED in v0.10.5**

`prompt_toolkit` supports reverse history search out of the box but it's not enabled. Users familiar with shell Ctrl+R expect this to work.

**Implementation:**
- `aios/shell.py` — `enable_history_search=True` on `PromptSession`
- `aios/ui/terminal.py` — documented in Keyboard Shortcuts help section

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

> **STATUS: IMPLEMENTED in v0.10.0**

When Claude chains multiple tool calls (e.g. "organize my downloads" triggers 10+ file operations), the user sees individual tool results but no overall progress. A "Step 3/7: Moving PDFs..." display would help.

**Implementation:**
- `MultiStepProgress` class in `aios/ui/terminal.py`
- Shows "Step X/Y: description" with spinner and progress bar
- Only displays for operations with 2+ tool calls
- Human-readable tool descriptions via `_get_tool_description()`
- Completion message: "✓ Completed N operations"

---

## Recommended implementation order (Updated)

| Priority | Item | Status | Rationale |
|----------|------|--------|-----------|
| ~~1~~ | ~~Streaming responses (#1)~~ | **DONE** | ~~Biggest UX win, lowest risk~~ |
| ~~2~~ | ~~Conversation history management (#2)~~ | **DONE** | ~~Prevents crashes in real usage~~ |
| ~~3~~ | ~~shell.py decomposition (#4)~~ | **DONE** | ~~Makes everything else easier to build~~ |
| ~~4~~ | ~~Multi-line input (#5)~~ | **DONE** | ~~Small change, big usability gain~~ |
| 5 | Package manager abstraction (#3) | TODO | Expands the user base significantly |
| 6 | Configurable system prompt (#14) | TODO | Low effort, high customization value |
| ~~7~~ | ~~Exponential backoff (#9)~~ | **DONE** | ~~Reliability improvement~~ |
| 8 | Undo command (#7) | TODO | Completes an existing half-built feature |
| 9 | Conversation export (#6) | TODO | Users need to save useful responses |
| ~~10~~ | ~~Ctrl+R history search (#13)~~ | **DONE** | ~~One-line config change~~ |
| 11 | Clipboard integration (#8) | TODO | Quality-of-life feature |
| ~~12~~ | ~~Audit log path fix (#11)~~ | **DONE** | ~~Quick config fix~~ |
| 13 | Image support (#15) | TODO | Differentiator for non-technical users |
| 14 | Richer rendering (#12) | TODO | Polish |
| ~~15~~ | ~~Progress display (#16)~~ | **DONE** | ~~Polish~~ |
| 16 | Windows/macOS support (#10) | TODO | Large scope, lower priority |

### Next Up (Recommended)
1. **Configurable system prompt (#14)** — Low effort, high value
2. **Package manager abstraction (#3)** — Expands user base
3. **Undo command (#7)** — Completes existing half-built feature
4. **Conversation export (#6)** — Users need to save useful responses
