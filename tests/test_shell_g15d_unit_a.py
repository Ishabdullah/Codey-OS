"""G15d Unit A: D-3 slash rule, D-2 env/printenv + credential-path scan, text-tool
option tables (sed/sort/uniq/tree/file/awk), PATH-shadow check, shared walker.

Recording fakes only: subprocess.run is replaced before any call reaches
shell(), and refusals assert it was never called. The only real processes are
the benign real-parser smoke rows at the bottom (admitted forms on scratch
files, no shell() involved). HOME, CODEY_STATE_DIR and the gateway audit are
disposable; no real credential file is read or named.
"""

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, task_executor
from core.action_gateway import ACT, HIGH_IMPACT, READ, ActionGateway
from tools import shell_tools
from utils.config import AGENT_CONFIG

ORIG_SHADOW = shell_tools._command_shadows_system_binary
classify = shell_tools.classify_shell_command


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    state = tmp_path / "state"
    ws = tmp_path / "ws"
    for d in (home, state, ws):
        d.mkdir()
    (home / ".ssh").mkdir()
    (home / ".ssh" / "id_rsa").write_text("FAKE-KEY")
    (home / ".ssh" / "id_ed25519").write_text("FAKE-KEY")
    (home / ".netrc").write_text("FAKE")
    (home / ".git-credentials").write_text("FAKE")
    (home / ".npmrc").write_text("FAKE")
    (home / ".bash_history").write_text("FAKE")
    (home / ".config" / "gh").mkdir(parents=True)
    (home / ".config" / "gh" / "hosts.yml").write_text("FAKE")
    for name in ("age.key", "config.json", "cloudflare_tunnel_token.age", "restoricon.db",
                 "restoricon.db-wal", "gcp_credentials.json"):
        (state / name).write_text("FAKE")
    (ws / "README.md").write_text("hello\n")
    (ws / "src").mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEY_STATE_DIR", str(state))
    monkeypatch.setattr(shell_tools._config, "CODEY_STATE_DIR", state)
    monkeypatch.setattr(shell_tools._config, "WORKSPACE_ROOT", ws)
    monkeypatch.chdir(ws)
    # Classification-only tests must not depend on the host PATH layout.
    monkeypatch.setattr(shell_tools, "_command_shadows_system_binary", lambda command: False)
    audit = tmp_path / "audit.jsonl"
    instance = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: instance)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    monkeypatch.delitem(AGENT_CONFIG, "_shell_fn", raising=False)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    prompt = Mock(return_value=True)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    return SimpleNamespace(home=home, state=state, ws=ws, audit=audit, runner=runner, prompt=prompt)


def last_row(env):
    return json.loads(env.audit.read_text().splitlines()[-1])


def assert_refused(env, result):
    assert result.startswith("[BLOCKED]")
    env.runner.assert_not_called()
    row = last_row(env)
    assert row["authority"] == HIGH_IMPACT and row["outcome"] == "refused"


# ---------------------------------------------------------------------------
# _walk_options (shared walker, R1-R5, R7)
# ---------------------------------------------------------------------------

T = shell_tools._OptionTable(
    short_bare=frozenset("ab"), short_operand=frozenset("o"),
    long_bare=frozenset({"quiet", "must"}), long_operand=frozenset({"out"}),
    long_optional=frozenset({"check"}), max_positionals=2,
    required=frozenset({"--must"}),
)
T_NOREQ = shell_tools._OptionTable(
    short_bare=frozenset("ab"), short_operand=frozenset("o"),
    long_bare=frozenset({"quiet", "must"}), long_operand=frozenset({"out"}),
    long_optional=frozenset({"check"}), max_positionals=2,
)


def walk(parts, table=T_NOREQ):
    return shell_tools._walk_options(parts, table)


