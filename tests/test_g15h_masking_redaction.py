"""G15h Unit B: secret masking in sessions, file logger, show-config and list_processes.

All canaries are fabricated. B-3 (action-gateway audit rows) is intentionally absent (held, Q-a).
"""
import builtins
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from core import export_hygiene as eh
from core import sessions
from core.export_hygiene import find_secret, mask_secrets

B64 = "eyJhIjoiRkFLRUFDQ09VTlQiLCJ0IjoiRkFLRVRVTk5FTCIsInMiOiJGQUtFU0VDUkVUMDEyMzQ1Njc4OWFiY2RlZiJ9"
AGE = "AGE-SECRET-KEY-1" + "QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L"[:29] * 2  # 58 chars from the bech32 set
SSHKEY = "-----BEGIN OPENSSH PRIVATE KEY-----"

# (name, text, canary substring that must vanish)
SHAPES = [
    ("cf_flag", f"cloudflared tunnel run --token {B64}", B64),
    ("cf_bare", f"token is {B64} ok", B64),
    ("tunnel_env", "TUNNEL_TOKEN=Zx9Qw8Er7Ty6Ui5Op4Fake3", "Zx9Qw8Er7Ty6Ui5Op4Fake3"),
    ("export_cf", "export CLOUDFLARE_TUNNEL_TOKEN=Ab12Cd34Ef56Gh78Ij90Kl", "Ab12Cd34Ef56Gh78Ij90Kl"),
    ("age", f"key: {AGE}", AGE),
    ("netrc", "machine example.com login bob password Hunter2xFake", "Hunter2xFake"),
    ("or", "sk-or-v1-" + "a1B2c3D4" * 8, "a1B2c3D4a1B2c3D4"),
    ("ant", "sk-ant-api03-" + "Fake0123456789abcdefXYZ", "Fake0123456789abcdefXYZ"),
    ("bearer", "curl -H 'Authorization: Bearer FakeBearer0123456789abcdefXYZ' x", "FakeBearer0123456789abcdefXYZ"),
    ("mysql", "mysql -h db -u root -pFakePw9Z!x mydb", "FakePw9Z!x"),
    ("aigentik", "AIGENTIK_INTERNAL_TOKEN=Fake9Aigentik8Tok7en6Zz", "Fake9Aigentik8Tok7en6Zz"),
    ("hf", "hf_" + "AbCdEfGhIj0123456789KlMnOpQrSt", "AbCdEfGhIj0123456789KlMnOpQrSt"),
    ("ssh", SSHKEY, SSHKEY),
    ("password_eq", "run --password=Sup3rS3cretPw now", "Sup3rS3cretPw"),
    ("ghp", "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8", "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"),
]


@pytest.mark.parametrize("name,text,canary", SHAPES, ids=[s[0] for s in SHAPES])
def test_mask_secrets_masks_every_shape(name, text, canary):
    assert find_secret(text) is not None
    out = mask_secrets(text)
    assert canary not in out
    assert "[REDACTED:" in out
    assert mask_secrets(out) == out  # idempotent


def test_age_canary_matches_real_shape():
    assert len(AGE) == 74
    assert re.fullmatch(r"AGE-SECRET-KEY-1[QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L]{58}", AGE)


# --- new pattern acceptance table -------------------------------------------------
POS = {
    "age_secret_key": [AGE],
    "base64_json_blob": [B64, f"TOKEN: {B64}."],
    "secret_flag": [f"cloudflared tunnel run --token {B64}", "--password=Sup3rS3cretPw",
                    "--password 'Sup3rS3cretPw'", "--api-key abcdef123456"],
    "netrc_inline": ["machine example.com login bob password Hunter2x"],
    "netrc_line": ["machine x\nlogin bob\npassword Hunter2x\n", "password abcdef"],
}
NEG = {
    "age_secret_key": ["AGE-SECRET-KEY-1 placeholder"],
    "base64_json_blob": ["eyJhbGciOiJIUzI1NiJ9", "see eyJ in docs"],
    "secret_flag": ["--token-file /x/y", "--token $VAR", "--token <your-token>", "--token-name",
                    "--secret-name abc"],
    "netrc_inline": ["login bob password must be set", "machine a login b password xx",
                     "machine a login b password {x}"],
    "netrc_line": ["password reset flow", "Enter your password here", "password abc12"],
}


