"""
patch_file — surgical find/replace in files.
Much more efficient than write_file for small edits.
"""

import os
from pathlib import Path

from core.filehistory import snapshot
from utils.config import AGENT_CONFIG
from utils.logger import confirm as ask_confirm
from utils.logger import warning


def tool_patch_file(path: str, old_str: str, new_str: str) -> str:
    """
    Replace first occurrence of old_str with new_str in file.
    Snapshots before patching for /undo support.
    """
    if not path or not isinstance(path, str):
        return "[ERROR] Invalid path: empty or not a string"
    if not old_str or not isinstance(old_str, str):
        return "[ERROR] Invalid old_str: empty or not a string"
    if new_str is None:
        return "[ERROR] Invalid new_str: None"
    if not isinstance(new_str, str):
        new_str = str(new_str)

    p = Path(path).expanduser()
    if not p.exists():
        # Try relative to cwd
        p = Path(os.getcwd()) / path

    # G15e Unit C (Q7a, NEW-1031): validate the path BEFORE anything is read,
    # so a non-matching old_str can no longer echo a file outside the
    # workspace or a credential file (the [PATCH_FAILED] branch below returns
    # the whole file). Runs before the exists() check on purpose: a refusal
    # that depended on existence would be an existence oracle for secrets.
    # Same boundary as Filesystem.read(): workspace/CODE_DIR plus credentials.
    try:
        from core.filesystem import FilesystemAccessError, get_filesystem

        fs = get_filesystem(
            allow_self_modification=AGENT_CONFIG.get("allow_self_modification", False)
        )
        fs._validate_for_read(os.path.abspath(p))
    except FilesystemAccessError as e:
        return f"[ERROR] {e}"
    except (ValueError, OSError) as e:
        # Malformed path (e.g. embedded NUL): refuse before reading.
        return f"[ERROR] Invalid path {path!r}: {e}"
    if not p.exists():
        return f"[ERROR] File not found: {path}"

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[ERROR] Could not read {path}: {e}"

    count = content.count(old_str)
    if count == 0:
        # old_str not found — model's context may be stale.  Return the current
        # file content so the model can reconstruct the correct patch or fall back
        # to write_file with the full intended content instead of retrying blindly.
        lines = content.splitlines()
        return (
            f"[PATCH_FAILED] old_str not found in {path} ({len(lines)} lines).\n"
            "The file may have changed since you last read it. "
            "Re-read the file first and issue a corrected patch with an old_str that "
            "matches exactly. Only use write_file as a last resort, and only with the "
            "file's complete, verified content — never a partial reconstruction from memory.\n"
            f"Current file content:\n{content}"
        )

    if count > 1:
        lines = content.splitlines()
        return (
            f"[ERROR] String found {count} times in {path}. "
            f"Provide more context in 'old_str' to make it unique.\n"
            f"File has {len(lines)} lines."
        )

    # Show diff preview
    new_content = content.replace(old_str, new_str, 1)

    if AGENT_CONFIG.get("confirm_write"):
        warning(f"About to patch: {path}")
        # Show context around the change
        old_lines = old_str.splitlines()
        new_lines = new_str.splitlines()
        print(f"  Removing: {repr(old_str[:80])}")
        print(f"  Adding:   {repr(new_str[:80])}")
        if not ask_confirm("Apply patch?"):
            return "[CANCELLED] Patch cancelled."

    # Pre-patch syntax check for Python files: reject patches that break syntax
    if p.suffix == ".py":
        try:
            from core.linter import check_syntax

            syn_err = check_syntax(new_content, str(p))
            if syn_err:
                return (
                    f"[ERROR] Patch would introduce syntax error: {syn_err}\n"
                    "Fix the syntax in your patch and try again. "
                    "Consider using write_file to replace the entire file instead."
                )
        except Exception:
            pass  # linter unavailable — allow patch

    try:
        # Route through Filesystem layer (workspace boundary + safety
        # enforcement) via core.action_gateway (WP2.1 slice 3): classified
        # here, then gated, same as tools.file_tools.tool_write_file.
        from core.action_gateway import OUTCOME_FAILED, OUTCOME_REFUSED, get_action_gateway
        from core.filesystem import FilesystemAccessError
        from tools.file_tools import classify_write_action

        authority = classify_write_action(str(p), workspace=fs.workspace)
        # See tools.file_tools.tool_write_file's comment on why
        # allow_self_modification also counts as a confirmation path for
        # HIGH_IMPACT (core-file) writes here.
        confirm_available = bool(AGENT_CONFIG.get("confirm_write", True)) or bool(
            AGENT_CONFIG.get("allow_self_modification", False)
        )
        # G15e Unit C: snapshot for /undo only AFTER the protection check, so a
        # DENY-tier target (state dir, audit ledger, ~/.bashrc, .git, ...) is
        # never copied into file history before the gateway refuses it. The
        # denied call still goes to the gateway below so it is audited.
        try:
            fs._validate_for_mutation(p)
            snapshot(str(p))
        except FilesystemAccessError:
            # Protected / out-of-bounds: skip the snapshot; the gateway call
            # below fails with the same error and writes the audit row.
            pass
        # No gateway `confirm=` here by design (G15j): the earlier
        # ask_confirm("Apply patch?") under confirm_write is the human consent
        # for HIGH targets; see file_tools._high_write_confirm for the file path.
        decision = get_action_gateway().gate_write(
            authority=authority,
            action="patch_tools.tool_patch_file",
            path=str(p),
            content=new_content,
            confirm_available=confirm_available,
            filesystem=fs,
        )
        if decision.outcome == OUTCOME_REFUSED:
            return f"[BLOCKED] {decision.reason}"
        if decision.outcome == OUTCOME_FAILED:
            return f"[ERROR] {decision.reason}"
        # Keep patch_file's own diff-shaped success string on ALLOWED —
        # unlike write_file/append_file, this function already builds a
        # more useful message (char counts, not Filesystem.write()'s
        # generic "Written {path}") than the gateway's delegated result.
        return f"Patched {path} ({len(old_str)} chars → {len(new_str)} chars)"
    except Exception as e:
        return f"[ERROR] Could not write {path}: {e}"
