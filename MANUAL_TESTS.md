# AIOS v0.5.0 Manual Test Checklist

Run these tests to verify all features work end-to-end.
Mark each test with `[x]` when passed or `[!]` if failed.

## Prerequisites

```bash
# Start AIOS (Docker)
docker compose up -d --build
docker compose exec -it aios aios

# Or start AIOS (local)
export ANTHROPIC_API_KEY="your-key"
aios
```

---

## 1. Shell Commands

### General Commands

- [ ] **1.1** Type `help` -- should display help with all sections including Plugin Commands, Session Commands, Coding Tasks
- [ ] **1.2** Type `clear` -- screen should clear
- [ ] **1.3** Type `history` -- should show current session summary (session_id, message counts)
- [ ] **1.4** Type `exit` -- should print "Goodbye!" and exit cleanly

### Plugin Commands

- [ ] **1.5** Type `plugins` or `/plugins` -- should show "No plugins loaded" (unless plugins dir populated) or list loaded plugins
- [ ] **1.6** Type `tools` or `/tools` -- should list all 9 built-in tools (run_command, read_file, write_file, search_files, list_directory, get_system_info, manage_application, ask_clarification, open_application)
- [ ] **1.7** Type `recipes` or `/recipes` -- should show "No recipes available" or list available recipes
- [ ] **1.8** Type `stats` or `/stats` -- should display API Usage (requests, tokens), Cache Performance, and Plugins sections

### Session Commands

- [ ] **1.9** Type `sessions` or `/sessions` -- should list previous sessions (or "No previous sessions found" on first run)
- [ ] **1.10** Type `resume nonexistent` -- should show error "Session 'nonexistent' not found"

### Credential Commands

- [ ] **1.11** Type `credentials` or `/credentials` -- should show "Credential store not initialized" or list stored credentials

### Task Commands

- [ ] **1.12** Type `tasks` or `/tasks` -- should show "No background tasks." when no tasks exist
- [ ] **1.13** Press **Ctrl+B** -- should open task browser (same as `tasks` command), then type `b` to go back

### Model Commands

- [ ] **1.14** Type `model` or `/model` -- should display a table of available models with current selection marked
- [ ] **1.15** Type `model 1` -- should change model to the first option and confirm with success message
- [ ] **1.16** Type `model invalid-name` -- should show "Invalid model" error

---

## 2. Plugin System

### Plugin Loading

- [ ] **2.1** Place a test plugin in `~/.config/aios/plugins/` and restart AIOS -- should show "Loaded 1 plugin(s)" on startup
- [ ] **2.2** After loading, `plugins` command should list the plugin with name, version, description
- [ ] **2.3** `tools` command should show the plugin's tools under "Plugin Tools" section

### Plugin Tool Example (Ansible)

To test with the Ansible plugin:
```bash
# Copy plugin to plugins directory
mkdir -p ~/.config/aios/plugins
cp /app/plugins/ansible_network.py ~/.config/aios/plugins/  # Docker
# or
cp plugins/ansible_network.py ~/.config/aios/plugins/         # local
```

- [ ] **2.4** Restart AIOS -- should show "Loaded 1 plugin(s)" and plugin info line
- [ ] **2.5** `plugins` shows "ansible-network" with version and description
- [ ] **2.6** `tools` shows Ansible tools (ansible_run_playbook, ansible_adhoc, etc.)
- [ ] **2.7** `recipes` shows network recipes (network_health_check, network_backup, etc.)

### Plugin Lifecycle

- [ ] **2.8** Start session -- plugins receive on_session_start (no errors in output)
- [ ] **2.9** Exit session -- plugins receive on_session_end (no errors in output)

---

## 3. Caching System

### System Info Cache

- [ ] **3.1** Ask "How much disk space do I have?" -- should get response (cache miss)
- [ ] **3.2** Immediately ask the same question again -- should respond faster (cache hit)
- [ ] **3.3** Type `stats` -- Cache Performance section should show hit rate > 0% for system info

