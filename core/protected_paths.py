#!/usr/bin/env python3
"""
Shared protected-path set (WP2.1 slice G15e, Unit A).

One data module consulted by every enforcement surface, so the set cannot
drift between them. Today's consumers are core.filesystem.Filesystem (the five
mutation entry points) and tools.file_tools.classify_write_action. The shell
argv scan (Unit B) will import the same API. The shell classifier
(tools.shell_tools.classify_shell_command) deliberately does NOT use anything
here except the lifted constants: it must stay free of filesystem access.

Two tiers:
- TIER_DENY: non-repo targets (audit ledger, state dir, $HOME startup and
  credential files, `.git` components, PATH directories). File tools refuse in
  every mode; no flag, including --allow-self-mod, unlocks it. HIGH would be a
  weak control for file tools (it is unprompted in the REPL and unlocked by
  --allow-self-mod, which was granted for Codey code, not for $HOME).
- TIER_HIGH: repo targets Ish put under HIGH classification (F3: launchers,
  scripts, root config.json, non-.py plugin files). Classified HIGH_IMPACT by
  the caller, exactly like core .py files; --allow-self-mod still unlocks them.

Precedence: any matching `f3-*` row keeps HIGH even if `path-shadow` or
`config-active` also match (see F3_OVERRIDES), otherwise the executable
launchers and the repo-root config.json would silently become DENY. Every
other DENY row beats HIGH.

Everything is compared in two forms (lexical absolute path and resolved path),
alias-folded (/data/user/0 <-> /data/data) and casefolded. Dynamic inputs
(audit sink, active config path, state dir, HOME, PATH) are read at CALL time
by build_context(), never cached at import. The module performs no filesystem
discovery except the injected `listdir` / `is_exec` callables and a `resolve()`
of its own entries, so unit tests drive it with recording fakes.
"""

import fnmatch
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, FrozenSet, Iterable, List, Optional, Tuple

TIER_DENY = "deny"
TIER_HIGH = "high"

# Shared system executable directories (G15d R8, moved verbatim from
# tools/shell_tools.py, which re-exports it under its old name). Hard-coded,
# not derived from $PREFIX, because the shell classifier must not read the
# environment. `/system/bin` is included because `/bin` is a symlink to it on
# this device. A naming convention, NOT an ownership boundary: the Termux bin
# dir is writable by the agent's own uid, which is why it is also a
# `path-dedicated` DENY subtree below.
SYSTEM_BIN_DIRS = frozenset({
    "/bin", "/sbin", "/usr/bin", "/usr/sbin", "/usr/local/bin",
    "/system/bin", "/system/xbin",
    "/data/data/com.termux/files/usr/bin",
})

# D-2 option (b), credential set (G15d 3.2b), moved verbatim from
# tools/shell_tools.py. Entries under $HOME (equal or descendant). Why:
# private keys, API/registry tokens, cloud and VCS credential stores, and
# shell history (can embed secrets typed on a command line). The write side
# (`home-credential`) reuses CRED_HOME_ENTRIES.
CRED_HOME_ENTRIES = (
    ".ssh", ".netrc", ".git-credentials", ".gnupg", ".aws", ".kube",
    ".npmrc", ".pypirc", ".docker/config.json", ".config/gh",
    ".config/gcloud", ".config/git/credentials",
    ".bash_history", ".zsh_history",
)
# Entries directly under the Codey state dir (and under ~/.codeyOS, the usual
# default, so an overridden CODEY_STATE_DIR does not unprotect it). Why: the
# age key, tunnel-token fallback config, GCP creds, internal service tokens.
CRED_STATE_ENTRIES = (
    "age.key", "config.json", "gcp_credentials.json",
    "aigentik_internal_token", "ccos_crm_read_token",
)
# fnmatch patterns for names directly under the state dir: encrypted secrets
# and the Restoricon database with its -wal/-shm/-journal siblings (PII).
CRED_STATE_PATTERNS = ("*.age", "restoricon.db*")
# Basename patterns, any directory, applied ONLY to candidates that exist on
# disk (otherwise a search pattern such as `grep -rn .env src` would be HIGH).
# Same family as core/context.py's default ignore list. `.pub` is excluded.
CRED_BASENAME_PATTERNS = (
    ".env", ".env.*", "*.pem", "*.key",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
)
# This device exposes the same tree as /data/data/<pkg> and /data/user/0/<pkg>
# (same st_ino/st_dev) and realpath() does not collapse one to the other, so
# both spellings are folded to the first before any comparison. User 0 only:
# it is the only alias observed.
CRED_PATH_ALIASES = (("/data/user/0/", "/data/data/"),)


