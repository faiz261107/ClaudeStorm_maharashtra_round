"""
Tutor response: a reply written about the learner's OWN explanation.

How it is built (all local NLP, no network):
  1. find_claims()  – every recognisable claim in their sentence, in the order they said it,
                      each with a verdict (true / partly / false) and a reply to THAT claim
  2. analyse()      – concepts mentioned, hedging/certainty, reason clause, length
  3. compose()      – opener → walk through their claims one by one ("You said '…' — true. Then
                      you said '…' — this is where it breaks, because …") → the physics in one
                      line → a question to carry forward

If OPENAI_API_KEY or ANTHROPIC_API_KEY is set, the same analysis is handed to the LLM, which
writes the reply (backend/llm.py). The offline composer is always the fallback.
"""

from __future__ import annotations

import random
import re

from backend.claims import find_claims
from backend.llm import available as llm_available, generate as llm_generate
from backend.personalise import _find_trigger

CONCEPTS: dict[str, list[str]] = {
    "gravity": [r"\bgravit\w*", r"\bweight\b", r"\bpull(s|ed|ing)? (it )?down", r"\b9\.8\b", r"\bg\b"],
    "velocity": [r"\bveloc\w*", r"\bspeed\w*", r"\bv\s*=", r"\bm/s\b"],
    "acceleration": [r"\baccel\w*", r"\ba\s*=", r"\bm/s\^?2|m/s²"],
    "rest": [r"\bstop\w*", r"\bat rest\b", r"\bstationary\b", r"\bstill\b", r"\bnot moving\b", r"\bmotionless\b", r"\bzero velocity\b", r"\bv\s*=\s*0"],
    "force": [r"\bforce\w*", r"\bpush\w*", r"\bpull\w*", r"\bthrust\b", r"\bnet\b"],
    "inertia": [r"\binertia\b", r"\bfirst law\b", r"\bkeeps? (on )?(moving|going)\b", r"\bno force (is )?needed\b"],
    "mass": [r"\bmass\w*", r"\bheav\w*", r"\blight(er)?\b", r"\bkg\b"],
    "third_law": [r"\bthird law\b", r"\bequal and opposite\b", r"\breaction\b", r"\bpair\b", r"\bsame (force|size)\b"],
    "contact": [r"\btouch\w*", r"\bcontact\b", r"\bleaves? (the |your )?hand\b", r"\brelease\w*", r"\blet go\b"],
    "balance": [r"\bbalanc\w*", r"\bcancel\w*", r"\bnet force (is |= ?)?(zero|0)\b", r"\bequal\b"],
    "air": [r"\bair\b", r"\bdrag\b", r"\bresistance\b", r"\bvacuum\b"],
    "time_change": [r"\bchang\w*", r"\brate\b", r"\bper second\b", r"\bincreas\w*", r"\bdecreas\w*", r"\bslow\w* down\b", r"\bspeed\w* up\b"],
}
HEDGES = [r"\bi think\b", r"\bmaybe\b", r"\bprobably\b", r"\bnot sure\b", r"\bi guess\b", r"\bperhaps\b", r"\bmight\b", r"\bi believe\b"]
CERTAIN = [r"\bdefinitely\b", r"\bobviously\b", r"\bclearly\b", r"\bof course\b", r"\bfor sure\b", r"\balways\b", r"\bmust\b"]

