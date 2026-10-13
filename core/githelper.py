"""
Git helper for Codey-OS.

v2.5.5 — Phase 3: branch management, smart commit messages,
                   merge conflict detection and resolution.
"""

import os
import re
from pathlib import Path
from typing import List

from core.git_commit_context import (
    ScopedCommitError,
    discover_worktree,
    isolated_broad_commit_context,
    isolated_scoped_commit_context,
)
from core.git_execution import push_environment, run_git
from core.git_mutation_context import GitMutationError, isolated_mutation_context
from core.git_query_context import metadata_query
from core.git_worktree_context import worktree_query

# ── Basic repo queries ─────────────────────────────────────────────────────────


def _is_git_repo(path, runner):
    path = path or os.getcwd()
    result = runner(["git", "rev-parse", "--git-dir"], capture_output=True, cwd=path)
    return result.returncode == 0


def is_git_repo(path: str = None) -> bool:
    return metadata_query(path, action="githelper.is_git_repo", operation="is_repo")


def _git_status(path, runner):
    path = path or os.getcwd()
    result = runner(["git", "status", "--short"], capture_output=True, text=True, cwd=path)
    return result.stdout.strip() or "Nothing to commit."


def git_status(path: str = None) -> str:
    """READ-gated worktree status; see core/git_worktree_context.py."""
    return worktree_query(path, action="githelper.git_status", operation="status")


def git_diff_stat(path: str = None) -> str:
    """READ-gated diff --stat; see core/git_worktree_context.py.

    No production caller as of this slice (test-only; HANDOFF.md names this
    as possible dead code — not fixed here, see handoff).
    """
    return worktree_query(path, action="githelper.git_diff_stat", operation="diff_stat")


def git_log(n: int = 5, path: str = None) -> str:
    return metadata_query(path, action="githelper.git_log", operation="log", n=n)


def git_current_branch(path: str = None) -> str:
    """Return the validated branch name, including unborn, or detached HEAD."""
    return metadata_query(path, action="githelper.git_current_branch", operation="branch")


# ── Commit ─────────────────────────────────────────────────────────────────────


def _gate_local_commit(action, operation):
    """Audit a local commit attempt, preserving strings and original errors.

    An allowed no-op is not proof of a commit; staging can precede failure.
    Git error text is retained in failed audit reasons.
    """
    from core.action_gateway import ACT, get_action_gateway

    result = None
    original_error = None

    def execute():
        nonlocal result, original_error
        try:
            result = operation()
        except Exception as exc:
            # The gateway records failure instead of raising; keep the
            # original exception so this adapter preserves caller behavior.
            original_error = exc
            if getattr(exc, "_scoped_cleanup_failed", False):
                raise RuntimeError(f"{exc}; scoped Git context cleanup or publication also failed") from exc
            raise
        if result.startswith("[ERROR]"):
            # Existing helpers report Git failures as strings. Raise only
            # inside the gate to distinguish them from allowed attempts.
            raise RuntimeError(result)
        return result

    decision = get_action_gateway().gate_exec(
        authority=ACT,
        action=action,
        command="local git commit attempt",
        confirm_available=False,
        execute=execute,
    )
    if original_error is not None:
        raise original_error
    if result is not None:
        return result
    return f"[ERROR] Local git commit {decision.outcome}: {decision.reason}"


def git_commit(message: str, path: str = None, add_all: bool = True) -> str:
    """Commit through positive configuration and private administration.

    Add-all covers the entire repo; staged-only preserves existing blobs.
    Ordinary one-head merge/squash continuation is bounded. Partial effects
    can remain after failure; this is not a filesystem sandbox or transaction.
    """
    def attempt():
        nonlocal path
        path = path or os.getcwd()
        if discover_worktree(path) is None:
            return "[ERROR] Not a git repository."
        try:
            with isolated_broad_commit_context(path, add_all=add_all) as context:
                runner = context.run
                if add_all:
                    result = runner(["git", "add", "-A"], capture_output=True, text=True, cwd=path)
                    if result.returncode != 0:
                        raise ScopedCommitError(f"git add failed: {result.stderr}")
                status = _git_status(path, runner)
                if status == "Nothing to commit." and not context.pending_merge:
                    return "Nothing to commit — working tree clean."
                result = runner(["git", "commit", "-m", message], capture_output=True, text=True, cwd=path)
                if result.returncode == 0:
                    return result.stdout.strip()
                raise ScopedCommitError(result.stderr.strip())
        except ScopedCommitError as exc:
            extra = "; scoped Git context cleanup or publication also failed" if getattr(exc, "_scoped_cleanup_failed", False) else ""
            return f"[ERROR] {exc}{extra}"

    return _gate_local_commit("githelper.git_commit", attempt)