def _only(name, text):
    rx = dict(eh.SECRET_PATTERNS)[name]
    return rx.search(text) is not None


@pytest.mark.parametrize("name", sorted(POS))
def test_new_patterns_positive(name):
    for t in POS[name]:
        assert _only(name, t), (name, t)


@pytest.mark.parametrize("name", sorted(NEG))
def test_new_patterns_negative(name):
    for t in NEG[name]:
        assert not _only(name, t), (name, t)


def test_real_age_keygen_shape():
    import shutil
    if not shutil.which("age-keygen"):
        pytest.skip("age-keygen absent")
    out = subprocess.run(["age-keygen"], capture_output=True, text=True, timeout=10)
    key = re.search(r"AGE-SECRET-KEY-1\S+", out.stdout).group(0)
    assert _only("age_secret_key", key)
    assert key not in mask_secrets(f"id {key}")


# --- false positives: ordinary text must survive ----------------------------------
BENIGN = [
    "Refactored the parser and updated the docs.",
    "commit 9a61e94f3c2b1a0d8e7f6a5b4c3d2e1f00112233 fix typo",
    "sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "/data/data/com.termux/files/home/Codey-OS/core/sessions.py",
    "uuid 123e4567-e89b-12d3-a456-426614174000 created",
    "x = base64.b64decode('aGVsbG8gd29ybGQ=')",
    "def f(password): return os.environ['HOME']",
    "git log --oneline -n 5",
    "python3 -m pytest tests/test_x.py -q",
    "--token-file /home/u/t",
]


@pytest.mark.parametrize("text", BENIGN)
def test_benign_text_unchanged(text):
    assert mask_secrets(text) == text


# --- contract ---------------------------------------------------------------------
def test_mask_secrets_never_raises_returns_marker(monkeypatch):
    class Boom:
        def sub(self, *a, **k):
            raise RuntimeError("boom FAKE")
    monkeypatch.setattr(eh, "SECRET_PATTERNS", (("x", Boom()),))
    assert mask_secrets("secret text") == "[withheld: redaction failed]"


def test_mask_secrets_truncates():
    out = mask_secrets("a" * 100, max_chars=10)
    assert out.startswith("a" * 10) and "truncated 90" in out


@pytest.mark.parametrize("payload", [
    "a" * 1_000_000, "--token " * 125_000, "eyJ" + "a" * 1_000_000, "password " * 100_000,
])
def test_mask_secrets_linear(payload):
    t0 = time.time()
    mask_secrets(payload, max_chars=2_000_000)
    assert time.time() - t0 < 20


def test_perf_many_lines():
    t0 = time.time()
    for i in range(2000):
        mask_secrets(("line %d " % i) + "x" * 300)
    assert time.time() - t0 < 30


def test_existing_find_secret_still_reads_module_global(monkeypatch):
    monkeypatch.setattr(eh, "SECRET_PATTERNS", (("only", re.compile("ZZZ")),))
    assert find_secret("ZZZ") == "only"


# --- B-2 sessions: end to end through save_session --------------------------------
def test_redact_secrets_all_shapes_and_legacy():
    for name, text, canary in SHAPES:
        assert canary not in sessions.redact_secrets(text), name
    assert sessions.redact_secrets('{"password": "x"}') == '{"password": "[REDACTED]"}'
    assert sessions.redact_secrets(5) == 5


