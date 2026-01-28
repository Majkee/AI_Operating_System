"""
Caching system for AIOS.

Provides:
- LRU cache for expensive operations
- TTL-based cache for system info
- Tool result caching
"""

import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Callable, Set, TypeVar, Generic
from dataclasses import dataclass, field
from collections import OrderedDict
from functools import wraps
from threading import Lock


T = TypeVar('T')


@dataclass
class CacheEntry(Generic[T]):
    """A single cache entry with metadata."""
    value: T
    created_at: float
    expires_at: Optional[float] = None
    hits: int = 0

    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def touch(self) -> None:
        """Record a cache hit."""
        self.hits += 1


class LRUCache(Generic[T]):
    """
    Least Recently Used (LRU) cache with optional TTL.

    Thread-safe implementation suitable for caching expensive operations.
    """

    def __init__(self, max_size: int = 100, default_ttl: Optional[float] = None):
        """
        Initialize the cache.

        Args:
            max_size: Maximum number of entries to store
            default_ttl: Default time-to-live in seconds (None = no expiry)
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._lock = Lock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0
        }

    def get(self, key: str) -> Optional[T]:
        """
        Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                self._stats["misses"] += 1
                return None

            entry = self._cache[key]

            # Check expiration
            if entry.is_expired:
                del self._cache[key]
                self._stats["misses"] += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.touch()
            self._stats["hits"] += 1

            return entry.value

    def set(self, key: str, value: T, ttl: Optional[float] = None) -> None:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None = use default)
        """
        with self._lock:
            # Calculate expiration
            actual_ttl = ttl if ttl is not None else self.default_ttl
            expires_at = time.time() + actual_ttl if actual_ttl else None

            # Create entry
            entry = CacheEntry(
                value=value,
                created_at=time.time(),
                expires_at=expires_at
            )

            # Update or add
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = entry

            # Evict if necessary
            while len(self._cache) > self.max_size:
                self._cache.popitem(last=False)
                self._stats["evictions"] += 1

    def delete(self, key: str) -> bool:
        """
        Delete a key from the cache.

        Returns:
            True if key was deleted, False if not found
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.

        Returns:
            Number of entries removed
        """
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)

    @property
    def stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total if total > 0 else 0
            return {
                **self._stats,
                "size": len(self._cache),
                "max_size": self.max_size,
                "hit_rate": hit_rate
            }

    def __contains__(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return self.get(key) is not None

    def __len__(self) -> int:
        """Get number of entries (including expired)."""
        return len(self._cache)


def cached(
    cache: LRUCache,
    key_func: Optional[Callable[..., str]] = None,
    ttl: Optional[float] = None
):
    """
    Decorator for caching function results.

    Args:
        cache: LRUCache instance to use
        key_func: Function to generate cache key from args (default: hash of args)
        ttl: Time-to-live for cached results

    Example:
        cache = LRUCache(max_size=100, default_ttl=300)

        @cached(cache)
        def expensive_operation(param):
            return compute_something(param)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = _generate_key(func.__name__, args, kwargs)

            # Check cache
            result = cache.get(key)
            if result is not None:
                return result

            # Call function and cache result
            result = func(*args, **kwargs)
            cache.set(key, result, ttl)
            return result

        # Add cache control methods
        wrapper.cache = cache
        wrapper.cache_clear = cache.clear
        wrapper.cache_stats = lambda: cache.stats

        return wrapper
    return decorator


def _generate_key(func_name: str, args: tuple, kwargs: dict) -> str:
    """Generate a cache key from function arguments."""
    key_data = {
        "func": func_name,
        "args": _serialize_args(args),
        "kwargs": _serialize_args(kwargs)
    }
    key_str = json.dumps(key_data, sort_keys=True, default=str)
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


def _serialize_args(obj: Any) -> Any:
    """Serialize arguments for key generation."""
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    elif isinstance(obj, (list, tuple)):
        return [_serialize_args(item) for item in obj]
    elif isinstance(obj, dict):
        return {str(k): _serialize_args(v) for k, v in obj.items()}
    else:
        return str(obj)


class SystemInfoCache:
    """
    Specialized cache for system information.

    Different types of system info have different staleness tolerances.
    """

    # TTL in seconds for different info types
    TTL_CONFIG = {
        "disk": 30,           # Disk info changes slowly
        "memory": 5,          # Memory changes frequently
        "cpu": 2,             # CPU usage is very dynamic
        "processes": 5,       # Process list changes often
        "network": 10,        # Network info moderate
        "general": 15,        # General system info
    }

    def __init__(self):
        """Initialize system info caches."""
        self._caches = {
            info_type: LRUCache(max_size=10, default_ttl=ttl)
            for info_type, ttl in self.TTL_CONFIG.items()
        }

    def get(self, info_type: str, key: str = "default") -> Optional[Any]:
        """Get cached system info."""
        cache = self._caches.get(info_type)
        if cache:
            return cache.get(key)
        return None

    def set(self, info_type: str, value: Any, key: str = "default") -> None:
        """Set cached system info."""
        cache = self._caches.get(info_type)
        if cache:
            cache.set(key, value)

    def invalidate(self, info_type: Optional[str] = None) -> None:
        """
        Invalidate cache entries.

        Args:
            info_type: Specific type to invalidate, or None for all
        """
        if info_type:
            cache = self._caches.get(info_type)
            if cache:
                cache.clear()
        else:
            for cache in self._caches.values():
                cache.clear()

    def get_or_compute(
        self,
        info_type: str,
        compute_func: Callable[[], T],
        key: str = "default"
    ) -> T:
        """
        Get from cache or compute if missing.

        Args:
            info_type: Type of system info
            compute_func: Function to compute value if not cached
            key: Cache key

        Returns:
            Cached or freshly computed value
        """
        cached = self.get(info_type, key)
        if cached is not None:
            return cached

        value = compute_func()
        self.set(info_type, value, key)
        return value

    @property
    def stats(self) -> dict:
        """Get stats for all caches."""
        return {
            info_type: cache.stats
            for info_type, cache in self._caches.items()
        }


