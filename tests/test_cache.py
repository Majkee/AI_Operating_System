"""Tests for caching system."""

import time
from unittest.mock import MagicMock

import pytest

from aios.cache import (
    CacheEntry,
    LRUCache,
    cached,
    SystemInfoCache,
    ToolResultCache,
    ToolCacheConfig,
    get_system_info_cache,
    get_tool_result_cache,
    _generate_key,
)
from aios.claude.tools import ToolResult


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


class TestToolResultCache:
    """Test ToolResultCache class."""

    def _make_result(self, output="ok", success=True):
        return ToolResult(success=success, output=output)

    def test_unconfigured_tool_not_cached(self):
        """Unconfigured tools are never cached."""
        cache = ToolResultCache()
        result = self._make_result()

        cache.set("unknown_tool", {"arg": "val"}, result)
        assert cache.get("unknown_tool", {"arg": "val"}) is None

    def test_cacheable_tool_stores_and_retrieves(self):
        """A configured cacheable tool's result is stored and returned."""
        cache = ToolResultCache()
        cache.configure_tool("get_system_info", ToolCacheConfig(
            cacheable=True, ttl=60.0, key_params=["info_type"],
        ))

        result = self._make_result("disk data")
        cache.set("get_system_info", {"info_type": "disk", "explanation": "x"}, result)

        cached = cache.get("get_system_info", {"info_type": "disk", "explanation": "y"})
        assert cached is not None
        assert cached.output == "disk data"

    def test_failed_results_never_cached(self):
        """Results with success=False are not stored."""
        cache = ToolResultCache()
        cache.configure_tool("read_file", ToolCacheConfig(cacheable=True, ttl=300.0))

        fail = self._make_result("err", success=False)
        cache.set("read_file", {"path": "/tmp/x"}, fail)
        assert cache.get("read_file", {"path": "/tmp/x"}) is None

    def test_ttl_expiration(self):
        """Entries expire after TTL."""
        cache = ToolResultCache()
        cache.configure_tool("fast", ToolCacheConfig(cacheable=True, ttl=0.1))

        result = self._make_result()
        cache.set("fast", {"a": 1}, result)
        assert cache.get("fast", {"a": 1}) is not None

        time.sleep(0.15)
        assert cache.get("fast", {"a": 1}) is None

    def test_explanation_excluded_from_key(self):
        """The 'explanation' param should not affect the cache key."""
        cache = ToolResultCache()
        cache.configure_tool("list_directory", ToolCacheConfig(cacheable=True, ttl=60.0))

        result = self._make_result("listing")
        cache.set("list_directory", {"path": "/home", "explanation": "first"}, result)

        cached = cache.get("list_directory", {"path": "/home", "explanation": "different"})
        assert cached is not None
        assert cached.output == "listing"

    def test_specific_key_invalidation(self):
        """write_file -> read_file invalidation for same path only."""
        cache = ToolResultCache()
        cache.configure_tool("read_file", ToolCacheConfig(
            cacheable=True, ttl=300.0, key_params=["path"],
        ))

        # Cache two read_file entries
        r1 = self._make_result("content a")
        r2 = self._make_result("content b")
        cache.set("read_file", {"path": "/a.txt"}, r1)
        cache.set("read_file", {"path": "/b.txt"}, r2)

        # Add specific-key invalidation rule
        cache.add_invalidation_rule(
            "write_file", "read_file",
            key_transform=lambda inp: _generate_key(
                "read_file", (), {"path": inp.get("path")},
            ),
        )

        # Trigger invalidation for /a.txt only
        cache.process_invalidations("write_file", {"path": "/a.txt", "content": "new"})

        assert cache.get("read_file", {"path": "/a.txt"}) is None
        assert cache.get("read_file", {"path": "/b.txt"}) is not None

    def test_wipe_all_invalidation(self):
        """write_file -> search_files wipes all search_files entries."""
        cache = ToolResultCache()
        cache.configure_tool("search_files", ToolCacheConfig(
            cacheable=True, ttl=60.0, key_params=["query", "location", "search_type"],
        ))

        cache.set("search_files", {"query": "*.py", "location": "/", "search_type": "filename"},
                   self._make_result("found"))
        cache.set("search_files", {"query": "*.txt", "location": "/", "search_type": "filename"},
                   self._make_result("found2"))

        cache.add_invalidation_rule("write_file", "search_files")
        cache.process_invalidations("write_file", {"path": "/x.py", "content": ""})

        assert cache.get("search_files", {"query": "*.py", "location": "/", "search_type": "filename"}) is None
        assert cache.get("search_files", {"query": "*.txt", "location": "/", "search_type": "filename"}) is None

    def test_stats_tracking(self):
        """Stats track hits and misses."""
        cache = ToolResultCache()
        cache.configure_tool("t", ToolCacheConfig(cacheable=True, ttl=60.0))

        cache.set("t", {"k": 1}, self._make_result())
        cache.get("t", {"k": 1})  # hit
        cache.get("t", {"k": 2})  # miss

        stats = cache.stats
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1

    def test_clear_removes_all(self):
        """clear() empties the cache completely."""
        cache = ToolResultCache()
        cache.configure_tool("t", ToolCacheConfig(cacheable=True, ttl=60.0))

        cache.set("t", {"k": 1}, self._make_result())
        cache.set("t", {"k": 2}, self._make_result())
        cache.clear()

        assert cache.get("t", {"k": 1}) is None
        assert cache.get("t", {"k": 2}) is None
        assert cache.stats["size"] == 0


class TestGlobalCaches:
    """Test global cache instances."""

    def test_get_system_info_cache(self):
        """Test getting global system info cache."""
        cache1 = get_system_info_cache()
        cache2 = get_system_info_cache()
        assert cache1 is cache2

    def test_get_tool_result_cache(self):
        """Test getting global tool result cache."""
        cache1 = get_tool_result_cache()
        cache2 = get_tool_result_cache()
        assert cache1 is cache2
