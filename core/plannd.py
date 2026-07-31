"""
plannd — Task planner for Codey-OS

Provides get_plan(): sends a user prompt to the 1.5B model on port 8081
and returns a numbered step list for the 7B agent to execute.

get_plan() ensures the local 1.5B planner server is loaded before calling
it, via core/planner_loader.py's PlannerLoader.ensure_planner() — this
performs a sequential swap with the primary 7B model (core/loader_v2.py):
the two are never resident at the same time on this device. See
core/planner_loader.py and core/loader_v2.py's SWAP_GUARD docstring for the
swap mechanics. Skipped entirely when a remote planner backend
(CODEY_BACKEND_P / CODEY_BACKEND) is configured — no local server needed.

Port assignments:
  8080 — Qwen2.5-Coder-7B  (agent execution only)
  8081 — Qwen2.5-1.5B       (planning + summarization)
  8082 — nomic-embed-text    (embeddings)
"""

import json
import re
import urllib.error
import urllib.request
from typing import List, Optional

# ── Planner prompt ────────────────────────────────────────────────────────────
# Single prompt used by ALL backends: local 1.5B, OpenRouter, UnlimitedClaude.
# Test and tune this prompt against remote models (faster iteration), then
# the same prompt runs on local — results are directly comparable.

PLANNER_PROMPT = (
    "You are a task planner. Write a numbered list of 1 to 8 steps. Include every "
    "action the user asked for — no more, no fewer. A one-step plan is correct when "
    "the request only needs one action (e.g. a single Edit). If the user asks for "
    "something to happen multiple times (e.g. 'run it three times'), your plan must "
    "contain that many separate steps for it — do not collapse repeats into one step.\n"
    "Your plan is executed AS-IS by a code agent. Every filename and path in your plan\n"
    "will be used exactly as you write it. Do not abbreviate, paraphrase, or assume.\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "CRITICAL RULE: CREATE vs EDIT — CHECK THIS FIRST\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "• FIRST check: does the user ask to create/write/make/generate a NEW file?\n"
    "  If yes → Create, even if the message also contains a word like 'fix',\n"
    "  'update', or 'replace' describing what the new file should DO.\n"
    "• OTHERWISE, if the user's message contains fix, bug, error, off-by-one,\n"
    "  wrong, broken, change, modify, update, correct, debug, refactor, rename,\n"
    "  or replace, referring to a file that already exists → the file ALREADY\n"
    "  EXISTS, use Edit, NEVER Create.\n"
    "• An edit-only request gets Edit step(s) ONLY. No Create step. No Run/Verify\n"
    "  step unless the user explicitly asked to run or verify something.\n"
    "• Step content comes ONLY from the user's own words. Never copy content from\n"
    "  the examples below — those show FORMAT only, not tasks to reuse.\n\n"
    "VIOLATION (real observed failure):\n"
    "  ✗ User says 'Fix the off-by-one error in the loop in core/legacy_calc.py'\n"
    "    → you write '1. Create core/legacy_calc.py: prints each Fibonacci number...'\n"
    "    WRONG: 'fix' means this file exists (Edit, not Create — a Create step here\n"
    "    would overwrite and destroy the real file), and the Fibonacci content was\n"
    "    copied from an example, not from anything this user said.\n"
    "  ✓ Correct: '1. Edit core/legacy_calc.py: fix the off-by-one error in the loop'\n"
    "  ✗ User says 'create ping_check.py ... run it twice' → you write only ONE "
    "'Run: python ping_check.py' step. WRONG: 'twice' means two separate Run steps, "
    "not one — under-counting is as wrong as adding unrequested steps.\n"
    "  ✓ Correct: two separate, identical 'Run: python ping_check.py' steps.\n"
    "  ✗ User says 'run report.py, then verify it wrote 3 rows to out.csv' → you "
    "write three Run steps. WRONG: '3 rows' describes the expected Verify OUTCOME, "
    "not a repeat count — this is one Run step plus one Verify step, never more.\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "CRITICAL RULE: FILENAMES AND PATHS\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "• EXTRACT the exact filenames from the user's message FIRST. Highlight them mentally.\n"
    "• COPY them AS-IS into your plan. Do not abbreviate, shorten, or 'clean up' names.\n"
    "• EVERY mention of a filename in your plan must be identical to the user's original.\n"
    "• Use the SAME filename consistently across ALL steps (Create, Edit, Run, Verify).\n"
    "• Do NOT invent subdirectory paths (e.g. do NOT write 'data/results.py' unless the\n"
    "  user explicitly said 'data/results.py'). Files go in the current working directory.\n\n"
    "VIOLATIONS (these are WRONG):\n"
    "  ✗ User says 'fibonacci.py' → you write 'fib.py' (abbreviation)\n"
    "  ✗ User says 'fibonacci.py' → you write 'fibonacci.py' in step 1 but 'fib.py' in step 2\n"
    "  ✗ User says 'fibonacci.py' → you write 'src/fibonacci.py' (invented path)\n"
    "  ✗ User says 'results.json' → you write 'out.json' (different name)\n\n"
    "STEP TEMPLATES:\n"
    "  Create <file>: <only the features/inputs/outputs the user actually named — "
    "never add a feature, parameter, or format the user did not mention>\n"
    "  Edit <file>: <specific change to make — what to add/modify/remove and where>\n"
    "  Run: python <exact filename from user> <exact value from user>\n"
    "  Run: pytest <file>\n"
    "  Verify: <expected outcome>\n"
    "  Ask <cli> to <the user's instruction copied word-for-word, including every "
    "trailing clause> — this template applies even when it is the ONLY step in the "
    "plan (a one-step plan still uses the full template, never a shortened form).\n\n"
    "RULES:\n"
    "1. Create step: use the format above, ONLY for a file that does not exist yet. "
    "List every feature after the colon, comma-separated. Read the full user message. "
    "Include ALL of: input args, processing, file saves, timestamps, print format. "
    "Keep adding features until complete.\n"
    "2. Edit step: use the format above, for a file the user refers to as already "
    "existing (see CREATE vs EDIT rule above). Include the exact filename and a specific "
    "description of what to change, using the user's own words. An edit-only request "
    "gets Edit steps ONLY — no Create step.\n"
    "3. Run: copy the exact filename and argument from the user's message word for word. "
    "One Run step per execution. Use the SAME filename as in the Create/Edit step. "
    "ONLY include a Run step if the user's message asks you to run, execute, or test "
    "something — never add one on your own. If the user gives a repeat count attached "
    "to the word run/execute/test (twice, three times, 3x, run it N times), emit "
    "exactly that many separate, identical Run steps — 'twice' means 2 Run steps, "
    "'three times' means 3 Run steps. This is a required exception to keeping steps "
    "minimal, not an extra step you invented. A number that instead describes an "
    "expected RESULT (e.g. 'printed exactly 10 lines', 'contains 2 entries') is NOT a "
    "repeat count — it belongs in a Verify step's description, never in the Run count.\n"
    "4. Verify: describes what should be true — never a command. ONLY include a Verify "
    "step if the user's message asks you to check, verify, or confirm something — "
    "never add one on your own.\n"
    "5. Repeat a step ONLY when the user asked for repetition (e.g. 'run it three times' "
    "→ three separate Run steps). Otherwise, no two steps repeat the same action.\n"
    "6. Use 'pytest' for test files, not 'python'.\n"
    "7. No code, no markdown, no extra text. Plain English step descriptions only.\n"
    "8. Never invent capabilities or steps. If the user only asked you to create or edit "
    "a file, your plan ends after that step — do not add Run/Verify/extra steps the user "
    "did not request.\n"
    "9. Peer CLI steps: if the user says 'ask claude to X', 'have gemini do X', 'use qwen to X', "
    "etc., copy that instruction EXACTLY as: 'Ask claude to X'. Never rephrase, and never drop "
    "trailing words — copy the WHOLE instruction including any trailing clause like "
    "'for bugs' or 'and summarize it'. This rule applies IDENTICALLY whether the delegation "
    "is step 1 of a ONE-STEP plan or step 2+ of a longer plan — a single-step plan is still "
    "a plan, and a lone delegation step gets copied whole, exactly as it would at any other "
    "position. Do not shorten a delegation instruction just because it is the only step.\n"
    "  ✗ User says 'ask claude to review report_gen.py for bugs' → you write "
    "'Ask claude to review report_gen.py' (dropped 'for bugs')\n"
    "  ✓ Correct: 'Ask claude to review report_gen.py for bugs' (nothing dropped)\n\n"
    "EXAMPLE — user says:\n"
    "'Create a Python script called fibonacci.py that generates the first 20 fibonacci "
    "numbers and prints them one per line then runs it to show the output'\n\n"
    "Your plan:\n"
    "1. Create fibonacci.py: generates the first 20 Fibonacci numbers, prints each one on "
    "its own line\n"
    "2. Run: python fibonacci.py\n\n"
    "NOTE: User said 'fibonacci.py', so you MUST use 'fibonacci.py' in both steps. "
    "This is a NEW file (Create), because the user asked to 'create a Python script'. "
    "The user never mentioned a command-line argument or a parameter named 'n' — do NOT "
    "add 'accepts n' or an argument to the Run command unless the user's own words asked "
    "for one; '20' here is the count of numbers to generate (already in the Create step), "
    "not a value the file accepts as input.\n\n"
    "ANOTHER EXAMPLE — user says:\n"
    "'Create xform.py that accepts a corpus.txt path, counts tokens/lines, appends each result "
    "with a timestamp to tally.json, prints a clean summary; run on corpus.txt twice, "
    "verify tally.json has 2 entries'\n\n"
    "Your plan:\n"
    "1. Create xform.py: accepts a path, counts tokens and lines, "
    "appends result with timestamp to tally.json, prints a clean summary\n"
    "2. Run: python xform.py corpus.txt\n"
    "3. Run: python xform.py corpus.txt\n"
    "4. Verify: tally.json contains exactly 2 entries with timestamps\n\n"
    "NOTE: user explicitly asked to run it twice AND verify the result — that is why "
    "this plan has Run and Verify steps unlike the edit-only example below.\n\n"
    "ANOTHER EXAMPLE — user says:\n"
    "'Create ping_check.py that prints OK, run it twice'\n\n"
    "Your plan:\n"
    "1. Create ping_check.py: prints OK\n"
    "2. Run: python ping_check.py\n"
    "3. Run: python ping_check.py\n\n"
    "NOTE: 'twice' means exactly two Run steps, even though there is no Verify step and "
    "no arguments — the repeat count is the only thing that changed from a single-Run "
    "plan, so do not collapse the two runs into one.\n\n"
    "EXAMPLE — user says:\n"
    "'Fix the off-by-one error in the loop in core/legacy_calc.py'\n\n"
    "Your plan:\n"
    "1. Edit core/legacy_calc.py: fix the off-by-one error in the loop\n\n"
    "NOTE: 'Fix' means this file already exists — Edit, never Create. The user did not "
    "ask to run or verify anything, so the plan has exactly one step. Do not add "
    "content the user did not mention.\n\n"
    "EXAMPLE — user says:\n"
    "'Ask gemini to summarize sync_utils.py and list its public functions'\n\n"
    "Your plan:\n"
    "1. Ask gemini to summarize sync_utils.py and list its public functions\n\n"
    "NOTE: this is a ONE-STEP plan because the user asked for exactly one thing — a peer "
    "CLI delegation, nothing else. Even though it is the only step (no Create/Edit came "
    "before it), you still copy the FULL instruction word-for-word, including the trailing "
    "clause 'and list its public functions'. Being the only step is never a reason to "
    "shorten it — a one-step delegation plan gets the exact same full-copy treatment as a "
    "delegation step in a longer plan."
)


