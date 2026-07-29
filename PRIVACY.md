# Codey-OS Privacy Policy

## Overview

Codey-OS is designed with privacy as a core principle. This document explains how Codey-OS handles your data.

## Key Principles

### 1. 100% Local by Default
- All AI inference runs locally on your device using llama.cpp
- No data is sent to external servers unless you explicitly configure a remote backend
- Your code, conversations, and project data never leave your device

### 2. No Telemetry
- Codey-OS does not collect any usage statistics
- No analytics or tracking of any kind
- No phone-home calls or telemetry endpoints

### 3. No Cloud Dependencies
- Core functionality works completely offline
- Optional remote backends (OpenRouter) require explicit opt-in
- API keys are loaded from environment variables, never hardcoded

## Data Storage

### Local Files
All data is stored locally in:
- `~/.codeyOS/` - Configuration, session data, daemon state
- `~/.models/` - Downloaded AI models
- Your project directories - Source code and files

### What We Store
- Conversation history (for session resume)
- File changes (for undo/diff functionality)
- Task queue (for daemon mode)
- Embeddings cache (for RAG features)

### What We Don't Store
- No cloud backups
- No sync to external services
- No user accounts or authentication

## Network Connections

### Default (Local Mode)
- No network connections required
- All communication is via Unix domain sockets (local only)
- llama-server binds to 127.0.0.1 only

### Optional Remote Backends
If you configure a remote backend (e.g., OpenRouter):
- API keys are sent via HTTPS with Bearer token authentication
- Only your prompt and conversation are sent for inference
- No file contents or project data is sent unless explicitly included in the prompt

## Security Features

### Command Execution
- Shell commands require user confirmation by default
- Dangerous commands (rm, curl, etc.) receive extra warnings
- Command allowlist in daemon mode restricts available commands

### File System Access
- Path traversal prevention (../ attacks blocked)
- Workspace boundary enforcement
- File size limits to prevent memory exhaustion

### Process Isolation
- Daemon mode uses PID file locking
- Unix socket permissions restricted to owner only
- Process group isolation for subprocesses

## Your Rights

### Data Control
- You can delete all data by removing `~/.codeyOS/`
- Session data can be cleared with `/clear` command
- No data persists after uninstalling

### Transparency
- All code is open source
- No hidden network calls
- Security audit available in codebase

## Contact

For privacy concerns or questions, please open an issue on the GitHub repository.