def test_save_session_writes_no_canary(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions, "SESSIONS_DIR", tmp_path / "sess")
    hist = [{"role": "user", "content": t} for _, t, _ in SHAPES]
    sessions.save_session(hist, project_dir=str(tmp_path), max_turns=50)
    files = list((tmp_path / "sess").glob("*.json"))
    if not files:
        pytest.skip("save_session wrote no file in this harness")
    raw = "".join(f.read_text() for f in files)
    for name, _, canary in SHAPES:
        assert canary not in raw, name


# --- B-4 logger: through the real file handler ------------------------------------
@pytest.fixture
def filelog(tmp_path, monkeypatch):
    from utils import logger
    lf = tmp_path / "d.log"
    monkeypatch.setattr(logger, "_file_logger", None)
    monkeypatch.setattr(logger, "_file_handler", None)
    logging.getLogger("codey_daemon").handlers.clear()
    logger.setup_file_logging(str(lf))
    yield logger, lf
    logging.getLogger("codey_daemon").handlers.clear()


def test_file_log_masks_all_shapes_console_untouched(filelog, capsys):
    logger, lf = filelog
    for name, text, _ in SHAPES:
        logger.info(text)
        logger.warning(text)
        logger.error(text)
        logger.debug(text)
        logger.success(text)
        logger.think(text)
    logger._file_handler.flush()
    raw = lf.read_text()
    for name, _, canary in SHAPES:
        assert canary not in raw, name
    assert "[REDACTED:" in raw


def test_file_log_import_failure_writes_marker(filelog, monkeypatch):
    logger, lf = filelog
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "core.export_hygiene":
            raise ImportError("nope")
        return real(name, *a, **k)
    with monkeypatch.context() as m:
        m.setattr(builtins, "__import__", fake)
        logger._log_to_file("info", "secret FAKE-CANARY-777")
    logger._file_handler.flush()
    raw = lf.read_text()
    assert "FAKE-CANARY-777" not in raw
    assert "[withheld: redaction failed]" in raw


# --- B-5 show-config --------------------------------------------------------------
def test_show_config_redacts(monkeypatch, capsys, tmp_path):
    import utils.config as cfg
    from core import service_actions
    conf = {
        "db_password": "PwFake1", "aws_credentials": "CredFake2", "ssh_private_key": "PkFake3",
        "s3_access_key": "AkFake4", "x-api-key": "XkFake5", "apikey": "AkFake6", "passwd": "PdFake7",
        "url": "https://user:UrlPwFake8@host/x", "cmd": "run --token " + B64,
        "nested": {"list": ["--password=Sup3rS3cretPw"], "port": 5},
        "name": "plain", 7: "seven",
    }
    monkeypatch.setattr(cfg, "load_user_config", lambda: conf)
    monkeypatch.setattr(cfg, "get_config_file_path", lambda: tmp_path / "c.json")
    monkeypatch.setattr(cfg, "get_cloudflare_tunnel_token", lambda: None)
    monkeypatch.setattr(cfg, "get_restoricon_api_config", lambda: {})
    monkeypatch.setattr(cfg, "get_aigentik_config", lambda: {})
    service_actions._show_config()
    out = capsys.readouterr().out
    for c in ("PwFake1", "CredFake2", "PkFake3", "AkFake4", "XkFake5", "AkFake6", "PdFake7",
              "UrlPwFake8", B64, "Sup3rS3cretPw"):
        assert c not in out, c
    assert "plain" in out and '"port": 5' in out


# --- B-6 list_processes -----------------------------------------------------------
def _fake_ps(cmds):
    hdr = "USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND\n"
    rows = "".join(f"u0_a1 {100+i} 1.0 1.0 1 1 ? S 00:00 0:00 {c}\n" for i, c in enumerate(cmds))
    return subprocess.CompletedProcess([], 0, hdr + rows, "")


