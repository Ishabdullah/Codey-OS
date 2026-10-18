#!/usr/bin/env python3
"""
Static analysis tools for Codey-OS — Phase 2 (v2.5.2).

Provides:
  - Syntax checking via ast.parse (no tools required)
  - Linter integration: ruff → flake8 (first available wins)
  - Full multi-linter scan for /review command (ruff + flake8 + mypy)
  - Auto-lint hook: runs after every successful file write
  - Pre-write syntax gate: blocks writes with broken Python syntax

Linter preference order: ruff > flake8 > mypy > ast (syntax-only)
User can override by setting CODEY_LINTER env var to "ruff", "flake8", etc.
"""

import ast
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class LintIssue:
    file: str
    line: int
    col: int
    code: str
    message: str
    severity: str  # "error" | "warning" | "info"

    def __str__(self):
        return f"Line {self.line}:{self.col} [{self.code}] {self.message}"


# ── Syntax check (free, no external tools) ────────────────────────────────────


def check_syntax(content: str, filename: str = "<string>") -> Optional[str]:
    """
    Check Python syntax using ast.parse.
    Returns a human-readable error string on failure, None if valid.
    """
    try:
        ast.parse(content, filename=filename)
        return None
    except SyntaxError as e:
        return f"SyntaxError at line {e.lineno}: {e.msg}"
    except Exception as e:
        return f"Parse error: {e}"


# ── Output parsers ─────────────────────────────────────────────────────────────


# 'path:line:col: CODE message'. The path is matched non-greedily up to the first
# ':<digits>:<digits>: ' so a path containing ':' still parses UNLESS it itself
# contains a ':<digits>:<digits>: ' sequence (then the match splits early, the path
# no longer resolves to the file, and the line surfaces as LINT-PARSE, fail-visible).
_COLON_LINE_RE = re.compile(r"^(?P<path>.+?):(?P<line>\d+):(?P<col>\d+): (?P<rest>\S.*)$")
_FOUND_RE = re.compile(r"^Found (\d+) errors?\.?$")
# Lines ruff/flake8 print that are neither violations nor failures.
_NOISE_PREFIXES = ("All checks", "[*]", "No fixes available", "warning:")

