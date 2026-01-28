# AIOS Caching System

AIOS includes a flexible caching system to improve performance and reduce redundant operations.

## Overview

The caching system provides:
- **LRU Cache**: General-purpose cache with size limits and TTL
- **System Info Cache**: Specialized cache for system metrics
- **Tool Result Cache**: Transparent caching of tool execution results

## LRU Cache

A thread-safe Least Recently Used cache that automatically evicts old entries.

### Basic Usage

```python
from aios.cache import LRUCache

# Create cache: max 100 items, 5-minute TTL
cache = LRUCache(max_size=100, default_ttl=300)

# Store and retrieve
cache.set("user_prefs", {"theme": "dark"})
prefs = cache.get("user_prefs")  # Returns {"theme": "dark"}

# Returns None if not found or expired
result = cache.get("nonexistent")  # None
```

### Custom TTL Per Entry

```python
# Override default TTL for specific entries
cache.set("temporary", "value", ttl=60)    # Expires in 1 minute
cache.set("permanent", "value", ttl=None)  # Never expires (until evicted)
```

### Cache Operations

```python
# Check if key exists (and not expired)
if "key" in cache:
    print("Found!")

# Delete specific key
cache.delete("key")

# Clear entire cache
cache.clear()

# Remove only expired entries
removed_count = cache.cleanup_expired()

# Get cache statistics
stats = cache.stats
print(f"Hit rate: {stats['hit_rate']:.2%}")
print(f"Size: {stats['size']}/{stats['max_size']}")
```

### Statistics

The cache tracks performance metrics:

```python
stats = cache.stats
# {
#     "hits": 150,        # Successful retrievals
#     "misses": 23,       # Key not found or expired
#     "evictions": 5,     # Removed due to size limit
#     "size": 87,         # Current entry count
#     "max_size": 100,    # Maximum entries
#     "hit_rate": 0.867   # hits / (hits + misses)
# }
```

## Cached Decorator

Automatically cache function results:

```python
from aios.cache import LRUCache, cached

cache = LRUCache(max_size=100, default_ttl=300)

@cached(cache)
def expensive_computation(x, y):
    # This only runs once per unique (x, y)
    return complex_calculation(x, y)

# First call: computes and caches
result1 = expensive_computation(10, 20)

# Second call: returns cached result
result2 = expensive_computation(10, 20)

# Different args: computes again
result3 = expensive_computation(30, 40)
```

### Custom Cache Keys

```python
@cached(cache, key_func=lambda user_id: f"user_{user_id}")
def get_user_data(user_id):
    return fetch_from_database(user_id)
```

### Decorator Utilities

```python
@cached(cache)
def my_function():
    pass

# Access cache through decorated function
my_function.cache_clear()     # Clear all cached results
stats = my_function.cache_stats()  # Get statistics
```

## System Info Cache

Specialized cache for system information with type-specific TTLs.

### TTL Configuration

Different system metrics change at different rates:

| Info Type | TTL | Rationale |
|-----------|-----|-----------|
| `disk` | 30s | Disk usage changes slowly |
| `general` | 15s | General system info |
| `network` | 10s | Network state moderate |
| `memory` | 5s | Memory changes frequently |
| `processes` | 5s | Process list dynamic |
| `cpu` | 2s | CPU usage very volatile |

### Usage

```python
from aios.cache import get_system_info_cache

cache = get_system_info_cache()

# Simple get/set
cache.set("disk", {"free_gb": 125, "total_gb": 500})
disk_info = cache.get("disk")

# Get or compute (preferred pattern)
def fetch_disk_info():
    # Expensive system call
    return get_disk_usage()

disk_info = cache.get_or_compute("disk", fetch_disk_info)
# Returns cached value if available, otherwise calls function
```

### Invalidation

```python
# Invalidate specific type
cache.invalidate("disk")

# Invalidate all cached system info
cache.invalidate()
```

### Statistics

```python
stats = cache.stats
# {
#     "disk": {"hits": 45, "misses": 3, ...},
#     "memory": {"hits": 120, "misses": 15, ...},
#     "cpu": {"hits": 200, "misses": 50, ...},
#     ...
# }
```

## Tool Result Cache

Caches the raw `ToolResult` from tool handlers so that expensive operations
(subprocess calls, psutil, file I/O) are skipped on cache hits. Claude still
generates a fresh prose response every time — only the tool execution is cached.

### How It Works

1. When `ToolHandler.execute()` is called, it checks the cache first.
2. On a **hit**, the cached `ToolResult` is returned instantly — no handler runs.
3. On a **miss**, the handler runs normally. If it succeeds, the result is stored.
4. After every execution, **invalidation rules** are checked — a `write_file`
   call can automatically evict stale `read_file` entries, for example.

### Per-Tool Configuration