def canon(path: str) -> str:
    """Normalize a path string and fold the known device alias prefixes."""
    path = os.path.normpath(path)
    for alias, target in CRED_PATH_ALIASES:
        if path.startswith(alias):
            return target + path[len(alias):]
    return path


def fold(path: str) -> str:
    """`canon` plus casefold: what every protected-set comparison uses, so a
    case-insensitive mount (e.g. fuse /sdcard) cannot dodge an entry."""
    return canon(path).casefold()


# ---------------------------------------------------------------------------
# Data rows. Each row carries a one-line why; evidence ids are G15b/NEW ids.
# ---------------------------------------------------------------------------

# home-startup: executes at the operator's next shell (B:HM-01). Only .bashrc
# and friends exist on this device; the rest is creation-protection.
HOME_STARTUP_FILES = (
    ".bashrc", ".bash_profile", ".bash_login", ".profile", ".bash_logout",
    ".inputrc", ".zshrc", ".zshenv", ".zprofile", ".zlogin", ".zlogout",
    ".vimrc", ".tmux.conf", ".nanorc",
)
HOME_STARTUP_SUBTREES = (".config/fish",)
# home-git: core.hooksPath, aliases, core.sshCommand (A:G11-G13; B:HM-04).
HOME_GIT_FILES = (".gitconfig",)
HOME_GIT_SUBTREES = (".config/git",)
# home-termux: boot scripts, termux.properties, shell override (B:HM-02).
HOME_TERMUX_SUBTREES = (".termux", ".shortcuts")
# path-dedicated: directories that exist only to hold commands. A planted
# executable shadows a command in the operator's shell (Ish Q2, NEW-1037).
HOME_BIN_SUBTREES = ("bin", ".local/bin", "google-cloud-sdk/bin")
# Mixed PATH directories under $HOME (Ish Q2): only direct children examined.
HOME_MIXED_DIRS = ("Codey-v4",)

# F3 (Ish 2026-10-23): HIGH write classification for repo files that run or
# configure the system. `codey-metrics` is a tracked bash launcher of the same
# class (spec Q4 default yes). Folded names, direct children of CODE_DIR.
F3_LAUNCHERS = (
    "main.py", "codey", "codeyos", "codeydos", "codey-start", "codey-stop",
    "codey-metrics",
)
F3_PLUGIN_ROOT = "ccos/plugins/"
F3_OVERRIDES = frozenset({"path-shadow", "config-active"})

# --- G15e Unit C: Ish-accepted data rows (decisions 2026-10-23/24) ----------
# bench-evaluator (G15f Q1): `bench/**`, EVERY suffix at every depth, HIGH. The
# evaluator is the thing that scores the agent, so a write to its lock file,
# scorecards, task yaml or hidden tests is score tampering (G15b-29); the
# `.py`-only is_core_file rule missed all of the non-.py files. Repo-relative.
BENCH_EVALUATOR_SUBTREES: Tuple[str, ...] = ("bench",)
# d7-authority (D-7, Ish 2026-10-24): files that decide who may do what. HIGH,
# so --allow-self-mod still unlocks them. Repo-relative; an entry containing a
# glob character is `<dir>/<pattern>` and matches the first path component
# below <dir> (so `authority*.py` matches `authority.py` and
# `authority_policy.py`, not the rest of restoricon_core). Queued, NOT added:
# telemetry/store.py, pipeline/run.py, codey_estimator/__init__.py.
# NEW-1016 friction, stated plainly: Track B edits to restoricon_core/
# authority*.py through the file tools or the shell now need --allow-self-mod
# (or the operator's own editor) in confirm-less modes such as --yolo.
D7_HIGH_ENTRIES: Tuple[str, ...] = ("ccos/core", "restoricon_core/authority*.py")

