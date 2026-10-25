#!/usr/bin/env python3
"""
File tools for Codey-OS.

Refactored for v2: Uses core/filesystem.Filesystem class for direct access.
Confirmation logic moved to agent layer. No more PROTECTED_FILES block.
Snapshots handled by Filesystem class.
"""

from pathlib import Path

from core.action_gateway import (
    ACT,
    HIGH_IMPACT,
    OUTCOME_FAILED,
    OUTCOME_REFUSED,
    get_action_gateway,
)
from core.checkpoint import is_core_file
from core.filesystem import Filesystem, FilesystemAccessError, get_filesystem
from utils.config import AGENT_CONFIG

# File types that must be created by code, not written as text by the agent.
# Writing these as plain text produces corrupt/invalid files.
BINARY_FILE_TYPES = {
    ".db",
    ".sqlite",
    ".sqlite3",  # SQLite databases (binary format)
    ".gguf",
    ".bin",
    ".safetensors",  # ML model files
    ".so",
    ".dylib",
    ".dll",  # Compiled native libraries
    ".pyc",
    ".pyo",
    ".pyd",  # Python bytecode
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",  # Archives
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".ico",  # Images
    ".pdf",  # PDFs
}

# Files that must never be silently overwritten — always prompt regardless of yolo.
# These are repo/project metadata files whose loss is hard to recover without git history.
WRITE_PROTECTED = {
    ".gitignore",
    "README.md",
    "readme.md",
    "CLAUDE.md",
    "CODEY.md",
    "requirements.txt",
    "requirements-dev.txt",
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
    "Makefile",
    ".env",
}

# Text source file extensions that receive \" → " decode on write.
# The 7B model sometimes double-encodes JSON, leaving literal \" in content.
# Excluded: .json (\" is valid JSON escaping), .sh (\" is a shell escape).
_DECODE_EXTS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".html",
    ".css",
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
}

def classify_write_action(path: str, *, workspace=None) -> str:
    """Classify a write/append/patch action into an ActionGateway authority
    class (WP2.1 slice 3, CODEY_OS_MASTER_BLUEPRINT.md §21).

    - HIGH_IMPACT when the target is a Codey-OS core file (core/, tools/,
      utils/, prompts/, ccos/plugins/, bench/ — see
      core.checkpoint.is_core_file) — "modify
      Codey itself" is the one HIGH_IMPACT category that clearly applies
      to these tools.
    - HIGH_IMPACT when the target is in the shared protected-path set
      (core.protected_paths), at EITHER tier: the F3 repo files (launchers,
      `*.sh`, `lib/`, root config.json, non-.py plugin files), and, as
      defense in depth, the DENY-tier paths too, so confirm-less modes refuse
      them with an audited HIGH row before Filesystem is reached (Filesystem
      itself still raises for DENY in every mode). is_core_file is
      deliberately NOT widened: it also decides _require_checkpoint (git
      commit + backup), a separate scope (NEW-951).
    - ACT otherwise (ordinary workspace file writes).

    The target is the path Filesystem will actually write: a relative `path`
    is joined to `workspace` (default utils.config.WORKSPACE_ROOT, what
    Filesystem defaults to), NOT to the process cwd. Callers pass the
    Filesystem instance's `.workspace`.

    Deliberately does NOT promote WRITE_PROTECTED filenames (.gitignore,
    README.md, etc.) to HIGH_IMPACT — that set already has its own
    independent ask_confirm() gate BEFORE the function reaches the final
    write call below; if the user declines there, the function returns
    "[CANCELLED]" and never reaches the gateway at all. This is not an
    oversight, it's two independent mechanisms that don't need to be
    unified.

    Resolving the path can raise on a genuinely malformed path (e.g.
    embedded NUL). Falling back to ACT on that failure, rather than letting
    it propagate, preserves the tools' existing error shape (a clean
    "[ERROR] ..." string from Filesystem's own validation) instead of a new
    unhandled exception — the caller downstream still rejects the bad path,
    just later. Any OTHER failure while evaluating the protected set fails
    closed to HIGH_IMPACT (the cost of a false HIGH is a refusal).
    """
    import os

    import core.checkpoint as _ckpt
    import utils.config as _config
    from core.protected_paths import RULE_GIT, build_context, first_hit

    try:
        ws = Path(workspace) if workspace is not None else _config.WORKSPACE_ROOT
        p = Path(path)
        if not p.is_absolute():
            p = ws / p
        lexical = os.path.normpath(str(p))
        target = Path(lexical).resolve()
        if is_core_file(str(target)):
            return HIGH_IMPACT
    except (TypeError, ValueError, OSError):
        return ACT
    try:
        ctx = build_context(code_dir=_ckpt.CODE_DIR, workspace_root=ws)
        # `git-component` is skipped: Filesystem already denies every `.git`
        # path with its pinned "Git metadata directory" FAILED outcome, and
        # relabelling those HIGH would change that contract (the same class
        # of path was ACT before G15e). Every other DENY rule is HIGH here.
        if first_hit((lexical, str(target)), ctx, skip=frozenset({RULE_GIT})) is not None:
            return HIGH_IMPACT
    except Exception:
        # Fail closed: an unevaluable protected set must not downgrade to ACT.
        return HIGH_IMPACT
    return ACT