| Tool | TTL | key_params | Notes |
|------|-----|------------|-------|
| `get_system_info` | 30 s | `["info_type"]` | Disk/memory/cpu/etc. |
| `read_file` | 300 s | `["path"]` | Invalidated by `write_file` |
| `list_directory` | 60 s | `["path", "show_hidden"]` | Invalidated by `write_file` |
| `search_files` | 60 s | `["query", "location", "search_type"]` | Invalidated by `write_file` |

The `explanation` parameter is always excluded from the cache key so that
rephrased requests hit the same entry.

### Invalidation Rules

| Trigger Tool | Target Tool | Scope |
|-------------|-------------|-------|
| `write_file` | `read_file` | Specific key (same path) |
| `write_file` | `list_directory` | Wipe all entries |
| `write_file` | `search_files` | Wipe all entries |
| `manage_application` | `get_system_info` | Wipe all entries |
| `run_command` | All 4 cacheable tools | Wipe all (commands can do anything) |

### Usage

```python
from aios.cache import get_tool_result_cache, ToolCacheConfig

cache = get_tool_result_cache()

# Configure a tool for caching
cache.configure_tool("my_tool", ToolCacheConfig(
    cacheable=True,
    ttl=60.0,
    key_params=["param1", "param2"],  # None = all params minus "explanation"
))

# Add invalidation rules
cache.add_invalidation_rule("mutating_tool", "my_tool")  # wipe all on trigger
```

### Stats Output (via `stats` command)

```
Tool Result Cache:
  Hit rate: 67% (4 hits, 2 misses)
  Entries: 3/200
  Evictions: 0
```

## Global Cache Instances

AIOS provides singleton instances for convenience:

```python
from aios.cache import get_system_info_cache, get_tool_result_cache

# These return the same instance across your application
sys_cache = get_system_info_cache()
tool_cache = get_tool_result_cache()
```

## Cache Entry Details

Each cache entry tracks metadata:

```python
from aios.cache import CacheEntry

entry = CacheEntry(
    value="data",
    created_at=time.time(),
    expires_at=time.time() + 300,  # Optional
    hits=0
)

# Check expiration
if entry.is_expired:
    print("Entry has expired")

# Record access
entry.touch()  # Increments hits counter
```

## Thread Safety

All cache implementations are thread-safe:

```python
from aios.cache import LRUCache
from concurrent.futures import ThreadPoolExecutor

cache = LRUCache(max_size=100)

def worker(i):
    cache.set(f"key_{i}", f"value_{i}")
    return cache.get(f"key_{i}")

# Safe to use from multiple threads
with ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(worker, range(100)))
```

## Best Practices

### 1. Choose Appropriate TTLs

```python
# Static data: longer TTL
config_cache = LRUCache(max_size=50, default_ttl=3600)  # 1 hour

# Dynamic data: shorter TTL
status_cache = LRUCache(max_size=100, default_ttl=30)   # 30 seconds
```

### 2. Use get_or_compute Pattern

```python
# Instead of this:
value = cache.get("key")
if value is None:
    value = expensive_operation()
    cache.set("key", value)

# Do this:
value = cache.get_or_compute("key", expensive_operation)
```

### 3. Monitor Hit Rates

```python
stats = cache.stats
if stats["hit_rate"] < 0.5:
    print("Consider increasing TTL or cache size")
```

### 4. Invalidate on Updates

```python
def update_user_settings(user_id, settings):
    save_to_database(user_id, settings)
    cache.delete(f"user_{user_id}")  # Invalidate cached data
```

### 5. Size Cache Appropriately

```python
# Estimate: average_entry_size * max_size = memory usage
# 1KB entries * 1000 max = ~1MB memory
cache = LRUCache(max_size=1000)
```

## Performance Considerations

### Memory Usage

- Each entry has overhead (~100 bytes) plus value size
- Use `max_size` to limit memory consumption
- Call `cleanup_expired()` periodically for long-running processes

### CPU Overhead

- Get/set operations are O(1) average
- Cleanup is O(n) but only touches expired entries
- Thread locking adds minimal overhead

### When NOT to Cache

- Large binary data (images, files)
- Highly personalized data
- Security-sensitive information
- Data that must always be fresh

## Integration Example

```python
from aios.cache import LRUCache, cached, get_system_info_cache, get_tool_result_cache

# Application-level cache
app_cache = LRUCache(max_size=200, default_ttl=300)

# Cache expensive API calls
@cached(app_cache, ttl=60)
def get_weather(city):
    return weather_api.fetch(city)

# Use system cache for metrics
sys_cache = get_system_info_cache()

def get_dashboard_data():
    return {
        "weather": get_weather("New York"),
        "disk": sys_cache.get_or_compute("disk", fetch_disk_info),
        "memory": sys_cache.get_or_compute("memory", fetch_memory_info),
    }

# Tool result cache is wired up automatically by AIOSShell.__init__
# and attached to ToolHandler via set_cache().  Stats are visible via
# the 'stats' command in the AIOS shell.
```
