import logging
import sys
from typing import Optional

from rich.console import Console
from rich.theme import Theme

_theme = Theme(
    {
        "info": "bold cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "tool": "bold magenta",
        "think": "dim italic white",
        "user": "bold blue",
    }
)

console = Console(theme=_theme, highlight=False)

# Log level mapping
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}

# Current log level (can be set from config)
_current_log_level: int = logging.INFO

# File handler for daemon logging
_file_handler: Optional[logging.FileHandler] = None
_file_logger: Optional[logging.Logger] = None


def set_log_level(level: str):
    """Set the current log level."""
    global _current_log_level
    _current_log_level = LOG_LEVELS.get(level.upper(), logging.INFO)


def setup_file_logging(log_file: str):
    """Set up file logging for daemon mode."""
    global _file_handler, _file_logger

    _file_logger = logging.getLogger("codey_daemon")
    _file_logger.setLevel(logging.DEBUG)

    _file_handler = logging.FileHandler(log_file, mode="a")
    _file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    _file_handler.setFormatter(formatter)

    _file_logger.addHandler(_file_handler)


def _log_to_file(level: str, message: str):
    """Log a message to the file handler."""
    if _file_logger:
        log_method = getattr(_file_logger, level.lower(), _file_logger.info)
        try:
            # Lazy: the utils package must not import core at module import time.
            from core.export_hygiene import mask_secrets

            message = mask_secrets(message)
        except Exception:
            # Fail closed: an unmaskable message is replaced, never written raw.
            message = "[withheld: redaction failed]"
        log_method(message)


def info(msg):
    if _current_log_level <= logging.INFO:
        console.print(f"[info]ℹ  {msg}[/info]")
    _log_to_file("info", msg)


def success(msg):
    if _current_log_level <= logging.INFO:
        console.print(f"[success]✓  {msg}[/success]")
    _log_to_file("info", msg)


def warning(msg):
    if _current_log_level <= logging.WARNING:
        console.print(f"[warning]⚠  {msg}[/warning]")
    _log_to_file("warning", msg)


def error(msg):
    if _current_log_level <= logging.ERROR:
        console.print(f"[error]✗  {msg}[/error]")
    _log_to_file("error", msg)


def think(msg):
    if _current_log_level <= logging.DEBUG:
        console.print(f"[think]💭 {msg}[/think]")
    _log_to_file("debug", msg)


def debug(msg):
    """Debug level logging."""
    if _current_log_level <= logging.DEBUG:
        console.print(f"[dim]🔍 {msg}[/dim]")
    _log_to_file("debug", msg)


def tool_call(name, args):
    console.print(f"[tool]🔧 TOOL [{name}][/tool]")


def tool_result(result):
    preview = str(result)[:200]
    console.print(f"[success]   ↳ {preview}[/success]")


def separator():
    console.rule(style="dim")


def _stdin_is_tty() -> bool:
    """True only when stdin is a terminal. Any failure (stdin None/closed,
    isatty missing or raising) is "no human here". Test seam; there is
    deliberately no env/flag override (NEW-1074)."""
    try:
        return bool(sys.stdin.isatty())
    except Exception:
        # Fail closed: an unusable stdin cannot carry human consent.
        return False


def _flush_stdin_typeahead() -> None:
    """Discard keystrokes buffered before the prompt (same idea as
    core/tty_confirm.py; inlined so utils never imports core). Fail-soft:
    the tty check already ran and a flush failure must not block the prompt
    -- the residual risk is only stale typeahead on an interactive tty."""
    try:
        import termios

        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except Exception:
        pass  # termios unavailable / not flushable: best-effort only


def confirm(question) -> bool:
    """Keep asking until we get a real y or n — never auto-cancel.

    Fails closed (NEW-1074): stdin not a tty -> False WITHOUT reading it, so
    piped/queued input can never approve (use --yolo for unattended runs).
    On a tty, stale typeahead is flushed before the prompt."""
    if not _stdin_is_tty():
        return False
    sys.stdout.flush()
    sys.stderr.flush()
    _flush_stdin_typeahead()
    while True:
        try:
            ans = console.input(f"\n⚠  {question} \\[y/N]: ").strip().lower()
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no", ""):
                # Only accept empty as No if it was a deliberate Enter
                # Re-prompt if stdin might have leftover newlines
                return False
        except EOFError:
            # stdin closed (e.g. piped input) — default to False
            return False
        except KeyboardInterrupt:
            print()
            return False
