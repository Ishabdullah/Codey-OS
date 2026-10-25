"""S2 unit A, fix 1 (G15z NV33 / EV03): the shell credential READ scan casefolds.

`cat $HOME/.SSH/id_rsa` used to classify READ and pass the credential scan while
the protected-WRITE scan blocked `cp x $HOME/.BASHRC`. Recording fakes only
(subprocess.run mocked); HOME, state dir and audit are disposable; every secret
is a fabricated placeholder.
"""

import json
import shlex
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway
from core.action_gateway import HIGH_IMPACT, ActionGateway
from core import protected_paths as pp
from tools import shell_tools
from utils.config import AGENT_CONFIG


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    state = tmp_path / "state"
    ws = tmp_path / "ws"
    for d in (home, state, ws):
        d.mkdir()
    (home / ".ssh").mkdir()
    (home / ".ssh" / "id_rsa").write_text("FAKE-KEY")
    (state / "age.key").write_text("FAKE")
    (state / "restoricon.db-wal").write_text("FAKE")
    (ws / "README.md").write_text("hello\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEY_STATE_DIR", str(state))
    monkeypatch.setattr(shell_tools._config, "CODEY_STATE_DIR", state)
    monkeypatch.setattr(shell_tools._config, "WORKSPACE_ROOT", ws)
    monkeypatch.chdir(ws)
    monkeypatch.setattr(shell_tools, "_command_shadows_system_binary", lambda command: False)
    audit = tmp_path / "audit.jsonl"
    instance = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: instance)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    monkeypatch.delitem(AGENT_CONFIG, "_shell_fn", raising=False)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    monkeypatch.setattr(shell_tools, "ask_confirm", Mock(return_value=True))
    return SimpleNamespace(home=home, state=state, ws=ws, audit=audit, runner=runner)


def _fill(template, env):
    return template.replace("{home}", str(env.home)).replace("{state}", str(env.state))


def _refused(env, command):
    env.runner.reset_mock()
    result = shell_tools.shell(command)
    assert result.startswith("[BLOCKED]"), command
    env.runner.assert_not_called()
    row = json.loads(env.audit.read_text().splitlines()[-1])
    assert row["authority"] == HIGH_IMPACT and row["outcome"] == "refused"


def _allowed(env, command):
    env.runner.reset_mock()
    assert not shell_tools.shell(command).startswith("[BLOCKED]"), command
    env.runner.assert_called_once()
    assert env.runner.call_args.args[0] == shlex.split(command)


@pytest.mark.parametrize("template", [
    "cat $HOME/.SSH/id_rsa", "cat $HOME/.Ssh/id_rsa", "cat ${HOME}/.ssh/ID_RSA",
    "cat ~/.SSH/ID_RSA", "head ~/.NETRC", "cat ~/.Git-Credentials", "cat ~/.BASH_HISTORY",
    "cat ~/.Config/GH/hosts.yml", "cat {home}/.AWS/credentials",
    "cat {state}/AGE.KEY", "cat {state}/Restoricon.DB-wal", "cat {state}/X.AGE",
    "cat {state}/Config.JSON", "sort {home}/.Ssh/known_hosts",
    "cat -n ~/.SSH/id_rsa", "grep x --file=~/.SSH/id_rsa",
])
def test_casefolded_credential_operands_are_refused(env, template):
    _refused(env, _fill(template, env))


def test_alias_plus_case_is_refused(env):
    s = str(env.home)
    if not s.startswith("/data/data/"):
        pytest.skip("alias only exists under /data/data")
    _refused(env, "cat /data/user/0/" + s[len("/data/data/"):] + "/.SSH/id_rsa")


def test_ancestor_rule_casefolds(env, monkeypatch):
    # grep -r on an upper-case spelling of an ancestor of a credential entry.
    _refused(env, f"cp {env.home}/.SSH /tmp/x")
    monkeypatch.chdir(env.home / ".ssh")
    _refused(env, "grep -r x .")


def test_symlink_resolved_form_casefolds(env):
    # Resolved form of a workspace link into the credential file is caught.
    (env.ws / "lnk").symlink_to(env.home / ".ssh" / "id_rsa")
    _refused(env, "cat lnk")


@pytest.mark.parametrize("name", [".ENV", ".Env.local", "KEY.PEM", "ID_RSA", "Id_Ed25519", "server.KEY"])
def test_existing_basename_secret_names_casefold(env, name):
    (env.ws / name).write_text("FAKE")
    _refused(env, f"cat {name}")


@pytest.mark.parametrize("name", [".ENV", "ID_RSA", "KEY.PEM"])
def test_nonexistent_basename_names_still_allowed(env, name):
    # Existence guard unchanged: a search pattern that names no file is fine.
    _allowed(env, f"grep -rn {name} src")


@pytest.mark.parametrize("command", [
    "cat ssh_notes.txt", "cat ~/.sshfoo", "cat ~/.ssh2/x", "cat ~/.SSH2/x",
    "cat ~/.netrc.example", "cat ~/.NETRC.example", "cat {state}/notes.json",
    "cat {state}/age.key.bak", "cat {state}/Restoricon.txt", "cat {state}/x.agent",
    "cat {home}/SSH/id_rsa", "cat README.md", "grep -rn Ssh src", "cat ID_RSA.PUB",
])
def test_similarly_named_non_credentials_stay_allowed(env, command):
    (env.ws / "id_rsa.pub").write_text("pub")
    _allowed(env, _fill(command, env))


def test_lowercase_behaviour_unchanged(env):
    _refused(env, f"cat {env.home}/.ssh/id_rsa")
    _refused(env, f"cat {env.state}/age.key")
    _allowed(env, "cat README.md")


def test_filesystem_read_side_already_casefolds(env, monkeypatch):
    # Filesystem.read uses core.protected_paths.credential_read_hit, which folds
    # both sides; pinned here so a future refactor cannot regress it.
    for forms, want in [
        ([str(env.home / ".SSH" / "ID_RSA")], "credential-file"),
        ([str(env.home / ".NETRC")], "credential-file"),
        ([str(env.state / "AGE.KEY")], "credential-file"),
        ([str(env.state / "Restoricon.DB-wal")], "credential-file"),
        ([str(env.home / "ssh_notes.txt")], None),
        ([str(env.home / ".sshfoo")], None),
        ([str(env.state / "notes.json")], None),
    ]:
        assert pp.credential_read_hit(forms, home=env.home, state_dirs=[env.state]) == want, forms
