#!/usr/bin/env python3
"""
Real live TTS provider testing script.
Tests all TTS providers and reports which interfaces work and which don't.
"""

import os
import sys
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# Ensure we can import from the project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm4free.TTS import (
    TTSAI,
    XLNKTTS,
    BaseTTSProvider,
    DeepgramTTS,
    ElevenlabsTTS,
    KittenTTS,
    LuxTTS,
    MurfAITTS,
    OpenAIFMTTS,
    ParlerTTS,
    PocketTTS,
    QwenTTS,
    SherpaTTS,
    StreamElements,
    TTSOpenTTS,
)

TEST_TEXT = "Hello, this is a test of the text to speech system."
SHORT_TEXT = "Test successful."
AUDIO_MIN_SIZE = 100  # Bytes - real audio should be larger than this


def check_audio_file(path: str) -> tuple[bool, int, str]:
    """Check if audio file exists and has actual content."""
    if not path or not isinstance(path, str):
        return False, 0, "No path returned"
    p = Path(path)
    if not p.exists():
        return False, 0, f"File does not exist: {path}"
    size = p.stat().st_size
    if size < AUDIO_MIN_SIZE:
        return False, size, f"File too small ({size} bytes)"
    return True, size, "OK"


def test_provider(provider_name: str, provider_cls, init_kwargs: dict = None) -> dict:
    """Test a single TTS provider."""
    init_kwargs = init_kwargs or {}
    result = {
        "provider": provider_name,
        "status": "FAIL",
        "error": None,
        "duration_sec": 0,
        "audio_path": None,
        "audio_size_bytes": 0,
        "details": "",
        "interface": "create_speech",
    }

    provider = None
    try:
        provider = provider_cls(**init_kwargs)
    except Exception as e:
        result["error"] = f"Init failed: {e}"
        result["details"] = traceback.format_exc()
        return result

    # Determine which text and method to use
    text = SHORT_TEXT
    kwargs = {}

    # Provider-specific configurations for the OpenAI-compatible interface
    if provider_name == "ElevenlabsTTS":
        text = TEST_TEXT
        kwargs = {"verbose": False}
        # If no API key, we expect auth failure
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key and getattr(provider, "api_key", None) is None:
            result["error"] = "No API key provided (ElevenLabs requires auth)"
            result["status"] = "SKIP"
            result["details"] = "Set ELEVENLABS_API_KEY env var to test"
            return result
    elif provider_name == "DeepgramTTS":
        text = TEST_TEXT
        kwargs = {"voice": "thalia", "verbose": False}
        result["interface"] = "create_speech"
    elif provider_name == "KittenTTS":
        text = TEST_TEXT
        kwargs = {"voice": "Jasper", "model": "micro", "verbose": False}
        result["interface"] = "tts (create_speech broken)"
    elif provider_name == "ParlerTTS":
        text = SHORT_TEXT
        kwargs = {"verbose": False}
        result["interface"] = "create_speech"
    elif provider_name == "QwenTTS":
        text = SHORT_TEXT
        kwargs = {"voice": "cherry", "response_format": "wav", "verbose": False}
        result["interface"] = "create_speech"
    elif provider_name == "SherpaTTS":
        text = SHORT_TEXT
        kwargs = {"verbose": False}
        result["interface"] = "tts (create_speech broken)"
    elif provider_name == "OpenAIFMTTS":
        text = SHORT_TEXT
        kwargs = {"voice": "coral", "model": "gpt-4o-mini-tts", "verbose": False}
        result["interface"] = "create_speech"
    elif provider_name == "TTSAI":
        text = SHORT_TEXT
        kwargs = {"voice": "en_GB-alan-medium", "verbose": False}
        result["interface"] = "create_speech"
    elif provider_name == "StreamElements":
        text = SHORT_TEXT
        kwargs = {"voice": "Emma", "verbose": False}
        result["interface"] = "create_speech"
    elif provider_name == "MurfAITTS":
        text = SHORT_TEXT
        kwargs = {"voice": "Hazel", "response_format": "mp3", "verbose": False}
        result["interface"] = "create_speech"
    elif provider_name == "LuxTTS":
        text = SHORT_TEXT
        kwargs = {"voice": "default", "verbose": False}
        result["interface"] = "tts (create_speech broken)"
    elif provider_name == "PocketTTS":
        text = SHORT_TEXT
        kwargs = {"voice": "alba", "response_format": "wav", "verbose": False}
        result["interface"] = "create_speech"
    elif provider_name == "XLNKTTS":
        text = SHORT_TEXT
        kwargs = {"voice": "alba", "verbose": False}
        result["interface"] = "create_speech"
    elif provider_name == "TTSOpenTTS":
        text = SHORT_TEXT
        kwargs = {"voice": "onyx", "response_format": "mp3", "verbose": False}
        result["interface"] = "create_speech"

    # Helper to actually run and check audio
    def _run(provider_obj, call_text, call_kwargs) -> dict:
        start = time.time()
        try:
            if hasattr(provider_obj, "create_speech"):
                audio_path = provider_obj.create_speech(input_text=call_text, **call_kwargs)
                used_interface = "create_speech"
            else:
                audio_path = provider_obj.tts(text=call_text, **call_kwargs)
                used_interface = "tts"

            duration = time.time() - start
            ok, size, details = check_audio_file(audio_path)
            res = {
                "status": "PASS" if ok else "FAIL",
                "error": None if ok else f"Invalid audio file: {details}",
                "duration_sec": round(duration, 2),
                "audio_path": audio_path,
                "audio_size_bytes": size,
                "details": f"Audio generated ({size} bytes, {duration:.1f}s)" if ok else details,
                "interface": used_interface,
            }
            return res
        except Exception as e:
            duration = time.time() - start
            return {
                "status": "FAIL",
                "error": str(e),
                "duration_sec": round(duration, 2),
                "audio_path": None,
                "audio_size_bytes": 0,
                "details": traceback.format_exc(),
                "interface": "unknown",
            }

    # Try the primary interface first
    primary_result = _run(provider, text, kwargs)

    # For known broken interfaces, try tts() directly as fallback
    if primary_result["status"] == "FAIL" and provider_name in {
        "LuxTTS", "KittenTTS", "SherpaTTS", "TTSAI"
    }:
        fallback_kwargs = {}
        if provider_name == "LuxTTS":
            fallback_kwargs = {"voice": "default", "verbose": False}
        elif provider_name == "KittenTTS":
            fallback_kwargs = {"voice": "Jasper", "model": "micro", "verbose": False}
        elif provider_name == "SherpaTTS":
            fallback_kwargs = {"verbose": False}
        elif provider_name == "TTSAI":
            fallback_kwargs = {"voice": "en_GB-alan-medium", "verbose": False}

        fallback_result = _run(provider, text, fallback_kwargs)
        if fallback_result["status"] == "PASS":
            fallback_result["interface"] = "tts() (fallback)"
            result.update(fallback_result)
            result["details"] = f"create_speech FAILED; tts() fallback PASSED ({fallback_result['audio_size_bytes']} bytes, {fallback_result['duration_sec']}s)"
            return result
        else:
            # Both failed - report primary failure but mention fallback attempt
            if "unexpected keyword argument" in primary_result.get("error", "") or \
               "not supported. Available voices" in primary_result.get("error", "") or \
               "got an unexpected keyword argument" in primary_result.get("error", ""):
                result["details"] = f"Interface bug: {primary_result['error'][:100]}; tts() fallback also failed: {fallback_result['error'][:100]}"
            else:
                result["details"] = f"{primary_result['error'][:200]}"
            result.update(primary_result)
            return result

    result.update(primary_result)
    return result