def _git_status_paths(paths, path, runner):
    path = path or os.getcwd()
    result = runner(
        ["git", "--literal-pathspecs", "status", "--short", "--"] + list(paths),
        capture_output=True, text=True, cwd=path,
    )
    return result.stdout.strip() or "Nothing to commit."


def git_status_paths(paths: List[str], path: str = None) -> str:
    """Status of literal paths; directories select subtrees, including '.'.

    An empty path list retains historical unrestricted status (NEW-879). This
    provides no single-file or workspace containment. READ-gated through
    core/git_worktree_context.py, whose fixed environment allowlist excludes
    GIT_*_PATHSPECS by construction (not popped at call time as before).
    """
    return worktree_query(path, action="githelper.git_status_paths", operation="status_paths", paths=paths)


def git_commit_paths(message: str, paths: List[str], path: str = None) -> str:
    """Stage/commit literal paths through ACT; directories select their subtrees.

    A private administrative context imports selected configuration data only;
    effective filter drivers and unsupported layouts fail before staging.
    Clean/no-path attempts audit without proving a commit.
    A directory (including '.') intentionally selects its subtree; this is no
    single-file or workspace containment guarantee. Staging may remain after
    a failed commit (see NEW-17 for scoped paths).
    """
    def attempt():
        nonlocal path
        path = path or os.getcwd()
        if discover_worktree(path) is None:
            return "[ERROR] Not a git repository."
        if not paths:
            return "Nothing to commit."
        try:
            with isolated_scoped_commit_context(path, paths) as runner:
                result = runner(["git", "--literal-pathspecs", "add", "--"] + list(paths), capture_output=True, text=True, cwd=path)
                if result.returncode != 0:
                    raise ScopedCommitError(f"git add failed: {result.stderr}")
                status = _git_status_paths(paths, path, runner)
                if status == "Nothing to commit.":
                    return "Nothing to commit — working tree clean."
                result = runner(
                    ["git", "--literal-pathspecs", "commit", "-m", message, "--"] + list(paths), capture_output=True, text=True, cwd=path
                )
                if result.returncode == 0:
                    return result.stdout.strip()
                raise ScopedCommitError(result.stderr.strip())
        except ScopedCommitError as exc:
            extra = "; scoped Git context cleanup or publication also failed" if getattr(exc, "_scoped_cleanup_failed", False) else ""
            return f"[ERROR] {exc}{extra}"

    return _gate_local_commit("githelper.git_commit_paths", attempt)


def git_push(path: str = None, *, confirm=None) -> str:
    """Publish through HIGH_IMPACT mediation with explicit human approval.

    No callback means no confirmation path and no Git execution. Git
    error strings and subprocess exception identity are preserved.

    The child process runs under core/git_execution.py::push_environment(),
    which strips ambient ssh/proxy/credential/config-override variables and
    forces core.hookspath, push.gpgSign, submodule.recurse, gc.auto, and
    maintenance.auto to safe values at the highest config precedence. This
    push does NOT inherit core/git_mutation_context.py's preflight() or
    active-sequencer-state checks: push transmits already-committed refs
    and objects, so it never reads the index (the split/sparse-index and
    linked-worktree checks are meaningless here) and does not care about
    local sequencer state (refusing to push finished commits just because
    an unrelated local rebase is mid-flight would be a real, unrequested
    behavior change — see NEW_ISSUES.md).
    """
    from core.action_gateway import HIGH_IMPACT, get_action_gateway

    path = path or os.getcwd()
    output = None
    original_error = None

    def execute():
        nonlocal output, original_error
        try:
            result = run_git(
                ["git", "push"], capture_output=True, text=True, cwd=path,
                env=push_environment(),
            )
        except Exception as exc:
            # Audit execution failure, then restore the caller's original
            # subprocess exception instead of replacing it with a decision.
            original_error = exc
            raise
        if result.returncode == 0:
            output = result.stdout.strip() or "Pushed successfully."
            return output
        output = f"[ERROR] {result.stderr.strip()}"
        raise RuntimeError(output)

    decision = get_action_gateway().gate_exec(
        authority=HIGH_IMPACT,
        action="githelper.git_push",
        command="git push attempt",
        confirm_available=confirm is not None,
        confirm=confirm,
        execute=execute,
    )
    if original_error is not None:
        raise original_error
    if output is not None:
        return output
    return f"[ERROR] Git push {decision.outcome}: {decision.reason}"


