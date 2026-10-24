# LitAgent: The Advanced User Agent Generator
> Last updated: 2025-12-19
> Maintained by [LLM4Free](https://github.com/OEvortex/LLM4Free)

**🚀 Powerful, modern user agent generator to keep your requests fresh and undetectable!**

---

## 📋 Overview

LitAgent is a high-performance, enterprise-grade user agent generation and management library. Built for the modern web, it provides a comprehensive suite of tools for simulating realistic browser signatures, rotating IP addresses, and managing proxy pools. Whether you're building a web crawler, an automation script, or a security tool, LitAgent ensures your traffic looks like legitimate user activity.

<details open>
<summary><b>🌟 Why LitAgent is the Ultimate Choice</b></summary>

- **⚡ Lightning-Fast**: Designed for high-concurrency environments with minimal overhead.
- **🛡️ Anti-Fingerprinting**: Generates complete, consistent browser fingerprints to bypass detection.
- **📱 Device Diversity**: Supports Desktop, Mobile, Tablet, Smart TV, Gaming Consoles, and Wearables.
- **🌐 Browser Broadness**: Pre-configured with the latest signatures for Chrome, Firefox, Safari, Edge, Opera, Brave, and Vivaldi.
- **🔄 Smart Rotation**: Built-in mechanisms for IP and proxy rotation.
- **🕰️ Auto-Refresh**: Keep your agent pool fresh with automatic background updates.
- **🧵 Optional Thread Safety**: Enable a shared `RLock` with `LitAgent(thread_safe=True)` when using one instance across threads.
- **📊 Usage Analytics**: Track your requests and monitor browser/device distribution.

</details>

## 📑 Table of Contents

- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Features](#-features)
- [Advanced Usage](#-advanced-usage)
- [Fingerprinting](#-fingerprinting)
- [API Reference](#-api-reference)
- [Dependencies](#-dependencies)
- [Supported Versions](#-supported-versions)
- [Contributing](#-contributing)
- [License](#-license)

## 📦 Installation

LitAgent is included with LLM4Free:

```bash
pip install llm4free
```

Or install the latest version from GitHub:

```bash
pip install git+https://github.com/OEvortex/LLM4Free.git
```

## 🚀 Quick Start

```python
from llm4free import LitAgent

# Create a LitAgent instance
agent = LitAgent()          # thread_safe=False by default
# agent = LitAgent(thread_safe=True)  # serialize shared-state updates

# Get a random user agent
ua = agent.random()
print(f"Random Agent: {ua}")
```

## ✨ Features

### 🌐 Browser-Specific Agents
Get the latest user agent for any major browser:

```python
chrome_ua = agent.chrome()      # Latest Chrome
firefox_ua = agent.firefox()    # Latest Firefox
safari_ua = agent.safari()      # Latest Safari
edge_ua = agent.edge()          # Latest Edge
opera_ua = agent.opera()        # Latest Opera
brave_ua = agent.brave()        # Latest Brave
vivaldi_ua = agent.vivaldi()    # Latest Vivaldi
```

### 📱 Device-Specific Agents
Simulate different hardware platforms:

```python
mobile_ua = agent.mobile()      # Mobile phone
desktop_ua = agent.desktop()    # Desktop/Laptop
tablet_ua = agent.tablet()      # Tablet device
tv_ua = agent.smart_tv()        # Smart TV
console_ua = agent.gaming()     # Gaming console
wearable_ua = agent.wearable()  # Wearables (Watch, etc.)
```

### 🪟 OS-Specific Agents
Target specific operating systems:

```python
win_ua = agent.windows()    # Windows
mac_ua = agent.macos()      # macOS
linux_ua = agent.linux()    # Linux
android_ua = agent.android()# Android
ios_ua = agent.ios()        # iOS
```

### 🛠️ Custom Agent Generation
Create precise signatures with custom parameters:

```python
custom_ua = agent.custom(
    browser="chrome",
    version="131.0",
    os="windows",
    os_version="11.0",
    device_type="desktop"
)
```

## 🔬 Advanced Usage

### 🛡️ Browser Fingerprinting
Generate a complete set of headers to simulate a real browser:

```python
fingerprint = agent.generate_fingerprint(browser="chrome")
print(fingerprint['user_agent'])
print(fingerprint['sec_ch_ua'])
print(fingerprint['platform'])
```

### 🔄 IP & Proxy Rotation
Manage your network identity:

```python
# IP Rotation (simulated for headers)
ip = agent.rotate_ip()

# Proxy Pool Management
agent.set_proxy_pool(["http://proxy1:8080", "http://proxy2:8080"])
proxy = agent.rotate_proxy()
```

### 📊 Usage Statistics
Monitor your agent generation patterns:

```python
stats = agent.get_stats()
print(f"Total Served: {stats['requests_served']}")
print(f"Top Browser: {stats['top_browser']}")
print(f"Avoidance Rate: {stats['avoidance_rate']}%")

# Export stats for reporting
agent.export_stats('usage_report.json')
```

### 🕰️ Automatic Refresh
Keep the internal pool updated automatically:

```python
# Refresh every 15 minutes in the background
agent.auto_refresh(interval_minutes=15)
```

## 📚 API Reference

### `LitAgent` Class

| Method | Description |
|--------|-------------|
| `LitAgent(thread_safe=False)` | Creates an agent pool and simulated IP pool; set `thread_safe=True` to enable locking. |
| `random()` | Returns a random user agent from the pool. |
| `browser(name)` | Returns an agent for the specified browser name. |
| `mobile() / desktop() / tablet()` | Returns an agent for the specified device type. |
| `chrome() / firefox() / safari() / ...` | Shortcut methods for specific browsers. |
| `windows() / macos() / linux() / ...` | Shortcut methods for specific OS. |
| `custom(...)` | Generates a custom user agent based on parameters. |
| `generate_fingerprint(browser)` | Generates a full header fingerprint dictionary. |
| `refresh()` | Manually re-generates the internal agent pool. |
| `auto_refresh(interval)` | Starts background refreshing of agents. |
| `rotate_ip()` | Rotates through the internal simulated IP pool. |
| `set_proxy_pool(list)` | Sets the pool of proxies to rotate through. |
| `rotate_proxy()` | Returns the next proxy from the pool. |
| `get_stats()` | Returns usage statistics and analytics. |
| `validate_agent(ua)` | Performs basic validation on a UA string. |

## 🔧 Dependencies

- **Standard Library Only**: LitAgent runs on pure Python with zero external dependencies for core functionality.
- **Optional**: `json` for stats export (included in stdlib).

## 🌈 Supported Versions

- **Python**: 3.10+ (same as the rest of the package)
- **OS**: Windows, macOS, Linux, Android, iOS (the generated UA strings cover these platforms)

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository.
2. Create your feature branch (`git checkout -b feature/amazing-feature`).
3. Commit your changes (`git commit -m 'Add some amazing feature'`).
4. Push to the branch (`git push origin feature/amazing-feature`).
5. Open a Pull Request.

---

<div align="center">
  <p>Made with ❤️ by the LLM4Free team</p>
  <p>
    <a href="https://github.com/OEvortex/LLM4Free">GitHub</a> •
    <a href="https://github.com/OEvortex/LLM4Free/wiki">Documentation</a> •
    <a href="https://github.com/OEvortex/LLM4Free/issues">Report Bug</a>
  </p>
</div>
