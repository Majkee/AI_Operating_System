"""Tests for caching system."""

import time
from unittest.mock import MagicMock

import pytest

from aios.cache import (
    CacheEntry,
    LRUCache,
    cached,
    SystemInfoCache,
    QueryCache,
    get_system_info_cache,
    get_query_cache,
)


class TestCacheEntry:
    """Test CacheEntry dataclass."""

    def test_entry_creation(self):
        """Test creating a cache entry."""
        entry = CacheEntry(value="test", created_at=time.time())
        assert entry.value == "test"
        assert entry.hits == 0
        assert entry.is_expired is False

    def test_entry_expiration(self):
        """Test entry expiration."""
        entry = CacheEntry(
            value="test",
            created_at=time.time(),
            expires_at=time.time() - 1  # Already expired
        )
        assert entry.is_expired is True

    def test_entry_not_expired(self):
        """Test entry not expired."""
        entry = CacheEntry(
            value="test",
            created_at=time.time(),
            expires_at=time.time() + 100
        )
        assert entry.is_expired is False

    def test_entry_touch(self):
        """Test recording cache hit."""
        entry = CacheEntry(value="test", created_at=time.time())
        entry.touch()
        entry.touch()
        assert entry.hits == 2


class TestLRUCache:
    """Test LRUCache class."""

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = LRUCache(max_size=10)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent(self):
        """Test getting non-existent key."""
        cache = LRUCache(max_size=10)
        assert cache.get("nonexistent") is None

    def test_max_size_eviction(self):
        """Test that oldest entries are evicted when max size reached."""
        cache = LRUCache(max_size=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")  # Should evict key1

        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key4") == "value4"

    def test_lru_order(self):
        """Test that accessing an entry moves it to end."""
        cache = LRUCache(max_size=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Access key1, making it most recently used
        cache.get("key1")

        # Add new entry, should evict key2 (least recently used)
        cache.set("key4", "value4")

        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_ttl_expiration(self):
        """Test TTL-based expiration."""
        cache = LRUCache(max_size=10, default_ttl=0.1)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        time.sleep(0.15)
        assert cache.get("key1") is None

    def test_custom_ttl(self):
        """Test custom TTL per entry."""
        cache = LRUCache(max_size=10, default_ttl=10)
        cache.set("key1", "value1", ttl=0.1)

        time.sleep(0.15)
        assert cache.get("key1") is None

    def test_delete(self):
        """Test deleting an entry."""
        cache = LRUCache(max_size=10)
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None
        assert cache.delete("key1") is False

    def test_clear(self):
        """Test clearing the cache."""
        cache = LRUCache(max_size=10)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert len(cache) == 0

    def test_cleanup_expired(self):
        """Test cleaning up expired entries."""
        cache = LRUCache(max_size=10)
        cache.set("key1", "value1", ttl=0.1)
        cache.set("key2", "value2", ttl=10)

        time.sleep(0.15)
        removed = cache.cleanup_expired()

        assert removed == 1
        assert cache.get("key2") == "value2"

    def test_stats(self):
        """Test cache statistics."""
        cache = LRUCache(max_size=10)
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.stats
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_contains(self):
        """Test __contains__ method."""
        cache = LRUCache(max_size=10)
        cache.set("key1", "value1")
        assert "key1" in cache
        assert "key2" not in cache


class TestCachedDecorator:
    """Test cached decorator."""

    def test_caches_result(self):
        """Test that decorator caches function results."""
        cache = LRUCache(max_size=10)
        call_count = [0]

        @cached(cache)
        def expensive_func(x):
            call_count[0] += 1
            return x * 2

        assert expensive_func(5) == 10
        assert expensive_func(5) == 10
        assert call_count[0] == 1  # Only called once

    def test_different_args(self):
        """Test that different args get different cache entries."""
        cache = LRUCache(max_size=10)

        @cached(cache)
        def func(x):
            return x * 2

        assert func(5) == 10
        assert func(10) == 20
        assert cache.stats["size"] == 2

    def test_custom_key_func(self):
        """Test custom key function."""
        cache = LRUCache(max_size=10)

        @cached(cache, key_func=lambda x: f"custom_{x}")
        def func(x):
            return x * 2

        func(5)
        assert cache.get("custom_5") == 10


class TestSystemInfoCache:
    """Test SystemInfoCache class."""

    def test_ttl_config_exists(self):
        """Test that TTL config is defined."""
        cache = SystemInfoCache()
        assert "disk" in cache.TTL_CONFIG
        assert "memory" in cache.TTL_CONFIG
        assert "cpu" in cache.TTL_CONFIG

    def test_different_ttls(self):
        """Test different info types have different TTLs."""
        cache = SystemInfoCache()
        # CPU has short TTL (2s), disk has longer TTL (30s)
        assert cache.TTL_CONFIG["cpu"] < cache.TTL_CONFIG["disk"]

    def test_invalidate_clears_cache(self):
        """Test that invalidate clears the cache."""
        cache = SystemInfoCache()
        # Set and immediately invalidate
        cache.set("disk", "disk_data")
        cache.invalidate("disk")
        # After invalidation, should be None
        assert cache.get("disk") is None

    def test_invalidate_all(self):
        """Test invalidating all caches."""
        cache = SystemInfoCache()
        cache.set("disk", "disk_data")
        cache.invalidate()
        assert cache.get("disk") is None

    def test_get_or_compute_calls_function(self):
        """Test get_or_compute calls the compute function."""
        cache = SystemInfoCache()

        def compute():
            return "computed_value"

        # Should call compute
        result = cache.get_or_compute("disk", compute)
        assert result == "computed_value"

    def test_stats_available(self):
        """Test that stats are available."""
        cache = SystemInfoCache()
        stats = cache.stats
        assert "disk" in stats
        assert "memory" in stats


class TestQueryCache:
    """Test QueryCache class."""

    def test_cacheable_queries(self):
        """Test identifying cacheable queries."""
        cache = QueryCache()

        assert cache.is_cacheable("what is the current date") is True
        assert cache.is_cacheable("how do i list files") is True
        assert cache.is_cacheable("explain what grep does") is True

    def test_non_cacheable_queries(self):
        """Test identifying non-cacheable queries."""
        cache = QueryCache()

        assert cache.is_cacheable("delete that file") is False
        assert cache.is_cacheable("install vim") is False
        assert cache.is_cacheable("hi") is False  # Too short

    def test_cache_and_retrieve(self):
        """Test caching and retrieving queries."""
        cache = QueryCache()

        query = "what is the current date"
        response = "Today is January 26, 2026"

        cache.set(query, response)
        assert cache.get(query) == response

    def test_non_cacheable_not_stored(self):
        """Test that non-cacheable queries are not stored."""
        cache = QueryCache()

        query = "delete the file"
        cache.set(query, "response")
        assert cache.get(query) is None


class TestGlobalCaches:
    """Test global cache instances."""

    def test_get_system_info_cache(self):
        """Test getting global system info cache."""
        cache1 = get_system_info_cache()
        cache2 = get_system_info_cache()
        assert cache1 is cache2

    def test_get_query_cache(self):
        """Test getting global query cache."""
        cache1 = get_query_cache()
        cache2 = get_query_cache()
        assert cache1 is cache2