def _stdin_is_tty() -> bool:
    """True only when stdin is a terminal. Thin wrapper over the single
    source utils.logger._stdin_is_tty (NEW-1074), looked up at call time so a
    test patching EITHER this name or the logger seam is effective here."""
    from utils import logger

    return logger._stdin_is_tty()


def _high_write_confirm(kind: str, path: str, content):
    """Build the zero-arg human-confirmation callback for a HIGH_IMPACT file
    write/append (G15j / NEW-1027). Same stdin `ask_confirm` convention as the
    shell HIGH confirm and the overwrite prompt (no /dev/tty primitive).

    Fail-closed: no tty -> False WITHOUT reading stdin (a piped "y" cannot
    approve). The callback makes exactly one call to utils.logger.confirm();
    confirm() itself re-asks on input that is neither yes nor no, returns
    True only for y/yes, and returns False for n/no/empty/EOF/interrupt. Only
    a literal True approves. The model-chosen path is ascii-escaped, shown as
    head+tail when over 300 chars, and rich-markup-escaped before display.
    """

    def confirm() -> bool:
        if not _stdin_is_tty():
            return False
        from rich.markup import escape

        from utils.logger import confirm as ask_confirm

        shown_raw = ascii(str(path))
        if len(shown_raw) > 300:
            # Keep head AND tail so a long benign prefix cannot hide the
            # real file name.
            shown_raw = shown_raw[:120] + "..." + shown_raw[-160:]
        shown = escape(shown_raw)
        try:
            size = len(str(content).encode("utf-8", "replace"))
        except Exception:
            size = -1
        question = (
            f"{kind} {shown} ({size} bytes)? This is a Codey-OS core / "
            f"protected file (HIGH_IMPACT)."
        )
        return ask_confirm(question) is True

    return confirm


def _high_confirm_kwargs(fs, kind: str, path: str, content, authority: str, human_consented: bool) -> dict:
    """Return {"confirm": callback} only when a human prompt is warranted:
    HIGH_IMPACT, confirm_write on (a REPL-style prompt path exists), no consent
    already obtained in this call, and the path passes Filesystem's mutation
    validation (DENY / out-of-workspace targets are refused by Filesystem with
    no prompt). Otherwise {} so the gateway is called exactly as before."""
    if authority != HIGH_IMPACT or human_consented:
        return {}
    if not bool(AGENT_CONFIG.get("confirm_write", True)):
        return {}
    try:
        fs._validate_for_mutation(path)
    except FilesystemAccessError:
        return {}
    except Exception:
        # Unexpected validator failure: keep the prompt (fail toward asking
        # the human) -- Filesystem re-validates and refuses after it anyway.
        pass
    return {"confirm": _high_write_confirm(kind, path, content)}


# Global filesystem instance
_fs: Filesystem = None
_fs_allow_self_mod: bool = False


def _get_fs() -> Filesystem:
    """Get or create filesystem instance."""
    global _fs, _fs_allow_self_mod

    # Check if allow_self_modification setting changed
    allow_self_mod = AGENT_CONFIG.get("allow_self_modification", False)

    if _fs is None or _fs_allow_self_mod != allow_self_mod:
        _fs = get_filesystem(allow_self_modification=allow_self_mod)
        _fs_allow_self_mod = allow_self_mod

    return _fs