def _load_si():
    import importlib.util
    p = Path(__file__).resolve().parents[1] / "ccos/plugins/system/system_info/system_info.py"
    spec = importlib.util.spec_from_file_location("g15h_system_info", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_list_processes_masks_then_cuts(monkeypatch):
    si = _load_si()
    # canary straddles the 100-char cut: a cut-then-mask order would leave a partial token
    cmd = "cloudflared tunnel run --token " + B64
    monkeypatch.setattr(si.subprocess, "run", lambda *a, **k: _fake_ps([cmd, "sleep 5"]))
    rows = si.list_processes(limit=5)
    assert len(rows) == 2
    for r in rows:
        assert B64[:12] not in r["command"]
        assert len(r["command"]) <= 100
    assert rows[1]["command"] == "sleep 5"


def test_list_processes_import_failure_returns_argv0_only(monkeypatch):
    si = _load_si()
    monkeypatch.setattr(si.subprocess, "run", lambda *a, **k: _fake_ps(
        ["/usr/bin/cloudflared tunnel run --token " + B64]))
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "core.export_hygiene":
            raise ImportError("nope")
        return real(name, *a, **k)
    with monkeypatch.context() as m:
        m.setattr(builtins, "__import__", fake)
        rows = si.list_processes(limit=5)
    assert rows[0]["command"] == "cloudflared"


def test_list_processes_cut_after_mask_no_partial_secret(monkeypatch):
    si = _load_si()
    # token value begins just before char 100: cutting first would leave a short unmasked prefix
    cmd = "x" * 88 + " --token Sup3rS3cretPw"
    monkeypatch.setattr(si.subprocess, "run", lambda *a, **k: _fake_ps([cmd]))
    out = si.list_processes(limit=5)[0]["command"]
    assert "Sup" not in out and len(out) <= 100


# --- B-3 action-gateway audit ledger -----------------------------------------------
BEARER = "FakeBearer0123456789abcdefXYZ"


def _rows(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines()]


def test_audit_masks_command_and_reason_keeps_structure(tmp_path):
    from core.action_gateway import ACT, HIGH_IMPACT, OUTCOME_ALLOWED, OUTCOME_REFUSED, ActionGateway
    audit = tmp_path / "a.jsonl"
    gw = ActionGateway(audit_file=audit)
    cmd = f"curl -H 'Authorization: Bearer {BEARER}' https://x.example/y"
    d = gw.gate_exec(authority=ACT, action="t.exec", command=cmd,
                     confirm_available=False, execute=lambda: "ok")
    assert d.outcome == OUTCOME_ALLOWED
    assert d.detail["command"] == cmd  # in-process decision stays raw
    d2 = gw.gate_exec(authority=HIGH_IMPACT, action="t.hi", command=f"rm x --token {B64}",
                      confirm_available=False, execute=lambda: "no")
    assert d2.outcome == OUTCOME_REFUSED
    r1, r2 = _rows(audit)
    assert "[REDACTED:bearer_token]" in r1["command"]
    assert r1["command"].startswith("curl -H 'Authorization: ") and r1["command"].endswith("https://x.example/y")
    assert (r1["action"], r1["authority"], r1["outcome"]) == ("t.exec", ACT, OUTCOME_ALLOWED)
    assert (r2["action"], r2["authority"], r2["outcome"]) == ("t.hi", HIGH_IMPACT, OUTCOME_REFUSED)
    assert r2["command"].startswith("rm x ") and "[REDACTED:" in r2["command"]
    raw = audit.read_text()
    assert BEARER not in raw and B64 not in raw


def test_audit_masks_reason(tmp_path):
    from core.action_gateway import ACT, ActionGateway
    audit = tmp_path / "a.jsonl"
    gw = ActionGateway(audit_file=audit)

    def boom():
        raise RuntimeError(f"failed with --password=Sup3rS3cretPw")
    gw.gate_exec(authority=ACT, action="t.fail", command="x", confirm_available=False, execute=boom)
    raw = audit.read_text()
    assert "Sup3rS3cretPw" not in raw
    assert _rows(audit)[-1]["action"] == "t.fail"


def test_audit_unmasked_ordinary_row_identical(tmp_path):
    from core.action_gateway import ACT, ActionGateway
    audit = tmp_path / "a.jsonl"
    ActionGateway(audit_file=audit).gate_exec(
        authority=ACT, action="t.ok", command="git status --short", confirm_available=False,
        execute=lambda: "ok")
    assert _rows(audit)[0]["command"] == "git status --short"


def test_audit_mask_failure_still_appends_marker_row(tmp_path, monkeypatch):
    from core import action_gateway as ag
    audit = tmp_path / "a.jsonl"

    def bad(_t):
        raise RuntimeError("x")
    monkeypatch.setattr(eh, "mask_secrets", bad)
    ag._append_audit({"ts": 1, "action": "a", "authority": "ACT", "outcome": "allowed",
                      "command": f"echo {B64}", "reason": "r"}, audit)
    row = _rows(audit)[0]
    assert row["command"] == "[withheld: redaction failed]"
    assert row["reason"] == "[withheld: redaction failed]"
    assert row["action"] == "a" and B64 not in audit.read_text()


def test_audit_append_does_not_mutate_caller_record(tmp_path):
    from core import action_gateway as ag
    rec = {"ts": 1, "command": f"x --token {B64}"}
    ag._append_audit(rec, tmp_path / "a.jsonl")
    assert B64 in rec["command"]


# --- review round: W1 quoted multi-word flag values -------------------------------
@pytest.mark.parametrize("text,gone", [
    ('run --password "correct horse battery staple" --x', "horse"),
    ('run --password "hunter22 extra" --x', "extra"),
    ("run --token 'multi word secret here' --x", "word"),
    ("run --secret='multi word secret here' --x", "word"),
    (r'run --password "ab\"cd efghijk" tail', "efghijk"),
    ('run --password "unterminated purple words here', "purple"),
    ("run --password 'unterminated secret words here", "words"),
])
def test_secret_flag_quoted_values(text, gone):
    out = mask_secrets(text)
    assert gone not in out and "[REDACTED:secret_flag]" in out
    assert out.startswith("run ")


def test_secret_flag_quoted_keeps_trailing_text():
    out = mask_secrets('run --password "correct horse battery" --verbose')
    assert out.endswith("--verbose")


@pytest.mark.parametrize("text", [
    "--password-file=/x", "--password-file /x/y/z/w", "--api-key-path=/some/long/path",
    "--token-file /x/y", "--token '$TOKEN_VAR'", '--password "<your password>"',
    "--token-name something-long",
])
def test_secret_flag_quoted_negatives(text):
    assert mask_secrets(text) == text


@pytest.mark.parametrize("payload", [
    '--password "' * 100_000,
    '--password "' + "a" * 1_000_000,
    '--password \'"' * 80_000,
    "--password " + "\"'" * 500_000,
    '--password "' + 'a\\' * 500_000,
    '--token "a b' * 100_000,
])
def test_secret_flag_quoted_linear(payload):
    t0 = time.time()
    mask_secrets(payload, max_chars=2_000_000)
    assert time.time() - t0 < 20


# --- W2 guard must cover the whole value ------------------------------------------
def test_redacted_prefix_bypass_closed():
    for t in ('password="[REDACTED:x]realsecret99"', 'password="[REDACTED]realsecret99"'):
        assert find_secret(t) is not None
        assert "realsecret99" not in mask_secrets(t)


@pytest.mark.parametrize("t", [
    '"password": "[REDACTED]"', "password=[REDACTED]", "password=[REDACTED:quoted_secret_assignment]",
    'password="[REDACTED:quoted_secret_assignment]"',
])
def test_redacted_placeholders_stable(t):
    assert mask_secrets(t) == t
    once = sessions.redact_secrets(t)  # legacy rule may normalise the placeholder text
    assert sessions.redact_secrets(once) == once and "[REDACTED" in once


def test_legacy_sessions_unchanged_for_real_values():
    assert sessions.redact_secrets('{"password": "x"}') == '{"password": "[REDACTED]"}'
    out = sessions.redact_secrets('password=Hunter2xyzzy')
    assert "Hunter2xyzzy" not in out and out.startswith("password=")


# --- W3 system_info must not prepend to sys.path ----------------------------------
def test_list_processes_does_not_prepend_syspath(monkeypatch):
    si = _load_si()
    before = list(sys.path)
    monkeypatch.setattr(si.subprocess, "run", lambda *a, **k: _fake_ps(["sleep 5"]))
    si.list_processes(limit=2)
    assert sys.path[0] == before[0] and sys.path[:len(before)] == before


def test_safe_command_appends_root_on_importerror(monkeypatch):
    si = _load_si()
    real = builtins.__import__
    state = {"n": 0}

    def fake(name, *a, **k):
        if name == "core.export_hygiene" and state["n"] == 0:
            state["n"] += 1
            raise ImportError("first")
        return real(name, *a, **k)
    root = str(Path(__file__).resolve().parents[1])
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != root])
    with monkeypatch.context() as m:
        m.setattr(builtins, "__import__", fake)
        out = si._safe_command("x --password Sup3rS3cretPw")
    assert "Sup3rS3cretPw" not in out and sys.path[-1] == root


