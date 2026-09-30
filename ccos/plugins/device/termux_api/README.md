# Termux API capability layer

This plugin turns Termux:API into structured CCOS capabilities. The agent sees capability names and parameter schemas rather than raw shell commands.

## Architecture

```text
Natural language
  -> planner / agent
  -> CCOS capability registry
  -> Termux capability
  -> explicit argv
  -> Termux:API command
  -> Android
```

The adapter never invokes a shell. Model-controlled values are passed as subprocess argv, which prevents shell metacharacters from becoming shell syntax.

## Permission model

Capabilities that can communicate externally or make consequential changes are marked dangerous and require explicit permission. The core adapter defaults `allow_dangerous=False`.

Examples: SMS sending, phone calls, Wi-Fi state changes, public sharing, wallpaper changes, scheduled jobs and other write/destructive operations.

## Installation

Inside Termux:

```bash
pkg update
pkg install termux-api
```

Install the matching Termux:API Android add-on as well. The upstream project documents that the add-on and Termux package must be compatible and that API calls may require Android permissions. The Codey plugin reports unavailable commands through `health()` rather than assuming every device supports every capability.

## Agent integration

The plugin manager registers each capability from `manifest.json`. The LLM can therefore receive definitions such as:

```text
name: device.battery
description: Get battery status
parameters: {}
```

or:

```text
name: device.tts_speak
parameters:
  text: string (required)
```

The agent selects `device.tts_speak(text="Hello")`; CCOS executes the registered capability and feeds the structured result back into the agent loop.

## Coverage

The implementation covers the Termux:API device API families present in the upstream project, including battery, brightness, camera, clipboard, contacts, dialogs, downloads, fingerprint, infrared, jobs, keystore, location, media, microphone, NFC, notifications, SAF storage, sensors, sharing, SMS, speech recognition, storage, telephony, TTS, toast, torch, USB, vibration, volume, wallpaper and Wi-Fi. Some general Termux utilities such as `termux-open`, `termux-info`, package management and shell commands intentionally remain outside this plugin because they are not device API capabilities and should be governed by separate CCOS tools.