# ── Step parser ───────────────────────────────────────────────────────────────


def parse_steps(raw: str) -> List[str]:
    """
    Extract numbered steps from model output.

    Strips <think>...</think> blocks (R1-style reasoning traces),
    then collects lines matching "N. step" or "N) step".
    """
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    steps: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^(\d+)[.)]\s+(.+)$", line)
        if m:
            step = m.group(2).strip()
            if step:
                steps.append(step)
    if steps:
        last = steps[-1]
        if last and last[-1] not in ".!?)" and last[-1].isalpha():
            print(
                "[plannd] plan may be truncated — consider increasing max_tokens",
                flush=True,
            )
    return steps


# ── Tool-call step filter ─────────────────────────────────────────────────────

_TOOL_VERBS = re.compile(
    r"^(create|write|build|add|edit|run|execute|install|verify|check|test|confirm|update|delete|remove"
    r"|ask|have|use|tell|call|let|get|initialize|init|commit|push)\b",
    re.IGNORECASE,
)

# Peer CLI names — steps mentioning these are always kept regardless of verb
_PEER_NAME_RE = re.compile(r"\b(claude|gemini|qwen)\b", re.IGNORECASE)


def filter_tool_steps(steps: List[str]) -> List[str]:
    """
    Keep only steps that correspond to real tool calls (create file, run
    command, verify output).  Drops implementation-detail steps the 1.5B
    model sometimes emits (e.g. "Count lines using os.linesep").

    Rules:
    - Step 1 is always kept (create/write the file — enriched with full prompt).
    - Subsequent steps are kept if they start with a recognised action verb,
      contain 'Run:' / 'Verify' / 'Check', or mention a peer CLI by name
      (claude/gemini/qwen — these are delegation steps and must be preserved).
    """
    if not steps:
        return steps
    kept = [steps[0]]
    for step in steps[1:]:
        if (
            _TOOL_VERBS.match(step)
            or re.search(r"\bRun:|Verify|Check\b", step, re.IGNORECASE)
            or _PEER_NAME_RE.search(step)
        ):
            kept.append(step)
    return kept if len(kept) > 1 else steps[:2]  # fallback: keep first two


