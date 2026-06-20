"""
TTS Speech Plugin — Text-to-speech output.

Tries multiple engines in order:
1. Piper (offline, high quality)
2. espeak (offline, lightweight)
3. Termux:API tts-speak (Android/Termux)
4. Python pyttsx3 (cross-platform fallback)
"""

import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional


def list_engines() -> List[Dict[str, Any]]:
    """List available TTS engines on this system."""
    engines = []

    # Piper
    if shutil.which("piper"):
        engines.append({"name": "piper", "available": True, "quality": "high", "offline": True})

    # espeak
    if shutil.which("espeak") or shutil.which("espeak-ng"):
        engines.append({"name": "espeak", "available": True, "quality": "medium", "offline": True})

    # Termux API
    if shutil.which("termux-tts-speak"):
        engines.append({"name": "termux", "available": True, "quality": "medium", "offline": False})

    # pyttsx3
    try:
        import pyttsx3
        engines.append({"name": "pyttsx3", "available": True, "quality": "medium", "offline": True})
    except ImportError:
        pass

    return engines


def speak(
    text: str,
    engine: str = None,
    rate: int = 150,
    voice: str = None,
    output_path: str = None,
) -> Dict[str, Any]:
    """
    Speak text using the best available TTS engine.

    Args:
        text: Text to speak
        engine: Specific engine to use (auto-detect if None)
        rate: Speech rate (words per minute)
        voice: Voice name/path (engine-specific)
        output_path: Save audio to file instead of playing

    Returns:
        dict with success, engine_used, error
    """
    if not text or not text.strip():
        return {"success": False, "error": "Empty text", "engine_used": None}

    engines = list_engines()
    if not engines:
        return {"success": False, "error": "No TTS engines available", "engine_used": None}

    # Auto-select engine
    if engine:
        selected = next((e for e in engines if e["name"] == engine), None)
        if not selected:
            return {"success": False, "error": f"Engine '{engine}' not available", "engine_used": None}
        engine_name = engine
    else:
        # Prefer: piper > espeak > termux > pyttsx3
        priority = ["piper", "espeak", "termux", "pyttsx3"]
        engine_name = None
        for p in priority:
            if any(e["name"] == p for e in engines):
                engine_name = p
                break
        if not engine_name:
            engine_name = engines[0]["name"]

    # Execute TTS
    try:
        if engine_name == "piper":
            return _speak_piper(text, voice, output_path)
        elif engine_name == "espeak":
            return _speak_espeak(text, rate, voice, output_path)
        elif engine_name == "termux":
            return _speak_termux(text, rate)
        elif engine_name == "pyttsx3":
            return _speak_pyttsx3(text, rate, voice)
        else:
            return {"success": False, "error": f"Unknown engine: {engine_name}", "engine_used": None}
    except Exception as e:
        return {"success": False, "error": str(e), "engine_used": engine_name}


def _speak_piper(text: str, voice: str = None, output_path: str = None) -> Dict[str, Any]:
    cmd = ["piper"]
    if voice:
        cmd.extend(["--model", voice])
    if output_path:
        cmd.extend(["--output_file", output_path])

    result = subprocess.run(
        cmd,
        input=text,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0:
        return {"success": True, "engine_used": "piper", "error": None, "output": output_path}
    return {"success": False, "engine_used": "piper", "error": result.stderr[:200]}


def _speak_espeak(text: str, rate: int = 150, voice: str = None, output_path: str = None) -> Dict[str, Any]:
    cmd = ["espeak"]
    if shutil.which("espeak-ng"):
        cmd = ["espeak-ng"]
    cmd.extend(["-s", str(rate)])
    if voice:
        cmd.extend(["-v", voice])
    if output_path:
        cmd.extend(["-w", output_path])
    cmd.append(text)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        return {"success": True, "engine_used": "espeak", "error": None, "output": output_path}
    return {"success": False, "engine_used": "espeak", "error": result.stderr[:200]}


def _speak_termux(text: str, rate: int = 150) -> Dict[str, Any]:
    result = subprocess.run(
        ["termux-tts-speak", "-r", str(rate), text],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        return {"success": True, "engine_used": "termux", "error": None}
    return {"success": False, "engine_used": "termux", "error": result.stderr[:200]}


def _speak_pyttsx3(text: str, rate: int = 150, voice: str = None) -> Dict[str, Any]:
    import pyttsx3
    engine = pyttsx3.init()
    engine.setProperty("rate", rate)
    if voice:
        engine.setProperty("voice", voice)
    engine.say(text)
    engine.runAndWait()
    return {"success": True, "engine_used": "pyttsx3", "error": None}


def install():
    return len(list_engines()) > 0


def uninstall():
    return True


def test():
    engines = list_engines()
    return isinstance(engines, list)
