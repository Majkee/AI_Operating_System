"""
Rate limiting for AIOS API calls.

Provides:
- Token bucket rate limiter
- Sliding window rate limiter
- API-specific rate limit handling
"""

import time
from typing import Optional, Callable
from dataclasses import dataclass, field
from threading import Lock
from collections import deque
from functools import wraps


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    requests_per_minute: int = 50
    requests_per_hour: int = 1000
    tokens_per_minute: int = 100000
    burst_allowance: int = 10  # Extra requests allowed in burst


class TokenBucket:
    """
    Token bucket rate limiter.

    Allows bursts while maintaining average rate.
    """

    def __init__(
        self,
        rate: float,
        capacity: int,
        initial_tokens: Optional[int] = None
    ):
        """
        Initialize token bucket.

        Args:
            rate: Tokens added per second
            capacity: Maximum tokens in bucket
            initial_tokens: Starting tokens (default: full bucket)
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = initial_tokens if initial_tokens is not None else capacity
        self.last_update = time.time()
        self._lock = Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now

    def acquire(self, tokens: int = 1, blocking: bool = True) -> bool:
        """
        Acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire
            blocking: Whether to wait for tokens

        Returns:
            True if tokens acquired, False if not available (non-blocking)
        """
        with self._lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            if not blocking:
                return False

            # Calculate wait time
            needed = tokens - self.tokens
            wait_time = needed / self.rate

        # Wait outside lock
        time.sleep(wait_time)

        # Try again
        with self._lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def wait_time(self, tokens: int = 1) -> float:
        """
        Calculate time to wait for tokens.

        Returns:
            Seconds to wait (0 if tokens available)
        """
        with self._lock:
            self._refill()
            if self.tokens >= tokens:
                return 0
            needed = tokens - self.tokens
            return needed / self.rate

    @property
    def available(self) -> float:
        """Get number of available tokens."""
        with self._lock:
            self._refill()
            return self.tokens


class SlidingWindowCounter:
    """
    Sliding window rate limiter.

    More accurate than fixed windows, tracks requests over rolling period.
    """

    def __init__(self, limit: int, window_seconds: float):
        """
        Initialize sliding window counter.

        Args:
            limit: Maximum requests allowed in window
            window_seconds: Size of window in seconds
        """
        self.limit = limit
        self.window_seconds = window_seconds
        self._timestamps: deque = deque()
        self._lock = Lock()

    def _cleanup(self) -> None:
        """Remove expired timestamps."""
        cutoff = time.time() - self.window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    def is_allowed(self) -> bool:
        """Check if a request is allowed."""
        with self._lock:
            self._cleanup()
            return len(self._timestamps) < self.limit

    def record(self) -> bool:
        """
        Record a request.

        Returns:
            True if request was allowed and recorded, False if rate limited
        """
        with self._lock:
            self._cleanup()
            if len(self._timestamps) >= self.limit:
                return False
            self._timestamps.append(time.time())
            return True

    def wait_time(self) -> float:
        """
        Calculate time to wait until a request is allowed.

        Returns:
            Seconds to wait (0 if request allowed now)
        """
        with self._lock:
            self._cleanup()
            if len(self._timestamps) < self.limit:
                return 0
            # Wait until oldest request expires
            oldest = self._timestamps[0]
            return max(0, oldest + self.window_seconds - time.time())

    @property
    def current_count(self) -> int:
        """Get current request count in window."""
        with self._lock:
            self._cleanup()
            return len(self._timestamps)

    @property
    def remaining(self) -> int:
        """Get remaining requests allowed."""
        with self._lock:
            self._cleanup()
            return max(0, self.limit - len(self._timestamps))


@dataclass
class RateLimitStatus:
    """Status of rate limiting."""
    is_limited: bool
    wait_time: float
    requests_remaining: int
    tokens_remaining: float
    message: str = ""


class APIRateLimiter:
    """
    Comprehensive rate limiter for API calls.

    Combines multiple strategies:
    - Per-minute request limit
    - Per-hour request limit
    - Token bucket for burst handling
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        """
        Initialize API rate limiter.

        Args:
            config: Rate limit configuration
        """
        self.config = config or RateLimitConfig()

        # Per-minute limiter
        self._minute_limiter = SlidingWindowCounter(
            limit=self.config.requests_per_minute,
            window_seconds=60
        )

        # Per-hour limiter
        self._hour_limiter = SlidingWindowCounter(
            limit=self.config.requests_per_hour,
            window_seconds=3600
        )

        # Token bucket for bursts
        self._token_bucket = TokenBucket(
            rate=self.config.requests_per_minute / 60,  # Convert to per-second
            capacity=self.config.requests_per_minute + self.config.burst_allowance
        )

        # Track total requests
        self._total_requests = 0
        self._total_tokens_used = 0
        self._lock = Lock()

    def check(self) -> RateLimitStatus:
        """
        Check if a request is allowed without recording it.

        Returns:
            Rate limit status
        """
        # Check minute limit
        if not self._minute_limiter.is_allowed():
            wait = self._minute_limiter.wait_time()
            return RateLimitStatus(
                is_limited=True,
                wait_time=wait,
                requests_remaining=0,
                tokens_remaining=self._token_bucket.available,
                message=f"Per-minute limit reached. Wait {wait:.1f}s"
            )

        # Check hour limit
        if not self._hour_limiter.is_allowed():
            wait = self._hour_limiter.wait_time()
            return RateLimitStatus(
                is_limited=True,
                wait_time=wait,
                requests_remaining=0,
                tokens_remaining=self._token_bucket.available,
                message=f"Per-hour limit reached. Wait {wait:.1f}s"
            )

        return RateLimitStatus(
            is_limited=False,
            wait_time=0,
            requests_remaining=self._minute_limiter.remaining,
            tokens_remaining=self._token_bucket.available,
            message=""
        )

    def acquire(self, blocking: bool = True) -> RateLimitStatus:
        """
        Acquire permission to make a request.

        Args:
            blocking: Whether to wait if rate limited

        Returns:
            Rate limit status after acquisition attempt
        """
        status = self.check()

        if status.is_limited:
            if blocking and status.wait_time > 0:
                time.sleep(status.wait_time)
                return self.acquire(blocking=False)
            return status

        # Record the request
        self._minute_limiter.record()
        self._hour_limiter.record()
        self._token_bucket.acquire(1, blocking=False)

        with self._lock:
            self._total_requests += 1

        return RateLimitStatus(
            is_limited=False,
            wait_time=0,
            requests_remaining=self._minute_limiter.remaining,
            tokens_remaining=self._token_bucket.available,
            message=""
        )

    def record_tokens(self, tokens_used: int) -> None:
        """Record tokens used in a request."""
        with self._lock:
            self._total_tokens_used += tokens_used

    def wait_if_needed(self) -> float:
        """
        Wait if rate limited.

        Returns:
            Time waited in seconds
        """
        status = self.check()
        if status.is_limited and status.wait_time > 0:
            time.sleep(status.wait_time)
            return status.wait_time
        return 0

    @property
    def stats(self) -> dict:
        """Get rate limiter statistics."""
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "total_tokens_used": self._total_tokens_used,
                "minute_remaining": self._minute_limiter.remaining,
                "hour_remaining": self._hour_limiter.remaining,
                "burst_tokens": self._token_bucket.available,
            }


