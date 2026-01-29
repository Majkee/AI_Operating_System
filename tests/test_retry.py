"""
Tests for exponential backoff and circuit breaker.

Tests cover:
- Exponential backoff calculation with jitter
- Circuit breaker state transitions
- ErrorRecovery.retry with backoff
- Integration with ClaudeClient
"""

import time
import threading
import pytest
from unittest.mock import Mock, patch, MagicMock

from aios.errors import (
    ErrorRecovery,
    CircuitBreaker,
    CircuitOpenError,
    calculate_backoff,
    Result,
    ErrorCategory,
)


class TestCalculateBackoff:
    """Tests for calculate_backoff function."""

    def test_first_attempt_returns_base_delay(self):
        """First attempt should return approximately base delay."""
        delay = calculate_backoff(attempt=1, base_delay=1.0, jitter=False)
        assert delay == 1.0

    def test_exponential_growth(self):
        """Delay should grow exponentially."""
        delays = [
            calculate_backoff(attempt=i, base_delay=1.0, jitter=False)
            for i in range(1, 5)
        ]
        assert delays == [1.0, 2.0, 4.0, 8.0]

    def test_max_delay_cap(self):
        """Delay should be capped at max_delay."""
        delay = calculate_backoff(
            attempt=10, base_delay=1.0, max_delay=30.0, jitter=False
        )
        assert delay == 30.0

    def test_jitter_adds_variation(self):
        """With jitter enabled, delays should vary."""
        delays = set()
        for _ in range(20):
            delay = calculate_backoff(attempt=1, base_delay=1.0, jitter=True)
            delays.add(round(delay, 3))  # Round to avoid floating point issues

        # Should have multiple different values due to jitter
        assert len(delays) > 1

    def test_jitter_stays_within_bounds(self):
        """Jitter should keep delay within ±25% of calculated value."""
        base = 4.0  # attempt=3 with base_delay=1.0
        for _ in range(100):
            delay = calculate_backoff(attempt=3, base_delay=1.0, jitter=True)
            assert 3.0 <= delay <= 5.0  # 4.0 ± 25%

    def test_zero_base_delay(self):
        """Zero base delay should work."""
        delay = calculate_backoff(attempt=1, base_delay=0.0, jitter=False)
        assert delay == 0.0


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    def test_initial_state_is_closed(self):
        """Circuit breaker starts in closed state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitBreaker.CLOSED

    def test_allows_request_when_closed(self):
        """Closed circuit allows requests."""
        cb = CircuitBreaker()
        assert cb.allow_request() is True

    def test_opens_after_threshold_failures(self):
        """Circuit opens after failure_threshold consecutive failures."""
        cb = CircuitBreaker(failure_threshold=3)

        for _ in range(3):
            cb.record_failure()

        assert cb.state == CircuitBreaker.OPEN
        assert cb.allow_request() is False

    def test_success_resets_failure_count(self):
        """Success resets the failure counter."""
        cb = CircuitBreaker(failure_threshold=3)

        cb.record_failure()
        cb.record_failure()
        cb.record_success()  # Reset

        assert cb.state == CircuitBreaker.CLOSED
        assert cb.allow_request() is True

    def test_transitions_to_half_open_after_timeout(self):
        """Circuit transitions to half-open after recovery timeout."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        time.sleep(0.15)  # Wait for recovery timeout
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_half_open_allows_limited_requests(self):
        """Half-open state allows limited test requests."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01, half_open_max_calls=1)

        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)

        assert cb.state == CircuitBreaker.HALF_OPEN
        assert cb.allow_request() is True  # First allowed
        assert cb.allow_request() is False  # Second blocked

    def test_half_open_success_closes_circuit(self):
        """Success in half-open state closes the circuit."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)

        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)

        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_half_open_failure_reopens_circuit(self):
        """Failure in half-open state reopens the circuit."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)

        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)

        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    def test_reset_clears_state(self):
        """Reset returns circuit to closed state."""
        cb = CircuitBreaker(failure_threshold=2)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        cb.reset()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.allow_request() is True

    def test_get_stats(self):
        """get_stats returns correct information."""
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)
        cb.record_failure()
        cb.record_failure()

        stats = cb.get_stats()

        assert stats["state"] == CircuitBreaker.CLOSED
        assert stats["failure_count"] == 2
        assert stats["failure_threshold"] == 5
        assert stats["recovery_timeout"] == 60.0
        assert stats["last_failure_time"] is not None

    def test_thread_safety(self):
        """Circuit breaker is thread-safe."""
        cb = CircuitBreaker(failure_threshold=100)
        errors = []

        def record_failures():
            try:
                for _ in range(50):
                    cb.record_failure()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_failures) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert cb.state == CircuitBreaker.OPEN


class TestErrorRecoveryRetry:
    """Tests for ErrorRecovery.retry with backoff."""

    def test_success_on_first_attempt(self):
        """Successful function returns immediately."""
        func = Mock(return_value="success")

        result = ErrorRecovery.retry(func, max_attempts=3)

        assert result.is_ok
        assert result.unwrap() == "success"
        assert func.call_count == 1

    def test_retry_on_failure(self):
        """Function is retried on failure."""
        func = Mock(side_effect=[Exception("fail"), Exception("fail"), "success"])

        result = ErrorRecovery.retry(func, max_attempts=3, base_delay=0.01)

        assert result.is_ok
        assert result.unwrap() == "success"
        assert func.call_count == 3

    def test_returns_error_after_max_attempts(self):
        """Returns error result after exhausting attempts."""
        func = Mock(side_effect=Exception("persistent failure"))

        result = ErrorRecovery.retry(func, max_attempts=3, base_delay=0.01)

        assert result.is_err
        assert "3 attempts" in result.error.user_message
        assert func.call_count == 3

    def test_on_retry_callback(self):
        """on_retry callback is called for each retry."""
        exc1 = Exception("fail1")
        exc2 = Exception("fail2")
        func = Mock(side_effect=[exc1, exc2, "success"])
        on_retry = Mock()

        result = ErrorRecovery.retry(
            func, max_attempts=3, on_retry=on_retry, base_delay=0.01
        )

        assert result.is_ok
        assert on_retry.call_count == 2
        on_retry.assert_any_call(1, exc1)
        on_retry.assert_any_call(2, exc2)

    def test_backoff_delay_applied(self):
        """Backoff delay is applied between retries."""
        func = Mock(side_effect=[Exception("fail"), "success"])

        start = time.time()
        result = ErrorRecovery.retry(
            func, max_attempts=2, base_delay=0.1, jitter=False
        )
        elapsed = time.time() - start

        assert result.is_ok
        assert elapsed >= 0.1  # At least one delay

    def test_circuit_breaker_blocks_when_open(self):
        """Circuit breaker blocks requests when open."""
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()  # Opens circuit

        func = Mock(return_value="success")
        result = ErrorRecovery.retry(func, circuit_breaker=cb)

        assert result.is_err
        assert "temporarily unavailable" in result.error.user_message
        assert func.call_count == 0  # Never called

    def test_circuit_breaker_records_success(self):
        """Successful retry records success with circuit breaker."""
        cb = CircuitBreaker(failure_threshold=5)
        cb.record_failure()

        func = Mock(return_value="success")
        result = ErrorRecovery.retry(func, circuit_breaker=cb)

        assert result.is_ok
        stats = cb.get_stats()
        assert stats["failure_count"] == 0  # Reset on success

    def test_circuit_breaker_records_failure(self):
        """Failed retry records failure with circuit breaker."""
        cb = CircuitBreaker(failure_threshold=5)

        func = Mock(side_effect=Exception("fail"))
        result = ErrorRecovery.retry(
            func, max_attempts=2, circuit_breaker=cb, base_delay=0.01
        )

        assert result.is_err
        stats = cb.get_stats()
        assert stats["failure_count"] == 2  # Two failed attempts

    def test_retryable_exceptions_filter(self):
        """Only retryable exceptions trigger retry."""
        # ValueError is not retryable, should fail immediately
        func = Mock(side_effect=ValueError("not retryable"))

        result = ErrorRecovery.retry(
            func,
            max_attempts=3,
            retryable_exceptions=(ConnectionError,),
            base_delay=0.01
        )

        assert result.is_err
        assert func.call_count == 1  # No retry for non-retryable

    def test_retryable_exceptions_allows_retry(self):
        """Retryable exceptions are retried."""
        func = Mock(side_effect=[ConnectionError("fail"), "success"])

        result = ErrorRecovery.retry(
            func,
            max_attempts=3,
            retryable_exceptions=(ConnectionError,),
            base_delay=0.01
        )

        assert result.is_ok
        assert func.call_count == 2

    def test_get_circuit_breaker_creates_named_instance(self):
        """get_circuit_breaker creates and reuses named instances."""
        cb1 = ErrorRecovery.get_circuit_breaker("test_service", failure_threshold=3)
        cb2 = ErrorRecovery.get_circuit_breaker("test_service")

        assert cb1 is cb2  # Same instance

        cb3 = ErrorRecovery.get_circuit_breaker("other_service")
        assert cb1 is not cb3  # Different instance


class TestClaudeClientRetry:
    """Tests for ClaudeClient retry integration."""

    @pytest.fixture
    def mock_anthropic(self):
        """Mock anthropic module."""
        with patch("aios.claude.client.anthropic") as mock:
            # Set up exception classes
            mock.APIConnectionError = type("APIConnectionError", (Exception,), {})
            mock.RateLimitError = type("RateLimitError", (Exception,), {})
            mock.InternalServerError = type("InternalServerError", (Exception,), {})
            yield mock

    @pytest.fixture
    def mock_config(self):
        """Mock configuration."""
        with patch("aios.claude.client.get_config") as mock:
            config = MagicMock()
            config.api.api_key = "test-key"
            config.api.model = "claude-sonnet-4-5-20250929"
            config.api.max_tokens = 4096
            config.api.context_budget = 150000
            config.api.summarize_threshold = 0.75
            config.api.min_recent_messages = 6
            mock.return_value = config
            yield mock

    def test_client_has_circuit_breaker(self, mock_anthropic, mock_config):
        """ClaudeClient initializes with circuit breaker."""
        from aios.claude.client import ClaudeClient

        client = ClaudeClient()

        assert client._circuit_breaker is not None
        assert client._retry_config["max_attempts"] == 3

    def test_get_circuit_breaker_stats(self, mock_anthropic, mock_config):
        """get_circuit_breaker_stats returns stats."""
        from aios.claude.client import ClaudeClient

        client = ClaudeClient()
        stats = client.get_circuit_breaker_stats()

        assert "state" in stats
        assert "failure_count" in stats
        assert stats["state"] == CircuitBreaker.CLOSED

    def test_reset_circuit_breaker(self, mock_anthropic, mock_config):
        """reset_circuit_breaker resets the circuit."""
        from aios.claude.client import ClaudeClient

        client = ClaudeClient()
        # Simulate failures
        for _ in range(5):
            client._circuit_breaker.record_failure()

        assert client._circuit_breaker.state == CircuitBreaker.OPEN

        client.reset_circuit_breaker()
        assert client._circuit_breaker.state == CircuitBreaker.CLOSED

    def test_retryable_exceptions_defined(self, mock_anthropic, mock_config):
        """Client defines appropriate retryable exceptions."""
        from aios.claude.client import ClaudeClient

        client = ClaudeClient()

        assert ConnectionError in client._retryable_exceptions
        assert TimeoutError in client._retryable_exceptions


class TestCircuitOpenError:
    """Tests for CircuitOpenError exception."""

    def test_has_correct_category(self):
        """CircuitOpenError has API category."""
        error = CircuitOpenError()
        assert error.category == ErrorCategory.API

    def test_has_user_message(self):
        """CircuitOpenError has user-friendly message."""
        error = CircuitOpenError()
        assert "temporarily unavailable" in error.user_message

    def test_has_suggested_action(self):
        """CircuitOpenError suggests waiting."""
        error = CircuitOpenError()
        assert "try again" in error.suggested_action.lower()
