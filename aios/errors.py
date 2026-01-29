"""
Error handling and recovery for AIOS.

Provides:
- Custom exception types
- Error boundary wrapper for graceful failure handling
- Error recovery mechanisms
- User-friendly error messages
"""

import sys
import time
import random
import traceback
import threading
from typing import Optional, Callable, Any, TypeVar, Generic
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps


class ErrorSeverity(Enum):
    """Severity levels for errors."""
    LOW = "low"           # Minor issues, can continue
    MEDIUM = "medium"     # Significant issues, may affect functionality
    HIGH = "high"         # Serious issues, should stop current operation
    CRITICAL = "critical" # Fatal issues, should exit application


class ErrorCategory(Enum):
    """Categories of errors for better handling."""
    CONFIGURATION = "configuration"
    NETWORK = "network"
    API = "api"
    FILE_SYSTEM = "file_system"
    PERMISSION = "permission"
    COMMAND_EXECUTION = "command_execution"
    USER_INPUT = "user_input"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """Context information about an error."""
    category: ErrorCategory
    severity: ErrorSeverity
    operation: str
    user_message: str
    technical_message: str
    recoverable: bool = True
    suggested_action: Optional[str] = None
    original_exception: Optional[Exception] = None
    traceback_str: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class AIOSError(Exception):
    """Base exception for AIOS errors."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        user_message: Optional[str] = None,
        recoverable: bool = True,
        suggested_action: Optional[str] = None
    ):
        super().__init__(message)
        self.category = category
        self.severity = severity
        self.user_message = user_message or message
        self.recoverable = recoverable
        self.suggested_action = suggested_action


class ConfigurationError(AIOSError):
    """Configuration-related errors."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.CONFIGURATION,
            severity=kwargs.get("severity", ErrorSeverity.HIGH),
            **{k: v for k, v in kwargs.items() if k != "severity"}
        )


class APIError(AIOSError):
    """API communication errors."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.API,
            severity=kwargs.get("severity", ErrorSeverity.MEDIUM),
            **{k: v for k, v in kwargs.items() if k != "severity"}
        )


class CommandExecutionError(AIOSError):
    """Command execution errors."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.COMMAND_EXECUTION,
            severity=kwargs.get("severity", ErrorSeverity.LOW),
            **{k: v for k, v in kwargs.items() if k != "severity"}
        )


class FileOperationError(AIOSError):
    """File operation errors."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.FILE_SYSTEM,
            severity=kwargs.get("severity", ErrorSeverity.LOW),
            **{k: v for k, v in kwargs.items() if k != "severity"}
        )


class PermissionError(AIOSError):
    """Permission-related errors."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.PERMISSION,
            severity=kwargs.get("severity", ErrorSeverity.MEDIUM),
            **{k: v for k, v in kwargs.items() if k != "severity"}
        )


T = TypeVar('T')


@dataclass
class Result(Generic[T]):
    """
    A result type that can hold either a success value or an error.

    Similar to Rust's Result type, this provides explicit error handling.
    """
    value: Optional[T] = None
    error: Optional[ErrorContext] = None

    @property
    def is_ok(self) -> bool:
        """Check if result is successful."""
        return self.error is None

    @property
    def is_err(self) -> bool:
        """Check if result is an error."""
        return self.error is not None

    def unwrap(self) -> T:
        """Get the value, raising if error."""
        if self.error:
            raise ValueError(f"Unwrap called on error: {self.error.user_message}")
        return self.value

    def unwrap_or(self, default: T) -> T:
        """Get the value or a default."""
        return self.value if self.is_ok else default

    @staticmethod
    def ok(value: T) -> "Result[T]":
        """Create a success result."""
        return Result(value=value)

    @staticmethod
    def err(error: ErrorContext) -> "Result[T]":
        """Create an error result."""
        return Result(error=error)


