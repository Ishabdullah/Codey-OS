#!/usr/bin/env python3
"""
AGI-alignment scorecard (WP1.4, CODEY_OS_MASTER_BLUEPRINT.md §21/§17.3).

An independent, new measurement -- NOT a reproduction of the unverifiable
"18/100" baseline cited in AGI_AUDIT_PLAN.md/AGI_AUDIT_LOG.md (no scoring
methodology for that number exists anywhere). See bench/scorecard.md for
the full rubric, category weights, and the mandatory read-the-rubric-
before-reading-the-score discipline.

HARD CONSTRAINT: this module never runs pytest, never imports a test
module to execute it, and never shells out to anything except itself (the
determinism test in tests/test_scorecard.py invokes THIS module via
`python -m bench.scorecard` in a subprocess -- that subprocess call lives
in the test file, not here). All test-structure checks are done via
`ast` parsing of test files -- structure, not execution -- because
pytest's pass/fail results are environment-dependent in this repo
specifically (missing llama-server, ambient HTTP_PROXY; see
bench/scorecard.md's "Constraint" section).

This is a read-only analysis tool over --repo-root. Its only write is
appending one line to <repo-root's own bench dir>/scorecard_history.jsonl
(skippable via --no-history). It never touches ~/.codeyOS or any other
real device state.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ENTRY_POINTS = ("main.py", "core/agent.py", "core/daemon.py")

EXCLUDED_DIR_PARTS = {"__pycache__", ".git"}
EXCLUDED_PATH_SUBSTRINGS = ("tests/fixtures/",)


# ─────────────────────────────────────────────────────────────────────────
# Repo-wide file discovery (sorted -- no filesystem-iteration-order
# nondeterminism; see bench/agents.py's copy2-over-iterdir() fix, WP1.2)
# ─────────────────────────────────────────────────────────────────────────


def _is_excluded(rel_posix: str) -> bool:
    parts = rel_posix.split("/")
    if any(p in EXCLUDED_DIR_PARTS for p in parts):
        return True
    if any(sub in rel_posix for sub in EXCLUDED_PATH_SUBSTRINGS):
        return True
    if parts and parts[-1].startswith("demo_"):
        return True
    return False


def discover_py_files(repo_root: Path) -> List[str]:
    """All .py files under repo_root, relative posix paths, sorted, with
    demo scripts / __pycache__ / .git / tests/fixtures excluded."""
    out = []
    for p in sorted(repo_root.rglob("*.py")):
        rel = p.relative_to(repo_root).as_posix()
        if not _is_excluded(rel):
            out.append(rel)
    return sorted(out)


# ─────────────────────────────────────────────────────────────────────────
# AST parsing, cached per file
# ─────────────────────────────────────────────────────────────────────────


class RepoAst:
    """Parses every discovered .py file once; records parse errors instead
    of crashing (SyntaxError-tolerant, per rubric's methodology section)."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.files = discover_py_files(repo_root)
        self.trees: Dict[str, ast.AST] = {}
        self.sources: Dict[str, str] = {}
        self.parse_errors: List[str] = []
        for rel in self.files:
            try:
                src = (repo_root / rel).read_text(encoding="utf-8", errors="replace")
                self.sources[rel] = src
                self.trees[rel] = ast.parse(src, filename=rel)
            except SyntaxError:
                self.parse_errors.append(rel)
        self.parse_errors.sort()

    def tree(self, rel: str) -> Optional[ast.AST]:
        return self.trees.get(rel)


# ─────────────────────────────────────────────────────────────────────────
# Import graph + reachability (BFS from ENTRY_POINTS), module-level AND
# function-local imports (ast.walk already descends into nested scopes)
# ─────────────────────────────────────────────────────────────────────────


def _file_to_module(rel: str) -> str:
    parts = rel[:-3].split("/") if rel.endswith(".py") else rel.split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _module_to_file(mod: str, file_set: Set[str]) -> Optional[str]:
    if not mod:
        return None
    path_prefix = mod.replace(".", "/")
    cand1 = f"{path_prefix}.py"
    cand2 = f"{path_prefix}/__init__.py"
    if cand1 in file_set:
        return cand1
    if cand2 in file_set:
        return cand2
    return None


def _resolve_relative_base(rel: str, level: int, module: Optional[str]) -> str:
    own_mod_parts = _file_to_module(rel).split(".")
    pkg_parts = own_mod_parts[:-1]  # package containing this file
    strip = max(level - 1, 0)
    if strip:
        pkg_parts = pkg_parts[: len(pkg_parts) - strip] if len(pkg_parts) >= strip else []
    base = list(pkg_parts)
    if module:
        base += module.split(".")
    return ".".join(base)


def build_import_graph(repo: RepoAst) -> Dict[str, Set[str]]:
    """edges[file] = set of local repo files it imports (directly)."""
    file_set = set(repo.files)
    edges: Dict[str, Set[str]] = {rel: set() for rel in repo.files}

    for rel in repo.files:
        tree = repo.tree(rel)
        if tree is None:
            continue
        candidates: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    candidates.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    base = _resolve_relative_base(rel, node.level, node.module)
                    if base:
                        candidates.add(base)
                        for alias in node.names:
                            candidates.add(f"{base}.{alias.name}")
                else:
                    if node.module:
                        candidates.add(node.module)
                        for alias in node.names:
                            candidates.add(f"{node.module}.{alias.name}")
        for mod in sorted(candidates):
            target = _module_to_file(mod, file_set)
            if target and target != rel:
                edges[rel].add(target)
    return edges


def imports_resolving_to_file(repo: "RepoAst", caller_rel: str, target_rel: str) -> Dict[str, str]:
    """local_alias -> original_name for every name imported into
    `caller_rel` (module-level or function-local; `ast.walk` already
    descends into nested scopes) via a statement that resolves to exactly
    `target_rel` -- handles both `from <mod> import X [as Y]` (absolute and
    relative) and plain `import <mod>` / `import <mod> as Y`. Resolution
    reuses `_resolve_relative_base` / `_module_to_file` (the same machinery
    `build_import_graph` uses) rather than a module-name substring/suffix
    match, so e.g. `ccos.core.context` can never be mistaken for
    `core.context`."""
    file_set = set(repo.files)
    tree = repo.tree(caller_rel)
    out: Dict[str, str] = {}
    if tree is None:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                base = _resolve_relative_base(caller_rel, node.level, node.module)
            else:
                base = node.module or ""
            if _module_to_file(base, file_set) == target_rel:
                for alias in node.names:
                    out[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _module_to_file(alias.name, file_set) == target_rel:
                    out[alias.asname or alias.name.split(".")[0]] = alias.name
    return out


def _call_root_name(node: ast.Call) -> Optional[str]:
    """Walk a (possibly chained) attribute expression down to the base
    `Name` id of a call's callee -- e.g. `_mem.to_natural_language(...)`
    -> `"_mem"`; `read_codeymd(...)` -> `"read_codeymd"`."""
    f = node.func
    while isinstance(f, ast.Attribute):
        f = f.value
    if isinstance(f, ast.Name):
        return f.id
    return None


def module_called_from(repo: "RepoAst", caller_rel: str, target_rel: str) -> Tuple[bool, str]:
    """True + a human-readable call-site detail iff `caller_rel` both
    imports a name resolving to `target_rel` AND actually invokes it (a
    direct call to an imported function, or a method/attribute call on an
    imported name) -- not merely imports it for a type hint or shared
    dataclass. This is a genuine call-site check, deliberately stricter
    than import-graph reachability (`reachable_from`'s BFS), for the
    sub-items whose own label specifically claims "call sites"."""
    aliases = imports_resolving_to_file(repo, caller_rel, target_rel)
    if not aliases:
        return False, f"{target_rel} not imported in {caller_rel}"
    tree = repo.tree(caller_rel)
    if tree is None:
        return False, f"{caller_rel} failed to parse"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            root = _call_root_name(node)
            if root and root in aliases:
                try:
                    call_src = ast.unparse(node.func) + "(...)"
                except Exception:
                    call_src = f"{root}(...)"
                lineno = getattr(node, "lineno", "?")
                return True, f"{caller_rel}:{lineno} calls {call_src}"
    return False, f"{target_rel} imported ({sorted(aliases.values())}) in {caller_rel} but never called"


MEMORY_TIER_FILES = ("core/memory_v2.py", "core/context.py", "core/embeddings.py")
PROMPT_BUILDER_FILE = "prompts/layered_prompt.py"


def memory_tier_callsites(repo: "RepoAst") -> List[Tuple[str, bool, str]]:
    """For each of the memory-tier *implementation* files -- tiers
    1/3/4/5/6 live in `core/memory_v2.py`, tier 1's carrier in the prompt
    path is `core/context.py`, tier 3 (long-term embeddings) is
    `core/embeddings.py` -- check whether `prompts/layered_prompt.py`
    genuinely CALLS into it, via `module_called_from`, not merely whether
    it is import-graph-reachable from some entry point.

    `core/codeymd.py` is deliberately EXCLUDED from this set even though
    `_get_project_block()` does call `read_codeymd()`: the blueprint
    census (`CODEY_OS_MASTER_BLUEPRINT.md` §15.1, `NEW-770`) found this is
    a *confirmed false positive* -- the "Project Memory" block it produces
    looks like memory tier 2 but is unrelated code (tier 2 stores an md5
    hash and is never read back at all). Counting codeymd as a reachable
    "memory tier" here would reproduce the exact false-positive finding
    this check exists to catch. Shared by 1c and 6c (see scorecard.md).
    """
    return [
        (tier_file,) + module_called_from(repo, PROMPT_BUILDER_FILE, tier_file)
        for tier_file in MEMORY_TIER_FILES
    ]


def reachable_from(entry_points: Tuple[str, ...], edges: Dict[str, Set[str]]) -> Set[str]:
    seen: Set[str] = set()
    frontier = [e for e in entry_points if e in edges]
    for e in frontier:
        seen.add(e)
    while frontier:
        nxt = []
        for f in frontier:
            for dep in sorted(edges.get(f, ())):
                if dep not in seen:
                    seen.add(dep)
                    nxt.append(dep)
        frontier = nxt
    return seen


# ─────────────────────────────────────────────────────────────────────────
# AST helper predicates
# ─────────────────────────────────────────────────────────────────────────


def _call_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name):
            return f.id
        if isinstance(f, ast.Attribute):
            return f.attr
    return None


def find_functions_by_name(tree: ast.AST, name: str) -> List[ast.FunctionDef]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            out.append(node)
    return out


def module_level_function_exists(tree: ast.AST, name: str) -> bool:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return True
    return False


def subtree_calls(node: ast.AST, name: str) -> int:
    return sum(1 for n in ast.walk(node) if _call_name(n) == name)


def subtree_has_assert(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Assert) for n in ast.walk(node))