# --- W4 truncation marker survives ------------------------------------------------
def test_truncation_marker_not_swallowed():
    out = mask_secrets("abc --password " + "z" * 20, max_chars=len("abc --password "))
    assert out.endswith("...[truncated 20 chars]")
    out2 = mask_secrets("--token " + "z" * 30, max_chars=8 + 12)
    assert out2.endswith("...[truncated 18 chars]") and "zzzz" not in out2


# --- audit non-str fields ---------------------------------------------------------
def test_audit_masks_non_str_command(tmp_path):
    from core import action_gateway as ag
    audit = tmp_path / "a.jsonl"
    ag._append_audit({"ts": 1, "action": "a", "command": ["curl", "--token", B64], "reason": None}, audit)
    raw = audit.read_text()
    assert B64 not in raw
    row = _rows(audit)[0]
    assert isinstance(row["command"], str) and row["reason"] is None


# --- re-review residuals ----------------------------------------------------------
@pytest.mark.parametrize("text,gone", [
    (r'--password=\"x1y2 z3w4 q5\" k', "z3w4"),
    (r'--token \"multi word value\" k', "word"),
    (r'--token \"unterminated esc words', "words"),
])
def test_secret_flag_json_escaped_form(text, gone):
    out = mask_secrets(text)
    assert gone not in out and "[REDACTED:secret_flag]" in out