# ── Branch management (Phase 3.1) ─────────────────────────────────────────────


def git_branches(path: str = None) -> str:
    """
    List all local branches with current branch marked.
    Shows remote-tracking refs too when present.
    """
    return metadata_query(path, action="githelper.git_branches", operation="branches")


def git_branch_create(name: str, path: str = None) -> str:
    """Create and switch to a local branch through ACT mediation.

    Existing name validation precedes the gate; invalid names do not
    produce mutation audits. Git failure text is retained in audit reasons.
    Runs inside core/git_mutation_context.py's isolated environment: ambient
    hooks, filter/merge drivers, and other configured helpers are bounded
    (see that module's docstring); an in-progress merge/cherry-pick/rebase
    is rejected. A branch create writes no working-tree content, so no
    filter probe applies here (unlike git_checkout).
    """
    path = path or os.getcwd()
    # Validate name (no spaces, no special chars, no leading dashes)
    if re.search(r"[\s~^:?*\[\\\]@{]", name):
        return f"[ERROR] Invalid branch name: '{name}'"
    if name.startswith("-"):
        return f"[ERROR] Branch name cannot start with '-': '{name}'"
    if not name or name in (".", ".."):
        return f"[ERROR] Invalid branch name: '{name}'"

    from core.action_gateway import ACT, get_action_gateway

    output = None
    original_error = None

    def execute():
        nonlocal output, original_error
        try:
            with isolated_mutation_context(path) as context:
                result = context.run(
                    ["git", "checkout", "-b", name], capture_output=True, text=True, cwd=path
                )
        except GitMutationError as exc:
            extra = "; Git mutation context cleanup also failed" if getattr(exc, "_mutation_cleanup_failed", False) else ""
            output = f"[ERROR] {exc}{extra}"
            raise RuntimeError(output)
        except Exception as exc:
            # The gateway records failure instead of raising; preserve
            # the original subprocess exception for this helper's caller.
            original_error = exc
            raise
        extra = "; Git mutation context cleanup also failed" if getattr(context, "_mutation_cleanup_failed", False) else ""
        if result.returncode == 0:
            output = f"Created and switched to branch '{name}'.{extra}"
            return output
        output = f"[ERROR] {result.stderr.strip()}{extra}"
        # Preserve the helper's error string while recording failed execution.
        raise RuntimeError(output)

    decision = get_action_gateway().gate_exec(
        authority=ACT,
        action="githelper.git_branch_create",
        command="local git branch creation attempt",
        confirm_available=False,
        execute=execute,
    )
    if original_error is not None:
        raise original_error
    if output is not None:
        return output
    return f"[ERROR] Local git branch creation {decision.outcome}: {decision.reason}"


def git_checkout(name: str, path: str = None) -> str:
    """Switch a branch/ref through ACT mediation, without checkout options.

    A trailing path separator prevents filename-only targets from restoring
    files. The exact '-' target still selects the previous branch.
    Runs inside core/git_mutation_context.py's isolated environment: ambient
    hooks are bounded, an in-progress merge/cherry-pick/rebase is rejected,
    and any path that would change content on this checkout and carries a
    `filter` attribute is rejected before the real checkout runs (see that
    module's docstring). If the target does not resolve to a commit, the
    probe is skipped and the real checkout produces its own error text. The
    real checkout runs with `--no-guess` so it cannot resolve a name via
    Git's branch-name DWIM (auto-creating a local tracking branch from a
    same-named remote-tracking ref) when the resolve_target() probe above
    reports that name as unresolvable -- without this, such a name would
    bypass the filter probe entirely while still succeeding against the
    real worktree (see core/git_mutation_context.py's docstring).
    """
    if name.startswith("-") and name != "-":
        return f"[ERROR] Checkout options are not supported: '{name}'"

    from core.action_gateway import ACT, get_action_gateway

    path = path or os.getcwd()
    output = None
    original_error = None

    def execute():
        nonlocal output, original_error
        try:
            with isolated_mutation_context(path) as context:
                target = context.resolve_target(name)
                if target is not None:
                    context.reject_attribute(context.changed_paths(target), "filter", source=target)
                result = context.run(
                    ["git", "checkout", "--no-guess", name, "--"], capture_output=True, text=True, cwd=path
                )
        except GitMutationError as exc:
            extra = "; Git mutation context cleanup also failed" if getattr(exc, "_mutation_cleanup_failed", False) else ""
            output = f"[ERROR] {exc}{extra}"
            raise RuntimeError(output)
        except Exception as exc:
            # Record failed execution, then preserve the caller's original
            # subprocess exception instead of replacing it with a decision.
            original_error = exc
            raise
        extra = "; Git mutation context cleanup also failed" if getattr(context, "_mutation_cleanup_failed", False) else ""
        if result.returncode == 0:
            output = (result.stderr.strip() or result.stdout.strip() or f"Switched to branch '{name}'.") + extra
            return output
        output = f"[ERROR] {result.stderr.strip()}{extra}"
        raise RuntimeError(output)

    decision = get_action_gateway().gate_exec(
        authority=ACT,
        action="githelper.git_checkout",
        command="local git checkout attempt",
        confirm_available=False,
        execute=execute,
    )
    if original_error is not None:
        raise original_error
    if output is not None:
        return output
    return f"[ERROR] Local git checkout {decision.outcome}: {decision.reason}"


