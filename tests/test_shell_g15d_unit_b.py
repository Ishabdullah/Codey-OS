"""G15d Unit B: node --inspect host rule, python -m module allowlist, pip
per-subcommand option tables, npm exact-subcommand/option allowlist,
pnpm/yarn operand-shape rule.

Pure classification plus recording fakes only: nothing here runs npm, pip or
node for real (the only real binary invocations are the benign `--help` /
cmd-list cross-checks that never reach shell()). No network, no model.
"""

import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, task_executor
from core.action_gateway import ACT, HIGH_IMPACT, ActionGateway
from tools import shell_tools
from utils.config import AGENT_CONFIG

classify = shell_tools.classify_shell_command


# ---------------------------------------------------------------- 4.4 node
@pytest.mark.parametrize("command", [
    "node --inspect x.js", "node --inspect=9229 x.js",
    "node --inspect-brk=127.0.0.1:9229 x.js", "node --inspect-wait=[::1]:9229 x.js",
    "node --inspect-brk x.js", "node --inspect=127.0.0.1:1 x.js",
])
def test_node_inspect_loopback_forms_stay_act(command):
    assert classify(command) == ACT


@pytest.mark.parametrize("command", [
    "node --inspect=0.0.0.0:9229 x.js", "node --inspect=:9229 x.js",
    "node --inspect-brk=192.168.1.5:9229 x.js", "node --inspect=localhost:9229 x.js",
    "node --inspect=[::]:9229 x.js", "node --inspect-port=0.0.0.0:1 x.js",
    "node --inspect=9229:1 x.js", "node --inspect=123456 x.js",
    "node --inspect=127.0.0.1:9229x x.js", "node --inspect=0.0.0.0 x.js",
    "node --inspect= x.js", "node '--inspect=127.0.0.1:9229\n' x.js",
    "node --inspect-publish-uid=http x.js", "nodejs --inspect=0.0.0.0:9229 x.js",
])
def test_node_inspect_non_loopback_forms_are_high(command):
    assert classify(command) == HIGH_IMPACT


def test_node_inspect_prefixes_are_not_on_the_attached_prefix_list():
    # The three --inspect*= prefixes were removed on purpose; re-adding any
    # makes every host ACT again.
    assert not any(p.startswith("--inspect") for p in shell_tools._NODE_SAFE_ATTACHED_PREFIXES)
    assert shell_tools._NODE_INSPECT_ATTACHED_RE.pattern == (
        r"^--inspect(?:-brk|-wait)?=(?:\d{1,5}|127\.0\.0\.1:\d{1,5}|\[::1\]:\d{1,5})$"
    )


# -------------------------------------------------------- 4.5 python -m
@pytest.mark.parametrize("command", [
    "python3 -m pytest -q", "python3 -Im pytest", "python3 -mpytest",
    "python3 -m pip list", "python3 -m venv .v", "python3 -m unittest",
    "python3 -m ruff check .", "python3 -Bm pytest -c foo", "python3 -m json.tool f",
    "python3 -W ignore -m pytest", "python3 -Wignore -m pytest", "python -m compileall .",
    "python3 -m py_compile x.py", "python3.14 -m pytest", "python3 -m mypy .",
    "python3 -m black .", "python3 -m isort .", "python3 -m flake8", "python3 -m pylint x",
])
def test_python_m_allowlisted_modules_stay_act(command):
    assert classify(command) == ACT