def imported_names_from(tree: ast.AST, module_suffix: str) -> Set[str]:
    """Names imported via `from <mod ending in module_suffix> import X [as Y]`.
    Returns the set of X (the original, not the alias)."""
    out: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith(module_suffix):
            for alias in node.names:
                out.add(alias.name)
    return out


def repo_wide_callers(repo: RepoAst, func_name: str, exclude_files: Set[str]) -> List[str]:
    """Files (outside exclude_files) containing a Call to func_name."""
    out = []
    for rel in repo.files:
        if rel in exclude_files:
            continue
        tree = repo.tree(rel)
        if tree is None:
            continue
        if subtree_calls(tree, func_name) > 0:
            out.append(rel)
    return sorted(out)


def subscript_string_keys(node: ast.AST) -> Set[str]:
    """All string literal keys used as a Subscript slice anywhere in node."""
    keys: Set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Subscript):
            sl = n.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                keys.add(sl.value)
    return keys


# ─────────────────────────────────────────────────────────────────────────
# Category scorers. Each returns a list of sub-item dicts:
#   {label, points, max_points, detail}
# ─────────────────────────────────────────────────────────────────────────


def _subitem(label: str, points: float, max_points: float, detail: str) -> dict:
    points = max(0.0, min(points, max_points))
    return {"label": label, "points": round(points, 3), "max_points": max_points, "detail": detail}


