#!/usr/bin/env python3
"""
Daemon configuration for Codey-OS.

Loads configuration from ~/.codeyOS/config.json
Provides defaults for all settings.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any, Dict, Optional

from utils.config import (CODEY_STATE_DIR, DAEMON_CONFIG_FILE, DAEMON_LOG_FILE,
                          DAEMON_PID_FILE, DAEMON_SOCKET_FILE, STATE_DB_FILE)

# Configuration directory
CONFIG_DIR = CODEY_STATE_DIR
CONFIG_FILE = DAEMON_CONFIG_FILE

_MAX_PATH_BYTES = 4096


class DaemonPathError(ValueError):
    """An effective daemon path is not a usable absolute path (NEW-959)."""


def _refusal(field, value, source):
    shown = repr(value)[:120]
    message = f"Daemon path {field} must be absolute; got {shown} ({source})."
    if field.startswith("daemon."):
        message += (" If a daemon was started under this relative value, set the key to"
                    " the absolute location it was started in before stopping it; tools"
                    " will not scan for, adopt, move or stop it.")
    elif field == "CODEY_STATE_DIR":
        message += (" Set CODEY_STATE_DIR to an absolute directory; the tools will not"
                    " scan for or stop a daemon started under a relative root.")
    return DaemonPathError(message)


def validate_daemon_path(field, value, source):
    """Predicate only: never abspath/normpath/resolve/anchor a value."""
    text = str(value) if isinstance(value, PurePath) else value
    if not isinstance(text, str) or not text or "\0" in text:
        raise _refusal(field, value, source)
    try:
        too_long = len(os.fsencode(text)) > _MAX_PATH_BYTES
    except UnicodeError:
        too_long = True
    if too_long or not PurePath(text).is_absolute():
        raise _refusal(field, value, source)


def require_absolute_state_root():
    """A relative CODEY_STATE_DIR also relocates config.json and the defaults."""
    validate_daemon_path("CODEY_STATE_DIR", str(CODEY_STATE_DIR), "state directory")


# Default configuration
DEFAULT_CONFIG: Dict[str, Any] = {
    # Daemon settings
    "daemon": {
        "pid_file": str(DAEMON_PID_FILE),
        "socket_file": str(DAEMON_SOCKET_FILE),
        "log_file": str(DAEMON_LOG_FILE),
        "log_level": "INFO",  # DEBUG, INFO, WARNING, ERROR
    },
    # Task processing settings
    "tasks": {
        "max_concurrent": 1,
        "task_timeout": 1800,  # 30 minutes
        "max_retries": 3,
    },
    # Health check settings
    "health": {
        "check_interval": 60,  # seconds
        "max_memory_mb": 1500,
        "stuck_task_threshold": 1800,  # 30 minutes
    },
    # State database settings
    "state": {
        "db_path": str(STATE_DB_FILE),
        "cleanup_old_actions_hours": 24,
    },
}


class DaemonConfig:
    """
    Daemon configuration manager.

    Loads from config file, falls back to defaults.
    Provides get/set methods for configuration access.
    """

    def __init__(self, config_file: Path = CONFIG_FILE):
        self.config_file = config_file
        self._config: Dict[str, Any] = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or return defaults."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    user_config = json.load(f)
                # Merge with defaults
                return self._merge_configs(DEFAULT_CONFIG, user_config)
            except (json.JSONDecodeError, IOError) as e:
                from utils.logger import warning
                warning(f"Could not load config file: {e}")
                return DEFAULT_CONFIG.copy()
        return DEFAULT_CONFIG.copy()

    def _merge_configs(self, base: Dict, override: Dict) -> Dict:
        """Recursively merge override config into base config."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result

    def get(self, *keys: str, default: Any = None) -> Any:
        """
        Get a configuration value by nested keys.

        Example: config.get("daemon", "log_level")
        """
        current = self._config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default

        # Expand tilde paths for string values
        if isinstance(current, str) and current.startswith("~"):
            return str(Path(current).expanduser())
        return current

    def set(self, *keys: str, value: Any):
        """
        Set a configuration value by nested keys.

        Example: config.set("daemon", "log_level", value="DEBUG")
        """
        current = self._config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value

    def save(self):
        """Save current configuration to file."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w") as f:
            json.dump(self._config, f, indent=2)

    def create_default_config(self) -> Path:
        """Create a default config file if it doesn't exist."""
        resolve_daemon_paths(self)
        if not self.config_file.exists():
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
        return self.config_file

    @property
    def all(self) -> Dict[str, Any]:
        """Get all configuration as a dictionary."""
        return self._config.copy()


# Global configuration instance
_config: Optional[DaemonConfig] = None


def get_config() -> DaemonConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = DaemonConfig()
    return _config


def reset_config():
    """Reset the global configuration (for testing)."""
    global _config
    if _config:
        _config = None


def create_default_config() -> Path:
    """Create a default config file."""
    config = get_config()
    return config.create_default_config()


@dataclass(frozen=True)
class DaemonPaths:
    """One effective path snapshot shared by a complete daemon operation."""

    pid_file: Path
    socket_file: Path
    log_file: Path

    def __post_init__(self):
        for name in ("pid_file", "socket_file", "log_file"):
            validate_daemon_path(f"daemon.{name}", getattr(self, name), "path snapshot")


def resolve_daemon_paths(config=None):
    """Read configured daemon paths without creating state directories.

    Each effective value (after default merge and leading-~ expansion) must be
    a non-empty absolute path; relative values and a relative CODEY_STATE_DIR
    are refused with DaemonPathError, never anchored, resolved or rewritten.
    """
    selected = get_config() if config is None else config
    require_absolute_state_root()
    source = f"config file {getattr(selected, 'config_file', CONFIG_FILE)}"
    defaults = {"pid_file": DAEMON_PID_FILE, "socket_file": DAEMON_SOCKET_FILE, "log_file": DAEMON_LOG_FILE}
    values = {}
    for name, default in defaults.items():
        field = f"daemon.{name}"
        configured = selected.all.get("daemon", {})
        original = configured.get(name, str(default)) if isinstance(configured, dict) else str(default)
        try:
            value = selected.get("daemon", name, default=str(default))
        except (TypeError, RuntimeError):  # e.g. ~nosuchuser expansion
            raise _refusal(field, original, source) from None
        validate_daemon_path(field, value, source)
        values[name] = Path(value)
    return DaemonPaths(**values)
