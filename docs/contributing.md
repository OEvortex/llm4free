# Contributing to LLM4Free

> **Last updated:** 2026-01-24  
> **Type:** Developer Guide  
> **Status:** Active contributions welcome

## Welcome!

Thank you for considering contributing to LLM4Free. This guide will help you get started with development and ensure your contributions meet our quality standards.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Types of Contributions](#types-of-contributions)
- [Code Quality Standards](#code-quality-standards)
- [Testing Requirements](#testing-requirements)
- [Commit Standards](#commit-standards)
- [Pull Request Process](#pull-request-process)
- [Documentation Standards](#documentation-standards)

---

## Getting Started

### Prerequisites

- Python 3.10+
- Git
- A GitHub account

### Fork and Clone

```bash
# 1. Fork the repository on GitHub
# Visit: https://github.com/OEvortex/LLM4Free

# 2. Clone your fork
git clone https://github.com/YOUR-USERNAME/LLM4Free.git
cd LLM4Free

# 3. Add upstream remote
git remote add upstream https://github.com/OEvortex/LLM4Free.git

# 4. Verify remotes
git remote -v
# origin   YOUR-FORK (fetch/push)
# upstream ORIGINAL (fetch)
```

---

## Development Setup

### Using UV (Recommended)

```bash
# Install UV if not already installed
pip install uv

# Install with development dependencies
uv sync --extra dev --extra api

# Run tests
uv run pytest

# Run linter
uv run ruff check .

# Run type checker
uvx ty check .
```

### Using pip

```bash
# Create virtual environment
python -m venv venv

# Activate
# Linux/macOS
source venv/bin/activate
# Windows
venv\Scripts\activate

# Install in development mode
pip install -e ".[dev,api]"

# Install linting and type checking tools
pip install ruff ty
```

### Verify Setup

```bash
# Check Python version
python --version

# Check LLM4Free import
python -c "import llm4free; print(llm4free.__version__)"

# Check tools
ruff --version
ty --version
```

---

## Types of Contributions

### 1. New Providers

```python
# Modern OpenAI-compatible providers live in llm4free/llm/
from typing import Any, Dict, List, Optional

from llm4free.llm.base import BaseChat, BaseCompletions, OpenAICompatibleProvider, SimpleModelList


class NewProvider(OpenAICompatibleProvider):
    required_auth = False  # or True when an API key is mandatory
    AVAILABLE_MODELS = ["new-model"]

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any):
        super().__init__(api_key=api_key, **kwargs)
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


class Chat(BaseChat):
    def __init__(self, client: NewProvider):
        self.completions = Completions(client)


class Completions(BaseCompletions):
    def create(self, *, model: str, messages: List[Dict[str, Any]], stream: bool = False, **kwargs: Any):
        # Return a ChatCompletion, or a generator of ChatCompletionChunk when stream=True
        ...
```

See the [Provider Development Guide](provider-development.md) for the full contract.
### 2. Bug Fixes

```bash
# Create issue branch
git checkout -b fix/issue-description

# Make changes
# ... edit files ...

# Test changes
uv run pytest tests/

# Commit
git commit -m "fix: brief description of fix"

# Push
git push origin fix/issue-description
```

### 3. Features

```bash
# Create feature branch
git checkout -b feature/feature-name

# Make changes
# ... implement feature ...

# Add tests
# ... create tests/test_feature.py ...

# Commit and push
git commit -m "feat: add new feature"
git push origin feature/feature-name
```

### 4. Documentation

```bash
# Create docs branch
git checkout -b docs/update-name

# Edit docs
# ... edit files in docs/ ...

# Verify markdown renders properly
# Commit and push
git commit -m "docs: update documentation"
git push origin docs/update-name
```

---

## Code Quality Standards

### Line Length

Maximum 100 characters (enforced by Ruff):

```python
# ✓ Good - under 100 characters
response = client.chat.completions.create(model="gpt-4o", messages=messages, max_tokens=100)

# ❌ Bad - over 100 characters
response = client.chat.completions.create(model="gpt-4o", messages=messages, max_tokens=100, temperature=0.7, top_p=0.9)
# Should be split:
response = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    max_tokens=100,
    temperature=0.7,
    top_p=0.9,
)
```

### Type Hints

All functions must have type hints:

```python
# ✓ Good - complete type hints
def chat(
    self,
    prompt: str,
    stream: bool = False,
    **kwargs: Any,
) -> Union[str, Generator[str, None, None]]:
    pass

# ❌ Bad - missing type hints
def chat(self, prompt, stream=False, **kwargs):
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def chat(
    self,
    prompt: str,
    stream: bool = False,
) -> str:
    """
    Send a prompt and get a response.
    
    Args:
        prompt (str): The user's prompt
        stream (bool): Whether to stream response. Defaults to False.
    
    Returns:
        str: The AI response
    
    Raises:
        ProviderConnectionError: If the request fails
    
    Example:
        >>> client = MyProvider(api_key="key")
        >>> response = client.chat("Hello")
        >>> print(response)
    """
    pass
```

### Imports

Keep imports organized:

```python
# Order: standard library, third-party, local
import json
from typing import Any, Dict, Optional

import requests
from curl_cffi.requests import Session

from llm4free.AIbase import Provider
from llm4free import exceptions
```

### Naming Conventions

```python
# Classes: PascalCase
class MyProvider:
    pass

# Functions/methods: snake_case
def get_response():
    pass

# Constants: UPPER_SNAKE_CASE
MAX_TOKENS = 1000

# Private: _leading_underscore
def _internal_method():
    pass
```

---

## Testing Requirements

### Run All Tests

```bash
# Run full test suite
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_tool_calling.py

# Run specific test
uv run pytest tests/test_tool_calling.py::test_name
```

### Write Tests

Create `tests/test_yourprovider.py`:

```python
import unittest
from unittest.mock import MagicMock, patch

from llm4free.llm.your_provider import YourProvider


class TestYourProvider(unittest.TestCase):

    def setUp(self):
        """Setup test fixtures."""
        self.provider = YourProvider(api_key="test-key")

    @patch("llm4free.llm.your_provider.requests.post")
    def test_chat_basic(self, mock_post):
        """Test the OpenAI-compatible non-streaming interface."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "Test response"}}]},
        )

        response = self.provider.chat.completions.create(
            model="new-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        self.assertEqual(response.choices[0].message.content, "Test response")

    def test_available_models(self):
        """Test that the provider exposes its model list."""
        self.assertIn("new-model", list(self.provider.models))
        self.assertEqual(self.provider.required_auth, True)


if __name__ == "__main__":
    unittest.main()
```

### Test Coverage

Aim for at least 80% coverage:

```bash
# Run tests with coverage
uv run pytest --cov=llm4free tests/

# Generate coverage report
uv run pytest --cov=llm4free --cov-report=html tests/
# Open htmlcov/index.html to view report
```

---

## Linting & Type Checking

### Ruff (Linting & Formatting)

```bash
# Check all files
uv run ruff check .

# Fix automatically fixable issues
uv run ruff check . --fix

# Check specific file
uv run ruff check llm4free/llm/my_provider.py

# Format code
uv run ruff format .
```

### Type Checking with Ty

```bash
# Check all files
uvx ty check .

# Check specific file
uvx ty check llm4free/llm/my_provider.py
```

### Quality Checklist

Before submitting a PR:

```bash
# 1. Run linter
uv run ruff check .

# 2. Fix linter issues
uv run ruff check . --fix

# 3. Run type checker
uvx ty check .

# 4. Run tests
uv run pytest

# 5. Check coverage
uv run pytest --cov=llm4free tests/

# All should pass ✓
```

---

## Commit Standards

### Commit Message Format

Use conventional commits:

```
<type>: <description>

<body>

<footer>
```

### Types

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Code style (spacing, formatting)
- `refactor:` Code changes without feature/fix
- `perf:` Performance improvements
- `test:` Test changes
- `chore:` Maintenance tasks

### Examples

```bash
# Good commit messages
git commit -m "feat: add caching to provider responses"
git commit -m "fix: handle network timeout in GROQ provider"
git commit -m "docs: update getting started guide"
git commit -m "refactor: simplify chat method logic"

# Bad commit messages
git commit -m "Update stuff"
git commit -m "Fixed things"
git commit -m "Random changes"
```

### Write Descriptive Commits

```python
# If your change is more complex, provide context

git commit -m "feat: implement conversation history

This adds support for multi-turn conversations with automatic
context management. Conversation history is stored in memory
and cleared on provider reset.

Implements request #123"
```

---

## Pull Request Process

### Before You Start

1. **Create an issue** for major changes
2. **Check existing PRs** to avoid duplicates
3. **Sync with upstream** to avoid conflicts

```bash
# Update from upstream
git fetch upstream
git rebase upstream/main
```

### Submit Your PR

1. **Push your branch:**
   ```bash
   git push origin feature/your-feature
   ```

2. **Create PR on GitHub:**
   - Base: `OEvortex/LLM4Free` main
   - Compare: `YOUR-USERNAME/LLM4Free` your-branch
   - Title: Brief description
   - Description: Details about changes

3. **PR Description Template:**
   ```markdown
   ## Description
   Brief explanation of what this PR does.
   
   ## Type of Change
   - [ ] New feature
   - [ ] Bug fix
   - [ ] Documentation
   - [ ] Provider implementation
   
   ## Related Issue
   Closes #123
   
   ## Testing
   Steps to verify the changes work correctly.
   
   ## Checklist
   - [ ] Code follows style guidelines
   - [ ] Tests added/updated
   - [ ] Documentation updated
   - [ ] Linting passes
   - [ ] Type checking passes
   ```

### Review Process

- **Automated checks** must pass (CI/CD)
- **Code review** by maintainers
- **Changes may be requested** - respond promptly
- **Approval** from at least one maintainer
- **Merge** when ready

### Common Review Comments

| Comment | What to Do |
|---------|-----------|
| "Please add type hints" | Add type annotations to function |
| "Can you add a test?" | Create unit test for new code |
| "Ruff found issues" | Fix linting: `ruff check . --fix` |
| "Type checker failed" | Fix type hints for proper typing |
| "Update docs" | Document your new feature |

---

## Documentation Standards

### Markdown Files

Keep to these standards:

```markdown
# Heading 1 - File title (use only once per file)

> Context about the file
> Last updated: date
> Type: guide/reference

## Heading 2 - Major section

### Heading 3 - Subsection

#### Heading 4 - Sub-subsection

**Bold** for emphasis  
*Italic* for terms  
`code` for inline code

\`\`\`python
# Code blocks with language
code here
\`\`\`

- Bullet lists
- Are structured
- And easy to scan

| Table | Headers |
|-------|---------|
| are | useful |
| for | comparisons |

[Links](path/to/file.md) are relative paths
```

### Code Examples

Include runnable examples:

```python
# ✓ Good - complete, runnable example
from llm4free.llm.Auth.groq import Groq

client = Groq(api_key="your-key")
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "What is machine learning?"}],
)
print(response.choices[0].message.content)

# ❌ Bad - incomplete example
client = GROQ(api_key="key")
response = client.chat("What is ML?")
```

### Cross-References

Use relative paths:

```markdown
# Instead of absolute paths
[Getting Started](../getting-started.md)
[API Reference](api-reference.md)
[Provider List](api/providers.md)

# Not: https://github.com/... (too specific)
```

---

## Architecture Guidelines

Follow the structure in [AGENTS.md](../AGENTS.md):

- Provider implementations go in `llm4free/llm/`
- Search engines go in `llm4free/search/`
- Utilities go in `llm4free/Extra/`
- Tests go in `tests/`
- Documentation goes in `docs/`

---

## Getting Help

- **Questions:** [GitHub Discussions](https://github.com/OEvortex/LLM4Free/discussions)
- **Issues:** [GitHub Issues](https://github.com/OEvortex/LLM4Free/issues)
- **Chat:** [Telegram Group](https://t.me/OEvortexAI)
- **Documentation:** [docs/README.md](README.md)

---

## Summary

1. ✅ Fork and clone repository
2. ✅ Set up development environment with UV
3. ✅ Create a feature/fix branch
4. ✅ Make changes following code standards
5. ✅ Write/update tests
6. ✅ Ensure all checks pass:
   - `ruff check . --fix`
   - `ty check .`
   - `pytest`
7. ✅ Commit with conventional messages
8. ✅ Push and create PR
9. ✅ Respond to review comments
10. ✅ Celebrate your contribution! 🎉

Thank you for contributing to LLM4Free!
