"""Export hygiene for fine-tune datasets (always on inside export_dataset).

Drops, never edits, examples that must not be trained on:
  * truncated  -- contain the oversize-omitted marker (legacy "...[truncated]" rows are
                  detected at their source, core.finetune_prep.curate_verified, because
                  that text also appears legitimately mid-prompt)
  * secret     -- match a credential pattern (SECRET_PATTERNS)
  * oversize   -- longer than an optional max_example_chars policy
  * duplicate  -- identical content (metadata ignored); first occurrence kept

Why drop beats redact: a redacted example teaches the model to emit placeholder
junk, and redaction can miss encodings of the same secret. Dropping the whole
example is the only fail-safe outcome. Likewise nothing is ever truncated.

False-negative policy (accepted): letters-only values for token keys (e.g.
{"token": "abcdefghijklmnopqrstuvwxyz"}) and all-lowercase `mysql -p` passwords are
NOT caught -- requiring a digit/uppercase is what keeps ordinary prose and code clean.

False-positive policy: patterns favor precision on literal values (long
quoted/assigned strings, known token prefixes). Plain references such as
os.environ["X"], short values, PUBLIC KEY headers and PWD are kept. A wrongly
dropped example costs one training sample; a leaked secret is unrecoverable, so
when in doubt a borderline literal is dropped.

Fail closed: exceptions during scanning propagate to the caller. Matched text
is never logged or returned -- only the pattern name.
"""
import hashlib
import json
import re
from typing import Dict, List, Optional, Tuple

from core.trajectory import OVERSIZE_MARKER_PREFIX

TRUNCATION_MARKERS = (OVERSIZE_MARKER_PREFIX,)

_Q = r'\\*["\']'
_KW = (r'(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token'
       r'|client[_-]?secret|private[_-]?key)[A-Za-z0-9_\-]{0,32}')
_KW_YAML = (r'(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token'
            r'|client[_-]?secret|private[_-]?key)')
# Quoted values that are obviously not literals: all '*', paths, shell/template refs, ENV_VAR names.
# Also type annotations (Optional[...], Callable ...), which appear as quoted values in code.
_VAL_GUARD = (r'(?![/~${])(?!\[REDACTED(?::\w+)?\](?:["\'\s,}\\]|$))(?!\*+(?:["\'\\\s]|$))(?![^"\'\s]{0,200}\.\.\.)'
              r'(?!(?-i:[A-Z][A-Z0-9]*_[A-Z0-9_]*)(?:["\'\\\s]|$))'
              r'(?!(?-i:Optional|List|Dict|Union|Callable|Any|Tuple|Set|Type)\b)')
# Shared by the env-style patterns: value must not be a code expression, path or placeholder.
_ENV_VAL = (r'(?![/~]|\./)(?!os\.)(?![^\s]{0,200}\.\.\.)'
            r'(?![A-Za-z_][A-Za-z0-9_.]{0,100}(?:[(\[]|[ \t]+/))(?![^\s]{0,200}\.[A-Za-z_][A-Za-z0-9_]*\()'
            r'[^\s"\'$\\\[\](){}]{8,}(?![^\s"\'$\\\[\](){}]|[(\[])')
