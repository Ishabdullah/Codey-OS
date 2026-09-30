"""Task loading. Layout: tasks/<id>/{prompt.txt, starter/, hidden/, reference/}."""
from dataclasses import dataclass
from pathlib import Path

TASKS = Path(__file__).parent / "tasks"


@dataclass(frozen=True)
class Task:
    id: str
    dir: Path

    @property
    def prompt(self) -> str:
        return (self.dir / "prompt.txt").read_text().strip()

    @property
    def starter(self) -> Path:
        return self.dir / "starter"

    @property
    def hidden(self) -> Path:
        return self.dir / "hidden"

    @property
    def reference(self) -> Path:
        return self.dir / "reference"


def load_tasks(tasks_dir: Path = TASKS):
    return [Task(p.name, p) for p in sorted(tasks_dir.iterdir())
            if p.is_dir() and (p / "prompt.txt").exists()]
