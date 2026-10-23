"""G15d Unit C / Q5: the committed .qwen/settings.json must not pre-approve
destructive, egress, persistence or repo-mutating shell actions."""
import json
from pathlib import Path

SETTINGS = Path(__file__).resolve().parent.parent / ".qwen" / "settings.json"

DROPPED = (
    "pkill", "rm", "curl", "git add", "git commit", "git config", "command",
    "nohup", "timeout", "python3", "pip install", "codeydOS", "llama-server",
)


def test_settings_parse_and_keep_version():
    data = json.loads(SETTINGS.read_text())
    assert data["$version"] == 4
    assert isinstance(data["permissions"]["allow"], list)


def test_destructive_and_egress_entries_are_not_allowed():
    allow = json.loads(SETTINGS.read_text())["permissions"]["allow"]
    for entry in allow:
        body = entry[len("Bash("):-1]
        words = body.split()
        command = Path(words[0]).name
        joined = " ".join(words[:2])
        assert command not in DROPPED and joined not in DROPPED, entry
