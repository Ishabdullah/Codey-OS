"""Suite integrity lock: sha256 over every task file. Detects tampering/drift."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).parent
LOCK = ROOT / "suite.lock"


def suite_hash(tasks_dir: Path = ROOT / "tasks") -> str:
    h = hashlib.sha256()
    for p in sorted(tasks_dir.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            h.update(str(p.relative_to(tasks_dir)).encode())
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def write_lock(tasks_dir: Path = ROOT / "tasks", lock: Path = LOCK) -> str:
    d = suite_hash(tasks_dir)
    lock.write_text(d + "\n")
    return d


def verify_lock(tasks_dir: Path = ROOT / "tasks", lock: Path = LOCK) -> bool:
    if not lock.exists():
        return False
    return lock.read_text().strip() == suite_hash(tasks_dir)