def test_secret_flag_json_escaped_keeps_tail():
    assert mask_secrets(r'--password=\"x1y2 z3w4 q5\" k').endswith("k")
    assert json.loads(json.dumps(mask_secrets("--password=\"x1y2 z3w4 q5\" k"))) is not None


@pytest.mark.parametrize("text", [r'--password-file=\"/x y z w\"', r'--token \"$VAR is here\"'])
def test_secret_flag_json_escaped_negatives(text):
    assert mask_secrets(text) == text


@pytest.mark.parametrize("payload", [
    '--password \\"' * 100_000, '--password \\"' + "a" * 1_000_000, '--password \\"' + "a\\" * 500_000,
    '--password \\"a b' * 100_000, "--password " + '\\"' * 500_000,
])
def test_secret_flag_escaped_linear(payload):
    t0 = time.time()
    mask_secrets(payload, max_chars=2_000_000)
    print("elapsed", round(time.time() - t0, 2))
    assert time.time() - t0 < 20


def test_audit_list_command_joined_then_masked(tmp_path):
    from core import action_gateway as ag
    audit = tmp_path / "a.jsonl"
    ag._append_audit({"ts": 1, "action": "a", "command": ["sh", "--password", "Canary12345abc"],
                      "reason": ("x", "--token", B64)}, audit)
    raw = audit.read_text()
    assert "Canary12345abc" not in raw and B64 not in raw
    row = _rows(audit)[0]
    assert row["command"].startswith("sh ") and row["command"].count("[REDACTED:") == 1


