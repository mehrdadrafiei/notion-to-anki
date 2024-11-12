import logging
from functools import wraps

logging.basicConfig(level=logging.ERROR)

def handle_errors(default_return_value=None, exceptions=(Exception,), message="An error occurred"):
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