# Severity rule (applied to the normalized code: trailing ':' stripped):
#   1. Classic codes (ruff/flake8 'F401', 'E501', 'E999', 'I001', ...): first letter
#      E or F -> "error", anything else -> "warning". Unchanged from before.
#   2. ruff 0.17 prints kebab-case rule NAMES instead of codes (e.g. 'unused-import'
#      for F401, 'lambda-assignment' for E731 in preview mode). Names carry no
#      category letter, so EXACT membership in _ERROR_RULE_NAMES -> "error"; every
#      other name -> "warning". There is deliberately NO substring matching
#      (RUF027 'missing-f-string-syntax' is a warning).
# _ERROR_RULE_NAMES provenance: generated from ruff 0.17.1 on 2026-10-18 via
#   ruff rule --all --output-format json
# = names of all rules whose code matches ^[EF]\d (103 rules, includes preview-only
# ones and E999 'syntax-error'), plus 'invalid-syntax' (ruff's code-less parse-error
# name; it is emitted in output but absent from the rule dump) = 104 names.
# MUST be regenerated when ruff is upgraded; test_error_rule_names_match_ruff_dump
# fails on drift.
_ERROR_RULE_NAMES = frozenset(
    {
        "ambiguous-class-name",
        "ambiguous-function-name",
        "ambiguous-variable-name",
        "assert-tuple",
        "bare-except",
        "blank-line-after-decorator",
        "blank-line-between-methods",
        "blank-lines-after-function-or-class",
        "blank-lines-before-nested-definition",
        "blank-lines-top-level",
        "break-outside-loop",
        "continue-outside-loop",
        "default-except-not-last",
        "expressions-in-star-assignment",
        "f-string-missing-placeholders",
        "forward-annotation-syntax-error",
        "future-feature-not-defined",
        "if-tuple",
        "import-shadowed-by-loop-var",
        "indentation-with-invalid-multiple",
        "indentation-with-invalid-multiple-comment",
        "invalid-print-syntax",
        "invalid-syntax",
        "io-error",
        "is-literal",
        "lambda-assignment",
        "late-future-import",
        "line-too-long",
        "missing-whitespace",
        "missing-whitespace-after-keyword",
        "missing-whitespace-around-arithmetic-operator",
        "missing-whitespace-around-bitwise-or-shift-operator",
        "missing-whitespace-around-modulo-operator",
        "missing-whitespace-around-operator",
        "missing-whitespace-around-parameter-equals",
        "mixed-spaces-and-tabs",
        "module-import-not-at-top-of-file",
        "multi-value-repeated-key-literal",
        "multi-value-repeated-key-variable",
        "multiple-imports-on-one-line",
        "multiple-leading-hashes-for-block-comment",
        "multiple-spaces-after-comma",
        "multiple-spaces-after-keyword",
        "multiple-spaces-after-operator",
        "multiple-spaces-before-keyword",
        "multiple-spaces-before-operator",
        "multiple-starred-expressions",
        "multiple-statements-on-one-line-colon",
        "multiple-statements-on-one-line-semicolon",
        "no-indented-block",
        "no-indented-block-comment",
        "no-space-after-block-comment",
        "no-space-after-inline-comment",
        "none-comparison",
        "not-in-test",
        "not-is-test",
        "over-indented",
        "percent-format-expected-mapping",
        "percent-format-expected-sequence",
        "percent-format-extra-named-arguments",
        "percent-format-invalid-format",
        "percent-format-missing-argument",
        "percent-format-mixed-positional-and-named",
        "percent-format-positional-count-mismatch",
        "percent-format-star-requires-sequence",
        "percent-format-unsupported-format-character",
        "raise-not-implemented",
        "redefined-while-unused",
        "redundant-backslash",
        "return-outside-function",
        "string-dot-format-extra-named-arguments",
        "string-dot-format-extra-positional-arguments",
        "string-dot-format-invalid-format",
        "string-dot-format-missing-arguments",
        "string-dot-format-mixing-automatic",
        "syntax-error",
        "tab-after-comma",
        "tab-after-keyword",
        "tab-after-operator",
        "tab-before-keyword",
        "tab-before-operator",
        "too-few-spaces-before-inline-comment",
        "too-many-blank-lines",
        "true-false-comparison",
        "type-comparison",
        "undefined-export",
        "undefined-local",
        "undefined-local-with-import-star",
        "undefined-local-with-import-star-usage",
        "undefined-local-with-nested-import-star-usage",
        "undefined-name",
        "unexpected-indentation",
        "unexpected-indentation-comment",
        "unexpected-spaces-around-keyword-parameter-equals",
        "unused-annotation",
        "unused-import",
        "unused-variable",
        "useless-semicolon",
        "whitespace-after-decorator",
        "whitespace-after-open-bracket",
        "whitespace-before-close-bracket",
        "whitespace-before-parameters",
        "whitespace-before-punctuation",
        "yield-outside-function",
    }
)


def _normalize_code(code: str) -> str:
    """Strip the trailing ':' ruff 0.17 prints after rule names ('invalid-syntax:')."""
    return code.rstrip(":") or code


def _severity_for(code: str) -> str:
    """Severity for a normalized lint code; see the rule table above."""
    if code in _ERROR_RULE_NAMES:
        return "error"
    return "error" if code[0] in ("E", "F") else "warning"


def _same_file(displayed: str, filepath: str) -> bool:
    """True if a path as printed by the linter names the same file as filepath.

    ruff prints cwd-relative paths for files under cwd and absolute ones
    otherwise, so compare by resolved identity rather than by string prefix.
    """
    try:
        shown = Path(displayed)
        if not shown.is_absolute():
            shown = Path(os.getcwd()) / shown
        return shown.resolve() == Path(filepath).resolve()
    except (OSError, ValueError, RuntimeError):
        # Unresolvable path: cannot prove identity; the caller then reports the
        # line as unparsed (fail-visible), never as clean.
        return False


