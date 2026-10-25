"""Suite + evaluator integrity lock.

suite.lock (v2) has exactly two lines: ``tasks:<sha256>`` (every file under
bench/tasks) and ``evaluator:<sha256>`` (every bench/*.py except the
measurement-only modules in NOT_EVALUATOR). A NEW bench/*.py is covered by
default, so adding one changes the hash until the lock is regenerated.

Honest claim: the lock detects edits that are not accompanied by a deliberate
relock. It cannot stop a writer who can edit both the files and the lock
(write_lock() is self-attesting; accepted residual, G15f Q2), and it does not
defend the verifier itself (a modified lock.py/runner.py can skip the check;
its value there is a verifier run from an unmodified copy). The evaluator hash
is also recorded in every ledger row so compare() can refuse mixed versions.
A legacy single-line (v1) lock fails closed: verify_lock() is False (so does a
lock that is not valid UTF-8).

Coverage: every *.py at any depth under bench/ (excluding bench/tasks/**, which the
tasks hash covers, __pycache__, and NOT_EVALUATOR) feeds the evaluator hash, so a
new module or subpackage is covered by default. Intentionally uncovered: non-.py
data (suite.lock itself, scorecard_manual.json, scorecard_history.jsonl, *.md)
because they do not influence pass/fail. Residual: an unchecked-hash .pyc could
shadow a source file; not defended here.

Symlinks (fail closed, VC2-N01): ANY symlink anywhere under bench/ (file, directory
or dangling; including bench/tasks/** and __pycache__) is a lock violation.
rglob does not descend into symlinked directories and is_file() follows symlinked
files, so a link could hide a .py from the evaluator hash (importable but unhashed)
or let the hashed bytes change without the link changing. verify_lock() returns
False while one exists and write_lock() refuses (RuntimeError) to attest it.

Framing: evaluator_hash length-prefixes each path and content (unambiguous).
suite_hash keeps its original path\0bytes\0 framing UNCHANGED, which is
ambiguous ({f: b"X\0g\0Y"} collides with {f: b"X", g: b"Y"}); accepted residual,
kept so existing ledger suite_hash values stay comparable (Ish has not decided
to change it; tests/test_bench_integrity_lock.py pins the collision).
"""
import hashlib
import os
import struct
from pathlib import Path

ROOT = Path(__file__).parent
LOCK = ROOT / "suite.lock"

# Measurement, not verdict path (G15f Q3). Everything else under bench/*.py is covered.
NOT_EVALUATOR = frozenset({"scorecard.py", "power_analysis.py"})


def suite_hash(tasks_dir: Path = ROOT / "tasks") -> str:
    h = hashlib.sha256()
    for p in sorted(tasks_dir.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            h.update(str(p.relative_to(tasks_dir)).encode())
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def evaluator_files(bench_dir: Path = ROOT) -> list:
    bench_dir = Path(bench_dir)
    out = []
    for p in bench_dir.rglob("*.py"):
        rel = p.relative_to(bench_dir)
        if not p.is_file() or "__pycache__" in rel.parts or rel.parts[0] == "tasks":
            continue
        if len(rel.parts) == 1 and p.name in NOT_EVALUATOR:
            continue
        out.append(p)
    return sorted(out)


def evaluator_hash(bench_dir: Path = ROOT) -> str:
    bench_dir = Path(bench_dir)
    h = hashlib.sha256()
    for p in evaluator_files(bench_dir):
        name = p.relative_to(bench_dir).as_posix().encode()
        data = p.read_bytes()
        h.update(struct.pack(">Q", len(name)) + name + struct.pack(">Q", len(data)) + data)
    return h.hexdigest()


def find_symlinks(*roots) -> list:
    """Every symlink (file, directory or dangling) at any depth under the given roots.

    Walks without following links; a directory symlink is reported, never entered.
    """
    out = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            for n in dirnames + filenames:
                p = Path(dirpath) / n
                if p.is_symlink():
                    out.append(p)
    return sorted(set(out))


def write_lock(tasks_dir: Path = ROOT / "tasks", lock: Path = LOCK, bench_dir=None) -> str:
    """Write the v2 lock; returns the tasks hash (as the v1 version did).

    Raises RuntimeError (writing nothing) if any symlink exists under bench/.
    """
    links = find_symlinks(ROOT if bench_dir is None else bench_dir, tasks_dir)
    if links:
        raise RuntimeError("refusing to lock: symlink(s) under bench/: "
                           + ", ".join(str(p) for p in links))
    d = suite_hash(tasks_dir)
    e = evaluator_hash(ROOT if bench_dir is None else bench_dir)
    lock.write_text(f"tasks:{d}\nevaluator:{e}\n")
    return d


def read_lock(lock: Path = LOCK):
    """Parse a v2 lock into {"tasks": hex, "evaluator": hex}; None if missing or not exactly v2."""
    try:
        text = lock.read_text()
    except (OSError, UnicodeError):
        # unreadable or non-UTF8 lock == no valid lock: fail closed (verify_lock -> False)
        return None
    lines = text.splitlines()
    if len(lines) != 2:
        return None
    out = {}
    for line, key in zip(lines, ("tasks", "evaluator")):
        prefix = key + ":"
        val = line[len(prefix):]
        if not line.startswith(prefix) or len(val) != 64 or any(c not in "0123456789abcdef" for c in val):
            return None
        out[key] = val
    return out


def verify_lock(tasks_dir: Path = ROOT / "tasks", lock: Path = LOCK, bench_dir=None) -> bool:
    got = read_lock(lock)
    if got is None:
        return False
    if find_symlinks(ROOT if bench_dir is None else bench_dir, tasks_dir):
        return False
    return (got["tasks"] == suite_hash(tasks_dir)
            and got["evaluator"] == evaluator_hash(ROOT if bench_dir is None else bench_dir))