_ENV_NAME = (r'[A-Z0-9_]{0,32}(?:PASSWORD|PASSWD|SECRET|API_?KEY|TOKEN|PRIVATE_?KEY|MYSQL_PWD)[A-Z0-9_]{0,32}')
_EOL = r'(?=[ \t]*(?:\r?$|\\))'
_TOK_VAL = (r'(?=[A-Za-z0-9_\-+/=.]{0,200}[0-9])(?=[A-Za-z0-9_\-+/=.]{0,200}[A-Za-z])')
# NOTE on performance: every pattern must be linear on adversarial input (1MB of one char,
# repeated keywords...). Hence bounded repeats {0,64} and lookbehind-anchored run starts.
SECRET_PATTERNS = tuple((n, re.compile(r)) for n, r in (
    ("private_key", r'-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY'),
    ("aws_access_key_id", r'\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b'),
    ("aws_secret_access_key", r'(?i)aws_?secret_?access_?key' + _Q + r'?\s*[:=]\s*' + _Q + r'?[A-Za-z0-9/+=]{40}'),
    ("gcp_api_key", r'\bAIza[0-9A-Za-z_\-]{35}'),
    ("gcp_oauth_token", r'\bya29\.[0-9A-Za-z_\-]{20,}'),
    ("anthropic_key", r'\bsk-ant-[A-Za-z0-9_\-]{20,}'),
    ("openai_key", r'\bsk-(?:proj-|svcacct-|admin-)?(?:(?=[A-Za-z0-9_\-]{0,64}[0-9])(?=[A-Za-z0-9_\-]{0,64}[A-Z])[A-Za-z0-9_\-]{20,}|[A-Za-z0-9]{32,})'),
    ("openrouter_key", r'\bsk-or-(?:v1-)?[A-Za-z0-9_\-]{20,}'),
    ("huggingface_token", r'\bhf_[A-Za-z0-9]{30,}'),
    ("github_token", r'\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})'),
    ("gitlab_token", r'\bglpat-[A-Za-z0-9_\-]{20,}'),
    ("npm_token", r'\bnpm_[A-Za-z0-9]{36}'),
    ("stripe_key", r'\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}'),
    ("slack_token", r'\bxox[abprs]-[A-Za-z0-9\-]{10,}'),
    ("jwt", r'(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}'),
    ("bearer_token", r'(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{20,}=*'),
    ("basic_auth_header", r'(?i)\bbasic\s+(?=[A-Za-z0-9+/]{0,512}[0-9+/=])[A-Za-z0-9+/]{16,}={0,2}'),
    ("url_credentials", r'(?<![a-z0-9+.\-])[a-z][a-z0-9+.\-]{0,31}://[^/\s:@"\'\\]{0,128}:(?![%{$])[^/\s@"\'\\]{1,256}@'),
    ("quoted_secret_assignment", r'(?i)' + _KW + _Q + r'?\s*[:=]\s*' + _Q + _VAL_GUARD + r'[^"\'\\\s]{8,}'),
    # token keys (csrf_token, next_token, token): only when the value looks secret-shaped
    # (>=16 chars of letters AND digits); short/placeholder values are kept.
    ("quoted_token_assignment", r'(?i)token' + _Q + r'?\s*[:=]\s*' + _Q + _VAL_GUARD
     + r'(?=[A-Za-z0-9_\-+/=.]{0,200}[0-9])(?=[A-Za-z0-9_\-+/=.]{0,200}[A-Za-z])[A-Za-z0-9_\-+/=.]{16,}'),
    # YAML `key: value`: value must contain a digit/symbol, no dotted refs, nothing after it
    # on the line (prose). Keeps typed code like `api_key: SecretStr`.
    ("yaml_secret_assignment", r'(?im)^[ \t]*[A-Za-z0-9_\-]{0,32}' + _KW_YAML + r'[A-Za-z0-9_\-]{0,32}[ \t]*:[ \t]+'
     r'(?![${*~/])(?!os\.)(?![^\s]{0,200}[A-Za-z_]\.[A-Za-z_])'
     r'(?!(?-i:[a-z]+(?:[A-Z][a-z]+)+|(?:[A-Z][a-z]*){2,})' + _EOL + r')'
     r'(?:(?=[^\s]{0,200}[0-9!@#%^&*+=?<>|])[^\s"\'\\\[\](){},;]{8,}|[A-Za-z]{12,})' + _EOL),
    ("yaml_token_assignment", r'(?im)^[ \t]*[A-Za-z0-9_\-]{0,32}token[ \t]*:[ \t]+' + _TOK_VAL
     + r'[A-Za-z0-9_\-+/=.]{16,}' + _EOL),
    # `-H 'x-api-key: <32+ random>'` style headers
    ("header_secret", r'(?i)(?:api[_-]?key|auth[_-]?token|access[_-]?token)[ \t]*:[ \t]*(?![$%{/~])' + _TOK_VAL
     + r'[A-Za-z0-9_\-+/=.]{32,}'),
    # inline `docker run -e NAME=value` / `--env NAME=value`
    ("inline_env_secret", r'(?<![A-Za-z0-9_\-])(?:-e|--env)[ \t]+' + _ENV_NAME + r'=' + _ENV_VAL),
    ("password_flag", r'(?<![A-Za-z0-9_\-])--(?:password|passwd|pass|api-?key|secret|access-?token|auth-?token|client-?secret)'
     r'=(?![$"\'\\\s%{/~])[^\s"\'\\]{8,}'),
    ("env_secret_assignment", r'(?m)^[ \t]*(?:export[ \t]+)?' + _ENV_NAME + r'[ \t]*=[ \t]*' + _ENV_VAL),
    # mysql-ish command, then up to 12 tokens (options, their values, positionals), then -pPASSWORD.
    # 12 covers `mysql -h HOST -P PORT -u USER --opt ... -pPASS`; still bounded, so linear.
    ("mysql_password_flag", r'\b(?:mysql|mysqldump|mysqladmin|mariadb)(?:[ \t]+[^\s]{1,48}){0,12}?'
     r'[ \t]+-p(?![$"\'\\\s\-])(?=[^\s]{0,100}[0-9A-Z!@#%^&*+=?<>|.])[^\s]{3,}'),
    # G15h additions (NEW-1033): age identity, cloudflared-shaped base64-JSON blob (base64 of `{"`
    # is `eyJ`), secret-valued CLI flags with a space or `=`, and .netrc passwords.
    ("age_secret_key", r'\bAGE-SECRET-KEY-1[QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L]{58}\b'),
    ("base64_json_blob", r'(?<![A-Za-z0-9+/_\-])eyJ[A-Za-z0-9+/_\-]{80,}={0,2}'),
    # Value forms: a double- or single-quoted run (may hold spaces and \\-escaped quotes; an
    # unterminated quote masks to end of line) or one unquoted token. Linear: the repeated
    # groups have disjoint alternatives and the closing quote is optional (no backtracking).
    ("secret_flag", r'(?<![A-Za-z0-9_\-])--(?:token|password|passwd|api-?key|secret|access-?token|auth-?token|client-?secret)'
     r'(?:=|[ \t]+)(?:\\"(?![\-$%{/~<])(?:[^"\\\n]|\\[^"\n]){4,}(?:\\")?|"(?![\-$%{/~<])(?:[^"\\\n]|\\.){4,}"?|\'(?![\-$%{/~<])(?:[^\'\\\n]|\\.){4,}\'?'
     r'|(?![\-$%{/~<])[^\s"\'\\]{8,})'),
    ("netrc_inline", r'(?i)\bmachine[ \t]+\S+[ \t]+login[ \t]+\S+[ \t]+password[ \t]+(?![${*<])\S{4,}'),
    ("netrc_line", r'(?im)^[ \t]*password[ \t]+(?![${*<])\S{6,}[ \t]*$'),
))