def _parse_colon_format(output: str, filepath: str) -> List[LintIssue]:
    """
    Parse standard 'file:line:col: CODE message' format used by ruff and flake8.

    Lines are attributed to filepath when their path resolves to the same file
    (absolute, cwd-relative, bare basename or './'-prefixed). Fail-visible: if
    the output reports violations that could not be parsed, a single synthetic
    LINT-PARSE issue is appended instead of silently returning a clean result.
    """
    issues: List[LintIssue] = []
    unparsed = 0
    expected = 0
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        found = _FOUND_RE.match(line)
        if found:
            expected = int(found.group(1))
            continue
        if line.startswith(_NOISE_PREFIXES):
            continue
        m = _COLON_LINE_RE.match(line)
        if m and _same_file(m.group("path"), filepath):
            rest = m.group("rest").strip()
            space = rest.find(" ")
            code = _normalize_code(rest[:space].strip() if space > 0 else rest)
            msg = rest[space + 1 :].strip() if space > 0 else ""
            severity = _severity_for(code)
            issues.append(
                LintIssue(filepath, int(m.group("line")), int(m.group("col")), code, msg, severity)
            )
        else:
            unparsed += 1
    if unparsed or expected > len(issues):
        issues.append(
            LintIssue(
                filepath,
                0,
                0,
                "LINT-PARSE",
                f"linter reported violations that could not be parsed "
                f"({expected} reported, {len(issues)} parsed, {unparsed} unrecognised line(s)); "
                "run the linter directly",
                "error",
            )
        )
    return issues


def _parse_mypy_output(output: str, filepath: str) -> List[LintIssue]:
    """Parse mypy output: file.py:line: error: message"""
    issues = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Found") or line.startswith("Success"):
            continue
        for sev in ("error", "warning", "note"):
            marker = f": {sev}: "
            if marker in line:
                pre = line.split(marker)[0]
                msg = line.split(marker, 1)[1]
                parts = pre.rsplit(":", 1)
                try:
                    lineno = int(parts[-1]) if len(parts) > 1 else 0
                except ValueError:
                    lineno = 0
                issues.append(
                    LintIssue(
                        filepath, lineno, 0, "mypy", msg, "error" if sev == "error" else "warning"
                    )
                )
                break
    return issues


# ── Gated, isolated tool execution (WP2.1 slice 14c) ──────────────────────────

# flake8 and mypy are deliberately NOT executed. Both can load project-supplied
# Python from workspace config (flake8 local plugins, mypy ``plugins =``), and
# no isolation mechanism has been verified from an installed artifact (neither
# is installed on the reference device). Re-enable only after a documented,
# demonstrated isolation flag. Installed-but-skipped tools are listed by
# skipped_linters().
_SKIPPED_LINTERS = ("flake8", "mypy")


def skipped_linters() -> List[str]:
    """Installed linters that are intentionally not executed (isolation unverified)."""
    return [t for t in _SKIPPED_LINTERS if shutil.which(t)]


def _is_lintable_file(filepath: str) -> bool:
    """True only if filepath resolves to an existing regular file (not FIFO/dir/device)."""
    try:
        return Path(filepath).resolve().is_file()
    except (OSError, ValueError, RuntimeError):
        # NUL bytes, symlink loops, permission errors: not provably a regular
        # file, so refuse. Safe: refusal only skips external linting.
        return False


def _ruff_argv(filepath: str) -> List[str]:
    # --no-cache: ruff otherwise writes .ruff_cache/ into the checked project.
    # "--": a path beginning with '-' must never be parsed as an option.
    # Workspace ruff config is intentionally still honored (declarative only).
    return ["ruff", "check", "--no-cache", "--output-format=concise", "--", str(filepath)]