### Query Cache

- [ ] **3.4** Ask a general knowledge question like "What is Linux?" -- should get response
- [ ] **3.5** Ask the exact same question -- should respond instantly from cache (no "Thinking..." spinner)
- [ ] **3.6** Type `stats` -- should reflect the cached queries

### Cache Invalidation

- [ ] **3.7** Wait 60+ seconds and re-ask disk space question -- should refresh (cache expired)

---

## 4. Rate Limiting

### Normal Operation

- [ ] **4.1** Send several messages -- should work normally without rate limit warnings
- [ ] **4.2** Type `stats` -- API Usage should show request count incrementing

### Rate Limit Warning

- [ ] **4.3** If approaching limits, should see warning: "Approaching rate limit: X requests remaining this minute"

> Note: To fully test rate limiting, you would need to send 45+ messages in under a minute. This is impractical for manual testing. The automated tests in `test_ratelimit.py` cover this thoroughly.

---

## 5. Session Persistence

### Session Auto-Save

- [ ] **5.1** Start AIOS and have a conversation (2-3 messages)
- [ ] **5.2** Type `exit` to quit
- [ ] **5.3** Verify session file exists: `ls ~/.config/aios/history/session_*.json`

### Session Listing

- [ ] **5.4** Start AIOS again
- [ ] **5.5** Type `sessions` -- should list the session from step 5.1 with correct date and message count

### Session Resume

- [ ] **5.6** Copy a session ID from the `sessions` output
- [ ] **5.7** Type `resume <session_id>` -- should show:
  - "Resumed session: ..." success message
  - "Session has N message(s) in history"
  - Recent conversation preview (last 5 messages)
  - "Conversation history restored"
- [ ] **5.8** After resuming, ask a follow-up to the previous conversation -- Claude should have context from restored history

### Multiple Sessions

- [ ] **5.9** Run AIOS multiple times with different conversations
- [ ] **5.10** `sessions` should list them all in reverse chronological order (newest first)

---

## 6. Credential Management

### Credential Store Initialization

- [ ] **6.1** Type `credentials` -- should show "Credential store not initialized" on first use

### Credential Storage (via Python API)

Test from within the container or locally:
```python
python3 -c "
from aios.credentials import CredentialStore
from pathlib import Path
import tempfile

# Use temp file for testing
store = CredentialStore(Path(tempfile.mktemp(suffix='.enc')))
store.initialize(master_password='testpass123')

# Store credential
store.set('test-service', username='admin', password='secret123', api_key='sk-abc')
print('Stored credential')

# Retrieve credential
cred = store.get('test-service')
print(f'Username: {cred.username}')
print(f'Password: {cred.password}')
print(f'API Key: {cred.api_key}')

# List credentials
print(f'All credentials: {store.list()}')

# Delete
store.delete('test-service')
print(f'After delete: {store.list()}')
print('All credential tests passed!')
"
```

- [ ] **6.2** Store a credential -- should succeed
- [ ] **6.3** Retrieve a credential -- should return correct values
- [ ] **6.4** List credentials -- should show the stored name
- [ ] **6.5** Delete a credential -- should remove it from the store

### Encryption Verification

```bash
# Check the credential file is binary (encrypted), not readable JSON
file ~/.config/aios/credentials.enc  # Should say "data" not "JSON" or "ASCII"
```

- [ ] **6.6** Credential file should be encrypted (not readable plaintext)

---

## 7. File Content Display

- [ ] **7.1** Ask "Show me the contents of /etc/hostname" -- should display file content in a syntax-highlighted panel
- [ ] **7.2** Ask "Display /etc/os-release" -- should show file with proper formatting
- [ ] **7.3** Ask "Read /app/setup.py" (Docker) or a Python file -- should show syntax-highlighted Python code with line numbers

---

## 8. Error Handling

- [ ] **8.1** Ask to do something that triggers a tool error -- should show user-friendly error, not crash
- [ ] **8.2** Send empty input (just press Enter) -- should silently continue, no crash
- [ ] **8.3** Press Ctrl+C during idle prompt -- should show "Use 'exit' to quit" message, not crash

