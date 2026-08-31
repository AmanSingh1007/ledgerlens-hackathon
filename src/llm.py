"""LLM engine for LedgerLens.

Two interchangeable backends, selected via LEDGERLENS_ENGINE (default: auto):
  - "cli": shells out to the Claude Code CLI (`claude -p`). No API key needed;
           uses whatever account the local Claude Code is logged into.
  - "api": calls the Anthropic Messages API directly (needs ANTHROPIC_API_KEY).
auto = "api" if ANTHROPIC_API_KEY is set, else "cli".
"""

import json
import os
import shutil
import subprocess
import time
import urllib.request

DEFAULT_MODEL = os.environ.get("LEDGERLENS_MODEL", "claude-haiku-4-5-20251001")
ENGINE = os.environ.get("LEDGERLENS_ENGINE", "auto")

_CALL_COUNT = {"n": 0}


def call_count():
    return _CALL_COUNT["n"]


def reset_call_count():
    _CALL_COUNT["n"] = 0


def complete(prompt: str, model: str = None, max_retries: int = 2) -> str:
    """Send a single-turn prompt, return the text reply."""
    model = model or DEFAULT_MODEL
    engine = ENGINE
    if engine == "auto":
        engine = "api" if os.environ.get("ANTHROPIC_API_KEY") else "cli"

    last_err = None
    for attempt in range(max_retries + 1):
        try:
            _CALL_COUNT["n"] += 1
            if engine == "api":
                return _complete_api(prompt, model)
            return _complete_cli(prompt, model)
        except Exception as e:  # transient CLI/network hiccups
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"LLM call failed after retries: {last_err}")


def _complete_cli(prompt: str, model: str) -> str:
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("`claude` CLI not found on PATH and no ANTHROPIC_API_KEY set.")
    proc = subprocess.run(
        [exe, "-p", "--model", model],
        input=prompt.encode("utf-8"),
        capture_output=True,
        timeout=300,
    )
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 or not out:
        raise RuntimeError(f"claude CLI rc={proc.returncode}: {proc.stderr.decode('utf-8', errors='replace')[:500]}")
    return out


def _complete_api(prompt: str, model: str) -> str:
    body = json.dumps({
        "model": model,
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return "".join(b.get("text", "") for b in data["content"]).strip()


def extract_json(text: str):
    """Pull the first JSON object out of a model reply (tolerates ``` fences)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object in reply: {text[:200]}")
    return json.loads(text[start:end + 1])