def score_category_1(repo: RepoAst, reach: Set[str]) -> List[dict]:
    items = []

    # 1a
    needed = ["core/preferences.py", "core/learning.py", "prompts/layered_prompt.py"]
    present = [m for m in needed if m in reach]
    pts = 6.0 * (len(present) / len(needed))
    items.append(_subitem(
        "1a preferences write/read path reachable via core/learning.py bridge",
        pts, 6.0,
        f"reachable={sorted(present)} of {needed}",
    ))

    # 1b
    tree = repo.tree("core/trajectory.py")
    pts = 0.0
    detail = "core/trajectory.py not found"
    if tree is not None:
        has_bounded = module_level_function_exists(tree, "_bounded")
        has_budgeted = module_level_function_exists(tree, "_budgeted")
        run_fns = find_functions_by_name(tree, "instrument_run_agent")
        tool_fns = find_functions_by_name(tree, "instrument_execute_tool")
        run_uses = any(subtree_calls(f, "_budgeted") > 0 for f in run_fns)
        tool_uses = any(subtree_calls(f, "_budgeted") > 0 for f in tool_fns)
        conditions = [has_bounded, has_budgeted, run_uses, tool_uses]
        pts = 5.0 * (sum(conditions) / len(conditions))
        detail = (
            f"_bounded={has_bounded} _budgeted={has_budgeted} "
            f"instrument_run_agent uses _budgeted={run_uses} "
            f"instrument_execute_tool uses _budgeted={tool_uses}"
        )
    items.append(_subitem("1b trajectory full-fidelity recording (not truncate-at-record)", pts, 5.0, detail))

    # 1c
    tier_results = memory_tier_callsites(repo)
    present = [t for t, found, _ in tier_results if found]
    pts = 4.0 * (len(present) / len(tier_results))
    items.append(_subitem(
        "1c memory-tier modules genuinely called (AST call-site, not just imported/reachable) "
        "from layered_prompt.py",
        pts, 4.0,
        "; ".join(f"{t}: {d}" for t, _, d in tier_results),
    ))
    return items