def test_walker_accepts_and_returns_positionals_and_operands():
    assert walk(["t", "-ab", "f", "--out=x"]) == (["f"], ["x"])
    assert walk(["t", "--out", "y", "f"]) == (["f"], ["y"])
    assert walk(["t", "-ofile", "f"]) == (["f"], ["file"])
    assert walk(["t", "-o", "z", "f"]) == (["f"], ["z"])
    assert walk(["t", "--check", "f"]) == (["f"], [])
    assert walk(["t", "--check=quiet"]) == ([], ["quiet"])
    assert walk(["t", "-", "f"]) == (["-", "f"], [])


@pytest.mark.parametrize("parts", [
    ["t", "-c"],                 # unknown short
    ["t", "-ac"],                # unknown letter hidden in a cluster
    ["t", "-ao"],                # operand letter at end with nothing following
    ["t", "-o", "-a"],           # separate operand starting with a dash
    ["t", "--out"],              # missing operand
    ["t", "--out", "--quiet"],
    ["t", "--ou=x"],             # abbreviation never accepted
    ["t", "--qui"],
    ["t", "--quiet=1"],          # bare long must not carry a value
    ["t", "--unknown"],
    ["t", "f", "-c"],            # permuted: option AFTER a positional is still scanned
    ["t", "a", "b", "c"],        # max_positionals
    ["t", "a", "--", "b", "c"],  # positionals after -- still count
])
def test_walker_fails_closed(parts):
    assert walk(parts) is None


def test_walker_double_dash_ends_options_and_required_must_precede_it():
    assert walk(["t", "--", "-c"]) == (["-c"], [])
    assert shell_tools._walk_options(["t", "--must", "f"], T) == (["f"], [])
    assert shell_tools._walk_options(["t", "f"], T) is None
    assert shell_tools._walk_options(["t", "--", "--must"], T) is None
    assert shell_tools._walk_options(["t", "--must=1"], T) is None


# ---------------------------------------------------------------------------
# Table pins (derived from the tools' own --help on 2026-10-23)
# ---------------------------------------------------------------------------

def test_tables_are_exact():
    t = shell_tools
    assert t._SED_TABLE.short_bare == frozenset("nErszu")
    assert t._SED_TABLE.short_operand == frozenset("el")
    assert t._SED_TABLE.long_bare == frozenset(
        "quiet silent debug posix regexp-extended separate sandbox unbuffered null-data help version".split())
    assert t._SED_TABLE.long_operand == frozenset({"expression", "line-length"})
    assert t._SED_TABLE.required == frozenset({"--sandbox"})
    assert t._SORT_TABLE.short_bare == frozenset("bdfgiMhnRrVcCmsuz")
    assert t._SORT_TABLE.short_operand == frozenset("ktS")
    assert t._SORT_TABLE.long_operand == frozenset({"key", "field-separator", "sort", "buffer-size"})
    assert t._SORT_TABLE.long_optional == frozenset({"check"})
    assert t._UNIQ_TABLE.short_bare == frozenset("cdDiuz")
    assert t._UNIQ_TABLE.short_operand == frozenset("fsw")
    assert t._UNIQ_TABLE.long_optional == frozenset({"all-repeated", "group"})
    assert t._UNIQ_TABLE.max_positionals == 1
    assert t._TREE_TABLE.short_bare == frozenset("adlfxqNQpugshDFvtcUriASnC")
    assert t._TREE_TABLE.short_operand == frozenset("LPI")
    assert t._TREE_TABLE.long_operand == frozenset({"sort", "filelimit"})
    assert t._FILE_TABLE.short_bare == frozenset("bikLhnN0prszvZ")
    assert t._FILE_TABLE.short_operand == frozenset()
    assert set(t._TEXT_TOOL_TABLES) == {"sed", "sort", "uniq", "tree", "file"}


