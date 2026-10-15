"""AST-derived coverage test for BUSINESS_MUTATION_AUTHORITY (WP2.1 group 7,
NEW-919/920/921).

Mirrors tests/test_ccos_capability_authority_coverage.py's approach: derive
the "must be classified" set from the actual source rather than trusting a
second hand-typed list, and fail loudly -- not vacuously, not skip -- if
the scope stops matching any real call site.

The required-coverage set is every service method (keyed on the enclosing
function name, not the check line, to handle compound `or`/inline-
conditional has_permission() checks the same way the reference test does)
in restoricon_core/services/*.py whose body contains a
`<expr>.has_permission(PERM_X)` call where PERM_X's value is a permission
ROLE_AI_AGENT holds that is either write:/manage:-prefixed, or one of the
three action-write-capable exceptions
({"score:leads", "dispatch:work_orders", "log:communication"}) -- derived
programmatically from ROLE_PERMISSIONS[ROLE_AI_AGENT] directly, never a
hand-copied literal list, the same reasoning
tools/provision_ai_agent_auth.py::_compute_crm_reader_deny_permissions()
already documents for its own deny-list derivation.
"""
import ast
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from restoricon_core.auth import ROLE_AI_AGENT, ROLE_PERMISSIONS
import restoricon_core.auth as auth_mod
from restoricon_core.authority import ACT, BUSINESS_MUTATION_AUTHORITY, HIGH_IMPACT

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICES_DIR = REPO_ROOT / "restoricon_core" / "services"

_ACTION_WRITE_CAPABLE_EXTRAS = {"score:leads", "dispatch:work_orders", "log:communication"}


def _target_permissions() -> Set[str]:
    write_or_manage = {
        p for p in ROLE_PERMISSIONS[ROLE_AI_AGENT]
        if p.startswith("write:") or p.startswith("manage:")
    }
    extras = _ACTION_WRITE_CAPABLE_EXTRAS & ROLE_PERMISSIONS[ROLE_AI_AGENT]
    return write_or_manage | extras


def _perm_const_names() -> Dict[str, str]:
    """Map every PERM_* constant name in restoricon_core.auth to its string
    value (e.g. {"PERM_WRITE_CONTACTS": "write:contacts", ...})."""
    return {
        name: getattr(auth_mod, name)
        for name in dir(auth_mod)
        if name.startswith("PERM_")
    }


class _HasPermissionVisitor(ast.NodeVisitor):
    """Collects, per top-level service-class method, every PERM_* constant
    name referenced as a direct argument to a `<expr>.has_permission(...)`
    call anywhere in that method's body (walks the whole subtree, so a
    compound `or`/inline-conditional check is still found -- it does not
    need to be the first statement)."""

    def __init__(self, const_names: Set[str]):
        self._const_names = const_names
        self.hits: List[Tuple[str, Set[str]]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        found: Set[str] = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                func = n.func
                if isinstance(func, ast.Attribute) and func.attr == "has_permission":
                    for arg in n.args:
                        if isinstance(arg, ast.Name) and arg.id in self._const_names:
                            found.add(arg.id)
        if found:
            self.hits.append((node.name, found))
        # Do not recurse into nested function defs separately -- not a
        # pattern used in these service modules, and ast.walk above already
        # covers the whole subtree for the outer method.

    visit_AsyncFunctionDef = visit_FunctionDef


def _required_coverage_keys() -> Set[str]:
    const_names_by_value = _perm_const_names()
    const_names = set(const_names_by_value.keys())
    target_values = _target_permissions()

    required: Set[str] = set()
    for path in sorted(SERVICES_DIR.glob("*.py")):
        module = path.stem
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _HasPermissionVisitor(const_names)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visitor.visit_FunctionDef(node)

        for func_name, found_const_names in visitor.hits:
            found_values = {const_names_by_value[n] for n in found_const_names}
            if found_values & target_values:
                required.add(f"{module}.{func_name}")

    return required


def test_every_required_site_is_classified():
    required = _required_coverage_keys()
    missing = sorted(required - set(BUSINESS_MUTATION_AUTHORITY.keys()))
    assert not missing, (
        "Found service method(s) gated on a write:/manage:-prefixed "
        "ROLE_AI_AGENT permission (or score:leads/dispatch:work_orders/"
        "log:communication) with no entry in "
        f"restoricon_core.authority.BUSINESS_MUTATION_AUTHORITY: {missing}"
    )


def test_every_classified_value_is_act_or_high_impact():
    bad = {k: v for k, v in BUSINESS_MUTATION_AUTHORITY.items() if v not in (ACT, HIGH_IMPACT)}
    assert not bad, f"BUSINESS_MUTATION_AUTHORITY entries with an invalid classification value: {bad}"


def test_scope_actually_found_call_sites():
    """Sanity check against an empty-scope false pass: if the services
    directory stops matching any real has_permission() call site (e.g. a
    rename), this test must fail loudly rather than the test above passing
    vacuously."""
    required = _required_coverage_keys()
    assert required, (
        "No has_permission() call sites gated on a ROLE_AI_AGENT "
        "write:/manage: permission (or the three action-write-capable "
        "extras) found at all under restoricon_core/services/ -- the scan "
        "is likely stale."
    )
