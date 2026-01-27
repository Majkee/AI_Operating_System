# AIOS Rate Limiting System

AIOS includes a comprehensive rate limiting system to manage API requests and prevent quota exhaustion.

## Overview

The rate limiting system provides:
- **Token Bucket**: Smooth rate limiting with burst support
- **Sliding Window Counter**: Fixed-window request counting
- **API Rate Limiter**: Combined limiter for Claude API calls
- **Decorator**: Easy function-level rate limiting

## Token Bucket Algorithm

A token bucket allows bursts while maintaining a long-term average rate.

### How It Works

1. Bucket holds tokens up to a maximum capacity
2. Tokens are consumed when making requests
3. Tokens refill at a steady rate over time
4. If no tokens available, request must wait

### Basic Usage

```python
from aios.ratelimit import TokenBucket

# 10 tokens per second, max 50 tokens
bucket = TokenBucket(rate=10, capacity=50)

# Try to acquire a token (non-blocking)
if bucket.acquire(blocking=False):
    make_api_call()
else:
    print("Rate limited, try again later")

# Blocking acquire (waits for token)
bucket.acquire(blocking=True)  # Waits if necessary
make_api_call()
```

### Acquire Multiple Tokens

```python
# Acquire 5 tokens for a batch operation
if bucket.acquire(tokens=5, blocking=False):
    process_batch()
```

### Check Available Tokens

```python
# Check without consuming
available = bucket.available
print(f"Tokens available: {available}")

# Calculate wait time for N tokens
wait = bucket.wait_time(tokens=10)
if wait > 0:
    print(f"Wait {wait:.2f}s for 10 tokens")
```

### Custom Initial Tokens

```python
# Start with fewer tokens (e.g., after restart)
bucket = TokenBucket(
    rate=10,
    capacity=50,
    initial_tokens=5  # Start with only 5 tokens
)
```

## Sliding Window Counter

Counts requests within a time window, useful for per-minute/per-hour limits.

### Basic Usage

```python
from aios.ratelimit import SlidingWindowCounter

# 100 requests per minute
counter = SlidingWindowCounter(limit=100, window_seconds=60)

# Check if request is allowed
if counter.is_allowed():
    counter.record()  # Record the request
    make_api_call()
else:
    print("Rate limit exceeded")

# Combined check and record
if counter.record():  # Returns True if allowed
    make_api_call()
```

### Check Remaining Requests

```python
# How many requests left?
remaining = counter.remaining
print(f"Requests remaining: {remaining}")

# Current count in window
current = counter.current_count
print(f"Requests made: {current}")
```

### Calculate Wait Time

```python
# How long until a request is available?
wait = counter.wait_time()
if wait > 0:
    print(f"Wait {wait:.2f}s before next request")
    time.sleep(wait)
```

## API Rate Limiter

The `APIRateLimiter` combines multiple strategies for comprehensive API rate limiting.

### Configuration

```python
from aios.ratelimit import RateLimitConfig, APIRateLimiter

config = RateLimitConfig(
    requests_per_minute=50,     # Max requests per minute
    requests_per_hour=500,      # Max requests per hour
    tokens_per_minute=100000,   # Max tokens per minute
    burst_size=10,              # Allow bursts up to 10
    enable_backoff=True         # Exponential backoff on limits
)

limiter = APIRateLimiter(config)
```

### Default Configuration

```python
# Uses sensible defaults
limiter = APIRateLimiter()
# Default: 50 req/min, 500 req/hour, 100k tokens/min
```

### Making Requests

```python
# Check current status
status = limiter.check()
print(f"Limited: {status.is_limited}")
print(f"Requests remaining: {status.requests_remaining}")
print(f"Tokens remaining: {status.tokens_remaining}")

# Acquire permission (blocking)
status = limiter.acquire(blocking=True)
if not status.is_limited:
    response = call_claude_api()

# Non-blocking acquire
status = limiter.acquire(blocking=False)
if status.is_limited:
    print(f"Wait {status.wait_time:.2f}s")
else:
    make_request()
```

### Recording Token Usage

```python
# After API call, record tokens used
response = call_claude_api()
limiter.record_tokens(response.usage.total_tokens)
```

### Statistics

```python
stats = limiter.stats
print(f"Total requests: {stats['total_requests']}")
print(f"Total tokens used: {stats['total_tokens_used']}")
print(f"Requests remaining (minute): {stats['requests_remaining_minute']}")
print(f"Requests remaining (hour): {stats['requests_remaining_hour']}")
```

## Rate Limited Decorator

Apply rate limiting to functions automatically.

### Basic Usage

```python
from aios.ratelimit import APIRateLimiter, rate_limited

limiter = APIRateLimiter()

@rate_limited(limiter)
def call_claude(prompt):
    return claude_api.send(prompt)

# Function automatically waits if rate limited
response = call_claude("Hello!")
```

### With Callback

```python
def on_rate_limited(status):
    print(f"Rate limited! Wait {status.wait_time:.2f}s")

@rate_limited(limiter, on_limited=on_rate_limited)
def make_api_call():
    return api.request()

# Callback is invoked when rate limited
make_api_call()
```

### Access Statistics

```python
@rate_limited(limiter)
def my_function():
    pass

# Get stats through decorated function
my_function()
stats = my_function.stats()
print(f"Requests made: {stats['total_requests']}")
```

## Rate Limit Status

The `RateLimitStatus` object provides detailed information.

```python
status = limiter.check()

# Check if currently limited
if status.is_limited:
    print(f"Wait time: {status.wait_time}s")
    print(f"Reason: {status.message}")
else:
    print(f"Requests remaining: {status.requests_remaining}")
    print(f"Tokens remaining: {status.tokens_remaining}")
```

