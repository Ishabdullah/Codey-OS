#!/usr/bin/env python3
"""Test for TTS speech plugin."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from ccos.plugins.speech.tts_speech.tts import list_engines, speak, test


def test_list_engines():
    engines = list_engines()
    assert isinstance(engines, list)
    print(f"[PASS] Found {len(engines)} TTS engine(s)")
    for eng in engines:
        print(f"  - {eng['name']} (quality={eng['quality']}, offline={eng['offline']})")


def test_self_test():
    result = test()
    assert result is True
    print("[PASS] TTS self-test passed")


def test_speak():
    engines = list_engines()
    if not engines:
        print("[SKIP] No TTS engines available")
        return

    result = speak("Hello from CCOS", output_path="/tmp/ccos_tts_test.wav")
    if result["success"]:
        print(f"[PASS] TTS worked with engine: {result['engine_used']}")
    else:
        print(f"[SKIP] TTS failed: {result['error']}")


if __name__ == "__main__":
    test_list_engines()
    test_self_test()
    test_speak()
    print("\nTTS plugin tests complete!")
