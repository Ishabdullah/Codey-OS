"""Export hygiene: secrets/truncation/duplicates dropped at export_dataset (never redacted)."""
import json
import os
import sqlite3
import time

import pytest

from core import export_hygiene as eh
from core import trajectory as tj
from core.export_hygiene import find_secret, sanitize_examples
from core.finetune_prep import DatasetCurator, export_dataset


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setenv("CODEY_TRAJECTORY_DB", str(p))
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")
    return p


def _lines(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f.read().splitlines() if l]


def _agent_with(content, result, prompt="write it", final="Done."):
    def agent(msg, history, yolo=False):
        tj.instrument_execute_tool(lambda d: result)({"name": "write_file", "args": {"path": "f.py", "content": content}})
        return final, history
    return tj.instrument_run_agent(agent)(prompt, [])


def _clean_episode(prompt="clean task"):
    def agent(msg, history, yolo=False):
        tj.instrument_execute_tool(lambda d: "file contents")({"name": "read_file", "args": {"path": "a.py"}})
        return "Done.", history
    tj.instrument_run_agent(agent)(prompt, [])



def test_large_write_file_roundtrip_intact(db, tmp_path):
    content = "".join(f'def f{i}(x):\n    return "q\\"{i}" + \'é\\t\'\n' for i in range(300))
    assert len(content) > 8192
    _agent_with(content, "Done.")
    tj.label_episode(1, "pytest", True)
    con = sqlite3.connect(db)
    assert len(con.execute("select args from tool_calls").fetchone()[0]) > 8192
    ex = DatasetCurator.__new__(DatasetCurator).curate_verified()
    out, n = export_dataset(ex, str(tmp_path / "out"), "4b")
    rows = _lines(out)
    assert n == 1 and len(rows) == 1
    body = rows[0]["conversations"][2]["content"]
    body = body[len("<tool>\n"):-len("\n</tool>")]
    assert json.loads(body)["args"]["content"] == content


def _raw_episode(con, ts, args, result, final, passed=1):
    cur = con.execute("INSERT INTO episodes(ts,tag,prompt,final,n_tools,secs,crashed,verifier,passed) "
                      "VALUES(?,?,?,?,?,?,?,?,?)", (ts, "", "p", final, 1, 0.0, 0, "pytest", passed))
    con.execute("INSERT INTO tool_calls VALUES(?,?,?,?,?,?,?)", (cur.lastrowid, 0, "write_file", args, result, 0, 0.0))


def test_legacy_truncated_rows_excluded(db, tmp_path, monkeypatch):
    import core.finetune_prep as fp
    msgs = []
    monkeypatch.setattr(fp, "info", lambda m: msgs.append(m))
    con = tj._connect(db)
    _raw_episode(con, 1.0, '{"path": "a"}', "abc...[truncated]", "ok")
    _raw_episode(con, 2.0, '{"path": "a...[truncated]', "fine", "ok")
    _raw_episode(con, 3.0, '{"path": "a"}', "fine", "ok")
    _raw_episode(con, 4.0, '{"path": "a"}', "fine", "z...[truncated]")
    con.commit()
    con.close()
    ex = DatasetCurator.__new__(DatasetCurator).curate_verified()
    assert len(ex) == 1 and ex[0]["metadata"]["episode_id"] == 3
    assert any("skipped 3" in m for m in msgs)
    out, n = export_dataset(ex, str(tmp_path / "out"), "4b")
    rows = _lines(out)
    assert len(rows) == 1 and rows[0]["metadata"]["episode_id"] == 3


def test_midtext_truncated_literal_is_exported(db, tmp_path):
    _agent_with("c", "r", prompt="intro\n...[truncated]\nrest of the prompt")
    tj.label_episode(1, "pytest", True)
    ex = DatasetCurator.__new__(DatasetCurator).curate_verified()
    out, n = export_dataset(ex, str(tmp_path / "out"), "4b")
    assert n == 1 and "...[truncated]" in open(out, encoding="utf-8").read()


def test_oversize_marker_excluded(db, tmp_path):
    con = tj._connect(db)
    _raw_episode(con, 1.0, '{"path": "a"}', "[[codey-trajectory:omitted-oversize chars=2000000]]", "ok")
    con.commit()
    con.close()
    ex = DatasetCurator.__new__(DatasetCurator).curate_verified()
    _, stats = sanitize_examples(ex)
    assert stats["truncated"] == 1
    out, n = export_dataset(ex, str(tmp_path / "out"), "4b")
    assert n == 0 and _lines(out) == []


