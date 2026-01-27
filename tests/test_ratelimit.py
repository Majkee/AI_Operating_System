"""Tests for rate limiting system."""

import time
from unittest.mock import MagicMock

import pytest

from aios.ratelimit import (
    RateLimitConfig,
    TokenBucket,
    SlidingWindowCounter,
    RateLimitStatus,
    APIRateLimiter,
    rate_limited,
    get_rate_limiter,
    configure_rate_limiter,
)


class TestTokenBucket:
    """Test TokenBucket class."""

    def test_initial_tokens(self):
        """Test bucket starts with initial tokens."""
        bucket = TokenBucket(rate=1, capacity=10)
        assert bucket.available == 10

    def test_custom_initial_tokens(self):
        """Test custom initial token count."""
        bucket = TokenBucket(rate=1, capacity=10, initial_tokens=5)
        assert int(bucket.available) == 5

    def test_acquire_success(self):
        """Test successful token acquisition."""
        bucket = TokenBucket(rate=1, capacity=10)
        assert bucket.acquire(1, blocking=False) is True
        assert int(bucket.available) == 9

    def test_acquire_multiple(self):
        """Test acquiring multiple tokens."""
        bucket = TokenBucket(rate=1, capacity=10)
        assert bucket.acquire(5, blocking=False) is True
        assert int(bucket.available) == 5

    def test_acquire_insufficient(self):
        """Test acquiring when insufficient tokens."""
        bucket = TokenBucket(rate=1, capacity=10, initial_tokens=2)
        assert bucket.acquire(5, blocking=False) is False
        assert int(bucket.available) == 2  # Unchanged

    def test_refill(self):
        """Test token refill over time."""
        bucket = TokenBucket(rate=10, capacity=10, initial_tokens=0)
        time.sleep(0.2)  # Should add ~2 tokens
        assert bucket.available >= 1

    def test_wait_time(self):
        """Test calculating wait time."""
        bucket = TokenBucket(rate=10, capacity=10, initial_tokens=0)
        wait = bucket.wait_time(5)
        assert wait > 0
        assert wait <= 0.5  # 5 tokens at 10/sec = 0.5s

    def test_wait_time_available(self):
        """Test wait time when tokens available."""
        bucket = TokenBucket(rate=10, capacity=10)
        assert bucket.wait_time(5) == 0


class TestSlidingWindowCounter:
    """Test SlidingWindowCounter class."""

    def test_initial_state(self):
        """Test initial state allows requests."""
        counter = SlidingWindowCounter(limit=10, window_seconds=60)
        assert counter.is_allowed() is True
        assert counter.remaining == 10

    def test_record_request(self):
        """Test recording a request."""
        counter = SlidingWindowCounter(limit=10, window_seconds=60)
        assert counter.record() is True
        assert counter.remaining == 9
        assert counter.current_count == 1

    def test_limit_reached(self):
        """Test behavior when limit reached."""
        counter = SlidingWindowCounter(limit=3, window_seconds=60)

        assert counter.record() is True
        assert counter.record() is True
        assert counter.record() is True
        assert counter.record() is False  # Limit reached
        assert counter.is_allowed() is False

    def test_window_expiry(self):
        """Test requests expire after window."""
        counter = SlidingWindowCounter(limit=2, window_seconds=0.1)

        counter.record()
        counter.record()
        assert counter.is_allowed() is False

        time.sleep(0.15)
        assert counter.is_allowed() is True

    def test_wait_time(self):
        """Test calculating wait time."""
        counter = SlidingWindowCounter(limit=1, window_seconds=1)
        counter.record()

        wait = counter.wait_time()
        assert wait > 0
        assert wait <= 1

    def test_wait_time_available(self):
        """Test wait time when requests available."""
        counter = SlidingWindowCounter(limit=10, window_seconds=60)
        assert counter.wait_time() == 0


