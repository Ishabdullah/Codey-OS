"""Additional Termux API command adapters not covered by the core registry."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Dict, List


class ExtendedTermuxAPIError(RuntimeError):
    pass


def _run(command: str, args: List[str] | None = None, input_text: str | None = None, dangerous: bool = False, allow_dangerous: bool = False) -> Dict[str, Any]:
    if dangerous and not allow_dangerous:
        raise ExtendedTermuxAPIError(f"Capability requires explicit permission: {command}")
    if not shutil.which(command):
        raise ExtendedTermuxAPIError(f"Termux command unavailable: {command}")
    try:
        p = subprocess.run([command, *(args or [])], input=input_text, capture_output=True, text=True, timeout=30, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ExtendedTermuxAPIError(f"Timed out: {command}") from exc
    if p.returncode:
        raise ExtendedTermuxAPIError(p.stderr.strip() or p.stdout.strip() or f"{command} exited {p.returncode}")
    out = p.stdout.strip()
    try:
        value = json.loads(out) if out else None
    except json.JSONDecodeError:
        value = out
    return {"ok": True, "command": command, "result": value}


def audio_info(**kwargs): return _run("termux-audio-info")
def call_log(limit=None, offset=None, **kwargs): return _run("termux-call-log", (["-l", str(limit)] if limit is not None else []) + (["-o", str(offset)] if offset is not None else []))
def fingerprint(**kwargs): return _run("termux-fingerprint")
def infrared_frequencies(**kwargs): return _run("termux-infrared-frequencies")
def keystore(command="list", alias=None, algorithm=None, signature=None, detailed=False, allow_dangerous=False, **kwargs):
    args = [command]
    if command == "list":
        if detailed: args.append("-d")
    elif command in ("delete",):
        if not alias: raise ExtendedTermuxAPIError("alias is required")
        args.append(alias)
    elif command == "generate":
        if not alias: raise ExtendedTermuxAPIError("alias is required")
        args.append(alias)
    elif command in ("sign", "verify"):
        if not alias or not algorithm: raise ExtendedTermuxAPIError("alias and algorithm are required")
        args += [alias, algorithm]
        if command == "verify":
            if not signature: raise ExtendedTermuxAPIError("signature is required")
            args.append(signature)
    return _run("termux-keystore", args, dangerous=command == "delete", allow_dangerous=allow_dangerous)

def media_player(action, file=None, **kwargs):
    args = [action]
    if file is not None: args.append(file)
    return _run("termux-media-player", args)

def media_scan(files, recursive=False, verbose=False, **kwargs):
    args = ([] if not recursive else ["-r"]) + ([] if not verbose else ["-v"]) + list(files)
    return _run("termux-media-scan", args)

def nfc(action="read", mode=None, text=None, **kwargs):
    args = ["-r", mode or "short"] if action == "read" else ["-w"]
    if text is not None: args += ["-t", text]
    return _run("termux-nfc", args, dangerous=action == "write", allow_dangerous=kwargs.get("allow_dangerous", False))

def toast(text, background=None, color=None, gravity=None, long=False, **kwargs):
    args = [text]
    if background is not None: args += ["-b", str(background)]
    if color is not None: args += ["-c", str(color)]
    if gravity is not None: args += ["-g", str(gravity)]
    if long: args += ["-l"]
    return _run("termux-toast", args)

def saf_dirs(**kwargs): return _run("termux-saf-dirs")
def saf_managedir(**kwargs): return _run("termux-saf-managedir")
def saf_ls(uri, **kwargs): return _run("termux-saf-ls", [uri])
def saf_mkdir(uri, name, **kwargs): return _run("termux-saf-mkdir", [uri, name])
def saf_create(uri, name, mime=None, **kwargs): return _run("termux-saf-create", (["-t", mime] if mime else []) + [uri, name])
def saf_read(uri, **kwargs): return _run("termux-saf-read", [uri])
def saf_write(uri, text, **kwargs): return _run("termux-saf-write", [uri], input_text=text)
def saf_rm(uri, allow_dangerous=False, **kwargs): return _run("termux-saf-rm", [uri], dangerous=True, allow_dangerous=allow_dangerous)
def saf_stat(uri, **kwargs): return _run("termux-saf-stat", [uri])
def notification_channel(channel_id, name=None, delete=False, **kwargs):
    args = ["-d", channel_id] if delete else [channel_id, name or channel_id]
    return _run("termux-notification-channel", args, dangerous=delete, allow_dangerous=kwargs.get("allow_dangerous", False))