_OR_KEY = "sk-" + "or-v1-" + "0123456789abcdef" * 4
POSITIVES = [
    _OR_KEY,
    '{"openrouter": {"key": "' + _OR_KEY + '"}}',
    "OPENROUTER_KEY: " + _OR_KEY,
    'cfg["openrouter_key"] = "' + _OR_KEY + '"',
    "sk-" + "0123456789abcdef" * 3,
    "  password: correcthorsebatterystaple",
    "api_key: " + "qwertyuiopasdfghjklzxcvbnmqwerty",
    "mysqldump mydb -u root -pS3cretPass1",
    "mysql app_db -pS3cretPass1",
    "mysql -h db.example.com -P 3306 -u app -pS3cretPass1 app",
    "mysqldump -h db -P 3306 -u root -pS3cretPass1 --single-transaction mydb",
    "mysql -h 127.0.0.1 -P 3306 -u root -pS3cretPass1 -e 'show databases'",
    "token: " + "ab12" * 8,
    "docker run -e POSTGRES_PASSWORD=S3cretPass1 postgres",
    "mysql --password=S3cretPass1",
    "MYSQL_PWD=S3cretPass1",
    "curl -H 'x-api-key: " + "ab12" * 8 + "' http://x",
    'curl -H "X-API-Key: ' + "ab12" * 8 + '" http://x',
    "X-Auth-Token: " + "cd34" * 8,
    "AKIA" + "A" * 16,
    "aws_secret_access_key = " + "a1B2" * 10,
    "AIza" + "a" * 35,
    "ya29." + "b" * 30,
    "sk-proj-" + "c" * 40,
    "sk-ant-api03-" + "d" * 40,
    "hf_" + "e" * 34,
    "ghp_" + "g" * 36,
    "github_pat_" + "h" * 40,
    "Authorization: Bearer " + "i" * 32,
    "-----BEGIN RSA " + "PRIVATE KEY-----",
    "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
    'password = "hunter2hunter2"',
    '{"password": "s3cretValue!"}',
    "x=1\nDB_PASSWORD=supersecret123\n",
    "postgres://admin:pw12345678@db:5432/x",
    "xoxb-" + "1" * 20,
    "Authorization: Basic dXNlcjpwYXNzd29yZDEyMw==",
    'api_key: "abcd1234efgh"',
    "export OPENAI_API_KEY=abc123def456",
    '{"token": "' + "t0k3n" * 4 + '"}',
    "eyJ" + "a" * 12 + ".eyJ" + "b" * 12 + "." + "c" * 12,
    "glpat-" + "g" * 20,
    "npm_" + "n" * 36,
    "sk_live_" + "s" * 20,
    "rk_test_" + "r" * 20,
    "redis://:pw12345678@cache:6379",
    "db:\n  password: hunter2hunter2",
    "mysql -u root -pS3cretPass",
    'csrf_token = "' + "ab12" * 5 + '"',
    '"next_token": "' + "xy34" * 5 + '"',
]


@pytest.mark.parametrize("secret", POSITIVES)
def test_secret_never_in_output(db, tmp_path, secret):
    _agent_with("line\n" + secret + "\nmore\n", "result " + secret)
    _clean_episode()
    tj.label_episode(1, "pytest", True)
    tj.label_episode(2, "pytest", True)
    ex = DatasetCurator.__new__(DatasetCurator).curate_verified()
    assert len(ex) == 2
    _, stats = sanitize_examples(ex)
    assert stats["secret"] == 1
    out, n = export_dataset(ex, str(tmp_path / "out"), "4b")
    text = open(out, encoding="utf-8").read()
    assert secret not in text
    assert json.dumps(secret, ensure_ascii=False)[1:-1] not in text
    assert len(_lines(out)) == 1 and n == 1


NEGATIVES = [
    "export OPENROUTER_API_KEY=sk-or-...",
    'export OPENROUTER_API_KEY="sk-or-..."',
    'api_key = "your-key-here..."',
    "sk-or-...",
    "docker run -e POSTGRES_PASSWORD=$PG_PASS pg",
    "docker run -e POSTGRES_PASSWORD_FILE=/run/secrets/x pg",
    "mysql --password=$X",
    "mysql --password",
    "x-api-key: $API_KEY",
    '-H "X-API-Key: ${KEY}"',
    "x-api-key: abc",
    "token: short",
    "max_tokens: 4096",
    'password = os.environ["DB_PASSWORD"]',
    'tokenizer="Qwen/Qwen3.5-4B"',
    "# sk-learn",
    "Bearer token auth is used",
    "-----BEGIN PUBLIC KEY-----",
    "secret = None",
    "MAX_TOKENS=4096",
    "PWD=/data/data/com.termux",
    "PASSWORD_MIN_LEN=12",
    "git@github.com:org/repo.git",
    "http://localhost:8080/path",
    "basic responsibilities of the maintainers",
    "postgres://user:${DB_PASS}@host/db",
    "postgres://user:{pw}@host/db",
    "sk-spinner-double-bounce",
    'password = "**********"',
    '"secret": "/etc/ssl/secret.key"',
    'password = "~/.secrets/file"',
    'password: "$DB_PASSWORD"',
    '"password": "{{vault_password_value}}"',
    '"api_key_env": "OPENAI_API_KEY"',
    "password: Optional[str] = None",
    "password: os.environ.get_it",
    "mysql -u root -p",
    "mysql --port=3306 -h localhost",
    "gcc -pthread main.c",
    "    api_key: SecretStr",
    "    private_key: RSAPrivateKey",
    "    secret_key: settings.SECRET_KEY",
    "    api_key: OpenRouter-compatible key string",
    "  apiKey: process.env.OPENAI_API_KEY",
    "  password: hashedPassword",
    "        secretName: my-app-credentials",
    'OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")',
    'on_first_token: "Optional[callable]" = None',
    'CRM_READ_TOKEN_FILE = CODEY_STATE_DIR / "core_query_token"',
    "mysql then use -pedantic",
    "mysql -u root -p$MYSQL_PASSWORD",
    'mysql -u root -p"$VAR"',
    "postgresql://%(user)s:%(password)s@db",
    'class="sk-fading-circle2-container"',
    "SECRET_KEY_FILE=/run/secrets/key",
    'csrf_token = "short"',
    '"next_token": "placeholder"',
    "export OPENROUTER_API_KEY=sk-or-...",
]