def reset_fs():
    """Reset this module's cached Filesystem instance (NEW-899 Site B).

    core.filesystem.reset_filesystem() only clears that module's own
    singleton -- it does nothing to this module's independent _fs cache,
    so main.py's /cwd handler must call both. Without this, every tool
    in this file (tool_write_file, tool_append_file,
    tool_read_file, tool_list_dir, etc.) keeps using the Filesystem built
    against the pre-/cwd workspace.
    """
    global _fs, _fs_allow_self_mod
    _fs = None
    _fs_allow_self_mod = False


def tool_read_file(path: str) -> str:
    """
    Read file content.

    Args:
        path: Path to file

    Returns:
        File content or error message
    """
    if not path or not isinstance(path, str):
        return "[ERROR] Invalid path: empty or not a string"
    path = path.strip()
    if not path:
        return "[ERROR] Invalid path: empty string"
    try:
        return _get_fs().read(path)
    except FilesystemAccessError as e:
        return f"[ERROR] {e}"


def tool_write_file(path: str, content: str) -> str:
    """
    Write file content.

    - WRITE_PROTECTED files (e.g. .gitignore, README.md) always require
      explicit confirmation when the file already exists.
    - All other existing files require confirmation when AGENT_CONFIG
      confirm_write is True.

    Args:
        path: Path to file
        content: Content to write

    Returns:
        Success message or error message
    """
    from utils.logger import confirm as ask_confirm
    from utils.logger import warning as log_warning

    if not path or not isinstance(path, str):
        return "[ERROR] Invalid path: empty or not a string"
    path = path.strip()
    if not path:
        return "[ERROR] Invalid path: empty string"
    if content is None:
        return "[ERROR] Invalid content: None"
    if not isinstance(content, str):
        content = str(content)

    human_consented = False  # set when an overwrite prompt below was approved
    p = Path(path)
    if not p.is_absolute():
        import os

        p = Path(os.getcwd()) / path
    file_exists = p.exists() and p.is_file()

    # Block writes that would replace a file with drastically smaller content
    # (e.g., overwriting 500-line app.py with just a shebang line)
    if file_exists and p.suffix in (".py", ".js", ".ts", ".html", ".css"):
        try:
            existing_size = p.stat().st_size
            new_size = len(content.encode("utf-8"))
            # If existing file is > 200 bytes and new content is < 20% of it, block
            if existing_size > 200 and new_size < existing_size * 0.2:
                return (
                    f"[ERROR] Refusing to overwrite {p.name} ({existing_size} bytes) "
                    f"with much smaller content ({new_size} bytes). "
                    f"This looks like a stub or incomplete rewrite. "
                    f"Write the COMPLETE file content, or use patch_file for small edits."
                )
        except Exception:
            pass

    # Block writes that would replace an existing .py file with content that
    # has a syntax error — this usually indicates an incomplete or truncated
    # reconstruction (e.g. after a failed patch_file falling back to write_file
    # from stale/partial memory of the file's contents).
    if file_exists and p.suffix == ".py":
        try:
            from core.linter import check_syntax

            syn_err = check_syntax(content, str(p))
            if syn_err:
                return (
                    f"[ERROR] Refusing to overwrite {p.name}: new content has a syntax error: {syn_err}\n"
                    "This looks like an incomplete or truncated reconstruction. "
                    "Re-read the file and try patch_file for a targeted edit instead."
                )
        except Exception:
            pass  # linter unavailable — allow write (same fail-open behavior as patch_file)

    # Block writes to binary/non-text file types — these must be created by code.
    if p.suffix.lower() in BINARY_FILE_TYPES:
        hint = ""
        if p.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
            hint = (
                " SQLite databases are created automatically when your Python code "
                "calls sqlite3.connect(). Do NOT create them with write_file — "
                "just use sqlite3.connect() in your app code and the file appears on first run."
            )
        return f"[ERROR] Cannot write {p.name} as a text file.{hint}"

    # Protected files: always confirm before overwriting.
    if file_exists and p.name in WRITE_PROTECTED:
        log_warning(f"Attempting to overwrite protected file: {path}")
        if not ask_confirm(f"Really overwrite {p.name}?"):
            return f"[CANCELLED] Overwrite of {path} cancelled."
        human_consented = True

    # Regular files: confirm if the flag is set.
    elif file_exists and AGENT_CONFIG.get("confirm_write"):
        log_warning(f"About to overwrite: {path}")
        if not ask_confirm(f"Overwrite {path}?"):
            return f"[CANCELLED] Overwrite of {path} cancelled."
        human_consented = True

    if p.suffix.lower() in _DECODE_EXTS:
        content = content.replace('\\"', '"')

    # Routed through core.action_gateway (WP2.1 slice 3): classified here,
    # then gated. This call is deliberately last — every guard above
    # (size/syntax/binary-type blocks, WRITE_PROTECTED confirm, regular
    # confirm) runs first, so a "[CANCELLED]"/"[ERROR]" from one of those
    # never reaches the gateway at all. Do not move this earlier — that
    # would turn those returns into "[BLOCKED]" and break the
    # WRITE_PROTECTED interaction above.
    #
    # confirm_available also counts allow_self_modification=True (the
    # pre-existing, operator-granted --allow-self-mod/ALLOW_SELF_MOD=1
    # permission, core/filesystem.py:113-119) as a confirmation path for
    # HIGH_IMPACT (core-file) writes — Ish's decision, 2026-10-08. Without
    # this, a daemon/--yolo run with confirm_write=False but
    # allow_self_modification=True (two independently-documented,
    # simultaneously-usable flags, main.py:34,60) would have its
    # self-modification permission silently defeated by the gateway's
    # fail-closed rule, even though allow_self_modification exists
    # specifically to permit this.
    authority = classify_write_action(path, workspace=_get_fs().workspace)
    confirm_available = bool(AGENT_CONFIG.get("confirm_write", True)) or bool(
        AGENT_CONFIG.get("allow_self_modification", False)
    )
    # G15j: for a HIGH_IMPACT target where no human consent was obtained above
    # (new file; NEW-1063 pre-check mismatch included), pass a stdin confirm
    # callback. Only attached when warranted -- see _high_confirm_kwargs.
    extra = _high_confirm_kwargs(_get_fs(), "Write to", path, content, authority, human_consented)
    decision = get_action_gateway().gate_write(
        authority=authority,
        action="file_tools.write_file",
        path=path,
        content=content,
        confirm_available=confirm_available,
        filesystem=_get_fs(),
        **extra,
    )
    if decision.outcome == OUTCOME_REFUSED:
        return f"[BLOCKED] {decision.reason}"
    if decision.outcome == OUTCOME_FAILED:
        return f"[ERROR] {decision.reason}"
    return decision.detail.get("result", f"Written {path}")


