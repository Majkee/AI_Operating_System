# OpenAI Implementation for AIOS

This document provides a comprehensive technical overview of the OpenAI provider implementation in AIOS, supporting the GPT-5.2 model family with the modern Responses API.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Supported Models](#supported-models)
3. [Responses API Integration](#responses-api-integration)
4. [Tool Conversion System](#tool-conversion-system)
5. [GPT-5.2 Specific Features](#gpt-52-specific-features)
6. [Response Chaining](#response-chaining)
7. [Error Handling](#error-handling)
8. [Configuration](#configuration)
9. [Usage Examples](#usage-examples)

---

## Architecture Overview

The OpenAI implementation follows AIOS's multi-provider architecture pattern, implementing the `BaseClient` abstract interface to ensure consistency across all LLM providers.

### File Structure

```
aios/providers/
├── __init__.py           # Package exports
├── base.py               # BaseClient abstract class
├── openai_client.py      # OpenAI Responses API client
├── tool_converters.py    # Cross-provider tool format conversion
└── factory.py            # Provider factory pattern
```

### Class Hierarchy

```
BaseClient (ABC)
    ├── AnthropicClient    # Claude models
    ├── OpenAIClient       # GPT-5.2 family (Responses API)
    └── LMStudioClient     # Local models (Chat Completions API)
```

### Key Design Decisions

1. **Responses API over Chat Completions**: We use OpenAI's newer Responses API (`client.responses.create()`) instead of Chat Completions for:
   - Better tool handling
   - Response chaining via `previous_response_id`
   - Improved reasoning model support
   - 3% higher accuracy on benchmarks (per OpenAI)

2. **Strict Mode by Default**: All function tools use `strict: true` for reliable schema adherence with GPT-5.2+.

3. **Unified Tool Format**: Tools are defined in Anthropic format internally and converted for each provider.

---

## Supported Models

### GPT-5.2 Family (Latest)

| Model ID | Name | Best For | Speed | Cost |
|----------|------|----------|-------|------|
| `gpt-5.2` | GPT-5.2 | Complex reasoning, agentic tasks, code generation | Medium | High |
| `gpt-5.2-pro` | GPT-5.2 Pro | Tough problems requiring extended thinking | Slow | High |
| `gpt-5.2-codex` | GPT-5.2 Codex | Agentic coding workflows, development tasks | Medium | High |
| `gpt-5-mini` | GPT-5 Mini | Cost-optimized reasoning and chat | Fast | Medium |
| `gpt-5-nano` | GPT-5 Nano | High-throughput, simple tasks, classification | Fast | Low |

### Legacy Models (Still Supported)

| Model ID | Name | Notes |
|----------|------|-------|
| `gpt-4o` | GPT-4o (Legacy) | Consider upgrading to GPT-5.2 |
| `gpt-4o-mini` | GPT-4o Mini (Legacy) | Consider upgrading to GPT-5 Mini |

### Model Detection

```python
from aios.models import is_gpt5_model, is_reasoning_model, supports_verbosity

# GPT-5.x family detection
is_gpt5_model("gpt-5.2")      # True
is_gpt5_model("gpt-5-mini")   # True
is_gpt5_model("gpt-4o")       # False

# Reasoning support detection (GPT-5.x + o-series)
is_reasoning_model("gpt-5.2")   # True
is_reasoning_model("o3-mini")   # True
is_reasoning_model("gpt-4o")    # False

# Verbosity support (GPT-5.x only)
supports_verbosity("gpt-5.2")   # True
supports_verbosity("o3-mini")   # False
```

---

## Responses API Integration

### Basic Request Flow

```python
from openai import OpenAI

client = OpenAI()

response = client.responses.create(
    model="gpt-5.2",
    instructions="You are a helpful assistant.",
    input="Hello, how are you?",
    tools=[...],
    max_output_tokens=4096,
    previous_response_id=None,  # For chaining
)
```

### Response Structure

The Responses API returns a structured response with:

```python
{
    "id": "resp_abc123...",
    "object": "response",
    "output": [
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "output_text", "text": "Hello!"}
            ]
        }
    ],
    "output_text": "Hello!"  # Convenience accessor
}
```

### Function Calls in Response

When the model calls a function:

```python
{
    "output": [
        {
            "type": "function_call",
            "call_id": "call_xyz789",
            "name": "run_command",
            "arguments": "{\"command\": \"ls -la\"}"
        }
    ]
}
```

### Sending Tool Results

```python
response = client.responses.create(
    model="gpt-5.2",
    input=[
        {
            "type": "function_call_output",
            "call_id": "call_xyz789",
            "output": "file1.txt\nfile2.txt"
        }
    ],
    previous_response_id="resp_abc123...",
)
```

---

## Tool Conversion System

AIOS uses Anthropic's tool format internally. The `tool_converters.py` module handles conversion to OpenAI format.

### Anthropic Format (Internal)

```python
{
    "name": "run_command",
    "description": "Execute a shell command",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "requires_confirmation": {"type": "boolean", "default": False}
        },
        "required": ["command"]
    }
}
```

### OpenAI Responses API Format (Converted)

```python
{
    "type": "function",
    "name": "run_command",
    "description": "Execute a shell command",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "requires_confirmation": {"type": ["boolean", "null"], "default": False}
        },
        "required": ["command", "requires_confirmation"],
        "additionalProperties": False
    },
    "strict": True
}
```

### Strict Mode Requirements

OpenAI's strict mode (`strict: true`) enforces:

1. **ALL properties must be in `required`**: No optional parameters by omission
2. **`additionalProperties: false`**: No extra fields allowed
3. **Nullable types for optional params**: Use `["type", "null"]` union
4. **Nested objects**: All nested object schemas must also follow these rules

The tool converter automatically applies these rules recursively to handle nested objects and array items.

### Conversion Function

```python
from aios.providers.tool_converters import convert_tools_for_openai

# Convert with strict mode (default)
openai_tools = convert_tools_for_openai(anthropic_tools, strict=True)

# Convert without strict mode (legacy compatibility)
openai_tools = convert_tools_for_openai(anthropic_tools, strict=False)
```

### How Optional Parameters Are Handled

The converter automatically transforms optional parameters:

**Before (not in original `required`):**
```python
"requires_confirmation": {"type": "boolean", "default": False}
```

**After (added to `required` with nullable type):**
```python
"requires_confirmation": {"type": ["boolean", "null"], "default": False}
```

This allows the model to either:
- Provide a boolean value
- Provide `null` (which triggers the default)

---

## GPT-5.2 Specific Features

### Reasoning Effort

Controls how many reasoning tokens the model generates before producing a response.

| Level | Description | Use Case |
|-------|-------------|----------|
| `none` | No reasoning (default for GPT-5.2) | Fast responses, simple tasks |
| `low` | Minimal reasoning | Quick analysis |
| `medium` | Moderate reasoning | Balanced tasks |
| `high` | Thorough reasoning | Complex problems |
| `xhigh` | Maximum reasoning (GPT-5.2+ only) | Hardest problems |

```python
from aios.providers import OpenAIClient

client = OpenAIClient()
client.set_reasoning_effort("medium")  # Enable moderate reasoning
```

**API Request with Reasoning:**
```python
response = client.responses.create(
    model="gpt-5.2",
    input="Solve this complex math problem...",
    reasoning={"effort": "high"}
)
```

### Verbosity

Controls output length and detail level.

| Level | Description | Use Case |
|-------|-------------|----------|
| `low` | Concise answers, minimal commentary | SQL queries, short code |
| `medium` | Balanced (default) | General tasks |
| `high` | Thorough explanations, detailed code | Documentation, tutorials |

```python
client.set_verbosity("low")  # Concise responses
```

**API Request with Verbosity:**
```python
response = client.responses.create(
    model="gpt-5.2",
    input="Write a function to sort an array",
    text={"verbosity": "low"}
)
```

### Combined Example

```python
# Configure for complex coding task with detailed output
client.set_reasoning_effort("high")
client.set_verbosity("high")

response = client.send_message(
    "Implement a red-black tree with all operations"
)
```

---

## Response Chaining

The Responses API supports efficient multi-turn conversations via `previous_response_id`.

### How It Works

1. First request returns a response with `id`
2. Subsequent requests pass this `id` as `previous_response_id`
3. The API automatically includes previous context

### Benefits

- **Improved intelligence**: Reasoning tokens from previous turns are preserved
- **Lower costs**: Higher cache hit rates (40-80% improvement)
- **Less latency**: Fewer tokens need to be re-processed

### Implementation in AIOS

```python
class OpenAIClient(BaseClient):
    def __init__(self):
        self._last_response_id: Optional[str] = None

    def send_message(self, user_input: str, ...) -> AssistantResponse:
        response = self.client.responses.create(
            model=self.model,
            input=[{"role": "user", "content": user_input}],
            previous_response_id=self._last_response_id,  # Chain responses
        )
        self._last_response_id = response.id  # Save for next turn
        return self._process_response(response)

    def clear_history(self) -> None:
        self._last_response_id = None  # Break the chain
```

---

## Context Management & Summarization

AIOS uses a reusable `ContextManager` component for automatic conversation summarization across all providers.

### How It Works

1. **Track Messages**: All user, assistant, and tool messages are tracked locally
2. **Monitor Usage**: Token usage is estimated using character-based counting (~4 chars/token)
3. **Auto-Summarize**: When usage exceeds `summarize_threshold` (default 75%), older messages are summarized
4. **Preserve Recent**: The most recent messages (default 6) are always kept verbatim

### OpenAI-Specific Behavior

For OpenAI, summarization integrates with response chaining:

1. When summarization triggers, the response chain is broken (`previous_response_id = None`)
2. The summary is included in the system prompt
3. A new response chain starts with the summarized context
4. If `CONTEXT_LENGTH_EXCEEDED` error occurs, auto-summarizes and retries

### Configuration

```toml
[api]
# Maximum tokens for conversation history (default: 150000)
context_budget = 150000

# Trigger summarization at this percentage (default: 0.75 = 75%)
summarize_threshold = 0.75

# Always keep at least this many recent messages (default: 6)
min_recent_messages = 6
```

### ContextManager API

```python
from aios.providers import ContextManager

# Create with custom summarization function
manager = ContextManager(
    summarize_fn=my_summarize_function,
    context_budget=150000,
    summarize_threshold=0.75,
    min_recent_messages=6,
)

# Add messages
manager.add_message("user", "Hello")
manager.add_message("assistant", "Hi there!")

# Check and summarize if needed
if manager.check_and_summarize():
    print("Conversation was summarized")

# Get messages (includes summary as system message if present)
messages = manager.get_messages()

# Get statistics
stats = manager.get_stats()
print(f"Tokens: {stats.total_tokens}, Summarized: {stats.summarized_message_count}")
```

### Provider Comparison

| Feature | Anthropic | OpenAI | LM Studio |
|---------|-----------|--------|-----------|
| Summarization | ✅ Built-in | ✅ Via ContextManager | ✅ Via ContextManager |
| Default Budget | 150k tokens | 150k tokens | 32k tokens |
| Summary Location | Injected in history | System prompt | System prompt |
| Auto-Recovery | Yes | Yes (on context error) | Yes |

---

## Error Handling

### OpenAI-Specific Errors

The client converts OpenAI SDK exceptions to user-friendly `OpenAIError`:

| SDK Exception | Error Code | User Message |
|---------------|------------|--------------|
| `AuthenticationError` | `AUTH_ERROR` | Invalid API key |
| `RateLimitError` | `RATE_LIMIT` | Rate limited |
| `RateLimitError` | `TOKEN_RATE_LIMIT` | Token rate limited |
| `RateLimitError` | `QUOTA_EXCEEDED` | Quota exceeded |
| `APIConnectionError` | `CONNECTION_ERROR` | Network issue |
| `APITimeoutError` | `TIMEOUT` | Request timed out |
| `BadRequestError` | `INVALID_MODEL` | Invalid model name |
| `BadRequestError` | `CONTEXT_LENGTH_EXCEEDED` | Conversation too long |
| `BadRequestError` | `INVALID_SCHEMA` | Invalid function schema |
| `BadRequestError` | `CONTENT_POLICY` | Content policy violation |
| `BadRequestError` | `BAD_REQUEST` | Other bad request |
| `APIError` | `SERVER_OVERLOADED` | Servers overloaded |

### Error Handler

```python
from aios.providers.openai_client import handle_openai_error

try:
    response = client.send_message("Hello")
except Exception as e:
    error = handle_openai_error(e)
    print(f"Error [{error.error_code}]: {error.user_message}")
```

### Common Error: Strict Mode Schema Validation

**Error:**
```
'required' is required to be supplied and to be an array
including every key in properties. Missing 'requires_confirmation'.
```

**Cause:** Tool schema has properties not listed in `required`.

**Solution:** The converter automatically fixes this by adding all properties to `required` and making optional ones nullable.

---

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key (required for OpenAI provider) |
| `AIOS_PROVIDER` | Set to `openai` to use OpenAI as default |
| `AIOS_MODEL` | Override default model (e.g., `gpt-5.2-pro`) |

### Config File (`~/.config/aios/config.toml`)

```toml
[api]
provider = "openai"
model = "gpt-5.2"
max_tokens = 4096
openai_api_key = "sk-..."  # Or use environment variable

# OpenAI-specific settings
parallel_tool_calls = true  # Allow multiple tool calls in parallel
```

### Programmatic Configuration

```python
from aios.providers import create_client

# Create OpenAI client explicitly
client = create_client(provider="openai")

# Configure GPT-5.2 features
client.set_model("gpt-5.2-pro")
client.set_reasoning_effort("high")
client.set_verbosity("medium")
```

---

## Usage Examples

### Basic Text Generation

```python
from aios.providers import create_client

client = create_client(provider="openai")
response = client.send_message("What is the capital of France?")
print(response.text)
```

### With Streaming

```python
def on_text(chunk: str):
    print(chunk, end="", flush=True)

response = client.send_message(
    "Write a short poem about coding",
    on_text=on_text
)
```

### Tool Calling Flow

```python
# 1. Send message that triggers tool use
response = client.send_message("List files in the current directory")

# 2. Check for tool calls
if response.tool_calls:
    results = []
    for tool_call in response.tool_calls:
        # Execute tool
        output = execute_tool(tool_call["name"], tool_call["input"])
        results.append({
            "tool_use_id": tool_call["id"],
            "content": output
        })

    # 3. Send tool results back
    response = client.send_tool_results(results)

print(response.text)
```

### Complex Reasoning Task

```python
# Configure for maximum reasoning
client.set_reasoning_effort("xhigh")
client.set_verbosity("high")

response = client.send_message("""
Analyze this algorithm and suggest optimizations:

def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
""")
```

### Context Statistics

```python
stats = client.get_context_stats()
print(f"Provider: {stats['provider']}")
print(f"Model: {stats['model']}")
print(f"Is GPT-5.x: {stats['is_gpt5_model']}")
print(f"Reasoning Effort: {stats.get('reasoning_effort', 'N/A')}")
print(f"Verbosity: {stats.get('verbosity', 'N/A')}")
print(f"Messages: {stats['message_count']}")
print(f"Response Chain Active: {stats['has_response_chain']}")
```

---

## Comparison with Anthropic Implementation

| Feature | Anthropic (Claude) | OpenAI (GPT-5.2) |
|---------|-------------------|------------------|
| API | Messages API | Responses API |
| Context Management | Manual with summarization | Response chaining |
| Tool Format | Native | Converted from Anthropic |
| Reasoning Control | N/A | `reasoning.effort` parameter |
| Verbosity Control | N/A | `text.verbosity` parameter |
| Strict Mode | N/A | Enabled by default |
| Streaming | `stream.text_stream` | Event-based with deltas |

---

## Troubleshooting

### "Invalid schema for function" Error

**Problem:** Strict mode validation fails.

**Solution:** Ensure all properties are in `required` array. The converter handles this automatically, but if you define custom tools, follow strict mode requirements.

### "Authentication failed" Error

**Problem:** Invalid or missing API key.

**Solution:**
```bash
export OPENAI_API_KEY="sk-your-key-here"
```

### "Model not found" Error

**Problem:** Invalid model ID.

**Solution:** Check available models:
```python
from aios.models import get_models_by_provider
for m in get_models_by_provider("openai"):
    print(f"{m.id}: {m.name}")
```

### Slow Responses

**Problem:** High latency.

**Solution:**
1. Use `gpt-5-mini` or `gpt-5-nano` for simpler tasks
2. Set `reasoning.effort` to `none` or `low`
3. Set `verbosity` to `low`

---

## References

- [OpenAI Responses API Documentation](https://platform.openai.com/docs/api-reference/responses)
- [GPT-5.2 Model Guide](https://platform.openai.com/docs/guides/gpt-5)
- [Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)
- [Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
- [Migration from Chat Completions](https://platform.openai.com/docs/guides/migrate-to-responses)