# ── Planning via 1.5B on port 8081 (or remote when CODEY_BACKEND_P is set) ──


def _get_plan_remote(prompt: str) -> Optional[List[str]]:
    """Route planning through the active planner backend (OpenRouter or UnlimitedClaude)."""
    try:
        from utils.config import (CODEY_PLANNER_BACKEND, OPENROUTER_API_KEY,
                                  OPENROUTER_BASE_URL,
                                  OPENROUTER_PLANNER_MODEL, PLANNER_MAX_TOKENS,
                                  PLANNER_TEMPERATURE, UNLIMITEDCLAUDE_API_KEY,
                                  UNLIMITEDCLAUDE_BASE_URL,
                                  UNLIMITEDCLAUDE_PLANNER_MODEL)
        from utils.logger import info, warning

        if CODEY_PLANNER_BACKEND == "unlimitedclaude":
            planner_model = UNLIMITEDCLAUDE_PLANNER_MODEL
            base_url = UNLIMITEDCLAUDE_BASE_URL.rstrip("/")
            api_key = UNLIMITEDCLAUDE_API_KEY
            backend_label = "unlimitedclaude"
        else:
            planner_model = OPENROUTER_PLANNER_MODEL
            base_url = OPENROUTER_BASE_URL.rstrip("/")
            api_key = OPENROUTER_API_KEY
            backend_label = "openrouter"

        messages = [
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": prompt},
        ]

        # Use the dedicated planner model and low temperature (0.2 not 0.7)
        import json as _json
        import urllib.request as _req

        payload = {
            "model": planner_model,
            "messages": messages,
            "max_tokens": PLANNER_MAX_TOKENS,
            "temperature": PLANNER_TEMPERATURE,
            "stream": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/Ishabdullah/Codey-OS",
            "X-Title": "Codey-OS",
        }
        request = _req.Request(
            f"{base_url}/chat/completions",
            data=_json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with _req.urlopen(request, timeout=60) as resp:
                result = _json.loads(resp.read().decode("utf-8"))
            msg = result["choices"][0].get("message", {})
            # content can be null when the model returns a tool_call instead of text
            content = msg.get("content") or ""
            # Qwen3 / thinking models put output in reasoning_content when content is empty
            if not content:
                content = msg.get("reasoning_content") or ""
            # some models return text inside tool_calls[0].function.arguments
            if not content and "tool_calls" in msg:
                try:
                    content = msg["tool_calls"][0]["function"]["arguments"]
                except (KeyError, IndexError):
                    pass
            raw = content.strip()
        except Exception as e:
            warning(f"[plannd] {backend_label} plan request failed: {e}")
            return None

        if not raw:
            warning(f"[plannd] {backend_label} returned empty plan response")
            return None

        steps = parse_steps(raw)
        steps = filter_tool_steps(steps)
        if not steps:
            warning(f"[plannd] {backend_label} response had no parseable steps. Raw: {raw[:120]}")
            return None
        info(f"[plannd] {backend_label} plan ({planner_model}): {len(steps)} steps")
        return steps
    except Exception as e:
        from utils.logger import warning

        warning(f"[plannd] remote planning failed: {e}")
        return None


def get_plan(prompt: str) -> Optional[List[str]]:
    """
    Break *prompt* into a numbered plan.

    Uses the local 1.5B on port 8081 by default.
    When CODEY_BACKEND_P (or CODEY_BACKEND) is a remote backend, routes
    there instead so the 1.5B server does not need to be running.
    """
    try:
        from utils.config import is_remote_planner_backend

        if is_remote_planner_backend():
            return _get_plan_remote(prompt)
    except ImportError:
        pass

    # ── Ensure the local 1.5B planner is loaded (sequential swap) ─────────
    # Only reached for the local-backend path (remote returns above). This
    # unloads the primary 7B model first if needed — see
    # core/planner_loader.py. Any failure (model file missing, spawn
    # timeout, a cross-process conflict we can't safely resolve) means no
    # local planner is available right now: return None immediately so the
    # caller falls back to unplanned single-task execution
    # (core/daemon.py's existing fallback, ~line 212), rather than making
    # the HTTP call below against a server that was never started.
    try:
        from core.planner_loader import get_planner_loader

        if not get_planner_loader().ensure_planner():
            print("[plannd] planner model unavailable — falling back to unplanned execution", flush=True)
            return None
    except Exception as e:
        print(f"[plannd] planner load failed: {e}", flush=True)
        return None

    try:
        from utils.config import PLANNER_MAX_TOKENS, PLANNER_TEMPERATURE

        temperature = PLANNER_TEMPERATURE
        max_tokens = PLANNER_MAX_TOKENS
    except ImportError:
        temperature = 0.2
        max_tokens = 512

    try:
        from utils.config import PLANND_SERVER_PORT

        port = PLANND_SERVER_PORT
    except ImportError:
        port = 8081

    payload = {
        "model": "plannd",
        "messages": [
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    url = f"http://127.0.0.1:{port}/v1/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            choices = result.get("choices", [])
            if not choices:
                return None
            raw = choices[0].get("message", {}).get("content", "").strip()
            if not raw:
                return None
            steps = parse_steps(raw)
            steps = filter_tool_steps(steps)
            return steps if steps else None
    except Exception as e:
        print(f"[plannd] get_plan error: {e}", flush=True)
        return None
