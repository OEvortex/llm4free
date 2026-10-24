# GGUF Converter (Removed)

> Last updated: 2026-10-24

The former `llm4free.Extra.gguf` converter is **no longer part of the package**. It was deleted in commit `e86860f` ("Remove unfinished and experimental LLM providers..."), so commands such as:

```bash
python -m llm4free.Extra.gguf convert -m "organization/model-name"
```

will fail with `No module named llm4free.Extra.gguf`.

This page previously documented that removed module's CLI options, output types, quantization methods, and upload workflow. None of those options are available in the current package.

## What to use instead

For Hugging Face → GGUF conversion, quantization, and optional Hugging Face upload, use the upstream tools directly:

- [`llama.cpp`](https://github.com/ggerganov/llama.cpp) — `convert_hf_to_gguf.py` and `llama-quantize`
- [`llama-cpp-python`](https://github.com/abetlen/llama-cpp-python) — Python bindings for running GGUF models (hardware-specific install flags are documented in [inferno.md](inferno.md))

If you need the removed implementation for reference, it still exists in git history:

```bash
git show e86860f^:llm4free/Extra/gguf.py
```

It is not importable from the current release and is not supported.
