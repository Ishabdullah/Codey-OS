"""G15c: explicit ACT allowlist for build/lint/test tools; default-deny otherwise.

Classification only: no command is executed; subprocess is faked before use.
"""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, task_executor
from core.action_gateway import ACT, HIGH_IMPACT, READ, ActionGateway
from tools import shell_tools
from utils.config import AGENT_CONFIG

ALLOWLIST = [
    "ruff", "black", "isort", "flake8", "mypy", "pylint", "make", "cmake",
    "cargo", "rustc", "gcc", "g++", "cc", "clang", "go", "tsc", "javac",
    "pnpm", "yarn",
]


def test_allowlist_set_is_exactly_the_documented_one():
    assert shell_tools._BUILD_TOOL_ACT_BASENAMES == frozenset(ALLOWLIST)


@pytest.mark.parametrize("tool", ALLOWLIST)
def test_each_allowlisted_tool_is_act(tool):
    assert shell_tools.classify_shell_command(tool) == ACT
    assert shell_tools.classify_shell_command(f"{tool} --version") == ACT
    assert shell_tools.classify_shell_command(f"/usr/bin/{tool} --version") == ACT


@pytest.mark.parametrize("command", [
    "ruff check .", "ruff --fix .", "ruff format src", "black .", "isort .",
    "make test", "make -f /dev/stdin", "make SHELL=/bin/sh test",
    "cargo build", "cargo run", "cargo test", "go build ./...", "go run main.go",
    "go test ./...", "gcc -o a a.c", "tsc --noEmit", "yarn test", "pnpm install",
    "pnpm run build", "mypy pkg", "cmake -B build", "javac A.java",
])
def test_project_code_and_edit_forms_stay_act(command):
    # Residual (accepted, NEW-904 precedent): these run arbitrary project code.
    assert shell_tools.classify_shell_command(command) == ACT


@pytest.mark.parametrize("command", [
    "pnpm dlx evil", "yarn dlx evil", "pnpm exec evil", "yarn exec evil",
    "pnpm create x", "yarn --silent dlx evil",
    "go run example.com/x@latest", "go install example.com/x@latest",
])
def test_remote_fetch_and_run_forms_are_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", [
    "npx foo", "curl x", "wget x", "ssh h", "scp a b", "gh repo create x",
    "su -c id", "doas id", "sudo id", "kill 1", "pkill x", "killall x",
    "bash -c 'make'", "sh -c 'gcc a.c'", "python3 -c 'print(1)'",
    "node -e 1", "perl -e 1", "ruby -e 1", "lsof", "ninja", "rustup", "mvn",
])
def test_non_allowlisted_and_escape_forms_are_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", [
    "FOO=1 gcc a.c", "GCC a.c", "Make test", "./gcc a.c", "./make", "../bin/ruff .",
    "/tmp/x/gcc a.c", "/home/u/bin/make", "usr/bin/gcc", "/usr/bin/../../tmp/gcc",
    "gcc-12 a.c", "gccx", "makefile", "ruff2", "'unterminated gcc",
])
def test_argument_and_path_tricks_are_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", ['"gcc" a.c', "'make' test", "/usr/bin/'gcc' a.c"])
def test_quoted_exact_name_is_tokenized_like_unquoted(command):
    assert shell_tools.classify_shell_command(command) == ACT


def test_symlink_looking_name_gets_no_trust_from_target(tmp_path):
    # Classification is by the typed name only; a link called `gcc` elsewhere
    # is not on a system dir and a differently named link to gcc is unknown.
    assert shell_tools.classify_shell_command(f"{tmp_path}/gcc a.c") == HIGH_IMPACT
    assert shell_tools.classify_shell_command("my-gcc-link a.c") == HIGH_IMPACT


@pytest.mark.parametrize("command", ["ls", "cat f", "grep x f", "pytest -q"])
def test_read_and_existing_act_unchanged(command):
    assert shell_tools.classify_shell_command(command) in (READ, ACT)


# ---- daemon word boundary (NEW-1007) ------------------------------------

