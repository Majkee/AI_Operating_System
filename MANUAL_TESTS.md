# AIOS v0.14.0 Manual Test Checklist

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

- [ ] **1.1** Type `help` -- should display help with all sections including Skill Commands, Session Commands, Coding Tasks
- [ ] **1.2** Type `clear` -- screen should clear
- [ ] **1.3** Type `history` -- should show current session summary (session_id, message counts)
- [ ] **1.4** Type `exit` -- should print "Goodbye!" and exit cleanly
- [ ] **1.5** Type `show` or `/show` -- should show "No streaming output stored" (or last command output if available)

### Skill Commands

- [ ] **1.6** Type `skills` or `/skills` -- should show "No skills loaded" (unless skills dir populated) or list loaded skills
- [ ] **1.7** Type `tools` or `/tools` -- should list all 9 built-in tools (run_command, read_file, write_file, search_files, list_directory, get_system_info, manage_application, ask_clarification, open_application)
- [ ] **1.8** Type `recipes` or `/recipes` -- should show "No recipes available" or list available recipes
- [ ] **1.9** Type `stats` or `/stats` -- should display API Usage (requests, tokens), Cache Performance, and Skills sections

### Session Commands

- [ ] **1.10** Type `sessions` or `/sessions` -- should list previous sessions (or "No previous sessions found" on first run)
- [ ] **1.11** Type `resume nonexistent` -- should show error "Session 'nonexistent' not found"

### Credential Commands

- [ ] **1.12** Type `credentials` or `/credentials` -- should show "Credential store not initialized" or list stored credentials

### Task Commands

- [ ] **1.13** Type `tasks` or `/tasks` -- should show "No background tasks." when no tasks exist
- [ ] **1.14** Press **Ctrl+B** -- should open task browser (same as `tasks` command), then type `b` to go back

### Model Commands

- [ ] **1.15** Type `model` or `/model` -- should display a table of available models with current selection marked
- [ ] **1.16** Type `model 1` -- should change model to the first option and confirm with success message
- [ ] **1.17** Type `model invalid-name` -- should show "Invalid model" error

### Config Commands

- [ ] **1.18** Type `config` or `/config` -- should open interactive configuration menu with numbered settings table
- [ ] **1.19** Enter `0` or press Enter with no input -- should exit config menu
- [ ] **1.20** Enter an invalid number (e.g. `99`) -- should show "Invalid selection" error

---

## 2. Skill System

### Skill Loading

- [ ] **2.1** Place a test skill in `~/.config/aios/skills/` and restart AIOS -- should show "Loaded 1 skill(s)" on startup
- [ ] **2.2** After loading, `skills` command should list the skill with name, version, description
- [ ] **2.3** `tools` command should show the skill's tools under "Skill Tools" section

### Skill Tool Example (Ansible)

To test with the Ansible skill:
```bash
# Copy skill to skills directory
mkdir -p ~/.config/aios/skills
cp /app/skills/ansible_network.py ~/.config/aios/skills/  # Docker
# or
cp skills/ansible_network.py ~/.config/aios/skills/         # local
```

- [ ] **2.4** Restart AIOS -- should show "Loaded 1 skill(s)" and skill info line
- [ ] **2.5** `skills` shows "ansible-network" with version and description
- [ ] **2.6** `tools` shows Ansible tools (ansible_run_playbook, ansible_adhoc, etc.)
- [ ] **2.7** `recipes` shows network recipes (network_health_check, network_backup, etc.)

### Skill Lifecycle

- [ ] **2.8** Start session -- skills receive on_session_start (no errors in output)
- [ ] **2.9** Exit session -- skills receive on_session_end (no errors in output)

---

## 3. Caching System

### Tool Result Cache

- [ ] **3.1** Ask "How much disk space do I have?" -- should get response (tool executes, cache miss)
- [ ] **3.2** Immediately ask the same question -- tool result should be served from cache; Claude still generates fresh prose (one API call but no subprocess/psutil)
- [ ] **3.3** Type `stats` -- Tool Result Cache section should show hit rate > 0% with hits/misses

### Cache Invalidation

- [ ] **3.4** Ask "List files in /tmp" -- Claude uses `list_directory`, result cached
- [ ] **3.5** Ask "Create a file called /tmp/test_cache.txt" -- `write_file` should invalidate `list_directory` cache
- [ ] **3.6** Ask "List files in /tmp" again -- should be a fresh tool execution (cache was invalidated)
- [ ] **3.7** Run any shell command (e.g. "Run ls") -- `run_command` should invalidate all tool caches

### TTL Expiration