def test_dangerous_option_names_absent_from_tables():
    t = shell_tools
    assert "i" not in t._SED_TABLE.short_bare | t._SED_TABLE.short_operand
    assert "f" not in t._SED_TABLE.short_bare | t._SED_TABLE.short_operand
    assert not {"in-place", "file", "follow-symlinks"} & (t._SED_TABLE.long_bare | t._SED_TABLE.long_operand)
    every_sort = t._SORT_TABLE.long_bare | t._SORT_TABLE.long_operand | t._SORT_TABLE.long_optional
    assert not {"output", "compress-program", "temporary-directory", "files0-from",
                "random-source", "batch-size", "parallel"} & every_sort
    assert not set("oT") & (t._SORT_TABLE.short_bare | t._SORT_TABLE.short_operand)
    assert not set("oRHTXJ") & (t._TREE_TABLE.short_bare | t._TREE_TABLE.short_operand)
    assert not set("CmfcePSdl") & (t._FILE_TABLE.short_bare | t._FILE_TABLE.short_operand)
    assert not {"compile", "magic-file", "files-from", "parameter"} & t._FILE_TABLE.long_bare


# ---------------------------------------------------------------------------
# Classification: text tools, awk, sed --sandbox
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command", [
    "sed --sandbox -n 1,5p f", "sed --sandbox -E s/a/b/ f", "sed -n --sandbox p f",
    "sed --sandbox -e s/a/b/ -e s/c/d/ f", "sed --sandbox --expression=s/a/b/ f",
    "sed --sandbox -z p f", "sed --sandbox -- s/a/b/ f",
])
def test_sed_with_sandbox_is_act(command):
    assert classify(command) == ACT


@pytest.mark.parametrize("command", [
    "sed -n p f", "sed -i s/a/b/ f", "sed --sandbox -i s/a/b/ f", "sed --sandbox -ni p f",
    "sed --sandbox -n -i.bak p f", "sed --sandbox --in-place s/a/b/ f",
    "sed --sandbox --in-pl s/a/b/ f", "sed --sandbox --in s/a/b/ f", "sed --sandb -n p f",
    "sed --sandbox -f s.sed f", "sed --sandbox --file=s.sed f", "sed -- --sandbox p f",
    "sed --sandbox=1 p f", "sed --sandbox -e", "sed --sandbox -e -n f",
    "sed 1e\\ id f", "sed --version",
    # G15b-08 G01: sed script-embedded write to .git, closed as HIGH by the table.
    "sed -n 'w .git/config' f",
])
def test_sed_refusals(command):
    assert classify(command) == HIGH_IMPACT


# C1: GNU sed compiles each -e/--expression script while parsing options, so
# --sandbox protects only scripts parsed AFTER it (verified on sed 4.10, see
# test_sed_sandbox_order_matches_real_sed). Every form with -e/--expression
# (including clusters containing e) before --sandbox must be HIGH.
@pytest.mark.parametrize("command", [
    "sed -n -e 'w out' --sandbox f", "sed -e 'e id' --sandbox f",
    "sed -ne 'w out' --sandbox f", "sed --expression='w x' --sandbox f",
    "sed -e p --sandbox -e p f", "sed -nse p --sandbox f",
    "sed --expression p --sandbox f",
])
def test_sed_expression_before_sandbox_is_high(command):
    assert classify(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", [
    "sed --sandbox -e p f", "sed --sandbox -ne p f", "sed -n --sandbox -e p -e p f",
    "sed --sandbox --expression=p f", "sed -n --sandbox --expression p f",
    "sed -n --sandbox -nse p f",
])
def test_sed_sandbox_before_expression_is_act(command):
    assert classify(command) == ACT


def test_sed_sandbox_order_matches_real_sed(tmp_path):
    if shutil.which("sed") is None:
        pytest.skip("sed not installed")
    (tmp_path / "f").write_text("a\n")
    # Benign probes of the real tool: scripts that would create a file.
    for argv, writes in [
        (["-n", "-e", "w out1", "--sandbox", "f"], True),
        (["--sandbox", "-e", "w out2", "f"], False),
        (["--sandbox", "-ne", "w out3", "f"], False),
    ]:
        subprocess.run(["sed"] + argv, cwd=tmp_path, capture_output=True, text=True, timeout=20)
        name = [a for a in argv if a.startswith("w ")][0][2:]
        assert (tmp_path / name).exists() is writes
        assert (classify("sed " + " ".join(shlex.quote(a) for a in argv)) == HIGH_IMPACT) is writes


