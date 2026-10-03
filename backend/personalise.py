"""
Personalised interventions: "generate or select" (problem statement).

Two layers:
  1. Offline (always on): quote the learner's own sentence, find the phrase that carries the
     misconception, and write a short bridge from THEIR words to the physics.
  2. Optional LLM rewrite: if ANTHROPIC_API_KEY is set and the `anthropic` package is installed,
     the whole intervention is rewritten around the learner's explanation. Falls back silently.

Returns a dict the frontend renders above the standard intervention:
  {"quote": ..., "trigger": ..., "bridge": ..., "source": "rules" | "llm"}
"""

from __future__ import annotations

import os
import re

# Phrases that typically carry each misconception, with a one-line reply to that exact phrase.
TRIGGERS: dict[str, list[tuple[str, str]]] = {
    "VA_CONFUSION": [
        (r"\b(stops?|stopped|at rest|not moving|stationary|still|frozen|motionless)\b",
         "Being at rest for an instant says nothing about acceleration. Ask instead: is the velocity about to change? At a turnaround point it always is."),
        (r"\b(velocity|speed)\s*(is|=)\s*(zero|0)\b.{0,40}\b(acceleration|accel)",
         "You moved from v = 0 to a = 0 in one step. That step is the misconception: v and a are different quantities, and gravity keeps a at 9.8 m/s² even when v is 0."),
        (r"\b(nothing|no)\s+(is\s+)?(happening|changing)\b",
         "Something *is* changing: the velocity is reversing direction. That change is exactly what acceleration measures."),
    ],
    "IMPETUS": [
        (r"\b(throw|throwing|kick|hit|launch|push|flick)\s+force\b|\b(force|push|energy)\s+(of|from)\s+the\s+(throw|hand|hit|kick|flick|cannon|engine|bowler|push)\b",
         "Look for the object applying that force right now. There is none — so there is no such force. What keeps the object moving is inertia, not a push."),
        (r"\b(runs?|ran|running|wears?|wearing|dies?|dying|fad\w+|used up|exhaust\w*)\s*(out|off|away|down)?\b",
         "A force cannot ‘run out’ because it was never stored in the object. It existed only while the hand was in contact; after release it is gone instantly."),
        (r"\b(still|carries|carrying|inside|in it|with it|left ?over)\b",
         "Nothing travels inside the object. Draw the forces a moment after release: gravity is the only arrow you can justify."),
    ],
    "FORCE_VELOCITY": [
        (r"\bconstant\s+(force|push).{0,30}constant\s+(speed|velocity)\b",
         "Swap one word and it becomes true: constant force → constant *acceleration*. Velocity then keeps growing."),
        (r"\b(net\s+force|force)\s+(is|must be|has to be|points?)\s+(forward|up|in the direction)\b",
         "Direction of motion and direction of net force are different things. At constant velocity the net force is zero — the forward push is exactly cancelled."),
        (r"\b(need|needs|require\w*)\s+(a\s+)?(net\s+)?force\s+to\s+(keep|stay|move)\b",
         "No force is needed to keep moving; a force is needed to *change* motion. That is Newton's first law."),
        (r"\b(double|twice|more)\s+(the\s+)?force.{0,30}(double|twice|more)\s+(the\s+)?(speed|velocity)\b",
         "Doubling the force doubles the acceleration, not the speed. Speed then builds up twice as fast."),
    ],
    "THIRD_LAW": [
        (r"\b(bigger|heavier|larger|more massive|faster|stronger|more powerful)\b.{0,40}\b(pushes?|hits?|exerts?|force)\b",
         "Size, mass and speed change what the force *does* (a = F/m), never how big the pair of forces is. Both forces are identical."),
        (r"\b(crushed|damaged|destroyed|wrecked|flung|squashed|splat\w*)\b",
         "Damage shows acceleration, not force. The lighter object accelerates more under the *same* force — that is why it is the one wrecked."),
        (r"\b(doesn'?t|does not|can'?t|cannot)\s+(push|move|exert)\b",
         "A wall that does not move still pushes back — exactly as hard as it is pushed. If it did not, you would fall through it."),
        (r"\b(wins?|winning|won)\b",
         "Winning a tug-of-war comes from friction with the ground, not from pulling the rope harder. Rope tension is the same at both ends."),
    ],
    "HEAVIER_FASTER": [
        (r"\b(heavier|heavy|more mass|bigger|more weight|weighs more)\b.{0,40}\b(faster|quicker|first|more|sooner)\b",
         "Heavier does mean a bigger pull — and also more inertia. F = m·g and a = F/m, so the m cancels: a = g for everything."),
        (r"\b(gravity|pull)\s+(is\s+)?(stronger|harder|more)\b",
         "True: the pull is stronger on the heavy object. But the heavy object also needs more force to accelerate. Divide the bigger force by the bigger mass and you get the same 9.8 m/s²."),
        (r"\b(light|lighter)\b.{0,40}\b(slow\w*|float\w*|longer)\b",
         "Light objects fall slowly only because of air. Remove the air — a vacuum tube, or the Moon — and the feather drops like the hammer."),
    ],
}


def _find_trigger(label: str, explanation: str) -> tuple[str | None, str | None]:
    text = explanation or ""
    for pattern, reply in TRIGGERS.get(label, []):
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return text[m.start():m.end()], reply
    return None, None


def personalise(label: str, explanation: str, misconception: dict, intervention: dict, item_prompt: str = "") -> dict:
    quote = (explanation or "").strip()
    trigger, reply = _find_trigger(label, quote)
    if trigger:
        bridge = f"The key phrase is “{trigger}”. {reply}"
    else:
        bridge = (f"Your explanation reads as “{misconception['short'].lower()}”. "
                  f"{misconception['physics'].split('.')[0]}.")
    out = {"quote": quote, "trigger": trigger, "bridge": bridge, "source": "rules"}

    llm = _llm_rewrite(label, quote, misconception, intervention, item_prompt)
    if llm:
        out.update({"bridge": llm, "source": "llm"})
    return out


def _llm_rewrite(label: str, quote: str, misconception: dict, intervention: dict, item_prompt: str) -> str | None:
    """Optional: rewrite the bridge with an LLM, grounded in the learner's own sentence. Never required."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not quote:
        return None
    try:
        import anthropic  # type: ignore
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic(api_key=key)
        prompt = (
            "You are a physics tutor. A learner answered this question:\n"
            f"{item_prompt}\n\nThey explained: \"{quote}\"\n\n"
            f"The diagnosed misconception is '{misconception['name']}': {misconception['believes']}\n"
            f"The physics: {misconception['physics']}\n\n"
            "Write 2 short paragraphs (max 90 words total) that (1) quote the exact phrase in their explanation that carries the "
            "misconception and say why it feels right, and (2) correct it in plain language, ending with one question they can "
            "ask themselves next time. Address the learner as 'you'. No headings, no bullet points."
        )
        msg = client.messages.create(model=os.environ.get("RELEARN_LLM_MODEL", "claude-sonnet-4-5"), max_tokens=300,
                                     messages=[{"role": "user", "content": prompt}])
        text = "".join(getattr(b, "text", "") for b in msg.content).strip()
        return text or None
    except Exception:
        return None
