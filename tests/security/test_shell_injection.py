#!/usr/bin/env python3
"""
Shell-injection tests against the code production actually runs (WP2.3).

Why this file was rewritten: it used to test SHELL_METACHARACTERS /
validate_command_structure, which no production path ever called (deleted in
WP2.3). The real injection guard in tools.shell_tools.shell() is that argv is
built with shlex.split() and run WITHOUT a shell, so metacharacters are
literal arguments; everything else is the classifier + gateway fail-closed
rule for HIGH_IMPACT commands. These tests drive the real shell() with a real
subprocess in a tmp dir, spy on subprocess.run, and AST-scan the module for
shell=True so a switch to a shell executor fails loudly.
"""

import ast
import os
import subprocess
from pathlib import Path

import pytest

import tools.shell_tools as shell_tools
from core.action_gateway import HIGH_IMPACT, READ
from tools.shell_tools import classify_shell_command, shell

# Former SHELL_METACHARACTERS set; each must stay inert under shell().
METACHARS = [";", "&&", "||", "|", "`", "$(", "${", "<(", ">(", ">", "<", "&", "\\"]
# shlex treats backslash as an escape, so its text is not reproduced literally.
LITERAL_OK = [m for m in METACHARS if m != "\\"]


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("meta", METACHARS)
def test_metacharacter_never_runs_second_command(workdir, meta):
    """A metachar between two commands must not execute the second one."""
    out = shell(f"echo A {meta} touch PWNED", yolo=True)
    assert not (workdir / "PWNED").exists(), out
    assert not os.path.exists("PWNED")


@pytest.mark.parametrize("meta", LITERAL_OK)
def test_metacharacter_is_literal_argv(workdir, meta):
    out = shell(f"echo A {meta} touch PWNED", yolo=True)
    assert out == f"A {meta} touch PWNED"
    assert not (workdir / "PWNED").exists()


def test_subprocess_run_never_gets_shell_true(workdir, monkeypatch):
    calls = []
    real_run = subprocess.run

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(shell_tools.subprocess, "run", spy)
    shell("echo hello ; touch PWNED", yolo=True)
    shell("ls", yolo=True)
    assert calls, "spy never saw subprocess.run"
    for args, kwargs in calls:
        assert isinstance(args[0], list)
        assert not kwargs.get("shell")
    assert not (workdir / "PWNED").exists()


def test_no_subprocess_call_in_shell_tools_uses_shell_true():
    """Tripwire: the no-shell argv model is what makes metachars inert."""
    tree = ast.parse(Path(shell_tools.__file__).read_text())
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        owner = getattr(func, "value", None)
        if isinstance(owner, ast.Name) and owner.id == "subprocess":
            for kw in node.keywords:
                if kw.arg == "shell" and not (
                    isinstance(kw.value, ast.Constant) and kw.value.value is False
                ):
                    offenders.append(node.lineno)
    assert offenders == []


HIGH_CMDS = [
    "sh -c 'x'",
    "bash -lc 'x'",
    "python3 -c 'x'",
    "find . -exec x {} +",
    "xargs x",
    "ls | bash",
    "ls; rm -rf /",
]


@pytest.mark.parametrize("cmd", HIGH_CMDS)
def test_high_impact_classified_and_refused_under_yolo(workdir, monkeypatch, cmd):
    assert classify_shell_command(cmd) == HIGH_IMPACT
    run_mock_calls = []
    monkeypatch.setattr(
        shell_tools.subprocess, "run", lambda *a, **k: run_mock_calls.append(a)
    )
    out = shell(cmd, yolo=True)
    assert out.startswith("[BLOCKED]"), out
    assert run_mock_calls == []


def test_chained_read_commands_classify_read_only_because_no_shell():
    # `ls && cat /etc/passwd` is READ ONLY because shell() runs argv without a
    # shell, so `&&` is a literal argument to ls. If shell() ever switches to
    # a shell executor this expectation must be revisited.
    assert classify_shell_command("ls && cat /etc/passwd") == READ


# The daemon prefix gate (_daemon_shell refuses before shell() is reached) is
# already pinned by tests/test_shell_refusal_accounting.py
# ::test_each_daemon_refusal_one_audit_no_shell; not duplicated here.
