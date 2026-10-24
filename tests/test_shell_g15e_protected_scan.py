"""G15e Unit B: the shell() argv scan over the shared protected-path set.

Recording fakes only. The pure rows drive `_shell_command_targets_protected_path`
with a disposable HOME / state dir / audit sink / CODE_DIR and recording
`listdir` / `is_exec` fakes. The end-to-end rows go through the real `shell()`
and the real `TaskExecutor._daemon_shell` with `subprocess.run` replaced by a
recorder, so no command ever executes. The only filesystem objects created are
inside tmp_path (including a planted symlink used to test the resolved form).

`classify_shell_command` is deliberately not involved in the scan; one test
proves the classifier is unchanged even when every discovery primitive raises.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import core.protected_paths as pp
from core import action_gateway, task_executor
from core.action_gateway import ACT, HIGH_IMPACT, ActionGateway
from tools import shell_tools
from utils.config import AGENT_CONFIG

MUTATORS = ["cp", "mv", "ln", "touch", "mkdir", "rm", "rmdir", "chmod", "dd"]


class Fakes:
    def __init__(self, names=(), execs=()):
        self.names = list(names)
        self.execs = set(execs)

    def listdir(self, path):
        return list(self.names)

    def is_exec(self, path):
        return path in self.execs


@pytest.fixture
def world(tmp_path, monkeypatch):
    import utils.config as cfg

    home = tmp_path / "home"
    state = tmp_path / "state"
    code = tmp_path / "code"
    ws = tmp_path / "ws"
    audit = tmp_path / "audit.jsonl"
    pbin = tmp_path / "pbin" / "bin"
    for d in (home, state, code, ws, pbin, code / "lib", code / "core"):
        d.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEY_STATE_DIR", str(state))
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(audit))
    monkeypatch.delenv("CODEY_CONFIG_PATH", raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join([str(pbin), str(code)]))
    monkeypatch.setattr(cfg, "CODEY_STATE_DIR", state)
    monkeypatch.setattr(cfg, "WORKSPACE_ROOT", ws)
    monkeypatch.setattr(shell_tools._config, "CODEY_STATE_DIR", state)
    monkeypatch.setattr(shell_tools._config, "WORKSPACE_ROOT", ws)
    monkeypatch.setattr(shell_tools, "CODE_DIR", code)
    monkeypatch.chdir(ws)
    return SimpleNamespace(home=home, state=state, code=code, ws=ws, audit=audit, pbin=pbin)


def make_ctx(w, fakes=None, config_paths=None):
    fakes = fakes or Fakes()
    return pp.build_context(
        code_dir=w.code, workspace_root=w.ws, home=w.home, state_dir=w.state,
        audit=w.audit,
        config_paths=config_paths if config_paths is not None else [w.state / "config.json"],
        path_env=os.pathsep.join([str(w.pbin), str(w.code)]),
        listdir=fakes.listdir, is_exec=fakes.is_exec,
    )


def scan(w, command, *, cwd=None, fakes=None):
    return shell_tools._shell_command_targets_protected_path(
        command, cwd=Path(cwd or w.ws), home=w.home, ctx=make_ctx(w, fakes),
    )


def targets(w):
    """rule id -> a protected target spelled as an absolute path."""
    return {
        "git-component": str(w.ws / "proj" / "sub" / ".git" / "hooks" / "pre-commit"),
        "git-component-sibling": str(w.home.parent / "sibling" / ".git" / "config"),
        "git-component-case": str(w.ws / "proj" / ".GIT" / "config"),
        "audit-sink": str(w.audit),
        "state-dir": str(w.state / "state.db"),
        "config-active": str(w.state / "config.json"),
        "home-startup": str(w.home / ".bashrc"),
        "home-credential": str(w.home / ".ssh" / "authorized_keys"),
        "home-git": str(w.home / ".gitconfig"),
        "home-git-config": str(w.home / ".config" / "git" / "config"),
        "home-termux": str(w.home / ".termux" / "boot" / "start.sh"),
        "path-dedicated": str(w.pbin / "ls"),
        "path-dedicated-home": str(w.home / "bin" / "ls"),
        "f3-launcher": str(w.code / "main.py"),
        "f3-launcher-metrics": str(w.code / "codey-metrics"),
        "f3-script-lib": str(w.code / "lib" / "service_manager.sh"),
        "f3-script-install": str(w.code / "install.sh"),
        "f3-config": str(w.code / "config.json"),
        "f3-plugin-data": str(w.code / "ccos" / "plugins" / "x" / "manifest.json"),
        "core-py-mirror": str(w.code / "core" / "agent.py"),
    }


# --- 1. mutator x rule cross product: zero misses ---------------------------

@pytest.mark.parametrize("base", MUTATORS)
def test_mutators_hit_every_rule_class(world, base):
    misses = []
    for name, target in targets(world).items():
        if scan(world, f"{base} x {target}") is None:
            misses.append(name)
    assert misses == []


def test_path_shadow_rule_for_mutators_uses_fakes(world):
    fakes = Fakes(names=["ls", "install"])
    assert scan(world, f"touch {world.code / 'ls'}", fakes=fakes) == "path-shadow"
    assert scan(world, f"cp x {world.code / 'install'}", fakes=fakes) == "path-shadow"
    assert scan(world, f"touch {world.code / 'notes.txt'}", fakes=fakes) is None
    fakes = Fakes(execs={str(world.code / "newtool")})
    assert scan(world, f"touch {world.code / 'newtool'}", fakes=fakes) == "path-shadow"


@pytest.mark.parametrize("template", [
    "dd if=/dev/zero of={t}",
    "ln -s {t} innocent",
    "ln -s payload {t}",
    "cp -t {t} x",
    "cp --target-directory={t} x",
    "chmod --reference={t} y",
    "touch -r {t} y",
    "touch -d 2020-01-01 {t}",
    "mv --target-directory {t} y",
    "cp -a{t} y",
])
def test_operand_forms_found_without_positional_parsing(world, template):
    t = targets(world)["home-startup"]
    assert scan(world, template.format(t=t)) == "home-startup"


def test_gnu_long_option_abbreviation_does_not_hide_operand(world):
    t = targets(world)["home-startup"]
    for opt in ("--targ=" + t, "--target-dir=" + t, "--tar=" + t):
        assert scan(world, f"cp {opt} x") == "home-startup"


# --- 2. alias spelling, case, tilde, relative -------------------------------

def test_alias_and_case_and_tilde_forms(tmp_path, monkeypatch):
    # Synthetic home under the real /data/data prefix; nothing is created.
    home = Path("/data/data/com.termux/files/g15e_fake_home")
    state = tmp_path / "state"
    code = tmp_path / "code"
    ws = tmp_path / "ws"
    w = SimpleNamespace(home=home, state=state, code=code, ws=ws, audit=tmp_path / "a.jsonl",
                        pbin=tmp_path / "pbin" / "bin")
    alias_bashrc = "/data/user/0/com.termux/files/g15e_fake_home/.bashrc"
    assert scan(w, f"cp x {alias_bashrc}") == "home-startup"
    assert scan(w, f"cp x {str(home / '.BASHRC')}") == "home-startup"
    assert scan(w, "cp x ~/.bashrc") == "home-startup"
    assert scan(w, "cp x $HOME/.bashrc") == "home-startup"
    assert scan(w, "cp x ${HOME}/.bashrc") == "home-startup"
    assert scan(w, f"cp x {home}/.ssh/../.bashrc") == "home-startup"
    assert scan(w, "cp x .bashrc", cwd=home) == "home-startup"


# --- 3. runners: every rule except runner-exempt / path-shadow ---------------

@pytest.mark.parametrize("command", [
    "python3 {main}", "bash {install}", "bash {launcher}", "sh {lib}",
    "python3 {manifest}", "python {cfg}", "node {main}", "make -f {install}",
    "python3 script.py --out {startup}", "pip install -r {state}",
    "pytest --ignore={git}",
])
def test_runners_flag_f3_and_non_repo_rules(world, command):
    t = targets(world)
    cmd = command.format(
        main=t["f3-launcher"], install=t["f3-script-install"], launcher=str(world.code / "codeyOS"),
        lib=t["f3-script-lib"], manifest=t["f3-plugin-data"], cfg=t["f3-config"],
        startup=t["home-startup"], state=t["state-dir"], git=t["git-component"],
    )
    assert scan(world, cmd) is not None, cmd


@pytest.mark.parametrize("command", [
    "python3 core/agent.py", "python3 tools/wp21_census.py", "pytest tests",
    "python3 -m pytest -q", "pip install requests", "make test", "npm install",
    "pytest tests/test_x.py -k a", "python3 script.py",
])
def test_runners_not_flagged_for_core_py_or_subcommand_names(world, command):
    # cwd == CODE_DIR is the worst case: `pytest`, `install`, `test` are real
    # command names in PATH and would be path-shadow hits if applied to runners.
    fakes = Fakes(names=["pytest", "install", "test", "make", "npm", "pip"])
    assert scan(world, command, cwd=world.code, fakes=fakes) is None


def test_runner_exempt_rows_are_skipped_for_runners_only(world, monkeypatch):
    monkeypatch.setattr(pp, "BENCH_EVALUATOR_SUBTREES", ("bench",))
    bench = str(world.code / "bench" / "grader.py")
    assert scan(world, f"python3 {bench}") is None
    assert scan(world, f"pytest {bench}") is None
    assert scan(world, f"cp x {bench}") == "bench-evaluator"
    assert scan(world, f"touch {bench}") == "bench-evaluator"


def test_core_py_mirror_mutator_only(world):
    core_py = str(world.code / "core" / "agent.py")
    assert scan(world, f"python3 {core_py}") is None
    assert scan(world, f"cp x {core_py}") == "core-py-mirror"
    assert scan(world, f"dd of={core_py}") == "core-py-mirror"


def test_unknown_base_is_scanned_by_default(world):
    t = targets(world)["home-startup"]
    assert scan(world, f"someunknowntool {t}") == "home-startup"
    assert scan(world, f"termux-open {t}") == "home-startup"
    assert scan(world, f"termux-clipboard-set {t}") == "home-startup"


# --- 4. exempt bases and READ -----------------------------------------------

@pytest.mark.parametrize("command", [
    "cat {main}", "sed --sandbox -n p {main}", "echo {startup}", "grep -r x {code}",
    "ls {pbin}", "head {startup}", "tail {startup}", "diff {main} {startup}",
    "wc {main}", "stat {startup}", "cd {code}", "cut -d: -f1 {startup}",
    "tr a b", "termux-clipboard-get", "git status {git}", "pwd", "which {main}",
])
def test_exempt_bases_not_scanned(world, command):
    t = targets(world)
    cmd = command.format(main=t["f3-launcher"], startup=t["home-startup"],
                         code=world.code, pbin=world.pbin, git=t["git-component"])
    assert scan(world, cmd) is None, cmd


# --- 5. ancestor rule --------------------------------------------------------

@pytest.mark.parametrize("command", [
    "rm -rf {home}", "rm -rf {home}/.config", "cp -r payload {home}", "ln -s x {home}",
    "mv {state} elsewhere", "chmod -R 700 {home}", "rmdir {home}", "mv x {home}/..",
    "cp -r payload {home}/.config", "rm -rf {state}", "cp x {code}", "rm -rf {pbin}",
])
def test_ancestor_rule_hits(world, command):
    cmd = command.format(home=world.home, state=world.state, code=world.code, pbin=world.pbin)
    assert scan(world, cmd) is not None, cmd


def test_ancestor_rule_relative_dot_forms(world):
    assert scan(world, "cp x .", cwd=world.code) is not None
    assert scan(world, "mv x ..", cwd=world.home) is not None
    assert scan(world, "rm -rf .", cwd=world.home) is not None
    # Same operands on non-ancestor bases and exempt bases do not hit.
    assert scan(world, "ls .", cwd=world.code) is None
    assert scan(world, "pytest .", cwd=world.code) is None
    assert scan(world, "python3 -m pytest ..", cwd=world.home) is None
    # touch/mkdir/dd are not ancestor bases: creating the directory itself is not a plant.
    assert scan(world, f"mkdir -p {world.home}/projects/new") is None


def test_ordinary_workspace_mutations_are_clean(world):
    fakes = Fakes(names=["ls", "cat", "test"])
    for command in (
        "cp a.txt b.txt", "mv old.txt new.txt", "touch notes.txt", "mkdir -p out/sub",
        "rm build.log", "chmod +x tools/new.py", "ln -s a.txt b.txt", "dd if=a of=b",
        f"cp x {world.ws}/proj/readme.md", "mkdir .github",
    ):
        assert scan(world, command, fakes=fakes) is None, command


# --- 6. symlink plant (reviewer-found class) ---------------------------------

def test_ln_plants_are_caught_on_link_name_and_target(world):
    t = targets(world)
    # link NAME in a protected script area, harmless target
    assert scan(world, f"ln -s harmless.txt {world.code}/lib/innocent.sh") == "f3-script"
    assert scan(world, f"ln -sf harmless.txt {world.code}/lib/innocent.txt") == "f3-script"
    assert scan(world, f"ln -s harmless.txt {world.code}/ccos/plugins/x/run.sh") == "f3-script"
    # protected TARGET, innocent link name
    assert scan(world, f"ln -s {t['home-startup']} innocent") == "home-startup"
    assert scan(world, f"ln -s {t['f3-launcher']} innocent") == "f3-launcher"
    assert scan(world, f"ln -s {world.state} innocent") == "state-dir"


def test_existing_workspace_symlink_into_protected_path_is_caught_resolved(world):
    link = world.ws / "innocent"
    link.symlink_to(world.home / ".bashrc")
    assert scan(world, "cp x innocent") == "home-startup"
    assert scan(world, "touch innocent") == "home-startup"
    assert scan(world, "python3 innocent") == "home-startup"
    # A symlink planted AT a protected name is judged by its own (lexical) name.
    (world.home / ".profile").symlink_to(world.ws / "harmless")
    assert scan(world, f"cp x {world.home / '.profile'}") == "home-startup"
    # Structural (non-enumerable) rule: only the lexical form can match, because
    # the symlink's target is an innocent workspace file.
    (world.code / "lib" / "planted.sh").symlink_to(world.ws / "other-innocent")
    assert scan(world, f"cp x {world.code / 'lib' / 'planted.sh'}") == "f3-script"


# --- 7. fail closed ---------------------------------------------------------

def test_nul_and_resolve_failure_fail_closed(world, monkeypatch):
    assert scan(world, "cp x a\x00b") == "unresolvable-operand"

    def boom(self, strict=False):
        raise RuntimeError("symlink loop")
    monkeypatch.setattr(Path, "resolve", boom)
    assert shell_tools._shell_command_targets_protected_path(
        "cp x y", cwd=world.ws, home=world.home, ctx=SimpleNamespace(entries=()),
    ) == "unresolvable-operand"


def test_scan_error_rule_when_context_build_raises(world, monkeypatch):
    def boom(**kw):
        raise OSError("nope")
    monkeypatch.setattr(pp, "build_context", boom)
    assert shell_tools._scan_protected_safely("python3 x.py") == "scan-error"
    # exempt commands never reach the build, so they are unaffected
    assert shell_tools._scan_protected_safely("cat x") is None
    assert shell_tools._scan_protected_safely("") is None


# --- 8. drift guards ---------------------------------------------------------

def test_exempt_list_is_pinned_exactly():
    assert shell_tools._PROTECTED_SCAN_EXEMPT_BASES == frozenset(
        shell_tools.READ_COMMANDS) | {"echo", "cd", "cut", "tr", "sed", "termux-clipboard-get"}
    assert shell_tools._PROTECTED_SCAN_EXEMPT_BASES == frozenset({
        "cat", "date", "df", "diff", "du", "file", "grep", "head", "ls", "printenv", "pwd",
        "sort", "stat", "tail", "tree", "uniq", "wc", "which", "whoami",
        "echo", "cd", "cut", "tr", "sed", "termux-clipboard-get",
    })
    assert shell_tools._PROTECTED_MUTATOR_BASES == frozenset(MUTATORS)
    assert shell_tools._PROTECTED_ANCESTOR_BASES == frozenset({"cp", "mv", "ln", "rm", "rmdir", "chmod"})
    assert shell_tools._PROTECTED_RUNNER_SKIP_RULES == frozenset({"core-py-mirror", "path-shadow"})


def test_every_allowed_or_dangerous_base_has_exactly_one_role():
    exempt = shell_tools._PROTECTED_SCAN_EXEMPT_BASES
    mut = shell_tools._PROTECTED_MUTATOR_BASES
    assert not (exempt & mut)
    universe = set(shell_tools.ALLOWED_COMMANDS) | set(shell_tools.DANGEROUS_COMMANDS)
    assert mut <= universe
    for base in universe:
        role = (base in exempt) + (base in mut)
        assert role <= 1, base
    # Every exempt base is read-only by construction: a READ command, or one of the
    # documented non-READ write-less bases.
    assert exempt - set(shell_tools.READ_COMMANDS) == {"echo", "cd", "cut", "tr", "sed", "termux-clipboard-get"}


def test_new_allowed_base_is_scanned_by_default(monkeypatch):
    monkeypatch.setattr(shell_tools, "ALLOWED_COMMANDS", set(shell_tools.ALLOWED_COMMANDS) | {"newtool"})
    assert shell_tools._protected_scan_base("newtool x") == "newtool"
    assert shell_tools._protected_scan_base("cat x") is None
    assert shell_tools._protected_scan_base("git status") is None


# --- 9. classifier invariance (P2) ------------------------------------------

CORPUS = [
    "ls", "cat main.py", "cp a b", "mv a b", "rm -rf x", "touch f", "mkdir d", "ln -s a b",
    "chmod +x f", "dd if=a of=b", "python3 main.py", "python3 -m pytest", "pytest tests",
    "pip install x", "npm test", "node x.js", "sed -n p f", "sed --sandbox -n p f",
    "sort -o x y", "grep -r a .", "find . -name x", "env", "printenv HOME", "echo hi",
    "git status", "git push", "curl x", "wget x", "bash install.sh", "./codeyOS",
    "/bin/ls", "head f", "tail f", "wc f", "du -sh .", "df", "date", "uniq f", "tree",
    "file f", "stat f", "which ls", "whoami", "pwd", "cd x", "awk 1 f", "xargs ls",
    "make", "gcc x.c", "cargo build", "tr a b", "cut -c1 f", "diff a b", "cat ~/.ssh/id_rsa",
    "rm ~/.bashrc", "cp x ~/.bashrc", "touch lib/x.sh", "ln -s x lib/y.sh", "mkdir .git",
]


def test_classifier_is_independent_of_the_protected_module(monkeypatch):
    baseline = {c: shell_tools.classify_shell_command(c) for c in CORPUS}

    def boom(*a, **k):
        raise AssertionError("classifier touched discovery")

    for name in ("build_context", "first_hit", "ancestor_hit", "has_git_component",
                 "shadow_names", "fold", "canon"):
        monkeypatch.setattr(pp, name, boom)
    monkeypatch.setattr(Path, "resolve", boom)
    monkeypatch.setattr(Path, "exists", boom)
    monkeypatch.setattr(os, "listdir", boom)
    after = {c: shell_tools.classify_shell_command(c) for c in CORPUS}
    assert after == baseline


def test_classifier_still_does_not_flag_protected_targets():
    # The scan lives in shell(); the classifier alone still labels these ACT.
    assert shell_tools.classify_shell_command("ln -s /usr/bin/git ls") == ACT
    assert shell_tools.classify_shell_command("touch ~/.bashrc") == ACT


# --- 10. end to end through the real shell() --------------------------------

@pytest.fixture
def e2e(world, monkeypatch):
    instance = ActionGateway(audit_file=world.audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(shell_tools, "_command_shadows_system_binary", lambda command: False)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    monkeypatch.delitem(AGENT_CONFIG, "_shell_fn", raising=False)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    prompt = Mock(return_value=True)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    warnings = []
    monkeypatch.setattr(shell_tools, "warning", warnings.append)
    world.runner, world.prompt, world.warnings = runner, prompt, warnings
    return world


def rows(w):
    return [json.loads(line) for line in w.audit.read_text().splitlines()]


@pytest.mark.parametrize("name", [
    "home-startup", "home-git", "home-termux", "home-credential", "state-dir", "audit-sink",
    "f3-launcher", "f3-script-lib", "f3-config", "f3-plugin-data", "git-component", "path-dedicated",
])
@pytest.mark.parametrize("base", ["cp", "touch", "mkdir", "ln -s x", "chmod +x", "mv x", "rm", "dd of="])
def test_shell_refuses_protected_mutation_confirm_less(e2e, name, base):
    target = targets(e2e)[name]
    command = f"{base}{target}" if base.endswith("=") else f"{base} {target}"
    out = shell_tools.shell(command)
    assert out.startswith("[BLOCKED]"), (command, out)
    e2e.runner.assert_not_called()
    row = rows(e2e)[-1]
    assert row["action"] == "shell_tools.shell"
    assert row["authority"] == HIGH_IMPACT and row["outcome"] == "refused"


def test_shell_symlink_plant_refused_and_ordinary_cp_runs(e2e):
    out = shell_tools.shell(f"ln -s harmless.txt {e2e.code}/lib/innocent.sh")
    assert out.startswith("[BLOCKED]")
    e2e.runner.assert_not_called()
    assert shell_tools.shell("cp a.txt b.txt") == "ok"
    e2e.runner.assert_called_once()
    assert rows(e2e)[-1]["authority"] == ACT


def test_shell_exempt_and_clean_commands_unchanged(e2e):
    for command in (f"cat {targets(e2e)['f3-launcher']}", f"ls {e2e.home}/.bashrc", "echo hi"):
        e2e.runner.reset_mock()
        assert not shell_tools.shell(command).startswith("[BLOCKED]"), command
        e2e.runner.assert_called_once()
        assert rows(e2e)[-1]["authority"] in (ACT, "READ", "read")


def test_shell_scan_error_refuses(e2e, monkeypatch):
    def boom(**kw):
        raise RuntimeError("x")
    monkeypatch.setattr(pp, "build_context", boom)
    out = shell_tools.shell("python3 script.py")
    assert out.startswith("[BLOCKED]")
    e2e.runner.assert_not_called()


def test_shell_repl_prompts_with_protected_warning(e2e, monkeypatch):
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", True)
    target = targets(e2e)["home-startup"]
    e2e.prompt.return_value = False
    out = shell_tools.shell(f"touch {target}")
    assert out.startswith("[CANCELLED]")
    e2e.runner.assert_not_called()
    assert any("protected path (home-startup)" in w for w in e2e.warnings)
    assert rows(e2e)[-1]["outcome"] == "refused"
    e2e.prompt.return_value = True
    e2e.warnings.clear()
    assert shell_tools.shell(f"touch {target}") == "ok"
    e2e.runner.assert_called_once()
    assert any("protected path (home-startup)" in w for w in e2e.warnings)
    assert rows(e2e)[-1]["authority"] == HIGH_IMPACT


def test_shell_yolo_flag_cannot_unlock_protected_scan(e2e, monkeypatch):
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", True)
    out = shell_tools.shell(f"touch {targets(e2e)['home-startup']}", yolo=True)
    assert out.startswith("[BLOCKED]")
    e2e.runner.assert_not_called()


# --- 11. daemon end to end ---------------------------------------------------

def daemon(command):
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    return executor._daemon_shell(command)


@pytest.mark.parametrize("command", [
    "python3 {main}", "python3 {install}", "python3 {manifest}",
])
def test_daemon_refuses_f3_script_operands(e2e, command):
    t = targets(e2e)
    cmd = command.format(main=t["f3-launcher"], install=t["f3-script-install"], manifest=t["f3-plugin-data"])
    assert daemon(cmd).startswith("[BLOCKED]"), cmd
    e2e.runner.assert_not_called()
    row = rows(e2e)[-1]
    assert row["action"] == "shell_tools.shell"
    assert row["authority"] == HIGH_IMPACT and row["outcome"] == "refused"


def test_daemon_relative_f3_operand_from_repo_root(e2e, monkeypatch):
    monkeypatch.chdir(e2e.code)
    assert daemon("python3 main.py").startswith("[BLOCKED]")
    assert daemon("python3 install.sh").startswith("[BLOCKED]")
    e2e.runner.assert_not_called()


@pytest.mark.parametrize("command", [
    "python3 tests/x.py", "pytest tests", "ls", "echo hi", "grep -r x .",
])
def test_daemon_ordinary_forms_unchanged(e2e, monkeypatch, command):
    monkeypatch.chdir(e2e.code)
    assert not daemon(command).startswith("[BLOCKED]"), command
    e2e.runner.assert_called_once()


def test_daemon_cat_of_f3_file_is_not_blocked(e2e):
    assert not daemon(f"cat {targets(e2e)['f3-launcher']}").startswith("[BLOCKED]")
    e2e.runner.assert_called_once()


def test_daemon_shell_source_is_unchanged_in_behavior_shape():
    # _daemon_shell must still end in shell(command, yolo=True): the scan lives
    # in shell(), so the daemon is covered with no second implementation.
    import inspect
    assert "return shell(command, yolo=True)" in inspect.getsource(task_executor.TaskExecutor._daemon_shell)
