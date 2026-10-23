"""WP2.1 group 15 census tool (slice G15a): mechanical, re-runnable boundary census.

Design (docs/wp2_1_group15_scope.md section 2):

* PARSE-ONLY.  This module never imports, compiles-and-runs or executes any
  scanned code (NEW-855: importing Codey modules creates state).  Python files
  are read with ``ast.parse``; shell files, workflow YAML and JSON manifests
  are scanned as text / ``json``.  Run it as ``python3 -I tools/wp21_census.py``.
* READ-ONLY w.r.t. the repo.  It writes only below an explicit ``--out``
  directory (default: a ``wp21_census`` directory under the system temp dir).
  The only subprocesses are read-only git queries (``rev-parse``, ``archive``,
  ``status``) run with ``GIT_OPTIONAL_LOCKS=0`` so git does not refresh the index.
* The default source is a ``git archive`` snapshot of a revision, so another
  agent's uncommitted working-tree edits cannot leak in.  The dirty-path list
  is recorded in ``run_meta.json`` and each row carries a ``dirty`` flag.
* Row keys are ``file::qualname::callee::ordinal`` -- never line numbers.
  Line numbers are reported in a separate column only.  The ordinal is
  POSITIONAL: it numbers same-callee calls within one qualname in source order.
  Swapping two identical-callee calls in one function therefore yields identical
  keys, and a register decision silently follows the swap (it stays attached to
  "the Nth call", not to the call it was made about).  Considered and rejected
  (S1): a hash of the first argument's source text as an extra key component.
  It would be stable under line shifts and reordering of unrelated statements,
  but it changes every existing register key (a migration of the whole register),
  makes any edit to an argument look like stale+new rows, and still cannot
  separate calls with identical arguments.  So this is document-only: a reviewer
  who sees a diff that reorders same-callee calls in one function must re-check
  the dispositions of those rows by hand.
* ``scan.tsv`` and the other row TSVs are a pure function of the revision (no
  working-tree state); the dirty-path list is only in ``run_meta.json``.
* The tool does not judge mediation.  It enumerates candidate rows and (a) seeds
  a disposition only where evidence is purely mechanical, (b) diffs the rows
  against the committed disposition register (``evaluate_coverage``).
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import warnings
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

TOOL_VERSION = "2"

# --------------------------------------------------------------------------
# Scope
# --------------------------------------------------------------------------

# Top-level directories never scanned, each with a reason that is printed in
# every report.  Everything else that holds .py/.sh/manifests IS in scope.
EXCLUDED_DIRS: Dict[str, str] = {
    "tests": "test code (spec 2.3: only tests/** and conftest.py are skipped)",
    "docs": "documentation",
    "assets": "static assets",
    ".claude": "agent definitions/memory, not product code",
    ".git": "VCS metadata",
}
# Path components that exclude a file wherever they appear.
EXCLUDED_COMPONENTS = {"tests", "__pycache__", "node_modules"}

# Gate vocabulary (spec 2.3): names of mediator calls.
GATE_NAMES: Set[str] = {
    "gate_exec", "gate_write", "gate_append", "gate_read", "refuse_exec",
    "persist_coalesced", "_authority_for", "call_capability",
}

# Keyword argument that carries the thunk a gate EXECUTES (verified against the
# signatures in core/action_gateway.py and core/bookkeeping_persist.py at HEAD
# 941ec3f: gate_exec(execute=...), persist_coalesced(write=...)).
GATE_THUNK_KWARGS: Dict[str, Tuple[str, ...]] = {
    "gate_exec": ("execute",),
    "persist_coalesced": ("write",),
}

# The disposition taxonomy: 11 dispositions + UNKNOWN (initial state).
CLASSES: Tuple[str, ...] = (
    "GATED", "NATIVE_AUTHORITY", "BOOKKEEPING", "OPERATOR_BOOTSTRAP",
    "LOOPBACK_IPC", "READ_NOEFFECT", "DORMANT", "OPERATOR_SCRIPT_RUNNABLE",
    "EXCLUDED_SIBLING", "FALSE_POSITIVE", "UNMEDIATED", "UNKNOWN",
)
REACH_VALUES = {
    "", "prod-confirmless", "prod-interactive", "operator-only", "dormant",
    "test-only", "sibling",
}
SEVERITIES = {"", "HIGH", "MEDIUM", "LOW"}
QUALNAME_LEVEL_CLASSES = {"NATIVE_AUTHORITY", "BOOKKEEPING", "UNKNOWN"}
REGISTER_COLUMNS = (
    "key", "class", "mediator", "evidence", "reach", "severity", "finding",
    "decided_by", "reviewed_by", "first_seen_rev", "count",
)

# --------------------------------------------------------------------------
# Pattern tables (hashed into run_meta so a re-run can prove same pattern set)
# --------------------------------------------------------------------------

OS_FS = {
    "remove", "unlink", "rename", "renames", "replace", "rmdir", "removedirs",
    "makedirs", "mkdir", "chmod", "chown", "link", "symlink", "truncate",
    "ftruncate", "utime", "mkfifo", "write", "open",
}
FS_EXACT = {f"os.{n}" for n in OS_FS} | {
    f"shutil.{n}" for n in (
        "copy", "copy2", "copyfile", "copytree", "move", "rmtree",
        "make_archive", "unpack_archive", "copymode")
} | {
    f"tempfile.{n}" for n in (
        "mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryDirectory")
} | {"shelve.open", "dbm.open", "pickle.dump", "logging.FileHandler"}
ATTR_FS = {
    "write_text", "write_bytes", "writelines", "touch", "mkdir", "unlink",
    "rmdir", "symlink_to", "hardlink_to", "chmod", "truncate",
}
# Path.rename/replace take one argument; str.replace takes two.
ATTR_FS_ONE_ARG = {"rename", "replace"}
OPEN_EXACT = {"open", "io.open", "codecs.open", "os.fdopen", "gzip.open",
              "bz2.open", "lzma.open"}
ARCHIVE_MODE = {"zipfile.ZipFile": 1, "tarfile.open": 1, "tarfile.TarFile": 1}

EXEC_EXACT = {
    "subprocess.run", "subprocess.Popen", "subprocess.call",
    "subprocess.check_call", "subprocess.check_output", "subprocess.getoutput",
    "subprocess.getstatusoutput", "os.system", "os.popen", "os.fork",
    "os.forkpty", "pty.spawn", "multiprocessing.Process",
    "concurrent.futures.ProcessPoolExecutor",
}
EXEC_PREFIX = ("os.exec", "os.spawn", "asyncio.create_subprocess_")
KILL_EXACT = {"os.kill", "os.killpg", "signal.pthread_kill", "signal.raise_signal"}
KILL_ATTR = {"kill", "terminate", "send_signal"}
NET_PREFIX = (
    "socket.", "ssl.", "http.client.", "requests.", "httpx.", "aiohttp.",
    "websockets.", "smtplib.", "ftplib.", "http.server.", "socketserver.",
    "google.cloud.", "urllib3.", "xmlrpc.client.",
)
NET_EXACT = {"urllib.request.urlopen", "urllib.request.Request",
             "urllib.request.build_opener", "uvicorn.run"}
DYN_EXACT = {
    "exec", "eval", "compile", "__import__", "importlib.import_module",
    "importlib.util.spec_from_file_location", "importlib.util.module_from_spec",
    "pickle.load", "pickle.loads", "marshal.load", "marshal.loads", "yaml.load",
}
DYN_PREFIX = ("runpy.", "ctypes.")
ENV_CALLS = {
    "os.putenv", "os.unsetenv", "os.chdir", "os.umask", "os.environ.update",
    "os.environ.setdefault", "os.environ.pop", "os.environ.clear",
    "sys.path.append", "sys.path.insert", "sys.path.extend", "sys.path.remove",
}
CRED_CALLS_PREFIX = ("keyring.",)
CRED_CALLS_EXACT = {"getpass.getpass"}
CRED_ENV_RE = re.compile(r"(?i)(key|token|secret|passw|credential|auth)")
CRED_PATH_PARTS = {".ssh", ".netrc", "gcloud", "credentials", ".env",
                   "id_rsa", ".gnupg", "credentials.json"}
CRED_ARGV = {"openssl", "gpg", "age", "keyring"}
SQL_WRITE_RE = re.compile(
    r"^\s*(?:--[^\n]*\n\s*)*(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|REPLACE|"
    r"VACUUM|ATTACH|PRAGMA\s+\w+\s*=)", re.IGNORECASE)
SQL_ANY_WRITE_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|REPLACE|VACUUM|ATTACH)\b",
    re.IGNORECASE)

# Shell / launcher / workflow text patterns: (id, regex)
_W = r"(?<![\w./$-])"
SHELL_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("rm", _W + r"rm(?![\w./-])"),
    ("mv", _W + r"mv(?![\w./-])"),
    ("cp", _W + r"cp(?![\w./-])"),
    ("ln", _W + r"ln(?![\w./-])"),
    ("chmod", _W + r"chmod(?![\w./-])"),
    ("chown", _W + r"chown(?![\w./-])"),
    ("mkdir", _W + r"mkdir(?![\w./-])"),
    ("tee", _W + r"tee(?![\w./-])"),
    ("dd", _W + r"dd(?![\w./-])\s+\w+="),
    ("sed-i", _W + r"sed\s+(?:-\w*\s+)*-i"),
    ("redirect", r"(?<![\d&<>=-])>>?\s*(?!/dev/null|&)[^\s&>|]"),
    ("kill", _W + r"(?:kill|pkill|killall)(?![\w./-])"),
    ("net-fetch", _W + r"(?:curl|wget|scp|rsync|ssh)(?![\w./-])"),
    ("git-write", _W + r"git\s+(?:-\S+\s+)*(?:push|commit|clone|reset|clean|checkout|stash)\b"),
    ("gh", _W + r"gh(?![\w./-])\s+\w+"),
    ("pkg-install", _W + r"(?:pip3?|pkg|apt(?:-get)?|npm)\s+(?:-\S+\s+)*(?:install|uninstall|remove)\b"),
    ("detach", _W + r"(?:nohup|setsid)(?![\w./-])"),
    ("eval-source-exec", _W + r"(?:eval|source|exec)(?![\w./-])\s+\S"),
    ("python-c", _W + r"python3?\s+(?:-\w+\s+)*-c\b"),
    ("termux-cmd", _W + r"termux-[\w-]+"),
    ("db-llm-tools", _W + r"(?:sqlite3|litestream|cloudflared|llama-server)(?![\w./-])"),
    ("crontab", _W + r"crontab(?![\w./-])"),
    ("startup-file", r"\.bashrc|\.termux/boot|\.profile\b"),
)
_SHELL_RES = tuple((pid, re.compile(rx)) for pid, rx in SHELL_PATTERNS)
SHELL_FUNC_RE = re.compile(r"^\s*(?:function\s+)?([A-Za-z_][\w:-]*)\s*\(\)\s*\{?")

MANIFEST_EXEC_KEYS = {"implementation", "command", "entry_point", "entrypoint",
                      "exec", "script"}
MANIFEST_POLICY_KEYS = {"permissions", "resource_limits"}

ENV_CLASS_SELECTOR = {"CODEY_LLAMA_SERVER", "CODEY_LLAMA_LIB", "CODEY_LINTER"}
ENV_CLASS_AUTHORITY = {"ALLOW_SELF_MOD", "CODEY_SELF_IMPROVE", "CODEY_TRAJECTORY"}
ENV_CLASS_PATH = {"CODEY_STATE_DIR", "CODEY_ACTION_GATEWAY_AUDIT",
                  "CODEY_CONFIG_PATH", "RESTORICON_DB_PATH"}


def pattern_set_hash() -> str:
    payload = json.dumps({
        "v": TOOL_VERSION,
        "gate": sorted(GATE_NAMES), "thunk_kw": sorted(GATE_THUNK_KWARGS.items()),
        "fs": [sorted(FS_EXACT), sorted(ATTR_FS), sorted(ATTR_FS_ONE_ARG),
               sorted(OPEN_EXACT), sorted(ARCHIVE_MODE)],
        "exec": [sorted(EXEC_EXACT), list(EXEC_PREFIX)],
        "kill": [sorted(KILL_EXACT), sorted(KILL_ATTR)],
        "net": [list(NET_PREFIX), sorted(NET_EXACT)],
        "dyn": [sorted(DYN_EXACT), list(DYN_PREFIX)],
        "env": sorted(ENV_CALLS),
        "cred": [list(CRED_CALLS_PREFIX), sorted(CRED_CALLS_EXACT),
                 CRED_ENV_RE.pattern, sorted(CRED_PATH_PARTS), sorted(CRED_ARGV)],
        "sql": [SQL_WRITE_RE.pattern],
        "shell": [list(p) for p in SHELL_PATTERNS],
        "manifest": [sorted(MANIFEST_EXEC_KEYS), sorted(MANIFEST_POLICY_KEYS)],
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


# --------------------------------------------------------------------------
# Row model
# --------------------------------------------------------------------------

@dataclasses.dataclass
class Row:
    key: str
    kind: str          # py | shell | manifest
    category: str
    file: str
    qualname: str
    callee: str
    ordinal: int
    line: int
    detail: str = ""
    lexgate: str = ""   # "" | "lambda:<gate>" | "helper:<gate>"
    refs: str = ""      # informational: reference count of enclosing function name
    sig0: bool = False  # os.kill(pid, 0) liveness probe
    dirty: bool = False

    @property
    def top(self) -> str:
        return self.file.split("/", 1)[0] if "/" in self.file else "root"


def make_key(file: str, qualname: str, callee: str, ordinal: int) -> str:
    return f"{file}::{qualname}::{callee}::{ordinal}"


def qual_key(file: str, qualname: str, category: str) -> str:
    return f"{file}::{qualname}::{category}"


# --------------------------------------------------------------------------
# Python AST scanner
# --------------------------------------------------------------------------

def _collect_aliases(tree: ast.AST) -> Dict[str, str]:
    amap: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    amap[a.asname] = a.name
                else:
                    root = a.name.split(".")[0]
                    amap[root] = root
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                amap[a.asname or a.name] = f"{node.module}.{a.name}"
    return amap


def _collect_from_roots(tree: ast.AST) -> Dict[str, str]:
    """Local name -> source module for every ``from X import Y [as Z]`` binding."""
    out: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                out[a.asname or a.name] = node.module
    return out


def _known_callee(c: str) -> bool:
    """True iff the resolved dotted name matches any module-function pattern."""
    return (c in FS_EXACT or c in OPEN_EXACT or c in ARCHIVE_MODE or c in EXEC_EXACT
            or c in KILL_EXACT or c in NET_EXACT or c in DYN_EXACT or c in ENV_CALLS
            or c in CRED_CALLS_EXACT or c == "sqlite3.connect"
            or c.startswith(EXEC_PREFIX + NET_PREFIX + DYN_PREFIX + CRED_CALLS_PREFIX
                            + ("logging.handlers.",)))


def _module_str_consts(tree: ast.Module) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for st in tree.body:
        if (isinstance(st, ast.Assign) and len(st.targets) == 1
                and isinstance(st.targets[0], ast.Name)
                and isinstance(st.value, ast.Constant)
                and isinstance(st.value.value, str)):
            out[st.targets[0].id] = st.value.value
    return out


def _resolve(node: ast.AST, aliases: Dict[str, str]) -> str:
    """Dotted callee name.  Unresolvable receivers collapse to '*.<attr>'."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parts: List[str] = [node.attr]
        cur: ast.AST = node.value
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name) and cur.id in aliases:
            return ".".join([aliases[cur.id]] + list(reversed(parts)))
        return "*." + node.attr
    return "*"


