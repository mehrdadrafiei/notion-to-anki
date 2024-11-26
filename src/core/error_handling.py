import logging
from functools import wraps
from typing import Callable, Dict, Optional, ParamSpec, Type, TypeVar

from fastapi import HTTPException

from .exceptions.base import AppError

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")

ErrorMapping = Dict[Type[Exception], tuple[int, str]]

DEFAULT_ERROR_MAPPING: ErrorMapping = {
    AppError: (500, "Internal application error"),
    ValueError: (400, "Invalid input"),
    KeyError: (404, "Resource not found"),
    Exception: (500, "Internal server error"),
}


def handle_exceptions(
    error_mapping: Optional[ErrorMapping] = None,
    log_level: int = logging.ERROR,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Advanced exception handler with error mapping and logging

    Args:
        error_mapping: Custom mapping of exceptions to (status_code, message)
        log_level: Logging level for errors

    Usage:
        @handle_exceptions({
            ValidationError: (400, "Invalid input"),
            ResourceNotFoundError: (404, "Resource not found"),
            NotionError: (502, "Notion API error")
        })
        async def my_function():
            ...
    """
    combined_mapping = {**DEFAULT_ERROR_MAPPING, **(error_mapping or {})}

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Find the most specific matching exception type
                for exc_type, (status_code, message) in combined_mapping.items():
                    if isinstance(e, exc_type):
                        # Prepare log data without reserved fields
                        log_data = {
                            "function_name": func.__name__,
                            "function_module": func.__module__,
                            "arguments": str(args),
                            "keyword_arguments": str(kwargs),
                            "exception_type": type(e).__name__,
                        }

                        if isinstance(e, AppError):
                            log_data.update(
                                {
                                    "error_code": e.error_code,
                                    "error_details": e.details,
                                }
                            )
                            error_response = {"message": message, "error_code": e.error_code, "details": e.details}
                        else:
                            error_response = {"message": message}

                        logger.log(log_level, str(e), extra=log_data)
                        raise HTTPException(status_code=status_code, detail=error_response)

                # If no matching exception type is found, raise a generic 500 error
                logger.exception("Unhandled exception in %s", func.__name__)
                raise HTTPException(status_code=500, detail={"message": "Internal server error"})

        return wrapper

    return decorator


def handle_service_errors(
    default_return_value: Optional[T] = None,
    error_mapping: Optional[Dict[Type[Exception], str]] = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Error handler for service layer operations that should not raise HTTP exceptions

    Args:
        default_return_value: Value to return on error
        error_mapping: Custom mapping of exceptions to handler functions
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                log_data = {
                    "function_name": func.__name__,
                    "function_module": func.__module__,
                    "arguments": str(args),
                    "keyword_arguments": str(kwargs),
                    "exception_type": type(e).__name__,
                }

                if isinstance(e, AppError):
                    log_data.update(
                        {
                            "error_code": e.error_code,
                            "error_details": e.details,
                        }
                    )

                logger.error(str(e), extra=log_data)
                return default_return_value

        return wrapper

    return decorator