---

## 9. Claude Integration

### Basic Conversation

- [ ] **9.1** Ask "Hello, what can you do?" -- should get a friendly response
- [ ] **9.2** Ask "Show me my home directory" -- should use list_directory tool and show files
- [ ] **9.3** Ask "What operating system am I running?" -- should use get_system_info tool

### Tool Execution

- [ ] **9.4** Ask "Create a file called test.txt with 'Hello AIOS' in it" -- should ask confirmation, then create file
- [ ] **9.5** Ask "Search for .py files in /app" (Docker) -- should use search_files and list results
- [ ] **9.6** Ask "What processes are running?" -- should show process list

### Safety Guardrails

- [ ] **9.7** Ask "Delete everything on the disk" -- should be blocked by safety guardrails
- [ ] **9.8** Ask to remove a system package -- should require confirmation

---

## 10. Sudo, Timeouts & Streaming

### Sudo

- [ ] **10.1** Ask "Update the system packages" -- Claude should use `use_sudo: true` and the command should be prefixed with `sudo`
- [ ] **10.2** A warning about elevated privileges should appear when sudo is used

### Timeouts

- [ ] **10.3** Ask "Download a large file" -- Claude should set an appropriate `timeout` value (300+)
- [ ] **10.4** When timeout exceeds 60s, an info message like "This operation may take up to N minute(s)" should appear

### Streaming Output

- [ ] **10.5** Ask "Install curl" (or another package) -- should use `long_running: true` and show a live-updating Rich panel with scrolling output
- [ ] **10.6** The streaming display should show line count and description while running
- [ ] **10.7** After completion, a summary line like "Completed. (N lines of output)" should appear

---

## 11. Background Tasks

### Background via Tool Parameter

- [ ] **11.1** Ask "Run a sleep 120 command in the background" -- Claude should use `background: true`
- [ ] **11.2** Should see "Starting in background: ..." info message
- [ ] **11.3** Should see "Background task #1 started. Ctrl+B to view." success message
- [ ] **11.4** The prompt should return immediately (not block for 120 seconds)

### Toolbar Task Indicators

- [ ] **11.5** After starting a background task, the bottom toolbar should show "1 task running" and "Ctrl+B tasks"
- [ ] **11.6** After the task finishes, the toolbar should show "1 finished" until acknowledged

### Completion Notifications

- [ ] **11.7** After a background task finishes, the next time you see the prompt, a notification should appear: "Background task #1 (...) completed." (or "failed.")
- [ ] **11.8** The notification should only appear once (not repeated on subsequent prompts)

### Task Browser (Ctrl+B)

- [ ] **11.9** Press **Ctrl+B** (or type `tasks`) -- should open the task browser showing a Rich table
- [ ] **11.10** The table should have columns: ID, Status, Description, Elapsed, Lines, Command
- [ ] **11.11** A running task should show status `RUNNING` in cyan
- [ ] **11.12** A finished task should show `COMPLETED` (green) or `FAILED` (red)

### Task Browser Actions

- [ ] **11.13** Type `v <id>` -- should show the last 200 lines of task output in a panel
- [ ] **11.14** Type `a <id>` on a running task -- should attach to live output with a scrolling display; press Ctrl+C to detach
- [ ] **11.15** Type `a <id>` on a finished task -- should show "Task is not running. Use 'v' to view output."
- [ ] **11.16** Type `k <id>` on a running task -- should kill it and show "Task #N killed."
- [ ] **11.17** Type `k <id>` on a finished task -- should show "Task already finished."
- [ ] **11.18** Type `t <id>` on a running task -- should send SIGTERM and show "Sent SIGTERM to task #N."
- [ ] **11.19** Type `r <id>` on a finished task -- should remove it and show "Task #N removed."
- [ ] **11.20** Type `r <id>` on a running task -- should show "Cannot remove a running task. Kill it first."
- [ ] **11.21** Type `b` -- should exit the browser and return to the main prompt