@pytest.mark.parametrize("command", [
    "sort f", "sort -u -n -r f", "sort -t, -k2,2n f", "sort --key=2 --field-separator=, f",
    "sort -nr f", "sort --check=quiet f",
    "uniq", "uniq f", "uniq -c f", "uniq -f 1 f", "uniq -f1 f", "uniq --skip-fields=1 f",
    "uniq --group f", "uniq --all-repeated=separate f",
    "tree", "tree -L 2", "tree -aI node_modules", "tree -L2", "tree --noreport -d",
    "tree -P '*.py' -I __pycache__",
    "file f", "file -b f", "file --mime-type f", "file -bi f", "file -L f",
])
def test_text_tool_accept_rows_are_read(command):
    assert classify(command) == READ


@pytest.mark.parametrize("command", [
    "sort -o f1 f2", "sort -of1 f2", "sort -ro f1 f", "sort --output=x f", "sort --out=x f",
    "sort --o=x f", "sort --compress-program=sh f", "sort --compress=sh f", "sort -T /tmp f",
    "sort --files0-from=list", "sort --random-source=/dev/urandom -R f", "sort f -o out",
    "sort -k", "sort -t -",
    # G15b-08 G02: sort -o.git/config closed as HIGH.
    "sort -o.git/config f",
    "uniq in out", "uniq -c in out", "uniq --count in out", "uniq in -- out", "uniq -D=1",
    "tree -o out", "tree -ro out", "tree -R", "tree -H http://x", "tree -T t", "tree -X",
    "tree --fromfile .", "tree --gitfile x", "tree --infofile x", "tree --hintro=f",
    "tree --output=x", "tree -o", "tree -L -o",
    "file -C -m magic", "file -C", "file --compile", "file -m x f", "file --magic-file=x f",
    "file -f list", "file --files-from=list", "file -P name=1 f", "file -S f", "file -e text f",
    "file -F: f",
    # awk: every form, including the G15b-08 G05 redirect.
    "awk '{print}' f", "awk --version", "awk -f x f", "awk 'BEGIN{system(\"id\")}'",
    "awk '{print > \".git/x\"}' f",
])
def test_text_tool_refuse_rows_are_high(command):
    assert classify(command) == HIGH_IMPACT


@pytest.mark.parametrize("command,expected", [
    ("ls -la", READ), ("grep -rn x src", READ), ("diff -u a b", READ), ("wc -l f", READ),
    ("head -n 5 f", READ), ("tail -n 5 f", READ), ("date +%F", READ), ("stat f", READ),
    ("du -sh .", READ), ("df -h", READ), ("cut -d, -f1 f", ACT), ("tr a b", ACT),
])
def test_unrelated_tools_keep_their_class(command, expected):
    assert classify(command) == expected


# ---------------------------------------------------------------------------
# D-3
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command", [
    "./ls", "../ls", "bin/ls", "~/ls", "/tmp/x/ls", "/home/u/.local/bin/ruff",
    "./venv/bin/pytest", "/usr/bin/../../tmp/ls", "//usr/bin/ls", "/usr/bin/",
    "./gcc", "/tmp/x/gcc", "usr/bin/gcc", "/usr/bin/../../tmp/gcc",
    "./ls push origin main",
])
def test_d3_slash_argv0_outside_system_dirs_is_high(command):
    assert classify(command) == HIGH_IMPACT