@pytest.mark.parametrize("cmd,expected", [
    ("ls", True), ("ls -l", True), ("ls\t-l", True), ("cd /x", True), ("cd", True),
    ("git status", True), ("git status -s", True), ("env", True), ("pytest -q", True),
    ("lsof", False), ("lsof -i", False), ("catx f", False), ("environ", False),
    ("echoes", False), ("grepx", False), ("findx .", False), ("pytestx", False),
    ("git statusx", False), ("git status-x", False), ("cd/x", False), ("pwdx", False),
    ("whichever", False), ("printenvx", False), ("git logger", False),
])
def test_daemon_prefix_word_boundary(cmd, expected):
    got = any(task_executor._daemon_prefix_matches(cmd, p)
              for p in task_executor._DAEMON_ALLOWED_PREFIXES)
    assert got is expected


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    instance = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: instance)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    monkeypatch.delitem(AGENT_CONFIG, "_shell_fn", raising=False)
    return SimpleNamespace(audit=audit)


@pytest.mark.parametrize("command", ["lsof -i", "catx f", "environ"])
def test_daemon_blocks_prefix_lookalikes_before_any_spawn(gateway, monkeypatch, command):
    runner = Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell(command).startswith("[BLOCKED]")
    runner.assert_not_called()
    row = json.loads(gateway.audit.read_text())
    assert row["action"] == "task_executor.daemon_shell" and row["outcome"] == "refused"


def test_daemon_still_allows_whole_word_prefix(gateway, monkeypatch):
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="out", stderr=""))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell("ls -l") == "out"
    runner.assert_called_once()


# ---- round 2: bundled short-flag inline code (FIX 1) ----------------------

@pytest.mark.parametrize("command", [
    "python3 -Bc x", "python3 -Ic x", "python3 -Sc x", "python3 -uc x",
    "python3 -qc x", "python3 -Ec x", "python3 -OOc x", "python3.11 -Bc x",
    "python3 -Wignore -c x", "python3 -W ignore -Bc x", "python3 -Xdev -c x",
    "python3 -c x", "python -Bc x",
    "perl -Mstrict -e 1", "perl -we 1", "perl -pie 1", "perl -0777ne 1",
    "perl -i.bak -pe 1", "perl '-Mstrict;system\"id\"' x.pl",
    "perl -M'strict; system \"id\"' x.pl", "perl -M 'strict; system \"id\"' x.pl",
    "ruby -0777ne 1", "ruby -ne 1", "ruby -le 1", "ruby -Ke 1", "ruby -Cd -e 1",
    "node -pe 1", "node -e 1", "node --eval=1", "node -r x -e 1",
])
def test_bundled_inline_code_forms_are_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", [
    "python3 x.py", "python3 -B x.py", "python3 -u script.py -c foo",
    "python3 -Wc x.py",  # -W with operand `c`, not inline code
    "python3 -W ignore x.py", "python3 -X dev x.py",
    "python3 -m pytest", "python3 -Im pytest", "python3 -Bm pytest -c foo",
    "python3.11 x.py", "perl -Mstrict x.pl", "perl -MData::Dumper=Dumper x.pl",
    "ruby x.rb", "ruby -rcsv x.rb", "ruby -W0 x.rb", "node x.js", "pytest -q",
])
def test_script_and_module_forms_stay_act(command):
    # G15d 4.5: `-m` is ACT only for allowlisted modules (pytest here); the
    # former residual (`-m http.server` / `-m code`) is now HIGH, pinned in
    # tests/test_shell_g15d_unit_b.py.
    assert shell_tools.classify_shell_command(command) == ACT


@pytest.mark.parametrize("command", [
    "python3 -Bc 'print(1)'", "python3 -Ic x", "python3 -Ec x",
    "python3.11 -Bc x", "python3 -OOc x",
])
def test_shell_bundled_python_c_is_confirm_gated_not_silent(gateway, monkeypatch, command):
    # Without a confirm path (confirm_shell False, not yolo) a HIGH_IMPACT
    # command must not spawn.
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="o", stderr=""))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT
    out = shell_tools.shell(command)
    assert not runner.called, out


