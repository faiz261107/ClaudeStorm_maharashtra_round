"""
Optional LLM generation with no extra packages (urllib only).

Set ONE of these (in the environment, or in a `.env` file next to run.py):
    GEMINI_API_KEY      -> Google Gemini via its OpenAI-compatible endpoint (model: RELEARN_LLM_MODEL, default gemini-3.5-flash; falls back to lite models when busy)
    OPENAI_API_KEY      -> OpenAI chat completions, or any compatible server via OPENAI_BASE_URL (default gpt-4o-mini)
    ANTHROPIC_API_KEY   -> Anthropic messages        (model: RELEARN_LLM_MODEL, default claude-sonnet-4-5)

generate(prompt) returns the text, or None if no key / any error — callers always have an offline fallback.

Check your key:   python -m backend.llm
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

TIMEOUT = 8
# If the chosen Gemini model is busy (503), rate-limited (429), retired (404) or slow, try these next, so the demo always gets a reply
GEMINI_FALLBACKS = ["gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-3.5-flash-lite"]
RETRYABLE = {404, 429, 500, 503}
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
last_error: str | None = None


def load_dotenv(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from .env into the environment (never overrides variables that are already set)."""
    path = path or Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if key.strip() and value:
            os.environ.setdefault(key.strip(), value)


def _gemini_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def available() -> str | None:
    if _gemini_key():
        return "gemini"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def model_name() -> str | None:
    provider = available()
    default = {"gemini": "gemini-3.5-flash", "openai": "gpt-4o-mini", "anthropic": "claude-sonnet-4-5"}.get(provider or "")
    return os.environ.get("RELEARN_LLM_MODEL", default) if provider else None


def _post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def generate(prompt: str, max_tokens: int = 400, system: str | None = None,
             history: list[dict] | None = None) -> str | None:
    """`history` is earlier turns as [{"role": "user"|"assistant", "content": str}], oldest first."""
    global last_error
    provider = available()
    if not provider:
        return None
    turns = [{"role": t["role"], "content": t["content"]} for t in (history or [])
             if t.get("role") in ("user", "assistant") and t.get("content")]
    turns.append({"role": "user", "content": prompt})
    models = [model_name()]
    if provider == "gemini":
        models += [m for m in GEMINI_FALLBACKS if m not in models]
    for model in models:
        text = _attempt(provider, model, turns, max_tokens, system)
        if text:
            return text
        if not (last_error or "").startswith(tuple(f"HTTP {c}" for c in RETRYABLE)) and "timed out" not in (last_error or "") and last_error != "empty reply":
            break  # e.g. a bad key: trying other models won't help
    print(f"[llm] {provider} unavailable, using offline fallback — {last_error}", file=sys.stderr)
    return None


def _attempt(provider: str, model: str, turns: list[dict], max_tokens: int, system: str | None) -> str | None:
    global last_error
    try:
        if provider in ("gemini", "openai"):
            msgs = ([{"role": "system", "content": system}] if system else []) + turns
            if provider == "gemini":
                # Gemini models may "think" before answering and that counts against max_tokens: leave room for it
                url, key, budget = GEMINI_BASE + "/chat/completions", _gemini_key(), max_tokens + 1024
            else:
                url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions"
                key, budget = os.environ["OPENAI_API_KEY"], max_tokens
            data = _post(url, {"model": model, "messages": msgs, "max_tokens": budget, "temperature": 0.5},
                         {"Authorization": f"Bearer {key}"})
            text = (data["choices"][0]["message"].get("content") or "").strip()
        else:
            body = {"model": model, "max_tokens": max_tokens, "messages": turns}
            if system:
                body["system"] = system
            data = _post("https://api.anthropic.com/v1/messages", body,
                         {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
            text = "".join(b.get("text", "") for b in data.get("content", [])).strip()
        last_error = None if text else "empty reply"
        return text or None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        last_error = f"HTTP {e.code}: {detail}"
    except Exception as e:  # network down, timeout, unexpected shape
        last_error = f"{type(e).__name__}: {e}"
    return None


if __name__ == "__main__":  # python -m backend.llm  -> checks the key without printing it
    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = available()
    if not p:
        sys.exit("No key found. Put GEMINI_API_KEY=your-key in the .env file next to run.py.")
    print(f"Provider: {p} · model: {model_name()}")
    reply = generate("In one sentence: why is a ball's acceleration not zero at the top of its flight?", max_tokens=120)
    print("Reply:", reply if reply else f"FAILED — {last_error}")
    if not reply and p == "gemini":
        try:  # most common failure: the model name changed. Show the ones this key can use.
            req = urllib.request.Request(GEMINI_BASE + "/models", headers={"Authorization": f"Bearer {_gemini_key()}"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                names = sorted(m["id"].split("/")[-1] for m in json.load(r).get("data", []) if "gemini" in m["id"])
            print("Models your key can use:", ", ".join(names) or "(none listed)")
            print("Pick one and add a line to .env:  RELEARN_LLM_MODEL=<name>")
        except Exception as e:
            print(f"Could not list models ({type(e).__name__}) — check the key is correct.")
