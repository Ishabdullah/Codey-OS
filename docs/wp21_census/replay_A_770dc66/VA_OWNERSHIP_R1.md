# Rule6 factual correction R1 — ready for independent result re-review

The original receiver assertion “StateStore never constructed” was FALSE. Original va_receiver_ownership.csv, ADAPTER_VA.md and VA_REPLAY_RESULT.md are preserved unchanged as *.before_R1. Diagnostic va_module_import_graph.json remains unchanged, explicitly16-file7fe60cc AST-only. Corrections are documentary only: no adapter/source/data/guard behavior, new test, DB open, product import, seed or replay. Reviewer result/control totals remain unchanged; final result approval pending re-review.

## Actual SQLite bootstrap and path derivation

Frozen770dc6639e4100ea3215fca07d923769a8290078 source in exact executed nonce va-ybv196pf:

1. tools.shell_tools imports action_gateway, gateway55 imports filesystem, filesystem20 imports checkpoint.
2. checkpoint536 module-level _extend_state_schema() calls get_state_store at523. state544 constructs StateStore singleton, reaching sqlite3.connect41 with default STATE_DB.
3. StateStore48 enables WAL and _init_schema creates fixed seven diagnostic application tables, with implicit sqlite_sequence for AUTOINCREMENT (reviewer's observed8-table schema). checkpoint523+ extends checkpoints table with fixed CREATE IF NOT EXISTS. No caller-supplied SQL/schema/plugin is involved in this import bootstrap.
4. Controller execute creates fresh nonce home/state/prefix/tmp/out directories; only archive snapshot is copied under home/Codey-OS, not into nonce state/. minimal_env provides absolute HOME, CODEY_STATE_DIR=nonce/state, CODEY_CONFIG_PATH=nonce/state/config.json, audit path and Restoricon path, removing inherited configuration/proxies. guard.install validates ENV_PATHS absolute/resolved strictly below nonce before ANY product import (guard149-156). It rejects preloaded products. Existing config file is created as{} by target before source imports; currentJSON remains{}.
5. utils.config325 honors explicit CODEY_STATE_DIR;335 sets STATE_DB_FILE=CODEY_STATE_DIR/'state.db'. state19-23 imports that constant as STATE_DB; constructor default captures it. Therefore the reviewed default connection opens nonce/state/state.db, not live ~/.codeyOS and not Restoricon DB. Post-import adapter checks config.CODEY_STATE_DIR/core.state.STATE_DIR and related runtime paths below nonce. It does NOT separately check STATE_DB_FILE at runtime; exact frozen source derivation supplies that missing explicit check for this result. This is factual closure for this selected path, not a generic argument-validation or FS sandbox guarantee.
6. Guard does NOT monkeypatch sqlite3.connect, file writes or PRAGMAs. Actual nonce-local SQLite schema/WAL creation is allowed reviewed bootstrap, alongside owned config/audit/fixture FS effects. Policy scope is fresh own-root DB with source-constant schema only; foreign DBs, ATTACH, load_extension, caller SQLite plugins or dynamic DB paths require new review. No ATTACH/load_extension call appears in selected state/checkpoint source. Native SQLite implementation itself is trusted runtime, not intercepted/native-contained.

Actual state/state.db is53248bytes. Its main-file mtime is exactly24,000,000ns after out/va-complete.json. This is CONSISTENT WITH connection/WAL finalization; timing/cause is not proven, and does not establish a postrun creator. Coordinator explicitly reports no postrun product import or seeding. This correction used only JSON/source/hash/stat reads; no DB was opened here.

## Corrected18-file selected closure

VA_FROZEN_RUNTIME_CLOSURE.json retains exact18paths/SHA256 and equality to executed job's frozen1267-file manifest. Starting from preserved16 diagnostic files, actual audit redaction lazily reaches core.export_hygiene at action_gateway127 (also logger65); export_hygiene33 imports trajectory's OVERSIZE_MARKER_PREFIX. trajectory module defines _connect61 but constant import/mask_secrets do not invoke it. The18-file list is source-reconciled with executed selected path, NOT a saved sys.modules trace or exhaustive dynamic/import receiver proof. No runtime module inventory was newly obtained by product import.

The104 receiver inventory now records state41 as ACTUAL_IMPORT_BOOTSTRAP_OWNED_NONCE_SQLITE and trajectory61 as SELECTED_LAZY_AUDIT_IMPORT_CONNECT_NOT_CALLED_BY_MASK. Remaining102 rows remain outside selected closure and unverified globally. This corrects both previous “never constructed” and103-outside statements without claiming complete receiver containment.

## Evidence retained and unchanged

269casefiles/267matchedcontrols/301events;193legacyIDs mapped,74pending;8newcasefoldcases;8acceptedresidualattempts refused by harness;2explicitunrun; no case/control/hash result changed. Reviewer's all1267source hashes unchanged;18closure hashes independently source-read and matched here. ADAPTER_VA.md corrects live description and appends Rule6 R1 note; VA_REPLAY_RESULT.md corrects closure and allowed SQLite effects. Original false claims remain in preserved *.before_R1 artifacts. No source/adapter retry is necessary for this factual correction alone.

Unchanged execution-authorized identity:

```json
{
  "replay_va.py": "a644d8d176a13ad793b446500d9acbde1f921c12384c3e378271f2a85b551f32",
  "replay_va_cases.json": "8efc61fb08e65b9e7c688e6120645d190de34ff4331ac6e50ddee1362f5aa583",
  "replay_guard.py": "f68aa877fa92d0fc979c807d3fe7ce0e0d85d9d02075fce2c6bd61ecf0c36995"
}
```

Independent corrected-artifact review required before final result publication. No closure/DoD/residual signature inferred.