@pytest.mark.parametrize("command", [
    "python3 -m http.server", "python3 -mhttp.server", "python3 -Im http.server 8000",
    "python3 -m code", "python3 -m pdb x.py", "python3 -m", "python3 -Im",
    "python3 -m pytest.__main__", "python3 -m restoricon_core.api.server --host 0.0.0.0",
    "python3 -m tools.provision_ai_agent_auth", "python3 -m bench.promote",
    "python3 -m runpy x", "python3 -m trace", "python3 -m timeit", "python3 -m cProfile",
    "python3 -m PYTEST", "python3 -m pytest2", "python3 -m -c x", "python3 -W ignore -m http.server",
    "python3 -X dev -m code", "python3 -m telemetry.cli", "python3 -m aigentik.server",
    "python3 -m pip.__main__ list", "python3 -m pip3 list", "python3 -mpip3 list",
])
def test_python_m_other_modules_are_high(command):
    assert classify(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", ["python3 -c x", "python3 -Wignore -c x", "python3 -Ic x"])
def test_python_inline_code_unchanged(command):
    assert classify(command) == HIGH_IMPACT


def test_python_m_pytest_own_dash_c_is_not_inline_code():
    # `-c` after the module belongs to pytest, not to the interpreter.
    assert classify("python3 -mpytest -c x") == ACT


def test_python_script_and_bare_unchanged():
    for c in ("python3 x.py", "python3", "python3 -", "python3 -- x.py", "python3 -u x.py",
              "python3 --version", "python3 -B -O x.py", "python3 --check-hash-based-pycs always x.py"):
        assert classify(c) == ACT, c


def test_python_m_allowlist_is_pinned_exactly():
    assert shell_tools._PYTHON_M_ALLOWED_MODULES == frozenset({
        "pytest", "pip", "venv", "unittest", "ruff", "black", "isort", "flake8", "mypy",
        "pylint", "py_compile", "compileall", "json.tool",
    })
    for dangerous in ("http.server", "code", "pdb", "runpy", "trace", "smtpd", "idlelib"):
        assert dangerous not in shell_tools._PYTHON_M_ALLOWED_MODULES


def test_python_dash_m_pip_args_any_spelling():
    f = shell_tools._python_dash_m_pip_args
    assert f(["python3", "-m", "pip", "list"]) == ["list"]
    assert f(["python3", "-Im", "pip", "list"]) == ["list"]
    assert f(["python3", "-mpip", "list"]) == ["list"]
    assert f(["python3", "-m", "pytest", "pip"]) is None
    assert f(["python3", "x.py", "-m", "pip"]) is None
    assert f(["python3", "-c", "pip"]) is None


# ------------------------------------------------------------------ 4.2 pip
PIP_HIGH = [
    "pip install -qf x foo", "pip install -fq x foo", "pip install -qi x foo",
    "pip install --find-l=/d foo", "pip install --ind=x foo", "pip install --index=x foo",
    "pip install --fin x foo", "pip install --extra-index-url=x foo",
    "pip install -t /tmp/x foo", "pip install --target=x foo", "pip install --root x foo",
    "pip install --prefix x foo", "pip install --src x foo",
    "pip install --report /tmp/r.json foo", "pip install --log /tmp/l foo",
    "pip --python /tmp/e install foo", "pip install --python=/tmp/e foo",
    "pip --proxy http://x install foo", "pip install --cert x foo",
    "pip install --client-cert x foo", "pip install --cache-dir x foo",
    "pip install --keyring-provider=subprocess foo", "pip install --use-feature=x foo",
    "pip install -C x foo", "pip install --config-settings x foo",
    "pip install --requirements-from-script f", "pip install --group g",
    "pip install foo --no-index -f x", "pip download -d /tmp foo", "pip download --dest=x foo",
    "pip config set a b", "pip cache purge", "pip wheel .", "pip index versions x",
    "pip inspect", "pip debug", "pip hash f", "pip search x", "pip help install",
    "pip install -r https://x/reqs.txt", "pip install -e git+https://x/y#egg=z",
    "pip install 'foo @ https://x/y.whl'", "pip install git+ssh://h/r.git",
    "pip install file:///x", "pip list -i http://x", "pip list --path /tmp",
    "pip list -f /x", "pip list --exclude foo", "pip freeze -r requirements.txt",
    "pip freeze --path /x", "pip freeze --exclude foo",
    "pip install --index-url https://x y", "pip install --index-url=https://x y",
    "pip install -i https://x y", "pip install -ihttps://x y", "pip install -f/dir y",
    "pip install --find-links /x y", "pip install --trusted-host x y",
    "pip install git+https://x/y.git", "pip install https://x/y.tgz",
    "pip install svn+https://x/y", "pip3 install --index-url x y",
    "python3 -m pip install --index-url x y", "python3 -m pip config set a b",
    "python3 -m pip install git+https://x/y", "python3 -mpip install -f x y",
    "python3 -Im pip install --target=x y",
    "pip install -- foo -f x", "pip -- install foo", "pip - install foo", "pip install -",
    "pip install -r", "pip install -r -f", "pip install -e -f", "pip install -r --upgrade foo",
    "pip list --format=bad", "pip list --format", "pip list foo",
    "pip -f install foo", "pip --require-virtualenv install foo", "pip --debug install foo",
    "pip install --no-dep foo", "pip install --upgrad foo", "pip install --user=1 foo",
    "pip install --no-index=1 foo", "pip install foo bar:baz", "pip install 'foo; python_version<\"3\"'",
    "pip install foo@1", "pip install git@github.com:u/r.git", "pip install user/repo/extra:x",
    "pip install /tmp/x:y", "pip install ~/x;y", "pip uninstall -y -f foo", "pip uninstall --root foo",
    "pip download --user foo", "pip download --upgrade foo", "pip download --dry-run foo",
    "pip show --path foo", "pip check foo -f x", "pip check --python x",
    "pip3.14 install --find-l=x foo", "pip3.11 install -qf x foo", "pip3.14 config list",
    "pip install --only-deps foo", "pip install foo==", "pip install =foo",
]

PIP_ACT = [
    "pip install requests", "pip install -U requests", "pip install -e .",
    "pip install -r requirements.txt", "pip install ./localpkg", "pip list", "pip freeze",
    "pip show foo", "pip3 install foo", "python3 -m pip install foo", "python3 -m pip list",
    "pip download requests", "pip install -U pip", "pip install -qU foo",
    "pip install --no-deps -r requirements/dev.txt", 'pip install "requests>=2,<3"',
    "pip install requests[security]==2.0", "pip3.14 install foo", "pip3.11 install foo",
    "pip3.11 list", "pip3.11 --version", "python3 -m pip install -e .",
    "pip uninstall -y foo", "pip list --outdated --format=json", "pip show -f foo",
    "pip --version", "pip", "pip -h", "pip install --user --break-system-packages foo",
    "pip -q install -e .[dev]", "pip check", "pip -qq list", "pip -vv list",
    "pip install --upgrade pip setuptools wheel", "python3 -mpip list", "python3 -m pip",
    "pip --disable-pip-version-check install foo", "pip install --no-cache-dir foo",
    "pip install --dry-run --no-index foo", "pip install -c constraints.txt -r requirements.txt",
    "pip install --requirement=requirements.txt", "pip install --editable ../x",
    "pip install foo==1.2.3 bar~=2.0 baz!=3", "pip install -I foo", "pip freeze --local --all",
    "pip list --not-required --exclude-editable", "pip uninstall -r requirements.txt -y",
    "pip download --no-deps -r requirements.txt", "pip install /abs/path/pkg",
    "pip install ~/proj", "pip install ../proj", "pip install ..",
]


@pytest.mark.parametrize("command", PIP_HIGH)
def test_pip_high_rows(command):
    assert classify(command) == HIGH_IMPACT, command


@pytest.mark.parametrize("command", PIP_ACT)
def test_pip_act_rows(command):
    assert classify(command) == ACT, command


def _opt_names(table):
    return (
        {f"-{c}" for c in table.short_bare | table.short_operand}
        | {f"--{n}" for n in table.long_bare | table.long_operand | table.long_optional}
    )


_PIP_TABLE_PINS = {
    "install": (
        "UIqvhV", "rce",
        "no-deps dry-run user upgrade force-reinstall ignore-installed ignore-requires-python "
        "no-build-isolation check-build-dependencies break-system-packages compile no-compile "
        "no-warn-script-location no-warn-conflicts require-hashes no-require-hashes no-clean pre "
        "prefer-binary no-index quiet verbose version help no-color no-input "
        "disable-pip-version-check isolated no-cache-dir",
        "requirement constraint editable",
    ),
    "download": (
        "qvhV", "rc",
        "no-deps ignore-requires-python no-build-isolation check-build-dependencies "
        "require-hashes no-require-hashes no-clean pre prefer-binary no-index quiet verbose "
        "version help no-color no-input disable-pip-version-check isolated no-cache-dir",
        "requirement constraint",
    ),
    "uninstall": (
        "yqvhV", "r",
        "yes break-system-packages quiet verbose version help no-color no-input "
        "disable-pip-version-check isolated no-cache-dir",
        "requirement",
    ),
    "list": (
        "ouelqvhV", "",
        "outdated uptodate editable local user not-required exclude-editable include-editable pre "
        "prefer-binary no-index quiet verbose version help no-color no-input "
        "disable-pip-version-check isolated no-cache-dir",
        "format",
    ),
    "show": (
        "fqvhV", "",
        "files quiet verbose version help no-color no-input disable-pip-version-check isolated "
        "no-cache-dir",
        "",
    ),
    "freeze": (
        "lqvhV", "",
        "local user all exclude-editable quiet verbose version help no-color no-input "
        "disable-pip-version-check isolated no-cache-dir",
        "",
    ),
    "check": (
        "qvVh", "",
        "quiet verbose version help no-color no-input disable-pip-version-check isolated no-cache-dir",
        "",
    ),
}


@pytest.mark.parametrize("sub", sorted(_PIP_TABLE_PINS))
def test_pip_tables_pinned_exactly(sub):
    sb, so, lb, lo = _PIP_TABLE_PINS[sub]
    t = shell_tools._PIP_SUBCOMMAND_TABLES[sub]
    assert t.short_bare == frozenset(sb)
    assert t.short_operand == frozenset(so)
    assert t.long_bare == frozenset(lb.split())
    assert t.long_operand == frozenset(lo.split())
    assert t.long_optional == frozenset()


def test_pip_subcommand_set_and_dangerous_options_absent():
    assert set(shell_tools._PIP_SUBCOMMAND_TABLES) == set(_PIP_TABLE_PINS)
    bad = {"--index-url", "-i", "--extra-index-url", "--find-links", "-f", "--trusted-host",
           "--target", "-t", "--root", "--prefix", "--src", "--report", "--log", "--python",
           "--proxy", "--cert", "--client-cert", "--cache-dir", "--keyring-provider",
           "--use-feature", "--use-deprecated", "-C", "--config-settings", "--dest", "-d",
           "--path", "--exclude", "--requirements-from-script", "--group", "--debug",
           "--require-virtualenv", "--exists-action", "--retries", "--timeout", "--no-proxy-env"}
    for sub, t in shell_tools._PIP_SUBCOMMAND_TABLES.items():
        present = _opt_names(t) & bad
        # `-f` is `--files` on show and `-e` is bare on list; `-f` is not
        # dangerous there, so only the install-family tables are checked for it.
        if sub == "show":
            present -= {"-f"}
        assert not present, (sub, present)
    for sub in ("freeze", "list"):
        assert "-r" not in _opt_names(shell_tools._PIP_SUBCOMMAND_TABLES[sub])


@pytest.mark.skipif(shutil.which("pip") is None, reason="pip not installed")
@pytest.mark.parametrize("sub", sorted(_PIP_TABLE_PINS))
def test_pip_table_options_exist_in_real_help(sub, tmp_path, monkeypatch):
    """Every table option must be recognized by the installed pip's own
    `--help` (catches a typo'd or version-drifted entry). Runs only `pip
    <sub> --help`: no network, no install."""
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    out = subprocess.run(["pip", sub, "--help"], capture_output=True, text=True, timeout=60).stdout
    help_opts = set(re.findall(r"(?<![\w-])(--?[A-Za-z][\w-]*)", out))
    missing = _opt_names(shell_tools._PIP_SUBCOMMAND_TABLES[sub]) - help_opts
    assert not missing, missing


def test_pip_basename_regex_admits_versioned_pip_only_after_table_check():
    assert classify("pip3.14 install foo") == ACT
    assert classify("pip3.14 install --find-l=x foo") == HIGH_IMPACT
    assert classify("pip3.14x install foo") == HIGH_IMPACT
    assert classify("pipx install foo") == HIGH_IMPACT
    assert classify("/usr/bin/pip3.14 install foo") == ACT
    assert classify("./pip3.14 install foo") == HIGH_IMPACT


def test_pip_operand_shape_regexes():
    ok = ["requests", "requests>=2,<3", "requests[security]==2.0", "a.b-c_d", ".", "..", "./x",
          "../x", "/abs/p", "~/p", ".[dev]", "requirements/dev.txt", "x1", "A"]
    bad = ["", "-", "-e", "git+https://x", "https://x", "file:x", "pkg @ https://x", "a b",
           "x;y", "user/repo:x", "a:b", "foo@1", "-x", "name==", "[x]", "a/", "./x:y"]
    for v in ok:
        assert shell_tools._pip_operand_ok(v), v
    for v in bad:
        assert not shell_tools._pip_operand_ok(v), v


# ------------------------------------------------------------------ 4.1 npm
NPM_HIGH = [
    "npm pub", "npm publ", "npm publish", "npm tok list", "npm own ls", "npm add-user",
    "npm adduser", "npm c edit", "npm c set x y", "npm conf set x y", "npm config set x y",
    "npm test --node-options=--import=data:text/javascript,1", "npm test --node-opt=x",
    "npm test --userconfig=x", "npm test --globalconfig=x", "npm run build --script-shell=sh",
    "npm run build --script-shell sh", "npm --prefix sub test", "npm --prefix=. test",
    "npm -g install foo", "npm install -g foo", "npm install --global foo",
    "npm install --location=global foo", "npm install --location global foo",
    "npm install git+https://x/y.git", "npm install github:u/r", "npm install user/repo",
    "npm install https://x/t.tgz", "npm install file:../x", "npm install link:../x",
    "npm install npm:alias@1", "npm install foo@git+https://x", "npm install git@github.com:u/r.git",
    "npm install --registry=https://x foo", "npm i --registry https://x foo",
    "npm install --@scope:registry=https://x foo", "npm exec foo", "npm x foo", "npm ex foo",
    "npm explore foo", "npm link", "npm ln", "npm set x y", "npm version patch",
    "npm init vite", "npm init @scope/app", "npm create vite", "npm init --init-module=./x.js",
    "npm isntall foo", "npm insta foo", "npm tes", "npm tst", "npm build", "npm run",
    "npm run a b", "npm -- publish", "npm -- install foo", "npm install -- git+https://x/y",
    "npm config get _authToken", "npm config get _auth", "npm config get _password",
    "npm config get //r.example/:_authToken", "npm config get cert", "npm config get registry extra",
    "npm config", "npm config get", "npm config delete x", "npm config edit", "npm config fix",
    "npm ci foo", "npm init foo", "npm init -- x", "npm test foo", "npm start x",
    "npm run build -f", "npm install -w x", "npm install --workspace=x", "npm install --force foo",
    "npm install --otp=1 foo", "npm install --proxy=x foo", "npm install --cafile=x foo",
    "npm install --logs-dir=x foo", "npm install --cache=x foo", "npm install --loglevel silly foo",
    "npm install --loglevel=a/b foo", "npm install --loglevel=http://x foo", "npm --init-module=x init",
    "npm -", "npm - install", "npm install foo\\ bar", "npm install ./x:y", "npm prefix",
    "npm cache clean", "npm doctor", "npm whoami", "npm search x", "npm Install", "NPM install",
    "npm installTest", "npm it", "npm cit", "npm sit", "npm in", "npm ins", "npm un foo",
    "npm r foo", "npm u", "npm ddp", "npm rum build", "npm urn build", "npm la", "npm s x",
    "npm edit foo", "npm get x", "npm repo", "npm docs", "npm bugs", "npm login", "npm logout",
    "npm token", "npm owner", "npm access public", "npm team", "npm org", "npm profile",
    "npm trust", "npm stage", "npm star", "npm unpublish x", "npm deprecate x", "npm dist-tag add x",
    "npm approve-scripts", "/usr/bin/npm publish", "/tmp/x/npm install", "npm install --force",
    "npm install --dry-run=", "npm install --save=a b:c", "npm install --json=" + "x" * 40,
    "npm rebuild --foreground-scripts", "npm audit --audit-level=high", "npm pack --pack-destination=/x",
]

NPM_ACT = [
    "npm i x", "npm install -D vitest", "npm install left-pad@1.3.0", "npm install @types/node",
    "npm install ./local-pkg", "npm test -- --watch", "npm run build:prod",
    "npm run test -- --node-options=--import=x", "npm ci", "npm ls --json",
    "npm config get registry", "npm config list", "npm config ls", "npm --version", "npm -v",
    "npm -h", "npm", "npm init -y", "npm init --yes", "npm install", "npm test", "npm run build",
    "npm start", "npm init", "npm install left-pad", "npm rebuild", "npm pack", "npm list",
    "npm ls", "npm ll", "npm outdated", "npm audit", "npm audit fix", "npm why foo", "npm view foo",
    "npm info foo", "npm show foo", "npm v foo", "npm view foo version",
    "npm install --no-audit --no-fund --legacy-peer-deps", "npm install --omit=dev",
    "npm install --loglevel=silly foo", "npm run build --silent", "npm --silent run build",
    "npm ls -a -l", "npm update", "npm up foo", "npm uninstall foo", "npm rm foo",
    "npm remove foo", "npm dedupe", "npm prune", "npm add foo", "npm run-script build",
    "npm explain foo", "npm t", "npm stop", "npm restart", "npm rb", "npm install JSONStream",
    "npm install foo@^1.0.0", "npm install @scope/pkg@latest", "npm run lint -- --fix",
    "npm start -- --port 3000", "npm install .", "npm install ..", "npm install ~/x",
    "npm install --save-exact foo", "npm install -E foo", "npm install --prefer-offline foo",
    "npm install --ignore-scripts", "npm install --no-save foo", "npm outdated --json",
    "npm install --audit=false", "npm test --silent", "/usr/bin/npm install",
]


@pytest.mark.parametrize("command", NPM_HIGH)
def test_npm_high_rows(command):
    assert classify(command) == HIGH_IMPACT, command


@pytest.mark.parametrize("command", NPM_ACT)
def test_npm_act_rows(command):
    assert classify(command) == ACT, command


def test_npm_tables_pinned_exactly():
    assert shell_tools._NPM_ACT_SUBCOMMANDS == frozenset(
        "install i add ci test t start stop restart run run-script rebuild rb pack ls list ll "
        "outdated audit why explain view v info show config init uninstall remove rm update up "
        "dedupe prune".split()
    )
    assert shell_tools._NPM_SAFE_FLAGS == frozenset(
        "-q -s -d --quiet --silent --verbose --json --no-audit --no-fund --legacy-peer-deps "
        "--dry-run --offline --prefer-offline --save --save-dev -D -S -E --save-exact --no-save "
        "--ignore-scripts --no-package-lock --version -v --help -h -l --long -a --all -p "
        "--parseable -y --yes".split()
    )
    assert shell_tools._NPM_SAFE_VALUE_FLAGS == frozenset(
        "loglevel omit include audit fund progress package-lock ignore-scripts save "
        "legacy-peer-deps json".split()
    )
    for dangerous in ("-g", "--global", "-w", "--workspace", "--prefix", "-C", "--location", "-L",
                      "-c", "--call", "-f", "--force", "--registry", "--script-shell",
                      "--node-options", "--userconfig", "--globalconfig", "--cache", "--otp",
                      "--proxy", "--cafile", "--logs-dir", "--init-module", "--"):
        assert dangerous not in shell_tools._NPM_SAFE_FLAGS
        assert dangerous.lstrip("-") not in shell_tools._NPM_SAFE_VALUE_FLAGS


def _npm_cmd_list():
    npm = shutil.which("npm")
    if not npm:
        return None
    root = Path(npm).resolve().parent.parent
    path = root / "lib" / "utils" / "cmd-list.js"
    abbrev = root / "node_modules" / "abbrev"
    return (path, abbrev) if path.is_file() and abbrev.exists() else None


_NPM_SAFE_TARGETS = {
    "install", "ci", "test", "start", "stop", "restart", "run", "rebuild", "pack", "ls",
    "ll", "outdated", "audit", "explain", "view", "config", "init", "uninstall", "update",
    "dedupe", "prune",
}


@pytest.mark.skipif(_npm_cmd_list() is None, reason="npm cmd-list.js not available")
def test_npm_every_abbreviation_and_alias_is_checked_against_real_cmd_list(tmp_path, monkeypatch):
    """Ask the installed npm's own cmd-list.js (abbrev(commands + aliases), the
    exact resolver npm uses) what every word resolves to. A word is ACT only if
    it is in _NPM_ACT_SUBCOMMANDS, and every _NPM_ACT_SUBCOMMANDS entry must
    resolve to a command in the safe target set. Runs node on a local file
    only: no npm command, no network."""
    path, abbrev = _npm_cmd_list()
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    script = (
        f"const l=require({json.dumps(str(path))});const ab=require({json.dumps(str(abbrev))});"
        "const all=ab(l.commands.concat(Object.keys(l.aliases)));"
        "const out={};for(const k of Object.keys(all)){out[k]=l.deref(k);}"
        "console.log(JSON.stringify(out));"
    )
    resolved = json.loads(subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=60, cwd=str(tmp_path),
    ).stdout)
    assert len(resolved) > 100
    for word in shell_tools._NPM_ACT_SUBCOMMANDS:
        assert word in resolved, word  # a real command or alias
        assert resolved[word] in _NPM_SAFE_TARGETS, (word, resolved[word])
    for word, target in resolved.items():
        verdict = classify(f"npm {word}")
        if word in shell_tools._NPM_ACT_SUBCOMMANDS:
            continue
        assert verdict == HIGH_IMPACT, (word, target)