# C-1 (Ish 2026-10-24): `$PREFIX/etc/**` (bash.bashrc, profile, profile.d/*)
# runs at every login shell, mode 600 and writable by the agent uid. Non-repo,
# so DENY (file tools refuse in every mode; HIGH would be unlocked by
# --allow-self-mod, which was granted for Codey code, not for system config).
PREFIX_ETC_SUBTREE = "etc"
DEFAULT_PREFIX = "/data/data/com.termux/files/usr"
# C-2: `.pth` files (lines starting `import` run at EVERY interpreter start,
# including the daemon), `sitecustomize` and `usercustomize`, as a direct child
# of any site-packages / dist-packages directory (system site, user site,
# venvs). DENY: not repo code. Accepted false positive: pip-managed `.pth`
# files inside a workspace venv are not writable through the file tools.
SITE_DIR_NAMES = ("site-packages", "dist-packages")
SITE_STARTUP_STEMS = ("sitecustomize", "usercustomize")
# C-3, non-repo half (DENY): peer-agent config and the Codey session store.
# Agent configs hold hooks, MCP server commands and permission lists that a
# peer agent executes with the operator's authority (same class as .bashrc);
# ~/.codey_sessions holds forged-session material (B:HM-07). `.claude*` covers
# ~/.claude/ and ~/.claude.json(.backup). Operator-owned paths stay writable:
# Codey's own session/taskqueue code and the dashboard write these with plain
# IO (never core.filesystem), and CODEY.md / .codeyignore / notes are not here.
PEER_AGENT_HOME_SUBTREES = (
    ".qwen", ".codex", ".gemini", ".config/opencode", ".config/mimocode",
    ".codey_sessions",
)
PEER_AGENT_HOME_GLOBS = (".claude*",)
# C-3, repo half (HIGH): the checked-in `.claude/` and `.qwen/` of $CODE_DIR
# are repo targets, so they follow the repo tier (--allow-self-mod unlocks).
PEER_AGENT_REPO_SUBTREES = (".claude", ".qwen")

RULE_GIT = "git-component"


@dataclass(frozen=True)
class Hit:
    tier: str
    rule: str


@dataclass(frozen=True)
class Entry:
    kind: str  # "file" | "subtree" | "glob"
    value: str  # fold()ed absolute path (for "glob": the directory)
    tier: str
    rule: str
    runner_exempt: bool = False
    shell_only: bool = False
    pattern: str = ""  # kind "glob": fnmatch pattern for the first component below `value`


@dataclass(frozen=True)
class Context:
    """Immutable snapshot of the protected set for one decision. Never cache a
    Context across calls: its inputs are read at call time on purpose."""

    entries: Tuple[Entry, ...]
    code_roots: Tuple[str, ...]  # fold()ed CODE_DIR (lexical + resolved)
    core_roots: Tuple[str, ...]  # fold()ed core-classification roots (rel)
    bases: Tuple[str, ...]  # fold()ed workspace/CODE_DIR bases for .git rule
    mixed_dirs: Tuple[Tuple[str, str], ...]  # (canon path, fold path)
    shadow_dirs: Tuple[Tuple[str, str, bool], ...]  # (canon, fold, mixed) listed for shadow names
    listdir: Callable = os.listdir
    is_exec: Callable = None
    _cache: Dict = field(default_factory=dict)


def _default_is_exec(path: str) -> bool:
    """True for an existing REGULAR file with any exec bit. Directories are
    excluded: they carry x bits, and counting them would make every repo
    subdirectory (a direct child of the mixed repo-root PATH dir) a shadow."""
    try:
        mode = os.stat(path).st_mode
        return stat.S_ISREG(mode) and bool(mode & 0o111)
    except OSError:
        # Cannot stat (absent, unreadable): not an existing executable. The
        # name-collision half of path-shadow still applies, so failing to
        # stat only narrows, never widens, what is allowed.
        return False


def _forms_of(p) -> List[str]:
    """Lexical and resolved spellings of a context entry (deduplicated)."""
    s = str(p)
    out = [s]
    try:
        r = str(Path(s).resolve())
        if r != s:
            out.append(r)
    except (OSError, ValueError, RuntimeError):
        # Entry kept in lexical form only; the candidate side still checks
        # both of its own forms, so this narrows rather than disables.
        pass
    return out