def score_category_2(repo: RepoAst, reach: Set[str]) -> List[dict]:
    items = []

    skill_path = "ccos/core/skill_recombiner.py"
    exists = skill_path in repo.files
    is_reach = skill_path in reach
    pts = 5.0 if (exists and is_reach) else (2.0 if exists else 0.0)
    items.append(_subitem(
        "2a skill library reachable artifact (not just existing)",
        pts, 5.0,
        f"exists={exists} reachable_from_entry_points={is_reach}",
    ))

    exclude = {"core/trajectory.py"} | {f for f in repo.files if f.startswith("tests/")}
    callers = repo_wide_callers(repo, "verified_teacher_traces", exclude)
    pts = 5.0 if callers else 0.0
    items.append(_subitem(
        "2b teacher_traces read back into behavior (not write-only)",
        pts, 5.0,
        f"non-test callers outside core/trajectory.py: {callers or 'NONE (write-only)'}",
    ))
    return items


def score_category_3(repo: RepoAst, reach: Set[str]) -> List[dict]:
    goal_path = "ccos/core/goal_engine.py"
    exists = goal_path in repo.files
    is_reach = goal_path in reach
    pts = 10.0 if (exists and is_reach) else (3.0 if exists else 0.0)
    return [_subitem(
        "3a self-directed practice task generation reachable from entry points",
        pts, 10.0,
        f"exists={exists} reachable_from_entry_points={is_reach}",
    )]