def git_merge(branch: str, path: str = None) -> str:
    """Merge a branch/ref through ACT mediation; options are not accepted.

    Failed merges can leave changed files, index entries, and MERGE_HEAD.
    Returns the existing OK:, [CONFLICT], or [ERROR] output strings.
    Runs inside core/git_mutation_context.py's isolated environment: ambient
    hooks are bounded, an in-progress merge/cherry-pick/rebase is rejected,
    the merge commit's identity comes from Git's own default home/global
    configuration lookup, and any path touched by the merge that carries a
    `merge` attribute is rejected before the real merge runs (see that
    module's docstring). If the target does not resolve to a commit, the
    probe is skipped and the real merge produces its own error text.
    """
    if branch.startswith("-") and branch != "-":
        return f"[ERROR] Merge options are not supported: '{branch}'"

    from core.action_gateway import ACT, get_action_gateway

    path = path or os.getcwd()
    output = None
    original_error = None

    def execute():
        nonlocal output, original_error
        try:
            with isolated_mutation_context(path) as context:
                target = context.resolve_target(branch)
                if target is not None:
                    context.reject_attribute(context.changed_paths(target), "merge")
                result = context.run(
                    ["git", "merge", "--", branch], capture_output=True, text=True, cwd=path
                )
        except GitMutationError as exc:
            extra = "; Git mutation context cleanup also failed" if getattr(exc, "_mutation_cleanup_failed", False) else ""
            output = f"[ERROR] {exc}{extra}"
            raise RuntimeError(output)
        except Exception as exc:
            # Audit failed execution, then preserve the caller's original
            # subprocess exception instead of replacing it with a decision.
            original_error = exc
            raise
        combined = (result.stdout + result.stderr).strip()
        extra = "; Git mutation context cleanup also failed" if getattr(context, "_mutation_cleanup_failed", False) else ""
        if result.returncode == 0:
            output = f"OK: {combined or 'Merged successfully.'}{extra}"
            return output
        if "CONFLICT" in combined.upper():
            output = f"[CONFLICT] {combined}{extra}"
        else:
            output = f"[ERROR] {combined}{extra}"
        # A conflicted merge was attempted but did not complete successfully.
        raise RuntimeError(output)

    decision = get_action_gateway().gate_exec(
        authority=ACT,
        action="githelper.git_merge",
        command="local git merge attempt",
        confirm_available=False,
        execute=execute,
    )
    if original_error is not None:
        raise original_error
    if output is not None:
        return output
    return f"[ERROR] Local git merge {decision.outcome}: {decision.reason}"


# ── Conflict detection & parsing (Phase 3.2) ──────────────────────────────────


def detect_conflicts(path: str = None) -> List[str]:
    """
    Return a list of files that currently have merge conflict markers
    in the working tree.  Uses 'git diff --name-only --diff-filter=U'
    which is the authoritative way to find unmerged paths.

    READ-gated through core/git_worktree_context.py, which explicitly
    supports active merge/cherry-pick/revert/rebase state (detect_conflicts
    exists precisely to report unmerged paths). The UU/AA-only fallback
    prefix check (misses DU/UD/AU/UA/DD) is preserved verbatim — a known,
    separately-logged gap, not fixed in this slice.
    """
    return worktree_query(path, action="githelper.detect_conflicts", operation="detect_conflicts")