def build_context(*, code_dir, workspace_root=None, home=None, state_dir=None,
                  audit=None, config_paths=None, path_env=None,
                  listdir=os.listdir, is_exec=_default_is_exec) -> Context:
    """Snapshot the protected set. Reads at call time: $HOME, the state dir
    (utils.config.CODEY_STATE_DIR attribute and the env var), the audit sink
    (core.action_gateway.audit_path()), the active config path and PATH.
    `code_dir` is passed in by each caller from its own module global because
    the existing suites monkeypatch those module attributes. Performs no
    listdir/stat: those happen lazily, behind the injected callables.
    """
    import utils.config as _config
    from core.checkpoint import CORE_CLASSIFICATION_ROOTS

    home_p = Path(home) if home is not None else Path.home()
    code_p = Path(code_dir)

    state_dirs: List[Path] = []
    if state_dir is not None:
        state_dirs.append(Path(state_dir))
    else:
        state_dirs.append(Path(_config.CODEY_STATE_DIR))
        env_state = os.environ.get("CODEY_STATE_DIR")
        if env_state:
            state_dirs.append(Path(env_state))
    state_dirs.append(home_p / ".codeyOS")

    if audit is None:
        from core.action_gateway import audit_path

        audit_list = [audit_path()]
    else:
        audit_list = [Path(audit)]
    for sd in state_dirs:
        audit_list.append(sd / "action_gateway_audit.jsonl")

    if config_paths is None:
        cfg: List[Path] = [_config.get_config_file_path()]
        env_cfg = os.environ.get("CODEY_CONFIG_PATH")
        if env_cfg and env_cfg.strip():
            cfg.append(Path(env_cfg.strip()).expanduser())
    else:
        cfg = [Path(c) for c in config_paths]

    entries: List[Entry] = []
    seen = set()

    def add(kind, p, tier, rule, **kw):
        for form in _forms_of(p):
            f = fold(form)
            key = (kind, f, rule)
            if key in seen:
                continue
            seen.add(key)
            entries.append(Entry(kind, f, tier, rule, **kw))

    for a in audit_list:
        add("file", a, TIER_DENY, "audit-sink")
    for sd in state_dirs:
        add("subtree", sd, TIER_DENY, "state-dir")
    for c in cfg:
        add("file", c, TIER_DENY, "config-active")
    for name in HOME_STARTUP_FILES:
        add("file", home_p / name, TIER_DENY, "home-startup")
    for rel in HOME_STARTUP_SUBTREES:
        add("subtree", home_p / rel, TIER_DENY, "home-startup")
    for rel in CRED_HOME_ENTRIES:
        # Subtree covers both the exact file entries and the directories.
        add("subtree", home_p / rel, TIER_DENY, "home-credential")
    for name in HOME_GIT_FILES:
        add("file", home_p / name, TIER_DENY, "home-git")
    for rel in HOME_GIT_SUBTREES:
        add("subtree", home_p / rel, TIER_DENY, "home-git")
    for rel in HOME_TERMUX_SUBTREES:
        add("subtree", home_p / rel, TIER_DENY, "home-termux")

    # PATH directories (Ish Q2). Fixed list unioned with absolute PATH entries.
    dedicated: List[str] = [str(home_p / rel) for rel in HOME_BIN_SUBTREES]
    dedicated.extend(sorted(SYSTEM_BIN_DIRS))
    mixed: List[str] = [str(code_p)] + [str(home_p / rel) for rel in HOME_MIXED_DIRS]
    pe = os.environ.get("PATH", "") if path_env is None else path_env
    for entry in pe.split(os.pathsep):
        # Relative and empty entries are ignored (residual): resolving them
        # against the agent cwd would shadow-protect ordinary workspace files.
        if not entry or not entry.startswith("/"):
            continue
        if os.path.basename(os.path.normpath(entry)) in ("bin", "sbin"):
            dedicated.append(entry)
        else:
            mixed.append(entry)
    for d in dedicated:
        add("subtree", d, TIER_DENY, "path-dedicated")
    dedicated_folds = {fold(f) for d in dedicated for f in _forms_of(d)}

    mixed_dirs: List[Tuple[str, str]] = []
    for d in mixed:
        for form in _forms_of(d):
            f = fold(form)
            if f in dedicated_folds or any(f == m[1] for m in mixed_dirs):
                continue
            mixed_dirs.append((canon(form), f))
    shadow_dirs: List[Tuple[str, str, bool]] = [(c, f, True) for c, f in mixed_dirs]
    for d in dedicated:
        for form in _forms_of(d):
            shadow_dirs.append((canon(form), fold(form), False))

    for rel in BENCH_EVALUATOR_SUBTREES:
        add("subtree", code_p / rel, TIER_HIGH, "bench-evaluator", runner_exempt=True)
    for rel in D7_HIGH_ENTRIES:
        if any(ch in rel for ch in "*?["):
            parent_rel, _, pat = rel.rpartition("/")
            add("glob", code_p / parent_rel, TIER_HIGH, "d7-authority",
                runner_exempt=True, pattern=pat.casefold())
        else:
            add("subtree", code_p / rel, TIER_HIGH, "d7-authority", runner_exempt=True)

    # C-1: $PREFIX/etc (env PREFIX read at call time, plus the Termux default so
    # an unset/overridden PREFIX does not unprotect it).
    prefixes = [DEFAULT_PREFIX]
    env_prefix = os.environ.get("PREFIX")
    if env_prefix and env_prefix.startswith("/"):
        prefixes.append(env_prefix)
    for pre in prefixes:
        add("subtree", Path(pre) / PREFIX_ETC_SUBTREE, TIER_DENY, "prefix-etc")
    # C-3
    for rel in PEER_AGENT_HOME_SUBTREES:
        add("subtree", home_p / rel, TIER_DENY, "peer-agent-config")
    for pat in PEER_AGENT_HOME_GLOBS:
        add("glob", home_p, TIER_DENY, "peer-agent-config", pattern=pat.casefold())
    for rel in PEER_AGENT_REPO_SUBTREES:
        add("subtree", code_p / rel, TIER_HIGH, "peer-agent-repo")

    code_roots = tuple(dict.fromkeys(fold(f) for f in _forms_of(code_p)))
    bases = [fold(f) for f in _forms_of(code_p)]
    if workspace_root is not None:
        bases.extend(fold(f) for f in _forms_of(workspace_root))
    return Context(
        entries=tuple(entries),
        code_roots=code_roots,
        core_roots=tuple(fold(r) for r in CORE_CLASSIFICATION_ROOTS),
        bases=tuple(dict.fromkeys(bases)),
        mixed_dirs=tuple(mixed_dirs),
        shadow_dirs=tuple(shadow_dirs),
        listdir=listdir,
        is_exec=is_exec,
    )