def score_category_4(repo: RepoAst, repo_root: Path) -> List[dict]:
    items = []

    # 4a
    lock_exists = (repo_root / "bench" / "suite.lock").is_file()
    runner_tree = repo.tree("bench/runner.py")
    imports_verify = False
    calls_verify = False
    if runner_tree is not None:
        imports_verify = "verify_lock" in imported_names_from(runner_tree, "lock")
        calls_verify = subtree_calls(runner_tree, "verify_lock") > 0
    pts = 6.0 * (sum([lock_exists, imports_verify, calls_verify]) / 3)
    items.append(_subitem(
        "4a suite.lock exists and require_lock/verify_lock() is a real call",
        pts, 6.0,
        f"suite.lock exists={lock_exists} runner imports verify_lock={imports_verify} calls it={calls_verify}",
    ))

    # 4b
    test_tree = repo.tree("tests/test_trajectory.py")
    pts = 0.0
    detail = "tests/test_trajectory.py not found"
    if test_tree is not None:
        fns = find_functions_by_name(test_tree, "test_bench_tagged_episode_never_reaches_training_view")
        if not fns:
            detail = "function test_bench_tagged_episode_never_reaches_training_view not found"
        else:
            fn = fns[0]
            calls_accessor = subtree_calls(fn, "verified_training_episodes") > 0
            has_assert = subtree_has_assert(fn)
            pts = 7.0 * (sum([calls_accessor, has_assert]) / 2)
            detail = f"calls verified_training_episodes={calls_accessor} has_assert={has_assert}"
    items.append(_subitem(
        "4b bench-tagged-episode-excluded-from-training test exists and checks the right accessor",
        pts, 7.0, detail,
    ))

    # 4c
    gate_tree = repo.tree("bench/gate.py")
    pts = 0.0
    detail = "bench/gate.py not found"
    if gate_tree is not None:
        fns = find_functions_by_name(gate_tree, "decide")
        if fns:
            keys = subscript_string_keys(fns[0])
            expected = {"n", "cand_only", "base_only", "p_value", "ci95"}
            found = sorted(expected & keys)
            pts = 7.0 * (len(found) / len(expected))
            detail = f"condition keys found in decide(): {found} (of {sorted(expected)})"
        else:
            detail = "decide() function not found in bench/gate.py"
    items.append(_subitem(
        "4c gate.decide() structurally requires its conditions (AST-checked)",
        pts, 7.0, detail,
    ))

    # 4d
    pa_path = repo_root / "bench" / "power_analysis.md"
    pts = 0.0
    detail = "bench/power_analysis.md not found"
    if pa_path.is_file():
        text = pa_path.read_text(encoding="utf-8", errors="replace")
        found = "n=100" in text or "`n=100`" in text
        pts = 5.0 if found else 0.0
        detail = f"working-default n=100 recommendation found in file text: {found}"
    items.append(_subitem(
        "4d power_analysis.md's derived working-default n is read and cited",
        pts, 5.0, detail,
    ))
    return items


def score_category_5(repo: RepoAst) -> List[dict]:
    items = []

    # 5a
    reg_tree = repo.tree("core/model_registry.py")
    lora_tree = repo.tree("core/lora_import.py")
    reg_has_record = reg_tree is not None and module_level_function_exists(reg_tree, "record_adoption_attempt")
    lora_imports_record = False
    lora_calls_record = False
    lora_has_rollback = False
    rollback_wires_registry = False
    if lora_tree is not None:
        lora_imports_record = "record_adoption_attempt" in imported_names_from(lora_tree, "model_registry")
        lora_calls_record = subtree_calls(lora_tree, "record_adoption_attempt") > 0
        rb_fns = find_functions_by_name(lora_tree, "rollback_adoption")
        lora_has_rollback = bool(rb_fns)
        if rb_fns:
            fn = rb_fns[0]
            imports_in_fn = {
                alias.name
                for n in ast.walk(fn)
                if isinstance(n, ast.ImportFrom) and n.module and n.module.endswith("model_registry")
                for alias in n.names
            }
            rollback_wires_registry = (
                {"get_adoption", "mark_rolled_back"} <= imports_in_fn
                and subtree_calls(fn, "get_adoption") > 0
                and subtree_calls(fn, "mark_rolled_back") > 0
            )
    conditions = [reg_has_record, lora_imports_record, lora_calls_record, lora_has_rollback, rollback_wires_registry]
    pts = 8.0 * (sum(conditions) / len(conditions))
    items.append(_subitem(
        "5a model/adapter rollback: record_adoption_attempt + rollback_adoption real wiring "
        "(rollback_adoption lives in core/lora_import.py, not core/model_registry.py -- "
        "scored on the real shape, see scorecard.md's corrections section)",
        pts, 8.0,
        f"model_registry defines record_adoption_attempt={reg_has_record}; "
        f"lora_import imports it={lora_imports_record}, calls it={lora_calls_record}; "
        f"lora_import defines rollback_adoption={lora_has_rollback}, "
        f"wired to get_adoption/mark_rolled_back={rollback_wires_registry}",
    ))

    # 5b
    co_tree = repo.tree("ccos/core/capability_optimizer.py")
    write_exists = False
    if co_tree is not None:
        fns = find_functions_by_name(co_tree, "compare_and_upgrade")
        write_exists = any(subtree_calls(f, "copy2") > 0 for f in fns)
    exclude = {
        "ccos/core/capability_optimizer.py",
        "core/checkpoint.py",
        "core/lora_import.py",
    } | {f for f in repo.files if f.startswith("tests/")}
    readers = repo_wide_callers(repo, "previous_version", exclude)
    gap_correctly_identified = write_exists and not readers
    pts = (4.0 if write_exists else 0.0) + (3.0 if gap_correctly_identified else 0.0)
    items.append(_subitem(
        "5b CCOS capability-promotion backup write exists; read-back is a named gap "
        "(cite: NEW_ISSUES.md:20161, census A4 -- NOT NEW-813 as originally suggested, "
        "see scorecard.md's corrections section)",
        pts, 7.0,
        f"backup write (shutil.copy2) exists in compare_and_upgrade={write_exists}; "
        f"external readers of previous_version found={readers or 'none'}",
    ))
    return items