### Status Fields

| Field | Type | Description |
|-------|------|-------------|
| `is_limited` | bool | True if rate limited |
| `wait_time` | float | Seconds to wait (0 if not limited) |
| `requests_remaining` | int | Requests left in current window |
| `tokens_remaining` | int | Tokens left in current window |
| `message` | str | Human-readable status message |

## Global Rate Limiter

AIOS provides a singleton rate limiter for convenience.

```python
from aios.ratelimit import get_rate_limiter, configure_rate_limiter

# Get the global limiter (creates with defaults if needed)
limiter = get_rate_limiter()

# Configure the global limiter
config = RateLimitConfig(requests_per_minute=30)
limiter = configure_rate_limiter(config)

# Both return the same instance
limiter1 = get_rate_limiter()
limiter2 = get_rate_limiter()
assert limiter1 is limiter2
```

## Integration Example

```python
from aios.ratelimit import (
    RateLimitConfig,
    APIRateLimiter,
    rate_limited
)

# Configure for Claude API limits
config = RateLimitConfig(
    requests_per_minute=50,
    requests_per_hour=500,
    tokens_per_minute=100000,
    burst_size=5,
    enable_backoff=True
)

limiter = APIRateLimiter(config)

@rate_limited(limiter, on_limited=lambda s: print(f"Waiting {s.wait_time:.1f}s..."))
def chat_with_claude(messages):
    response = claude.messages.create(
        model="claude-sonnet-4-5-20250929",
        messages=messages,
        max_tokens=1024
    )
    # Record actual token usage
    limiter.record_tokens(response.usage.input_tokens + response.usage.output_tokens)
    return response

# Usage
def main():
    while True:
        user_input = input("> ")

        # Check rate limit before proceeding
        status = limiter.check()
        if status.requests_remaining < 5:
            print(f"Warning: Only {status.requests_remaining} requests remaining this minute")

        response = chat_with_claude([{"role": "user", "content": user_input}])
        print(response.content[0].text)
```

## Best Practices

### 1. Choose Appropriate Limits

```python
# Conservative for free tier
config = RateLimitConfig(
    requests_per_minute=20,
    requests_per_hour=200
)

# Higher for paid tier
config = RateLimitConfig(
    requests_per_minute=100,
    requests_per_hour=2000
)
```

### 2. Handle Rate Limits Gracefully

```python
def make_request_with_retry(prompt, max_retries=3):
    for attempt in range(max_retries):
        status = limiter.acquire(blocking=False)

        if status.is_limited:
            if attempt < max_retries - 1:
                print(f"Rate limited, waiting {status.wait_time:.1f}s...")
                time.sleep(status.wait_time)
                continue
            else:
                raise Exception("Max retries exceeded")

        return call_api(prompt)
```

### 3. Monitor Usage

```python
def log_rate_limit_stats():
    stats = limiter.stats

    # Alert if approaching limits
    if stats["requests_remaining_minute"] < 10:
        logger.warning(f"Low on requests: {stats['requests_remaining_minute']} remaining")

    if stats["tokens_remaining_minute"] < 10000:
        logger.warning(f"Low on tokens: {stats['tokens_remaining_minute']} remaining")
```

### 4. Use Backoff for Bursts

```python
config = RateLimitConfig(
    requests_per_minute=50,
    burst_size=10,        # Allow initial burst
    enable_backoff=True   # Back off when limited
)
```

### 5. Separate Limiters for Different Operations

```python
# Different limits for different operation types
chat_limiter = APIRateLimiter(RateLimitConfig(
    requests_per_minute=50
))

embedding_limiter = APIRateLimiter(RateLimitConfig(
    requests_per_minute=100  # Embeddings are cheaper
))

@rate_limited(chat_limiter)
def chat(message):
    return claude.messages.create(...)

@rate_limited(embedding_limiter)
def embed(text):
    return claude.embeddings.create(...)
```

## Thread Safety

All rate limiting components are thread-safe:

```python
from aios.ratelimit import APIRateLimiter
from concurrent.futures import ThreadPoolExecutor

limiter = APIRateLimiter()

def worker(task_id):
    status = limiter.acquire(blocking=True)
    if not status.is_limited:
        return process_task(task_id)

# Safe to use from multiple threads
with ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(worker, range(100)))
```

## Performance Considerations

### Memory Usage

- Token bucket: O(1) memory
- Sliding window: O(n) where n = requests in window
- API limiter: Combines both, generally small footprint

### CPU Overhead

- Token operations: O(1)
- Window cleanup: O(n) but amortized over requests
- Thread locking: Minimal overhead with RLock

### When to Use Each Strategy

| Strategy | Best For |
|----------|----------|
| Token Bucket | Smooth rate limiting, burst handling |
| Sliding Window | Strict per-minute/hour limits |
| API Limiter | Combined approach for API calls |

## Troubleshooting

### Rate Limited Too Aggressively

1. Check your configuration matches API limits
2. Verify token counting is accurate
3. Consider increasing burst size

```python
# Debug current state
status = limiter.check()
print(f"State: {status}")
print(f"Stats: {limiter.stats}")
```

### Requests Failing Despite Available Quota

1. Check if multiple limiters are in use
2. Verify the limiter instance is shared correctly
3. Check for threading issues

### High Latency

1. Use non-blocking acquire with custom wait logic
2. Consider larger burst sizes for batch operations
3. Implement request queuing for smoother throughput

```python
# Custom wait with progress indication
while True:
    status = limiter.acquire(blocking=False)
    if not status.is_limited:
        break
    print(f"Waiting... {status.wait_time:.1f}s remaining")
    time.sleep(min(1, status.wait_time))
```
