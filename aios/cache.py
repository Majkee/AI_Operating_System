"""
Caching system for AIOS.

Provides:
- LRU cache for expensive operations
- TTL-based cache for system info
- Query result caching
"""

import hashlib
import json
import time
from typing import Any, Optional, Callable, TypeVar, Generic
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


class QueryCache:
    """
    Cache for Claude API query results.

    Useful for repeated questions about the same topic.
    Note: Only caches pure informational queries, not actions.
    """

    def __init__(self, max_size: int = 50, ttl: float = 600):
        """
        Initialize query cache.

        Args:
            max_size: Maximum number of queries to cache
            ttl: Time-to-live in seconds (default: 10 minutes)
        """
        self._cache = LRUCache(max_size=max_size, default_ttl=ttl)
        self._cacheable_patterns = [
            "what is",
            "how do i",
            "explain",
            "show me",
            "list",
            "where is",
            "help me understand",
        ]

    def is_cacheable(self, query: str) -> bool:
        """
        Determine if a query result should be cached.

        Only informational queries should be cached, not action queries.
        """
        query_lower = query.lower().strip()

        # Don't cache short queries
        if len(query_lower) < 10:
            return False

        # Don't cache action-oriented queries
        action_words = ["delete", "remove", "install", "create", "write", "modify", "change"]
        if any(word in query_lower for word in action_words):
            return False

        # Cache queries that look informational
        return any(pattern in query_lower for pattern in self._cacheable_patterns)

    def get_key(self, query: str, context_hash: Optional[str] = None) -> str:
        """Generate cache key for a query."""
        normalized = query.lower().strip()
        key_parts = [normalized]
        if context_hash:
            key_parts.append(context_hash)
        return _generate_key("query", tuple(key_parts), {})

    def get(self, query: str, context_hash: Optional[str] = None) -> Optional[str]:
        """Get cached response for a query."""
        if not self.is_cacheable(query):
            return None
        key = self.get_key(query, context_hash)
        return self._cache.get(key)

    def set(self, query: str, response: str, context_hash: Optional[str] = None) -> None:
        """Cache a query response."""
        if not self.is_cacheable(query):
            return
        key = self.get_key(query, context_hash)
        self._cache.set(key, response)

    def clear(self) -> None:
        """Clear the query cache."""
        self._cache.clear()

    @property
    def stats(self) -> dict:
        """Get cache statistics."""
        return self._cache.stats


# Global cache instances
_system_info_cache: Optional[SystemInfoCache] = None
_query_cache: Optional[QueryCache] = None


def get_system_info_cache() -> SystemInfoCache:
    """Get the global system info cache instance."""
    global _system_info_cache
    if _system_info_cache is None:
        _system_info_cache = SystemInfoCache()
    return _system_info_cache


def get_query_cache() -> QueryCache:
    """Get the global query cache instance."""
    global _query_cache
    if _query_cache is None:
        _query_cache = QueryCache()
    return _query_cache