def score_category_6(repo: RepoAst, reach: Set[str], manual_entries: List[dict]) -> List[dict]:
    items = []

    # 6a (mirrors 1b)
    tree = repo.tree("core/trajectory.py")
    pts = 0.0
    if tree is not None:
        has_bounded = module_level_function_exists(tree, "_bounded")
        has_budgeted = module_level_function_exists(tree, "_budgeted")
        pts = 3.0 * (sum([has_bounded, has_budgeted]) / 2)
    items.append(_subitem("6a trajectories improved (full-fidelity recording) but still partial", pts, 3.0,
                           "mirrors 1b's _bounded/_budgeted check"))

    # 6b
    skill_path = "ccos/core/skill_recombiner.py"
    pts = 2.0 if skill_path in reach else 0.0
    items.append(_subitem("6b skill library reachable", pts, 2.0, f"reachable={skill_path in reach}"))

    # 6c (same lens as 1c, independent weighting -- see scorecard.md's
    # corrected methodology note: this is NOT an inverse of 1c's fraction,
    # it shares 1c's call-site check and scales it to this category's
    # own 3-point weight)
    tier_results = memory_tier_callsites(repo)
    present = [t for t, found, _ in tier_results if found]
    pts = 3.0 * (len(present) / len(tier_results))
    items.append(_subitem(
        "6c memory tiers genuinely called (AST call-site) from the prompt builder",
        pts, 3.0,
        "; ".join(f"{t}: {d}" for t, _, d in tier_results),
    ))

    # 6d
    corpus_hits = [f for f in repo.files if "corpus" in f.lower()]
    pts = 0.0 if not corpus_hits else 1.0
    items.append(_subitem("6d knowledge corpus artifact existence", pts, 2.0,
                           f"paths matching 'corpus': {corpus_hits or 'NONE (absent)'}"))

    # 6e -- manual
    manual_6e = [m for m in manual_entries if m.get("label", "").startswith("6e")]
    if manual_6e:
        m = manual_6e[0]
        items.append(_subitem(m["label"], m["points"], m["max_points"],
                               f"MANUAL, citation={m['citation']}: {m.get('note', '')}"))
    else:
        items.append(_subitem("6e benchmark ledger population", 0.0, 3.0, "MANUAL ENTRY MISSING"))

    # 6f
    registry_path = "ccos/core/capability_registry.py"
    exists = registry_path in repo.files
    is_reach = registry_path in reach
    pts = (1.0 if exists else 0.0) + (1.0 if (exists and is_reach) else 0.0)
    items.append(_subitem("6f capability registry exists but unenforced", pts, 2.0,
                           f"exists={exists} reachable={is_reach}"))

    return items


