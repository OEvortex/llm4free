from litprinter import ic
import asyncio
import functools
import inspect
import time

# --- Utility Decorators ---
from typing import Callable, Optional

from .prompt_manager import AwesomePrompts  # noqa: E402,F401
from .sanitize import *  # noqa: E402, F401, F403



def timeIt(func: Callable):
    """
    Decorator to measure execution time of a function (sync or async).
    Logs: - Execution time for '{func.__name__}' : {elapsed:.6f} Seconds.
    """
    GREEN_BOLD = "\033[1;92m"
    RESET = "\033[0m"

    def _log_elapsed(func_name: str, elapsed: float) -> None:
        msg = f"\n{GREEN_BOLD}- Execution time for '{func_name}' : {elapsed:.6f} Seconds.  {RESET}\n"
        try:
            ic(msg)
        except Exception:
            pass
        try:
            print(msg)
        except Exception:
            pass

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.monotonic()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            elapsed = time.monotonic() - start_time
            _log_elapsed(getattr(func, "__name__", getattr(func, "__qualname__", str(func))), elapsed)

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.monotonic()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            elapsed = time.monotonic() - start_time
            _log_elapsed(getattr(func, "__name__", getattr(func, "__qualname__", str(func))), elapsed)

    try:
        if inspect.iscoroutinefunction(func):
            return async_wrapper
    except Exception:
        pass
    try:
        import inspect

        if inspect.iscoroutinefunction(func):
            return async_wrapper
    except Exception:
        pass
    return sync_wrapper


def retry(retries: int = 3, delay: float = 1) -> Callable:
    """
    Decorator to retry a function on exception.

    Supports both synchronous and asynchronous functions. Uses
    ``time.sleep`` for sync functions and ``asyncio.sleep`` for async
    functions so that async callers are never blocked.
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    ic(
                        "Attempt %d failed: %s. Retrying in %s seconds...", attempt + 1, exc, delay
                    )
                    time.sleep(delay)
            if last_exc is not None:
                raise last_exc
            func_name = getattr(func, "__name__", str(func))
            raise RuntimeError(
                f"Function {func_name} failed after {retries} retries with no exception recorded"
            )

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    ic(
                        "Attempt %d failed: %s. Retrying in %s seconds...", attempt + 1, exc, delay
                    )
                    await asyncio.sleep(delay)
            if last_exc is not None:
                raise last_exc
            func_name = getattr(func, "__name__", str(func))
            raise RuntimeError(
                f"Function {func_name} failed after {retries} retries with no exception recorded"
            )

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator
