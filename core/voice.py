#!/usr/bin/env python3
"""
Voice interface for Codey-OS — TTS and STT via Termux:API.
Phase 1 of the upgrade roadmap (v2.5.1).

Requirements:
  - Termux:API app installed from Play Store / F-Droid
  - termux-api package: pkg install termux-api

TTS: termux-tts-speak [-r rate] [-p pitch] [-e engine] [-l lang] <text>
STT: termux-speech-to-text  → JSON {"text": "...", "error": "Unset"}
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from utils.logger import info, success, warning

# Persist voice settings across sessions
_VOICE_CONFIG_PATH = Path.home() / ".config" / "codeyOS" / "voice_config.json"


class VoiceManager:
    """Manages TTS and STT for Codey-OS via Termux:API."""

    def __init__(self):
        self.enabled: bool = False
        self.tts_rate: float = 1.0  # 0.5 = slow, 2.0 = fast
        self.tts_pitch: float = 1.0
        self.tts_engine: str = ""  # "" = system default
        self.tts_language: str = ""  # "" = system default
        self._tts_available: Optional[bool] = None
        self._stt_available: Optional[bool] = None
        self._speak_proc: Optional[subprocess.Popen] = None
        self._load_config()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load_config(self):
        """Load saved voice settings from disk."""
        try:
            if _VOICE_CONFIG_PATH.exists():
                data = json.loads(_VOICE_CONFIG_PATH.read_text())
                self.enabled = data.get("enabled", False)
                self.tts_rate = float(data.get("tts_rate", 1.0))
                self.tts_pitch = float(data.get("tts_pitch", 1.0))
                self.tts_engine = data.get("tts_engine", "")
                self.tts_language = data.get("tts_language", "")
        except Exception:
            pass  # silently fall back to defaults

    def _save_config(self):
        """Persist voice settings to disk (ACT, audited; best-effort).

        Failure stays non-raising, as before: the setters and turn_on/turn_off
        must not start raising because a config file could not be written.
        """
        from core.action_gateway import ACT, get_action_gateway

        data = {
            "enabled": self.enabled,
            "tts_rate": self.tts_rate,
            "tts_pitch": self.tts_pitch,
            "tts_engine": self.tts_engine,
            "tts_language": self.tts_language,
        }

        def persist():
            try:
                _VOICE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                _VOICE_CONFIG_PATH.write_text(json.dumps(data, indent=2))
            except Exception:
                # Fixed text only: gate_exec audits str(exc), which carries
                # the config path.
                raise RuntimeError("voice config write failed") from None
            return "voice config persisted"

        # Outcome intentionally not acted on. A refused or failed decision is
        # already recorded in the audit ledger by gate_exec, nothing was (or
        # only partially could be) written, and the in-memory settings remain
        # authoritative for this session, so swallowing here is safe and
        # matches the previous silent-failure behavior.
        get_action_gateway().gate_exec(
            authority=ACT,
            action="voice.save_config",
            command="persist voice_config.json",
            confirm_available=False,
            execute=persist,
        )

    # ── Availability ─────────────────────────────────────────────────────────

    def tts_available(self) -> bool:
        if self._tts_available is None:
            self._tts_available = bool(shutil.which("termux-tts-speak"))
        return self._tts_available

    def stt_available(self) -> bool:
        if self._stt_available is None:
            self._stt_available = bool(shutil.which("termux-speech-to-text"))
        return self._stt_available

    # ── Text filtering ───────────────────────────────────────────────────────

    def filter_for_speech(self, text: str) -> str:
        """
        Strip markdown, code blocks, and tool calls so TTS only speaks prose.
        Returns cleaned plain text suitable for speech synthesis.
        """
        # Remove <tool>...</tool> blocks entirely (agent internals)
        text = re.sub(r"<tool>[\s\S]*?</tool>", "", text, flags=re.IGNORECASE)
        # Replace fenced code blocks with a short spoken note
        text = re.sub(r"```[\s\S]*?```", " [code block] ", text)
        # Remove inline code
        text = re.sub(r"`[^`\n]+`", "", text)
        # Strip markdown headers
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # Unwrap bold/italic (keep text, drop markers)
        text = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text)
        text = re.sub(r"__([^_\n]+)__", r"\1", text)
        text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
        text = re.sub(r"_([^_\n]+)_", r"\1", text)
        # Replace URLs with spoken placeholder
        text = re.sub(r"https?://\S+", "[URL]", text)
        # Strip bullet / numbered list markers
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
        # Collapse whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    # ── TTS ─────────────────────────────────────────────────────────────────

    def speak(self, text: str, wait: bool = True) -> bool:
        """
        Speak text using termux-tts-speak.

        Args:
            text: Raw response text (markdown is stripped automatically).
            wait: If True, block until speech finishes. Set False for
                  background/non-blocking use (user can Ctrl+C to interrupt).
        Returns:
            True after successful synchronous speech, or asynchronous launch.
            False on refusal, interruption, or execution failure.
        """
        if not self.tts_available():
            return False

        prose = self.filter_for_speech(text)
        if not prose:
            return False

        # Cap length to avoid multi-minute TTS runs
        if len(prose) > 1200:
            prose = prose[:1200] + "... truncated."

        cmd = ["termux-tts-speak"]
        if self.tts_rate != 1.0:
            cmd += ["-r", str(self.tts_rate)]
        if self.tts_pitch != 1.0:
            cmd += ["-p", str(self.tts_pitch)]
        if self.tts_engine:
            cmd += ["-e", self.tts_engine]
        if self.tts_language:
            cmd += ["-l", self.tts_language]
        cmd.append(prose)

        from core.action_gateway import ACT, get_action_gateway

        interrupted = None

        def execute():
            nonlocal interrupted
            try:
                if wait:
                    proc = subprocess.run(cmd, timeout=180)
                    if proc.returncode != 0:
                        raise RuntimeError("Voice speech exited with nonzero status")
                else:
                    # Launch mediation only. Async overlap/stop ownership is the
                    # separately tracked NEW-972 debt; no new background caller.
                    self._speak_proc = subprocess.Popen(cmd)
            except (KeyboardInterrupt, SystemExit) as exc:
                interrupted = exc
                raise RuntimeError("Voice speech interrupted") from None
            except subprocess.TimeoutExpired:
                raise RuntimeError("Voice speech timed out") from None
            except Exception:
                # Never place speech text, argv or exception output in audit.
                raise RuntimeError("Voice speech execution failed") from None
            return "Voice speech completed" if wait else "Voice speech launched"

        decision = get_action_gateway().gate_exec(
            authority=ACT, action="voice.speak", command="voice.speak",
            confirm_available=False, execute=execute,
        )
        if isinstance(interrupted, SystemExit):
            raise interrupted
        return decision.allowed

    def stop_speaking(self):
        """Stop any in-progress TTS subprocess."""
        if self._speak_proc and self._speak_proc.poll() is None:
            self._speak_proc.terminate()
            try:
                self._speak_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._speak_proc.kill()
        self._speak_proc = None

    # ── STT ─────────────────────────────────────────────────────────────────

    def listen(self, timeout: int = 20, *, confirm=None) -> Optional[str]:
        """Capture one utterance only after this attempt's explicit approval.

        Availability and no-speech checks remain harmless. The real microphone
        subprocess is HIGH_IMPACT and refuses without a human callback.
        """
        if not self.stt_available():
            warning(
                "termux-speech-to-text not found. Install Termux:API app + pkg install termux-api"
            )
            return None

        from core.action_gateway import HIGH_IMPACT, get_action_gateway

        captured = None
        interrupted = None

        def execute():
            nonlocal captured, interrupted
            try:
                info("[Voice] Listening... (speak now, Ctrl+C to cancel)")
                result = subprocess.run(
                    ["termux-speech-to-text"], capture_output=True,
                    text=True, timeout=timeout,
                )
                if result.returncode != 0:
                    raise RuntimeError("Voice recording exited with nonzero status")
                raw = result.stdout.strip()
                if raw:
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        # Existing Termux versions may return plain text.
                        captured = raw
                    else:
                        if not isinstance(data, dict):
                            raise RuntimeError("Invalid voice recording response")
                        text = data.get("text", "")
                        error = data.get("error", "Unset")
                        if not isinstance(text, str) or (error is not None and not isinstance(error, str)):
                            raise RuntimeError("Invalid voice recording response")
                        if error and error.lower() not in ("unset", "none", ""):
                            raise RuntimeError("Voice recording reported an error")
                        captured = text.strip() or None
            except (KeyboardInterrupt, SystemExit) as exc:
                interrupted = exc
                raise RuntimeError("Voice recording interrupted") from None
            except subprocess.TimeoutExpired:
                raise RuntimeError("Voice recording timed out") from None
            except Exception:
                # Transcript, raw output and dynamic errors stay out of audit.
                raise RuntimeError("Voice recording execution failed") from None
            return "Voice recording completed"

        decision = get_action_gateway().gate_exec(
            authority=HIGH_IMPACT, action="voice.listen", command="voice.listen",
            confirm_available=callable(confirm),
            confirm=confirm if callable(confirm) else None, execute=execute,
        )
        if isinstance(interrupted, SystemExit):
            raise interrupted
        if not decision.allowed:
            warning("[Voice] Recording refused or failed.")
            return None
        if captured:
            success(f"[Voice] Heard: {captured}")
        else:
            warning("[Voice] No speech captured.")
        return captured

    # ── Mode control ─────────────────────────────────────────────────────────

    def turn_on(self) -> bool:
        """Enable voice mode. Returns True if at least TTS is available."""
        if not self.tts_available() and not self.stt_available():
            warning("Termux:API tools not found.")
            warning("  1. Install Termux:API app from Play Store or F-Droid")
            warning("  2. Run: pkg install termux-api")
            warning("  3. Grant microphone permission to Termux:API")
            return False
        self.enabled = True
        self._save_config()
        parts = []
        if self.tts_available():
            parts.append("TTS (speak responses)")
        if self.stt_available():
            parts.append("STT (voice input)")
        success(f"Voice mode ON — {' + '.join(parts)}")
        if not self.stt_available():
            info("Tip: Install termux-speech-to-text for voice input too.")
        return True

    def turn_off(self):
        """Disable voice mode."""
        self.stop_speaking()
        self.enabled = False
        self._save_config()
        info("Voice mode OFF.")

    def set_rate(self, rate: float):
        """Set TTS speech rate. Normal = 1.0, range 0.1–4.0."""
        self.tts_rate = max(0.1, min(4.0, rate))
        self._save_config()
        info(f"TTS rate set to {self.tts_rate}x")

    def set_pitch(self, pitch: float):
        """Set TTS speech pitch. Normal = 1.0, range 0.1–4.0."""
        self.tts_pitch = max(0.1, min(4.0, pitch))
        self._save_config()
        info(f"TTS pitch set to {self.tts_pitch}x")

    def status(self) -> str:
        """Return a one-line status string."""
        state = "[green]ON[/green]" if self.enabled else "[dim]OFF[/dim]"
        tts = "[green]yes[/green]" if self.tts_available() else "[red]no[/red]"
        stt = "[green]yes[/green]" if self.stt_available() else "[red]no[/red]"
        return (
            f"Voice: {state} | TTS: {tts} | STT: {stt} | "
            f"Rate: {self.tts_rate}x | Pitch: {self.tts_pitch}x"
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

_voice: Optional[VoiceManager] = None


def get_voice() -> VoiceManager:
    """Return the VoiceManager singleton."""
    global _voice
    if _voice is None:
        _voice = VoiceManager()
    return _voice
