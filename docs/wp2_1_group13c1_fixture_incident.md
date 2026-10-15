# WP2.1 group13c.1 fixture-safety incident

13c.1 initial fixture-safety incident — available evidence, not reconstructed full output

Exact command:
pytest -q tests/test_process_identity.py tests/test_process_identity_writers.py tests/test_new74_adopted_stop_noop.py tests/test_loader_v2_load_mode.py tests/test_loader_v2_telemetry.py tests/test_new145_149_155_option_c.py

Unified exec session: 23083. The full stdout was not redirected to a file.
The read returned a truncated tool response (original_token_count 14744).
Full raw output is unavailable; do not treat this excerpt as the full record.
No unsafe test was rerun to recover output.

Verbatim available warning excerpt for the load-mode fake PID5151 and
upgrade fake PID4242 cases:
⚠  LlamaServer.stop() on port 8080 hit an unexpected error during teardown:
[Errno 13] Permission denied
✗  Failed to start llama-server: Process identity unavailable

⚠  LlamaServer.stop() on port 28004 hit an unexpected error during teardown:
[Errno 13] Permission denied
✗  Failed to start llama-server: Process is not a live owned child or self

Relevant captured publication traceback excerpt:
  File "/data/data/com.termux/files/home/Codey-OS/core/loader_v2.py", line 814,
in _spawn_locked
    published = record.publish(self.process.pid)

Safety interpretation and limits:
- All15 failing tests mocked subprocess.Popen, so they did not spawn model
  processes. They supplied numeric PID placeholders5151/4242/4244/4243.
- The newly mandatory publication failure called the real LlamaServer.stop
  in some of these fake contexts. The teardown attempts os.getpgid then
  os.killpg; the caught warning has no traceback for the teardown line.
  Therefore this record cannot distinguish which OS operation was denied,
  or retrospectively prove zero attempted unknown-process signals.
- The never_uses_killpg test explicitly mocked os.kill/getpgid/killpg.
- No absence-of-current-process observation is evidence of earlier safety.
- Before the next expanded run, all8 fake-Popen contexts in these three
  files were amended to mock both identity publication and LlamaServer.stop.
  The repository regression guard is
  tests/test_process_identity_writers.py::test_synthetic_loader_pid_fixtures_guard_publication_and_teardown.
  Its earlier scratch proof is
  /data/data/com.termux/files/usr/tmp/wp21_13c1_fake_pid_safety_guard.txt.
  The other new loader wiring tests retain real disposable child handles
  with finally cleanup.

Verbatim available failure-summary test names:
FAILED tests/test_loader_v2_load_mode.py::test_load_mode_mapping_for_each_combo[True-False-mmap]
FAILED tests/test_loader_v2_load_mode.py::test_load_mode_mapping_for_each_combo[False-True-mlock]
FAILED tests/test_loader_v2_load_mode.py::test_load_mode_mapping_for_each_combo[True-True-mmap+mlock]
FAILED tests/test_loader_v2_load_mode.py::test_load_mode_mapping_for_each_combo[False-False-none]
FAILED tests/test_loader_v2_load_mode.py::test_load_mode_not_emitted_space_separated_not_equals
FAILED tests/test_loader_v2_load_mode.py::test_load_mode_omitted_on_import_failure
FAILED tests/test_loader_v2_load_mode.py::test_reverse_prompt_never_emitted_regardless_of_stop_config
FAILED tests/test_loader_v2_load_mode.py::test_version_diagnostic_logged_before_spawn
FAILED tests/test_loader_v2_load_mode.py::test_version_diagnostic_failure_does_not_block_real_spawn
FAILED tests/test_loader_v2_telemetry.py::test_argv_provenance_emitted_on_genuine_spawn
FAILED tests/test_loader_v2_telemetry.py::test_no_telemetry_calls_when_disabled
FAILED tests/test_loader_v2_telemetry.py::test_argv_provenance_failure_never_propagates
FAILED tests/test_new145_149_155_option_c.py::test_start_allow_upgrade_true_daemon_idle_kills_and_respawns
FAILED tests/test_new145_149_155_option_c.py::test_start_allow_upgrade_true_daemon_idle_releases_old_slot_on_upgrade
FAILED tests/test_new145_149_155_option_c.py::test_start_allow_upgrade_true_never_uses_killpg
15 failed, 122 passed in 2.07s
