# Multi-Provider LLM Support

AIOS now supports multiple LLM providers: **Anthropic Claude**, **OpenAI GPT**, and **LM Studio** (local models).

## Overview

This release introduces an abstract provider pattern that allows AIOS to work with different LLM backends through a unified interface. The implementation uses a strategy pattern with a factory function for creating the appropriate client.

## Architecture

```
BaseClient (abstract)
    ├── AnthropicClient (Claude models)
    ├── OpenAIClient (GPT models via Responses API)
    └── LMStudioClient (Local models via Chat Completions)
```

### Package Structure

```
aios/providers/
├── __init__.py           # Package exports
├── base.py               # BaseClient ABC, AssistantResponse dataclass
├── anthropic_client.py   # Anthropic Claude implementation
├── openai_client.py      # OpenAI Responses API client
├── lmstudio_client.py    # LM Studio Chat Completions client
├── tool_converters.py    # Tool format conversion utilities
└── factory.py            # create_client() factory function
```

## Supported Models

### Anthropic (Default)
| Model ID | Name | Speed | Cost |
|----------|------|-------|------|
| claude-haiku-4-5 | Claude Haiku 4.5 | Fast | Low |
| claude-sonnet-4-5-20250929 | Claude Sonnet 4.5 | Medium | Medium |
| claude-opus-4-20250514 | Claude Opus 4 | Slow | High |

### OpenAI
| Model ID | Name | Speed | Cost |
|----------|------|-------|------|
| gpt-5.2 | GPT-5.2 | Medium | High |
| gpt-5.2-pro | GPT-5.2 Pro | Slow | High |
| gpt-5.2-codex | GPT-5.2 Codex | Medium | High |
| gpt-5-mini | GPT-5 Mini | Fast | Medium |
| gpt-5-nano | GPT-5 Nano | Fast | Low |

### LM Studio (Local)
| Model ID | Name | Speed | Cost |
|----------|------|-------|------|
| Qwen/Qwen2.5-Coder-7B-Instruct-GGUF | Qwen 2.5 Coder 7B | Fast | Free |
| lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF | Llama 3.1 8B | Fast | Free |

## Configuration

### Environment Variables

```bash
# Provider selection
AIOS_PROVIDER=anthropic|openai|lm_studio

# Anthropic
AIOS_API_KEY=sk-ant-...
# or
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
OPENAI_API_KEY=sk-...

# LM Studio
AIOS_OPENAI_BASE_URL=http://localhost:1234/v1
```

### Config File (~/.config/aios/config.toml)

```toml
[api]
# LLM provider: anthropic, openai, or lm_studio
provider = "anthropic"

# Anthropic API key (required for anthropic provider)
api_key = "sk-ant-..."

# OpenAI settings (for openai/lm_studio providers)
openai_api_key = "sk-..."
openai_base_url = "http://localhost:1234/v1"  # For LM Studio

# Model to use (provider-specific)
model = "claude-sonnet-4-5-20250929"

max_tokens = 4096
streaming = true
```

## Usage

### Basic Usage

```bash
# Use Anthropic (default)
aios

# Use OpenAI
AIOS_PROVIDER=openai OPENAI_API_KEY=sk-xxx aios

# Use LM Studio (start LM Studio first)
AIOS_PROVIDER=lm_studio AIOS_OPENAI_BASE_URL=http://localhost:1234/v1 aios
```

### Docker

```bash
# Anthropic
docker compose exec aios aios

# OpenAI
docker compose exec -e AIOS_PROVIDER=openai -e OPENAI_API_KEY=sk-xxx aios aios

# LM Studio (from host)
docker compose exec -e AIOS_PROVIDER=lm_studio \
  -e AIOS_OPENAI_BASE_URL=http://host.docker.internal:1234/v1 aios aios
```

### Model Switching at Runtime

```
model                    # List all available models
model gpt-5.2           # Switch to OpenAI
model claude-sonnet-4-5 # Switch back to Anthropic
model 1                 # Switch by number
```