def has_git_component(path: str, bases: Iterable[str] = ()) -> bool:
    """True when any component of `path` is `.git` (casefolded, trailing dots
    and spaces ignored, as FAT-style aliasing would). Components are measured
    BELOW the longest base that is an ancestor of the path (the workspace and
    CODE_DIR), so a workspace that itself lives under a directory named `.git`
    does not deny every write, while nested repos, sibling repos outside both
    roots and `.GIT` variants all hit. Unicode-ignorable code points
    (HFS+-style) are a documented residual.
    """
    f = fold(path)
    best = ""
    for b in bases:
        bf = fold(b) if b else ""
        if bf and (f == bf or f.startswith(bf.rstrip("/") + "/")) and len(bf) > len(best):
            best = bf
    rest = f[len(best):] if best else f
    return any(part.rstrip(". ") == ".git" for part in rest.split("/") if part)


def _under(f: str, root: str) -> bool:
    return f == root or f.startswith(root.rstrip("/") + "/")


def shadow_names(ctx: Context, exclude: str) -> FrozenSet[str]:
    """Casefolded command names present in the PATH directories other than
    `exclude` (a fold()ed mixed dir). Lazy: each directory is listed at most
    once per Context, and only when a candidate is a direct child of a mixed
    dir. Incomplete by construction: /system/bin raises PermissionError here,
    and a listing error only removes names from the set (the is_exec half of
    path-shadow still applies), so swallowing it narrows, never widens, what
    is allowed.
    """
    names = set()
    for canon_dir, folded, is_mixed in ctx.shadow_dirs:
        if folded == exclude:
            continue
        listing = ctx._cache.get(folded)
        if listing is None:
            try:
                raw = ctx.listdir(canon_dir)
                if is_mixed:
                    # A mixed directory (repo root, ~/Codey-v4) also holds
                    # ordinary files and subdirectories; only an existing
                    # executable there is a command another dir could shadow.
                    raw = [n for n in raw if ctx.is_exec(os.path.join(canon_dir, n))]
                listing = frozenset(n.casefold() for n in raw)
            except OSError:
                listing = frozenset()
            ctx._cache[folded] = listing
        names |= listing
    return frozenset(names)


