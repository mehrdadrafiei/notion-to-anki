import logging
from functools import wraps
from typing import Callable

logging.basicConfig(level=logging.ERROR)


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