# S2-A (G15z V-C3 GW-10b): masking-only patterns. `env_secret_assignment` above is anchored to line
# start, so `env AIGENTIK_INTERNAL_TOKEN=<hex> python3 x` reached the audit ledger unmasked. Same name
# rule (_ENV_NAME) and value rule (_ENV_VAL) as that pattern, but anchored to a word boundary (not
# preceded by [A-Za-z0-9_-]) with `=` directly after the name (no spaces: mid-line `TOKEN = x` is
# prose-shaped). The NAME= prefix is kept (group `keep`) and only the value is replaced, so the
# audit still shows WHICH variable was set. Deliberately NOT in SECRET_PATTERNS: find_secret (the
# fine-tune export drop decision) is unchanged. Linear: the match can only start at the beginning of
# a name run (lookbehind) and every repeat is bounded. Same accepted false positives as the
# line-start rule: any 8+ char non-path value for an upper-case NAME containing TOKEN/SECRET/
# PASSWORD/API_KEY/... (e.g. MAX_TOKENS=1000000000); `$VAR`, `${VAR}`, paths, quoted values, lower-case
# flags such as --token-file=... and short values are untouched.
# The name prefix allowance here is 128 chars (the shared _ENV_NAME, and so the line-start rule, keeps 32);
# still linear because a match starts only at the beginning of a name run, so a start costs <= ~160 steps
# and consumes >= that many chars of a run before the next start. Residuals, pinned in tests: a name with
# more than 128 chars before the keyword is unmasked; mixed-case/lower-case names (`Api_Token=`, `a_TOKEN=`,
# `xTOKEN=`) are not matched (pre-existing limitation shared with the line-start rule); a `-` prefix
# (`-TOKEN=`) is excluded on purpose (option-like).
_ENV_NAME_INLINE = _ENV_NAME.replace('{0,32}(?:', '{0,128}(?:', 1)
assert _ENV_NAME_INLINE != _ENV_NAME
MASK_ONLY_PATTERNS = tuple((n, re.compile(r)) for n, r in (
    ("env_secret_assignment_inline",
     r'(?P<keep>(?<![A-Za-z0-9_\-])' + _ENV_NAME_INLINE + r'=)' + _ENV_VAL),
))