def _site_startup(f: str) -> bool:
    """C-2: `*.pth`, `sitecustomize*`, `usercustomize*` (file, or a package
    directory and everything below it) directly inside a site-packages or
    dist-packages directory. `f` is fold()ed. Dynamic like the `.git` rule, so
    it is not ancestor-checked."""
    parts = [p for p in f.split("/") if p]
    for i, comp in enumerate(parts[:-1]):
        if comp in SITE_DIR_NAMES:
            first = parts[i + 1]
            if first.endswith(".pth") or first.split(".")[0] in SITE_STARTUP_STEMS:
                return True
    return False


def _repo_hits(f: str, ctx: Context) -> List[Hit]:
    hits: List[Hit] = []
    for root in ctx.code_roots:
        if not f.startswith(root.rstrip("/") + "/"):
            continue
        rel = f[len(root.rstrip("/")) + 1:]
        if rel in F3_LAUNCHERS:
            hits.append(Hit(TIER_HIGH, "f3-launcher"))
        if rel.endswith(".sh") or rel.startswith("lib/"):
            hits.append(Hit(TIER_HIGH, "f3-script"))
        if rel == "config.json":
            hits.append(Hit(TIER_HIGH, "f3-config"))
        if rel.startswith(F3_PLUGIN_ROOT) and not rel.endswith(".py"):
            hits.append(Hit(TIER_HIGH, "f3-plugin-data"))
    return hits


def _matches(form: str, ctx: Context, *, shell: bool) -> List[Hit]:
    f = fold(form)
    hits: List[Hit] = []
    if has_git_component(form, ctx.bases):
        hits.append(Hit(TIER_DENY, RULE_GIT))
    for e in ctx.entries:
        if e.shell_only and not shell:
            continue
        if (e.kind == "file" and f == e.value) or (e.kind == "subtree" and _under(f, e.value)):
            hits.append(Hit(e.tier, e.rule))
        elif e.kind == "glob" and f.startswith(e.value.rstrip("/") + "/"):
            first = f[len(e.value.rstrip("/")) + 1:].split("/", 1)[0]
            if fnmatch.fnmatchcase(first, e.pattern):
                hits.append(Hit(e.tier, e.rule))
    if _site_startup(f):
        hits.append(Hit(TIER_DENY, "site-startup"))
    hits.extend(_repo_hits(f, ctx))
    if shell:
        for root in ctx.code_roots:
            if f.endswith(".py") and f.startswith(root.rstrip("/") + "/"):
                rel = f[len(root.rstrip("/")) + 1:]
                if any(rel.startswith(c.rstrip("/") + "/") for c in ctx.core_roots):
                    hits.append(Hit(TIER_HIGH, "core-py-mirror"))
    parent, _, name = f.rpartition("/")
    for canon_dir, folded in ctx.mixed_dirs:
        if parent == folded and name:
            if name in shadow_names(ctx, folded) or ctx.is_exec(canon(form)):
                hits.append(Hit(TIER_DENY, "path-shadow"))
            break
    return hits


def first_hit(forms: Iterable[str], ctx: Context, *, shell: bool = False,
              skip: FrozenSet[str] = frozenset()) -> Optional[Hit]:
    """Strongest hit over all `forms` (lexical, resolved). `shell=True` also
    evaluates shell-only rows (`core-py-mirror`); file tools get that from
    is_core_file. DENY beats HIGH, except that a matching `f3-*` row on a
    form drops F3_OVERRIDES hits of that same form so the executable launchers and the repo-root
    config.json keep their decided HIGH tier. Rules named in `skip` are
    ignored (file-tool classification skips `git-component`, see
    classify_write_action).
    """
    hits: List[Hit] = []
    for form in forms:
        fh = [h for h in _matches(form, ctx, shell=shell) if h.rule not in skip]
        # The F3 override is PER FORM: an f3-* hit on one spelling suppresses
        # override rules only on that same spelling. Pooling across forms let a
        # symlink `lib/x.sh -> <active config>` (lexical f3-script, resolved
        # config-active) drop the DENY and be unlocked by --allow-self-mod.
        if any(h.rule.startswith("f3-") for h in fh):
            fh = [h for h in fh if h.rule not in F3_OVERRIDES]
        hits.extend(fh)
    if not hits:
        return None
    for h in hits:
        if h.tier == TIER_DENY:
            return h
    return hits[0] if hits else None