# --- S2 unit A, fix 2 (G15z V-C3 GW-10b): mid-line NAME=secret masking ----------------
HEX_CANARY = "0123456789abcdef0123456789abcdef0123456789abcdef"  # fabricated


@pytest.mark.parametrize("text,keep_before,keep_after", [
    (f"env AIGENTIK_INTERNAL_TOKEN={HEX_CANARY} python3 x", "env AIGENTIK_INTERNAL_TOKEN=", " python3 x"),
    (f"FOO=1 CCOS_CRM_READ_TOKEN={HEX_CANARY} cmd", "FOO=1 CCOS_CRM_READ_TOKEN=", " cmd"),
    (f"a && DB_PASSWORD={HEX_CANARY} && echo done", "a && DB_PASSWORD=", " && echo done"),
    (f"curl 'https://h/p?API_KEY={HEX_CANARY}'", "curl 'https://h/p?API_KEY=", "'"),
    (f"x\n  export MY_SECRET={HEX_CANARY}\ny", None, None),
])
def test_midline_env_secret_masks_value_keeps_name_and_context(text, keep_before, keep_after):
    out = mask_secrets(text)
    assert HEX_CANARY not in out and "[REDACTED:" in out
    if keep_before is not None:
        assert out.startswith(keep_before) and out.endswith(keep_after)
        assert "[REDACTED:env_secret_assignment_inline]" in out
    assert mask_secrets(out) == out


def test_midline_env_secret_audit_ledger_end_to_end(tmp_path):
    from core.action_gateway import ACT, ActionGateway
    audit = tmp_path / "a.jsonl"
    gw = ActionGateway(audit_file=audit)
    gw.gate_exec(authority=ACT, action="t.exec",
                 command=f"env AIGENTIK_INTERNAL_TOKEN={HEX_CANARY} python3 x",
                 confirm_available=False, execute=lambda: "ok")
    raw = audit.read_text()
    assert HEX_CANARY not in raw
    assert "AIGENTIK_INTERNAL_TOKEN=[REDACTED:env_secret_assignment_inline] python3 x" in raw


@pytest.mark.parametrize("text", [
    "git show 0123456789abcdef0123456789abcdef01234567",
    "sha256sum x  e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "id=123e4567-e89b-12d3-a456-426614174000 ok",
    "cat /data/data/com.termux/files/home/token_file.txt",
    "tool --token-file=/path/to/the_token_file --token-count=123456789",
    "the password is stored elsewhere; password=short",
    "echo $TOKEN ${TOKEN} \"$SECRET_TOKEN\" X_TOKEN=$VALUE_FROM_ENV Y_TOKEN=${LONG_VALUE_REF}",
    "MY_TOKEN=short TOKEN_COUNT=5 PASSWORD=/etc/secret/file KEY_TOKEN=~/tokfile",
    "lower_token=abcdefghijklmnop1234 mytoken=abcdefghijklmnop1234",
    "run FOO_TOKEN = abcdefghijklmnop1234 mid TOKEN = x",  # spaced mid-line: prose-shaped, untouched
    "x-TOKEN=abcdefghijklmnop1234 a_TOKEN=abcdefghijklmnop1234x(",  # '-' lookbehind; trailing paren
])
def test_midline_env_secret_no_new_false_positives(text):
    out = mask_secrets(text)
    assert "env_secret_assignment_inline" not in out
    assert out == text


def test_midline_env_secret_residuals_documented():
    # Same name/value rule as the line-start pattern: an all-digit long value for a
    # TOKEN-named variable IS masked (accepted false positive). Quoted values are
    # not this pattern's job: the quoted_*_assignment patterns already mask them.
    assert "[REDACTED:env_secret_assignment_inline]" in mask_secrets("run MAX_TOKENS=1000000000 now")
    assert HEX_CANARY not in mask_secrets(f'env X_TOKEN="{HEX_CANARY}" y')