### Ctrl+C to Background

- [ ] **11.22** Ask Claude to run a long streaming command (e.g. "Run ping -c 100 localhost with long_running enabled")
- [ ] **11.23** While output is streaming, press **Ctrl+C** -- should see prompt: "Background this task? [y/N]:"
- [ ] **11.24** Type `y` -- should see "Backgrounded as task #N. Ctrl+B to view." and return to prompt
- [ ] **11.25** Press **Ctrl+B** -- the adopted task should appear in the browser with its accumulated output
- [ ] **11.26** Repeat Ctrl+C on a streaming command and type `n` (or just Enter) -- should kill the process and return "Cancelled by user"

### Multiple Background Tasks

- [ ] **11.27** Start 2-3 background tasks (e.g. `sleep 60`, `sleep 90`, `sleep 120`)
- [ ] **11.28** Toolbar should show correct running count (e.g. "3 tasks running")
- [ ] **11.29** Task browser should list all tasks with incrementing IDs
- [ ] **11.30** Kill one task -- running count should decrease

### Cleanup on Exit

- [ ] **11.31** Start a background task, then type `exit`
- [ ] **11.32** All running background tasks should be killed (verify with `ps` or Docker logs -- no orphan sleep processes)

---

## 12. Claude Code Interactive Sessions

### Prerequisites

Claude Code CLI must be installed (`npm install -g @anthropic-ai/claude-code`).
The Docker image includes it; for local testing, install it first.

### Availability Check

- [ ] **12.1** If Claude Code CLI is **not installed**, type `code` -- should show "Claude Code is not available" with install instructions
- [ ] **12.2** If Claude Code CLI **is installed**, type `code` -- should proceed to auth mode chooser (first use) or launch directly

### Auth Mode Chooser (First Use)

- [ ] **12.3** On first `code` invocation (no `auth_mode` in config), should display:
  - "Claude Code Authentication" header
  - "1. API Key" and "2. Subscription" options
  - Prompt "Choose auth mode (1 or 2) [1]:"
- [ ] **12.4** Enter `1` (or press Enter for default) -- should show "Auth mode set to: api_key"
- [ ] **12.5** Enter `2` -- should show "Auth mode set to: subscription"
- [ ] **12.6** Verify choice is persisted: check `~/.config/aios/config.toml` contains `auth_mode = "api_key"` (or `"subscription"`) under `[code]`
- [ ] **12.7** On subsequent `code` invocations, should **not** re-prompt for auth mode (goes straight to launch)

### Bare Interactive Launch

- [ ] **12.8** Type `code` -- should print:
  - "Launching Claude Code..."
  - "You'll return to AIOS when you exit."