@pytest.mark.parametrize("command", [
    "python3 -Ic 'import os'", "python3 -Bc x", "python3 -Ec x", "python3 -Wc x.py",
    "python3 -Im pytest", "python3 -Bm pytest", "python3 -OOc x", "python3 -Sc x",
    "python3 -c x", "python3 -m pytest", "python3 -Wignore -c x",
])
def test_daemon_refuses_bundled_inline_forms_without_spawn(gateway, monkeypatch, command):
    runner = Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell(command).startswith("[BLOCKED]")
    runner.assert_not_called()
    row = json.loads(gateway.audit.read_text().splitlines()[-1])
    assert row["action"] == "task_executor.daemon_shell" and row["outcome"] == "refused"


@pytest.mark.parametrize("command", ["python3.11 -Bc x", "python3 'unterminated"])
def test_daemon_refuses_python311_and_unparseable(gateway, monkeypatch, command):
    runner = Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell(command).startswith("[BLOCKED]")
    runner.assert_not_called()


@pytest.mark.parametrize("command", ["python3 x.py", "pytest -q"])
def test_daemon_still_allows_plain_script_and_pytest(gateway, monkeypatch, command):
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell(command) == "ok"
    runner.assert_called_once()


# ---- round 2: option-operand subcommand bypass (FIX 2) --------------------

@pytest.mark.parametrize("command", [
    "pnpm --dir . dlx x", "pnpm -C . exec x", "yarn --cwd . dlx x",
    "pnpm --filter x exec y", "pnpm -r dlx x", "yarn --silent dlx x",
    "pnpm -r exec x", "yarn -s create x",
])
def test_option_operand_before_remote_fetch_subcommand_is_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


def test_remote_fetch_token_anywhere_false_positive_is_documented():
    # Accepted false positive: a script named like a verb is conservative HIGH.
    assert shell_tools.classify_shell_command("pnpm run exec") == HIGH_IMPACT
    assert shell_tools.classify_shell_command("pnpm run build") == ACT


# ---- round 2: publishing policy (FIX 3, G15-F1) ---------------------------

@pytest.mark.parametrize("command", [
    "cargo publish", "cargo login tok", "cargo logout", "cargo owner --add x",
    "cargo yank --version 1", "cargo install --git https://x/y",
    "cargo install --registry other foo", "cargo install foo",
    "pnpm publish", "pnpm login", "pnpm logout", "pnpm adduser", "pnpm token list",
    "pnpm owner ls", "pnpm --dir . publish", "yarn publish", "yarn login",
    "yarn logout", "yarn npm publish", "yarn npm login", "yarn owner add",
    "go get example.com/x", "go get -u ./...", "go install example.com/x@v1",
    "go run example.com/x@latest",
    "npm publish", "npm login", "npm adduser", "npm token create", "npm owner add",
    "npm access public", "npm deprecate x", "npm unpublish x", "npm dist-tag add x",
    "npm exec foo", "npm x foo", "npm init vite", "npm init @scope/app",
    "npm create vite", "npm init --init-module=./x.js", "npm --prefix . publish",
    "/usr/bin/npm publish",
])
def test_publishing_and_remote_initializer_forms_are_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", [
    # G15d 4.1: `npm build` was removed from this list on purpose: it is not
    # an npm command (`Unknown command`), so the exact-subcommand allowlist
    # classifies it HIGH_IMPACT (see test_npm_build_is_high_not_a_command).
    "npm install", "npm test", "npm run build", "npm ci", "npm start",
    "npm init", "npm init -y", "npm install left-pad", "pip install requests",
    "pip install -U requests", "pip install -e .", "pip install -r requirements.txt",
    "pip download requests", "python3 -m pip install requests",
    "cargo build", "cargo install --path .", "go build ./...", "go test ./...",
    "pnpm install", "yarn install", "yarn test",
])
def test_ordinary_build_and_install_forms_stay_act(command):
    assert shell_tools.classify_shell_command(command) == ACT


