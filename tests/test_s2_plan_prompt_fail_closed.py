"""S2-E: the two default-Yes plan-approval prompts (core/agent.py run_agent
orchestrator gate, core/planner.py show_and_confirm_plan) must not read stdin
off-tty. Recording fakes only; no model loads."""

import io
import sys
import types

import pytest

import utils.logger as logger


class _Stdin:
    def __init__(self, text, tty):
        self._io = io.StringIO(text)
        self._tty = tty
        self.reads = 0

    def isatty(self):
        return self._tty

    def readline(self, *a):
        self.reads += 1
        return self._io.readline(*a)

    read = readline


class _Console:
    """Stand-in console: input() pops scripted answers and counts calls."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts = []

    def input(self, prompt=""):
        self.prompts.append(prompt)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)

    def print(self, *a, **k):
        pass

    def rule(self, *a, **k):
        pass


# ---------------------------------------------------------------- planner

@pytest.fixture
def planner_env(monkeypatch):
    import core.planner as planner

    def make(answers, tty):
        con = _Console(answers)
        monkeypatch.setattr(planner, "console", con)
        monkeypatch.setattr(planner, "separator", lambda: None)
        monkeypatch.setattr(logger, "_stdin_is_tty", lambda: tty)
        return planner, con

    return make


@pytest.mark.parametrize("ans", ["y", "", "yes", "edit text"])
def test_planner_non_tty_rejects_and_never_reads(planner_env, monkeypatch, ans):
    fake = _Stdin(ans + "\nrevised\n", tty=False)
    monkeypatch.setattr(sys, "stdin", fake)
    planner, con = planner_env([ans, "revised"], tty=False)
    assert planner.show_and_confirm_plan("1. do it") == (False, "1. do it")
    assert con.prompts == []  # neither the approval nor the edit prompt
    assert fake.reads == 0 and fake._io.tell() == 0


@pytest.mark.parametrize("ans", ["", "y", "yes"])
def test_planner_tty_default_yes_approves(planner_env, ans):
    planner, con = planner_env([ans], tty=True)
    assert planner.show_and_confirm_plan("P") == (True, "P")
    assert len(con.prompts) == 1


@pytest.mark.parametrize("ans", ["n", "no"])
def test_planner_tty_no_rejects(planner_env, ans):
    planner, con = planner_env([ans], tty=True)
    assert planner.show_and_confirm_plan("P") == (False, "P")


def test_planner_tty_edit_path_unchanged(planner_env):
    planner, con = planner_env(["edit", "do X instead"], tty=True)
    assert planner.show_and_confirm_plan("P") == (True, "do X instead")
    assert len(con.prompts) == 2


def test_planner_tty_eof_rejects(planner_env):
    planner, con = planner_env([], tty=True)
    assert planner.show_and_confirm_plan("P") == (False, "P")


# ------------------------------------------------------------------ agent

@pytest.fixture
def agent_env(monkeypatch):
    import core.agent as agent
    import core.display as display
    import core.orchestrator as orch

    def make(answers, tty):
        con = _Console(answers)
        calls = {"run_queue": 0}
        queue = types.SimpleNamespace(
            tasks=[types.SimpleNamespace(status="done", description="t")],
            done_count=lambda: 1,
        )
        monkeypatch.setattr(display, "console", con)
        monkeypatch.setattr(display, "show_task_plan", lambda q: None)
        monkeypatch.setattr(orch, "is_complex", lambda m, score=None: True)
        monkeypatch.setattr(orch, "plan_tasks", lambda m, c: queue)

        def rq(q, yolo=False):
            calls["run_queue"] += 1

        monkeypatch.setattr(orch, "run_queue", rq)
        monkeypatch.setattr(agent, "read_codeymd", lambda *a, **k: "")
        monkeypatch.setattr(agent, "auto_load_from_prompt", lambda *a, **k: None)
        monkeypatch.setattr(agent, "get_context_usage", lambda *a, **k: (10**9, 1))
        monkeypatch.setattr(logger, "_stdin_is_tty", lambda: tty)
        return agent, con, calls

    return make


def _run(agent):
    return agent.run_agent("build and test a large multi step feature", [], yolo=True)


@pytest.mark.parametrize("ans", ["y", "", "edit text"])
def test_agent_non_tty_cancels_unread_and_no_run_queue(agent_env, monkeypatch, ans):
    fake = _Stdin(ans + "\n", tty=False)
    monkeypatch.setattr(sys, "stdin", fake)
    agent, con, calls = agent_env([ans], tty=False)
    resp, _ = _run(agent)
    assert resp == "[Cancelled]"
    assert con.prompts == [] and calls["run_queue"] == 0
    assert fake.reads == 0 and fake._io.tell() == 0


@pytest.mark.parametrize("ans", ["", "y", "yes"])
def test_agent_tty_default_yes_proceeds(agent_env, ans):
    agent, con, calls = agent_env([ans], tty=True)
    resp, _ = _run(agent)
    assert resp.startswith("Completed 1/1") and calls["run_queue"] == 1
    assert len(con.prompts) == 1


@pytest.mark.parametrize("ans", ["n", "no"])
def test_agent_tty_no_cancels(agent_env, ans):
    agent, con, calls = agent_env([ans], tty=True)
    resp, _ = _run(agent)
    assert resp == "[Cancelled]" and calls["run_queue"] == 0


def test_agent_tty_eof_cancels(agent_env):
    agent, con, calls = agent_env([], tty=True)
    resp, _ = _run(agent)
    assert resp == "[Cancelled]" and calls["run_queue"] == 0


# ----------------------------------------------- unattended modes unchanged

@pytest.mark.parametrize("kw", [{"no_plan": True}, {"_in_subtask": True}])
def test_unattended_modes_never_reach_prompt(agent_env, monkeypatch, kw):
    """daemon/task_executor/main plan steps (no_plan=True) and orchestrator
    sub-tasks (_in_subtask=True) skip the orchestrator gate entirely, so they
    never depended on the prompt auto-proceeding. Fake the loop-side so the
    test stops right after the gate."""
    agent, con, calls = agent_env([], tty=False)
    import core.memory_v2 as mem

    class Stop(Exception):
        pass

    monkeypatch.setattr(mem.memory, "tick", lambda: (_ for _ in ()).throw(Stop()))
    with pytest.raises(Stop):
        agent.run_agent("build and test a large multi step feature", [], yolo=True, **kw)
    assert con.prompts == [] and calls["run_queue"] == 0