def main():
    providers = [
        ("DeepgramTTS", DeepgramTTS, {}),
        ("ElevenlabsTTS", ElevenlabsTTS, {}),
        ("KittenTTS", KittenTTS, {"timeout": 120}),
        ("LuxTTS", LuxTTS, {"timeout": 120}),
        ("MurfAITTS", MurfAITTS, {}),
        ("OpenAIFMTTS", OpenAIFMTTS, {}),
        ("ParlerTTS", ParlerTTS, {"timeout": 120}),
        ("PocketTTS", PocketTTS, {"timeout": 120}),
        ("QwenTTS", QwenTTS, {}),
        ("SherpaTTS", SherpaTTS, {}),
        ("StreamElements", StreamElements, {}),
        ("TTSAI", TTSAI, {}),
        ("TTSOpenTTS", TTSOpenTTS, {}),
        ("XLNKTTS", XLNKTTS, {"timeout": 120}),
    ]

    print("=" * 90)
    print("TTS Provider Live Testing")
    print("=" * 90)
    print(f"Testing {len(providers)} providers...\n")

    results = []
    max_workers = 2

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_provider = {}
        for name, cls, kwargs in providers:
            future = executor.submit(test_provider, name, cls, kwargs)
            future_to_provider[future] = name

        for future in as_completed(future_to_provider):
            name = future_to_provider[future]
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                results.append({
                    "provider": name,
                    "status": "FAIL",
                    "error": f"Test harness error: {e}",
                    "duration_sec": 0,
                    "audio_path": None,
                    "audio_size_bytes": 0,
                    "details": traceback.format_exc(),
                    "interface": "unknown",
                })

    # Sort results alphabetically for clean output
    results.sort(key=lambda x: x["provider"])

    # Print summary table
    print("\n" + "=" * 90)
    print(f"{'PROVIDER':<25} {'STATUS':<6} {'TIME':>6}  {'SIZE':>8}  {'INTERFACE':<30} ERROR")
    print("-" * 90)
    for res in results:
        status = res["status"]
        error_msg = (res["error"] or "")[:55]
        if status == "SKIP":
            error_msg = f"SKIP: {error_msg[:45]}"
        print(f"{res['provider']:<25} {status:<6} {res['duration_sec']:>5.1f}s  {res['audio_size_bytes']:>7,}  {res.get('interface',''):<30} {error_msg}")

    print("=" * 90)

    # Detailed failures
    failures = [r for r in results if r["status"] == "FAIL"]
    if failures:
        print("\n--- FAILED PROVIDERS DETAILS ---\n")
        for res in failures:
            print(f"[{res['provider']}]: {res['error']}")
            print("-" * 40)

    # Summary counts
    passed = sum(1 for r in results if r["status"] == "PASS")
    skipped = sum(1 for r in results if r["status"] == "SKIP")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(f"\nSummary: {passed} PASS, {skipped} SKIP, {failed} FAIL out of {len(results)} providers")

    # Print which providers work and which don't
    print("\n--- WORKING PROVIDERS ---")
    for res in results:
        if res["status"] == "PASS":
            print(f"  [OK] {res['provider']} ({res['audio_size_bytes']} bytes, {res['duration_sec']}s) via {res.get('interface', 'unknown')}")

    print("\n--- BROKEN / UNAVAILABLE PROVIDERS ---")
    for res in results:
        if res["status"] != "PASS":
            reason = "no API key" if res["status"] == "SKIP" else res.get("error", "unknown")
            print(f"  [!!] {res['provider']}: {reason[:100]}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