- [ ] **3.8** Wait 30+ seconds and re-ask disk space question -- should refresh (get_system_info TTL is 30s)

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

- [ ] **10.5** Ask "Install curl" (or another package) -- should use `long_running: true` and show a Progress display with spinner, line count, and elapsed time
- [ ] **10.6** The streaming display should show "⚙ Installing curl ████████ 123 lines 0:00:15" format while running
- [ ] **10.7** After completion, a summary line like "✓ Completed (123 lines)" should appear

### Show Command for Output Details

- [ ] **10.8** After a streaming command completes, type `show` -- should display the last output in a panel
- [ ] **10.9** The panel should show total line count and truncation info if applicable
- [ ] **10.10** After viewing, `show` again should say "No streaming output stored" (cleared after viewing)

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

## 13. Streaming Responses

### Basic Streaming

- [ ] **13.1** Ask "Tell me about Linux" -- response should stream word-by-word with live Markdown rendering (not appear all at once)
- [ ] **13.2** Watch for spinner → text transition: should see "Thinking..." spinner, then "AIOS:" header, then streaming text
- [ ] **13.3** Ask a question that triggers a tool (e.g. "Show disk usage") -- tool executes, then Claude's response streams

### Streaming Config

- [ ] **13.4** Type `config`, select `api.streaming`, set to OFF -- should save and confirm
- [ ] **13.5** Ask a question -- response should appear all at once (old behavior) with spinner until complete
- [ ] **13.6** Re-enable streaming via config -- streaming should resume

---

## 14. Interactive Config Menu

### Menu Navigation

- [ ] **14.1** Type `config` -- should show table with columns: #, Setting, Value, Description
- [ ] **14.2** Settings should include: api.streaming, api.model, api.max_tokens, api.context_budget, api.summarize_threshold, api.min_recent_messages, ui.*, safety.*, code.*
- [ ] **14.3** Boolean values should show ON (green) or OFF (red)

### Changing Boolean Settings

- [ ] **14.4** Select a boolean setting (e.g. `api.streaming`) -- should show "1. ON" and "2. OFF" options
- [ ] **14.5** Select "1" or "2" -- should update value and show confirmation
- [ ] **14.6** Enter "0" -- should cancel without changing

### Changing Model (Dropdown)

- [ ] **14.7** Select `api.model` -- should show numbered list of available models with descriptions
- [ ] **14.8** Select a model number -- should update and show "Updated api.model to: ..."
- [ ] **14.9** Changes should persist after restarting AIOS (check `~/.config/aios/config.toml`)

### Changing Numeric Settings

- [ ] **14.10** Select `api.max_tokens` -- should prompt for numeric input
- [ ] **14.11** Enter a valid number -- should update successfully
- [ ] **14.12** Enter invalid input (e.g. "abc") -- should show error and re-prompt or cancel

### Changing Summarization Settings

- [ ] **14.13** Select `api.context_budget` -- should allow entering value between 50000-200000
- [ ] **14.14** Select `api.summarize_threshold` -- should show dropdown: 50% to 90%
- [ ] **14.15** Select `api.min_recent_messages` -- should show dropdown: 2 to 20 messages

---

## 15. Context Window Management

### Context Stats

- [ ] **15.1** Have a conversation (5-10 messages) then type `stats` -- should show context usage in API stats
- [ ] **15.2** Type `history` -- should show context usage percentage and active message count

### Automatic Summarization

- [ ] **15.3** Configure low context budget: `config` → `api.context_budget` → set to 5000 (very low for testing)
- [ ] **15.4** Have a long conversation (10+ messages) -- should see log message about summarization triggered
- [ ] **15.5** After summarization, `history` should show "Summarized messages: N" count
- [ ] **15.6** Subsequent questions should still have context from summarized history (Claude remembers earlier topics)

### Summary in System Prompt

- [ ] **15.7** After summarization, Claude's responses should reflect knowledge from the summary
- [ ] **15.8** Ask "What did we discuss earlier?" -- should recall topics from before summarization

### Clear History

- [ ] **15.9** After summarization, type `clear` then ask a question -- Claude should have no memory of previous conversation (summary also cleared)

### Threshold Configuration

- [ ] **15.10** Set `summarize_threshold` to 0.5 (50%) via config -- summarization should trigger earlier
- [ ] **15.11** Set `min_recent_messages` to 2 via config -- only 2 messages should be kept verbatim after summarization

---

## 16. Multi-Step Progress Awareness

### Progress Display for Tool Chains