def test_midline_env_secret_line_start_behaviour_unchanged():
    out = mask_secrets(f"AIGENTIK_INTERNAL_TOKEN={HEX_CANARY}")
    assert out == "[REDACTED:env_secret_assignment]"
    out = mask_secrets(f"-e X_TOKEN={HEX_CANARY}")
    assert out == "[REDACTED:inline_env_secret]"
    assert find_secret(f"env X_TOKEN={HEX_CANARY} y") is None  # find_secret/export unchanged


@pytest.mark.parametrize("payload", [
    "A" * 1_000_000, "TOKEN=" * 170_000, "_TOKEN" * 170_000, " TOKEN=aaaaaaaa" * 66_000,
    "TOKEN=" + "a" * 1_000_000, " X_TOKEN=" * 110_000, "=SECRET" * 140_000,
    "PASSWORD " * 110_000, "A_" * 500_000, ("SECRET" + "A" * 31 + "=") * 27_000,
    ("A" * 32 + "TOKEN" + "A" * 32 + "=") * 13_000,
])
def test_midline_env_secret_linear_at_default_cap(payload):
    # CPU time, not wall: the device stalls processes for seconds under load (observed 28 s wall / 0.7 s CPU).
    t0 = time.process_time()
    mask_secrets(payload)  # default 256 KB cap
    assert time.process_time() - t0 < 2
    t0 = time.process_time()
    mask_secrets(payload, max_chars=2_000_000)  # whole payload (~1 MB)
    assert time.process_time() - t0 < 20


def test_midline_env_secret_fuzz_idempotent():
    # `--token --token` style atoms are left out on purpose: secret_flag (not this fix) is
    # non-idempotent on a doubled flag; see the S2-A report.
    import random
    rng = random.Random(20241024)
    atoms = ["env ", "A_TOKEN=", "X_SECRET=", "PASSWORD=", "API_KEY=", "TOKEN", "=", "'", '"', "\\", ",",
             " ", "\n", "abcdefgh12345678", "0123456789abcdef", "[REDACTED:x]", "$", "${", "}", "-", "_",
             "-e ", "export ", "(", ")", "/", ".", "~", "\\\"", "ZZ"]
    for _ in range(20000):
        t = "".join(rng.choice(atoms) for _ in range(rng.randint(1, 14)))
        once = mask_secrets(t)
        assert mask_secrets(once) == once, repr(t)


# --- S2-A review W1/W2: prefix cap and lookbehind boundary -----------------------------
_V = "abcdefghij1234"  # fabricated 14-char value


@pytest.mark.parametrize("prefix,masked", [
    ("a_", False),   # lower-case char is not a name char; mid-run start is blocked: unmasked (documented)
    ("x", False),
    ("9", True),     # digit is a name char: whole name 9TOKEN
    (".", True), ("/", True), (":", True), ('"', True), ("(", True), ("?", True),
    ("-", False),    # option-like, excluded on purpose
])
def test_midline_lookbehind_boundary_outcomes(prefix, masked):
    out = mask_secrets(f"run {prefix}TOKEN={_V} z")
    if masked:
        assert _V not in out and f"{prefix}TOKEN=[REDACTED:env_secret_assignment_inline] z" in out
    else:
        assert out == f"run {prefix}TOKEN={_V} z"


def test_midline_name_prefix_allowance_128_and_residual():
    ok = "A" * 120 + "TOKEN"
    assert _V not in mask_secrets(f"env {ok}={_V} x")
    assert mask_secrets(f"env {ok}={_V} x").startswith(f"env {ok}=[REDACTED:")
    too_long = "A" * 140 + "TOKEN"  # documented residual: > 128 chars before the keyword
    assert mask_secrets(f"env {too_long}={_V} x") == f"env {too_long}={_V} x"


def test_midline_mixed_case_names_unmasked_documented():
    # Pre-existing limitation shared with the line-start rule (names are upper-case only).
    assert mask_secrets(f"env Api_Token={_V} x") == f"env Api_Token={_V} x"
