import logging
from functools import wraps
from typing import Callable, Optional

logging.basicConfig(level=logging.ERROR)


class AppError(Exception):
    """Base application-specific exception"""

    def __init__(self, message: str, context: Optional[dict] = None):
        self.message = message
        self.context = context or {}
        super().__init__(self.message)


class ConfigurationError(AppError):
    """Raised when there's a configuration-related issue"""

    pass


class ExternalServiceError(AppError):
    """Raised when an external service (like Notion) fails"""

    pass


def handle_errors_decorator(
    default_return_value=None, exceptions=(Exception,), message="An error occurred"
) -> Callable:
    """
    Decorator for handling errors in a function.

    Args:
        default_return_value (Any, optional): The default return value if an error occurs. Defaults to None.
        exceptions (tuple, optional): The exceptions to catch. Defaults to (Exception,).
        message (str, optional): The message to log if an error occurs. Defaults to "An error occurred".

    Returns:
        Callable: The decorated function.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                logging.error(f"{message} in {func.__name__}: {e}")
                return default_return_value

        return wrapper

    return decorator


import logging
from functools import wraps
from typing import Any, Callable, List, Optional, Type


class AppError(Exception):
    """Base application-specific exception"""

    def __init__(self, message: str, context: Optional[dict] = None):
        self.message = message
        self.context = context or {}
        super().__init__(self.message)


class ConfigurationError(AppError):
    """Raised when there's a configuration-related issue"""

    pass


class ExternalServiceError(AppError):
    """Raised when an external service (like Notion) fails"""

    pass


def handle_errors(
    logger: logging.Logger,
    default_return: Any = None,
    exceptions: List[Type[Exception]] = None,
    error_type: Optional[Type[AppError]] = None,
) -> Callable:
    """
    Advanced error handling decorator with more robust logging and error tracking

    Args:
        logger: Logging instance to use
        default_return: Value to return if an error occurs
        exceptions: List of specific exceptions to catch
        error_type: Custom error type to raise
    """
    exceptions = exceptions or [Exception]

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except tuple(exceptions) as e:
                # Detailed error logging
                error_details = {'function': func.__name__, 'module': func.__module__, 'args': args, 'kwargs': kwargs}

                # Log the error with context
                logger.error(f"Error in {func.__name__}: {str(e)}", extra={'error_details': error_details})

                # Optionally raise a custom error type
                if error_type:
                    raise error_type(message=str(e), context=error_details) from e

                return default_return

        return wrapper

    return decorator