def _run_ruff_gated(filepath: str, action: str) -> Optional[str]:
    """Run ruff under an ACT gateway envelope; return combined output or None.

    None means refused/failed/unavailable; callers degrade as before. The
    audit label and failure reason are static (never paths or exception text).
    """
    from core.action_gateway import ACT, get_action_gateway

    def _execute() -> str:
        try:
            out = subprocess.run(
                _ruff_argv(filepath),
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            # Re-raise a static message: gate_exec audits str(exc), and the
            # original text embeds argv (the file path).
            raise RuntimeError("linter unavailable") from None
        return out.stdout + out.stderr

    decision = get_action_gateway().gate_exec(
        authority=ACT,
        action=action,
        command=action,
        confirm_available=False,
        execute=_execute,
    )
    if not decision.allowed:
        return None
    return decision.detail.get("result")


# ── Single-linter runner ───────────────────────────────────────────────────────


def run_linter(filepath: str, content: str = None) -> Tuple[List[LintIssue], str]:
    """
    Run the best available linter on a Python file.

    Priority: env CODEY_LINTER override → ruff → flake8 → ast syntax-only.

    Args:
        filepath: Path to the .py file.
        content:  Optional in-memory content (used for syntax-only fallback).

    Returns:
        (issues, linter_name) tuple.
        issues is empty list if file is clean or not a Python file.
    """
    p = Path(filepath)
    if p.suffix != ".py":
        return [], "none"

    # Respect user override
    preferred = os.environ.get("CODEY_LINTER", "").lower()

    def _try_ruff():
        out = _run_ruff_gated(filepath, "linter.ruff")
        if out is None:
            return None
        return _parse_colon_format(out, filepath), "ruff"

    # flake8/mypy are skipped (isolation unverified); see _SKIPPED_LINTERS.
    ruff_wanted = preferred in ("", "ruff") and shutil.which("ruff")
    if ruff_wanted and _is_lintable_file(filepath):
        res = _try_ruff()
        if res is not None:
            return res

    # Fallback: AST syntax check only
    src = content
    if src is None and _is_lintable_file(filepath):
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            src = None
    if src:
        err = check_syntax(src, filepath)
        if err:
            return [LintIssue(filepath, 0, 0, "SyntaxError", err, "error")], "ast"

    return [], "none"


# ── Multi-linter runner (for /review) ─────────────────────────────────────────


def run_all_linters(filepath: str) -> List[Tuple[str, List[LintIssue]]]:
    """
    Run ALL available linters and return a list of (tool_name, issues) pairs.
    Used by the /review command for a comprehensive report.
    """
    p = Path(filepath)
    if p.suffix != ".py":
        return []

    results = []

    if _is_lintable_file(filepath) and shutil.which("ruff"):
        out = _run_ruff_gated(filepath, "linter.ruff")
        if out is not None:
            results.append(("ruff", _parse_colon_format(out, filepath)))

    # flake8/mypy are skipped (isolation unverified); see _SKIPPED_LINTERS.

    # Always include syntax check as baseline
    if _is_lintable_file(filepath):
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
            err = check_syntax(src, filepath)
            syntax_issues = [LintIssue(filepath, 0, 0, "SyntaxError", err, "error")] if err else []
            results.append(("syntax", syntax_issues))
        except Exception:
            pass

    return results


# ── Formatting helpers ─────────────────────────────────────────────────────────


def format_issues(issues: List[LintIssue], max_issues: int = 8) -> str:
    """
    Format linter issues as a compact string to append to agent tool results.
    Errors shown first, warnings after.
    """
    if not issues:
        return ""
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity != "error"]
    shown = (errors + warnings)[:max_issues]
    lines = [f"\n\n[LINTER] {len(issues)} issue(s) found:"]
    for issue in shown:
        prefix = "  ✗" if issue.severity == "error" else "  ⚠"
        lines.append(f"{prefix} Line {issue.line}: [{issue.code}] {issue.message}")
    if len(issues) > max_issues:
        lines.append(f"  ... and {len(issues) - max_issues} more (run /review for full report)")
    lines.append("Review and fix any errors before the file is considered done.")
    return "\n".join(lines)


def get_available_linters() -> List[str]:
    """Return names of all installed linter tools."""
    return [t for t in ("ruff", "flake8", "pylint", "mypy") if shutil.which(t)]