@pytest.mark.skipif(_npm_cmd_list() is None, reason="npm lib not available")
def test_npm_name_shape_never_resolves_to_a_remote_spec_in_real_npa(tmp_path, monkeypatch):
    """Ground the operand regex in npm's own npm-package-arg: every token the
    shape check accepts (from every row above plus an adversarial corpus) must
    resolve to a registry (version/range/tag) or local (file/directory) spec,
    never git, remote or alias. Local node on a local module: no npm command,
    no network."""
    path, abbrev = _npm_cmd_list()
    npa = abbrev.parent / "npm-package-arg"
    if not npa.exists():
        pytest.skip("npm-package-arg not found")
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    corpus = {
        "foo", "foo@1", "foo@latest", "foo@^1.0.0", "foo@~1", "foo@>=1", "foo@1.x", "foo@*",
        "foo.git", "foo.tgz", "foo@x.tgz", "@s/p", "@s/p@1", "a.b", "foo@1||2", "Foo", "x", ".", "..",
        "./x", "../x", "/abs", "~/x", ".[dev]", "./x.tgz", "bitbucket", "github", "gist",
        "foo@github", "foo@user", "foo@1.0.0-beta.1", "foo@v1", "foo@next", "foo@git", "foo@npm",
        "foo@file", "foo@link", "foo@http", "foo@a.b", "foo@a-b", "a@b",
    }
    for row in (*NPM_ACT, *NPM_HIGH, *PNPM_YARN_ACT, *PNPM_YARN_HIGH):
        try:
            corpus.update(t for t in shlex.split(row) if not t.startswith("-"))
        except ValueError:
            pass
    accepted = sorted(v for v in corpus if shell_tools._npm_operand_ok(v))
    assert len(accepted) > 40
    script = (
        f"const npa=require({json.dumps(str(npa))});const out={{}};"
        f"for(const a of {json.dumps(accepted)}){{try{{out[a]=npa(a,{json.dumps(str(tmp_path))}).type;}}"
        "catch(e){out[a]='error';}}console.log(JSON.stringify(out));"
    )
    types = json.loads(subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=60, cwd=str(tmp_path),
    ).stdout)
    assert set(types) == set(accepted)
    bad = {a: t for a, t in types.items() if t not in {"version", "range", "tag", "file", "directory", "error"}}
    assert not bad, bad


