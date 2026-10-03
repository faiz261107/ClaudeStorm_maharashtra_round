"""
Voice interaction: turn one spoken utterance into actions (NLP intent parsing).

    "option b because gravity still acts at the top, I'm fairly sure"
      -> {select: "B", explanation: "gravity still acts at the top", confidence: "fairly_sure"}
    "the one that says nine point eight downwards"  -> select by fuzzy match against option text
    "twelve metres per second, a equals f over m"   -> number 12 + working text
    "next question" / "repeat" / "submit" / "test the fix" / "show the belief" -> commands

Pure Python + scikit-learn; no external speech service. Speech-to-text itself happens in the
browser (Web Speech API); this module only interprets the transcript.
"""

from __future__ import annotations

import re

from sklearn.feature_extraction.text import TfidfVectorizer

COMMANDS: list[tuple[str, str]] = [
    (r"\b(next|skip|continue|move on|go on|carry on)\b", "next"),
    (r"\b(repeat|say (it|that) again|read (it|that) again|again please|pardon)\b", "repeat"),
    (r"\b(submit|check (it|my|the)|diagnose|done|that'?s (it|all)|finished)\b", "submit"),
    (r"\b(test (the|my) fix|new situation|transfer|try (it|me) in a new)\b", "test_fix"),
    (r"\b(show|what does) the belief|belief mode|what (i|the student) (thought|believed)\b", "belief"),
    (r"\b(play|pause|stop|replay|restart) (the )?(animation|simulation|video)?\b", "sim"),
    (r"\b(report|finish( the)? session|i'?m done|end (the )?session)\b", "report"),
    (r"\b(clear|start over|delete that|undo)\b", "clear"),
    (r"\b(dark mode|light mode|toggle theme)\b", "theme"),
]

CONFIDENCE: list[tuple[str, str]] = [
    (r"\b(just |only )?(a )?guess(ing)?\b|\bnot sure\b|\bno idea\b|\bi think maybe\b|\bprobably not\b", "guessing"),
    (r"\b(certain|definitely|hundred percent|100 percent|for sure|positive|absolutely|very sure|totally sure|i'?m sure)\b", "certain"),
    (r"\b(fairly|pretty|quite|reasonably|somewhat|moderately|kind of) (sure|confident|certain)\b|\bi think so\b", "fairly_sure"),
]

OPTION_WORDS = {"a": "A", "b": "B", "c": "C", "d": "D", "first": "A", "second": "B", "third": "C", "fourth": "D",
                "one": "A", "two": "B", "three": "C", "four": "D", "last": "D"}

NUM_WORDS = {"zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
             "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
             "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000}


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").lower().replace("’", "'")).strip(" ,.;:-")


_NUMWORD_RUN = re.compile(r"\b(minus |negative )?((zero|oh|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
                          r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|point|and)\b\s*)+")
UNITS = r"\b(metres?|meters?) per second( squared)?\b|\bm/s\^?2?\b|\bm/s²|\bnewtons?\b|\bkilo ?newtons?\b|\bkn\b|\bper second squared\b"


def digits_for_words(text: str) -> str:
    """'nine point eight downward' -> '9.8 downward' (so spoken numbers match option text)."""
    def rep(m):
        run = m.group(0)
        if run.strip() in ("and", "point", "one", "zero", "oh"):
            return run
        v = words_to_number(run)
        return (f"{v:g} " if v is not None else run)
    return _NUMWORD_RUN.sub(rep, text)


def _strip_number_and_units(text: str) -> str:
    t = re.sub(UNITS, " ", text)
    t = _NUMWORD_RUN.sub(" ", t)
    t = re.sub(r"-?\d+(\.\d+)?\s*(thousand|k)?", " ", t)
    return _norm(t)


def words_to_number(text: str) -> float | None:
    """'minus nine point eight' -> -9.8 ; 'forty thousand' -> 40000 ; '12' -> 12 ; 'ten thousand' -> 10000."""
    t = _norm(text).replace(",", "")
    m = re.search(r"-?\d+(\.\d+)?", t)
    if m:
        val = float(m.group(0))
        if re.search(r"\b(thousand|k)\b", t[m.end():m.end() + 10]):
            val *= 1000
        return -val if re.search(r"\b(minus|negative)\b", t[:m.start()]) and val > 0 else val
    toks = re.findall(r"[a-z]+", t)
    if not toks:
        return None
    neg = any(w in ("minus", "negative") for w in toks)
    total, current, frac, after_point, seen = 0.0, 0.0, "", False, False
    for w in toks:
        if w == "point":
            after_point = True; continue
        if after_point:
            if w in NUM_WORDS and NUM_WORDS[w] < 10:
                frac += str(NUM_WORDS[w]); seen = True
            continue
        if w in NUM_WORDS:
            n = NUM_WORDS[w]; seen = True
            if n == 100:
                current = (current or 1) * 100
            elif n == 1000:
                total += (current or 1) * 1000; current = 0
            else:
                current += n
        elif w in ("and",):
            continue
        elif seen:
            break
    if not seen:
        return None
    val = total + current + (float("0." + frac) if frac else 0.0)
    return -val if neg else val