def ancestor_hit(forms: Iterable[str], ctx: Context) -> Optional[Hit]:
    """A form equal to, or a parent of, an exact entry, subtree root, F3
    launcher or PATH directory (for rm, mv, cp, ln, chmod: `rm -rf ~`).
    Only enumerable entries are checked; the dynamic rules (`.git`
    component, `*.sh`, core-py-mirror) are not (documented residual).
    """
    targets: List[Tuple[str, Hit]] = [(e.value, Hit(e.tier, e.rule)) for e in ctx.entries]
    for root in ctx.code_roots:
        for name in F3_LAUNCHERS:
            targets.append((root.rstrip("/") + "/" + name, Hit(TIER_HIGH, "f3-launcher")))
    best: Optional[Hit] = None
    for form in forms:
        f = fold(form)
        for value, hit in targets:
            if _under(value, f):
                if hit.tier == TIER_DENY:
                    return hit
                best = best or hit
    return best


# ---------------------------------------------------------------------------
# Read side (G15e Unit C, Q7b): credential files must not be returned by the
# file tools' read path (Filesystem.read, patch_file's pre-read). This is the
# D-2 option (b) credential set (the same CRED_* constants the shell scan uses)
# applied to a single resolved target. Deliberately NOT included: the
# CRED_BASENAME_PATTERNS (.env*, *.pem, *.key, id_rsa*): the shell scan applies
# them to existing operands only, `.env.example`/`*.key` fixtures are ordinary
# workspace files the agent legitimately reads, and G15b-39 owns that gap.
# ---------------------------------------------------------------------------

def _is_proc_secret(f: str) -> bool:
    """`/proc/{self,thread-self,<digits>}/<something>`: environ, cmdline, mem,
    fd/N, root/... expose another process's secrets. `/proc/cpuinfo` stays
    readable. Same rule as tools.shell_tools._cred_is_proc_secret (pid dir
    itself excluded: a file read of a directory fails anyway)."""
    pieces = f.split("/")
    if len(pieces) < 4 or pieces[0] != "" or pieces[1] != "proc":
        return False
    who = pieces[2]
    return who in ("self", "thread-self") or who.isdigit()


def credential_read_hit(forms: Iterable[str], *, home=None, state_dirs=None) -> Optional[str]:
    """Rule id when any of `forms` (lexical, resolved absolute paths) names a
    credential-bearing file, else None. Entries are compared in both
    spellings, alias-folded and casefolded. `home` / `state_dirs` default to
    call-time values ($HOME, utils.config.CODEY_STATE_DIR, the env var and
    ~/.codeyOS, as the shell scan does). Raises nothing for ordinary input;
    the caller treats any exception as a denial (fail closed).
    """
    import utils.config as _config

    home_p = Path(home) if home is not None else Path.home()
    if state_dirs is None:
        sds = [Path(_config.CODEY_STATE_DIR), home_p / ".codeyOS"]
        env_state = os.environ.get("CODEY_STATE_DIR")
        if env_state:
            sds.append(Path(env_state))
    else:
        sds = [Path(d) for d in state_dirs]

    subtrees: List[str] = []
    for rel in CRED_HOME_ENTRIES:
        for form in _forms_of(home_p / rel):
            subtrees.append(fold(form))
    roots: List[str] = []
    for sd in sds:
        for form in _forms_of(sd):
            roots.append(fold(form))
        for name in CRED_STATE_ENTRIES:
            for form in _forms_of(sd / name):
                subtrees.append(fold(form))

    for raw in forms:
        f = fold(raw)
        if any(_under(f, e) for e in subtrees):
            return "credential-file"
        if _is_proc_secret(f):
            return "proc-secret"
        parent, _, name = f.rpartition("/")
        if parent in roots and any(
            fnmatch.fnmatchcase(name, pat.casefold()) for pat in CRED_STATE_PATTERNS
        ):
            return "credential-file"
    return None