def test_npm_i_x_is_act_the_x_token_is_an_operand_not_the_exec_alias():
    assert classify("npm i x") == ACT
    assert classify("npm x i") == HIGH_IMPACT


def test_npm_operand_regexes():
    ok = ["foo", "foo@1.2.3", "@scope/pkg", "@scope/pkg@^1", "a.b_c-d", "JSONStream", "foo@latest"]
    bad = ["", "user/repo", "github:u/r", "git+https://x", "https://x", "file:x", "npm:a@1",
           "foo@npm:bar", "foo@git+ssh://x", "foo@u/r", "@scope", "-x", "a b", "foo@", "@scope/"]
    for v in ok:
        assert shell_tools._NPM_NAME_SPEC_RE.fullmatch(v), v
    for v in bad:
        assert not shell_tools._NPM_NAME_SPEC_RE.fullmatch(v), v


# ---------------------------------------------------------- 4.3 pnpm / yarn
PNPM_YARN_HIGH = [
    "pnpm add github:u/r", "yarn add https://x/t.tgz", "pnpm add git+https://x/y.git",
    "pnpm add user/repo", "yarn add git@github.com:u/r.git", "pnpm add --registry=https://x foo",
    "pnpm add --registry https://x foo", "pnpm link --global", "yarn link", "pnpm ln", "yarn ln",
    "pnpm install npm:foo@1", "yarn add foo@npm:bar", "yarn upgrade user/repo", "pnpm update x:y",
    "pnpm i github:u/r", "yarn up https://x", "pnpm add --filter=foo:bar x", "pnpm link ../x",
    "pnpm --dir https://x add foo", "yarn --cwd git+https://x add foo", "pnpm install foo user/repo",
]
PNPM_YARN_ACT = [
    "pnpm add foo", "pnpm add -D foo@1.2.3", "yarn add @scope/pkg", "pnpm install", "yarn install",
    "pnpm add ./local", "pnpm --dir ./sub add foo", "pnpm run build:prod", "pnpm install --frozen-lockfile",
    "yarn add foo@^1", "pnpm test", "yarn test", "pnpm remove foo", "yarn upgrade foo", "pnpm up foo",
    "yarn --silent add foo", "pnpm add ../x", "pnpm add .",
]


