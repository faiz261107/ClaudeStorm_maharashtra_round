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
