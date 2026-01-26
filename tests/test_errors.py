"""Tests for error handling module."""

import pytest

from aios.errors import (
    ErrorSeverity,
    ErrorCategory,
    ErrorContext,
    AIOSError,
    ConfigurationError,
    APIError,
    CommandExecutionError,
    FileOperationError,
    Result,
    ErrorBoundary,
    error_boundary,
    safe_execute,
    ErrorRecovery,
    format_error_for_user,
    format_error_for_log,
)


class TestErrorSeverity:
    """Test ErrorSeverity enum."""

    def test_severity_values(self):
        """Test severity enum values."""
        assert ErrorSeverity.LOW.value == "low"
        assert ErrorSeverity.MEDIUM.value == "medium"
        assert ErrorSeverity.HIGH.value == "high"
        assert ErrorSeverity.CRITICAL.value == "critical"


class TestErrorCategory:
    """Test ErrorCategory enum."""

    def test_category_values(self):
        """Test category enum values."""
        assert ErrorCategory.CONFIGURATION.value == "configuration"
        assert ErrorCategory.NETWORK.value == "network"
        assert ErrorCategory.API.value == "api"
        assert ErrorCategory.FILE_SYSTEM.value == "file_system"


class TestErrorContext:
    """Test ErrorContext dataclass."""

    def test_error_context_creation(self):
        """Test creating an error context."""
        ctx = ErrorContext(
            category=ErrorCategory.API,
            severity=ErrorSeverity.MEDIUM,
            operation="test_operation",
            user_message="Something went wrong",
            technical_message="API returned 500"
        )
        assert ctx.category == ErrorCategory.API
        assert ctx.severity == ErrorSeverity.MEDIUM
        assert ctx.recoverable is True  # default

    def test_error_context_with_all_fields(self):
        """Test error context with all fields."""
        exc = ValueError("test error")
        ctx = ErrorContext(
            category=ErrorCategory.INTERNAL,
            severity=ErrorSeverity.HIGH,
            operation="complex_operation",
            user_message="User friendly message",
            technical_message="Technical details",
            recoverable=False,
            suggested_action="Try again",
            original_exception=exc,
            traceback_str="Traceback...",
            metadata={"key": "value"}
        )
        assert ctx.recoverable is False
        assert ctx.suggested_action == "Try again"
        assert ctx.original_exception == exc
        assert ctx.metadata["key"] == "value"


class TestAIOSError:
    """Test custom exception classes."""

    def test_aios_error_basic(self):
        """Test basic AIOSError creation."""
        err = AIOSError("Test error")
        assert str(err) == "Test error"
        assert err.category == ErrorCategory.UNKNOWN
        assert err.severity == ErrorSeverity.MEDIUM
        assert err.recoverable is True

    def test_aios_error_with_params(self):
        """Test AIOSError with all parameters."""
        err = AIOSError(
            "Test error",
            category=ErrorCategory.API,
            severity=ErrorSeverity.HIGH,
            user_message="User message",
            recoverable=False,
            suggested_action="Do something"
        )
        assert err.category == ErrorCategory.API
        assert err.severity == ErrorSeverity.HIGH
        assert err.user_message == "User message"
        assert err.recoverable is False
        assert err.suggested_action == "Do something"

    def test_configuration_error(self):
        """Test ConfigurationError."""
        err = ConfigurationError("Missing config")
        assert err.category == ErrorCategory.CONFIGURATION
        assert err.severity == ErrorSeverity.HIGH

    def test_api_error(self):
        """Test APIError."""
        err = APIError("API failed")
        assert err.category == ErrorCategory.API
        assert err.severity == ErrorSeverity.MEDIUM

    def test_command_execution_error(self):
        """Test CommandExecutionError."""
        err = CommandExecutionError("Command failed")
        assert err.category == ErrorCategory.COMMAND_EXECUTION
        assert err.severity == ErrorSeverity.LOW

    def test_file_operation_error(self):
        """Test FileOperationError."""
        err = FileOperationError("File not found")
        assert err.category == ErrorCategory.FILE_SYSTEM
        assert err.severity == ErrorSeverity.LOW