@pytest.mark.parametrize("command", PNPM_YARN_HIGH)
def test_pnpm_yarn_high_rows(command):
    assert classify(command) == HIGH_IMPACT, command


@pytest.mark.parametrize("command", PNPM_YARN_ACT)
def test_pnpm_yarn_act_rows(command):
    assert classify(command) == ACT, command


# --------------------------------------- gateway rows (recording fakes only)
@pytest.fixture
def gw(tmp_path, monkeypatch):
    home, state, ws = tmp_path / "home", tmp_path / "state", tmp_path / "ws"
    for d in (home, state, ws):
        d.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEY_STATE_DIR", str(state))
    monkeypatch.setattr(shell_tools._config, "CODEY_STATE_DIR", state)
    monkeypatch.setattr(shell_tools._config, "WORKSPACE_ROOT", ws)
    monkeypatch.chdir(ws)
    # PATH-dependent shadow check is Unit A's concern, not under test here.
    monkeypatch.setattr(shell_tools, "_command_shadows_system_binary", lambda command: False)
    audit = tmp_path / "audit.jsonl"
    instance = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: instance)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    monkeypatch.delitem(AGENT_CONFIG, "_shell_fn", raising=False)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    return SimpleNamespace(audit=audit, runner=runner)


def _last(gw):
    return json.loads(gw.audit.read_text().splitlines()[-1])


