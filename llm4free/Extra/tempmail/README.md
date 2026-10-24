<div align="center">
  <a href="https://github.com/OEvortex/llm4free">
    <img src="https://img.shields.io/badge/LLM4Free-TempMail%20Toolkit-blue?style=for-the-badge&logo=maildotru&logoColor=white" alt="LLM4Free TempMail Toolkit">
  </a>

  <h1>📧 TempMail</h1>

  <p><strong>Temporary email generation and management</strong></p>

  <p>
    Create disposable email addresses, read messages, and automate email verification workflows with
    multiple providers and both synchronous and asynchronous APIs.
  </p>

  <p>
    <a href="https://pypi.org/project/llm4free/"><img src="https://img.shields.io/pypi/v/llm4free.svg?style=flat-square&logo=pypi&label=PyPI" alt="PyPI Version"></a>
    <a href="#"><img src="https://img.shields.io/badge/No%20API%20Key-Required-success?style=flat-square" alt="No API Key Required"></a>
    <a href="#"><img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python" alt="Python Version"></a>
  </p>
</div>

> [!NOTE]
> TempMail provides disposable email addresses for testing, verification, and privacy protection.
> It supports Mail.TM, TempMail.io, and Emailnator.

## ✨ Features

- **Multiple providers** — Mail.TM, TempMail.io, and Emailnator
- **Sync and async APIs** — Mail.TM and TempMail.io have both variants
- **Consistent interface** — `create_account()`/`create_email()`, `get_messages()`, `delete_account()`/`delete_email()`
- **Helpers** — `get_random_email()`, `get_provider()`, and async helper utilities
- **No API keys** — all providers are free/anonymous

## 🚀 Installation

```bash
pip install -U llm4free
```

## 🖥️ Usage

### Basic synchronous example

```python
from llm4free.Extra.tempmail import get_random_email

email, provider = get_random_email("mailtm")
print(f"Temporary email: {email}")

try:
    messages = provider.get_messages()
    for message in messages:
        print(message.get("subject"), "-", message.get("from"))
finally:
    provider.delete_account()
```

`create_account()` returns a `bool` and stores the address on the provider
(`provider.email`, plus `provider.account_id`/`provider.token` for Mail.TM).
It does **not** return an account dictionary.

### Choosing a specific provider

```python
from llm4free.Extra.tempmail import get_provider

provider = get_provider("mailtm")          # synchronous
if provider.create_account():
    print(provider.email)

    # Mail.TM exposes account_id and token after creation
    print(provider.account_id, provider.token)

    messages = provider.get_messages()
    provider.delete_account()
```

```python
from llm4free.Extra.tempmail import TempMailIO

provider = TempMailIO()
if provider.create_account():
    print(provider.email, provider.token)
    print(provider.get_messages())
    provider.delete_account()
```

### Asynchronous API

Async providers must be initialized. `create_email()` returns
`(email, token)`; `delete_email()` takes no arguments and deletes the
account currently held by the provider.

```python
import asyncio
from llm4free.Extra.tempmail import get_provider

async def main():
    provider = get_provider("mailtm", async_provider=True)
    await provider.initialize()

    try:
        email, token = await provider.create_email()
        print(f"Temporary email: {email}")

        messages = await provider.get_messages()
        for message in messages:
            print(message.get("subject"), "-", message.get("from"))
    finally:
        await provider.delete_email()
        await provider.close()

asyncio.run(main())
```

`TempMailIOAsync` supports the same flow and additionally accepts
`alias`/`domain` in `create_email(alias=None, domain=None)`.

### Async helper utilities

The helpers in `llm4free.Extra.tempmail.async_utils` wrap `TempMailIOAsync`:

```python
import asyncio
from llm4free.Extra.tempmail.async_utils import get_temp_email, wait_for_message

async def main():
    email, helper = await get_temp_email()
    print(f"Temporary email: {email}")

    try:
        message = await wait_for_message(helper, timeout=60, check_interval=5)
        if message:
            print(message.get("subject"), "-", message.get("from"))
    finally:
        await helper.delete()

asyncio.run(main())
```

### Command-line interface

> [!WARNING]
> The module CLI at `python -m llm4free.Extra.tempmail.cli` is currently
> non-functional: it imports the removed `llm4free.swiftcli` module. The
> import is wrapped in a no-op fallback, so commands exit silently. Use the
> Python API above instead until the CLI is ported.

## 📚 API Reference

### Base classes (`llm4free.Extra.tempmail.base`)

| Class | Interface |
|-------|-----------|
| `TempMailProvider` | `create_account() -> bool`, `get_messages() -> list`, `check_new_messages() -> list`, `delete_account() -> bool`, `get_account_info() -> dict`, `get_token() -> str` |
| `AsyncTempMailProvider` | `initialize()`, `close()`, `create_email(alias=None, domain=None) -> (email, token)`, `get_messages() -> list`, `delete_email() -> bool` |

### Provider implementations

| Provider | Sync class | Async class |
|----------|-----------|-------------|
| Mail.TM | `MailTM` | `MailTMAsync` |
| TempMail.io | `TempMailIO` | `TempMailIOAsync` |
| Emailnator | `EmailnatorProvider` | — (raises `NotImplementedError`) |

### Factory functions

- `get_provider(provider_name="mailtm", async_provider=False)` — accepts
  `"mailtm"`, `"tempmailio"`, or `"emailnator"`.
- `get_random_email(provider_name="mailtm") -> (email, provider)` — creates a
  synchronous account and returns the address plus provider instance.
- `get_disposable_email() -> (email, provider)` — alias for
  `get_random_email()`.

### Async utilities (`llm4free.Extra.tempmail.async_utils`)

- `AsyncTempMailHelper` — `create(alias=None, domain=None)`,
  `get_messages()`, `delete()`, `close()`
- `get_temp_email(alias=None, domain=None) -> (email, helper)`
- `wait_for_message(helper, timeout=60, check_interval=5) -> dict | None`

## 🔌 Provider Integration

1. Subclass `TempMailProvider` (sync) and/or `AsyncTempMailProvider` (async)
2. Implement the abstract methods listed above
3. Register the provider name in `get_provider()` in `base.py`
4. Export the classes from `llm4free/Extra/tempmail/__init__.py`
5. Add tests and update this README

## 🛠️ Implementation Details

- Mail.TM message bodies are parsed with `llm4free.scout.Scout` rather than
  BeautifulSoup.
- Mail.TM and TempMail.io both have synchronous and asynchronous variants;
  Emailnator is synchronous only.
- `get_random_email()` always returns a synchronous provider.

<div align="center">
  <div>
    <a href="https://t.me/OEvortexAI"><img alt="Telegram Group" src="https://img.shields.io/badge/Telegram%20Group-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white"></a>
    <a href="https://buymeacoffee.com/oevortex"><img alt="Buy Me A Coffee" src="https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black"></a>
  </div>
  <p>📧 TempMail - Part of the LLM4Free Toolkit</p>
  <a href="https://github.com/OEvortex/llm4free">Back to Main LLM4Free Project</a>
</div>