class TestResult:
    """Test Result type."""

    def test_ok_result(self):
        """Test successful result."""
        result = Result.ok("value")
        assert result.is_ok is True
        assert result.is_err is False
        assert result.value == "value"
        assert result.unwrap() == "value"

    def test_err_result(self):
        """Test error result."""
        ctx = ErrorContext(
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.LOW,
            operation="test",
            user_message="Error",
            technical_message="Error"
        )
        result = Result.err(ctx)
        assert result.is_ok is False
        assert result.is_err is True
        assert result.error == ctx

    def test_unwrap_on_error_raises(self):
        """Test that unwrap on error raises."""
        ctx = ErrorContext(
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.LOW,
            operation="test",
            user_message="Error",
            technical_message="Error"
        )
        result = Result.err(ctx)
        with pytest.raises(ValueError):
            result.unwrap()

    def test_unwrap_or_with_value(self):
        """Test unwrap_or returns value when ok."""
        result = Result.ok("value")
        assert result.unwrap_or("default") == "value"

    def test_unwrap_or_with_error(self):
        """Test unwrap_or returns default when error."""
        ctx = ErrorContext(
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.LOW,
            operation="test",
            user_message="Error",
            technical_message="Error"
        )
        result = Result.err(ctx)
        assert result.unwrap_or("default") == "default"


class TestErrorBoundary:
    """Test ErrorBoundary context manager."""

    def test_no_error(self):
        """Test boundary with no error."""
        with ErrorBoundary("test_operation") as boundary:
            result = 1 + 1

        assert boundary.has_error is False
        assert boundary.error_context is None

    def test_catches_exception(self):
        """Test boundary catches exception."""
        with ErrorBoundary("test_operation") as boundary:
            raise ValueError("test error")

        assert boundary.has_error is True
        assert boundary.error_context is not None
        assert "test error" in boundary.error_context.technical_message

    def test_error_callback(self):
        """Test error callback is called."""
        errors_received = []

        def on_error(ctx):
            errors_received.append(ctx)

        with ErrorBoundary("test_operation", on_error=on_error) as boundary:
            raise ValueError("test error")

        assert len(errors_received) == 1
        assert errors_received[0].operation == "test_operation"

    def test_custom_aios_error(self):
        """Test boundary with custom AIOSError."""
        with ErrorBoundary("test_operation") as boundary:
            raise APIError(
                "API failed",
                user_message="Could not connect",
                suggested_action="Check network"
            )

        assert boundary.error_context.category == ErrorCategory.API
        assert boundary.error_context.user_message == "Could not connect"
        assert boundary.error_context.suggested_action == "Check network"

    def test_keyboard_interrupt(self):
        """Test boundary handles KeyboardInterrupt."""
        with ErrorBoundary("test_operation") as boundary:
            raise KeyboardInterrupt()

        assert boundary.error_context.category == ErrorCategory.USER_INPUT
        assert "cancelled" in boundary.error_context.user_message.lower()

    def test_show_technical_details(self):
        """Test boundary captures traceback when requested."""
        with ErrorBoundary("test_operation", show_technical_details=True) as boundary:
            raise ValueError("test error")

        assert boundary.error_context.traceback_str is not None
        assert "ValueError" in boundary.error_context.traceback_str


class TestErrorBoundaryDecorator:
    """Test error_boundary decorator."""

    def test_decorator_success(self):
        """Test decorator with successful function."""
        @error_boundary("test_func")
        def successful_func():
            return "success"

        result = successful_func()
        assert result == "success"

    def test_decorator_with_error(self):
        """Test decorator with failing function."""
        @error_boundary("test_func", default_return="default")
        def failing_func():
            raise ValueError("error")

        result = failing_func()
        assert result == "default"


class TestSafeExecute:
    """Test safe_execute function."""

    def test_safe_execute_success(self):
        """Test safe_execute with successful function."""
        result = safe_execute(lambda: "value", "test")
        assert result.is_ok is True
        assert result.value == "value"

    def test_safe_execute_error(self):
        """Test safe_execute with failing function."""
        def failing():
            raise ValueError("error")

        result = safe_execute(failing, "test")
        assert result.is_err is True
        assert result.error is not None

    def test_safe_execute_with_callback(self):
        """Test safe_execute calls error callback."""
        errors = []

        def failing():
            raise ValueError("error")

        result = safe_execute(failing, "test", on_error=lambda e: errors.append(e))
        assert len(errors) == 1