def _const_str(node: Optional[ast.AST], consts: Dict[str, str]) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in consts:
        return consts[node.id]
    return None


def _mode_arg(call: ast.Call, pos: int) -> Tuple[bool, Optional[str]]:
    """(found, constant-mode-or-None-if-dynamic)."""
    for kw in call.keywords:
        if kw.arg == "mode":
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return True, kw.value.value
            return True, None
    if len(call.args) > pos:
        a = call.args[pos]
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            return True, a.value
        return True, None
    return False, None


def _is_gate_call(call: ast.Call, aliases: Dict[str, str]) -> Optional[str]:
    name = _resolve(call.func, aliases)
    last = name.rsplit(".", 1)[-1]
    return last if last in GATE_NAMES else None


class _FileScanner(ast.NodeVisitor):
    def __init__(self, path: str, tree: ast.Module):
        self.path = path
        self.aliases = _collect_aliases(tree)
        self.from_roots = _collect_from_roots(tree)
        self.consts = _module_str_consts(tree)
        self.scope: List[str] = []
        self.kinds: List[str] = []         # parallel to scope: 'f' function-like, 'c' class
        self.func_stack: List[str] = []
        self.rows: List[Row] = []
        self.counters: Dict[Tuple[str, str], int] = defaultdict(int)
        self.gate_lambda: List[str] = []   # gate names while inside a gate-arg Lambda
        self.gate_args_depth: List[str] = []  # gate names while inside any gate-call args
        # reference index entries: (name, in_gate_args)
        self.refs: List[Tuple[str, str]] = []
        self.str_consts: Set[str] = set()
        self.func_row_idx: Dict[int, str] = {}  # row index -> enclosing function name
        self.env_reads: List[Tuple[str, int]] = []
        self.flags: List[Tuple[str, int, str]] = []
        self.docstring_ids: Set[int] = set()
        for n in ast.walk(tree):
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef)):
                b = n.body
                if (b and isinstance(b[0], ast.Expr)
                        and isinstance(b[0].value, ast.Constant)
                        and isinstance(b[0].value.value, str)):
                    self.docstring_ids.add(id(b[0].value))

    # -- helpers ----------------------------------------------------------
    @property
    def qualname(self) -> str:
        return ".".join(self.scope) if self.scope else "<module>"

    def _emit(self, node: ast.AST, category: str, callee: str, detail: str = "",
              sig0: bool = False) -> None:
        q = self.qualname
        self.counters[(q, callee)] += 1
        ordinal = self.counters[(q, callee)]
        row = Row(
            key=make_key(self.path, q, callee, ordinal), kind="py",
            category=category, file=self.path, qualname=q, callee=callee,
            ordinal=ordinal, line=getattr(node, "lineno", 0), detail=detail,
            lexgate=f"lambda:{self.gate_lambda[-1]}" if self.gate_lambda else "",
            sig0=sig0,
        )
        self.func_row_idx[len(self.rows)] = self.func_stack[-1] if self.func_stack else ""
        self.rows.append(row)

    # -- scope tracking ---------------------------------------------------
    def _push(self, name: str, kind: str) -> int:
        n = 0
        if self.kinds and self.kinds[-1] == "f":
            self.scope.append("<locals>")
            self.kinds.append("c")
            n += 1
        self.scope.append(name)
        self.kinds.append(kind)
        return n + 1

    def _pop(self, n: int) -> None:
        for _ in range(n):
            self.scope.pop()
            self.kinds.pop()

    def _visit_def(self, node: ast.AST, name: str, is_func: bool) -> None:
        # Decorators/defaults/bases evaluate in the enclosing scope.
        for d in getattr(node, "decorator_list", []):
            self.visit(d)
        if is_func:
            args = node.args  # type: ignore[attr-defined]
            for d in list(args.defaults) + [x for x in args.kw_defaults if x]:
                self.visit(d)
            n = self._push(name, "f")
            self.func_stack.append(name)
            saved_lambda = self.gate_lambda
            self.gate_lambda = []   # a nested def body is not a lexical thunk
            for st in node.body:  # type: ignore[attr-defined]
                self.visit(st)
            self.gate_lambda = saved_lambda
            self.func_stack.pop()
            self._pop(n)
        else:
            for b in node.bases:  # type: ignore[attr-defined]
                self.visit(b)
            n = self._push(name, "c")
            saved_funcs = self.func_stack
            self.func_stack = []
            for st in node.body:  # type: ignore[attr-defined]
                self.visit(st)
            self.func_stack = saved_funcs
            self._pop(n)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_def(node, node.name, True)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_def(node, node.name, False)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        n = self._push("<lambda>", "f")
        self.visit(node.body)
        self._pop(n)

    # -- reference / constant index --------------------------------------
    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.refs.append((node.id, self.gate_args_depth[-1] if self.gate_args_depth else ""))

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, ast.Load):
            self.refs.append((node.attr, self.gate_args_depth[-1] if self.gate_args_depth else ""))
        self.visit(node.value)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and id(node) not in self.docstring_ids:
            self.str_consts.add(node.value)
            parts = re.split(r"[/\\]", node.value)
            hit = [p for p in parts if p in CRED_PATH_PARTS]
            if hit and len(node.value) < 200:
                self._emit(node, "credential", f"const:{hit[0]}")
            if node.value.startswith("--") and re.fullmatch(r"--[a-z0-9][a-z0-9-]*", node.value):
                self.flags.append((node.value, node.lineno, "const"))

    # -- assignments to os.environ / sys.path ----------------------------
    def _target_env(self, target: ast.AST, node: ast.AST) -> None:
        if isinstance(target, ast.Subscript):
            base = _resolve(target.value, self.aliases)
            if base == "os.environ":
                self._emit(node, "env_mut", "os.environ[]=")
            elif base == "sys.path":
                self._emit(node, "env_mut", "sys.path[]=")
        elif isinstance(target, ast.Attribute):
            if _resolve(target, self.aliases) == "sys.path":
                self._emit(node, "env_mut", "sys.path=")
        elif isinstance(target, (ast.Tuple, ast.List)):
            for e in target.elts:
                self._target_env(e, node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for t in node.targets:
            self._target_env(t, node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._target_env(node.target, node)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for t in node.targets:
            self._target_env(t, node)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if (isinstance(node.ctx, ast.Load)
                and _resolve(node.value, self.aliases) == "os.environ"):
            name = _const_str(node.slice, self.consts)
            self.env_reads.append((name or "<dynamic>", node.lineno))
            if name and CRED_ENV_RE.search(name):
                self._emit(node, "credential", "os.environ[]", f"name={name}")
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        # hand-parsed CLI flags: '--x' in argv / arg == '--x'
        for sub in [node.left] + list(node.comparators):
            if (isinstance(sub, ast.Constant) and isinstance(sub.value, str)
                    and re.fullmatch(r"--[a-z0-9][a-z0-9-]*", sub.value)):
                self.flags.append((sub.value, node.lineno, "compare"))
        self.generic_visit(node)

    # -- calls -------------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        self._classify_call(node)
        gate = _is_gate_call(node, self.aliases)
        if gate:
            # Only the keyword that carries the executed thunk counts as the
            # mediated body; e.g. gate_exec(confirm=...) is a prompt callback,
            # not a mediated effect, and gate_write/gate_append run inside the gateway.
            thunk_kw = GATE_THUNK_KWARGS.get(gate, ())
            self.visit(node.func)
            for a in node.args:
                self.visit(a)
            for kw in node.keywords:
                if kw.arg in thunk_kw:
                    self.gate_args_depth.append(gate)
                    if isinstance(kw.value, ast.Lambda):
                        self.gate_lambda.append(gate)
                        self.visit(kw.value)
                        self.gate_lambda.pop()
                    else:
                        self.visit(kw.value)
                    self.gate_args_depth.pop()
                else:
                    self.visit(kw.value)
        else:
            self.generic_visit(node)

    def _receiver_is_from_import_value(self, node: ast.Call, c: str) -> bool:
        """W1: ``from pkg.mod import NAME`` then ``NAME[.a.b].method(...)``.

        _resolve expands such a receiver to ``pkg.mod.NAME.method`` which starts
        with no ``*.`` and so used to dodge every attribute-method rule.  Treat it
        as an unknown-receiver attribute call iff (a) the call is an attribute call
        rooted at a from-imported Name, (b) that Name's source module is not a
        stdlib module (a stdlib ``from os import path`` / ``from pathlib import
        Path`` receiver is a module/class, not a project constant), and (c) the
        resolved name matches no module-function pattern (so ``os.remove`` and
        friends keep their existing single row and are never re-labelled).
        """
        f = node.func
        if not isinstance(f, ast.Attribute):
            return False
        cur: ast.AST = f.value
        while isinstance(cur, ast.Attribute):
            cur = cur.value
        if not (isinstance(cur, ast.Name) and cur.id in self.from_roots):
            return False
        top = self.from_roots[cur.id].split(".")[0]
        if top in sys.stdlib_module_names:
            return False
        return not _known_callee(c)

    def _classify_call(self, node: ast.Call) -> None:
        c = _resolve(node.func, self.aliases)
        if self._receiver_is_from_import_value(node, c):
            c = "*." + node.func.attr  # type: ignore[attr-defined]
        last = c.rsplit(".", 1)[-1]
        args = node.args

        # add_argument flag census (not a boundary row)
        if last == "add_argument":
            for a in args:
                if (isinstance(a, ast.Constant) and isinstance(a.value, str)
                        and a.value.startswith("--")):
                    self.flags.append((a.value, node.lineno, "add_argument"))

        # env reads census
        if c in ("os.environ.get", "os.getenv", "os.environ.pop"):
            name = _const_str(args[0], self.consts) if args else None
            self.env_reads.append((name or "<dynamic>", node.lineno))
            if c == "os.environ.pop":
                self._emit(node, "env_mut", c)
            elif name and CRED_ENV_RE.search(name):
                self._emit(node, "credential", c, f"name={name}")
            return
        if c in ENV_CALLS:
            self._emit(node, "env_mut", c)
            return

        # getattr indirection on dangerous modules
        if c == "getattr" and len(args) >= 2:
            base = _resolve(args[0], self.aliases)
            if base in ("os", "subprocess", "shutil", "socket") and not isinstance(
                    args[1], ast.Constant):
                self._emit(node, "dyn_code", "getattr-dynamic", f"base={base}")
            return

        # SQL
        if last in ("execute", "executemany", "executescript") and args:
            self._classify_sql(node, last, args[0])
            return

        if c in DYN_EXACT or any(c.startswith(p) for p in DYN_PREFIX):
            self._emit(node, "dyn_code", c)
            return
        if c in KILL_EXACT:
            sig0 = (c == "os.kill" and len(args) >= 2
                    and isinstance(args[1], ast.Constant) and args[1].value == 0)
            self._emit(node, "kill", c, "signal=0" if sig0 else "", sig0=sig0)
            return
        if c.startswith("*.") and last in KILL_ATTR:
            self._emit(node, "kill", c)
            return
        if c in EXEC_EXACT or any(c.startswith(p) for p in EXEC_PREFIX):
            self._emit(node, "exec_spawn", c)
            if args and isinstance(args[0], (ast.List, ast.Tuple)) and args[0].elts:
                first = _const_str(args[0].elts[0], self.consts)
                if first in CRED_ARGV:
                    self._emit(node, "credential", f"argv:{first}")
            return
        if c in NET_EXACT or any(c.startswith(p) for p in NET_PREFIX):
            self._emit(node, "network", c)
            return
        if c in CRED_CALLS_EXACT or any(c.startswith(p) for p in CRED_CALLS_PREFIX):
            self._emit(node, "credential", c)
            return
        if c == "sqlite3.connect":
            self._emit(node, "sqlite_conn", c)
            return

        # filesystem
        if c in OPEN_EXACT or (c.startswith("*.") and last == "open"):
            builtin = c in OPEN_EXACT
            pos = 1 if c in ("open", "io.open", "codecs.open", "os.fdopen",
                             "gzip.open", "bz2.open", "lzma.open") else 0
            found, mode = _mode_arg(node, pos)
            if not builtin:
                # Unknown receiver: only a literal write-mode string counts.
                if found and mode is not None and set("wax+") & set(mode):
                    self._emit(node, "fs_write", c, f"mode={mode}")
                return
            if not found:
                return                      # default mode 'r'
            if mode is None:
                self._emit(node, "fs_write", c, "mode=<dynamic>")
            elif set("wax+") & set(mode):
                self._emit(node, "fs_write", c, f"mode={mode}")
            return
        if c in ARCHIVE_MODE:
            found, mode = _mode_arg(node, ARCHIVE_MODE[c])
            if found and (mode is None or set("wax+") & set(mode)):
                self._emit(node, "fs_write", c,
                           "mode=<dynamic>" if mode is None else f"mode={mode}")
            return
        if c in FS_EXACT:
            self._emit(node, "fs_write", c)
            return
        if c.startswith("logging.handlers.") and c.endswith("FileHandler"):
            self._emit(node, "fs_write", c)
            return
        if c.startswith("*.") and (last in ATTR_FS or (
                last in ATTR_FS_ONE_ARG and len(args) == 1 and not node.keywords)):
            self._emit(node, "fs_write", c)

    def _classify_sql(self, node: ast.Call, last: str, arg: ast.AST) -> None:
        sql = _const_str(arg, self.consts)
        callee = f"*.{last}"
        if sql is not None:
            if last == "executescript":
                if SQL_ANY_WRITE_RE.search(sql):
                    self._emit(node, "sqlite_exec", callee, "script")
                return
            m = SQL_WRITE_RE.match(sql)
            if m:
                verb = re.sub(r"\s+", " ", m.group(1).upper())
                self._emit(node, "sqlite_write", callee, f"verb={verb}")
            return
        # Non-constant first argument: never dropped (spec 2.3).
        if isinstance(arg, (ast.Name, ast.JoinedStr, ast.BinOp, ast.Call,
                            ast.Attribute, ast.Subscript, ast.IfExp)):
            self._emit(node, "sql_dynamic", callee,
                       "script" if last == "executescript" else "")


def scan_python_source(path: str, source: str) -> Tuple[List[Row], dict]:
    """Scan one file's text.  Returns (rows, per-file index)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # scanned files' own SyntaxWarnings are not ours
        tree = ast.parse(source, filename=path)
    sc = _FileScanner(path, tree)
    sc.visit(tree)
    index = {
        "refs": sc.refs, "str_consts": sc.str_consts, "env": sc.env_reads,
        "flags": sc.flags, "func_idx": sc.func_row_idx,
        "defs": sorted({n.name for n in ast.walk(tree)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}),
    }
    return sc.rows, index


def _apply_helper_rule(rows_by_file: Dict[str, List[Row]],
                       indexes: Dict[str, dict]) -> None:
    """One-level reverse-reference helper rule (spec 2.3).

    A row inside function F is marked ``helper:<gate>`` iff F's simple name is
    referenced at least once in production code and EVERY reference (Name load or
    attribute name, any file) sits inside a gate call's arguments, and the name
    never appears as a string constant (dynamic getattr/dispatch).  Conservative:
    attribute-name collisions add references and therefore remove the seed.
    """
    total: Dict[str, int] = defaultdict(int)
    ingate: Dict[str, int] = defaultdict(int)
    gates: Dict[str, Set[str]] = defaultdict(set)
    strs: Set[str] = set()
    for idx in indexes.values():
        for name, ing in idx["refs"]:
            total[name] += 1
            if ing:
                ingate[name] += 1
                gates[name].add(ing)
        strs |= idx["str_consts"]
    for f, rows in rows_by_file.items():
        fidx = indexes[f]["func_idx"]
        for i, r in enumerate(rows):
            fn = fidx.get(i, "")
            if not fn:
                continue
            r.refs = str(total.get(fn, 0))
            if r.lexgate or fn.startswith("__"):
                continue
            if total.get(fn, 0) >= 1 and total[fn] == ingate.get(fn, 0) and fn not in strs:
                r.lexgate = "helper:" + "|".join(sorted(gates[fn]))


# --------------------------------------------------------------------------
# Shell / launcher / workflow scan (text only)
# --------------------------------------------------------------------------

def scan_shell_text(path: str, text: str) -> List[Row]:
    rows: List[Row] = []
    counters: Dict[Tuple[str, str], int] = defaultdict(int)
    func = "<script>"
    for lineno, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = SHELL_FUNC_RE.match(raw)
        if m and not raw.lstrip().startswith(("if ", "while ")):
            func = m.group(1)
        line = re.sub(r"\s#\s.*$", "", raw)   # trailing comment (naive)
        for pid, rx in _SHELL_RES:
            if rx.search(line):
                counters[(func, pid)] += 1
                n = counters[(func, pid)]
                rows.append(Row(
                    key=make_key(path, func, f"sh:{pid}", n), kind="shell",
                    category="shell", file=path, qualname=func,
                    callee=f"sh:{pid}", ordinal=n, line=lineno,
                    detail=stripped[:140]))
    return rows


def _authority_keys(source: Optional[str]) -> Set[str]:
    if not source:
        return set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    for n in ast.walk(tree):
        tgt = None
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            tgt = n.target.id
        elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(
                n.targets[0], ast.Name):
            tgt = n.targets[0].id
        if tgt == "CAPABILITY_AUTHORITY" and isinstance(getattr(n, "value", None), ast.Dict):
            return {k.value for k in n.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return set()


def scan_manifest_text(path: str, text: str, authority: Set[str]) -> List[Row]:
    rows: List[Row] = []
    counters: Dict[Tuple[str, str], int] = defaultdict(int)
    try:
        data = json.loads(text)
    except ValueError as exc:
        return [Row(key=make_key(path, "$", "manifest:parse-error", 1),
                    kind="manifest", category="manifest", file=path,
                    qualname="$", callee="manifest:parse-error", ordinal=1,
                    line=0, detail=str(exc)[:100])]

    def emit(q: str, callee: str, detail: str) -> None:
        counters[(q, callee)] += 1
        rows.append(Row(key=make_key(path, q, callee, counters[(q, callee)]),
                        kind="manifest", category="manifest", file=path,
                        qualname=q, callee=callee, ordinal=counters[(q, callee)],
                        line=0, detail=detail[:140]))

    def walk(node, q: str) -> None:
        if isinstance(node, dict):
            name = node.get("name") if isinstance(node.get("name"), str) else None
            here = f"{q}/{name}" if name and q != "$" or (name and q == "$") else q
            if name and isinstance(node.get("implementation"), str):
                emit(here, "manifest:capability",
                     f"authority_listed={name in authority}; impl={node['implementation']}")
            for k, v in node.items():
                if k in MANIFEST_EXEC_KEYS and isinstance(v, str):
                    emit(here, f"manifest:{k}", v)
                elif k in MANIFEST_POLICY_KEYS:
                    emit(here, f"manifest:{k}", json.dumps(v, sort_keys=True))
                if isinstance(v, (dict, list)):
                    walk(v, here)
        elif isinstance(node, list):
            for v in node:
                walk(v, q)

    walk(data, "$")
    return rows


# --------------------------------------------------------------------------
# Snapshot / source acquisition
# --------------------------------------------------------------------------

def _git_env() -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _git(repo: str, *args: str) -> bytes:
    p = subprocess.run(  # read-only git query; never writes the repo
        ["git", "--no-optional-locks", "-C", repo, *args],
        capture_output=True, env=_git_env(), check=False)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.decode(errors='replace')[:300]}")
    return p.stdout


def want_path(rel: str) -> bool:
    """True iff a repo-relative path is a candidate scan input."""
    parts = rel.split("/")
    if parts[0] in EXCLUDED_DIRS:
        return False
    if any(p in EXCLUDED_COMPONENTS for p in parts[:-1]):
        return False
    base = parts[-1]
    if rel.endswith(".py"):
        return not (base == "conftest.py" or base.startswith("test_"))
    if rel.endswith(".sh"):
        return True
    if rel.startswith(".github/workflows/") and rel.endswith((".yml", ".yaml")):
        return True
    if base == "manifest.json" and rel.startswith("ccos/plugins/"):
        return True
    if rel == "ccos/data/capabilities.json":
        return True
    # root launcher candidates (shebang checked after read)
    return len(parts) == 1 and "." not in base


@dataclasses.dataclass
class Source:
    files: Dict[str, bytes]        # rel path -> content (candidate inputs only)
    meta: dict
    authority_source: Optional[str] = None


def _collect_members(tf: tarfile.TarFile, files: Dict[str, bytes],
                     skipped_links: List[str]) -> None:
    for m in tf:
        name = m.name
        if name.startswith("/") or ".." in name.split("/"):
            continue    # never trust archive paths
        if m.issym() or m.islnk():
            if want_path(name):
                skipped_links.append(name)
            continue
        if not m.isfile() or not want_path(name):
            continue
        fh = tf.extractfile(m)
        if fh is not None:
            files[name] = fh.read()


def snapshot_head(repo: str, rev: str) -> Source:
    """Stream ``git archive <rev>`` and keep only candidate files in memory."""
    head = _git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}").decode().strip()
    files: Dict[str, bytes] = {}
    skipped_links: List[str] = []
    with tempfile.TemporaryFile() as errf:
        proc = subprocess.Popen(  # read-only; output consumed below
            ["git", "--no-optional-locks", "-C", repo, "archive", "--format=tar", head],
            stdout=subprocess.PIPE, stderr=errf, env=_git_env())
        try:
            with tarfile.open(fileobj=proc.stdout, mode="r|") as tf:
                _collect_members(tf, files, skipped_links)
            while proc.stdout and proc.stdout.read(65536):
                pass    # drain trailing tar padding so git exits 0 (no SIGPIPE)
        finally:
            if proc.stdout:
                proc.stdout.close()
            rc = proc.wait()
        if rc != 0:
            errf.seek(0)
            raise RuntimeError("git archive failed: " + errf.read().decode(errors="replace")[:300])
    dirty = dirty_paths(repo)
    meta = {
        "source": "head-snapshot", "rev_requested": rev, "head": head,
        "dirty_paths": dirty, "skipped_symlinks": sorted(skipped_links),
    }
    return Source(files, meta)


def worktree_source(repo: str) -> Source:
    files: Dict[str, bytes] = {}
    for dirpath, dirnames, filenames in os.walk(repo):
        rel_dir = os.path.relpath(dirpath, repo).replace(os.sep, "/")
        top = "" if rel_dir == "." else rel_dir.split("/")[0]
        dirnames[:] = sorted(d for d in dirnames
                             if d not in EXCLUDED_DIRS or top != "")
        if top in EXCLUDED_DIRS:
            dirnames[:] = []
            continue
        for fn in sorted(filenames):
            rel = fn if rel_dir == "." else f"{rel_dir}/{fn}"
            if want_path(rel):
                fp = os.path.join(dirpath, fn)
                if os.path.islink(fp):
                    continue
                with open(fp, "rb") as fh:
                    files[rel] = fh.read()
    try:
        head = _git(repo, "rev-parse", "HEAD").decode().strip()
    except RuntimeError:
        head = ""
    return Source(files, {"source": "worktree", "rev_requested": "worktree",
                          "head": head, "dirty_paths": dirty_paths(repo),
                          "skipped_symlinks": []})


def dirty_paths(repo: str) -> List[str]:
    try:
        out = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=normal")
    except RuntimeError:
        return []
    paths: List[str] = []
    toks = out.split(b"\0")
    i = 0
    while i < len(toks):
        t = toks[i]
        i += 1
        if len(t) < 4:
            continue
        xy, p = t[:2].decode(), t[3:].decode(errors="replace")
        paths.append(p)
        if "R" in xy or "C" in xy:      # rename/copy: next token is the old path
            if i < len(toks):
                paths.append(toks[i].decode(errors="replace"))
            i += 1
    return sorted(set(paths))


def is_dirty(path: str, dirty: Iterable[str]) -> bool:
    for d in dirty:
        if path == d or (d.endswith("/") and path.startswith(d)):
            return True
    return False


# --------------------------------------------------------------------------
# Whole-source scan
# --------------------------------------------------------------------------

@dataclasses.dataclass
class ScanResult:
    rows: List[Row]
    env_rows: List[dict]
    flag_rows: List[dict]
    file_hashes: Dict[str, str]
    parse_failures: List[str]
    meta: dict

    def by_key(self) -> Dict[str, Row]:
        return {r.key: r for r in self.rows}


def _is_shell(rel: str, data: bytes) -> bool:
    if rel.endswith((".sh", ".yml", ".yaml")):
        return True
    first = data.split(b"\n", 1)[0]
    return first.startswith(b"#!") and (b"sh" in first or b"bash" in first)


def _row_sort_key(r: Row):
    return (r.file, r.qualname, r.callee, r.ordinal)


def _env_class(name: str) -> str:
    if name in ENV_CLASS_SELECTOR:
        return "executable-selector"
    if name in ENV_CLASS_AUTHORITY:
        return "authority-modifier"
    if name in ENV_CLASS_PATH:
        return "path-redirect"
    if CRED_ENV_RE.search(name):
        return "credential"
    return "mode-toggle"


def scan_source(src: Source) -> ScanResult:
    rows_by_file: Dict[str, List[Row]] = {}
    indexes: Dict[str, dict] = {}
    all_rows: List[Row] = []
    hashes: Dict[str, str] = {}
    failures: List[str] = []
    auth_src = src.files.get("ccos/core/plugin_manager.py")
    authority = _authority_keys(auth_src.decode("utf-8", "replace") if auth_src else None)
    for rel in sorted(src.files):
        data = src.files[rel]
        text = data.decode("utf-8", "replace")
        if rel.endswith(".py"):
            hashes[rel] = hashlib.sha256(data).hexdigest()
            try:
                rows, idx = scan_python_source(rel, text)
            except (SyntaxError, ValueError) as exc:
                failures.append(f"{rel}: {type(exc).__name__}: {exc}")
                continue
            rows_by_file[rel] = rows
            indexes[rel] = idx
        elif rel.endswith(".json"):
            hashes[rel] = hashlib.sha256(data).hexdigest()
            all_rows.extend(scan_manifest_text(rel, text, authority))
        elif _is_shell(rel, data):
            hashes[rel] = hashlib.sha256(data).hexdigest()
            all_rows.extend(scan_shell_text(rel, text))
        # other root files without a shell shebang are not candidates
    _apply_helper_rule(rows_by_file, indexes)
    for rows in rows_by_file.values():
        all_rows.extend(rows)
    dirty = src.meta.get("dirty_paths", [])
    for r in all_rows:
        r.dirty = is_dirty(r.file, dirty)
    all_rows.sort(key=_row_sort_key)

    env: Dict[str, dict] = {}
    for f, idx in indexes.items():
        for name, line in idx["env"]:
            e = env.setdefault(name, {"name": name, "class": _env_class(name),
                                      "count": 0, "files": set()})
            e["count"] += 1
            e["files"].add(f)
    env_rows = [{"name": e["name"], "class": e["class"], "count": e["count"],
                 "files": ",".join(sorted(e["files"]))}
                for _, e in sorted(env.items())]
    flags: Dict[str, dict] = {}
    for f, idx in indexes.items():
        for name, line, how in idx["flags"]:
            e = flags.setdefault(name, {"flag": name, "files": set(), "how": set()})
            e["files"].add(f)
            e["how"].add(how)
    flag_rows = [{"flag": e["flag"], "how": ",".join(sorted(e["how"])),
                  "files": ",".join(sorted(e["files"]))}
                 for _, e in sorted(flags.items())]
    meta = dict(src.meta)
    meta.update({
        "tool_version": TOOL_VERSION, "pattern_set_sha256": pattern_set_hash(),
        "python": sys.version.split()[0], "excluded_dirs": EXCLUDED_DIRS,
        "scanned_files": len(hashes), "capability_authority_names": len(authority),
        "parse_failures": failures,
    })
    return ScanResult(all_rows, env_rows, flag_rows, dict(sorted(hashes.items())),
                      failures, meta)


# --------------------------------------------------------------------------
# Seeds and register
# --------------------------------------------------------------------------

def mechanical_disposition(r: Row) -> Optional[dict]:
    """Seed a disposition only on purely mechanical evidence, else None."""
    if r.kind == "py" and r.lexgate:
        kind, gate = r.lexgate.split(":", 1)
        if kind == "lambda":
            return {"cls": "GATED", "mediator": f"lexical:{gate}",
                        "evidence": f"row inside a Lambda thunk in the args of a {gate} call ({r.file})"}
        return {"cls": "GATED", "mediator": f"helper-of:{gate}",
                    "evidence": (f"every one of {r.refs} production reference(s) to the enclosing "
                              "function name sits inside gate-call args; no string-constant "
                              "reference (one-level helper rule; NOT proof against attribute-name "
                              "aliasing or dynamic dispatch)")}
    if r.sig0:
        return {"cls": "READ_NOEFFECT", "mediator": "",
                    "evidence": f"os.kill(pid, 0) liveness probe sends no signal ({r.file}); "
                             "identity-validation of real senders is a separate row"}
    return None


def is_qualname_level_path(file: str) -> bool:
    return file.startswith("restoricon_core/")


def seed_register_rows(scan: ScanResult, first_seen: str) -> List[dict]:
    out: List[dict] = []
    qual_counts: Dict[str, int] = defaultdict(int)
    for r in scan.rows:
        if r.kind == "py" and is_qualname_level_path(r.file):
            qual_counts[qual_key(r.file, r.qualname, r.category)] += 1
            continue
        d = mechanical_disposition(r)
        out.append({
            "key": r.key, "class": d["cls"] if d else "UNKNOWN",
            "mediator": d["mediator"] if d else "",
            "evidence": d["evidence"] if d else "",
            "reach": "", "severity": "", "finding": "",
            "decided_by": "census-tool:mechanical-seed" if d else "census-tool:initial",
            "reviewed_by": "", "first_seen_rev": first_seen, "count": "",
        })
    for k, n in sorted(qual_counts.items()):
        out.append({"key": k, "class": "UNKNOWN", "mediator": "", "evidence": "",
                    "reach": "", "severity": "", "finding": "",
                    "decided_by": "census-tool:initial", "reviewed_by": "",
                    "first_seen_rev": first_seen, "count": str(n)})
    out.sort(key=lambda d: d["key"])
    return out


def _tsv_field(v: object) -> str:
    return str(v).replace("\t", " ").replace("\r", " ").replace("\n", " ")


def parse_register(text: str) -> List[dict]:
    rows: List[dict] = []
    header: Optional[List[str]] = None
    for ln in text.splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        cells = ln.split("\t")
        if header is None:
            header = cells
            continue
        cells += [""] * (len(header) - len(cells))
        rows.append(dict(zip(header, cells)))
    return rows


def render_register(rows: Sequence[dict]) -> str:
    lines = ["\t".join(REGISTER_COLUMNS)]
    for d in rows:
        lines.append("\t".join(_tsv_field(d.get(c, "")) for c in REGISTER_COLUMNS))
    return "\n".join(lines) + "\n"


def merge_seed(existing: Sequence[dict], seed: Sequence[dict]) -> List[dict]:
    """Keep every existing disposition untouched; append only missing keys."""
    have = {d["key"] for d in existing}
    merged = list(existing) + [d for d in seed if d["key"] not in have]
    merged.sort(key=lambda d: d["key"])
    return merged


# --------------------------------------------------------------------------
# Coverage evaluation
# --------------------------------------------------------------------------

@dataclasses.dataclass
class Coverage:
    failures: List[Tuple[str, str]]
    warnings: List[Tuple[str, str]]
    stats: Dict[str, int]

    @property
    def ok(self) -> bool:
        return not self.failures


def _gates_of(mediator: str) -> List[str]:
    return mediator.split(":", 1)[-1].split("|")


def evaluate_coverage(scan: ScanResult, register: Sequence[dict], *,
                      dirty_paths: Iterable[str] = (),
                      present_files: Optional[Set[str]] = None,
                      require_no_unknown: bool = False,
                      gate_restoricon: bool = True) -> Coverage:
    """Diff scan rows against the register.

    Failures: unregistered row, qualname-count mismatch, stale register row,
    bad class/reach/severity, duplicate key, UNMEDIATED without finding+severity,
    GATED with a mediator outside the gate vocabulary or contradicting the scan's
    lexical evidence, missing evidence, and (``require_no_unknown``) any UNKNOWN.
    Rows from dirty (foreign in-progress) paths downgrade failures to warnings.
    A parse failure (file scanned as zero rows) is a failure the same way, and is
    likewise downgraded to a warning only for a dirty/foreign path.
    """
    dirty = list(dirty_paths)
    fails: List[Tuple[str, str]] = []
    warns: List[Tuple[str, str]] = []

    def report(code: str, detail: str, path: str, soft: bool = False) -> None:
        (warns if soft or is_dirty(path, dirty) else fails).append((code, detail))

    def path_of(key: str) -> str:
        return key.split("::", 1)[0]

    # A boundary file that no longer parses contributes ZERO rows; without this a
    # syntax error would make every one of its register entries look merely
    # "stale" (or, for a new file, hide it entirely).  Fail unless dirty/foreign.
    for pf in scan.parse_failures:
        report("parse-failure", pf, pf.split(":", 1)[0])

    by_key = scan.by_key()
    reg_exact: Dict[str, dict] = {}
    reg_qual: Dict[str, dict] = {}
    for d in register:
        key = d.get("key", "")
        n = key.count("::")
        cls = d.get("class", "")
        if cls not in CLASSES:
            report("bad-class", f"{key}: {cls!r}", path_of(key))
            continue
        if d.get("reach", "") not in REACH_VALUES:
            report("bad-reach", f"{key}: {d.get('reach')!r}", path_of(key))
        if d.get("severity", "") not in SEVERITIES:
            report("bad-severity", f"{key}: {d.get('severity')!r}", path_of(key))
        target = reg_exact if n == 3 else reg_qual if n == 2 else None
        if target is None:
            report("bad-key", key, path_of(key))
            continue
        if key in target:
            report("duplicate-key", key, path_of(key))
            continue
        if n == 2:
            if cls not in QUALNAME_LEVEL_CLASSES:
                report("bad-qualname-class", f"{key}: {cls}", path_of(key))
            if not str(d.get("count", "")).isdigit():
                report("bad-count", f"{key}: {d.get('count')!r}", path_of(key))
        target[key] = d
        if cls != "UNKNOWN" and not d.get("evidence", "").strip():
            report("missing-evidence", key, path_of(key))
        if cls == "UNMEDIATED" and not (d.get("finding", "").strip() and d.get("severity", "").strip()):
            report("unmediated-needs-finding-severity", key, path_of(key))
        if cls == "GATED":
            if not all(g in GATE_NAMES for g in _gates_of(d.get("mediator", ""))):
                report("gated-mediator-not-gate", f"{key}: {d.get('mediator')!r}", path_of(key))
            row = by_key.get(key)
            m = d.get("mediator", "")
            if row is not None and m.startswith(("lexical:", "helper-of:")):
                want = "lambda" if m.startswith("lexical:") else "helper"
                if not row.lexgate.startswith(want + ":"):
                    report("gated-lexical-claim-not-in-scan", key, path_of(key))

    qual_actual: Dict[str, int] = defaultdict(int)
    for r in scan.rows:
        if r.kind == "py":
            qual_actual[qual_key(r.file, r.qualname, r.category)] += 1

    unknown = 0
    covered_qual: Set[str] = set()
    for r in scan.rows:
        d = reg_exact.get(r.key)
        qk = qual_key(r.file, r.qualname, r.category) if r.kind == "py" else ""
        if d is None and qk and qk in reg_qual:
            d = reg_qual[qk]
            covered_qual.add(qk)
        if d is None:
            soft = (not gate_restoricon) and is_qualname_level_path(r.file)
            report("unregistered-row", r.key, r.file, soft=soft)
            continue
        if d.get("class") == "UNKNOWN":
            unknown += 1
            if require_no_unknown:
                report("unknown-remains", r.key, r.file)
    for qk in sorted(covered_qual):
        want = int(reg_qual[qk].get("count") or 0)
        if want != qual_actual[qk]:
            report("qualname-count-mismatch",
                   f"{qk}: register says {want}, scan has {qual_actual[qk]}", qk)

    # Stale register entries.
    for key in sorted(reg_exact):
        if key not in by_key:
            p = path_of(key)
            gone = present_files is not None and p not in present_files
            report("stale-row", key, p, soft=gone)
    for qk in sorted(reg_qual):
        if qual_actual.get(qk, 0) == 0:
            p = path_of(qk)
            gone = present_files is not None and p not in present_files
            report("stale-qualname", qk, p, soft=gone)

    stats = {
        "scan_rows": len(scan.rows), "register_entries": len(register),
        "unknown_rows": unknown, "failures": len(fails), "warnings": len(warns),
    }
    return Coverage(sorted(fails), sorted(warns), stats)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

# NOTE: no "dirty" column.  scan.tsv must be a pure function of the revision
# (independent re-runs must be byte-identical); dirtiness lives in run_meta.json.
SCAN_COLUMNS = ("key", "kind", "category", "file", "dir", "qualname", "callee",
                "ordinal", "line", "detail", "lexgate", "refs")


def _row_cells(r: Row) -> List[str]:
    return [r.key, r.kind, r.category, r.file, r.top, r.qualname, r.callee,
            str(r.ordinal), str(r.line), r.detail, r.lexgate, r.refs]


def _write_tsv(path: str, header: Sequence[str], rows: Iterable[Sequence[str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\t".join(header) + "\n")
        fh.writelines("\t".join(_tsv_field(c) for c in cells) + "\n" for cells in rows)


def summarize(scan: ScanResult, register: Optional[Sequence[dict]] = None) -> dict:
    by_cat: Dict[str, int] = defaultdict(int)
    by_dir: Dict[str, int] = defaultdict(int)
    by_kind: Dict[str, int] = defaultdict(int)
    for r in scan.rows:
        by_cat[r.category] += 1
        by_dir[r.top] += 1
        by_kind[r.kind] += 1
    out = {"total_rows": len(scan.rows), "by_kind": dict(sorted(by_kind.items())),
           "by_category": dict(sorted(by_cat.items())),
           "by_dir": dict(sorted(by_dir.items()))}
    if register is not None:
        cls_rows: Dict[str, int] = defaultdict(int)
        reg_exact = {d["key"]: d for d in register if d["key"].count("::") == 3}
        reg_qual = {d["key"]: d for d in register if d["key"].count("::") == 2}
        by_dir_class: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        none = 0
        for r in scan.rows:
            d = reg_exact.get(r.key) or (
                reg_qual.get(qual_key(r.file, r.qualname, r.category)) if r.kind == "py" else None)
            c = d["class"] if d else "NO_DISPOSITION"
            if not d:
                none += 1
            cls_rows[c] += 1
            by_dir_class[r.top][c] += 1
        out["by_class"] = dict(sorted(cls_rows.items()))
        out["no_disposition"] = none
        out["by_dir_class"] = {k: dict(sorted(v.items()))
                               for k, v in sorted(by_dir_class.items())}
    return out


def write_outputs(out: str, scan: ScanResult, seed: Optional[List[dict]],
                  register: Optional[Sequence[dict]]) -> None:
    os.makedirs(out, exist_ok=True)
    py = [r for r in scan.rows if r.kind == "py"]
    sh = [r for r in scan.rows if r.kind == "shell"]
    mf = [r for r in scan.rows if r.kind == "manifest"]
    _write_tsv(os.path.join(out, "scan.tsv"), SCAN_COLUMNS, (_row_cells(r) for r in py))
    _write_tsv(os.path.join(out, "shell_scan.tsv"), SCAN_COLUMNS, (_row_cells(r) for r in sh))
    _write_tsv(os.path.join(out, "manifest_scan.tsv"), SCAN_COLUMNS, (_row_cells(r) for r in mf))
    _write_tsv(os.path.join(out, "env_names.tsv"), ("name", "class", "count", "files"),
               ([e["name"], e["class"], str(e["count"]), e["files"]] for e in scan.env_rows))
    _write_tsv(os.path.join(out, "cli_flags.tsv"), ("flag", "how", "files"),
               ([e["flag"], e["how"], e["files"]] for e in scan.flag_rows))
    meta = dict(scan.meta)
    meta["file_sha256"] = scan.file_hashes
    with open(os.path.join(out, "run_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1, sort_keys=True)
        fh.write("\n")
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summarize(scan, register if register is not None else seed),
                  fh, indent=1, sort_keys=True)
        fh.write("\n")
    if seed is not None:
        with open(os.path.join(out, "dispositions.seed.tsv"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write(render_register(seed))


def default_out() -> str:
    return os.path.join(tempfile.gettempdir(), "wp21_census")


def run(repo: str, rev: str = "HEAD", source: str = "head") -> ScanResult:
    repo = os.path.abspath(repo)
    src = snapshot_head(repo, rev) if source == "head" else worktree_source(repo)
    return scan_source(src)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=".", help="repo root (default: cwd)")
    ap.add_argument("--rev", default="HEAD", help="revision for the git-archive snapshot")
    ap.add_argument("--source", choices=("head", "worktree"), default="head",
                    help="head = git-archive snapshot (default); worktree = read files in place")
    ap.add_argument("--out", default=None, help="output dir (default: <tmp>/wp21_census)")
    ap.add_argument("--register", default=None,
                    help="existing disposition register TSV (read only)")
    ap.add_argument("--seed", action="store_true",
                    help="write dispositions.seed.tsv into --out (existing register entries preserved)")
    ap.add_argument("--check", action="store_true",
                    help="run the coverage check against --register; exit 1 on failures")
    ap.add_argument("--strict", action="store_true", help="with --check: UNKNOWN rows fail")
    ns = ap.parse_args(argv)

    scan = run(ns.repo, ns.rev, ns.source)
    register = None
    if ns.register:
        with open(ns.register, encoding="utf-8") as fh:
            register = parse_register(fh.read())
    seed = None
    if ns.seed:
        seed = seed_register_rows(scan, scan.meta.get("head", "")[:8])
        if register:
            seed = merge_seed(register, seed)
    out = ns.out or os.path.join(default_out(), (scan.meta.get("head") or "worktree")[:8])
    write_outputs(out, scan, seed, register)
    print(json.dumps(summarize(scan, register if register is not None else seed),
                     indent=1, sort_keys=True))
    print(f"outputs: {out}")
    if ns.check:
        if register is None:
            print("--check needs --register", file=sys.stderr)
            return 2
        dirty = scan.meta["dirty_paths"] if ns.source == "worktree" else []
        cov = evaluate_coverage(scan, register, dirty_paths=dirty,
                                present_files=set(scan.file_hashes),
                                require_no_unknown=ns.strict)
        for code, detail in cov.failures:
            print(f"FAIL {code}: {detail}")
        for code, detail in cov.warnings:
            print(f"WARN {code}: {detail}")
        print(json.dumps(cov.stats, sort_keys=True))
        return 0 if cov.ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