def _scan_view(line: str) -> str:
    """Un-escape JSON string escapes (up to 3 nested passes) so line-anchored and
    quote-anchored patterns can see secrets inside serialized content."""
    for _ in range(3):
        line = line.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
    return line


def find_secret(text: str) -> Optional[str]:
    """Name of the first matching secret pattern, or None. Never returns matched text."""
    view = _scan_view(text)
    for name, rx in SECRET_PATTERNS:
        if rx.search(text) or rx.search(view):
            return name
    return None


WITHHELD_MARKER = "[withheld: redaction failed]"


def mask_secrets(text, *, max_chars: int = 262144) -> str:
    """Return `text` with every SECRET_PATTERNS match replaced by `[REDACTED:<name>]`.

    For audit/log/session sinks, where the surrounding text is evidence worth keeping
    (training export drops whole examples instead, see the module docstring). Pure and
    never raises: any internal error returns WITHHELD_MARKER, never the raw text. Input
    longer than `max_chars` is cut with a visible marker so the scan stays bounded.
    """
    try:
        if not isinstance(text, str):
            text = str(text)
        extra = len(text) - max_chars
        if extra > 0:
            text = text[:max_chars]
        for name, rx in SECRET_PATTERNS:
            text = rx.sub(f"[REDACTED:{name}]", text)
        for name, rx in MASK_ONLY_PATTERNS:
            marker = f"[REDACTED:{name}]"
            text = rx.sub(lambda m, marker=marker: m.group("keep") + marker, text)
        # Marker is appended after masking so a cut right after a flag cannot swallow it.
        return text + f"...[truncated {extra} chars]" if extra > 0 else text
    except Exception:
        # Fail closed by design: the caller gets a fixed marker, never the unmasked text.
        return WITHHELD_MARKER


def has_truncation_marker(text: str) -> bool:
    return any(m in text for m in TRUNCATION_MARKERS)


def dedup_key(example: Dict) -> str:
    body = {k: v for k, v in example.items() if k != "metadata"}
    blob = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8", "surrogatepass")).hexdigest()


def sanitize_examples(examples: List[Dict],
                      max_example_chars: Optional[int] = None) -> Tuple[List[Dict], Dict[str, int]]:
    """Return (kept, stats). Examples are never mutated; dropped whole, never redacted."""
    stats = {"input": 0, "kept": 0, "truncated": 0, "secret": 0, "oversize": 0, "duplicate": 0}
    kept: List[Dict] = []
    seen = set()
    for ex in examples:
        stats["input"] += 1
        line = json.dumps(ex, ensure_ascii=False)  # identical to finetune_prep._write_jsonl
        if has_truncation_marker(line):
            stats["truncated"] += 1
            continue
        if find_secret(line) is not None:
            stats["secret"] += 1
            continue
        if max_example_chars is not None and len(line) > max_example_chars:
            stats["oversize"] += 1
            continue
        key = dedup_key(ex)
        if key in seen:
            stats["duplicate"] += 1
            continue
        seen.add(key)
        kept.append(ex)
    stats["kept"] = len(kept)
    return kept, stats