## API Reference

### BaseClient Interface

All provider clients implement the `BaseClient` abstract base class:

```python
from aios.providers import create_client, BaseClient, AssistantResponse

# Create client based on configuration
client = create_client(tool_handler)

# Send a message
response: AssistantResponse = client.send_message(
    user_input="What files are in my home directory?",
    system_context=None,
    on_text=lambda chunk: print(chunk, end="")  # Optional streaming callback
)

# Send tool results
response = client.send_tool_results(
    tool_results=[{"tool_use_id": "xyz", "content": "result"}],
    on_text=lambda chunk: print(chunk, end="")
)

# Clear conversation history
client.clear_history()

# Get/set model
current_model = client.get_model()
client.set_model("gpt-5.2")
```

### AssistantResponse

```python
@dataclass
class AssistantResponse:
    text: str                          # Response text content
    tool_calls: list[dict[str, Any]]   # [{id, name, input}, ...]
    is_complete: bool                  # True if response is complete
    requires_action: bool              # True if tool calls need execution
    pending_confirmations: list[dict]  # Tools requiring user confirmation
```

### Factory Function

```python
from aios.providers import create_client

# Create client based on config
client = create_client(tool_handler)

# Create client with specific provider
client = create_client(tool_handler, provider="openai")
```

## Provider-Specific Notes

### OpenAI

- Uses the new **Responses API** (`client.responses.create()`)
- Supports response chaining via `previous_response_id` for multi-turn conversations
- Tool calling uses `function_call` format

### LM Studio

- Uses **Chat Completions API** (OpenAI-compatible)
- Tool calling support varies by model (auto-detected)
- Falls back to text-only mode if tools not supported
- Default base URL: `http://localhost:1234/v1`

### Anthropic

- Full feature parity with previous implementation
- Includes context window management with automatic summarization
- Circuit breaker for API resilience
- Retry with exponential backoff

## Backward Compatibility

The legacy `ClaudeClient` class is maintained for backward compatibility:

```python
# Old way (deprecated, still works)
from aios.claude.client import ClaudeClient
client = ClaudeClient(tool_handler)  # Shows deprecation warning

# New way (recommended)
from aios.providers import create_client
client = create_client(tool_handler)
```

## Tool Format Conversion

Tools are defined in Anthropic format and automatically converted for OpenAI:

| Aspect | Anthropic | OpenAI Responses API |
|--------|-----------|---------------------|
| Tool def | `{"name", "description", "input_schema"}` | `{"type": "function", "name", "description", "parameters"}` |
| Tool call | `{"type": "tool_use", "id", "name", "input"}` | `{"type": "function_call", "call_id", "name", "arguments"}` |
| Tool result | `{"type": "tool_result", "tool_use_id", "content"}` | `{"type": "function_call_output", "call_id", "output"}` |

## Files Changed

### New Files
- `aios/providers/__init__.py`
- `aios/providers/base.py`
- `aios/providers/anthropic_client.py`
- `aios/providers/openai_client.py`
- `aios/providers/lmstudio_client.py`
- `aios/providers/tool_converters.py`
- `aios/providers/factory.py`

### Modified Files
- `pyproject.toml` - Added `openai>=2.16.0` dependency
- `requirements.txt` - Added `openai>=2.16.0`
- `aios/config.py` - Added provider settings
- `aios/models.py` - Added OpenAI/LM Studio models
- `aios/data/default.toml` - Added provider config section
- `aios/shell.py` - Uses factory instead of direct ClaudeClient
- `aios/main.py` - Updated for factory pattern
- `aios/commands/config.py` - Updated to use BaseClient interface
- `aios/commands/sessions.py` - Updated to use BaseClient interface
- `aios/claude/client.py` - Deprecated wrapper for backward compatibility
- `aios/claude/__init__.py` - Lazy imports to avoid circular dependencies

## Testing

All 608 existing tests pass with the new provider architecture:

```bash
pytest tests/ -v
# 608 passed, 10 skipped (Windows-specific)
```