- [ ] **12.9** Claude Code interactive session should take over the terminal (you should see Claude Code's own UI)
- [ ] **12.10** Type `/exit` or Ctrl+C inside Claude Code to exit -- should return to AIOS prompt
- [ ] **12.11** After returning, should see "Claude Code session ended." success message

### Launch with Initial Prompt

- [ ] **12.12** Type `code build a hello world Python script` -- should launch Claude Code with the prompt pre-loaded
- [ ] **12.13** Claude Code should start working on the given prompt immediately
- [ ] **12.14** Exit Claude Code -- should return to AIOS with success message

### Code-Sessions

- [ ] **12.15** Type `code-sessions` -- should list previous code sessions in a table with columns: ID, Date, Task, Directory
- [ ] **12.16** The table should **not** have an "Events" column (removed in v0.5.0)
- [ ] **12.17** If no sessions exist, should show "No previous code sessions found."

### Code-Continue (Resume)

- [ ] **12.18** Copy a session ID from `code-sessions` output
- [ ] **12.19** Type `code-continue <id>` -- should print "Resuming code session: <id>" then launch with `--resume`
- [ ] **12.20** Type `code-continue <id> fix the bug in main.py` -- should resume the session with the given prompt
- [ ] **12.21** Type `code-continue nonexistent` -- should show "Code session 'nonexistent' not found" error

### Auto-Detection

- [ ] **12.22** With `auto_detect = true` in config, type a coding request like "write a Python script to sort files" -- should see:
  - "This looks like a coding task. Routing to Claude Code..."
  - Tip about using `code` for explicit mode
  - Claude Code session should launch with the request as prompt
- [ ] **12.23** Non-coding requests like "show disk space" should **not** trigger auto-detection

### Auth Mode Behavior

- [ ] **12.24** With `auth_mode = "api_key"`: Claude Code should use the ANTHROPIC_API_KEY from AIOS config/environment
- [ ] **12.25** With `auth_mode = "subscription"`: Claude Code should use the user's paid subscription (ANTHROPIC_API_KEY is removed from env so claude falls back to its own login)

### Error Handling

- [ ] **12.26** If Claude Code exits with a non-zero return code, should see an error message (not crash)
- [ ] **12.27** If Claude Code is interrupted (Ctrl+C), should return to AIOS gracefully

### Help Text

- [ ] **12.28** Type `help` -- Coding Tasks section should list:
  - `code` as "Launch Claude Code interactive session"
  - `code <task>` as "Launch Claude Code with an initial prompt"
  - `code-continue <id>` as "Resume a previous code session"
  - `code-sessions` as "List previous code sessions"

### Tab Completion

- [ ] **12.29** Type `cod` and press Tab -- should complete to `code`
- [ ] **12.30** Type `code-c` and press Tab -- should complete to `code-continue`
- [ ] **12.31** Type `code-continue ` and press Tab -- should show available code session IDs

---

## 13. Docker-Specific Tests

- [ ] **13.1** Container starts without errors: `docker compose up -d && docker compose logs`
- [ ] **13.2** Version check: `docker compose exec aios python3 -c "import aios; print(aios.__version__)"` -- should print "0.5.0"
- [ ] **13.3** All imports work:
  ```bash
  docker compose exec aios python3 -c "
  from aios.cache import LRUCache
  from aios.ratelimit import TokenBucket
  from aios.plugins import PluginBase
  from aios.credentials import CredentialStore
  from aios.tasks import TaskManager, TaskStatus, BackgroundTask
  from aios.tasks.browser import TaskBrowser
  from aios.code import CodeRunner, LaunchResult, CodeSession
  from aios.config import CodeConfig
  print('All imports OK')
  "
  ```
- [ ] **13.4** Config directories exist: `docker compose exec aios ls -la /home/aios/.config/aios/`
- [ ] **13.5** Claude Code CLI is available: `docker compose exec aios which claude` -- should print a path

---

## 14. Automated Test Suite

Run inside Docker or locally to confirm all automated tests pass:

```bash
# Docker
docker compose exec aios bash -c "cd /app && pip install pytest pytest-cov pytest-asyncio && pytest tests/ -v"

# Local
pytest tests/ -v
```

- [ ] **14.1** All 385 tests pass
- [ ] **14.2** No test failures or errors
- [ ] **14.3** Skipped tests are only platform-specific (Windows vs Linux)

---

## Test Summary

| Category | Tests | Passed | Failed |
|----------|-------|--------|--------|
| Shell Commands | 16 | | |
| Plugin System | 9 | | |
| Caching System | 7 | | |
| Rate Limiting | 3 | | |
| Session Persistence | 10 | | |
| Credential Management | 6 | | |
| File Content Display | 3 | | |
| Error Handling | 3 | | |
| Claude Integration | 8 | | |
| Sudo, Timeouts & Streaming | 7 | | |
| Background Tasks | 32 | | |
| Claude Code Interactive | 31 | | |
| Docker-Specific | 5 | | |
| Automated Tests | 3 | | |
| **Total** | **143** | | |

---

**Tester**: _______________
**Date**: _______________
**Version**: 0.5.0
**Environment**: Docker / Local (circle one)
**OS**: _______________
**Python**: _______________
