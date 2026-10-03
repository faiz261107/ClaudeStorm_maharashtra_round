"""
Optional LLM generation with no extra packages (urllib only).

Set ONE of:
    OPENAI_API_KEY      -> OpenAI chat completions   (model: RELEARN_LLM_MODEL, default gpt-4o-mini)
    ANTHROPIC_API_KEY   -> Anthropic messages        (model: RELEARN_LLM_MODEL, default claude-sonnet-4-5)

generate(prompt) returns the text, or None if no key / any error — callers always have an offline fallback.
"""

from __future__ import annotations

import json
import os
import urllib.request

TIMEOUT = 20


def available() -> str | None:
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def generate(prompt: str, max_tokens: int = 400, system: str | None = None) -> str | None:
    provider = available()
    if not provider:
        return None
    try:
        if provider == "openai":
            model = os.environ.get("RELEARN_LLM_MODEL", "gpt-4o-mini")
            msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
            body = {"model": model, "messages": msgs, "max_tokens": max_tokens, "temperature": 0.5}
            req = urllib.request.Request(os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions",
                                         data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = json.load(r)
            return (data["choices"][0]["message"]["content"] or "").strip() or None
        model = os.environ.get("RELEARN_LLM_MODEL", "claude-sonnet-4-5")
        body = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                                              "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.load(r)
        return "".join(b.get("text", "") for b in data.get("content", [])).strip() or None
    except Exception:
        return None