def match_option(text: str, options: list[dict]) -> tuple[str | None, float, str, str]:
    """Return (key, score, how, remainder). Letter/ordinal first, then fuzzy text match against option texts."""
    t = _norm(text)
    m = re.search(r"\b(option|answer|choice|choose|pick|select|go with|i'?ll say|it'?s|its|is it|was it|maybe|probably)\s+(letter\s+)?([abcd]|first|second|third|fourth|one|two|three|four|last)\b", t)
    if m:
        return OPTION_WORDS[m.group(3)], 1.0, "letter", t[m.end():]
    m = re.match(r"^(letter\s+)?([abcd])\b[\s,.:]", t + " ")
    if m:
        return OPTION_WORDS[m.group(2)], 1.0, "letter", t[m.end():]
    m = re.search(r"\bthe (first|second|third|fourth|last) (one|option|answer)\b", t)
    if m:
        return OPTION_WORDS[m.group(1)], 1.0, "ordinal", t[m.end():]
    if not options:
        return None, 0.0, "none", ""
    texts = [_norm(o["text"]) for o in options]
    # keep only the part before a reason clause, drop filler, spoken numbers -> digits
    head = re.split(r"\b(because|since|as|cause|coz|cuz)\b", t, maxsplit=1)[0]
    head = re.sub(r"\b(the one (that|which) says|the answer (that|which) says|i('?ll| will)? (say|go with|pick|choose)|it'?s|its)\b", " ", head)
    head = digits_for_words(head)
    vec = TfidfVectorizer(ngram_range=(1, 2), analyzer="word").fit(texts + [head])
    M = vec.transform(texts); q = vec.transform([head])
    sims = (M @ q.T).toarray().ravel()
    best = int(sims.argmax())
    return (options[best]["key"], float(sims[best]), "fuzzy", "") if sims[best] >= 0.18 else (None, float(sims[best]), "none", "")


def _match_palette(spoken: str, palette: list[str]) -> str | None:
    if not palette:
        return spoken or None
    s = spoken.strip()
    for p in palette:
        if s == p or s in p or p in s:
            return p
    aliases = {"weight": "gravity", "gravity force": "gravity", "normal": "normal force", "reaction": "normal force", "push": "forward push",
               "throw": "throw force", "the throw": "throw force", "engine": "engine force", "drag": "drag + friction", "friction": "friction",
               "air": "air resistance", "air resistance": "air resistance"}
    for k, v in aliases.items():
        if k in s and v in palette:
            return v
    if "drag" in s or "friction" in s:
        for p in palette:
            if "drag" in p or "friction" in p:
                return p
    return None


def parse_utterance(text: str, item: dict | None = None) -> dict:
    t = _norm(text)
    out: dict = {"text": text, "intent": "unknown", "actions": []}
    if not t:
        return out

    for pat, cmd in COMMANDS:
        if re.search(pat, t) and len(t.split()) <= 7:
            out["intent"] = "command"; out["actions"].append({"type": "command", "command": cmd})
            return out

    for pat, level in CONFIDENCE:
        if re.search(pat, t):
            out["actions"].append({"type": "confidence", "value": level})
            t_wo = re.sub(pat, " ", t)
            t = _norm(re.sub(r"\b(i am|i'm|and|,)\s*$", "", t_wo))
            break

    kind = (item or {}).get("kind", "choice")
    reason = None
    parts = re.split(r"\b(because|since|as|cause|coz|cuz|my reasoning is|the reason is)\b", t, maxsplit=1)
    if len(parts) == 3:
        head, reason = parts[0].strip(" ,."), parts[2].strip(" ,.")
    else:
        head = t

    if kind == "working":
        num = words_to_number(head) if head else None
        if num is not None:
            out["actions"].append({"type": "number", "value": num})
            # working = everything that is not the bare number + unit
            rest = reason or _strip_number_and_units(head)
            if rest and len(rest.split()) >= 2:
                out["actions"].append({"type": "explanation", "value": rest})
        elif head:
            out["actions"].append({"type": "explanation", "value": t})
    elif kind == "fbd":
        # "gravity down large", "add normal force up", "remove throw force"
        for m in re.finditer(r"\b(remove|delete)\s+(the\s+)?([a-z +]+?)(\s+arrow)?(?=,|\.|$|\band\b)", t):
            f = _match_palette(m.group(3).strip(), (item or {}).get("palette", []))
            if f:
                out["actions"].append({"type": "remove_force", "force": f})
        for m in re.finditer(r"\b(add\s+|draw\s+)?(a\s+|the\s+)?([a-z +]+?)\s+(pointing\s+|going\s+)?(up|down|left|right)(wards?)?(\s+(small|medium|large|big))?\b", t):
            force = re.sub(r"^(and|then|also|plus|a|the|add|draw)\s+", "", m.group(3).strip())
            force = _match_palette(force, (item or {}).get("palette", []))
            if not force:
                continue
            size = {"small": 1, "medium": 2, "large": 3, "big": 3}.get(m.group(8) or "medium", 2)
            out["actions"].append({"type": "add_force", "force": force, "direction": m.group(5), "size": size})
        if reason:
            out["actions"].append({"type": "explanation", "value": reason})
    else:
        key, score, how, rest = match_option(head, (item or {}).get("options", []))
        if key:
            out["actions"].append({"type": "select", "key": key, "score": round(score, 2), "how": how})
            rest = _norm(re.sub(r"^\s*(and|,|-|:|so|then)\s*", "", rest))
            if reason:
                out["actions"].append({"type": "explanation", "value": reason})
            elif rest and len(rest.split()) >= 3:
                out["actions"].append({"type": "explanation", "value": rest})
        elif reason:
            out["actions"].append({"type": "explanation", "value": reason})
        elif head:
            # no option identified: treat the whole thing as reasoning
            out["actions"].append({"type": "explanation", "value": t})

    if out["actions"]:
        types = {a["type"] for a in out["actions"]}
        out["intent"] = "answer" if types & {"select", "number", "add_force", "explanation"} else "command"
    return out
