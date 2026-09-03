"""
Allow-list enforcement for category-G provenance — asserts no secret-
bearing env var or config key can ever reach a record — and that
model-digest caching keys on (size_bytes, mtime_ns), per
docs/telemetry_layer_design.md §2.G / §3.4 / §8 item 4.
"""

from __future__ import annotations

import json

import pytest

from telemetry import provenance


SECRET_NAMES = ["OPENROUTER_API_KEY", "UNLIMITEDCLAUDE_API_KEY", "CLOUDFLARE_TUNNEL_TOKEN"]


def test_build_env_overrides_never_leaks_secret_values(monkeypatch):
    for name in SECRET_NAMES:
        monkeypatch.setenv(name, "super-secret-value-do-not-leak")

    overrides = provenance.build_env_overrides()

    serialized = json.dumps(overrides)
    assert "super-secret-value-do-not-leak" not in serialized
    for name in SECRET_NAMES:
        assert name not in overrides  # never a literal key either
        assert overrides[f"{name.lower()}_set"] is True


def test_build_env_overrides_presence_only_boolean_when_unset(monkeypatch):
    for name in SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)

    overrides = provenance.build_env_overrides()
    for name in SECRET_NAMES:
        assert overrides[f"{name.lower()}_set"] is False


def test_build_env_overrides_only_allow_listed_names_appear_as_keys(monkeypatch):
    monkeypatch.setenv("CODEY_N_CTX", "4096")
    monkeypatch.setenv("SOME_RANDOM_UNRELATED_VAR", "should-not-appear")

    overrides = provenance.build_env_overrides()
    assert overrides.get("CODEY_N_CTX") == "4096"
    assert "SOME_RANDOM_UNRELATED_VAR" not in overrides


def test_build_env_overrides_never_dumps_whole_environ(monkeypatch):
    monkeypatch.setenv("HOME", "/should/not/appear/verbatim/as/a/dump")
    overrides = provenance.build_env_overrides()
    assert "HOME" not in overrides


def test_build_config_snapshot_is_a_projection_not_a_dump():
    snapshot = provenance.build_config_snapshot()
    assert snapshot["_policy"] == "v1"
    # None of the projection's keys should be secret-shaped.
    for key in snapshot:
        assert "key" not in key.lower() and "token" not in key.lower() and "secret" not in key.lower()


def test_get_model_digest_cold_cache_returns_not_computed(tmp_path):
    model_file = tmp_path / "fake-model.gguf"
    model_file.write_bytes(b"not a real model, just needs to exist")
    cache_file = tmp_path / "model_digests.json"  # never created

    result = provenance.get_model_digest(model_file, cache_path=cache_file)
    assert result["sha256"] is None
    assert result["sha256_source"] == "not_computed"
    assert result["size_bytes"] == model_file.stat().st_size


def test_get_model_digest_uses_cache_when_size_and_mtime_match(tmp_path):
    model_file = tmp_path / "fake-model.gguf"
    model_file.write_bytes(b"some bytes representing a model")
    stat = model_file.stat()

    cache_file = tmp_path / "model_digests.json"
    cache_file.write_text(
        json.dumps(
            {
                str(model_file): {
                    "size_bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": "a" * 64,
                    "computed_at": 1234.0,
                }
            }
        ),
        encoding="utf-8",
    )

    result = provenance.get_model_digest(model_file, cache_path=cache_file)
    assert result["sha256"] == "a" * 64
    assert result["sha256_source"] == "cached"


def test_get_model_digest_cache_miss_on_size_mismatch(tmp_path):
    model_file = tmp_path / "fake-model.gguf"
    model_file.write_bytes(b"current content")
    stat = model_file.stat()

    cache_file = tmp_path / "model_digests.json"
    cache_file.write_text(
        json.dumps(
            {
                str(model_file): {
                    "size_bytes": stat.st_size + 999,  # deliberately wrong
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": "b" * 64,
                }
            }
        ),
        encoding="utf-8",
    )

    result = provenance.get_model_digest(model_file, cache_path=cache_file)
    assert result["sha256"] is None
    assert result["sha256_source"] == "not_computed"


def test_get_model_digest_never_raises_on_missing_file(tmp_path):
    missing = tmp_path / "does-not-exist.gguf"
    result = provenance.get_model_digest(missing, cache_path=tmp_path / "cache.json")
    assert result["sha256"] is None
    assert result["sha256_source"] == "not_computed"
    assert result["size_bytes"] is None


def test_get_model_digest_never_computes_a_real_hash_synchronously(tmp_path, monkeypatch):
    """T0 constraint: no synchronous hashing anywhere in this module
    (fact 0.23 — ~5.2s for the real primary model). If hashlib.sha256
    were ever called by get_model_digest, this would fail loudly rather
    than silently passing on a small test file."""
    import hashlib

    calls = []
    real_sha256 = hashlib.sha256

    def spy_sha256(*args, **kwargs):
        calls.append(True)
        return real_sha256(*args, **kwargs)

    monkeypatch.setattr(hashlib, "sha256", spy_sha256)

    model_file = tmp_path / "fake-model.gguf"
    model_file.write_bytes(b"x" * 1000)
    provenance.get_model_digest(model_file, cache_path=tmp_path / "nope.json")

    assert calls == []


def test_get_git_provenance_never_raises_when_git_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(provenance, "_run_git", lambda args, cwd: (_ for _ in ()).throw(FileNotFoundError()))
    result = provenance.get_git_provenance(tmp_path)
    assert result == {
        "commit_sha": None,
        "dirty": None,
        "dirty_file_count": None,
        "branch": None,
    }


def test_get_device_provenance_never_raises(monkeypatch):
    # Simulate getprop being entirely absent (e.g. a non-Android dev box).
    monkeypatch.setattr(provenance, "_getprop", lambda name: None)
    result = provenance.get_device_provenance()
    assert result["device_model"] is None
    assert result["python_version"]  # always available, no subprocess needed


def test_get_ram_swap_bytes_never_raises_when_meminfo_unreadable(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("nope")

    monkeypatch.setattr("builtins.open", boom)
    result = provenance.get_ram_swap_bytes()
    assert result == {"ram_total_bytes": None, "swap_total_bytes": None}