@pytest.mark.parametrize("command", [
    "npm pub", "npm publ", "npm tok list", "npm own ls", "npm add-user", "npm c edit",
    "npm test --node-opt=x", "pip install -qf x foo", "pip install --find-l=/d foo",
    "pip install --target=x foo", "pip --python /tmp/e install foo",
    "node --inspect=0.0.0.0:9229 x.js", "python3 -m http.server 8000",
])
def test_shell_refuses_without_spawn(gw, command):
    out = shell_tools.shell(command)
    assert out.startswith("[BLOCKED]"), out
    gw.runner.assert_not_called()
    row = _last(gw)
    assert row["authority"] == HIGH_IMPACT and row["outcome"] == "refused"


@pytest.mark.parametrize("command", [
    "npm i x", "npm test", "pip install foo", "pip3.14 install foo", "pip list",
    "python3 -m pytest -q", "node --inspect=9229 x.js", "npm config get registry",
])
def test_shell_admits_recorded_argv(gw, command):
    out = shell_tools.shell(command)
    assert not out.startswith("[BLOCKED]"), out
    gw.runner.assert_called_once()
    argv = gw.runner.call_args.args[0]
    assert argv == shlex.split(command)
    assert _last(gw)["authority"] == ACT


@pytest.mark.parametrize("command", [
    "pip install --find-l=x foo", "pip install -qf x foo", "pip install --target=x foo",
])
def test_daemon_refuses_pip_forms_without_spawn(gw, command):
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell(command).startswith("[BLOCKED]")
    gw.runner.assert_not_called()