@pytest.mark.parametrize("command,expected", [
    ("/bin/ls", READ), ("/system/bin/ls", READ),
    ("/data/data/com.termux/files/usr/bin/ls", READ),
    ("/usr/bin/python3 x.py", ACT), ("/usr/bin/gcc x.c", ACT), ("ls", READ),
    ("/usr/local/bin/ruff .", ACT), ("/sbin/ls", READ), ("/usr/bin/git status", HIGH_IMPACT),
])
def test_d3_system_dir_and_bare_names_keep_their_class(command, expected):
    assert classify(command) == expected


@pytest.mark.parametrize("command,expected", [
    # Lexical normalization is the specced (Q1) behavior: the parent is
    # compared after normpath, never via symlink-following realpath.
    ("/tmp/../usr/bin/ls", READ), ("/usr/bin/./ls", READ), ("/usr/bin//ls", READ),
])
def test_d3_lexical_normalization_of_parent(command, expected):
    assert classify(command) == expected


def test_system_bin_dirs_constant_exact_and_old_name_gone():
    assert shell_tools._SYSTEM_BIN_DIRS == frozenset({
        "/bin", "/sbin", "/usr/bin", "/usr/sbin", "/usr/local/bin", "/system/bin",
        "/system/xbin", "/data/data/com.termux/files/usr/bin",
    })
    assert not hasattr(shell_tools, "_BUILD_TOOL_SYSTEM_DIRS")


def test_d3_two_step_symlink_attack_is_refused_at_second_step(env):
    # Step one (documented, G15e's write-target problem) is ACT; the dispatch
    # through the planted name now carries a `/` and is refused.
    assert classify("ln -s /usr/bin/git ls") == ACT
    result = shell_tools.shell("./ls push origin main")
    assert_refused(env, result)


def test_d3_bare_name_residual_is_pinned_read_at_the_classifier():
    # Q2's shell()-level check closes this; the classifier stays lexical.
    assert classify("ls push origin main") == READ