@dataclass
class ToolCacheConfig:
    """Configuration for caching a specific tool's results."""
    cacheable: bool = False
    ttl: float = 60.0
    key_params: Optional[List[str]] = None  # None = all params minus "explanation"


class ToolResultCache:
    """
    Cache for tool execution results.

    Instead of caching Claude's prose responses (which are fragile and
    pattern-dependent), this caches the raw ToolResult from tool handlers.
    Claude still generates a fresh response each time, but the expensive
    tool execution (subprocess calls, psutil, file I/O) is avoided on
    cache hits.
    """

    _EXCLUDED_PARAMS = {"explanation"}

    def __init__(self, max_size: int = 200, default_ttl: float = 60.0):
        self._cache: LRUCache = LRUCache(max_size=max_size, default_ttl=default_ttl)
        self._tool_configs: Dict[str, ToolCacheConfig] = {}
        self._invalidation_rules: Dict[str, List[dict]] = {}
        self._tool_key_index: Dict[str, Set[str]] = {}
        self._index_lock = Lock()

    def configure_tool(self, tool_name: str, config: ToolCacheConfig) -> None:
        """Register caching configuration for a tool."""
        self._tool_configs[tool_name] = config

    def add_invalidation_rule(
        self,
        trigger_tool: str,
        target_tool: str,
        key_transform: Optional[Callable] = None,
    ) -> None:
        """Add a rule: when *trigger_tool* executes, invalidate *target_tool* entries.

        Args:
            trigger_tool: The tool whose execution triggers invalidation.
            target_tool: The tool whose cached results should be invalidated.
            key_transform: Optional callable(tool_input) -> specific cache key
                           to invalidate.  If None, all entries for *target_tool*
                           are wiped.
        """
        self._invalidation_rules.setdefault(trigger_tool, []).append({
            "target_tool": target_tool,
            "key_transform": key_transform,
        })

    def make_cache_key(self, tool_name: str, tool_input: dict) -> str:
        """Build a deterministic cache key for a tool invocation."""
        config = self._tool_configs.get(tool_name)

        if config and config.key_params is not None:
            filtered = {k: tool_input.get(k) for k in config.key_params}
        else:
            filtered = {
                k: v for k, v in tool_input.items()
                if k not in self._EXCLUDED_PARAMS
            }

        return _generate_key(tool_name, (), filtered)

    # ------------------------------------------------------------------
    # Core get / set
    # ------------------------------------------------------------------

    def get(self, tool_name: str, tool_input: dict) -> Any:
        """Return cached ToolResult or None."""
        config = self._tool_configs.get(tool_name)
        if not config or not config.cacheable:
            return None

        key = self.make_cache_key(tool_name, tool_input)
        return self._cache.get(key)

    def set(self, tool_name: str, tool_input: dict, result: Any) -> None:
        """Cache a successful ToolResult.  Failed results are never cached."""
        config = self._tool_configs.get(tool_name)
        if not config or not config.cacheable:
            return

        # Never cache failures
        if not getattr(result, "success", True):
            return

        key = self.make_cache_key(tool_name, tool_input)
        self._cache.set(key, result, ttl=config.ttl)

        with self._index_lock:
            self._tool_key_index.setdefault(tool_name, set()).add(key)

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def process_invalidations(self, trigger_tool: str, tool_input: dict) -> None:
        """Run all invalidation rules triggered by *trigger_tool*."""
        rules = self._invalidation_rules.get(trigger_tool)
        if not rules:
            return

        for rule in rules:
            target = rule["target_tool"]
            key_transform = rule["key_transform"]

            if key_transform is not None:
                specific_key = key_transform(tool_input)
                if specific_key is not None:
                    self._cache.delete(specific_key)
                    with self._index_lock:
                        keys = self._tool_key_index.get(target)
                        if keys:
                            keys.discard(specific_key)
            else:
                self._invalidate_by_tool(target)

    def _invalidate_by_tool(self, tool_name: str) -> int:
        """Remove all cached entries for *tool_name*."""
        with self._index_lock:
            keys = self._tool_key_index.pop(tool_name, set())

        count = 0
        for key in keys:
            if self._cache.delete(key):
                count += 1
        return count

    def clear(self) -> None:
        """Remove all entries."""
        self._cache.clear()
        with self._index_lock:
            self._tool_key_index.clear()

    @property
    def stats(self) -> dict:
        """Cache statistics."""
        return self._cache.stats


# Global cache instances
_system_info_cache: Optional[SystemInfoCache] = None
_tool_result_cache: Optional['ToolResultCache'] = None


def get_system_info_cache() -> SystemInfoCache:
    """Get the global system info cache instance."""
    global _system_info_cache
    if _system_info_cache is None:
        _system_info_cache = SystemInfoCache()
    return _system_info_cache


def get_tool_result_cache() -> ToolResultCache:
    """Get the global tool result cache instance."""
    global _tool_result_cache
    if _tool_result_cache is None:
        _tool_result_cache = ToolResultCache()
    return _tool_result_cache