class ErrorBoundary:
    """
    Error boundary for wrapping operations with graceful error handling.

    Usage:
        with ErrorBoundary("operation_name") as boundary:
            # do risky operation
            result = risky_function()

        if boundary.has_error:
            print(boundary.error_context.user_message)
    """

    def __init__(
        self,
        operation: str,
        on_error: Optional[Callable[[ErrorContext], None]] = None,
        show_technical_details: bool = False,
        default_category: ErrorCategory = ErrorCategory.UNKNOWN,
        default_severity: ErrorSeverity = ErrorSeverity.MEDIUM
    ):
        """
        Initialize the error boundary.

        Args:
            operation: Name of the operation being wrapped
            on_error: Optional callback when error occurs
            show_technical_details: Whether to include traceback
            default_category: Default error category if not determined
            default_severity: Default error severity if not determined
        """
        self.operation = operation
        self.on_error = on_error
        self.show_technical_details = show_technical_details
        self.default_category = default_category
        self.default_severity = default_severity
        self.error_context: Optional[ErrorContext] = None

    @property
    def has_error(self) -> bool:
        """Check if an error occurred."""
        return self.error_context is not None

    def __enter__(self) -> "ErrorBoundary":
        """Enter the error boundary context."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """
        Exit the error boundary, catching and processing any exception.

        Returns True to suppress the exception.
        """
        if exc_type is None:
            return False

        # Convert exception to error context
        self.error_context = self._exception_to_context(exc_val, exc_tb)

        # Call error handler if provided
        if self.on_error:
            self.on_error(self.error_context)

        # Suppress the exception (we've handled it)
        return True

    def _exception_to_context(
        self,
        exc: Exception,
        exc_tb
    ) -> ErrorContext:
        """Convert an exception to an ErrorContext."""
        # Determine category and severity based on exception type
        category = self.default_category
        severity = self.default_severity
        user_message = str(exc)
        suggested_action = None
        recoverable = True

        if isinstance(exc, AIOSError):
            category = exc.category
            severity = exc.severity
            user_message = exc.user_message
            suggested_action = exc.suggested_action
            recoverable = exc.recoverable

        elif isinstance(exc, KeyboardInterrupt):
            category = ErrorCategory.USER_INPUT
            severity = ErrorSeverity.LOW
            user_message = "Operation cancelled by user."
            recoverable = True

        elif isinstance(exc, ConnectionError):
            category = ErrorCategory.NETWORK
            severity = ErrorSeverity.MEDIUM
            user_message = "Network connection error. Please check your internet connection."
            suggested_action = "Check your internet connection and try again."

        elif isinstance(exc, FileNotFoundError):
            category = ErrorCategory.FILE_SYSTEM
            severity = ErrorSeverity.LOW
            user_message = f"File not found: {exc.filename if hasattr(exc, 'filename') else 'unknown'}"
            suggested_action = "Check the file path and try again."

        elif isinstance(exc, builtins_permission_error()):
            category = ErrorCategory.PERMISSION
            severity = ErrorSeverity.MEDIUM
            user_message = "Permission denied. You may not have access to this resource."
            suggested_action = "Try running with appropriate permissions."

        elif isinstance(exc, ValueError):
            category = ErrorCategory.USER_INPUT
            severity = ErrorSeverity.LOW
            user_message = f"Invalid value: {str(exc)}"

        elif isinstance(exc, TimeoutError):
            category = ErrorCategory.COMMAND_EXECUTION
            severity = ErrorSeverity.MEDIUM
            user_message = "Operation timed out."
            suggested_action = "Try again or increase the timeout."

        elif isinstance(exc, MemoryError):
            category = ErrorCategory.INTERNAL
            severity = ErrorSeverity.CRITICAL
            user_message = "Out of memory. The operation was too large."
            recoverable = False

        # Build traceback string if requested
        traceback_str = None
        if self.show_technical_details:
            traceback_str = "".join(traceback.format_exception(type(exc), exc, exc_tb))

        return ErrorContext(
            category=category,
            severity=severity,
            operation=self.operation,
            user_message=user_message,
            technical_message=str(exc),
            recoverable=recoverable,
            suggested_action=suggested_action,
            original_exception=exc,
            traceback_str=traceback_str
        )


def builtins_permission_error():
    """Get the built-in PermissionError to avoid shadowing."""
    import builtins
    return builtins.PermissionError


def error_boundary(
    operation: str,
    category: ErrorCategory = ErrorCategory.UNKNOWN,
    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    default_return: Any = None
):
    """
    Decorator for wrapping functions with error boundary.

    Usage:
        @error_boundary("fetch_data", category=ErrorCategory.API)
        def fetch_data():
            # risky operation
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            with ErrorBoundary(
                operation,
                default_category=category,
                default_severity=severity
            ) as boundary:
                return func(*args, **kwargs)

            if boundary.has_error:
                return default_return

        return wrapper
    return decorator


