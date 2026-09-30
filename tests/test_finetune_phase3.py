"""AGI audit Phase 3: 4b notebook, verified data path, CLI/instruction fixes."""
import ast
import json
import re

import pytest

from core import trajectory as tj
from core.finetune_prep import DatasetCurator, export_dataset, generate_notebook


def _cells(path):
    nb = json.load(open(path))
    assert nb["nbformat"] == 4
    return nb["cells"]


def test_4b_notebook_targets_deployed_model_and_is_valid(tmp_path):
    path = generate_notebook("4b", str(tmp_path))
    cells = _cells(path)
    assert len(cells) >= 6
    allsrc = "".join("".join(c["source"]) for c in cells)
    assert "Qwen/Qwen3.5-4B" in allsrc and "Qwen2.5" not in allsrc
    assert "load_in_16bit=True" in allsrc and "load_in_4bit" not in allsrc
    assert "transformers>=5" in allsrc
    assert "{" + "model_id" not in allsrc  # no unformatted placeholders
    for c in cells:  # every code cell must be syntactically valid Python (shell magics removed)
        if c["cell_type"] == "code":
            code = "".join(l for l in c["source"] if not l.lstrip().startswith("!"))
            ast.parse(code)


def test_notebook_sources_keep_line_endings(tmp_path):
    for variant in ("4b", "1.5b"):
        cells = _cells(generate_notebook(variant, str(tmp_path)))
        multi = [c for c in cells if len(c["source"]) > 1]
        assert multi and all(l.endswith("\n") for c in multi for l in c["source"][:-1]), variant


def test_export_4b(tmp_path):
    ex = [{"conversations": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]}]
    out, n = export_dataset(ex, str(tmp_path), "4b")
    assert out.endswith("codey-finetune-4b.jsonl") and n == 1


def _seed(db, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY_DB", str(db))
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")
    monkeypatch.setenv("CODEY_TRAJECTORY_TAG", "T")

    def agent(msg, history, yolo=False):
        tj.instrument_execute_tool(lambda d: "file contents")({"name": "read_file", "args": {"path": "a.py"}})
        return "Done.", history
    w = tj.instrument_run_agent(agent)
    w("fix a.py", []); w("other", [])


def test_curate_verified_uses_only_externally_labeled_passes(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    _seed(db, monkeypatch)
    cur = DatasetCurator.__new__(DatasetCurator)
    assert cur.curate_verified() == []  # nothing labeled yet
    tj.label_episode(1, "pytest", True)
    tj.label_episode(2, "pytest", False)
    ex = cur.curate_verified()
    assert len(ex) == 1
    roles = [m["role"] for m in ex[0]["conversations"]]
    assert roles == ["system", "user", "assistant", "user", "assistant"]
    assert "<tool>" in ex[0]["conversations"][2]["content"]
    assert ex[0]["metadata"]["verified"] is True and ex[0]["metadata"]["verifier"] == "pytest"


def test_curate_examples_verified_only_skips_heuristic_path(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    _seed(db, monkeypatch)
    tj.label_episode(1, "pytest", True)
    cur = DatasetCurator.__new__(DatasetCurator)
    cur.get_episodic_actions = lambda *a, **k: (_ for _ in ()).throw(AssertionError("legacy path used"))
    assert len(cur.curate_examples(verified_only=True)) == 1


def test_reading_verified_does_not_create_db(tmp_path, monkeypatch):
    db = tmp_path / "missing.db"
    monkeypatch.setenv("CODEY_TRAJECTORY_DB", str(db))
    assert tj.verified_episodes() == [] and not db.exists()


def test_cli_and_instructions_fixed(capsys):
    src = open("main.py").read()
    m = re.search(r'"--ft-model", choices=\[(.*?)\], default="(\w+)"', src)
    assert '"4b"' in m.group(1) and m.group(2) == "4b"
    from core.finetune_prep import print_instructions
    print_instructions("d.jsonl", "n.ipynb", "4b")
    out = capsys.readouterr().out
    assert "--lora-merge" in out and "--model 4b" not in out and "bench.promote" in out
