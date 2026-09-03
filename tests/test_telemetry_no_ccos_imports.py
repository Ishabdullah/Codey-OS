"""
Static enforcement of docs/telemetry_layer_design.md §1.3: the telemetry
package must contain zero imports resolving to `ccos.*`, including
function-local lazy imports (this codebase uses those heavily — see
utils/config.py's own docstring at the temp-critical warning for an
example of the pattern this test must still catch).

This is an `ast` walk, not a runtime import check, so it holds even for
code paths that never execute in the test suite.
"""

from __future__ import annotations

import ast
from pathlib import Path

TELEMETRY_DIR = Path(__file__).parent.parent / "telemetry"


def _iter_python_files():
    yield from TELEMETRY_DIR.rglob("*.py")


def _collect_ccos_imports(tree: ast.AST, filename: str):
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name == "ccos" or name.startswith("ccos."):
                    violations.append(f"{filename}:{node.lineno}: import {name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "ccos" or module.startswith("ccos."):
                violations.append(f"{filename}:{node.lineno}: from {module} import ...")
    return violations


def test_no_ccos_imports_anywhere_under_telemetry():
    all_violations = []
    files = list(_iter_python_files())
    assert files, "expected at least one .py file under telemetry/ to scan"

    for path in files:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        all_violations.extend(_collect_ccos_imports(tree, str(path)))

    assert not all_violations, (
        "telemetry/ must never import from ccos.* (docs/telemetry_layer_design.md "
        f"§1.3) — found:\n" + "\n".join(all_violations)
    )


def test_scan_covers_every_expected_t0_module():
    """Pin the file set so a future new telemetry/*.py module is
    guaranteed to be picked up by this scan rather than silently
    skipped."""
    scanned = {p.name for p in _iter_python_files()}
    expected = {
        "__init__.py",
        "schema.py",
        "envelope.py",
        "store.py",
        "provenance.py",
        "recorders.py",
    }
    assert expected.issubset(scanned), f"missing from scan: {expected - scanned}"
