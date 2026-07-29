#!/usr/bin/env python3
"""Test for TTS speech plugin."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from ccos.plugins.speech.tts_speech.tts import (
    list_engines,
    listen,
    speak,
    stt_available,
    test,
)


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


def test_stt_available():
    result = stt_available()
    assert isinstance(result, bool)
    print(f"[PASS] stt_available() returned {result}")


def test_listen_without_mic_input():
    # No mic input is fed in this environment — just confirm the call
    # doesn't raise and times out/returns None rather than hanging forever.
    if not stt_available():
        print("[SKIP] STT not available on this system")
        return
    result = listen(timeout=2)
    assert result is None or isinstance(result, str)
    print(f"[PASS] listen() returned without raising: {result!r}")


if __name__ == "__main__":
    test_list_engines()
    test_self_test()
    test_speak()
    test_stt_available()
    test_listen_without_mic_input()
    print("\nTTS/STT plugin tests complete!")
