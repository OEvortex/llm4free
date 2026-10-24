# Stream Sanitization Utilities (`llm4free.sanitize`)
> Last updated: 2025-12-20
> Maintained by [LLM4Free](https://github.com/OEvortex/LLM4Free)

LLM4Free's [`llm4free.sanitize`](../llm4free/sanitize.py#L1) module provides a comprehensive suite of utilities for processing, transforming, and sanitizing data streams. These tools are designed for robust, flexible, and high-performance handling of text and byte streams, including real-time data, API responses, and streaming content from various sources.

## Table of Contents

1. [Core Components](#core-components)
2. [Main Function](#main-function)
3. [Parameters Reference](#parameters-reference)
4. [Processing Modes](#processing-modes)
5. [Internal Functions](#internal-functions)
6. [Advanced Usage Examples](#advanced-usage-examples)
7. [Error Handling](#error-handling)
8. [Performance Considerations](#performance-considerations)
9. [Troubleshooting](#troubleshooting)
10. [Integration Guide](#integration-guide)

## Core Components

### [`sanitize.py`](../llm4free/sanitize.py#L1)

The main sanitization module that provides comprehensive stream processing capabilities.

```python
from llm4free.sanitize import sanitize_stream, LITSTREAM, sanitize_stream_decorator, lit_streamer

# Basic usage
gen = sanitize_stream(data, intro_value="data:", to_json=True)
for item in gen:
    print(item)
```

**Key Features:**
- Stream processing for strings, bytes, and iterables
- JSON parsing and validation
- Regex-based filtering and extraction
- Marker-based content selection
- Custom error handling and formatting
- Support for both synchronous and asynchronous streams
- Flexible output formatting

## Main Function

### [`sanitize_stream()`](../llm4free/sanitize.py#L684)

The main entry point for stream processing that handles multiple data types and processing modes.

```python
from llm4free.sanitize import sanitize_stream

# Basic usage
gen = sanitize_stream(data, intro_value="data:", to_json=True)
for item in gen:
    print(item)
```

**Function Signature:**
```python
def sanitize_stream(
    data: Union[str, bytes, Iterable[str], Iterable[bytes], AsyncIterable[str],
                AsyncIterable[bytes], dict, list, int, float, bool, None],
    intro_value: str = "data:",
    to_json: bool = True,
    skip_markers: Optional[List[str]] = None,
    strip_chars: Optional[str] = None,
    start_marker: Optional[str] = None,
    end_marker: Optional[str] = None,
    content_extractor: Optional[Callable[[Union[str, Dict[str, Any]]], Optional[Any]]] = None,
    yield_raw_on_error: bool = True,
    encoding: EncodingType = "utf-8",
    encoding_errors: str = "replace",
    buffer_size: int = 8192,
    line_delimiter: Optional[str] = None,
    error_handler: Optional[Callable[[Exception, str], Optional[Any]]] = None,
    skip_regexes: Optional[List[Union[str, Pattern[str]]]] = None,
    extract_regexes: Optional[List[Union[str, Pattern[str]]]] = None,
    object_mode: Literal["as_is", "json", "str"] = "json",
    raw: bool = False,
    output_formatter: Optional[Callable[[Any], Any]] = None,
) -> Union[Generator[Any, None, None], AsyncGenerator[Any, None]]
```

## Parameters Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data` | `Union[str, bytes, Iterable, AsyncIterable, dict, list, int, float, bool, None]` | - | Input data to process |
| `intro_value` | `str` | `"data:"` | Prefix to remove from each chunk |
| `to_json` | `bool` | `True` | Parse chunks as JSON |
| `skip_markers` | `Optional[List[str]]` | `None` | Skip lines containing these exact strings |
| `strip_chars` | `Optional[str]` | `None` | Characters to strip from lines |
| `start_marker` | `Optional[str]` | `None` | Begin processing after this marker |
| `end_marker` | `Optional[str]` | `None` | Stop processing at this marker |
| `content_extractor` | `Optional[Callable]` | `None` | Transform content before yielding |
| `yield_raw_on_error` | `bool` | `True` | Yield raw content on JSON parse errors |
| `encoding` | `EncodingType` | `"utf-8"` | Encoding for byte streams |
| `encoding_errors` | `str` | `"replace"` | How to handle encoding errors |
| `buffer_size` | `int` | `8192` | Buffer size for byte decoding |
| `line_delimiter` | `Optional[str]` | `None` | Custom line delimiter |
| `error_handler` | `Optional[Callable]` | `None` | Custom error handling callback |
| `skip_regexes` | `Optional[List[Union[str, Pattern]]]` | `None` | Regex patterns to skip |
| `extract_regexes` | `Optional[List[Union[str, Pattern]]]` | `None` | Regex patterns for content extraction |
| `object_mode` | `Literal["as_is", "json", "str"]` | `"json"` | How to handle non-iterable objects |
| `raw` | `bool` | `False` | Yield raw API response chunks |
| `output_formatter` | `Optional[Callable[[Any], Any]]` | `None` | Custom callable to format/transform each output item before yielding |

### Supported Encodings

The [`EncodingType`](../llm4free/sanitize.py#L20) supports a wide range of character encodings:
- **Unicode**: `utf-8`, `utf-16`, `utf-32`
- **ASCII/Latin**: `ascii`, `latin1`, `iso-8859-1`, `iso-8859-2`
- **Windows**: `cp1252`, `windows-1250`, `windows-1251`, `windows-1252`
- **Asian**: `gbk`, `big5`, `shift_jis`, `euc-jp`, `euc-kr`

## Processing Modes

### Synchronous Mode

Handles strings, bytes, and synchronous iterables:

```python
# String processing
data = "data: {'result': 42}\ndata: {'result': 99}"
for item in sanitize_stream(data):
    print(item)  # {'result': 42}, {'result': 99}

# List processing
data = ['data: {"status": "ok"}', 'data: {"count": 5}']
for item in sanitize_stream(data):
    print(item)
```

### Asynchronous Mode

Handles async iterables automatically:

```python
import asyncio

async def async_data_source():
    yield 'data: {"message": "hello"}'
    yield 'data: {"message": "world"}'

async def process_async():
    async for item in sanitize_stream(async_data_source()):
        print(item)

asyncio.run(process_async())
```

### Raw Mode

Returns unprocessed chunks as received:

```python
# Raw mode preserves original formatting
for chunk in sanitize_stream(data, raw=True):
    print(repr(chunk))  # Shows exact content with whitespace
```

### Object Mode

Handles non-iterable objects:

```python
# JSON mode (default)
result = list(sanitize_stream({"key": "value"}))
# Returns: ['{"key": "value"}']

# String mode
result = list(sanitize_stream({"key": "value"}, object_mode="str"))
# Returns: ["{'key': 'value'}"]

# As-is mode
result = list(sanitize_stream({"key": "value"}, object_mode="as_is"))
# Returns: [{"key": "value"}]
```

## Internal Functions

### [`_compile_regexes(patterns)`](../llm4free/sanitize.py#L24)

Compiles regex patterns for efficient matching.

**Parameters:**
- `patterns`: List of regex patterns as strings or compiled Pattern objects

**Returns:**
- List of compiled Pattern objects, or None if input is None

**Raises:**
- `ValueError`: If any pattern is invalid

### [`_process_chunk(...)`](../llm4free/sanitize.py#L54)

Core chunk processing function that handles sanitization and parsing.

**Key Operations:**
1. Prefix removal (`intro_value`)
2. Character stripping (`strip_chars`)
3. Marker-based skipping (`skip_markers`)
4. Regex-based extraction (`extract_regexes`)
5. Regex-based skipping (`skip_regexes`)
6. JSON parsing (`to_json`)
7. Error handling (`error_handler`)

### [`_decode_byte_stream(byte_iterator, ...)`](../llm4free/sanitize.py#L154)

Synchronous byte stream decoder with flexible encoding support.

**Features:**
- Real-time decoding with buffering
- Graceful encoding error handling
- Performance optimization with memory views
- Support for multiple character encodings

### [`_decode_byte_stream_async(byte_iterator, ...)`](../llm4free/sanitize.py#L217)

Asynchronous counterpart to the synchronous byte decoder.

### [`_sanitize_stream_sync(...)`](../llm4free/sanitize.py#L273)

Synchronous stream processing engine with advanced filtering and transformation capabilities.

### [`_sanitize_stream_async(...)`](../llm4free/sanitize.py#L468)

Asynchronous stream processing engine that mirrors synchronous functionality.

## Advanced Usage Examples

### Complex Filtering with Regex

```python
import re
from llm4free.sanitize import sanitize_stream

data = [
    'data: {"type": "message", "content": "Hello"}',
    'data: {"type": "error", "content": "Failed"}',
    'data: {"type": "message", "content": "World"}',
]

# Skip error messages and extract only content
skip_regexes = [r'"type":\s*"error"']
extract_regexes = [r'"content":\s*"([^"]+)"']

for item in sanitize_stream(
    data,
    skip_regexes=skip_regexes,
    extract_regexes=extract_regexes,
    to_json=False  # Since we're extracting strings
):
    print(item)  # "Hello", "World"
```

### Custom Content Transformation

```python
def extract_important_data(content):
    """Extract only important fields from parsed JSON."""
    if isinstance(content, dict):
        return {k: v for k, v in content.items() if k.startswith('important_')}
    return content

data = [
    'data: {"important_field": "keep", "noise": "ignore"}',
    'data: {"important_data": 42, "metadata": "skip"}',
]

for item in sanitize_stream(data, content_extractor=extract_important_data):
    print(item)
```

### Error Handling with Custom Handler

```python
def custom_error_handler(exception, raw_chunk):
    """Custom error handling for JSON parsing failures."""
    print(f"JSON Error: {exception}")
    # Try to extract useful info even from malformed JSON
    if "partial_data" in raw_chunk:
        return {"status": "partial", "raw": raw_chunk}
    return None  # Skip this chunk

data = [
    'data: {"valid": "json"}',
    'data: {invalid json with partial_data}',
    'data: {completely broken}',
]

for item in sanitize_stream(
    data,
    error_handler=custom_error_handler,
    yield_raw_on_error=False
):
    print(item)
```

### File Processing

```python
# Process file-like objects
with open('data.jsonl', 'r') as f:
    for item in sanitize_stream(f, intro_value="", to_json=True):
        print(item)

# Process bytes from file
with open('data.txt', 'rb') as f:
    for item in sanitize_stream(f, encoding='utf-8'):
        print(item)
```

### Streaming API Responses

```python
import requests

def process_streaming_api():
    response = requests.get('https://api.example.com/stream', stream=True)

    # Process raw chunks
    for chunk in sanitize_stream(response.iter_content(chunk_size=1024), raw=True):
        print(f"Raw chunk: {chunk}")

    # Process as JSON stream
    for item in sanitize_stream(response.iter_lines(decode_unicode=True)):
        print(f"Parsed: {item}")
```

### Output Formatting with `output_formatter`

The `output_formatter` parameter allows you to transform each output item into any desired structure before yielding. Define your own custom formatter function to structure the output however you need.

```python
from llm4free.sanitize import sanitize_stream
import time

# Simple custom formatter - wrap content in a dict with timestamp
def simple_formatter(content):
    return {'text': content, 'timestamp': time.time()}

data = ['data: {"message": "Hello"}', 'data: {"message": "World"}']
for item in sanitize_stream(data, output_formatter=simple_formatter):
    print(item)  # {'text': {'message': 'Hello'}, 'timestamp': 1234567890.123}

# Message format with role
def message_formatter(content):
    return {'role': 'assistant', 'content': content}

for item in sanitize_stream(data, output_formatter=message_formatter):
    print(item)  # {'role': 'assistant', 'content': {'message': 'Hello'}}

# Custom OpenAI-like response format
def openai_formatter(content):
    return {
        'choices': [{'message': {'role': 'assistant', 'content': content}}]
    }

for item in sanitize_stream(data, output_formatter=openai_formatter):
    print(item['choices'][0]['message']['content'])
```

### Decorator Usage

```python
from llm4free.sanitize import sanitize_stream_decorator, lit_streamer

# Basic decorator
@sanitize_stream_decorator
def api_data_generator():
    yield 'data: {"result": 1}'
    yield 'data: {"result": 2}'

# Decorator with parameters
@lit_streamer(skip_markers=["[DONE]"], to_json=True)
def streaming_response():
    yield 'data: {"message": "hello"}'
    yield 'data: {"message": "world"}'
    yield '[DONE]'

# Async decorator
@sanitize_stream_decorator(to_json=True)
async def async_api_generator():
    yield 'data: {"async": "result"}'
```

### Marker-Based Processing

```python
# Process content between markers
data = """
START_DATA
data: {"item": 1}
data: {"item": 2}
END_DATA
other content
"""

for item in sanitize_stream(
    data,
    start_marker="START_DATA",
    end_marker="END_DATA"
):
    print(item)  # Only processes content between markers
```

### Multi-Pattern Regex Extraction

```python
# Extract different types of content with multiple patterns
data = [
    'log: [INFO] User login: john_doe',
    'log: [ERROR] Failed attempt from 192.168.1.1',
    'log: [INFO] User logout: jane_smith',
]

# Extract usernames from INFO logs and IPs from ERROR logs
extract_regexes = [
    r'\[INFO\] User \w+: (\w+)',  # Extract usernames
    r'\[ERROR\].*?(\d+\.\d+\.\d+\.\d+)',  # Extract IP addresses
]

for item in sanitize_stream(
    data,
    intro_value="log: ",
    extract_regexes=extract_regexes,
    to_json=False
):
    print(item)  # "john_doe", "192.168.1.1", "jane_smith"
```

## Error Handling

### Exception Types

The module handles several types of errors gracefully:

1. **JSON Parsing Errors**: When `to_json=True` and content isn't valid JSON
2. **Encoding Errors**: When byte streams can't be decoded with specified encoding
3. **Regex Errors**: When invalid regex patterns are provided
4. **Type Errors**: When unsupported data types are passed

### Error Handler Callback

```python
def comprehensive_error_handler(exception, raw_chunk):
    """Comprehensive error handling with logging and recovery."""
    import logging
    
    if isinstance(exception, json.JSONDecodeError):
        logging.warning(f"JSON decode error: {exception}")
        # Try to fix common JSON issues
        if raw_chunk.endswith(','):
            try:
                return json.loads(raw_chunk[:-1])
            except:
                pass
    
    # Log other errors
    logging.error(f"Processing error: {type(exception).__name__}: {exception}")
    
    # Return structured error info
    return {
        "error": True,
        "error_type": type(exception).__name__,
        "raw_content": raw_chunk,
        "timestamp": time.time()
    }
```

### Graceful Degradation

```python
# Handle mixed content types gracefully
mixed_data = [
    'data: {"valid": "json"}',
    'data: invalid json content',
    'data: {"another": "valid"}',
    b'data: {"bytes": "content"}',  # Mixed bytes and strings
]

for item in sanitize_stream(
    mixed_data,
    yield_raw_on_error=True,  # Keep processing on errors
    encoding_errors='ignore'  # Skip problematic bytes
):
    print(type(item), item)
```

## Performance Considerations

### Optimization Tips

1. **Buffer Size Tuning**: Adjust `buffer_size` based on your data characteristics
   ```python
   # For small, frequent chunks
   sanitize_stream(data, buffer_size=1024)
   
   # For large data streams
   sanitize_stream(data, buffer_size=32768)
   ```

2. **Regex Compilation**: Pre-compile regex patterns for better performance
   ```python
   import re
   
   # Pre-compiled patterns are more efficient
   skip_patterns = [re.compile(r'debug|trace'), re.compile(r'temporary')]
   sanitize_stream(data, skip_regexes=skip_patterns)
   ```

3. **Memory Management**: Use generators instead of collecting all results
   ```python
   # Memory efficient - processes one item at a time
   for item in sanitize_stream(large_dataset):
       process_item(item)
   
   # Memory intensive - loads everything into memory
   all_items = list(sanitize_stream(large_dataset))
   ```

4. **Encoding Selection**: Choose appropriate encoding for your data
   ```python
   # Use specific encoding if known
   sanitize_stream(data, encoding='latin1')  # Faster than utf-8 for some data
   ```

## Troubleshooting

### Common Issues

#### Issue: "TypeError: Input must be a string or an iterable"
**Cause**: Passing unsupported data type
**Solution**: 
```python
# Wrong
sanitize_stream(None)

# Right - handle None explicitly
data = data or []
sanitize_stream(data)
```

#### Issue: "ValueError: Invalid regex pattern"
**Cause**: Malformed regex in `skip_regexes` or `extract_regexes`
**Solution**:
```python
import re

# Test regex patterns first
try:
    pattern = re.compile(r'your_pattern_here')
    sanitize_stream(data, skip_regexes=[pattern])
except re.error as e:
    print(f"Invalid regex: {e}")
```

#### Issue: Memory usage grows continuously
**Cause**: Accumulating results instead of processing incrementally
**Solution**:
```python
# Wrong - accumulates in memory
results = list(sanitize_stream(large_data))

# Right - process incrementally
for item in sanitize_stream(large_data):
    process_and_discard(item)
```

#### Issue: JSON parsing fails frequently
**Cause**: Malformed JSON in stream
**Solution**:
```python
# Use custom error handler for recovery
def json_fixer(exception, chunk):
    # Try common fixes
    fixes = [
        lambda x: x.replace("'", '"'),  # Single to double quotes
        lambda x: x + '}',              # Add missing closing brace
        lambda x: x.rstrip(',')         # Remove trailing comma
    ]
    
    for fix in fixes:
        try:
            return json.loads(fix(chunk))
        except:
            continue
    return None

sanitize_stream(data, error_handler=json_fixer)
```

#### Issue: Encoding errors with international text
**Cause**: Wrong encoding specified
**Solution**:
```python
# Try multiple encodings
encodings = ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']

for encoding in encodings:
    try:
        results = list(sanitize_stream(data, encoding=encoding))
        break
    except UnicodeDecodeError:
        continue
else:
    # Fallback to error-tolerant mode
    results = list(sanitize_stream(data, encoding_errors='replace'))
```

### Debug Mode

Enable detailed logging for troubleshooting:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# The module will output debug information to stderr
for item in sanitize_stream(problematic_data):
    print(item)
```

### Testing Your Configuration

```python
def test_sanitize_config(data_sample, **kwargs):
    """Test sanitize_stream configuration with sample data."""
    try:
        results = list(sanitize_stream(data_sample, **kwargs))
        print(f"✓ Processed {len(results)} items successfully")
        print(f"Sample output: {results[:3]}")
        return True
    except Exception as e:
        print(f"✗ Configuration failed: {e}")
        return False

# Test your configuration
test_data = ['data: {"test": "value"}', 'data: {"test": 123}']
test_sanitize_config(test_data, intro_value="data:", to_json=True)
```

## Decorator Aliases

The module provides several aliases for decorator usage:

- [`sanitize_stream_decorator`](../llm4free/sanitize.py#L1000): Full decorator function
- [`lit_streamer`](../llm4free/sanitize.py#L1001): Short alias for decorator
- [`LITSTREAM`](../llm4free/sanitize.py#L997): Alias for main function

```python
from llm4free.sanitize import LITSTREAM, lit_streamer

# All equivalent
@sanitize_stream_decorator(to_json=True)
@lit_streamer(to_json=True)  
@LITSTREAM.__decorator__(to_json=True)
def my_generator():
    yield 'data: {"key": "value"}'
```

## Integration Guide

### With FastAPI

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from llm4free.sanitize import sanitize_stream

app = FastAPI()

@app.get("/stream")
async def stream_data():
    async def generate():
        data_source = get_async_data_source()
        async for item in sanitize_stream(data_source):
            yield f"data: {json.dumps(item)}\n\n"
    
    return StreamingResponse(generate(), media_type="text/plain")
```

### With asyncio

```python
import asyncio
from llm4free.sanitize import sanitize_stream

async def process_multiple_streams():
    streams = [get_stream_1(), get_stream_2(), get_stream_3()]
    
    async def process_stream(stream):
        async for item in sanitize_stream(stream):
            await handle_item(item)
    
    # Process all streams concurrently
    await asyncio.gather(*[process_stream(s) for s in streams])
```

### With requests

```python
import requests
from llm4free.sanitize import sanitize_stream

def stream_api_data(url):
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    # Process streaming response
    for item in sanitize_stream(
        response.iter_lines(decode_unicode=True),
        intro_value="data: ",
        to_json=True
    ):
        yield item
```

### With LLM4Free Providers

Provider streaming APIs return typed `ChatCompletionChunk` objects, not raw SSE
text, so you usually do **not** need `sanitize_stream` for them:

```python
from llm4free import Client

client = Client()
stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True,
)

for chunk in stream:
    text = chunk.choices[0].delta.content
    if text:
        print(text, end="")
```

Use `sanitize_stream` when you have a raw SSE/bytes stream from a custom
provider or HTTP endpoint (see the `requests` example above).

### With File Processing

```python
# Process large log files efficiently
with open('large_log_file.log', 'r') as f:
    for item in sanitize_stream(
        f,
        intro_value="LOG:",
        skip_regexes=[r'DEBUG.*', r'TRACE.*'],
        extract_regexes=[r'ERROR: (.*)'],
        to_json=False
    ):
        # Process only ERROR messages
        log_error(item)
```

### With Data Cleaning Pipelines

```python
# Create a data cleaning pipeline
def clean_data_pipeline(raw_data):
    """Multi-stage data cleaning pipeline."""
    
    # Stage 1: Basic cleaning
    cleaned = sanitize_stream(
        raw_data,
        intro_value="data:",
        skip_markers=["[INVALID]", "[CORRUPTED]"],
        strip_chars="\t\r\n"
    )
    
    # Stage 2: JSON validation and extraction
    validated = sanitize_stream(
        cleaned,
        to_json=True,
        extract_regexes=[r'"valid_data": (.*)'],
        error_handler=custom_json_fixer
    )
    
    # Stage 3: Final formatting
    formatted = sanitize_stream(
        validated,
        output_formatter=final_formatter
    )
    
    return formatted
```

*This documentation covers the comprehensive functionality of the [`llm4free.sanitize`](../llm4free/sanitize.py#L1) module. For the most up-to-date information, refer to the source code and inline documentation.*
