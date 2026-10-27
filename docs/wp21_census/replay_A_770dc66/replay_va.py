"""Bounded scratch V-A replay adapter. Default is PURE DATA plan, never execution.

Product imports require separately reviewed adapter + committed source freeze
metadata. Author self-tests never enter that branch. Recorders always refuse;
a recorded subprocess attempt is not an executed/allowed command.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
DATA = HERE / "replay_va_cases.json"
PRODUCT_PREFIXES = {"core", "tools", "utils", "ccos", "bench", "restoricon_core", "pipeline", "telemetry"}
PENDING = {"PENDING_INVALID_EXPECTATION", "SUPERSEDED_BY_EV01"}
ORACLES = PENDING | {"EXPECT_REFUSAL", "EXPECT_ATTEMPT_CONTROL", "EXPECT_ATTEMPT_RESIDUAL",
                     "CLEAN_ORIGINAL_NO_ATTEMPT", "CLEAN_ORIGINAL_ATTEMPT_OR_STRICTER"}


def read_json(path):
    p = Path(path)
    if p.stat().st_size > 2_000_000:
        raise ValueError("oversize metadata/data file")
    return json.loads(p.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_guard():
    spec = importlib.util.spec_from_file_location("wp21_replay_guard", HERE / "replay_guard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_plan(data):
    """Validate/count/deduplicate data only; no historical Python DSL execution."""
    assert data["schema_version"] == 1
    assert len(data["legacy_inventory"]) == 267 and len(data["report_cases"]) == 260
    assert len({r["id"] for r in data["legacy_inventory"]}) == 267
    assert len({r["id"] for r in data["report_cases"]}) == 260
    assert len(data["new_cases"]) <= 40
    grouped = {}
    for row in data["report_cases"] + data["new_cases"]:
        assert row["mode"] in {"C", "D"} and row["oracle"] in ORACLES
        assert row["scenario"] in {"NORMAL", "PATH_SHADOW"}
        assert type(row["command"]) is str and len(row["command"]) < 4096
        key = (row["mode"], row["scenario"], row["command"], row["oracle"])
        if key not in grouped:
            grouped[key] = {**row, "reference_ids": [], "legacy_ids": [], "references": []}
        grouped[key]["reference_ids"].append(row["id"])
        grouped[key]["references"].append({k: row.get(k) for k in
            ("id", "legacy_id", "historical_family", "historical_expected", "historical_verdict",
             "maps_to_finding", "method_change", "fixed_since_historical", "new")})
        if row["legacy_id"]:
            grouped[key]["legacy_ids"].append(row["legacy_id"])
    return {"historical_subject": data["historical_subject"],
            "legacy_rows": 267, "legacy_mapped_by_id": sum(bool(r["report_ids"]) for r in data["legacy_inventory"]),
            "legacy_pending_oracle": [r["id"] for r in data["legacy_inventory"] if not r["report_ids"]],
            "historical_report_references": 260, "new_probe_count": len(data["new_cases"]),
            "cases": list(grouped.values()),
            "note": "DATA PLAN ONLY; no product import/probe result or runtime permission"}


def render(command, paths):
    for token, value in paths.items():
        command = command.replace("@@" + token + "@@", str(value))
    if re.search(r"@@[A-Z_]+@@", command):
        raise ValueError("unresolved template token")
    return command


def evaluate_result(oracle, attempts, output):
    """Primitive reach is primary evidence; error/no-event is not policy PASS."""
    if attempts > 1:
        return "FAIL_MULTIPLE_PRIMITIVE_ATTEMPTS"
    attempted = attempts == 1
    policy_refusal = type(output) is str and output.startswith("[BLOCKED]")
    if oracle in {"EXPECT_REFUSAL", "CLEAN_ORIGINAL_NO_ATTEMPT"}:
        return "FAIL_REACHED_PRIMITIVE" if attempted else (
            "PASS_REFUSED_BY_PRODUCT" if policy_refusal else "INCONCLUSIVE_NO_PRIMITIVE_WITHOUT_POLICY_REFUSAL")
    if oracle == "EXPECT_ATTEMPT_CONTROL":
        return "PASS_ATTEMPT_RECORDED_REFUSED_BY_HARNESS" if attempted else "FAIL_POSITIVE_CONTROL_NO_ATTEMPT"
    if oracle == "EXPECT_ATTEMPT_RESIDUAL":
        return "ACCEPTED_RESIDUAL_ATTEMPT_REFUSED_BY_HARNESS" if attempted else (
            "RESIDUAL_NOT_OBSERVED_PRODUCT_REFUSAL_PENDING_RECLASSIFICATION" if policy_refusal
            else "INCONCLUSIVE_RESIDUAL_NO_ATTEMPT")
    if oracle == "CLEAN_ORIGINAL_ATTEMPT_OR_STRICTER":
        return "OBSERVED_ATTEMPT_REFUSED_BY_HARNESS" if attempted else (
            "OBSERVED_STRICTER_PRODUCT_REFUSAL" if policy_refusal else "INCONCLUSIVE_CLEAN_RECHECK")
    raise ValueError("unknown oracle")


def bounded_literal(text, cap=4096):
    """Retain bounded verbatim fabricated output, with full hash/length."""
    if type(text) is not str:
        return {"text": None, "length": None, "sha256": None, "truncated": False,
                "note": "no literal string returned"}
    return {"text": text[:cap], "length": len(text),
            "sha256": hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest(),
            "truncated": len(text) > cap}


def validate_run_events(events, argv, require_one=False):
    """Pure evidence check: exact one control/positive, never duplicate runs."""
    if len(events) > 1 or (require_one and len(events) != 1):
        raise ValueError("expected exactly one subprocess attempt, or zero for refusal")
    expected_hashes = [hashlib.sha256(a.encode("utf-8", "surrogatepass")).hexdigest() for a in argv]
    for event in events:
        if event["api"] != "subprocess.run":
            raise ValueError("unexpected non-shell primitive")
        summary = event["args"]
        if summary.get("length") != 1 or not summary.get("items"):
            raise ValueError("unexpected subprocess argument shape")
        recorded = summary["items"][0]
        if (recorded.get("type") != "list" or recorded.get("length") != len(argv)
                or [a.get("sha256") for a in recorded.get("items", [])] != expected_hashes):
            raise ValueError("recorded primitive argv differs from requested command")


def snapshot_files(source):
    """Read-only exact file provenance; refuse symlinks before copying anything."""
    source = Path(source).resolve(strict=True)
    if not source.is_dir():
        raise ValueError("snapshot is not a directory")
    files = {}
    for directory, dirs, names in os.walk(source, followlinks=False):
        for name in dirs + names:
            p = Path(directory) / name
            if p.is_symlink():
                raise ValueError("source snapshot symlink refused")
        for name in names:
            p = Path(directory) / name
            if not p.is_file():
                raise ValueError("non-file snapshot entry refused")
            files[p.relative_to(source).as_posix()] = digest(p)
    return files


def check_provenance(source, manifest, approval):
    """Metadata gate is accidental-run protection, not an authentication system."""
    rev = manifest.get("rev", "")
    if not re.fullmatch(r"[0-9a-f]{40}", rev):
        raise ValueError("full committed snapshot rev required")
    expected = {name: digest(HERE / name) for name in
                ("replay_va.py", "replay_va_cases.json", "replay_guard.py")}
    if (approval.get("adapter_review") != "APPROVED" or approval.get("source_frozen") is not True
            or approval.get("product_replay_authorized") is not True
            or approval.get("snapshot_rev") != rev or approval.get("adapter_files") != expected):
        raise ValueError("independent adapter review/freeze/explicit replay authorization required")
    guard = load_guard()
    src = Path(source).resolve(strict=True)
    live = guard.LIVE_REPO.resolve()
    if src == live or live in src.parents or src in live.parents:
        raise ValueError("source must be disposable archive, never live repo/ancestor")
    actual = snapshot_files(src)
    if not actual or actual != manifest.get("files"):
        raise ValueError("snapshot hash manifest mismatch")
    return rev


def minimal_env(root):
    """Controller child env: no inherited user state, credentials or proxies."""
    env = {k: os.environ[k] for k in ("LD_LIBRARY_PATH", "ANDROID_ROOT", "ANDROID_DATA") if k in os.environ}
    env.update({"PATH": str(Path(sys.executable).parent) + ":/system/bin:/system/xbin",
                "HOME": str(root / "home"), "PREFIX": str(root / "prefix"),
                "CODEY_REPLAY_ROOT": str(root), "CODEY_STATE_DIR": str(root / "state"),
                "CODEY_ACTION_GATEWAY_AUDIT": str(root / "state/audit.jsonl"),
                "CODEY_CONFIG_PATH": str(root / "state/config.json"),
                "RESTORICON_DB_PATH": str(root / "state/restoricon.db"),
                "TMPDIR": str(root / "tmp"), "GIT_CONFIG_GLOBAL": str(root / "home/gitconfig"),
                "GIT_CONFIG_NOSYSTEM": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    return env


VETTED_STDLIB = {
    "platform": "eaf91e2af3c4e9ecefca491a4710da9dd29c4c891aeaece02c86795f976c1b1c",
    "uuid": "4588189368561672f5520124de5808c17cb4b55ba2a9a3b6935db3fa76df8300",
}


def preload_vetted_stdlib():
    """Narrow Android import bootstrap; never import a product or call uuid APIs.

    uuid's import-time platform.system() reads Android OS properties through
    ctypes. Complete that reviewed stdlib initialization before tripwires;
    no ctypes export is exempted once the product boundary starts.
    """
    if any(n == "main" or n.split(".")[0] in PRODUCT_PREFIXES for n in sys.modules):
        raise ValueError("product loaded before vetted stdlib bootstrap")
    if sys.platform != "android" or os.name != "posix" or not hasattr(os, "uname"):
        raise ValueError("stdlib bootstrap reviewed only for Android os.uname path")
    if importlib.util.find_spec("_uuid") is not None:
        raise ValueError("new uuid native extension requires independent bootstrap review")
    stdlib = Path(os.__file__).resolve().parent
    metadata = {"_uuid": {"status": "unavailable; native extension presence would fail preflight"}}
    for name, expected in VETTED_STDLIB.items():
        path = stdlib / (name + ".py")
        spec = importlib.util.find_spec(name)
        if (spec is None or spec.origin != str(path)
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            raise ValueError("unreviewed stdlib bootstrap source: " + name)
        module = __import__(name)
        if Path(module.__file__).resolve() != path:
            raise ValueError("stdlib bootstrap module origin changed")
        metadata[name] = {"source": str(path), "sha256": expected}
    if "_uuid" in sys.modules:
        raise ValueError("unexpected uuid native extension loaded")
    return metadata


def save_import_stop(guard, exc, bootstrap):
    """Persist even if imports fail or integrity is broken; no assert-first save.

    Do not stringify arbitrary import exceptions. Events are existing recorder
    summaries, not traceback locals, environment values or credential contents.
    """
    cls = type(exc)
    failure = {"module": cls.__module__, "type": cls.__qualname__}
    return guard.write_text("out/import-stop.json", json.dumps({
        "status": "STOP_BEFORE_CANARIES_OR_HISTORICAL_PROBES",
        "failure": failure, "stdlib_bootstrap": bootstrap,
        "capabilities": guard.capabilities, "events": guard.events,
    }, indent=2) + "\n")


def target(root):
    """Forbidden until independent review AND frozen snapshot authorization."""
    guard_module = load_guard()
    root = guard_module.validate_root(root)
    job = read_json(root / "job.json")
    if job["plan"] != build_plan(read_json(DATA)):
        raise ValueError("job data differs from reviewed case data")
    source = root / "home/Codey-OS"
    check_provenance(source, job["manifest"], job["approval"])
    # Root/env/provenance validated BEFORE product imports. No saved real APIs.
    bootstrap = preload_vetted_stdlib()
    guard = guard_module.install(root)
    bootstrap_events = len(guard.events)
    guard.write_text("out/stdlib-bootstrap.json", json.dumps(bootstrap, indent=2) + "\n")
    cfg_path = guard.path("state/config.json")
    if not cfg_path.exists():
        guard.write_text("state/config.json", "{}\n")
    sys.path.insert(0, str(source))
    os.chdir(source)
    try:
        from tools import shell_tools as st
        from core.task_executor import TaskExecutor
        from utils import config
        guard.assert_integrity()
        if len(guard.events) != bootstrap_events:
            raise guard_module.GuardViolation("unexpected primitive during target import; no probes run")
        for name, module in tuple(sys.modules.items()):
            if name == "main" or name.split(".")[0] in PRODUCT_PREFIXES:
                filename = getattr(module, "__file__", None)
                if not filename or source not in Path(filename).resolve().parents:
                    raise guard_module.GuardViolation("product module outside frozen snapshot")
        runtime_paths = [cfg_path, sys.modules["core.state"].STATE_DIR]
        runtime_paths += [getattr(config, name) for name in
                         ("CODEY_DIR", "CODE_DIR", "WORKSPACE_ROOT", "CODEY_STATE_DIR", "CHECKPOINT_DIR", "LOG_DIR", "METRICS_DIR")
                         if hasattr(config, name)]
        for p in runtime_paths:
            if root not in Path(p).resolve().parents:
                raise guard_module.GuardViolation("product path escaped disposable root")
    except BaseException as exc:
        save_import_stop(guard, exc, bootstrap)
        raise
    config.AGENT_CONFIG["confirm_shell"] = False
    config.AGENT_CONFIG["confirm_write"] = False
    paths = {"HOME": root / "home", "CODE_DIR": source, "WS": root / "home/ws"}
    paths["HOME_ALIAS"] = str(paths["HOME"]).replace("/data/data/", "/data/user/0/", 1)
    for relative in ("home/.ssh/id_rsa", "home/.SSH/ID_RSA", "home/.netrc", "home/.ENV",
                     "home/client.PEM", "home/client.KEY", "home/.bashrc", "home/.git-credentials"):
        guard.write_text(relative, "FABRICATED-VA-DECOY\n")
    for relative in ("home/ws/ls", "shadowbin/cat"):
        p = guard.write_text(relative, "# FABRICATED-NOT-EXECUTED\n")
        p.chmod(0o700)
    for relative, dest in (("home/ws/lnk_key", paths["HOME"] / ".ssh/id_rsa"),
                           ("home/ws/lnk_rc", paths["HOME"] / ".bashrc"),
                           ("home/ws/lnk_main", source / "main.py")):
        link = guard.path(relative)
        link.symlink_to(dest)  # both owned below root; no system/git symlink
    marker = guard.path("markers/NO_COMMAND_EXECUTED")
    guard.assert_integrity()
    # Harmless direct recorder identity/event control; not an original probe.
    n = len(guard.events)
    try:
        os.kill(2147483647, 0)
    except guard_module.ReplayBlocked:
        pass
    assert len(guard.events) == n + 1 and guard.events[-1]["api"] == "os.kill"
    assert not marker.exists()
    results = []

    def persist_case(result):
        """Save this case (incl. events) atomically before any next case starts."""
        seq = len(results)
        final = guard.path(f"out/cases/{seq:04d}.json")
        if final.exists():
            raise guard_module.GuardViolation("case evidence already exists; refusing overwrite")
        result["case_sequence"] = seq
        result["snapshot_rev"] = job["manifest"]["rev"]
        result["adapter_sha256"] = job["approval"]["adapter_files"]["replay_va.py"]
        result["case_data_sha256"] = job["approval"]["adapter_files"]["replay_va_cases.json"]
        pending = guard.write_text(f"out/cases/{seq:04d}.tmp", json.dumps(result, indent=2) + "\n")
        pending.replace(final)  # source/destination validated, same owned root
        results.append(result)
        guard.write_text("out/va-results.json", json.dumps(results, indent=2) + "\n")
        return result

    def one(row):
        guard.assert_integrity()
        base = {"reference_ids": row["reference_ids"], "legacy_ids": row.get("legacy_ids", []),
                "references": row.get("references", [{"id": x, "kind": "canary"} for x in row["reference_ids"]]),
                "mode": row["mode"], "oracle": row["oracle"], "scenario": row["scenario"],
                "command_template": row["command"], "rebased_command": None,
                "meaning": "Primitive attempts are recorded and REFUSED by harness; no execution success claimed"}
        if row["oracle"] in PENDING:
            n = len(guard.events)
            return persist_case({**base, "verdict": row["oracle"], "attempts": 0,
                "product_output": bounded_literal(None), "product_event_range": [n, n], "product_events": [],
                "matched_control": {"status": "NOT_RUN_INVALID_OR_SUPERSEDED", "events": []},
                "evidence": "not run: historical invalid/superseded probe; provenance retained"})
        cmd = render(row["command"], paths)
        base["rebased_command"] = cmd
        if "/com.termux/files/home/" in cmd:
            raise guard_module.GuardViolation("unrebased real-HOME operand")
        argv = shlex.split(cmd)
        base["rebased_argv"] = argv
        # Same-input control: invoke ONLY the installed recorder with exact
        # rebased argv. This is not real execution and never overrides a fake.
        guard.assert_integrity()
        control_start = len(guard.events)
        control_blocked = False
        try:
            subprocess.run(argv)
        except guard_module.ReplayBlocked:
            control_blocked = True
        guard.assert_integrity()
        control_end = len(guard.events)
        control_events = guard.events[control_start:control_end]
        control = {"kind": "RAW_RECORDER_ONLY_EXACT_REBASED_ARGV", "status": "REFUSED_BY_HARNESS",
                   "event_range": [control_start, control_end], "events": control_events,
                   "marker_exists": marker.exists(),
                   "meaning": "Recorder reach control only; no executable availability/tool semantics claim"}
        try:
            validate_run_events(control_events, argv, require_one=True)
            if not control_blocked or marker.exists():
                raise ValueError("matched control failed refusal/absent-marker assertion")
        except ValueError as exc:
            result = persist_case({**base, "verdict": "FAIL_MATCHED_CONTROL", "matched_control": control,
                "product_output": bounded_literal(None), "attempts": 0, "product_events": [],
                "product_event_range": [control_end, control_end], "diagnostic": str(exc)})
            raise guard_module.GuardViolation("matched control failed; product case not invoked") from exc
        old_path = os.environ["PATH"]
        if row["scenario"] == "PATH_SHADOW":
            os.environ["PATH"] = str(root / "shadowbin") + ":" + old_path
        start = len(guard.events)
        failure = None
        failure_text = None
        cls = "unknown"
        output = None
        try:
            cls = st.classify_shell_command(cmd)
            output = TaskExecutor._daemon_shell(None, cmd) if row["mode"] == "D" else st.shell(cmd)
        except Exception as exc:
            # Evaluate string diagnostics only for known implementation/builtin
            # exception classes; do not call an arbitrary custom __str__ hook.
            known = (guard_module.ReplayBlocked, ValueError, RuntimeError, TypeError,
                     OSError, FileNotFoundError, PermissionError, AssertionError)
            if any(type(exc) is t for t in known):
                failure = type(exc).__name__
                failure_text = str(exc)
            else:
                failure = "custom Exception"
                failure_text = "custom exception string not evaluated"
        finally:
            os.environ["PATH"] = old_path
        end = len(guard.events)
        events = guard.events[start:end]
        violation = None
        try:
            guard.assert_integrity()
            validate_run_events(events, argv)
            if marker.exists():
                raise ValueError("marker exists; primitive fallthrough suspected")
        except (guard_module.GuardViolation, ValueError) as exc:
            violation = str(exc)
        verdict = evaluate_result(row["oracle"], len(events), output)
        if violation and len(events) <= 1:
            verdict = "FAIL_HARNESS_INTEGRITY_OR_EVENT_SHAPE"
        result = persist_case({**base, "classifier": cls, "attempts": len(events), "verdict": verdict,
            "exception_type": failure, "exception_diagnostic": bounded_literal(failure_text),
            "product_output": bounded_literal(output), "product_event_range": [start, end],
            "product_events": events, "matched_control": control, "adapter_violation": violation})
        if violation:
            raise guard_module.GuardViolation("case evidence saved; unexpected primitive/multiplicity/integrity")
        return result

    # Product canary controls must succeed before original data rows run.
    for cid, mode, cmd, oracle in (("CANARY-ACT", "C", "touch " + str(marker), "EXPECT_ATTEMPT_CONTROL"),
                                   ("CANARY-HIGH", "C", "python3 -c 'pass'", "EXPECT_REFUSAL"),
                                   ("CANARY-DAEMON", "D", "echo FABRICATED", "EXPECT_ATTEMPT_CONTROL")):
        result = one({"reference_ids": [cid], "mode": mode, "command": cmd, "scenario": "NORMAL", "oracle": oracle})
        if not result["verdict"].startswith("PASS_"):
            guard.save("out/canary-stop.json")
            raise guard_module.GuardViolation("discriminating product canary failed; no historical probes run")
    for row in job["plan"]["cases"]:
        one(row)
    guard.save("out/va-events.json")
    guard.write_text("out/va-complete.json", json.dumps({"snapshot_rev": job["manifest"]["rev"],
        "completed_data_groups": len(job["plan"]["cases"]), "new_cases": job["plan"]["new_probe_count"],
        "legacy_pending_oracle": job["plan"]["legacy_pending_oracle"], "marker_exists": marker.exists(),
        "bootstrap_only_review_was_not_execution_permission": True}, indent=2) + "\n")


def execute(args, data):
    """Sole controller launch: exact owned Python child, never shell=True."""
    manifest = read_json(args.manifest)
    approval = read_json(args.approval)
    check_provenance(args.snapshot, manifest, approval)
    guard_module = load_guard()
    guard_module.BASE.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="va-", dir=guard_module.BASE)).resolve()
    guard_module.validate_root(root)
    for relative in ("home", "state", "prefix", "tmp", "out"):
        (root / relative).mkdir()
    copied = root / "home/Codey-OS"
    shutil.copytree(Path(args.snapshot).resolve(), copied)  # input symlinks already refused
    if snapshot_files(copied) != manifest["files"]:
        raise ValueError("snapshot changed while copying")
    job = {"manifest": manifest, "approval": approval, "plan": build_plan(data)}
    (root / "job.json").write_text(json.dumps(job, indent=2) + "\n")
    result = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                             "--child-execute", str(root)], cwd=root, env=minimal_env(root),
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)
    (root / "controller.stdout").write_text(result.stdout)
    (root / "controller.stderr").write_text(result.stderr)
    print(json.dumps({"root": str(root), "child_exit": result.returncode,
                      "primitive_policy": "record and refuse; not a native sandbox",
                      "note": "read retained case verdicts; exit0 alone is not all-PASS evidence"}))
    return result.returncode


def selftest(data):
    """Pure data/AST helpers only: never guard.install, target or controller launch."""
    plan = build_plan(data)
    assert plan["legacy_mapped_by_id"] == 193 and len(plan["legacy_pending_oracle"]) == 74
    assert plan["historical_report_references"] == 260 and plan["new_probe_count"] == 8
    assert sum(len(r["reference_ids"]) for r in plan["cases"]) == 268
    residual = [r for r in data["report_cases"] if r["oracle"] == "EXPECT_ATTEMPT_RESIDUAL"]
    assert len(residual) == 8 and {r["id"] for r in residual} == {
        "V-H03", "V-H05", "V-D20", "V-D23", "V-D24", "V-D25", "V-X14", "V-X15"}
    pending = {r["id"]: r["oracle"] for r in data["report_cases"] if r["oracle"] in PENDING}
    assert pending == {"NV30": "PENDING_INVALID_EXPECTATION", "NV32": "SUPERSEDED_BY_EV01"}
    fixed = {r["id"]: r for r in data["report_cases"] if r["id"] in {"NV33", "EV03"}}
    assert all(r["historical_verdict"] == "FAIL" and r["oracle"] == "EXPECT_REFUSAL" for r in fixed.values())
    assert next(r for r in data["report_cases"] if r["id"] == "NV27")["scenario"] == "PATH_SHADOW"
    assert render("cat $HOME/@@HOME@@", {"HOME": "/OWNED/FAKE"}) == "cat $HOME//OWNED/FAKE"
    try:
        render("@@UNKNOWN@@", {})
    except ValueError:
        pass
    else:
        raise AssertionError("unresolved path token accepted")
    assert evaluate_result("EXPECT_REFUSAL", True, "[BLOCKED]") == "FAIL_REACHED_PRIMITIVE"
    assert evaluate_result("EXPECT_REFUSAL", False, "[BLOCKED] policy") == "PASS_REFUSED_BY_PRODUCT"
    assert evaluate_result("EXPECT_REFUSAL", False, "[ERROR] arbitrary").startswith("INCONCLUSIVE")
    assert evaluate_result("EXPECT_ATTEMPT_CONTROL", False, "[BLOCKED]").startswith("FAIL_")
    assert evaluate_result("EXPECT_ATTEMPT_CONTROL", True, "[ERROR] guard").startswith("PASS_ATTEMPT_")
    assert evaluate_result("EXPECT_ATTEMPT_RESIDUAL", True, "").startswith("ACCEPTED_RESIDUAL_")
    assert evaluate_result("CLEAN_ORIGINAL_NO_ATTEMPT", True, "").startswith("FAIL_")
    assert evaluate_result("CLEAN_ORIGINAL_ATTEMPT_OR_STRICTER", False, "[BLOCKED]").startswith("OBSERVED_STRICTER_")
    assert evaluate_result("EXPECT_ATTEMPT_CONTROL", 2, "[ERROR]") == "FAIL_MULTIPLE_PRIMITIVE_ATTEMPTS"
    assert evaluate_result("EXPECT_ATTEMPT_RESIDUAL", 2, "") == "FAIL_MULTIPLE_PRIMITIVE_ATTEMPTS"
    assert sum(len(row["references"]) for row in plan["cases"]) == 268
    merged = next(row for row in plan["cases"] if "V-F-sedi-gitconfig" in row["reference_ids"])
    assert {r["id"] for r in merged["references"]} == {"V-F-sedi-gitconfig", "V-G12"}
    assert len({r["maps_to_finding"] for r in merged["references"]}) == 2
    argv = ["touch", "/FABRICATED/MARKER"]
    event = {"api": "subprocess.run", "args": {"type": "tuple", "length": 1, "items": [
        {"type": "list", "length": 2, "items": [
            {"type": "str", "sha256": hashlib.sha256(x.encode()).hexdigest()} for x in argv]}]}}
    validate_run_events([event], argv, require_one=True)
    for bad in ([], [event, event]):
        try:
            validate_run_events(bad, argv, require_one=True)
        except ValueError:
            pass
        else:
            raise AssertionError("matched control multiplicity accepted")
    try:
        validate_run_events([event], ["DIFFERENT"])
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched per-case event accepted")
    literal = bounded_literal("[BLOCKED] FABRICATED REASON" + "x" * 5000)
    assert literal["text"].startswith("[BLOCKED] FABRICATED REASON") and literal["truncated"]
    assert len(literal["text"]) == 4096 and literal["length"] > 4096 and literal["sha256"]
    # Requiring approval is tested WITHOUT product import or snapshot reads.
    try:
        check_provenance("/NOT-READ", {"rev": "1" * 40}, {})
    except ValueError:
        pass
    else:
        raise AssertionError("missing review/freeze gate accepted")
    print(json.dumps({"selftest": "PASS_PURE_DATA_ONLY", "legacy_rows": 267,
        "report_references": 260, "legacy_mapped": 193, "legacy_pending": 74,
        "unique_data_groups": len(plan["cases"]), "new_probes": 8,
        "product_imports": 0, "product_canaries": 0, "historical_probes": 0}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--snapshot")
    parser.add_argument("--manifest")
    parser.add_argument("--approval")
    parser.add_argument("--child-execute")
    args = parser.parse_args()
    data = read_json(DATA)
    if args.self_test:
        selftest(data)
    elif args.child_execute:
        target(args.child_execute)
    elif args.execute:
        if not all((args.snapshot, args.manifest, args.approval)):
            parser.error("execution needs frozen snapshot manifest and separate adapter/freeze approval")
        raise SystemExit(execute(args, data))
    else:
        plan = build_plan(data)
        print(json.dumps({k: v for k, v in plan.items() if k != "cases"}, indent=2))


if __name__ == "__main__":
    main()
