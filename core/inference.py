import json
import time

last_tps = 0.0  # tokens per second from last inference
import sys
import urllib.error
import urllib.request

from utils.config import MODEL_CONFIG, PRIMARY_SERVER_PORT
from utils.logger import error, info

SERVER_URL = f"http://127.0.0.1:{PRIMARY_SERVER_PORT}"
CHAT_URL = f"{SERVER_URL}/v1/chat/completions"
HEALTH_URL = f"{SERVER_URL}/health"


def _server_ready(retries=90, delay=1.0) -> bool:
    for _ in range(retries):
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as r:
                if json.loads(r.read()).get("status") == "ok":
                    return True
        except Exception:
            pass
        time.sleep(delay)
    return False


def _start_server():
    """Ensure the primary llama-server is running.

    Delegates to core.loader_v2's ModelLoader — the canonical launcher
    (port-in-use check, os.setsid process-group, SIGINT-masked Popen,
    log file). This module no longer spawns its own llama-server
    subprocess; see NEW-12 in NEW_ISSUES.md for why the old independent
    launcher here was removed.
    """
    from core.loader_v2 import get_loader

    if not get_loader().ensure_model():
        error("llama-server failed to start.")
        raise RuntimeError("llama-server did not become ready.")

    # Start dedicated embed server (nomic on port 8082) alongside generation server
    try:
        from core.embed_server import start_embed_server

        start_embed_server()
    except Exception:
        pass  # embed server is optional — BM25 fallback remains active


def infer(messages: list[dict], stream: bool = True, extra_stop: list = None) -> str:
    global last_tps
    _start_server()
    cfg = MODEL_CONFIG

    stop_tokens = list(cfg["stop"]) + [
        "</tool>",
        "</write_file>",
        "</shell>",
        # Prevent model from echoing system prompt sections into its response
        "\n## Current Project",
        "\n## Project Map",
        "\n## Loaded Files",
        "\n## Project Memory",
        "\nuser\n",
        "\nUSER\n",
        "\nUser\n",
        "<|im_start|>user",
        "<|im_start|>system",
    ]
    if extra_stop:
        stop_tokens += [s for s in extra_stop if s not in stop_tokens]

    payload = json.dumps(
        {
            "model": "codey",
            "messages": messages,
            "max_tokens": cfg["max_tokens"],
            "temperature": cfg["temperature"],
            "top_p": cfg["top_p"],
            "top_k": cfg["top_k"],
            "repeat_penalty": cfg["repeat_penalty"],
            "stop": stop_tokens,
            "stream": stream,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        CHAT_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    response_text = ""

    _t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            if stream:
                print("\033[1;32mCodey:\033[0m ", end="", flush=True)
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    chunk = line[6:]
                    if chunk == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk)
                        token = data["choices"][0]["delta"].get("content", "")
                        response_text += token
                        print(token, end="", flush=True)
                    except Exception:
                        continue
                print()
                _elapsed = time.time() - _t0
                if _elapsed > 0 and response_text:
                    # Approximate tokens from character count (same heuristic as estimate_tokens)
                    approx_tokens = len(response_text) / 4
                    last_tps = round(approx_tokens / _elapsed, 1)
                sys.stdout.flush()
            else:
                data = json.loads(resp.read())
                response_text = data["choices"][0]["message"]["content"]
                # Capture tokens/sec from timings if available
                if "usage" in data:
                    usage = data["usage"]
                    # llama.cpp puts timing in timings field
                if "timings" in data:
                    t = data["timings"]
                    predicted = t.get("predicted_n", 0)
                    ms = t.get("predicted_ms", 0)
                    if ms > 0:
                        last_tps = round((predicted / ms) * 1000, 1)

    except urllib.error.URLError as e:
        return f"[ERROR] Server request failed: {e}"
    except Exception as e:
        return f"[ERROR] Inference failed: {e}"

    return response_text.strip()