- [ ] **16.1** Ask "Show me disk usage, memory usage, and list of running processes" -- should trigger multiple tool calls
- [ ] **16.2** Should see "Step 1/3: Getting system info..." with spinner and progress bar
- [ ] **16.3** Should see steps incrementing: "Step 2/3: ...", "Step 3/3: ..."
- [ ] **16.4** After completion, should see "✓ Completed 3 operations"

### Single Tool Operations

- [ ] **16.5** Ask "Show me disk usage" (single tool) -- should NOT show progress bar (clean output)
- [ ] **16.6** Only multi-step operations (2+ tools) should display the progress indicator

### Human-Readable Descriptions

- [ ] **16.7** Progress should show friendly descriptions like "Reading: config.yaml" or "Running: ls -la..."
- [ ] **16.8** Long commands should be truncated to ~40 characters with "..."

---

## 17. Exponential Backoff and Circuit Breaker

### Backoff Behavior

Test using Python API:
```python
docker compose exec aios python3 -c "
from aios.errors import calculate_backoff

# Verify exponential growth
for attempt in range(1, 6):
    delay = calculate_backoff(attempt, base_delay=1.0, jitter=False)
    print(f'Attempt {attempt}: {delay:.1f}s')

# Expected: 1.0, 2.0, 4.0, 8.0, 16.0
"
```

- [ ] **17.1** Backoff grows exponentially: 1s → 2s → 4s → 8s → 16s...
- [ ] **17.2** Backoff is capped at `max_delay` (default 30s for client, 60s for general)
- [ ] **17.3** Jitter adds ±25% variation to prevent thundering herd

### Circuit Breaker

Test using Python API:
```python
docker compose exec aios python3 -c "
from aios.errors import CircuitBreaker

cb = CircuitBreaker(failure_threshold=3, recovery_timeout=5.0)
print(f'Initial: {cb.state}')  # closed

for i in range(3):
    cb.record_failure()
    print(f'After failure {i+1}: {cb.state}')

print(f'Allow request: {cb.allow_request()}')  # False

cb.reset()
print(f'After reset: {cb.state}')  # closed
"
```

- [ ] **17.4** Circuit starts in CLOSED state
- [ ] **17.5** After N consecutive failures (default 5), circuit opens
- [ ] **17.6** Open circuit rejects requests immediately (returns error without calling API)
- [ ] **17.7** After recovery timeout, circuit transitions to HALF_OPEN
- [ ] **17.8** Success in HALF_OPEN closes circuit; failure reopens it
- [ ] **17.9** `reset()` returns circuit to CLOSED state

### Client Integration

```python
docker compose exec aios python3 -c "
import os
os.environ['ANTHROPIC_API_KEY'] = 'test-key'

from aios.claude.client import ClaudeClient

client = ClaudeClient()
print(f'Circuit breaker: {client._circuit_breaker is not None}')
print(f'Retry config: {client._retry_config}')
print(f'Stats: {client.get_circuit_breaker_stats()}')
"
```

- [ ] **17.10** ClaudeClient has circuit breaker with default settings (threshold=5, timeout=60s)
- [ ] **17.11** Retry config has max_attempts=3, base_delay=1.0, max_delay=30.0
- [ ] **17.12** `get_circuit_breaker_stats()` returns state, failure_count, etc.
- [ ] **17.13** `reset_circuit_breaker()` resets to closed state

### Retryable Exceptions

- [ ] **17.14** Client retries on: `APIConnectionError`, `RateLimitError`, `InternalServerError`, `ConnectionError`, `TimeoutError`
- [ ] **17.15** Client does NOT retry on: `AuthenticationError`, `BadRequestError` (non-transient)

---

## 18. Audit Logging

### Log Path

- [ ] **18.1** Default log path should be `~/.config/aios/logs/audit.log` (not `/var/log/aios/`)
- [ ] **18.2** Log directory should be created automatically if it doesn't exist

### Verify Log Location

```bash
docker compose exec aios python3 -c "
from aios.config import get_config
from pathlib import Path

config = get_config()
log_path = Path(config.logging.path).expanduser()
print(f'Log path: {config.logging.path}')
print(f'Expanded: {log_path}')
print(f'Parent exists: {log_path.parent.exists()}')
"
```

- [ ] **18.3** Log path should expand `~` to user home directory
- [ ] **18.4** Works for non-root users (no permission errors)

---

## 19. Docker-Specific Tests

