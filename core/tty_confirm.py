"""Human confirmation on the controlling terminal (WP2.1 G15i-A, from NEW-977).

Shared primitive extracted verbatim in behaviour from core/lora_import.py so
that every "a human must be present" HIGH_IMPACT guard uses one audited
implementation. Stdlib only: `termios` and `core.action_gateway` are imported
inside functions, so importing this module pulls in nothing else.

/dev/tty is used (not stdin/stdout) because stdout/stderr are routinely
captured when a CLI is spawned by a tool. A process with no controlling
terminal (daemon, detached child, agent harness: ENXIO) cannot open it, so
every unattended path fails closed. This is a human-presence check, not a
security boundary against a same-uid process (G15i spec section 1.2).

The prompt is written as-is (UTF-8, undecodable replaced). Callers that embed
dynamic text (paths, usernames) must escape it themselves (e.g. `{x!a}`).
"""

import os

TTY_PATH = "/dev/tty"


def open_tty() -> int:
    """Open the controlling terminal read/write and return the fd. Raises
    OSError when the process has none (the gateway treats that as
    'confirmation unavailable' and refuses). A raw fd, not a text file:
    open(path, "r+") raises 'File or stream is not seekable' on a terminal."""
    return os.open(TTY_PATH, os.O_RDWR | os.O_NOCTTY)


def confirm_on_tty(prompt: str, *, open_tty=open_tty) -> bool:
    """Ask the human on the tty returned by `open_tty()`. True only for an
    explicit y/yes; decline, empty answer, EOF and any I/O failure never
    return True (EOF raises EOFError, tty/flush failures raise OSError)."""
    fd = open_tty()
    try:
        # Discard stale typeahead (an earlier stray "y\n") BEFORE prompting, so
        # only an answer typed after the prompt appears can approve. Fail
        # closed: if the flush fails (or termios is unavailable) we cannot
        # prove the input queue is clean, so raise and the gateway refuses.
        try:
            import termios
        except ImportError as exc:
            raise OSError("termios unavailable; refusing to confirm") from exc
        try:
            termios.tcflush(fd, termios.TCIFLUSH)
        except (OSError, termios.error) as exc:
            raise OSError("cannot flush tty input; refusing to confirm") from exc
        os.write(fd, prompt.encode("utf-8", errors="replace"))
        line = b""
        while len(line) < 256:
            chunk = os.read(fd, 1)
            if not chunk:
                break  # EOF
            if chunk == b"\n":
                line += chunk
                break
            line += chunk
    finally:
        os.close(fd)
    if line == b"":
        raise EOFError("no answer on tty")
    return line.decode("utf-8", errors="replace").strip().lower() in ("y", "yes")


def gate_human_action(action, command, prompt, execute, *, confirm=None, open_tty=None):
    """Run `execute` as HIGH_IMPACT behind a per-attempt tty confirm.

    `action` and `command` are static audit labels (gate_exec writes them to
    the ledger): never put paths, payload or exception text in them. Dynamic
    detail belongs only in `prompt`, which goes to the human's tty.
    `confirm` overrides the callback (consumers pass a call-time lookup of
    their own module seam); otherwise `confirm_on_tty(prompt, open_tty=...)`.
    """
    from core.action_gateway import HIGH_IMPACT, get_action_gateway

    if confirm is None:
        opener = open_tty if open_tty is not None else globals()["open_tty"]

        def confirm():
            return confirm_on_tty(prompt, open_tty=opener)

    return get_action_gateway().gate_exec(
        authority=HIGH_IMPACT,
        action=action,
        command=command,
        # A confirmation path exists in principle; whether a human actually
        # answers is decided by the confirm callback, which fails closed.
        confirm_available=True,
        execute=execute,
        confirm=confirm,
    )