def score_category_7(repo: RepoAst, reach: Set[str], manual_entries: List[dict]) -> List[dict]:
    items = []

    # 7a
    ccos_core_files = [
        f for f in repo.files
        if f.startswith("ccos/core/") and not f.endswith("__init__.py")
    ]
    reachable_count = 0
    for f in ccos_core_files:
        mod = _file_to_module(f).split(".")[-1]
        has_outside_caller = any(
            (not caller.startswith("ccos/")) and subtree_calls(repo.tree(caller), mod) == 0
            for caller in []
        )
        # Real check: does any file outside ccos/ import this module by name?
        found = False
        for other in repo.files:
            if other.startswith("ccos/"):
                continue
            t = repo.tree(other)
            if t is None:
                continue
            for node in ast.walk(t):
                if isinstance(node, ast.ImportFrom) and node.module and mod in node.module.split("."):
                    found = True
                    break
                if isinstance(node, ast.Import):
                    if any(mod in alias.name.split(".") for alias in node.names):
                        found = True
                        break
            if found:
                break
        if found:
            reachable_count += 1
    total = len(ccos_core_files)
    pts = 3.0 * (reachable_count / total) if total else 0.0
    items.append(_subitem(
        "7a CCOS reachable-module count (real caller outside ccos/)",
        pts, 3.0,
        f"{reachable_count}/{total} ccos/core/*.py modules have >=1 importer outside ccos/",
    ))

    # 7b
    found_gateway = False
    for f in repo.files:
        t = repo.tree(f)
        if t is None:
            continue
        for node in ast.walk(t):
            if isinstance(node, ast.ClassDef) and node.name == "ActionGateway":
                found_gateway = True
                break
        if found_gateway:
            break
    pts = 2.0 if found_gateway else 0.0
    items.append(_subitem("7b Action Gateway existence", pts, 2.0,
                           f"ActionGateway class found={found_gateway}"))

    # 7c
    exclude = {"ccos/core/tool_router.py"} | {f for f in repo.files if f.startswith("tests/")}
    callers = repo_wide_callers(repo, "validate_tool_safety", exclude)
    reachable_callers = [c for c in callers if c in reach]
    if reachable_callers:
        pts = 3.0
    elif callers:
        pts = 1.0
    else:
        pts = 0.0
    items.append(_subitem(
        "7c sandbox/safety-validator real invocation sites "
        "(correction: a real non-test caller exists, see scorecard.md's corrections section)",
        pts, 3.0,
        f"non-test callers={callers or 'none'}; reachable-from-entry-points subset={reachable_callers or 'none'}",
    ))

    # 7d -- manual
    manual_7d = [m for m in manual_entries if m.get("label", "").startswith("7d")]
    if manual_7d:
        m = manual_7d[0]
        items.append(_subitem(m["label"], m["points"], m["max_points"],
                               f"MANUAL, citation={m['citation']}: {m.get('note', '')}"))
    else:
        items.append(_subitem("7d confident-falsehood sidecar check", 0.0, 2.0, "MANUAL ENTRY MISSING"))

    return items


# ─────────────────────────────────────────────────────────────────────────
# Manual sidecar loading -- hard error on any entry missing a citation
# ─────────────────────────────────────────────────────────────────────────


