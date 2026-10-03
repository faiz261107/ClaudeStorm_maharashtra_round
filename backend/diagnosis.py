"""
Diagnosis service: diagnose(item, choice, explanation) -> status, label, confidence.

Wraps the trained classifier + description embedder + shared decision rule.
Loads once at startup; a single diagnosis takes a few milliseconds on CPU.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.data import MISCONCEPTIONS, NONE_LABEL, all_misconceptions_for_item, option_of  # noqa: E402
from ml.decision import Decision, DecisionConfig, decide  # noqa: E402
from ml.model import MODEL_DIR, DescriptionEmbedder, load_best_classifier  # noqa: E402


class Diagnoser:
    def __init__(self, cfg: DecisionConfig | None = None):
        self.cfg = cfg or DecisionConfig()
        self.classifier, self.backend = load_best_classifier()
        descriptions = {k: v["description"] + " " + v["believes"] for k, v in MISCONCEPTIONS.items()}
        emb_path = MODEL_DIR / "embedder.joblib"
        self.embedder = (DescriptionEmbedder.load(emb_path, descriptions) if emb_path.exists()
                         else DescriptionEmbedder().fit(descriptions))
        self.known_labels = set(self.classifier.classes_)

    def diagnose(self, item: dict, choice: str, explanation: str) -> tuple[Decision, float]:
        """Returns (decision, latency_ms)."""
        t0 = time.perf_counter()
        opt = option_of(item, choice)
        if opt is None:
            raise ValueError(f"unknown option {choice!r} for item {item['id']}")
        is_correct = choice == item["answer"]
        probs = self.classifier.predict_one(explanation, opt["text"])
        sims = self.embedder.similarities(explanation)
        d = decide(probs, explanation=explanation, is_correct=is_correct,
                   option_misconceptions=list(opt["misconceptions"]), similarities=sims, cfg=self.cfg,
                   item_misconceptions=all_misconceptions_for_item(item))
        return d, (time.perf_counter() - t0) * 1000

    @staticmethod
    def is_correct(item: dict, choice: str) -> bool:
        return choice == item["answer"]

    # ---------------- working mode (number + shown working) ----------------
    @staticmethod
    def working_is_correct(item: dict, value: float) -> bool:
        target, tol = float(item["answer_value"]), float(item.get("tolerance", 0.0))
        if abs(value - target) <= tol:
            return True
        return bool(item.get("accept_abs")) and abs(abs(value) - abs(target)) <= tol

    def diagnose_working(self, item: dict, value: float | None, working: str) -> tuple[Decision, float, dict | None]:
        """Rules on the working first (precise, explainable); classifier on the text as backup."""
        import re
        t0 = time.perf_counter()
        norm = re.sub(r"\s+", " ", (working or "").lower().replace("×", "x").replace("·", "x").replace("−", "-"))
        is_correct = value is not None and self.working_is_correct(item, value)
        matched: dict | None = None
        for pat in item["patterns"]:
            if re.search(pat["regex"], norm):
                matched = pat
                break
        if matched:
            label = matched["misconception"]
            probs = {label: 0.9}
            status = "flawed_reasoning" if is_correct else "misconception"
            d = Decision(status, label, 0.9, probs, "working-rules", [f"working pattern matched: {matched['why']}"])
            return d, (time.perf_counter() - t0) * 1000, matched
        if is_correct:
            # Right number and no misconception pattern in the working: count it as correct.
            # (Flawed-reasoning flags in working mode come from the explainable rules only.)
            return Decision("correct", NONE_LABEL, 0.9, {NONE_LABEL: 0.9}, "working-rules", []), (time.perf_counter() - t0) * 1000, None
        # wrong number: text classifier on the working, with the item-level prior
        probs = self.classifier.predict_one(working, item["prompt"][:60])
        sims = self.embedder.similarities(working)
        d = decide(probs, explanation=working, is_correct=is_correct, option_misconceptions=all_misconceptions_for_item(item),
                   similarities=sims, cfg=self.cfg, item_misconceptions=all_misconceptions_for_item(item))
        if d.status == "unknown" and value is not None and not is_correct and len((working or "").split()) >= self.cfg.min_words:
            d.notes.append("number is off but the working does not show a known misconception")
        return d, (time.perf_counter() - t0) * 1000, None

    def info(self) -> dict:
        return {"backend": self.backend, "labels": sorted(self.known_labels),
                "embedder": self.embedder.backend, "abstain_threshold": self.cfg.abstain_threshold}


_singleton: Diagnoser | None = None


def get_diagnoser() -> Diagnoser:
    global _singleton
    if _singleton is None:
        if not (MODEL_DIR / "classifier.joblib").exists():
            raise RuntimeError("No trained model found. Run:  python ml/train.py")
        _singleton = Diagnoser()
    return _singleton


__all__ = ["Diagnoser", "get_diagnoser", "NONE_LABEL"]


# ---------------- free-body-diagram mode ----------------

def _fbd_find(diagram: list[dict], force: str) -> dict | None:
    return next((a for a in diagram if a.get("force") == force), None)


def diagnose_fbd(self: Diagnoser, item: dict, diagram: list[dict], explanation: str = "") -> tuple[Decision, float, dict]:
    """Rules over the drawn arrows; the optional sentence disambiguates confusable pairs.
    Returns (decision, latency_ms, feedback) where feedback lists what is missing / extra / wrong."""
    t0 = time.perf_counter()
    diagram = [a for a in (diagram or []) if a.get("force")]
    feedback = {"missing": [], "extra": [], "wrong_direction": [], "wrong_size": [], "ok": []}
    hits: list[tuple[list[str], str]] = []

    if not diagram and item.get("empty_rule"):
        hits.append((item["empty_rule"]["misconceptions"], item["empty_rule"]["why"]))
    for req in item.get("required", []):
        a = _fbd_find(diagram, req["force"])
        if a is None:
            feedback["missing"].append(req["force"])
        elif a.get("direction") != req["direction"]:
            feedback["wrong_direction"].append(f"{req['force']} should point {req['direction']}")
        else:
            feedback["ok"].append(req["force"])
    for fb in item.get("forbidden", []):
        if _fbd_find(diagram, fb["force"]) is not None:
            feedback["extra"].append(fb["force"])
            if fb["misconceptions"]:
                hits.append((fb["misconceptions"], fb["why"]))
    for dr in item.get("direction_rules", []):
        a = _fbd_find(diagram, dr["force"])
        if a is not None and a.get("direction") == dr["direction"]:
            hits.append((dr["misconceptions"], dr["why"]))
    for sr in item.get("size_rules", []):
        big, small = _fbd_find(diagram, sr["bigger"]), _fbd_find(diagram, sr["smaller"])
        if big is not None and small is not None and int(big.get("size", 2)) > int(small.get("size", 2)):
            feedback["wrong_size"].append(f"{sr['bigger']} drawn larger than {sr['smaller']}")
            hits.append((sr["misconceptions"], sr["why"]))

    correct = not feedback["missing"] and not feedback["extra"] and not feedback["wrong_direction"] and not feedback["wrong_size"]
    latency = (time.perf_counter() - t0) * 1000
    if hits:
        cands, why = hits[0]
        label = cands[0]
        source = "diagram-rules"
        note = why
        if len(cands) > 1 and explanation and len(explanation.split()) >= self.cfg.min_words:
            # confusable pair: let the learner's sentence decide
            probs = self.classifier.predict_one(explanation, item["prompt"][:60])
            restricted = {k: v for k, v in probs.items() if k in cands}
            if restricted:
                label = max(restricted.items(), key=lambda kv: kv[1])[0]
                source = "diagram+text"
                note += f" Your sentence reads as {label}."
        elif len(cands) > 1:
            note += " Add a sentence saying why you drew it and I can tell which."
        d = Decision("misconception", label, 0.9 if len(cands) == 1 or source == "diagram+text" else 0.7,
                     {c: (0.9 if c == label else 0.1) for c in cands}, source, [note])
        return d, latency, feedback
    if correct:
        return Decision("correct", NONE_LABEL, 0.9, {NONE_LABEL: 0.9}, "diagram-rules", []), latency, feedback
    # incomplete but no misconception pattern: ask for more
    return Decision("unknown", "UNKNOWN", 0.5, {}, "abstain",
                    ["diagram incomplete: " + ", ".join(feedback["missing"] + feedback["wrong_direction"])]), latency, feedback


Diagnoser.diagnose_fbd = diagnose_fbd
