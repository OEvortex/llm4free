# Inferno LLM Integration
> Last updated: 2025-11-16
> Maintained by [LLM4Free](https://github.com/OEvortex/LLM4Free)

Inferno is a local LLM server designed to run Large Language Models (LLMs) on your hardware, offering an intuitive Command Line Interface (CLI) and an OpenAI/Ollama-compatible API. It supports various cutting-edge models and provides features for model management, quantization, and GPU acceleration.

## Installation

To install Inferno, you must first install `llama-cpp-python` with the correct hardware acceleration backend for your system. This is a critical prerequisite for optimal performance.

### 1. Install `llama-cpp-python` with Hardware Acceleration

Choose one of the following commands based on your hardware:

- **NVIDIA GPU (CUDA):** `CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --force-reinstall --upgrade --no-cache-dir`
- **Apple Silicon GPU (Metal):** `CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python --force-reinstall --upgrade --no-cache-dir`
- **AMD GPU (ROCm):** `CMAKE_ARGS="-DGGML_HIPBLAS=on" pip install llama-cpp-python --force-reinstall --upgrade --no-cache-dir`
- **CPU Only (OpenBLAS):** `CMAKE_ARGS="-DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS" pip install llama-cpp-python --force-reinstall --upgrade --no-cache-dir`
- Other backends like Vulkan and SYCL are also supported.

It is recommended to use a virtual environment and ensure Python 3.9+ and necessary build tools are installed.

### 2. Install Inferno

After `llama-cpp-python` is installed, you can install Inferno from PyPI:

```bash
pip install inferno-llm
```

Alternatively, you can install from source for development.

## Features

Inferno provides a comprehensive set of features for local LLM deployment:

- **Bleeding-Edge Model Support:** Runs models like Llama 3.3, DeepSeek-R1, Phi-4, Gemma 3, Mistral Small 3.1
- **Hugging Face Integration:** Allows downloading models with interactive file selection and direct `repo_id:filename` targeting
- **Dual API Compatibility:** Serves models through both OpenAI and Ollama compatible API endpoints
- **Native Python Client:** Includes an OpenAI-compatible Python client for seamless integration into Python projects
- **Interactive CLI:** Command-line interface for downloading, managing, quantizing, and chatting with models
- **Blazing-Fast Inference:** GPU acceleration (CUDA, Metal, ROCm, Vulkan, SYCL) and CPU acceleration via OpenBLAS
- **Advanced Quantization:** Converts models between various GGUF quantization levels with interactive comparison and RAM estimates
- **Smart Model Management:** Lists, shows details, copies, removes, and displays running models with RAM requirement estimates

## CLI Commands

Inferno's CLI provides various commands for interacting with models:

| Command | Description | Example |
| :------------------------- | :--------------------------------------------------- | :-------------------------------------------------------- |
| `pull <model_id_or_path>` | Download models (GGUF) from Hugging Face | `inferno pull meta-llama/Llama-3.3-8B-Instruct-GGUF` |
| `list` or `ls` | List locally downloaded models & RAM estimates | `inferno list` |
| `serve <model_name_or_id>` | Start API server (OpenAI & Ollama compatible) | `inferno serve MyLlama3 --port 8080` |
| `run <model_name_or_id>` | Start interactive chat session in the terminal | `inferno run MyLlama3` |
| `remove <model_name>` | Delete a downloaded model | `inferno remove MyLlama3` |
| `quantize <input> [out]` | Convert models (HF or GGUF) to different quant levels | `inferno quantize hf:Qwen/Qwen3-0.6B Qwen3-0.6B-Q4_K_M` |
| `show <model_name>` | Display detailed model info (metadata, path, etc.) | `inferno show MyLlama3` |
| `ps` | Show running Inferno server processes/models | `inferno ps` |

The `inferno run` command initiates an interactive chat session where you can converse with a loaded model. Inside the chat, special commands like `/help`, `/bye`, `/set system <prompt>`, and `/set context <size>` are available to manage the session and model parameters.

## Hardware Requirements

Hardware requirements are crucial for optimal performance:

- **RAM:** This is the most critical factor.
  - ~2-4 GB RAM for 1-3B parameter models
  - **8 GB+ RAM** recommended for 7-8B models
  - **16 GB+ RAM** recommended for 13B models
  - **32 GB+ RAM** needed for ~30B models
  - **64 GB+ RAM** needed for ~70B models
- **CPU:** A modern multi-core CPU is recommended, with performance scaling with core count and speed
- **GPU (Highly Recommended):** NVIDIA, AMD, or Apple Silicon GPUs significantly accelerate inference. VRAM requirements depend on model size and layers offloaded
- **Disk Space:** Sufficient space for downloaded GGUF models, which can range from ~1GB to 100GB+

Inferno provides RAM usage estimates for different quantization types to help users manage resources.

## Calling Inferno from Python

Inferno is a separate project and is **not bundled with LLM4Free**. LLM4Free has no `Inferno` provider in `llm4free/llm/`, and its OpenAI-compatible providers use fixed endpoints, so Inferno-hosted models cannot be selected through `llm4free.Client`.

Call Inferno directly over its OpenAI-compatible endpoint instead:

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "your-local-model",
        "messages": [{"role": "user", "content": "Hello"}],
    },
    timeout=120,
)
response.raise_for_status()
print(response.json()["choices"][0]["message"]["content"])
```

You can also use any OpenAI-compatible SDK by pointing its `base_url` at `http://localhost:8000/v1`.

Inferno's API compatibility makes it usable with tools and frameworks that accept a custom OpenAI base URL, such as the official OpenAI SDK, LangChain, and LlamaIndex. Because the model runs locally, no LLM4Free provider or `LLM4FREE_DEFAULT_PROVIDER` setting is involved.

For more information, visit the [Inferno GitHub repository](https://github.com/HelpingAI/inferno) or [PyPI package page](https://pypi.org/project/inferno-llm/).