KEY_IDEA = {
    "VA_CONFUSION": "velocity and acceleration are different quantities — v can be zero while a is not",
    "IMPETUS": "a force exists only while something is applying it; nothing is stored in a moving object",
    "FORCE_VELOCITY": "force changes velocity, it does not set it — constant velocity means zero net force",
    "THIRD_LAW": "the two forces in an interaction are always equal; only the accelerations differ",
    "HEAVIER_FASTER": "the bigger pull and the bigger inertia cancel — every object free-falls at g",
}
THINK_QUESTION = {
    "VA_CONFUSION": "Is the velocity about to change at that instant? If yes, the acceleration cannot be zero.",
    "IMPETUS": "Which object is applying that force right now? If you can't name one, the force isn't there.",
    "FORCE_VELOCITY": "If the net force really pointed forward, what would happen to the speed?",
    "THIRD_LAW": "If the forces were unequal, why would the lighter object get wrecked while feeling the smaller force?",
    "HEAVIER_FASTER": "What do you get when you divide a force ten times bigger by a mass ten times bigger?",
}
CORRECT_PRAISE = {
    "accel_is_g_at_rest": "You separated velocity from acceleration — exactly the distinction most people miss here.",
    "only_gravity": "You looked for the object applying each force instead of drawing one for the motion. That's the habit that makes free-body diagrams work.",
    "inertia": "You used Newton's first law the way it's meant to be used: no net force, no change in motion.",
    "net_force_zero_const_v": "You read 'constant velocity' as 'balanced forces'. That single move solves most of these questions.",
    "const_force_accel": "You kept force tied to acceleration rather than speed — that's Newton's second law doing its job.",
    "third_law_equal": "You kept the force pair equal and put the difference where it belongs: in the accelerations.",
    "same_accel_free_fall": "You saw that the extra pull and the extra inertia cancel. That's the whole argument.",
}
PROBE_CONCEPT = {"VA_CONFUSION": "accel_is_g_at_rest", "IMPETUS": "only_gravity", "FORCE_VELOCITY": "net_force_zero_const_v",
                 "THIRD_LAW": "third_law_equal", "HEAVIER_FASTER": "same_accel_free_fall"}


def _spot(text: str, patterns: list[str]) -> bool:
    t = (text or "").lower()
    return any(re.search(p, t) for p in patterns)


def analyse(explanation: str, priority: list[str] | None = None) -> dict:
    t = (explanation or "").strip()
    return {
        "concepts": [c for c, pats in CONCEPTS.items() if _spot(t, pats)],
        "hedged": _spot(t, HEDGES),
        "certain_words": _spot(t, CERTAIN),
        "n_words": len(t.split()),
        "has_reason_clause": bool(re.search(r"\b(because|since|so|as|therefore|which means|that'?s why|cause|coz|cuz)\b", t.lower())),
        "quote": t[:200] + ("…" if len(t) > 200 else ""),
        "claims": find_claims(t, priority),
    }