def load_manual_entries(path: Path) -> List[dict]:
    if not path.is_file():
        raise SystemExit(f"FATAL: manual sidecar file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"FATAL: manual sidecar file is not valid JSON: {path} ({e})")
    if not isinstance(data, list):
        raise SystemExit(f"FATAL: manual sidecar file must be a JSON list: {path}")
    required = {"category", "label", "points", "max_points", "citation"}
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise SystemExit(f"FATAL: manual sidecar entry #{i} is not an object: {path}")
        missing = required - set(entry.keys())
        if missing:
            raise SystemExit(
                f"FATAL: manual sidecar entry #{i} ({entry.get('label', '?')}) missing required "
                f"field(s) {sorted(missing)} in {path}. A manual score with no citation is exactly "
                "the 'number pushed up by relabeling' CLAUDE.md rule 1 prohibits -- this is not "
                "optional defensive code."
            )
        if not entry.get("citation") or not str(entry["citation"]).strip():
            raise SystemExit(
                f"FATAL: manual sidecar entry #{i} ({entry.get('label', '?')}) has an empty "
                f"'citation' field in {path}."
            )
    return data


# ─────────────────────────────────────────────────────────────────────────
# Top-level scoring
# ─────────────────────────────────────────────────────────────────────────


def compute_scorecard(repo_root: Path, manual_path: Path) -> dict:
    repo = RepoAst(repo_root)
    edges = build_import_graph(repo)
    entry_points = tuple(e for e in ENTRY_POINTS if e in edges)
    reach = reachable_from(entry_points, edges)

    manual_entries = load_manual_entries(manual_path)

    categories = {
        "1_experience_to_behavior": score_category_1(repo, reach),
        "2_skills_developmental_history": score_category_2(repo, reach),
        "3_bounded_practice_curiosity": score_category_3(repo, reach),
        "4_evaluator_integrity": score_category_4(repo, repo_root),
        "5_rollback_reversibility": score_category_5(repo),
        "6_brain_swap_independence": score_category_6(repo, reach, manual_entries),
        "7_safety_honesty": score_category_7(repo, reach, manual_entries),
    }

    category_totals = {}
    automated_subtotal = 0.0
    manual_subtotal = 0.0
    for cat, items in categories.items():
        cat_points = sum(i["points"] for i in items)
        cat_max = sum(i["max_points"] for i in items)
        category_totals[cat] = {"points": round(cat_points, 3), "max_points": cat_max, "items": items}
        for i in items:
            if "MANUAL" in i["detail"]:
                manual_subtotal += i["points"]
            else:
                automated_subtotal += i["points"]

    total_score = round(automated_subtotal + manual_subtotal, 3)

    scorecard_md_path = repo_root / "bench" / "scorecard.md"
    scorecard_md_sha256 = None
    if scorecard_md_path.is_file():
        scorecard_md_sha256 = hashlib.sha256(scorecard_md_path.read_bytes()).hexdigest()

    result = {
        "total_score": total_score,
        "max_score": 100,
        "automated_subtotal": round(automated_subtotal, 3),
        "manual_subtotal": round(manual_subtotal, 3),
        "categories": category_totals,
        "entry_points": sorted(entry_points),
        "reachable_file_count": len(reach),
        "total_scanned_files": len(repo.files),
        "parse_errors": repo.parse_errors,
        "scorecard_md_sha256": scorecard_md_sha256,
        "repo_root": str(repo_root),
    }
    return result


def render_markdown(result: dict) -> str:
    lines = [
        "# AGI-Alignment Scorecard Result",
        "",
        f"**Total score: {result['total_score']} / {result['max_score']}** "
        f"(automated: {result['automated_subtotal']}, manual: {result['manual_subtotal']})",
        "",
        "This is an independent measurement, not a reproduction of the unverifiable "
        "18/100 baseline -- see bench/scorecard.md.",
        "",
        "| Category | Points | Max |",
        "|---|---:|---:|",
    ]
    for cat, data in sorted(result["categories"].items()):
        lines.append(f"| {cat} | {data['points']} | {data['max_points']} |")
    lines.append("")
    lines.append("## Sub-items")
    for cat, data in sorted(result["categories"].items()):
        lines.append(f"\n### {cat}")
        for item in data["items"]:
            lines.append(f"- **{item['label']}**: {item['points']}/{item['max_points']} -- {item['detail']}")
    lines.append("")
    lines.append(f"Scanned {result['total_scanned_files']} files, {result['reachable_file_count']} "
                  f"reachable from entry points {result['entry_points']}.")
    if result["parse_errors"]:
        lines.append(f"Parse errors (excluded from analysis, not crashed on): {result['parse_errors']}")
    return "\n".join(lines)


def append_history(repo_root: Path, result: dict) -> None:
    history_path = repo_root / "bench" / "scorecard_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    category_scores = {cat: data["points"] for cat, data in result["categories"].items()}
    commit_sha = None
    head_path = repo_root / ".git" / "HEAD"
    if head_path.is_file():
        head_text = head_path.read_text(encoding="utf-8", errors="replace").strip()
        if head_text.startswith("ref:"):
            ref_rel = head_text.split(" ", 1)[1].strip()
            ref_path = repo_root / ".git" / ref_rel
            if ref_path.is_file():
                commit_sha = ref_path.read_text(encoding="utf-8", errors="replace").strip()
        else:
            commit_sha = head_text
    entry = {
        "timestamp": time.time(),
        "repo_root": str(repo_root),
        "commit_sha": commit_sha,
        "total_score": result["total_score"],
        "category_scores": category_scores,
        "scorecard_md_sha256": result["scorecard_md_sha256"],
    }
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AGI-alignment scorecard (WP1.4)")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--manual-file", default=None)
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    manual_path = Path(args.manual_file) if args.manual_file else repo_root / "bench" / "scorecard_manual.json"

    result = compute_scorecard(repo_root, manual_path)

    # JSON output is deterministic across runs on the same tree: no timestamps,
    # sorted keys, no dependency on iteration order (all inputs already sorted).
    print(json.dumps(result, sort_keys=True, indent=2))
    print()
    print(render_markdown(result))

    if not args.no_history:
        append_history(repo_root, result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