class TestErrorRecovery:
    """Test ErrorRecovery strategies."""

    def test_retry_success_first_try(self):
        """Test retry succeeds on first try."""
        result = ErrorRecovery.retry(lambda: "success")
        assert result.is_ok is True
        assert result.value == "success"

    def test_retry_success_after_failure(self):
        """Test retry succeeds after initial failure."""
        attempts = [0]

        def flaky():
            attempts[0] += 1
            if attempts[0] < 3:
                raise ValueError("not yet")
            return "success"

        result = ErrorRecovery.retry(flaky, max_attempts=5)
        assert result.is_ok is True
        assert result.value == "success"
        assert attempts[0] == 3

    def test_retry_all_fail(self):
        """Test retry fails after max attempts."""
        def always_fail():
            raise ValueError("always fails")

        result = ErrorRecovery.retry(always_fail, max_attempts=3)
        assert result.is_err is True
        assert "3 attempts" in result.error.user_message

    def test_retry_callback(self):
        """Test retry calls callback on each retry."""
        retries = []

        def always_fail():
            raise ValueError("fails")

        ErrorRecovery.retry(
            always_fail,
            max_attempts=3,
            on_retry=lambda attempt, exc: retries.append(attempt)
        )
        assert retries == [1, 2]

    def test_with_fallback_primary_success(self):
        """Test fallback uses primary when it succeeds."""
        result = ErrorRecovery.with_fallback(
            primary=lambda: "primary",
            fallback=lambda: "fallback"
        )
        assert result.is_ok is True
        assert result.value == "primary"

    def test_with_fallback_uses_fallback(self):
        """Test fallback is used when primary fails."""
        result = ErrorRecovery.with_fallback(
            primary=lambda: (_ for _ in ()).throw(ValueError("fail")),
            fallback=lambda: "fallback"
        )
        assert result.is_ok is True
        assert result.value == "fallback"

    def test_with_fallback_both_fail(self):
        """Test error when both primary and fallback fail."""
        result = ErrorRecovery.with_fallback(
            primary=lambda: (_ for _ in ()).throw(ValueError("primary fail")),
            fallback=lambda: (_ for _ in ()).throw(ValueError("fallback fail"))
        )
        assert result.is_err is True
        assert "both" in result.error.user_message.lower()


class TestFormatters:
    """Test error formatters."""

    def test_format_error_for_user_basic(self):
        """Test basic user formatting."""
        ctx = ErrorContext(
            category=ErrorCategory.API,
            severity=ErrorSeverity.MEDIUM,
            operation="test",
            user_message="Something went wrong",
            technical_message="API error"
        )
        formatted = format_error_for_user(ctx)
        assert "Something went wrong" in formatted

    def test_format_error_for_user_with_suggestion(self):
        """Test user formatting with suggestion."""
        ctx = ErrorContext(
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.MEDIUM,
            operation="test",
            user_message="Connection failed",
            technical_message="Timeout",
            suggested_action="Check your internet"
        )
        formatted = format_error_for_user(ctx)
        assert "Connection failed" in formatted
        assert "Check your internet" in formatted

    def test_format_error_for_log(self):
        """Test log formatting."""
        ctx = ErrorContext(
            category=ErrorCategory.API,
            severity=ErrorSeverity.HIGH,
            operation="api_call",
            user_message="User message",
            technical_message="Technical details"
        )
        formatted = format_error_for_log(ctx)
        assert "HIGH" in formatted
        assert "api" in formatted
        assert "Technical details" in formatted

    def test_format_error_for_log_with_traceback(self):
        """Test log formatting with traceback."""
        ctx = ErrorContext(
            category=ErrorCategory.INTERNAL,
            severity=ErrorSeverity.CRITICAL,
            operation="test",
            user_message="Error",
            technical_message="Error",
            traceback_str="Traceback (most recent call last)..."
        )
        formatted = format_error_for_log(ctx)
        assert "Traceback" in formatted