def safe_execute(
    func: Callable[[], T],
    operation: str,
    on_error: Optional[Callable[[ErrorContext], None]] = None,
    default: Optional[T] = None
) -> Result[T]:
    """
    Execute a function safely and return a Result.

    Args:
        func: The function to execute
        operation: Name of the operation (for error context)
        on_error: Optional error callback
        default: Default value if error occurs

    Returns:
        Result containing either the return value or error context
    """
    with ErrorBoundary(operation, on_error=on_error) as boundary:
        result = func()

    if boundary.has_error:
        return Result.err(boundary.error_context)
    return Result.ok(result)


class CircuitBreaker:
    """
    Circuit breaker pattern to prevent hammering a failing service.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Circuit is open, requests fail immediately without calling the service
    - HALF_OPEN: Testing if service has recovered, allows limited requests

    Thread-safe implementation.
    """

    # States
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1
    ):
        """
        Initialize the circuit breaker.

        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery (half-open)
            half_open_max_calls: Number of test calls allowed in half-open state
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        """Get current circuit state."""
        with self._lock:
            return self._get_state_unlocked()

    def _get_state_unlocked(self) -> str:
        """Get state without lock (must be called with lock held)."""
        if self._state == self.OPEN:
            # Check if recovery timeout has elapsed
            if self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._state = self.HALF_OPEN
                    self._half_open_calls = 0
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        with self._lock:
            state = self._get_state_unlocked()

            if state == self.CLOSED:
                return True

            if state == self.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False

            # OPEN state
            return False

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            if self._state == self.HALF_OPEN:
                # Success in half-open state, close the circuit
                self._state = self.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            self._half_open_calls = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == self.HALF_OPEN:
                # Failure in half-open state, reopen the circuit
                self._state = self.OPEN
            elif self._failure_count >= self.failure_threshold:
                self._state = self.OPEN

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        with self._lock:
            self._state = self.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            self._half_open_calls = 0

    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        with self._lock:
            return {
                "state": self._get_state_unlocked(),
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "last_failure_time": self._last_failure_time,
            }


class CircuitOpenError(AIOSError):
    """Raised when circuit breaker is open and request is rejected."""

    def __init__(self, message: str = "Service temporarily unavailable", **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.API,
            severity=ErrorSeverity.MEDIUM,
            user_message="The service is temporarily unavailable. Please try again later.",
            suggested_action="Wait a moment and try again.",
            **kwargs
        )


def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True
) -> float:
    """
    Calculate exponential backoff delay with optional jitter.

    Args:
        attempt: Current attempt number (1-based)
        base_delay: Base delay in seconds
        max_delay: Maximum delay cap in seconds
        jitter: Whether to add randomized jitter

    Returns:
        Delay in seconds
    """
    # Exponential backoff: base_delay * 2^(attempt-1)
    delay = base_delay * (2 ** (attempt - 1))

    # Cap at maximum delay
    delay = min(delay, max_delay)

    # Add jitter (±25% randomization) to prevent thundering herd
    if jitter:
        jitter_range = delay * 0.25
        delay = delay + random.uniform(-jitter_range, jitter_range)

    return max(0.0, delay)


class ErrorRecovery:
    """
    Provides error recovery strategies with exponential backoff and circuit breaker.
    """

    # Shared circuit breakers by name
    _circuit_breakers: dict[str, CircuitBreaker] = {}
    _cb_lock = threading.Lock()

    @classmethod
    def get_circuit_breaker(
        cls,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0
    ) -> CircuitBreaker:
        """
        Get or create a named circuit breaker.

        Args:
            name: Identifier for the circuit breaker
            failure_threshold: Failures before opening
            recovery_timeout: Seconds before recovery attempt

        Returns:
            CircuitBreaker instance
        """
        with cls._cb_lock:
            if name not in cls._circuit_breakers:
                cls._circuit_breakers[name] = CircuitBreaker(
                    failure_threshold=failure_threshold,
                    recovery_timeout=recovery_timeout
                )
            return cls._circuit_breakers[name]

    @staticmethod
    def retry(
        func: Callable[[], T],
        max_attempts: int = 3,
        on_retry: Optional[Callable[[int, Exception], None]] = None,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        circuit_breaker: Optional[CircuitBreaker] = None,
        retryable_exceptions: Optional[tuple] = None
    ) -> Result[T]:
        """
        Retry a function with exponential backoff and optional circuit breaker.

        Args:
            func: Function to execute
            max_attempts: Maximum number of attempts
            on_retry: Callback for each retry (attempt number, exception)
            base_delay: Base delay for exponential backoff (seconds)
            max_delay: Maximum delay cap (seconds)
            jitter: Whether to add randomized jitter to delays
            circuit_breaker: Optional circuit breaker instance
            retryable_exceptions: Tuple of exception types to retry on.
                                  If None, retries on all exceptions.

        Returns:
            Result of the operation
        """
        last_error = None

        # Check circuit breaker before starting
        if circuit_breaker and not circuit_breaker.allow_request():
            stats = circuit_breaker.get_stats()
            return Result.err(ErrorContext(
                category=ErrorCategory.API,
                severity=ErrorSeverity.MEDIUM,
                operation="retry",
                user_message="Service temporarily unavailable due to repeated failures.",
                technical_message=f"Circuit breaker open (failures: {stats['failure_count']})",
                recoverable=True,
                suggested_action=f"Wait {stats['recovery_timeout']}s and try again."
            ))

        for attempt in range(1, max_attempts + 1):
            try:
                result = func()

                # Record success with circuit breaker
                if circuit_breaker:
                    circuit_breaker.record_success()

                return Result.ok(result)

            except Exception as e:
                last_error = e

                # Check if this exception type is retryable
                if retryable_exceptions and not isinstance(e, retryable_exceptions):
                    # Non-retryable exception, fail immediately
                    if circuit_breaker:
                        circuit_breaker.record_failure()
                    break

                # Record failure with circuit breaker
                if circuit_breaker:
                    circuit_breaker.record_failure()

                    # Check if circuit just opened
                    if not circuit_breaker.allow_request():
                        break  # Stop retrying if circuit opened

                # Notify retry callback
                if on_retry and attempt < max_attempts:
                    on_retry(attempt, e)

                # Apply backoff delay (except after last attempt)
                if attempt < max_attempts:
                    delay = calculate_backoff(
                        attempt,
                        base_delay=base_delay,
                        max_delay=max_delay,
                        jitter=jitter
                    )
                    time.sleep(delay)

        return Result.err(ErrorContext(
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.MEDIUM,
            operation="retry",
            user_message=f"Operation failed after {max_attempts} attempts.",
            technical_message=str(last_error) if last_error else "Unknown error",
            recoverable=False,
            original_exception=last_error
        ))

    @staticmethod
    def with_fallback(
        primary: Callable[[], T],
        fallback: Callable[[], T],
        operation: str = "operation"
    ) -> Result[T]:
        """
        Try primary function, fall back to secondary on failure.

        Args:
            primary: Primary function to try
            fallback: Fallback function if primary fails
            operation: Name of the operation

        Returns:
            Result from either primary or fallback
        """
        try:
            return Result.ok(primary())
        except Exception:
            try:
                return Result.ok(fallback())
            except Exception as e:
                return Result.err(ErrorContext(
                    category=ErrorCategory.UNKNOWN,
                    severity=ErrorSeverity.MEDIUM,
                    operation=operation,
                    user_message="Both primary and fallback operations failed.",
                    technical_message=str(e),
                    recoverable=False,
                    original_exception=e
                ))


def format_error_for_user(context: ErrorContext) -> str:
    """
    Format an error context for display to the user.

    Args:
        context: The error context

    Returns:
        Formatted error message
    """
    lines = [context.user_message]

    if context.suggested_action:
        lines.append(f"Suggestion: {context.suggested_action}")

    return "\n".join(lines)


def format_error_for_log(context: ErrorContext) -> str:
    """
    Format an error context for logging.

    Args:
        context: The error context

    Returns:
        Formatted log message
    """
    lines = [
        f"[{context.severity.value.upper()}] {context.category.value}: {context.operation}",
        f"  Message: {context.technical_message}",
    ]

    if context.traceback_str:
        lines.append(f"  Traceback:\n{context.traceback_str}")

    return "\n".join(lines)
