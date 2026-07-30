"""
NEW-10 regression test: main.py had no SIGTERM handler at all, leaving
SIGTERM's disposition at SIG_DFL (immediate kernel-level termination that
never reaches Python bytecode, never raises anything, and bypasses every
`except (KeyboardInterrupt, SystemExit): shutdown()` guard in main.py --
including mid-model-load, where an orphaned llama-server child is the real
cost).

The fix installs an explicit signal.signal(signal.SIGTERM, ...) handler as
the first thing main() does, whose only job is to raise SystemExit -- the
same mechanism Python's own default SIGINT handler already uses, so the
4 existing `except (KeyboardInterrupt, SystemExit): ... shutdown()` guards
around main.py's loader.load_primary() calls catch SIGTERM for free with
zero new shutdown-calling logic. Two other REPL code paths are NOT
covered by this fix (no SystemExit-catching guard exists there to reuse)
-- see NEW-40 in NEW_ISSUES.md.

See NEW_ISSUES.md NEW-10 (this fix) and NEW-40 (known coverage gap) for
full context.
"""
import signal

import pytest

import main


def test_sigterm_handler_raises_system_exit():
    """The handler itself must do nothing but raise -- no shutdown(), no I/O."""
    with pytest.raises(SystemExit) as excinfo:
        main._sigterm_handler(signal.SIGTERM, None)
    # 128 + signum (POSIX "terminated by signal N" convention), not 0 --
    # so an uncaught propagation (the two REPL paths logged as NEW-40)
    # still reports "killed by a signal" rather than a false clean exit.
    assert excinfo.value.code == 128 + signal.SIGTERM


def test_main_installs_sigterm_handler_before_any_branch_logic(monkeypatch):
    """
    Exercise the real main() entry point (not just the handler function in
    isolation) to confirm the signal.signal() call actually happens, and
    happens before any argument-dependent branch -- not just somewhere in
    main(). Disposition is reset to SIG_DFL first, and --version is the
    first branch checked and exits (via sys.exit(0), raising SystemExit)
    immediately: if the handler installation were moved to after the
    --version check instead of before it, sys.exit(0) would fire first,
    getsignal(SIGTERM) would still read SIG_DFL, and the final assertion
    below would correctly fail -- so this test does verify placement, not
    just that the handler is installed somewhere in main().
    """
    original_disposition = signal.getsignal(signal.SIGTERM)
    try:
        # Reset to SIG_DFL to make sure we're not accidentally reusing a
        # handler installed by a previous test/import in this same process.
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

        monkeypatch.setattr(main.sys, "argv", ["main.py", "--version"])
        with pytest.raises(SystemExit):
            main.main()

        assert signal.getsignal(signal.SIGTERM) is main._sigterm_handler
    finally:
        signal.signal(signal.SIGTERM, original_disposition)


def test_sigint_handling_is_unmodified():
    """
    This fix must not touch SIGINT's disposition -- Python's own default
    SIGINT -> KeyboardInterrupt translation should be untouched.
    """
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler
