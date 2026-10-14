"""AST-derived coverage test for CAPABILITY_AUTHORITY (WP2.1 group 4,
NEW-910/911/912).

A hand-typed "every capability name that reaches call_capability()" list
is exactly the drift class core/agent.py's own _CRM_QUERY_CAPABILITIES
comment warns about (NEW-750): someone adds a new call_capability() call
site or a new _CRM_QUERY_CAPABILITIES entry and nobody notices the
classification table in ccos/core/plugin_manager.py never got updated.

This test derives the "must be classified" set from the actual source
(every literal first argument to a `*.call_capability(` call across
core/, tools/, main.py, restoricon_core/, plus the literal values of
core/agent.py's _CRM_QUERY_CAPABILITIES dict) instead of trusting a
second hand-typed list, and fails -- rather than silently skipping -- on
any call_capability() call site in that scope whose first argument is
not a string literal, outside the one already-known, already-reviewed
exception (core/agent.py's tool_crm_query(), which dispatches via its own
_CRM_QUERY_CAPABILITIES whitelist rather than a literal).
"""
import ast
from pathlib import Path
from typing import List, Optional, Set, Tuple

import pytest

from ccos.core.plugin_manager import CAPABILITY_AUTHORITY

REPO_ROOT = Path(__file__).resolve().parent.parent

# Scope matches the task's required coverage exactly: core/, tools/,
# main.py, restoricon_core/ -- NOT ccos/ (a dormant library per NEW-769,
# with its own non-literal call sites in planner.py/lifecycle_manager.py
# that are a different, already-disclosed concern) and NOT tests/ (mocks
# and synthetic fixture names, classified per-test-file instead, see
# tests/test_context_passing.py and ccos/tests/test_external_plugin_supervision.py).
SCOPE_DIRS = ("core", "tools", "restoricon_core")
SCOPE_FILES = ("main.py",)

# The one already-known, already-reviewed non-literal call_capability()
# call site: core/agent.py's tool_crm_query() dispatches via `cap_name`,
# a variable looked up from the _CRM_QUERY_CAPABILITIES whitelist dict
# (itself pulled into the required-coverage set below), not a literal
# capability name. Identified narrowly by file + enclosing function name,
# not just "any non-literal in core/agent.py", so a new non-literal call
# added anywhere else still fails this test.
_ALLOWED_NON_LITERAL = {("core/agent.py", "tool_crm_query")}


def _iter_scope_files():
    for dirname in SCOPE_DIRS:
        base = REPO_ROOT / dirname
        if not base.exists():
            continue
        yield from sorted(base.rglob("*.py"))
    for filename in SCOPE_FILES:
        f = REPO_ROOT / filename
        if f.exists():
            yield f


class _CallCapabilityVisitor(ast.NodeVisitor):
    """Collects every `<expr>.call_capability(...)` call's first argument,
    tagged with the enclosing function name (for the one allowed
    non-literal exception)."""

    def __init__(self):
        self.literal_names: Set[str] = set()
        self.non_literal_calls: List[Tuple[Optional[str], int]] = []
        self._func_stack: List[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "call_capability":
            first_arg = node.args[0] if node.args else None
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                self.literal_names.add(first_arg.value)
            else:
                enclosing = self._func_stack[-1] if self._func_stack else None
                self.non_literal_calls.append((enclosing, node.lineno))
        self.generic_visit(node)


def _scan_file(path: Path) -> _CallCapabilityVisitor:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = _CallCapabilityVisitor()
    visitor.visit(tree)
    return visitor


def test_every_literal_call_capability_name_is_classified():
    missing = []
    unexpected_non_literal = []

    for path in _iter_scope_files():
        rel = str(path.relative_to(REPO_ROOT))
        visitor = _scan_file(path)

        for name in sorted(visitor.literal_names):
            if name not in CAPABILITY_AUTHORITY:
                missing.append((rel, name))

        for enclosing_func, lineno in visitor.non_literal_calls:
            if (rel, enclosing_func) not in _ALLOWED_NON_LITERAL:
                unexpected_non_literal.append((rel, enclosing_func, lineno))

    assert not unexpected_non_literal, (
        "Found call_capability() call site(s) with a non-literal first "
        "argument outside the one already-known tool_crm_query whitelist "
        "pattern -- classify_capability coverage cannot be verified for "
        "these by this AST scan; add an explicit allowance only if this "
        "is genuinely another whitelist-dispatch pattern: "
        f"{unexpected_non_literal}"
    )
    assert not missing, (
        "Found call_capability() literal name(s) not present in "
        f"ccos.core.plugin_manager.CAPABILITY_AUTHORITY: {missing}"
    )


def test_crm_query_whitelist_values_are_classified():
    """core/agent.py's _CRM_QUERY_CAPABILITIES dict values are the actual
    capability names tool_crm_query() dispatches to (see the allowed
    non-literal exception above) -- classify every one of them too."""
    from core.agent import _CRM_QUERY_CAPABILITIES

    missing = sorted(
        name for name in _CRM_QUERY_CAPABILITIES.values() if name not in CAPABILITY_AUTHORITY
    )
    assert not missing, (
        f"_CRM_QUERY_CAPABILITIES value(s) not classified in CAPABILITY_AUTHORITY: {missing}"
    )


def test_scope_actually_found_call_sites():
    """Sanity check against an empty-scope false pass: if SCOPE_DIRS/
    SCOPE_FILES stop matching any real call_capability() call site (e.g.
    a rename), this test must fail loudly rather than the two tests above
    passing vacuously."""
    total_literal = set()
    total_non_literal = 0
    for path in _iter_scope_files():
        visitor = _scan_file(path)
        total_literal |= visitor.literal_names
        total_non_literal += len(visitor.non_literal_calls)
    assert total_literal or total_non_literal, (
        "No call_capability() call sites found at all under core/, tools/, "
        "main.py, restoricon_core/ -- SCOPE_DIRS/SCOPE_FILES likely stale."
    )
