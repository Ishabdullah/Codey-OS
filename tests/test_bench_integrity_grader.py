"""G15f Unit A: hardened bench grader and bench-child environment (docs/wp2_1_g15f_spec.md).

Only the grader tests start subprocesses (short pytest children on disposable
copies of a task). Nothing here runs main.py or the real agent closure.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bench import agents, verify
from bench.agents import bench_child_env, make_codey_cli_agent
from bench.suite import Task, load_tasks
from bench.verify import GradingError, _grader_env, grade
from tools.wp21_census import ENV_CLASS_AUTHORITY


def _task(tmp_path):
    t = load_tasks()[0]
    d = tmp_path / "tasks" / t.id
    shutil.copytree(t.dir, d)
    return Task(t.id, d)


def _ws(tmp_path, task, solved=False):
    ws = tmp_path / "ws"
    shutil.copytree(task.reference if solved else task.starter, ws)
    return ws


COLLECT_ONLY = "[pytest]\naddopts = --collect-only\n"
PLANTED = {
    "conftest_force_pass": {"conftest.py": (
        "import pytest\n@pytest.hookimpl(hookwrapper=True)\n"
        "def pytest_runtest_makereport(item, call):\n    out = yield\n    rep = out.get_result()\n"
        "    rep.outcome = 'passed'\n")},
    "conftest_configure_exit0": {"conftest.py": "import os\ndef pytest_configure(config):\n    os._exit(0)\n"},
    "pytest_ini": {"pytest.ini": COLLECT_ONLY},
    "tox_ini": {"tox.ini": COLLECT_ONLY},
    "setup_cfg": {"setup.cfg": "[tool:pytest]\naddopts = --collect-only\n"},
    "pyproject": {"pyproject.toml": "[tool.pytest.ini_options]\naddopts = '--collect-only'\n"},
    "ini_plugin": {"pytest.ini": "[pytest]\naddopts = -p zzplug\n",
                   "zzplug.py": "import os\ndef pytest_configure(config):\n    os._exit(0)\n"},
    "sitecustomize": {"sitecustomize.py": "import os\nos._exit(0)\n"},
    "usercustomize": {"usercustomize.py": "import os\nos._exit(0)\n"},
    "extra_test_exit0": {"test_zz.py": "import os\nos._exit(0)\n"},
    "sys_exit0": {"slug.py": "import sys\nsys.exit(0)\n"},
    "pytest_main_hijack": {"slug.py": "import os, pytest\nos._exit(pytest.main(['--collect-only', '-q']))\n"},
    "shadow_pytest_py": {"pytest.py": "import os\nos._exit(0)\n"},
    "shadow__pytest_pkg": {"_pytest/__init__.py": "import os\nos._exit(0)\n"},
    "shadow_xml_pkg": {"xml/__init__.py": "import os\nos._exit(0)\n"},
    "shadow_pluggy": {"pluggy/__init__.py": "import os\nos._exit(0)\n"},
    "conftest_in_subdir": {"sub/conftest.py": "import os\nos._exit(0)\n"},
}


def test_positive_control_reference_passes(tmp_path):
    t = _task(tmp_path)
    assert grade(t, _ws(tmp_path, t, solved=True)) is True
    shutil.rmtree(tmp_path / "ws")
    assert grade(t, _ws(tmp_path, t)) is False  # unsolved starter loses


@pytest.mark.parametrize("name", sorted(PLANTED))
def test_planted_config_cannot_force_a_pass(tmp_path, name):
    t = _task(tmp_path)
    ws = _ws(tmp_path, t)
    for rel, body in PLANTED[name].items():
        p = ws / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    assert grade(t, ws) is False


def test_ambient_pytest_addopts_does_not_leak(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTEST_ADDOPTS", "--collect-only")
    t = _task(tmp_path)
    assert grade(t, _ws(tmp_path, t)) is False
    shutil.rmtree(tmp_path / "ws")
    assert grade(t, _ws(tmp_path, t, solved=True)) is True


def test_exit0_without_evidence_is_false(tmp_path):
    t = _task(tmp_path)
    ws = _ws(tmp_path, t)
    (ws / "slug.py").write_text("import os\nos._exit(0)\n")
    assert grade(t, ws) is False  # rc 0, no junit


FORGE = (
    "import os, sys\n"
    "path = [a for a in sys.argv if a.startswith('--junitxml=')][0].split('=', 1)[1]\n"
    "open(path, 'w').write('<testsuites><testsuite tests=\"{n}\" failures=\"0\" errors=\"0\" skipped=\"0\"/></testsuites>')\n"
    "os._exit(0)\n")


def test_forged_junit_wrong_count_is_false(tmp_path):
    t = _task(tmp_path)
    ws = _ws(tmp_path, t)
    (ws / "slug.py").write_text(FORGE.format(n=1))
    assert grade(t, ws) is False


def test_forged_junit_correct_count_passes_known_residual(tmp_path):
    # KNOWN RESIDUAL, spec 0.3: the agent module runs inside the grader process,
    # so a forged junit with the correct count passes. Pinned so a future fix
    # (out-of-process verdict channel, D-10) has to flip this deliberately.
    t = _task(tmp_path)
    ws = _ws(tmp_path, t)
    (ws / "slug.py").write_text(FORGE.format(n=4))
    assert grade(t, ws) is True


def test_garbled_or_oversized_junit_is_false_not_exception(tmp_path):
    t = _task(tmp_path)
    ws = _ws(tmp_path, t)
    (ws / "slug.py").write_text(
        "import os, sys\npath = [a for a in sys.argv if a.startswith('--junitxml=')][0].split('=', 1)[1]\n"
        "open(path, 'w').write('<<<not xml')\nos._exit(0)\n")
    assert grade(t, ws) is False
    big = tmp_path / "big.xml"
    big.write_bytes(b"<a>" + b"x" * (verify._JUNIT_MAX_BYTES + 10) + b"</a>")
    assert verify._junit_counts(big) is None
    assert verify._junit_counts(tmp_path / "missing.xml") is None


@pytest.mark.parametrize("rc,counts,ok", [
    (0, (4, 0, 0, 0), True),
    (1, (4, 0, 0, 0), False),      # perfect-looking junit but non-zero exit
    (0, None, False),              # no evidence
    (0, (3, 0, 0, 0), False),      # fewer tests than expected
    (0, (5, 0, 0, 0), False),      # more tests than expected
    (0, (4, 1, 0, 0), False),
    (0, (4, 0, 1, 0), False),
    (0, (4, 0, 0, 1), False),      # skipped tests exit 0 but are not passes
])
def test_verdict_evidence_rule(rc, counts, ok):
    assert verify._verdict(rc, counts, 4) is ok


def test_hidden_with_config_file_is_grading_error(tmp_path):
    t = _task(tmp_path)
    (t.hidden / "conftest.py").write_text("")
    with pytest.raises(GradingError):
        grade(t, _ws(tmp_path, t, solved=True))


def test_hidden_without_tests_is_grading_error(tmp_path):
    t = _task(tmp_path)
    for f in t.hidden.glob("test_*.py"):
        f.unlink()
    with pytest.raises(GradingError):
        grade(t, _ws(tmp_path, t, solved=True))


def test_failing_reference_is_grading_error(tmp_path):
    t = _task(tmp_path)
    shutil.copy2(t.starter / "slug.py", t.reference / "slug.py")
    with pytest.raises(GradingError):
        grade(t, _ws(tmp_path, t, solved=True))


def test_argv_and_env_are_hardened(tmp_path, monkeypatch):
    t = _task(tmp_path)
    ws = _ws(tmp_path, t, solved=True)
    grade(t, ws)  # warm the expected-count cache with the real runner
    calls = []
    cfg_texts = []
    real = subprocess.run

    def rec(argv, **kw):
        calls.append((argv, kw))
        cfg_texts.append(Path(argv[argv.index("-c") + 1]).read_text())  # temp dir is gone after grade()
        return real(argv, **kw)

    monkeypatch.setattr(verify.subprocess, "run", rec)
    monkeypatch.setenv("PYTEST_ADDOPTS", "--collect-only")
    monkeypatch.setenv("ALLOW_SELF_MOD", "1")
    assert grade(t, ws) is True
    (argv, kw), = calls
    for flag in ("-I", "--noconftest", "--disable-plugin-autoload"):
        assert flag in argv
    assert argv[argv.index("-p") + 1] == "no:cacheprovider"
    work = kw["cwd"]
    cfg = Path(argv[argv.index("-c") + 1])
    assert work not in cfg.parents and len(cfg_texts) == 1 and cfg_texts[0].strip().splitlines()[0] == "[pytest]" and len(cfg_texts[0].strip().splitlines()) == 2 and cfg_texts[0].splitlines()[1].startswith("pythonpath = ")
    assert argv[argv.index("--rootdir") + 1] == str(work)
    junit = [a for a in argv if a.startswith("--junitxml=")][0].split("=", 1)[1]
    assert Path(work) not in Path(junit).parents
    assert argv[-1] == "test_t01_slugify.py"
    assert "PYTEST_ADDOPTS" not in kw["env"] and "ALLOW_SELF_MOD" not in kw["env"]


def test_grader_env_allowlist(tmp_path):
    hostile = {"PYTEST_ADDOPTS": "x", "PYTEST_PLUGINS": "x", "PYTHONPATH": "x", "ALLOW_SELF_MOD": "1",
               "OPENROUTER_API_KEY": "k", "HTTP_PROXY": "p", "PATH": "/bin", "HOME": "/real"}
    env = _grader_env(hostile, tmp_path / "home")
    assert env == {"PATH": "/bin", "HOME": str(tmp_path / "home")}


def test_bench_child_env_pure():
    base = {"ALLOW_SELF_MOD": "1", "CODEY_SELF_IMPROVE": "1", "OPENROUTER_API_KEY": "k", "HTTPS_PROXY": "p",
            "PYTHONPATH": "x", "PYTEST_ADDOPTS": "x", "NODE_OPTIONS": "x", "PATH": "/bin", "HOME": "/h",
            "CODEY_STATE_DIR": "/s", "CODEY_PRIMARY_PORT": "1", "CODEY_TRAJECTORY": "0"}
    env = bench_child_env(base, "t01", None)
    assert set(env) == {"PATH", "HOME", "CODEY_STATE_DIR", "CODEY_PRIMARY_PORT",
                        "CODEY_TRAJECTORY", "CODEY_TRAJECTORY_TAG"}
    assert env["CODEY_TRAJECTORY"] == "1" and env["CODEY_TRAJECTORY_TAG"] == "bench:t01"
    assert bench_child_env(base, "t01", {"OPENROUTER_API_KEY": "x"})["OPENROUTER_API_KEY"] == "x"
    for bad in ("ALLOW_SELF_MOD", "CODEY_SELF_IMPROVE"):
        with pytest.raises(ValueError):
            bench_child_env(base, "t01", {bad: "1"})
    # the deny set cannot drift from the census authority class
    assert ENV_CLASS_AUTHORITY - {"CODEY_TRAJECTORY"} <= agents._CHILD_ENV_DENY


def test_agent_closure_uses_recording_fake_only(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(agents.subprocess, "run", lambda argv, **kw: calls.append((argv, kw)))
    monkeypatch.setenv("ALLOW_SELF_MOD", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("CODEY_SELF_IMPROVE", "1")
    t = _task(tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    make_codey_cli_agent(extra_args=["--plan"])(t, ws)
    (argv, kw), = calls
    assert argv == [sys.executable, str(agents.REPO / "main.py"), t.prompt, "--yolo", "--no-resume", "--plan"]
    assert kw["stdin"] is subprocess.DEVNULL and kw["cwd"] == ws
    assert not {"ALLOW_SELF_MOD", "OPENROUTER_API_KEY", "CODEY_SELF_IMPROVE"} & set(kw["env"])
    assert kw["env"]["CODEY_TRAJECTORY"] == "1"


@pytest.mark.parametrize("args", [["--allow-self-mod"], ["--allow"], ["--allow-s"], ["--import-lora", "x"],
                                  ["--plan", "--yolo"], ["--PLAN"]])
def test_extra_args_exact_allowlist(args):
    with pytest.raises(ValueError):
        make_codey_cli_agent(extra_args=args)


def test_extra_env_authority_rejected_at_construction():
    with pytest.raises(ValueError):
        make_codey_cli_agent(extra_env={"ALLOW_SELF_MOD": "1"})


def test_workspace_root_init_py_does_not_break_correct_solution(tmp_path):
    # Regression (reviewer W1): -I removes the cwd from sys.path, and with a
    # root __init__.py pytest's prepend import mode used to put the workspace's
    # PARENT on sys.path -> ModuleNotFoundError for a correct solution.
    t = _task(tmp_path)
    ws = _ws(tmp_path, t, solved=True)
    (ws / "__init__.py").write_text("")
    assert grade(t, ws) is True
    shutil.rmtree(ws)
    ws = _ws(tmp_path, t)
    (ws / "__init__.py").write_text("")
    assert grade(t, ws) is False


def test_symlinked_hidden_dir_is_still_graded(tmp_path):
    t = _task(tmp_path)
    real = tmp_path / "real_hidden"
    t.hidden.rename(real)
    t.hidden.symlink_to(real, target_is_directory=True)
    assert grade(t, _ws(tmp_path, t, solved=True)) is True
    shutil.rmtree(tmp_path / "ws")
    assert grade(t, _ws(tmp_path, t)) is False


def test_shadow_pytest_module_forging_junit_needs_dash_I(tmp_path):
    # Behavioural pin for -I: without it the cwd is on sys.path, so a workspace
    # pytest.py would BE `python -m pytest` and could forge a perfect junit.
    t = _task(tmp_path)
    ws = _ws(tmp_path, t)
    (ws / "pytest.py").write_text(FORGE.format(n=4))
    assert grade(t, ws) is False


def test_autoloaded_entry_point_plugins_are_off(tmp_path):
    # Behavioural pin for --disable-plugin-autoload and -c, using the hidden test
    # itself as the probe. The expected-count run (reference + hidden) must also
    # pass, so under the hardened command anyio (an entry-point plugin installed
    # here) must NOT be registered; without the flag the reference run fails.
    plain = subprocess.run(
        [sys.executable, "-m", "pytest", "--trace-config", "--co", "-q", "-p", "no:cacheprovider",
         "--rootdir", str(tmp_path)], cwd=tmp_path, capture_output=True, text=True, timeout=60,
        env={"PATH": __import__("os").environ["PATH"], "HOME": str(tmp_path)})
    if "anyio" not in plain.stdout.lower():
        pytest.skip("no autoloaded entry-point plugin on this device to probe with")
    t = _task(tmp_path)
    h = next(t.hidden.glob("test_*.py"))
    h.write_text(h.read_text() + "\n\ndef test_no_autoload(pytestconfig):\n"
                 "    assert not pytestconfig.pluginmanager.has_plugin('anyio')\n")
    assert grade(t, _ws(tmp_path, t, solved=True)) is True


def test_copy_ignore_skips_pyc_links_and_special_files(tmp_path):
    import os
    d = tmp_path / "d"
    d.mkdir()
    (d / "a.py").write_text("")
    (d / "stale.pyc").write_bytes(b"x")
    (d / "dangling").symlink_to(tmp_path / "nowhere")
    (d / "loop").symlink_to(d / "loop")
    os.mkfifo(d / "fifo")
    (d / "valid_link").symlink_to(d / "a.py")  # even a working link is not followed into the grading tree
    skipped = verify._copy_ignore(str(d), os.listdir(d))
    assert skipped == {"stale.pyc", "dangling", "loop", "fifo", "valid_link"}


def test_workspace_with_dangling_link_loop_and_fifo_is_graded_not_errored(tmp_path):
    import os
    t = _task(tmp_path)
    ws = _ws(tmp_path, t, solved=True)
    (ws / "dangling").symlink_to(tmp_path / "nowhere")
    (ws / "loop").symlink_to(ws / "loop")
    os.mkfifo(ws / "fifo")
    (ws / "stale.pyc").write_bytes(b"x")
    assert grade(t, ws) is True
    shutil.rmtree(ws)
    ws = _ws(tmp_path, t)
    (ws / "loop").symlink_to(ws / "loop")
    os.mkfifo(ws / "fifo")
    assert grade(t, ws) is False


def test_symlink_cannot_redirect_hidden_overlay_write(tmp_path):
    t = _task(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    ws = _ws(tmp_path, t, solved=True)
    (ws / "test_t01_slugify.py").symlink_to(victim)
    assert grade(t, ws) is True
    assert victim.read_text() == "keep"


def test_extra_args_copied_at_construction(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(agents.subprocess, "run", lambda argv, **kw: calls.append(argv))
    args = ["--plan"]
    agent = make_codey_cli_agent(extra_args=args)
    args.append("--allow-self-mod")
    t = _task(tmp_path)
    agent(t, tmp_path)
    assert calls[0][-1] == "--plan" and "--allow-self-mod" not in calls[0]


def test_child_env_keeps_git_identity_names_drops_credentials():
    base = {"USER": "u", "LOGNAME": "u", "EMAIL": "e", "GIT_AUTHOR_NAME": "n", "SHELL": "/s", "SSL_CERT_FILE": "f",
            "XDG_CONFIG_HOME": "/x", "OPENROUTER_API_KEY": "k", "UNLIMITEDCLAUDE_API_KEY": "k",
            "GOOGLE_APPLICATION_CREDENTIALS": "g", "NODE_OPTIONS": "n"}
    env = bench_child_env(base, "t", None)
    assert {"USER", "LOGNAME", "EMAIL", "GIT_AUTHOR_NAME", "SHELL", "SSL_CERT_FILE", "XDG_CONFIG_HOME"} <= set(env)
    assert not {"OPENROUTER_API_KEY", "UNLIMITEDCLAUDE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "NODE_OPTIONS"} & set(env)