def get_conflict_sections(filepath: str) -> dict:
    """
    Parse a file containing git conflict markers and extract both sides.

    Returns a dict:
        {
            "has_conflicts": bool,
            "ours":   str,   # HEAD / current branch content
            "theirs": str,   # Incoming branch content
            "pre":    str,   # Lines before first conflict
            "post":   str,   # Lines after last conflict
            "raw":    str,   # Full file content
            "count":  int,   # Number of conflict blocks
        }
    """
    try:
        raw = Path(filepath).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"has_conflicts": False, "error": str(e)}

    if "<<<<<<< " not in raw:
        return {"has_conflicts": False, "raw": raw, "count": 0}

    ours_blocks: List[str] = []
    theirs_blocks: List[str] = []
    pre_lines: List[str] = []
    post_lines: List[str] = []

    state = "pre"  # pre | ours | theirs | post
    ours_buf: List[str] = []
    theirs_buf: List[str] = []

    for line in raw.splitlines(keepends=True):
        if line.startswith("<<<<<<<"):
            state = "ours"
            ours_buf = []
        elif line.startswith("=======") and state == "ours":
            state = "theirs"
            theirs_buf = []
        elif line.startswith(">>>>>>>") and state == "theirs":
            ours_blocks.append("".join(ours_buf))
            theirs_blocks.append("".join(theirs_buf))
            state = "post"
        elif state == "pre":
            pre_lines.append(line)
        elif state == "ours":
            ours_buf.append(line)
        elif state == "theirs":
            theirs_buf.append(line)
        elif state == "post":
            post_lines.append(line)

    return {
        "has_conflicts": True,
        "ours": "\n---\n".join(ours_blocks),
        "theirs": "\n---\n".join(theirs_blocks),
        "pre": "".join(pre_lines),
        "post": "".join(post_lines),
        "raw": raw,
        "count": len(ours_blocks),
    }


# ── Smart commit helpers (Phase 3.3) ──────────────────────────────────────────


def git_diff_for_commit(path: str = None, max_chars: int = 3000) -> str:
    """
    Get a diff suitable for generating a commit message.
    Tries staged diff first, then unstaged.
    Truncates to `max_chars` to stay within context window.

    READ-gated through core/git_worktree_context.py. Staged/unstaged diffs
    succeed on unborn HEAD (vs the empty tree); the HEAD~1..HEAD fallback
    fails on unborn AND on a single-commit (no-parent) repository — both
    map explicitly to the existing "(no diff available)" sentinel.
    Truncation can still cut mid-UTF-8/mid-hunk (pre-existing, not fixed
    in this slice — see handoff).
    """
    return worktree_query(path, action="githelper.git_diff_for_commit", operation="diff_for_commit", max_chars=max_chars)


def git_commit_log_messages(n: int = 10, path: str = None) -> List[str]:
    """Return the last n commit subject lines (for style detection)."""
    return metadata_query(path, action="githelper.git_commit_log_messages", operation="messages", n=n)


def uses_conventional_commits(messages: List[str]) -> bool:
    """
    Return True if the majority of recent commits follow conventional commits
    format:  type(scope)?: description
    """
    if not messages:
        return False
    _cc_re = re.compile(
        r"^(feat|fix|docs|style|refactor|test|chore|perf|ci|build|revert)" r"(\([^)]+\))?!?:\s+.+",
        re.IGNORECASE,
    )
    hits = sum(1 for m in messages if _cc_re.match(m))
    return hits >= max(1, len(messages) // 2)


def generate_commit_message(diff: str, history_msgs: List[str]) -> str:
    """
    Use the inference engine to generate a meaningful commit message
    from a git diff.  Calls infer() directly (no tool loop needed).

    Returns a single-line commit message string.
    """
    from core.inference_v2 import infer

    cc_style = uses_conventional_commits(history_msgs)
    style_hint = (
        "Use conventional commits format: type(scope)?: description\n"
        "Types: feat, fix, docs, style, refactor, test, chore, perf\n"
        "Examples: 'feat: add voice interface', 'fix: agent loop on simple writes'"
        if cc_style
        else "Write a clear, descriptive single-line message.\n"
        "Examples: 'Add voice TTS/STT interface', 'Fix agent loop after file write'"
    )

    prompt_text = (
        f"Git diff:\n```\n{diff}\n```\n\n"
        f"Task: Write ONE commit message line for this diff.\n"
        f"{style_hint}\n"
        "Reply with ONLY the commit message. No explanation. No quotes."
    )

    messages = [
        {
            "role": "system",
            "content": "You are a git commit message writer. Output only the commit message line, nothing else.",
        },
        {"role": "user", "content": prompt_text},
    ]

    try:
        result = infer(messages, stream=False, show_thinking=False)
        if result and not result.startswith("[ERROR]"):
            # Clean up: strip quotes, trim, take first line only
            msg = result.strip().strip("\"'`").splitlines()[0].strip()
            # Cap length
            return msg[:100] if len(msg) > 100 else msg
    except Exception:
        pass

    return "Update project files"