# ---------------------------------------------------------------------------
# D-2 classifier half: env / printenv
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command", [
    "env", "env -i", "/usr/bin/env", "printenv", "printenv OPENROUTER_API_KEY",
    "printenv HOME SECRET", "printenv --null HOME", "printenv -0", "printenv --help",
    "printenv -- HOME", "printenv home",
])
def test_env_and_printenv_outside_allowlist_are_high(command):
    assert classify(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", ["printenv HOME", "printenv PATH TERM", "printenv SHLVL"])
def test_printenv_allowlisted_names_are_read(command):
    assert classify(command) == READ


def test_printenv_allowlist_is_exact():
    assert shell_tools._PRINTENV_SAFE_NAMES == frozenset(
        "HOME USER LOGNAME SHELL PWD OLDPWD LANG LC_ALL LC_CTYPE TERM TZ TMPDIR PREFIX PATH HOSTNAME SHLVL".split())
    assert len(shell_tools._PRINTENV_SAFE_NAMES) == 16


@pytest.mark.parametrize("command", ["env", "printenv", "printenv OPENROUTER_API_KEY"])
def test_daemon_env_and_secret_printenv_refused_inside_shell(env, command):
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell(command).startswith("[BLOCKED]")
    env.runner.assert_not_called()
    row = last_row(env)
    assert row["action"] == "shell_tools.shell"
    assert row["outcome"] == "refused" and row["authority"] == HIGH_IMPACT


def test_daemon_printenv_home_runs_once(env):
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell("printenv HOME") == "ok"
    env.runner.assert_called_once()
    assert env.runner.call_args.args[0] == ["printenv", "HOME"]


# ---------------------------------------------------------------------------
# D-2 filesystem half: credential-path scan in shell()
# ---------------------------------------------------------------------------

def credential_commands(env):
    h, s = env.home, env.state
    return [
        f"cat {h}/.ssh/id_ed25519", "cat ~/.ssh/id_rsa", "cat $HOME/.ssh/id_rsa",
        "cat ${HOME}/.netrc", f"head -n1 {h}/.git-credentials", f"cat {s}/age.key",
        f"cat {s}/cloudflare_tunnel_token.age", f"cat {s}/config.json",
        f"cat {s}/restoricon.db", f"cat {s}/restoricon.db-wal", f"cat {s}/gcp_credentials.json",
        f"grep token {h}/.config/gh/hosts.yml", "cat /proc/self/environ", "cat /proc/1/cmdline",
        f"cat /proc/{os.getpid()}/cmdline", "cat /proc/thread-self/environ", "cat /proc/self/fd/0",
        f"sed --sandbox -n 1p {h}/.npmrc", f"wc --files0-from={h}/.ssh/x",
        f"grep -f {h}/.ssh/id_rsa file", f"cp {h}/.ssh/id_rsa out",
        f"cat -- {h}/.ssh/id_rsa", f"cat -n{h}/.ssh/id_rsa", f"cat {h}/x/../.ssh/id_rsa",
        f"tail -c 10 {h}/.bash_history", f"sort {h}/.ssh/id_rsa",
        f"cat /proc/self/root{h}/.ssh/id_rsa", f"cat /proc/self/cwd/../home/.ssh/id_rsa",
        "cat ../home/.ssh/id_rsa", "cat .env", "cat sub/id_rsa", "cat key.pem",
        "cat link_to_cred",
        # Device alias: /data/user/0 and /data/data are the same tree but
        # realpath() does not fold one into the other.
        # (.netrc: its name matches no basename pattern, so only the alias fold
        # can catch it).
        "cat " + str(h).replace("/data/data/", "/data/user/0/", 1) + "/.netrc"
        if str(h).startswith("/data/data/") else f"cat {h}/.netrc",
        # Ancestor rule for recursive content readers.
        f"grep -r token {h}", "grep -rn x /", "grep -r x /proc", f"grep -R x {s}",
        f"diff -r {h} .", f"cp -r {h} out", "grep -r x /proc/self",
    ]


def plant_workspace_files(env):
    (env.ws / ".env").write_text("FAKE=1")
    (env.ws / "sub").mkdir()
    (env.ws / "sub" / "id_rsa").write_text("FAKE")
    (env.ws / "key.pem").write_text("FAKE")
    # .netrc: matches no basename pattern, so only the resolved form can catch it.
    os.symlink(env.home / ".netrc", env.ws / "link_to_cred")


def test_credential_paths_refused_through_shell(env):
    plant_workspace_files(env)
    for command in credential_commands(env):
        env.runner.reset_mock()
        result = shell_tools.shell(command)
        assert_refused(env, result)
        assert last_row(env)["command"] == command


def test_credential_paths_refused_through_daemon(env):
    plant_workspace_files(env)
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    for command in credential_commands(env):
        if not any(task_executor._daemon_prefix_matches(command, p)
                   for p in task_executor._DAEMON_ALLOWED_PREFIXES):
            continue  # only admitted daemon prefixes are interesting here
        env.runner.reset_mock()
        assert executor._daemon_shell(command).startswith("[BLOCKED]")
        env.runner.assert_not_called()
        row = last_row(env)
        assert row["action"] == "shell_tools.shell" and row["outcome"] == "refused"
        assert row["authority"] == HIGH_IMPACT


def test_ancestor_rule_for_grep_cwd_and_dot(env, monkeypatch):
    monkeypatch.chdir(env.home)
    assert_refused(env, shell_tools.shell("grep -r x"))
    env.runner.reset_mock()
    monkeypatch.chdir(env.home / ".ssh")
    assert_refused(env, shell_tools.shell("grep -r x ."))


@pytest.mark.parametrize("command", [
    "grep -rn foo src", "grep -r todo .", "cat README.md", "cat /proc/cpuinfo",
    "cat /proc/meminfo", "ls /proc", "echo safe",
    # Basename-pattern guard: patterns/strings with NO such file present.
    "grep -rn .env src", "grep -r id_rsa .", "grep -n '\\.key' f", "echo .env", "cat .env",
])
def test_non_credential_operands_are_not_escalated(env, command):
    result = shell_tools.shell(command)
    assert not result.startswith("[BLOCKED]"), command
    env.runner.assert_called_once()
    assert env.runner.call_args.args[0] == shlex.split(command)


def test_ls_and_du_of_home_and_state_dirs_stay_allowed(env):
    for command in (f"ls {env.home}", f"du -sh {env.state}"):
        env.runner.reset_mock()
        assert not shell_tools.shell(command).startswith("[BLOCKED]")
        env.runner.assert_called_once()


def test_repo_root_config_json_is_not_credential(env):
    (env.ws / "config.json").write_text("{}")
    env.runner.reset_mock()
    assert not shell_tools.shell("cat config.json").startswith("[BLOCKED]")
    env.runner.assert_called_once()


def test_pub_keys_and_nonexistent_basename_matches_are_allowed(env):
    (env.ws / "id_rsa.pub").write_text("pub")
    assert not shell_tools.shell("cat id_rsa.pub").startswith("[BLOCKED]")
    env.runner.assert_called_once()


def test_no_read_command_exemption_for_credentials(env):
    for tool in ("cat", "head", "grep x", "sort", "wc", "stat", "tail"):
        env.runner.reset_mock()
        assert_refused(env, shell_tools.shell(f"{tool} {env.home}/.ssh/id_rsa"))


def test_nul_byte_resolve_failure_and_home_failure_fail_closed(env, monkeypatch):
    direct = shell_tools._shell_command_targets_credentials
    assert direct("cat a\x00b", cwd=env.ws, home=env.home, state_dir=env.state) is True
    with monkeypatch.context() as m:
        m.setattr(Path, "resolve", Mock(side_effect=OSError("boom")))
        assert direct("cat README.md", cwd=env.ws, home=env.home, state_dir=env.state) is True
    # Through shell(): any exception in the scan is a refusal, not a crash.
    with monkeypatch.context() as m:
        m.setattr(Path, "home", Mock(side_effect=RuntimeError("no home")))
        assert_refused(env, shell_tools.shell("cat README.md"))


def test_nul_in_argv0_alone_fails_closed(env):
    direct = shell_tools._shell_command_targets_credentials
    assert direct("c\x00at README.md", cwd=env.ws, home=env.home, state_dir=env.state) is True


def test_scan_wrapper_fails_closed_on_any_exception(env, monkeypatch):
    monkeypatch.setattr(
        shell_tools, "_shell_command_targets_credentials", Mock(side_effect=ValueError("x"))
    )
    assert shell_tools._scan_credentials_safely("cat README.md") is True


def test_direct_scan_pure_function_cases(env):
    direct = lambda c, cwd=None: shell_tools._shell_command_targets_credentials(  # noqa: E731
        c, cwd=cwd or env.ws, home=env.home, state_dir=env.state)
    assert direct(f"cat {env.home}/.ssh/id_rsa") is True
    assert direct("cat README.md") is False
    assert direct("") is False


def test_interactive_path_preserved_for_credential_escalation(env, monkeypatch):
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", True)
    command = f"cat {env.home}/.ssh/id_rsa"
    env.prompt.return_value = False
    assert shell_tools.shell(command).startswith("[CANCELLED]")
    env.runner.assert_not_called()
    env.prompt.return_value = True
    assert shell_tools.shell(command) == "ok"
    env.runner.assert_called_once()
    assert env.runner.call_args.args[0] == shlex.split(command)


def test_state_entries_cover_default_codeyos_dir_when_state_dir_is_overridden(env, monkeypatch, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.setattr(shell_tools._config, "CODEY_STATE_DIR", other)
    (env.home / ".codeyOS").mkdir()
    assert_refused(env, shell_tools.shell(f"cat {env.home}/.codeyOS/age.key"))


# ---------------------------------------------------------------------------
# Q2 PATH-shadow check
# ---------------------------------------------------------------------------

def make_exe(path, text="#!/bin/sh\n"):
    path.write_text(text)
    path.chmod(0o755)


def test_path_shadow_planted_ls_is_refused_and_system_ls_allowed(env, tmp_path, monkeypatch):
    monkeypatch.setattr(shell_tools, "_command_shadows_system_binary", ORIG_SHADOW)
    fake_sys = tmp_path / "fakesys"
    user_bin = tmp_path / "userbin"
    fake_sys.mkdir()
    user_bin.mkdir()
    make_exe(fake_sys / "ls")
    make_exe(user_bin / "ls")
    monkeypatch.setattr(shell_tools, "_SYSTEM_BIN_DIRS", frozenset({str(fake_sys)}))
    # Shadowed: the user-writable dir comes first on PATH.
    monkeypatch.setenv("PATH", f"{user_bin}{os.pathsep}{fake_sys}")
    assert_refused(env, shell_tools.shell("ls push origin main"))
    # Not shadowed: only the system dir.
    env.runner.reset_mock()
    monkeypatch.setenv("PATH", str(fake_sys))
    assert shell_tools.shell("ls push origin main") == "ok"
    env.runner.assert_called_once()
    assert env.runner.call_args.args[0] == ["ls", "push", "origin", "main"]


def test_path_shadow_unresolvable_name_left_alone_and_slash_names_skipped(env, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty_dir_does_not_exist"))
    assert ORIG_SHADOW("definitely-not-a-real-command-xyz") is False
    assert ORIG_SHADOW("./ls") is False  # D-3 owns names containing a slash
    assert ORIG_SHADOW("ls 'unterminated") is True  # fail closed on tokenization failure


def test_path_shadow_lookup_error_fails_closed(monkeypatch):
    monkeypatch.setattr(shell_tools.shutil, "which", Mock(side_effect=OSError("boom")))
    assert ORIG_SHADOW("ls") is True


def test_path_shadow_runs_after_classification_and_only_for_non_high(env, monkeypatch):
    called = Mock(return_value=False)
    monkeypatch.setattr(shell_tools, "_command_shadows_system_binary", called)
    shell_tools.shell("git status")  # already HIGH: the check is skipped
    called.assert_not_called()
    env.runner.reset_mock()
    shell_tools.shell("echo hi")
    called.assert_called_once_with("echo hi")


# ---------------------------------------------------------------------------
# Benign real-parser smoke: every ACCEPT row must be recognized by the real tool
# (catches a table entry the tool rejects). Admitted forms only, scratch files,
# no shell() involved.
# ---------------------------------------------------------------------------

SMOKE_ROWS = [
    "sed --sandbox -n p f", "sed --sandbox -E s/a/b/ f", "sed --sandbox -n -e p f",
    "sed --sandbox --expression=p f", "sed --sandbox -s -n p f",
    "sort -u f", "sort -t, -k1,1 f", "sort --key=1 f", "sort -nr f", "sort --check=quiet f",
    "sort -b -d -f f", "sort --sort=numeric f", "sort -S 1M f",
    "uniq -c f", "uniq -f1 f", "uniq --skip-fields=1 f", "uniq -s 1 f", "uniq -w 3 f",
    "uniq --group f", "uniq --all-repeated=separate f", "uniq -i f",
    "tree -L 1", "tree -aI x", "tree -L2", "tree --noreport -d", "tree -P '*.py' -I y",
    "tree --filelimit 5", "tree --sort name", "tree -sh",
    "file -b f", "file --mime-type f", "file -bi f", "file -L f", "file -k f", "file -z f",
]


@pytest.mark.parametrize("row", SMOKE_ROWS)
def test_real_parser_accepts_every_admitted_row(row, tmp_path):
    parts = shlex.split(row)
    if shutil.which(parts[0]) is None:
        pytest.skip(f"{parts[0]} not installed")
    assert classify(row) in {READ, ACT}, row
    (tmp_path / "f").write_text("a 1\nb 2\n")
    result = subprocess.run(parts, cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, (row, result.stderr)
