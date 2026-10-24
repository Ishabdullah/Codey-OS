"""G15f Unit B: every file under bench/ is HIGH_IMPACT for the agent write tools
(G15e Unit C landed the `bench/**` row; this is the enumerating pin so a NEW file
cannot sit outside it). Disposable dirs only; nothing is run or executed."""
from pathlib import Path

import pytest

import core.checkpoint as checkpoint_module
from tools.file_tools import ACT, HIGH_IMPACT, classify_write_action

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def code(tmp_path, monkeypatch):
    code = tmp_path / "code"
    code.mkdir()
    monkeypatch.setattr(checkpoint_module, "CODE_DIR", code)
    return code


def _bench_files():
    out = []
    for p in sorted((REPO / "bench").rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            out.append(p.relative_to(REPO).as_posix())
    return out


def test_bench_files_enumerated():
    files = _bench_files()
    assert "bench/suite.lock" in files and "bench/lock.py" in files and len(files) > 20


def test_every_bench_file_is_high_impact(code):
    bad = [rel for rel in _bench_files()
           if classify_write_action(str(code / rel)) != HIGH_IMPACT]
    assert bad == []


@pytest.mark.parametrize("rel", ["benchmark/x.json", "x/bench/a.json", "bench.json"])
def test_lookalikes_stay_act(code, rel):
    assert classify_write_action(str(code / rel)) == ACT