def test_npm_build_is_high_not_a_command():
    # Deliberate G15d 4.1 update (rule 6): `npm build` used to be ACT only
    # because the old denylist did not mention it; npm has no such command.
    assert shell_tools.classify_shell_command("npm build") == HIGH_IMPACT


# ---- round 3: structural fail-closed for node/ruby/perl --------------------
# Reviewer's round-2 lists (res.txt/c2.txt): every previously-HIGH stays HIGH,
# legitimate script runs stay ACT, operand-taking-option bypasses are HIGH.

@pytest.mark.parametrize("command", [
    # round-2 bypass forms: an option operand hid the real -e/-p
    "node -C x -e 1", "node -C x -p '2+2'", "node --conditions x -e 1",
    "node --title x -e 1", "node --disable-warning x -e 1",
    "node --env-file x -e 1", "node --env-file x.env -e 1",
    "node --input-type module -e 1", "node --input-type=module -e 1",
    "node --stack-size 1 -e 1", "node --max-old-space-size 100 -e 1",
    "node --max-old-space-size 100 -p 1", "node --experimental-loader x -e 1",
    "node --test-name-pattern x -e 1", "node --input-type module x.mjs",
    "ruby --disable gems -e 1", "ruby --external-encoding utf-8 -e 1",
    "ruby -C dir -e 1", "perl -I lib -e 1", "perl -M strict -e 1",
    # previously HIGH, must stay HIGH
    "node -pe 1", "node -e 1", "node --eval=1", "node --eval 1", "node --print 1",
    "node -r x -e 1", "node -p 1", "node -pr x", "node --check x.js",
    "nodejs -e 1", "node --require x -e 1", "node --import x -e 1",
    "node --loader x -e 1", "node --eval-x 1", "node --stack-size=1 -e 1",
    "node --experimental-vm-modules -e 1", "node --import=data:text/javascript,1 x.js",
    "perl -Mstrict -e 1", "perl -we 1", "perl -pie 1", "perl -0777ne 1",
    "perl -i.bak -pe 1", "perl5.30 -e 1", "perl -mstrict;system x.pl",
    "perl -Mstrict;system(\"id\") x.pl", "perl -x x.pl",
    "ruby -0777ne x", "ruby -Ke x", "ruby -le x", "ruby -e x", "ruby -w -e x",
    "ruby -ne x", "ruby -cw x", "ruby -I lib -e x", "ruby -rfoo -e x",
    "ruby -x x.rb", "ruby -a x.rb", "node --some-unknown-flag x.js",
    "perl -unknown x.pl", "ruby --unknown x.rb", "perl -I -e 1", "perl -I",
    "perl -I lib -I -e 1",
])
def test_node_ruby_perl_unknown_or_inline_forms_are_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", [
    "node", "node app.js", "node app.js -e", "node x.js -p 1", "node -", "node -- x.js",
    "node -v", "node --version", "node --help", "node -i", "node --interactive",
    "node --inspect x.js", "node --inspect=9229 x.js", "node --test",
    "node --test x.test.js", "node --run build", "node --run=build",
    "node --watch x.js", "node --no-warnings x.js", "node -r./x.js x.js",
    "node --require=x x.js", "node --max-old-space-size=100 x.js",
    "nodejs x.js",
    "perl", "perl x.pl", "perl x.pl -e", "perl -l x.pl", "perl -w x.pl",
    "perl -Mstrict x.pl", "perl -MPOSIX=floor x.pl", "perl -M-strict x.pl",
    "perl -I lib x.pl", "perl -Mstrict=vars x.pl", "perl -MFoo::Bar x.pl", "perl -I. x.pl",
    "perl -- x.pl", "perl -v",
    "ruby", "ruby x.rb", "ruby x.rb -e", "ruby -rcsv x.rb", "ruby -Ilib x.rb",
    "ruby -W0 x.rb", "ruby -w x.rb", "ruby --version", "ruby -- x.rb",
])
def test_node_ruby_perl_script_runs_stay_act(command):
    assert shell_tools.classify_shell_command(command) == ACT


