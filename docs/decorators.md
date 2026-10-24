# Utility Decorators (`AIutel.py`)
> Last updated: 2025-11-16
> Maintained by [LLM4Free](https://github.com/OEvortex/LLM4Free)

LLM4Free's [`AIutel.py`](../llm4free/AIutel.py:1) module provides powerful utility decorators for function timing and automatic retry logic. These decorators are designed for robust, flexible, and high-performance function enhancement, supporting both synchronous and asynchronous functions with comprehensive error handling and performance monitoring.

## Table of Contents

1. [Core Decorators](#core-decorators)
2. [Parameters Reference](#parameters-reference)
3. [Function Signatures](#function-signatures)
4. [Advanced Usage Examples](#advanced-usage-examples)
5. [Error Handling](#error-handling)
6. [Performance Considerations](#performance-considerations)
7. [Integration Examples](#integration-examples)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

## Core Decorators

### [`timeIt`](../llm4free/AIutel.py:15)

A versatile timing decorator that measures and displays the execution time of both synchronous and asynchronous functions with colored output.

```python
from llm4free.AIutel import timeIt

@timeIt
def my_function():
    # Your code here
    pass
```

**Key Features:**
- Automatic detection of sync/async functions using `inspect.iscoroutinefunction()` (imported at the top of `AIutel.py`)
- High-precision timing with microsecond accuracy (`time.monotonic()`)
- Colored terminal output (green bold) for better visibility
- Preserves function metadata with `functools.wraps`
- Zero-configuration setup

### [`retry`](../llm4free/AIutel.py:69)

A configurable retry decorator that automatically retries functions on exceptions with customizable retry count and delay intervals.

```python
from llm4free.AIutel import retry

@retry(retries=5, delay=2)
def unreliable_function():
    # Your code here
    pass
```

**Key Features:**
- Configurable retry attempts and a fixed delay between attempts
- Attempt logging through `litprinter.ic`
- Re-raises the original exception after the final attempt
- Supports both synchronous and asynchronous functions
- No shared state, so it is safe to use across threads

## Parameters Reference

### [`timeIt`](../llm4free/AIutel.py:15) Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `func` | `Callable` | The function to be timed (sync or async) |

**Returns:** Decorated function with timing capabilities

### [`retry`](../llm4free/AIutel.py:69) Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `retries` | `int` | `3` | Maximum number of retry attempts |
| `delay` | `float` | `1` | Delay in seconds between retry attempts |

**Returns:** Decorator function that can be applied to target functions

## Function Signatures

### [`timeIt` Decorator](../llm4free/AIutel.py:15)

```python
def timeIt(func: Callable) -> Callable:
    """
    Decorator to measure execution time of a function (sync or async).
    Prints: - Execution time for '{func.__name__}' : {elapsed:.6f} Seconds.  
    """
```

**Internal Wrappers:**
- `sync_wrapper`: Handles synchronous functions
- `async_wrapper`: Handles asynchronous functions

### [`retry` Decorator](../llm4free/AIutel.py:69)

```python
def retry(retries: int = 3, delay: float = 1) -> Callable:
    """
    Decorator to retry a function on exception.
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            # Retry logic implementation
```

## Advanced Usage Examples

### Basic Function Timing

```python
from llm4free.AIutel import timeIt
import time

@timeIt
def cpu_intensive_task():
    """Simulate CPU-intensive work."""
    total = 0
    for i in range(1000000):
        total += i ** 2
    return total

result = cpu_intensive_task()
# Output: - Execution time for 'cpu_intensive_task' : 0.123456 Seconds.
```

### Async Function Timing

```python
import asyncio
from llm4free.AIutel import timeIt

@timeIt
async def async_api_call():
    """Simulate async API call."""
    await asyncio.sleep(1)
    return {"status": "success"}

async def main():
    result = await async_api_call()
    # Output: - Execution time for 'async_api_call' : 1.001234 Seconds.

asyncio.run(main())
```

### Basic Retry Logic

```python
from llm4free.AIutel import retry
import random

@retry(retries=3, delay=1)
def unreliable_network_call():
    """Simulate unreliable network operation."""
    if random.random() < 0.7:  # 70% failure rate
        raise ConnectionError("Network timeout")
    return {"data": "success"}

try:
    result = unreliable_network_call()
    print(f"Success: {result}")
except ConnectionError as e:
    print(f"Failed after all retries: {e}")
```

### Advanced Retry with Custom Delays

```python
from llm4free.AIutel import retry
import requests

@retry(retries=5, delay=2)
def fetch_data_with_retry(url):
    """Fetch data with automatic retry on failure."""
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()

# Usage
try:
    data = fetch_data_with_retry("https://api.example.com/data")
    print(f"Data fetched: {data}")
except Exception as e:
    print(f"Failed to fetch data: {e}")
```

### Combining Both Decorators

```python
import random
import time

from llm4free.AIutel import timeIt, retry

@timeIt
@retry(retries=3, delay=0.5)
def critical_operation():
    """Critical operation with timing and retry."""
    # Simulate operation that might fail
    if random.random() < 0.3:
        raise RuntimeError("Operation failed")
    
    # Simulate work
    time.sleep(0.1)
    return "Operation completed"

result = critical_operation()
# Output shows both retry attempts and final execution time
```

### Class Method Decoration

```python
import random

from llm4free.AIutel import timeIt, retry

class DataProcessor:
    
    @timeIt
    def process_data(self, data):
        """Process data with timing."""
        return [item.upper() for item in data]
    
    @retry(retries=5, delay=1)
    def save_to_database(self, data):
        """Save data with retry logic."""
        # Simulate database operation
        if random.random() < 0.2:
            raise ConnectionError("Database connection failed")
        return "Data saved successfully"

processor = DataProcessor()
result = processor.process_data(["hello", "world"])
processor.save_to_database(result)
```

### Async Retry Pattern

```python
import asyncio
import random
from llm4free.AIutel import retry

# retry() detects coroutine functions and awaits them between attempts
@retry(retries=3, delay=1)
async def unreliable_async_operation():
    """Async operation that might fail."""
    await asyncio.sleep(0.1)
    if random.random() < 0.5:
        raise RuntimeError("Async operation failed")
    return "Async success"

async def main():
    try:
        print(await unreliable_async_operation())
    except Exception as e:
        print(f"Failed: {e}")

asyncio.run(main())
```

## Error Handling

### Exception Propagation

The [`retry`](../llm4free/AIutel.py:69) decorator handles exceptions gracefully:

1. **Catches all exceptions** during function execution
2. **Logs attempt information** with exception details
3. **Applies delay** between retry attempts
4. **Preserves original exception** if all retries fail

```python
from llm4free.AIutel import retry

@retry(retries=2, delay=0.5)
def failing_function():
    raise ValueError("This always fails")

try:
    failing_function()
except ValueError as e:
    # Original exception is preserved
    print(f"Final exception: {e}")
    # Output shows all retry attempts:
    # Attempt 1 failed: This always fails. Retrying in 0.5 seconds...
    # Attempt 2 failed: This always fails. Retrying in 0.5 seconds...
```

### Custom Exception Handling

```python
import random

from llm4free.AIutel import retry

class CustomRetryError(Exception):
    pass

@retry(retries=3, delay=1)
def operation_with_custom_exceptions():
    """Function that raises custom exceptions."""
    error_type = random.choice([ValueError, TypeError, CustomRetryError])
    raise error_type(f"Custom error: {error_type.__name__}")

try:
    operation_with_custom_exceptions()
except Exception as e:
    print(f"Final error type: {type(e).__name__}")
    print(f"Error message: {e}")
```

### Timing Accuracy

The [`timeIt`](../llm4free/AIutel.py:15) decorator uses `time.monotonic()` for timing:

- **Precision**: Microsecond accuracy (6 decimal places)
- **Overhead**: Minimal timing overhead (~1-2 microseconds)
- **Thread-safe**: Safe for use in multi-threaded environments

## Performance Considerations

### Timing Overhead

The [`timeIt`](../llm4free/AIutel.py:15) decorator adds minimal overhead:

```python
@timeIt
def minimal_function():
    return 42

# Typical overhead: 1-5 microseconds
# For functions running < 1ms, overhead might be noticeable
# For functions running > 10ms, overhead is negligible
```