@pytest.mark.parametrize("text", NEGATIVES)
def test_secret_false_positives_kept(db, tmp_path, text):
    assert find_secret(text) is None
    _agent_with("line\n" + text + "\n", "result " + text)
    tj.label_episode(1, "pytest", True)
    ex = DatasetCurator.__new__(DatasetCurator).curate_verified()
    out, n = export_dataset(ex, str(tmp_path / "out"), "4b")
    assert n == 1 and len(_lines(out)) == 1


def test_dedup_collapses_exact_duplicates(db, tmp_path):
    _agent_with("c", "r")
    _agent_with("c", "r")
    _agent_with("c", "r", final="Different.")
    for i in (1, 2, 3):
        tj.label_episode(i, "pytest", True)
    ex = DatasetCurator.__new__(DatasetCurator).curate_verified()
    out, n = export_dataset(ex, str(tmp_path / "out"), "4b")
    rows = _lines(out)
    assert len(rows) == 2 and n == 2
    assert rows[0]["metadata"]["episode_id"] == 1
    _, stats = sanitize_examples(ex)
    assert stats["duplicate"] == 1
    a = {"conversations": [{"role": "user", "content": "x"}], "metadata": {"m": 1}}
    b = {"conversations": [{"role": "user", "content": "x"}], "metadata": {"m": 2}}
    kept, _ = sanitize_examples([a, b])
    assert len(kept) == 1 and kept[0] is a


def _phase3_ex():
    return [{"conversations": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]}]


def test_clean_export_byte_identical(tmp_path):
    ex = _phase3_ex()
    out, n = export_dataset(ex, str(tmp_path), "4b")
    with open(out, encoding="utf-8", newline="") as f:
        assert f.read() == json.dumps(ex[0], ensure_ascii=False) + "\n"
    assert n == 1


def test_max_example_chars_drops_not_truncates():
    ex = _phase3_ex()
    L = len(json.dumps(ex[0], ensure_ascii=False))
    kept, stats = sanitize_examples(ex, max_example_chars=L - 1)
    assert kept == [] and stats["oversize"] == 1 and stats["kept"] == 0
    kept, stats = sanitize_examples(ex, max_example_chars=L)
    assert kept == ex and kept[0] is ex[0]


def test_scan_error_fails_closed(tmp_path, monkeypatch):
    class Boom:
        def search(self, _):
            raise RuntimeError("scan failed")
    monkeypatch.setattr(eh, "SECRET_PATTERNS", (("x", Boom()),))
    out_dir = tmp_path / "out"
    with pytest.raises(RuntimeError):
        export_dataset(_phase3_ex(), str(out_dir), "4b")
    assert not (out_dir / "codey-finetune-4b.jsonl").exists()
    assert not out_dir.exists()  # hygiene runs before any mkdir


@pytest.mark.parametrize("text", ["a" * 200_000, "x" * 200_000 + "\n", "secret_" * 30_000,
                                  "PASSWORD_" * 20_000, "sk-" * 60_000, "mysql " * 30_000])
def test_find_secret_is_linear_on_adversarial_input(text):
    t = time.perf_counter()
    assert find_secret(text) is None
    assert time.perf_counter() - t < 3


def test_write_jsonl_failure_leaves_previous_export_intact(tmp_path):
    from core.finetune_prep import _write_jsonl
    target = tmp_path / "x.jsonl"
    target.write_text("old\n", encoding="utf-8")
    with pytest.raises(TypeError):
        _write_jsonl([{"a": 1}, {"a": {1, 2}}], target)  # set is not JSON serializable
    assert target.read_text(encoding="utf-8") == "old\n"
    assert os.listdir(tmp_path) == ["x.jsonl"]  # no temp file left behind
    assert _write_jsonl([{"a": 1}], target) == 1
    assert target.read_text(encoding="utf-8") == '{"a": 1}\n'


def test_letters_only_token_not_caught_by_design():
    assert find_secret('{"token": "' + "abcdefghij" * 3 + '"}') is None