@pytest.mark.parametrize("command", ["pip install foo", "python3 x.py"])
def test_daemon_still_runs_ordinary_forms_once(gw, command):
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert not executor._daemon_shell(command).startswith("[BLOCKED]")
    gw.runner.assert_called_once()
    assert gw.runner.call_args.args[0] == shlex.split(command)


def test_classifier_stays_lexical_for_unit_b_forms(monkeypatch):
    """No filesystem, subprocess or environment access while classifying the
    Unit B forms (the no-discovery invariant of the wrapper-boundary test)."""
    def boom(*a, **k):
        raise AssertionError("classifier touched the outside world")
    monkeypatch.setattr(shell_tools.subprocess, "run", boom)
    monkeypatch.setattr(Path, "exists", boom)
    monkeypatch.setattr(Path, "resolve", boom)
    monkeypatch.setattr(shell_tools.os, "getenv", boom)
    for c in ("npm pub", "npm i x", "pip install -qf x foo", "pip3.14 install foo",
              "python3 -m http.server", "node --inspect=0.0.0.0:1 x.js", "pnpm link", "yarn add foo"):
        classify(c)


# ------------------- review W1: `node inspect` subcommand (debugger client)
@pytest.mark.parametrize("command", [
    "node inspect --probe t.js:2 --expr 'CODE' -- t.js", "node inspect -e 1", "node inspect -p 1",
    "node inspect t.js", "node inspect host:9229", "node inspect", "nodejs inspect t.js",
    "node --no-warnings inspect t.js", "node --inspect-brk inspect x", "node -- inspect",
    "node -- inspect -e 1", "node --test inspect", "node -i inspect",
])
def test_node_inspect_subcommand_is_high(command):
    assert classify(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", [
    "node t.js inspect", "node t.js -p 1 inspect", "node -- t.js inspect", "node debug t.js",
    "node inspect.js", "node ./inspect", "node inspector.js", "node x.js --inspect",
    "node Inspect", "ruby inspect", "perl inspect",
])
def test_node_inspect_as_argument_or_other_name_stays_act(command):
    # `inspect` after the script is a script argument; `node debug` is a plain
    # script path in node v24 (verified: "Cannot find module .../debug").
    assert classify(command) == ACT