def tool_append_file(path: str, content: str) -> str:
    """
    Append content to file.

    Routed through core.action_gateway (WP2.1 slice 3) — this was the
    first gating tool_append_file ever received; previously it had no
    confirm/protected-name checks at all.

    Args:
        path: Path to file
        content: Content to append

    Returns:
        Success message or error message
    """
    authority = classify_write_action(path, workspace=_get_fs().workspace)
    # See tool_write_file's comment above on why allow_self_modification
    # also counts as a confirmation path here.
    confirm_available = bool(AGENT_CONFIG.get("confirm_write", True)) or bool(
        AGENT_CONFIG.get("allow_self_modification", False)
    )
    # G15j: append never has a legacy human prompt, so human_consented=False.
    extra = _high_confirm_kwargs(_get_fs(), "Append to", path, content, authority, False)
    decision = get_action_gateway().gate_append(
        authority=authority,
        action="file_tools.append_file",
        path=path,
        content=content,
        confirm_available=confirm_available,
        filesystem=_get_fs(),
        **extra,
    )
    if decision.outcome == OUTCOME_REFUSED:
        return f"[BLOCKED] {decision.reason}"
    if decision.outcome == OUTCOME_FAILED:
        return f"[ERROR] {decision.reason}"
    return decision.detail.get("result", f"Appended to {path}")


def tool_list_dir(path: str = ".") -> str:
    """
    List directory contents.

    Args:
        path: Directory path (default: current directory)

    Returns:
        Formatted list of entries or error message
    """
    try:
        entries = _get_fs().list_dir(path)
        # Format as multi-line string
        lines = []
        for entry in entries:
            full_path = Path(path) / entry
            if full_path.is_dir():
                lines.append(f"📁 {entry}/")
            else:
                lines.append(f"📄 {entry}")
        return "\n".join(lines)
    except FilesystemAccessError as e:
        return f"[ERROR] {e}"


def file_exists(path: str) -> bool:
    """Check if file exists."""
    return _get_fs().exists(path)


def file_is_file(path: str) -> bool:
    """Check if path is a file."""
    return _get_fs().is_file(path)


def file_is_dir(path: str) -> bool:
    """Check if path is a directory."""
    return _get_fs().is_dir(path)