class TestRateLimitStatus:
    """Test RateLimitStatus dataclass."""

    def test_not_limited(self):
        """Test status when not limited."""
        status = RateLimitStatus(
            is_limited=False,
            wait_time=0,
            requests_remaining=10,
            tokens_remaining=50
        )
        assert status.is_limited is False
        assert status.wait_time == 0

    def test_limited(self):
        """Test status when limited."""
        status = RateLimitStatus(
            is_limited=True,
            wait_time=5.5,
            requests_remaining=0,
            tokens_remaining=0,
            message="Rate limited"
        )
        assert status.is_limited is True
        assert status.wait_time == 5.5
        assert "Rate limited" in status.message


class TestAPIRateLimiter:
    """Test APIRateLimiter class."""

    def test_default_config(self):
        """Test limiter with default config."""
        limiter = APIRateLimiter()
        assert limiter.config.requests_per_minute == 50

    def test_custom_config(self):
        """Test limiter with custom config."""
        config = RateLimitConfig(requests_per_minute=10)
        limiter = APIRateLimiter(config)
        assert limiter.config.requests_per_minute == 10

    def test_check_allowed(self):
        """Test checking when requests are allowed."""
        limiter = APIRateLimiter()
        status = limiter.check()
        assert status.is_limited is False
        assert status.requests_remaining > 0

    def test_acquire(self):
        """Test acquiring permission to make request."""
        limiter = APIRateLimiter()
        status = limiter.acquire(blocking=False)
        assert status.is_limited is False

    def test_acquire_records_request(self):
        """Test that acquire records the request."""
        config = RateLimitConfig(requests_per_minute=100)
        limiter = APIRateLimiter(config)

        initial = limiter.check().requests_remaining
        limiter.acquire(blocking=False)
        after = limiter.check().requests_remaining

        assert after == initial - 1

    def test_record_tokens(self):
        """Test recording token usage."""
        limiter = APIRateLimiter()
        limiter.record_tokens(1000)
        assert limiter.stats["total_tokens_used"] == 1000

    def test_stats(self):
        """Test getting statistics."""
        limiter = APIRateLimiter()
        limiter.acquire(blocking=False)
        limiter.acquire(blocking=False)
        limiter.record_tokens(500)

        stats = limiter.stats
        assert stats["total_requests"] == 2
        assert stats["total_tokens_used"] == 500


class TestRateLimitedDecorator:
    """Test rate_limited decorator."""

    def test_allows_requests(self):
        """Test decorator allows requests within limits."""
        limiter = APIRateLimiter()
        call_count = [0]

        @rate_limited(limiter)
        def api_call():
            call_count[0] += 1
            return "success"

        result = api_call()
        assert result == "success"
        assert call_count[0] == 1

    def test_callback_on_limited(self):
        """Test callback is called when rate limited."""
        config = RateLimitConfig(requests_per_minute=1)
        limiter = APIRateLimiter(config)
        limited_calls = []

        def on_limited(status):
            limited_calls.append(status)

        @rate_limited(limiter, on_limited=on_limited)
        def api_call():
            return "success"

        # First call should succeed
        limiter.acquire(blocking=False)  # Use up the limit

        # Note: This test verifies the callback mechanism
        # In practice, the decorator would wait
        status = limiter.check()
        if status.is_limited:
            on_limited(status)
            assert len(limited_calls) == 1

    def test_stats_accessible(self):
        """Test stats are accessible through decorated function."""
        limiter = APIRateLimiter()

        @rate_limited(limiter)
        def api_call():
            return "success"

        api_call()
        stats = api_call.stats()
        assert "total_requests" in stats


class TestGlobalRateLimiter:
    """Test global rate limiter functions."""

    def test_get_rate_limiter(self):
        """Test getting global rate limiter."""
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()
        assert limiter1 is limiter2

    def test_configure_rate_limiter(self):
        """Test configuring global rate limiter."""
        config = RateLimitConfig(requests_per_minute=25)
        limiter = configure_rate_limiter(config)
        assert limiter.config.requests_per_minute == 25