def _cap(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


def _walk_claims(claims: list[dict], label: str) -> list[str]:
    """One sentence per claim, in the learner's order, quoting their words."""
    out = []
    for i, c in enumerate(claims):
        lead = "You said" if i == 0 else ("Then you said" if i == 1 else "You also said")
        q = c["quote"]
        if c["verdict"] == "true":
            out.append(f"{lead} “{q}” — {c['reply']}.")
        elif c["verdict"] == "partly":
            out.append(f"{lead} “{q}” — {c['reply']}.")
        else:
            out.append(f"{lead} “{q}” — {c['reply']}.")
    return out


def compose(status: str, label: str, explanation: str, item: dict, misconception: dict | None, intervention: dict | None,
            correct: bool, probability: float, mode: str = "choice", learner: str | None = None) -> dict:
    try:
        from backend.data import all_misconceptions_for_item
        priority = ([label] if label in KEY_IDEA else []) + all_misconceptions_for_item(item)
    except Exception:
        priority = [label]
    sig = analyse(explanation, priority)
    claims = sig["claims"]
    rng = random.Random(hash(explanation) & 0xFFFF)
    first = learner.split()[0] if learner else None
    name = f"{first}, " if first else ""
    m = misconception or {}
    paras: list[str] = []

    # ---------------- correct ----------------
    if status == "correct":
        concept = item.get("concept") or PROBE_CONCEPT.get(label, "")
        praise = CORRECT_PRAISE.get(concept, "Your reasoning holds up.")
        paras.append(f"{name}{rng.choice(['yes — that is right, and for the right reason.', 'correct, and your reasoning is the real thing, not a guess.', 'right answer, sound reasoning.'])}".strip())
        trues = [c for c in claims if c["verdict"] == "true"]
        if trues:
            paras.append(" ".join(_walk_claims(trues[:3], label)))
        paras.append(praise)
        if sig["hedged"]:
            paras.append("You sounded unsure, but the physics in your sentence is solid — trust that reasoning next time.")
        return {"text": "\n\n".join(_cap(p) for p in paras), "source": "rules", "signals": sig}

    # ---------------- unknown ----------------
    if status == "unknown":
        if sig["n_words"] < 3:
            paras.append(f"{name}I can't see your thinking yet. " + ("The number is right, but a" if correct else "A") +
                         " sentence about why — which forces act, or what the velocity and acceleration are doing — lets me find the idea behind your answer instead of guessing.")
        else:
            trues = [c for c in claims if c["verdict"] == "true"]
            if trues:
                paras.append(f"{name}I can see part of your thinking: " + " ".join(_walk_claims(trues[:2], label)) +
                             " But I can't tell what led you to the option you chose. Say what the forces are doing, or what happens to the velocity next.")
            else:
                paras.append(f"{name}I read “{sig['quote']}” but it doesn't tell me what you were picturing. Name the forces you think act, or say what the velocity and the acceleration are each doing at that moment.")
        return {"text": "\n\n".join(_cap(p) for p in paras), "source": "rules", "signals": sig}

    # ---------------- misconception / flawed reasoning ----------------
    if status == "flawed_reasoning":
        opener = rng.choice(["your answer is right — but the reasoning under it isn't, and that matters more than the tick.",
                             "the option is correct, but the explanation would lead you astray on the next question.",
                             "right answer, wrong road. Let's fix the road."])
    else:
        opener = rng.choice(["not quite — and I can see exactly where it goes sideways.",
                             "a very common way to think about this, and it is wrong in one specific, fixable place.",
                             "close, but one step in your explanation is doing the damage."])
    paras.append(f"{name}{opener}")

    if claims:
        paras.append(" ".join(_walk_claims(claims[:4], label)))
        if not any(c["verdict"] == "false" for c in claims):
            # we saw true/partly claims but no explicit false step: name the hidden step
            trigger, reply = _find_trigger(label, explanation)
            paras.append((f"The step you didn't say out loud is the one that goes wrong: {m.get('believes', '')}" if not trigger else
                          f"The phrase “{trigger}” is where the idea hides. {reply}"))
    else:
        trigger, reply = _find_trigger(label, explanation)
        if trigger:
            paras.append(f"You wrote “{sig['quote']}”. The phrase “{trigger}” is the giveaway. {reply}")
        else:
            paras.append(f"You wrote “{sig['quote']}”. Reading it, the idea underneath is “{m.get('short', '').lower()}” — {m.get('believes', '')}")

    paras.append(f"In one line: {KEY_IDEA.get(label, '')}. {THINK_QUESTION.get(label, '')}")
    if sig["certain_words"]:
        paras.append("You sounded certain, which is worth noticing — this idea feels obviously true, and that is exactly why it survives.")
    if intervention:
        paras.append("Below: the explanation, an animation where you can switch on “what the belief predicts”, and a worked example. Then a different question on the same idea.")

    text = "\n\n".join(_cap(p) for p in paras)
    llm = _llm(status, label, explanation, item, m, sig, first)
    if llm:
        return {"text": llm, "source": "llm", "signals": sig}
    return {"text": text, "source": "rules", "signals": sig}


def _llm(status: str, label: str, explanation: str, item: dict, m: dict, sig: dict, learner: str | None) -> str | None:
    if not llm_available() or not explanation:
        return None
    claims = "\n".join(f"- \"{c['quote']}\" -> {c['verdict']}: {c['reply']}" for c in sig["claims"]) or "- (no recognised claims)"
    prompt = (
        f"Question: {item.get('prompt')}\n"
        f"The learner{' (' + learner + ')' if learner else ''} chose an option that is {'correct' if status == 'flawed_reasoning' else 'wrong'} and explained:\n"
        f"\"{explanation}\"\n\n"
        f"Diagnosed misconception: {m.get('name')} — {m.get('believes')}\nCorrect physics: {m.get('physics')}\n"
        f"Claim-by-claim analysis of their sentence:\n{claims}\n"
        f"Tone: {'hedged' if sig['hedged'] else 'certain' if sig['certain_words'] else 'neutral'}.\n\n"
        "Write the tutor's reply in 3 short paragraphs (max 170 words), addressed to the learner as 'you'. "
        "Paragraph 1: go through what THEY said, quoting their exact words — credit what is true, and say precisely which step is wrong and why. "
        "Paragraph 2: the correct physics in plain language, tied to their own example. "
        "Paragraph 3: one question they should ask themselves next time. No headings, bullets or emojis. Do not repeat the question text."
    )
    return llm_generate(prompt, max_tokens=380, system="You are a warm, precise physics tutor. You respond to what the student actually wrote.")
