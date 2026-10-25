"""Output-directory guard for the retained G15b hunter harness (not product code).

Every script in docs/wp2_1_g15b_harness/{A,B,C} takes its work root and its TSV/log
output location from work_root(), which REFUSES to return unless the G15Z_OUT
environment variable names an absolute scratch directory that is outside the repo
(and therefore outside docs/ and every tracked path). This is what stops a re-run
from truncating or deleting the committed docs/wp2_1_g15b_hunter_{A,B,C}.tsv reports.

Layout under $G15Z_OUT: A/, B/, C/ each holding snap/ (a snapshot of the tree under
test, built by the caller), home/, state/, ws/, work/, out/, logs/ and the hunter TSV.
"""
import os, sys

_HERE = os.path.dirname(os.path.realpath(__file__))
_REPO = os.path.realpath(os.path.join(_HERE, "..", ".."))


def _die(msg):
    sys.stderr.write("g15z_guard: REFUSING TO RUN: %s\n" % msg)
    raise SystemExit(2)


def out_dir():
    raw = os.environ.get("G15Z_OUT", "")
    if not raw:
        _die("G15Z_OUT is unset (must be an absolute scratch directory outside the repo)")
    if not os.path.isabs(raw):
        _die("G15Z_OUT must be an absolute path, got %r" % raw)
    p = os.path.realpath(raw)
    if p == _REPO or p.startswith(_REPO + os.sep):
        _die("G15Z_OUT resolves inside the repo (%s); committed reports live there" % p)
    if _REPO.startswith(p.rstrip(os.sep) + os.sep) or p == os.sep:
        _die("G15Z_OUT (%s) contains the repo; choose a dedicated scratch directory" % p)
    home = os.path.realpath(os.path.expanduser("~"))
    if p == home or home.startswith(p.rstrip(os.sep) + os.sep):
        _die("G15Z_OUT must not be HOME or an ancestor of HOME (%s)" % p)
    if p.count(os.sep) < 3:
        _die("G15Z_OUT %s is too shallow to be a dedicated scratch directory" % p)
    if os.path.exists(p) and not os.path.isdir(p):
        _die("G15Z_OUT %s exists and is not a directory" % p)
    os.makedirs(p, exist_ok=True)
    return p


def work_root(name):
    """Return (and create) $G15Z_OUT/<name> for name in A, B, C."""
    assert name in ("A", "B", "C"), name
    d = os.path.join(out_dir(), name)
    os.makedirs(d, exist_ok=True)
    return d


def tsv_path(name):
    """Hunter TSV location: $G15Z_OUT/<name>/hunter_<name>.tsv (never under the repo)."""
    return os.path.join(work_root(name), "hunter_%s.tsv" % name)
