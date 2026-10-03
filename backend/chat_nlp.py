"""
Chat NLP: understands a free-text (typed or spoken) chat message from the learner.

Pipeline for one message:
  1. normalise + detect small talk (greeting, thanks, frustration)
  2. global commands (next, repeat, hint, explain more, show animation, report, ...)
  3. physics QUESTIONS from the learner ("what is acceleration?", "why doesn't the throw force count?")
     -> answered by TF-IDF retrieval over a small knowledge base (optional LLM if ANTHROPIC_API_KEY is set)
  4. otherwise an ANSWER to the current item -> backend.voice.parse_utterance
     (option by letter / ordinal / fuzzy text, reason clause, confidence, spoken numbers, diagram arrows)

Returns {"intent": ..., "actions": [...], "reply": optional tutor text, "sources": [...]}
"""

from __future__ import annotations

import os
import re

from sklearn.feature_extraction.text import TfidfVectorizer

from backend.data import CONCEPTS, INTERVENTIONS, MISCONCEPTIONS
from backend.voice import parse_utterance

# ---------------------------------------------------------------------------
# Knowledge base for learner questions
# ---------------------------------------------------------------------------

GLOSSARY: list[tuple[str, str]] = [
    ("what is velocity speed and direction",
     "Velocity is speed with a direction — how fast something moves and which way. A ball going up at 5 m/s and one going down at 5 m/s have the same speed but opposite velocities."),
    ("what is acceleration rate of change of velocity",
     "Acceleration is how quickly the velocity is changing (a = Δv/Δt). It is not the velocity itself: something can be momentarily at rest and still be accelerating, like a ball at the top of its flight."),
    ("what is force push pull interaction",
     "A force is a push or pull that one object exerts on another. Every force needs an object applying it — if you cannot name the object doing the pushing, the force is not there."),
    ("what is inertia newton first law keep moving",
     "Inertia is the tendency of an object to keep its velocity. Newton's first law: with no net force, an object at rest stays at rest and a moving object keeps moving in a straight line at constant speed. No force is needed to keep moving."),
    ("newton second law f equals m a net force mass acceleration",
     "Newton's second law: F_net = m·a. The net force sets the acceleration, not the velocity. Double the net force and the acceleration doubles; double the mass and it halves."),
    ("newton third law action reaction equal opposite pairs",
     "Newton's third law: when A pushes on B, B pushes back on A with a force of exactly the same size in the opposite direction — whatever their masses or speeds. The effects differ because a = F/m."),
    ("what is g gravity 9.8 acceleration due to gravity free fall",
     "g ≈ 9.8 m/s² is the acceleration of any object in free fall near Earth's surface, whatever its mass. Gravity pulls a heavier object harder, but it also has more inertia, so a = mg/m = g."),
    ("mass versus weight difference kilograms newtons",
     "Mass (kg) is how much matter and inertia an object has. Weight (N) is the gravitational force on it: W = m·g. A 10 kg stone weighs about 98 N on Earth."),
    ("net force resultant sum of forces balanced",
     "The net force is the sum of all forces, taking direction into account. If the forces balance, the net force is zero and the velocity does not change."),
    ("free body diagram how to draw forces arrows",
     "A free-body diagram shows only the forces acting ON one object, as arrows from it. For each arrow, name the object applying it. Motion is not a force — never draw an arrow just because the object is moving that way."),
    ("terminal velocity constant speed falling drag",
     "At terminal velocity, air drag has grown until it equals the weight. The forces balance, so the net force and the acceleration are zero and the speed stays constant."),
    ("why does a feather fall slowly air resistance vacuum moon hammer",
     "A feather falls slowly only because air resistance is large compared with its tiny weight. In a vacuum — or on the Moon, as Apollo 15 showed — a hammer and a feather land together."),
    ("momentum mass times velocity",
     "Momentum is mass × velocity (p = m·v). It is not a force. A fast truck has a lot of momentum, but in a collision the forces between it and a car are still equal and opposite."),
    ("how does re learn work what do you do tutor",
     "I ask a question, you answer in your own words — type or speak. I work out the idea behind your answer, explain exactly that, then test you in a new situation. An idea only counts as fixed when the answer is right AND the reasoning is clean, twice, and it still holds later."),
]


def _kb() -> list[dict]:
    docs = [{"title": t.split(" ")[2] if t.startswith("what is") else t.split(" ")[0], "query": t, "text": a, "source": "glossary"} for t, a in GLOSSARY]
    for mid, m in MISCONCEPTIONS.items():
        iv = INTERVENTIONS[mid]
        docs.append({"title": m["name"], "query": f"{m['name']} {m['short']} {m['believes']} {m['description']}",
                     "text": f"{iv['headline']} {m['physics']}", "source": mid})
    for key, line in CONCEPTS.items():
        docs.append({"title": key, "query": line, "text": line + ".", "source": "concept"})
    return docs


KB = _kb()


def _clean_q(q: str) -> str:
    q = q.lower().replace("newton's", "newton").replace("newtons", "newton").replace("'s", "")
    q = re.sub(r"\b(what|whats|what is|what are|why|how|does|do|is|are|the|a|an|of|me|tell|explain|define|please|can you|could you|mean|meaning)\b", " ", q)
    return re.sub(r"[^a-z0-9. ]+", " ", q)


_VQ = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"(?u)\b\w+\b").fit([_clean_q(d["query"]) for d in KB])
_MQ = _VQ.transform([_clean_q(d["query"]) for d in KB])
_VT = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english").fit([d["text"] for d in KB])
_MT = _VT.transform([d["text"] for d in KB])
import numpy as _np  # noqa: E402
_PRIOR = _np.array([1.0 if d["source"] == "glossary" else 0.85 for d in KB])


def answer_question(q: str, context: str = "") -> dict:
    cq = _clean_q(q)
    sims = 0.75 * (_MQ @ _VQ.transform([cq]).T).toarray().ravel() + 0.25 * (_MT @ _VT.transform([cq]).T).toarray().ravel()
    sims = sims * _PRIOR
    order = sims.argsort()[::-1]
    best = KB[order[0]]
    if sims[order[0]] < 0.08:
        return {"reply": "I'm not sure I can answer that one. I'm best at velocity, acceleration, forces, Newton's laws and free fall — try asking about one of those, or just answer the question and I'll explain as we go.",
                "sources": [], "score": float(sims[order[0]])}
    reply = best["text"]
    llm = _llm_answer(q, reply, context)
    return {"reply": llm or reply, "sources": [best["source"]], "score": float(sims[order[0]]), "generated": bool(llm)}


def _llm_answer(q: str, grounding: str, context: str) -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic  # type: ignore
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=os.environ.get("RELEARN_LLM_MODEL", "claude-sonnet-4-5"), max_tokens=220,
            messages=[{"role": "user", "content": (
                "You are a friendly physics tutor in a chat. Answer the learner's question in at most 3 short sentences, "
                "using this reference text as ground truth. Do not reveal the answer to the current quiz question.\n\n"
                f"Reference: {grounding}\nCurrent question (do not answer it): {context}\nLearner asks: {q}")}])
        return "".join(getattr(b, "text", "") for b in msg.content).strip() or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

SMALLTALK = [
    (r"^(hi|hello|hey|hii+|good (morning|afternoon|evening)|namaste)\b", "greeting"),
    (r"\b(thanks|thank you|thx|ty|great|awesome|cool|nice)\b[!. ]*$", "thanks"),
    (r"\b(i don'?t (get|understand)( it)?|confused|this is hard|i'?m lost|makes no sense|stuck)\b", "confused"),
    (r"\b(who are you|what are you|are you (a )?(bot|ai|human))\b", "who"),
]

# "what can you explain?" is about the tutor, not physics: answering it from the knowledge base gave a random fact
CAPABILITIES = (r"\bwhat (all |else |topics |things |stuff )?(can|do|could) (you|u) (explain|teach|answer|help( me)? with|do|know)\b"
                r"|\bwhat (topics|things|can i ask)\b|\bwhat do you know\b")

CHAT_COMMANDS = [
    (r"^(skip( the)? (reason|why|explanation)|no reason|i don'?t know why|just the answer|no explanation)[.!]?$", "skip_reason"),
    (r"^(next|next question|skip|continue|move on|go on|ok next|okay next|let'?s continue|carry on)[.!]?$", "next"),
    (r"^(repeat|say (it|that) again|repeat (the )?question|read (it|that) again|again|pardon|what was the question)\??[.!]?$", "repeat"),
    (r"\b(give me a |any |a )?hint\b|\bhelp me\b", "hint"),
    (r"\b(explain (more|again|it|that)|tell me more|more detail|elaborate|go deeper|why is that)\b", "explain_more"),
    (r"\b(show|play|open) (me )?(the )?(animation|simulation|sim|video|demo)\b", "show_sim"),
    (r"\b(show|what does) (me )?the belief|belief mode\b", "belief"),
    (r"\b(worked example|show (me )?(the )?(steps|example|working))\b", "worked"),
    (r"\b(test me|test the fix|new situation|i'?m ready|ready|try another|another question like (this|that))\b", "test_fix"),
    (r"\b(report|how am i doing|my progress|progress|summary|finish( the)? session|end (the )?session|i'?m done|stop)\b", "report"),
    (r"\b(my (thinking )?map|what have i fixed|what'?s left)\b", "map"),
    (r"\b(dark mode|light mode|toggle theme)\b", "theme"),
    (r"\b(voice (on|off)|speak to me|talk to me|stop talking|mute)\b", "voice"),
    (r"\b(start over|restart|new session|start again)\b", "restart"),
]

QUESTION_START = r"^(what|why|how|when|where|which|who|is|are|does|do|can|could|should|would|explain|define|tell me|what'?s|whats)\b"


def looks_like_question(t: str) -> bool:
    return t.endswith("?") or bool(re.match(QUESTION_START, t))


def understand(text: str, item: dict | None = None, phase: str = "question", context: str = "") -> dict:
    raw = (text or "").strip()
    t = re.sub(r"\s+", " ", raw.lower()).strip()
    out: dict = {"text": raw, "intent": "unknown", "actions": []}
    if not t:
        return out

    if re.search(CAPABILITIES, t):
        out["intent"] = "capabilities"
        return out

    for pat, kind in SMALLTALK:
        if re.search(pat, t) and len(t.split()) <= 6:
            out["intent"] = kind
            return out

    for pat, cmd in CHAT_COMMANDS:
        if re.search(pat, t) and len(t.split()) <= 8:
            out["intent"] = "command"; out["actions"].append({"type": "command", "command": cmd})
            return out

    answering = phase in ("question", "probe", "recheck", "reason", "working", "fbd")
    parsed = parse_utterance(raw, item) if (answering and item) else {"actions": []}
    answer_types = {a["type"] for a in parsed["actions"]}
    is_q = looks_like_question(t)

    # A question that is not clearly an answer -> knowledge-base answer
    if is_q and not ({"select", "number", "add_force"} & answer_types):
        ans = answer_question(raw, context)
        out.update({"intent": "question", **ans})
        return out

    if answering and parsed["actions"]:
        out["intent"] = "answer"; out["actions"] = parsed["actions"]
        return out

    if not answering and is_q:
        ans = answer_question(raw, context)
        out.update({"intent": "question", **ans})
        return out

    out["intent"] = "chat"
    return out