def test_node_option_table_derived_from_real_help_is_exact():
    # Read from `node --help` / `node --v8-options` (v24.18.0). Any change to
    # the allowlist must be a deliberate, reviewed edit of this table.
    assert shell_tools._NODE_SAFE_BARE_OPTIONS == frozenset({
        "-v", "--version", "-h", "--help", "-i", "--interactive",
        "--inspect", "--inspect-brk", "--inspect-wait", "--test", "--test-only",
        "--watch", "--run", "--no-warnings", "--no-deprecation",
        "--trace-warnings", "--trace-deprecation", "--trace-uncaught",
        "--throw-deprecation", "--enable-source-maps", "--expose-gc",
        "--preserve-symlinks", "--experimental-vm-modules",
    })
    for forbidden in ("-e", "--eval", "-p", "--print", "-c", "--check",
                      "--import", "--loader", "--experimental-loader"):
        assert forbidden not in shell_tools._NODE_SAFE_BARE_OPTIONS
        assert not forbidden.startswith(shell_tools._NODE_SAFE_ATTACHED_PREFIXES)


# ---- round 3: package-manager dispatch to executors ------------------------

@pytest.mark.parametrize("command", [
    "yarn node -e 1", "pnpm node -p 1", "yarn run node -e 1", "pnpm env use 20",
    "pnpm env", "pnpm self-update", "yarn self-update", "yarn set version berry",
    "yarn set version https://x/y.cjs", "yarn plugin import https://x",
    "yarn config set x y", "pnpm config set x y", "yarn explore foo", "yarn bin",
    "pnpm bin", "pnpm --dir . node -e 1",
    "npm explore foo -- node -e 1", "npm explore foo", "npm set x y",
    "npm link", "npm config set script-shell x", "npm config edit",
    "npm config delete x", "npm config fix", "npm run build --script-shell=sh",
    "npm run build --script-shell sh", "pnpm run build --script-shell=sh",
    "yarn run build --script-shell=sh",
])
def test_package_manager_executor_dispatch_forms_are_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", [
    "npm install", "npm i left-pad", "npm run build", "npm test", "npm ci",
    "npm start", "npm rebuild", "npm pack", "npm config get registry",
    "npm config list", "npm list", "npm ls", "npm outdated", "npm audit",
    "npm why foo", "npm view foo", "npm info foo",
    "pnpm install", "pnpm add foo", "pnpm remove foo", "pnpm run build", "pnpm test",
    "pnpm build", "pnpm lint", "pnpm why foo", "pnpm list", "pnpm ls",
    "pnpm outdated", "pnpm audit", "pnpm info foo", "pnpm view foo",
    "yarn install", "yarn add foo", "yarn remove foo", "yarn run build", "yarn test",
    "yarn build", "yarn start", "yarn lint", "yarn why foo", "yarn list",
    "yarn outdated", "yarn audit", "yarn info foo", "yarn --version",
])
def test_routine_package_manager_forms_stay_act(command):
    # Accepted false positives: an operand/script named node|env|set|plugin|
    # config|explore|bin|self-update (`pnpm run node`) is HIGH, not the
    # reverse. G15d 4.1: for npm only the SUBCOMMAND position is checked now,
    # so the old accidental false positive (`npm i x`, operand `x` equal to the
    # `x` exec alias) is gone and `npm i x` is ACT (pinned in the unit B file).
    assert shell_tools.classify_shell_command(command) == ACT


# ---- round 3: residual flags closed ----------------------------------------

@pytest.mark.parametrize("command", [
    "go build -toolexec x", "go build -toolexec=x", "go build --toolexec=x ./...",
    "go test -exec x", "go test -exec=x ./...", "go run -exec x y.go",
    "go vet -vettool=x", "go vet -vettool x", "go generate", "go generate ./...",
    "go env -w GOFLAGS=-toolexec=x", "go env -u GOFLAGS", "go -C x generate",
    "cargo build --config build.rustc-wrapper=x", "cargo --config x build",
    "cargo build --config=x", "cargo -Z unstable-options build", "cargo -Zfoo build",
    "cargo build --rustc-wrapper x", "cargo test -Z x",
    "gcc -wrapper gdb a.c", "g++ -wrapper x a.cc", "cc -wrapper x a.c",
    "clang -wrapper x a.c", "rustc -wrapper x a.rs",
    "make --eval=x", "make --eval x", "make -E x", "make -Ex", "make -kE x",
    "pip config set global.index-url x", "pip install --index-url https://x y",
    "pip install --index-url=https://x y", "pip install -i https://x y",
    "pip install -ihttps://x y", "pip install --extra-index-url https://x y",
    "pip install --find-links /x y", "pip install -f /x y",
    "pip install --trusted-host x y", "pip install git+https://x/y.git",
    "pip install https://x/y.tgz", "pip install http://x/y.tgz",
    "pip install file:///x/y", "pip install -e git+https://x/y#egg=z",
    "pip install svn+https://x/y", "pip3 install --index-url x y",
    # non-URL operands: only the option token itself can trigger HIGH
    "pip install -i /local/idx y", "pip install --extra-index-url /idx y",
    "pip install --index-url=/idx y", "pip install --extra-index-url=/idx y",
    "pip install --find-links=/d y", "pip install --trusted-host=h y",
    "pip install -i/local/idx y", "pip install -f/dir y",
    "pip install git+ssh://h/r.git", "pip install git+file:///r",
    "python3 -m pip install --index-url x y", "python3 -m pip config set a b",
    "python3 -m pip install git+https://x/y",
])
def test_round3_residual_flag_forms_are_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", [
    "go build ./...", "go test ./...", "go test -run exec ./...", "go vet ./...",
    "go run ./cmd", "go env", "go env GOPATH", "go env -json", "go mod tidy",
    "go install ./...", "go fmt ./...",
    "cargo build", "cargo test", "cargo run", "cargo check", "cargo build --release",
    "gcc a.c", "g++ -Wall a.cc", "cc -o a a.c", "clang -O2 a.c", "rustc a.rs",
    "make", "make test", "make -j4", "make -f Makefile", "make -C sub",
    "make -k test", "make -e test", "make SHELL=/bin/sh test",
    "pip install foo", "pip install -U foo", "pip install -e .",
    "pip install -r requirements.txt", "pip install ./localpkg", "pip list",
    "pip freeze", "pip show foo", "pip3 install foo", "python3 -m pip install foo",
    "python3 -m pip list",
])
def test_round3_routine_forms_stay_act(command):
    assert shell_tools.classify_shell_command(command) == ACT


# ---- round 3: daemon HIGH_IMPACT clause is load-bearing --------------------
# These pass the daemon's python prefix check, contain no `-c/-e/-m/-r` flag or
# bundled cluster, so ONLY the classify_shell_command(...) == HIGH_IMPACT
# clause (DANGEROUS_PATTERNS) refuses them (reviewer mutation M7 survived).

@pytest.mark.parametrize("command", [
    "python3 x.py sudo foo", "python3 x.py chmod 777 y", "python3 x.py mkfs y",
    "python3 x.py dd if=a of=b",
    "python3 x.py > /etc/passwd", "pip install foo mkfs",
])
def test_daemon_high_impact_clause_refuses_dangerous_pattern_args(gateway, monkeypatch, command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT
    runner = Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    out = executor._daemon_shell(command)
    assert out.startswith("[BLOCKED]")
    runner.assert_not_called()
    row = json.loads(gateway.audit.read_text().splitlines()[-1])
    assert row["action"] == "task_executor.daemon_shell" and row["outcome"] == "refused"


@pytest.mark.parametrize("command", [
    "pip install --index-url https://x y", "pip install git+https://x/y.git",
])
def test_daemon_refuses_redirected_or_vcs_pip_without_spawn(gateway, monkeypatch, command):
    runner = Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell(command).startswith("[BLOCKED]")
    runner.assert_not_called()
