"""
Train the misconception classifier (FR-2, M3).

  * Splits by ITEM (question / probe), never by row, so test items are fully unseen.
  * Trains three models:
        classifier_heldout.joblib   trained on train-split items   -> used by evaluate.py
        classifier_template.joblib  trained on template rows only  -> tests transfer to hand-written text
        classifier.joblib           trained on everything          -> served by the API
  * Fits the description embedder used for unseen-misconception fallback.

Usage:
    python ml/train.py
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import pandas as pd

# Windows consoles may default to a legacy code page; keep ✓/✗/≥ printable.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.data import MISCONCEPTIONS, PROBES, QUESTIONS  # noqa: E402
from ml.model import MODEL_DIR, DescriptionEmbedder, MisconceptionClassifier  # noqa: E402

DATA = ROOT / "ml" / "data" / "responses.csv"
SPLIT = ROOT / "ml" / "data" / "split.json"
SEED = 7


def make_split(seed: int = SEED) -> dict:
    """Hold out ~25% of questions (stratified by topic) and one probe per misconception."""
    rng = random.Random(seed)
    by_topic: dict[str, list[str]] = {}
    for q in QUESTIONS:
        by_topic.setdefault(q["topic"], []).append(q["id"])
    test_items: list[str] = []
    for topic, ids in by_topic.items():
        k = max(1, round(len(ids) * 0.3))
        test_items += rng.sample(ids, k)
    for m, plist in PROBES.items():
        test_items.append(rng.choice(plist)["id"])
    all_items = [q["id"] for q in QUESTIONS] + [p["id"] for pl in PROBES.values() for p in pl]
    train_items = [i for i in all_items if i not in test_items]
    return {"seed": seed, "train_items": sorted(train_items), "test_items": sorted(test_items)}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="also train the served model on ml/data/real_responses.csv (teacher-labelled rows)")
    args = ap.parse_args()
    if not DATA.exists():
        print("Dataset missing – generating it first.")
        from ml.generate_dataset import main as gen
        gen()

    df = pd.read_csv(DATA)
    split = make_split()
    SPLIT.write_text(json.dumps(split, indent=2), encoding="utf-8")
    train_df = df[df.item_id.isin(split["train_items"])]
    test_df = df[df.item_id.isin(split["test_items"])]
    print(f"Rows: {len(df)} total | {len(train_df)} train | {len(test_df)} test "
          f"({len(split['test_items'])} held-out items: {', '.join(split['test_items'])})")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    MisconceptionClassifier().fit(train_df.explanation, train_df.option_text, train_df.label) \
        .save(MODEL_DIR / "classifier_heldout.joblib")
    print(f"classifier_heldout.joblib  trained on train items          ({time.time() - t0:.1f}s)")

    t0 = time.time()
    tmpl = df[df.source == "template"]
    MisconceptionClassifier().fit(tmpl.explanation, tmpl.option_text, tmpl.label) \
        .save(MODEL_DIR / "classifier_template.joblib")
    print(f"classifier_template.joblib trained on template rows only   ({time.time() - t0:.1f}s)")

    t0 = time.time()
    # Synthetic-only copy of the served model: evaluate.py scores real rows with this one,
    # so folding real rows into training (--real) never leaks them into their own test.
    synthetic = MisconceptionClassifier().fit(df.explanation, df.option_text, df.label)
    synthetic.save(MODEL_DIR / "classifier_synthetic.joblib")
    served = df
    real_path = ROOT / "ml" / "data" / "real_responses.csv"
    if args.real and real_path.exists():
        real = pd.read_csv(real_path)
        real = real[real.label != "OTHER"]  # "fits no known misconception" is not a trainable class
        served = pd.concat([df, real[df.columns.intersection(real.columns)]], ignore_index=True)
        print(f"  + {len(real)} real learner rows folded into the served model")
        MisconceptionClassifier().fit(served.explanation, served.option_text, served.label) \
            .save(MODEL_DIR / "classifier.joblib")
    else:
        synthetic.save(MODEL_DIR / "classifier.joblib")
    print(f"classifier.joblib          trained on all rows (served)    ({time.time() - t0:.1f}s)")

    descriptions = {k: v["description"] + " " + v["believes"] for k, v in MISCONCEPTIONS.items()}
    DescriptionEmbedder().fit(descriptions, corpus=df.explanation.tolist()).save(MODEL_DIR / "embedder.joblib")
    print("embedder.joblib            description embedder for unseen-misconception fallback")
    print("\nDone. Next: python ml/evaluate.py")


if __name__ == "__main__":
    main()