def rate_limited(
    limiter: APIRateLimiter,
    on_limited: Optional[Callable[[RateLimitStatus], None]] = None
):
    """
    Decorator for rate-limited functions.

    Args:
        limiter: APIRateLimiter instance
        on_limited: Callback when rate limited (before waiting)

    Example:
        limiter = APIRateLimiter()

        @rate_limited(limiter)
        def call_api():
            return api.request()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            status = limiter.check()

            if status.is_limited:
                if on_limited:
                    on_limited(status)
                limiter.wait_if_needed()

            limiter.acquire(blocking=False)
            return func(*args, **kwargs)

        wrapper.limiter = limiter
        wrapper.check_limit = limiter.check
        wrapper.stats = lambda: limiter.stats

        return wrapper
    return decorator


# Global rate limiter instance
_api_rate_limiter: Optional[APIRateLimiter] = None


def get_rate_limiter() -> APIRateLimiter:
    """Get the global API rate limiter instance."""
    global _api_rate_limiter
    if _api_rate_limiter is None:
        _api_rate_limiter = APIRateLimiter()
    return _api_rate_limiter


def configure_rate_limiter(config: RateLimitConfig) -> APIRateLimiter:
    """Configure and return the global rate limiter."""
    global _api_rate_limiter
    _api_rate_limiter = APIRateLimiter(config)
    return _api_rate_limiter
