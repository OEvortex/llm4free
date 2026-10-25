# 🚀 LLM4Free Awesome Prompts Manager
> Last updated: 2025-12-20
> Maintained by [LLM4Free](https://github.com/OEvortex/LLM4Free)

LLM4Free's Awesome Prompts Manager provides a comprehensive system for managing and utilizing AI personas and specialized prompts. This module offers optimized prompt retrieval, caching, and management capabilities for enhanced AI interactions.

## Table of Contents

1. [Core Components](#core-components)
2. [Prompt Manager](#prompt-manager)
3. [Configuration Options](#configuration-options)
4. [Usage Examples](#usage-examples)
5. [Prompt Categories](#prompt-categories)
6. [Advanced Features](#advanced-features)
7. [Integration Guide](#integration-guide)

## Core Components

### [`prompt_manager.py`](../llm4free/prompt_manager.py#L1)

The main prompt management module that provides comprehensive prompt handling capabilities.

```python
from llm4free.prompt_manager import AwesomePrompts

# Initialize the prompt manager
prompt_manager = AwesomePrompts()

# Get a specific prompt
prompt = prompt_manager.get_act("UX/UI Developer")
print(prompt)
```

**Key Features:**
- Optimized prompt retrieval with LRU caching
- Automatic updates from online repository
- Thread-safe operations with proper locking
- Efficient prompt management and indexing
- Support for both string and numeric key access
- Comprehensive error handling and validation

## Prompt Manager

### [`AwesomePrompts` Class](../llm4free/prompt_manager.py#L22)

The main class for managing awesome prompts with caching and optimization.

```python
from llm4free.prompt_manager import AwesomePrompts

# Initialize with default settings
prompt_manager = AwesomePrompts()

# Or with custom configuration
custom_manager = AwesomePrompts(
    repo_url="https://custom-repo.com/prompts.json",
    local_path="/custom/path/prompts.json",
    auto_update=False,
    cache_size=256
)
```

**Main Methods:**

| Method | Description |
|--------|-------------|
| `get_act(key, default=None, case_insensitive=True, use_cache=True)` | Get a prompt by name or index |
| `add_prompt(name, prompt, validate=True)` | Add a new prompt to the collection |
| `delete_prompt(name, case_insensitive=True, raise_not_found=False)` | Delete a prompt from the collection |
| `update_prompts_from_online(force=False)` | Update prompts from the online repository |
| `show_acts(search=None, limit=100)` | Display available prompts with filtering |
| `get_random_act()` | Get a random prompt from the collection |

## Configuration Options

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo_url` | `str` | `"https://raw.githubusercontent.com/OEvortex/prompts/main/prompt.json"` | URL to fetch prompts from |
| `local_path` | `Optional[str]` | `~/.llm4free/awesome-prompts.json` | Where to save prompts locally |
| `auto_update` | `bool` | `True` | Auto update prompts on initialization |
| `timeout` | `int` | `10` | Timeout for HTTP requests in seconds |
| `impersonate` | `str` | `"chrome110"` | Browser profile for the impersonation backend (`primp`) |
| `cache_size` | `int` | `128` | LRU cache size for get operations |
| `max_workers` | `int` | `4` | Maximum threads for concurrent operations |

## Usage Examples

### Basic Usage

```python
from llm4free.prompt_manager import AwesomePrompts

# Initialize the prompt manager
prompt_manager = AwesomePrompts()

# Get a prompt by name
ux_prompt = prompt_manager.get_act("UX/UI Developer")
print(ux_prompt)

# Get a prompt by index
first_prompt = prompt_manager.get_act(0)
print(first_prompt)
```

### Adding Custom Prompts

```python
# Add a new custom prompt
success = prompt_manager.add_prompt(
    "Custom Developer",
    "I want you to act as a custom software developer specialized in Python and AI applications."
)

if success:
    # Use the newly added prompt
    custom_prompt = prompt_manager.get_act("Custom Developer")
    print(custom_prompt)
```

### Managing Prompts

```python
# List all available prompts
prompt_manager.show_acts()

# Search for specific prompts
prompt_manager.show_acts(search="developer")

# Delete a prompt
prompt_manager.delete_prompt("Custom Developer")

# Get a random prompt
random_prompt = prompt_manager.get_random_act()
print(random_prompt)
```

### Advanced Configuration

```python
# Custom configuration with larger cache
advanced_manager = AwesomePrompts(
    repo_url="https://custom-repo.com/prompts.json",
    local_path="/custom/path/prompts.json",
    auto_update=True,
    cache_size=512,
    timeout=30,
    max_workers=8
)

# Force update from repository
advanced_manager.update_prompts_from_online(force=True)
```

### Using with LLM4Free Providers

```python
from llm4free import Client
from llm4free.prompt_manager import AwesomePrompts

# Initialize both components
prompt_manager = AwesomePrompts()
client = Client()

# Get a specialized prompt
tech_writer_prompt = prompt_manager.get_act("Tech Writer")

# Use the prompt with a provider
response = client.chat.completions.create(
    model="ChatGPT/GPT-6-free",
    messages=[
        {"role": "user", "content": f"{tech_writer_prompt}\n\nPlease write documentation for a new AI API."}
    ],
)
print(response.choices[0].message.content)
```

## Prompt Categories

The upstream catalog (`prompt.json`) currently contains **266 named prompts**. The nine groups below are documentation themes, not fields in the data. Names are the stable keys; numeric indices depend on insertion order and change when the upstream catalog is updated.

```python
prompt_manager.get_act("UX/UI Developer")  # stable: use names
prompt_manager.get_act(30)                  # index may point to a different prompt after an update
```

| Theme | Example prompts |
|-------|-----------------|
| 💻 Development & Technical | `UX/UI Developer`, `Cyber Security Specialist`, `IT Architect`, `Machine Learning Engineer`, `Software Quality Assurance Tester` |
| 🧩 Programming Environments | `Linux Terminal`, `JavaScript Console`, `SQL terminal`, `Python Interpreter`, `Web Browser` |
| 📝 Writing & Content Creation | `English Translator and Improver`, `Storyteller`, `Screenwriter`, `Tech Writer`, `Commit Message Generator` |
| 🎓 Education & Learning | `Philosophy Teacher`, `Math Teacher`, `AI Writing Tutor`, `Wikipedia page`, `note-taking assistant` |
| 💼 Professional Roles | `Recruiter`, `Career Counselor`, `Accountant`, `Financial Analyst`, `Product Manager` |
| 🎭 Entertainment & Creative | `Advertiser`, `Stand-up Comedian`, `Composer`, `Ascii Artist`, `Song Recommender` |
| 🧠 Advisors & Coaches | `Travel Guide`, `Motivational Coach`, `Life Coach`, `Personal Trainer`, `Socratic Method` |
| 🌐 Alternative Models | `Free-mode`, `Lunatic`, `Gaslighter`, `Fallacy Finder`, `Unconstrained AI model DAN` |
| 🔮 Specialized Assistants | `Etymologist`, `Statistician`, `Prompt Generator`, `Tech Reviewer:`, `Synonym finder` |

To see the current list (including prompts added upstream), call:

```python
prompt_manager.show_acts()
prompt_manager.show_acts(search="writer", limit=50)
```

## Advanced Features

### Caching and Performance

The AwesomePrompts manager includes several performance optimizations:

```python
# LRU caching for frequent access
prompt_manager = AwesomePrompts(cache_size=256)

# Thread-safe operations
import threading
def safe_access():
    with threading.Lock():
        prompt = prompt_manager.get_act("Tech Writer")
        print(prompt)

# Efficient updates with minimal network calls
prompt_manager.update_prompts_from_online()
```

### Custom Repository Integration

```python
# Use a custom prompts repository
custom_manager = AwesomePrompts(
    repo_url="https://your-company.com/custom-prompts.json",
    local_path="/company/prompts/custom.json"
)

# Update from custom source
custom_manager.update_prompts_from_online(force=True)
```

### Error Handling and Validation

```python
# Comprehensive error handling
try:
    prompt = prompt_manager.get_act("NonExistentPrompt")
    if prompt is None:
        print("Prompt not found, using default")
        prompt = "Default prompt text"
except Exception as e:
    print(f"Error getting prompt: {e}")

# Input validation when adding prompts
success = prompt_manager.add_prompt(
    "Valid Prompt Name",
    "This is a valid prompt text that meets all requirements."
)
```

### Batch Operations

```python
# Process multiple prompts efficiently
prompts_to_use = ["UX/UI Developer", "Tech Writer", "Linux Terminal"]
for prompt_name in prompts_to_use:
    prompt = prompt_manager.get_act(prompt_name)
    if prompt:
        process_prompt(prompt)

# Filter and display specific categories
prompt_manager.show_acts(search="developer")
```

## Integration Guide

### With LLM4Free Providers

```python
from llm4free import Client
from llm4free.prompt_manager import AwesomePrompts

# Initialize components
prompt_manager = AwesomePrompts()
client = Client()

# Use prompts with different providers
def ask_with_prompt(client, prompt_name, question):
    """Ask a question using a specific prompt persona."""
    persona_prompt = prompt_manager.get_act(prompt_name)
    if persona_prompt:
        full_prompt = f"{persona_prompt}\n\nQuestion: {question}"
        response = client.chat.completions.create(
            model="ChatGPT/GPT-6-free",
            messages=[{"role": "user", "content": full_prompt}],
        )
        return response.choices[0].message.content
    return None

# Example usage
response = ask_with_prompt(client, "Tech Writer", "Explain quantum computing")
print(response)
```

### With FastAPI

```python
from fastapi import FastAPI, HTTPException
from llm4free.prompt_manager import AwesomePrompts

app = FastAPI()
prompt_manager = AwesomePrompts()

@app.get("/prompts/{prompt_name}")
async def get_prompt(prompt_name: str):
    """Get a specific prompt by name."""
    prompt = prompt_manager.get_act(prompt_name)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"prompt_name": prompt_name, "prompt_text": prompt}

@app.get("/prompts/")
async def list_prompts(search: str = None, limit: int = 50):
    """List available prompts with optional filtering."""
    prompt_manager.show_acts(search=search, limit=limit)
    return {"message": "Prompts displayed in console"}
```

### With CLI Applications

```python
import click
from llm4free.prompt_manager import AwesomePrompts

@click.group()
def cli():
    """Awesome Prompts CLI"""
    pass

@cli.command()
@click.argument('prompt_name')
def get(prompt_name):
    """Get a specific prompt"""
    prompt_manager = AwesomePrompts()
    prompt = prompt_manager.get_act(prompt_name)
    if prompt:
        click.echo(prompt)
    else:
        click.echo(f"Prompt '{prompt_name}' not found", err=True)

@cli.command()
@click.option('--search', '-s', help='Search term')
@click.option('--limit', '-l', default=20, help='Limit results')
def list(search, limit):
    """List available prompts"""
    prompt_manager = AwesomePrompts()
    prompt_manager.show_acts(search=search, limit=limit)

if __name__ == '__main__':
    cli()
```

### With Testing Frameworks

```python
import pytest
from llm4free.prompt_manager import AwesomePrompts

@pytest.fixture
def prompt_manager():
    """Fixture for prompt manager"""
    return AwesomePrompts(auto_update=False)

def test_get_existing_prompt(prompt_manager):
    """Test getting an existing prompt"""
    prompt = prompt_manager.get_act("Tech Writer")
    assert prompt is not None
    assert isinstance(prompt, str)
    assert len(prompt) > 0

def test_get_nonexistent_prompt(prompt_manager):
    """Test getting a non-existent prompt"""
    prompt = prompt_manager.get_act("NonExistentPrompt")
    assert prompt is None

def test_add_and_delete_prompt(prompt_manager):
    """Test adding and deleting a prompt"""
    # Add a test prompt
    success = prompt_manager.add_prompt("TestPrompt", "Test prompt content")
    assert success is True
    
    # Verify it exists
    prompt = prompt_manager.get_act("TestPrompt")
    assert prompt == "Test prompt content"
    
    # Delete it
    success = prompt_manager.delete_prompt("TestPrompt")
    assert success is True
    
    # Verify it's gone
    prompt = prompt_manager.get_act("TestPrompt")
    assert prompt is None
```

### With Async Applications

```python
import asyncio
from llm4free.prompt_manager import AwesomePrompts

async def process_prompts_async():
    """Example of using prompts in async context"""
    prompt_manager = AwesomePrompts()
    
    # Get multiple prompts
    prompts = []
    for name in ["UX/UI Developer", "Tech Writer", "Linux Terminal"]:
        prompt = prompt_manager.get_act(name)
        if prompt:
            prompts.append((name, prompt))
    
    # Process them asynchronously
    async def process_prompt_pair(name, prompt):
        # Simulate async processing
        await asyncio.sleep(0.1)
        return f"Processed {name}: {len(prompt)} chars"
    
    results = await asyncio.gather(*[
        process_prompt_pair(name, prompt) 
        for name, prompt in prompts
    ])
    
    return results

# Run the async function
results = asyncio.run(process_prompts_async())
for result in results:
    print(result)
```

## Usage Tips

> [!TIP]
> - **Activation**: Use `prompt_manager.get_act("PromptName")` to retrieve specific prompts
> - **Caching**: Enable caching for better performance with frequently accessed prompts
> - **Updates**: Use `auto_update=True` to keep prompts current with the online repository
> - **Customization**: Add your own prompts with `add_prompt()` for specialized use cases
> - **Thread Safety**: The manager is thread-safe for concurrent access in multi-threaded applications
> - **Error Handling**: Always check for `None` returns when prompts might not exist

## Configuration Best Practices

```python
# Production configuration
production_manager = AwesomePrompts(
    repo_url="https://your-company.com/production-prompts.json",
    local_path="/var/lib/llm4free/prompts.json",
    auto_update=True,
    cache_size=512,
    timeout=30,
    max_workers=8
)

# Development configuration
development_manager = AwesomePrompts(
    repo_url="https://localhost:8000/dev-prompts.json",
    local_path="./dev-prompts.json",
    auto_update=False,
    cache_size=128,
    timeout=10
)

# Testing configuration
test_manager = AwesomePrompts(
    repo_url="https://test-repo.com/prompts.json",
    local_path="./test-prompts.json",
    auto_update=False,
    cache_size=64
)
```

<div align="center">
  <p>
    <a href="https://github.com/OEvortex/LLM4Free"><img alt="GitHub Repository" src="https://img.shields.io/badge/GitHub-Repository-181717?style=for-the-badge&logo=github&logoColor=white"></a>
    <a href="https://t.me/PyscoutAI"><img alt="Telegram Group" src="https://img.shields.io/badge/Telegram%20Group-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white"></a>
  </p>
</div>

*This documentation covers the comprehensive functionality of the [`llm4free.prompt_manager`](../llm4free/prompt_manager.py#L1) module. For the most up-to-date information, refer to the source code and inline documentation.*
