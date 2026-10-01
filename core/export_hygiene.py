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
_VAL_GUARD = (r'(?![/~${])(?!\*+(?:["\'\\\s]|$))(?![^"\'\s]{0,200}\.\.\.)'
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