- [ ] **19.1** Container starts without errors: `docker compose up -d && docker compose logs`
- [ ] **19.2** Version check: `docker compose exec aios python3 -c "import aios; print(aios.__version__)"` -- should print "0.10.3"
- [ ] **19.3** All imports work:
  ```bash
  docker compose exec aios python3 -c "
  from aios.cache import LRUCache
  from aios.ratelimit import TokenBucket
  from aios.skills import SkillBase
  from aios.credentials import CredentialStore
  from aios.tasks import TaskManager, TaskStatus, BackgroundTask
  from aios.tasks.browser import TaskBrowser
  from aios.code import CodeRunner, LaunchResult, CodeSession
  from aios.config import CodeConfig
  from aios.errors import CircuitBreaker, ErrorRecovery, calculate_backoff
  print('All imports OK')
  "
  ```
- [ ] **19.4** Config directories exist: `docker compose exec aios ls -la /home/aios/.config/aios/`
- [ ] **19.5** Claude Code CLI is available: `docker compose exec aios which claude` -- should print a path
- [ ] **19.6** Audit log directory: `docker compose exec aios ls -la /home/aios/.config/aios/logs/` -- should exist or be creatable

---

## 20. Automated Test Suite

Run inside Docker or locally to confirm all automated tests pass:

```bash
# Docker
docker compose exec aios bash -c "cd /app && pip install pytest pytest-cov pytest-asyncio && pytest tests/ -v"

# Local
pytest tests/ -v
```

- [ ] **20.1** All 623 tests pass
- [ ] **20.2** No test failures or errors
- [ ] **20.3** Skipped tests are only platform-specific (Windows vs Linux)

---

## 21. Prompts Command (Power User)

### Viewing Prompts

- [ ] **21.1** Type `prompts` or `/prompts` -- should display full system prompt in syntax-highlighted panel
- [ ] **21.2** Type `prompts sections` -- should show table with all prompt sections (key, title, enabled status)
- [ ] **21.3** Type `prompts view role` -- should display just the "role" section content
- [ ] **21.4** Type `prompts view nonexistent` -- should show "Section 'nonexistent' not found" error
- [ ] **21.5** Type `prompts help` -- should display help with all subcommands

### Modifying Prompts (Power User Warning)

- [ ] **21.6** Type `prompts disable safety` -- should show POWER USER WARNING panel with confirmation prompt
- [ ] **21.7** Enter `n` at confirmation -- should cancel and show "Cancelled"
- [ ] **21.8** Type `prompts disable safety` again, enter `y` -- should disable section and show success
- [ ] **21.9** Type `prompts sections` -- "safety" section should now show "Disabled" (red)
- [ ] **21.10** Type `prompts enable safety` with confirmation -- should re-enable section
- [ ] **21.11** Type `prompts sections` -- "safety" section should show "Enabled" (green)

### Config Persistence

- [ ] **21.12** After disabling a section, check `~/.config/aios/config.toml` -- should have `disabled_sections = ["safety"]` under `[prompts]`
- [ ] **21.13** Restart AIOS -- disabled sections should remain disabled
- [ ] **21.14** Type `prompts reset` with confirmation -- should restore all defaults
- [ ] **21.15** Check config file -- `disabled_sections` should be empty

### Provider Integration

- [ ] **21.16** With AIOS_PROVIDER=anthropic, `prompts` shows unified prompt
- [ ] **21.17** With AIOS_PROVIDER=openai, `prompts` shows same unified prompt structure
- [ ] **21.18** With AIOS_PROVIDER=lmstudio, `prompts` shows same unified prompt structure

### Help and Completion

- [ ] **21.19** Type `help` -- should include "Power User" section with prompts commands
- [ ] **21.20** Type `prom` and press Tab -- should complete to `prompts`
- [ ] **21.21** Double-tap Tab on empty input -- should show `prompts` in command list

---

## Test Summary

| Category | Tests | Passed | Failed |
|----------|-------|--------|--------|
| Shell Commands | 20 | | |
| Skill System | 9 | | |
| Caching System | 8 | | |
| Rate Limiting | 3 | | |
| Session Persistence | 10 | | |
| Credential Management | 6 | | |
| File Content Display | 3 | | |
| Error Handling | 3 | | |
| Claude Integration | 8 | | |
| Sudo, Timeouts & Streaming | 10 | | |
| Background Tasks | 32 | | |
| Claude Code Interactive | 31 | | |
| Streaming Responses | 6 | | |
| Interactive Config Menu | 15 | | |
| Context Window Management | 11 | | |
| Multi-Step Progress | 8 | | |
| Exponential Backoff & Circuit Breaker | 15 | | |
| Audit Logging | 4 | | |
| Docker-Specific | 6 | | |
| Automated Tests | 3 | | |
| Prompts Command | 21 | | |
| **Total** | **232** | | |

---

**Tester**: _______________
**Date**: _______________
**Version**: 0.14.0
**Environment**: Docker / Local (circle one)
**OS**: _______________
**Python**: _______________
