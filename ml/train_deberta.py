"""
OPTIONAL: fine-tune DeBERTa-v3-base as the misconception classifier (PRD §8, M3).

The default TF-IDF model already meets every v1 target and trains in < 1 s.
Use this when you want a transformer backend (recommended once the dataset
contains real student writing). Requires:

    pip install torch transformers datasets accelerate sentencepiece

Trains on the same item-level split as ml/train.py and saves to ml/models/deberta/.
backend/diagnosis.py picks the DeBERTa model up automatically when that folder
exists (set RELEARN_BACKEND=sklearn to force the light model).

Usage:
    python ml/train_deberta.py --epochs 4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA = ROOT / "ml" / "data"
OUT = ROOT / "ml" / "models" / "deberta"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="microsoft/deberta-v3-base")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--all-items", action="store_true", help="train on every item (for serving), not just the train split")
    args = ap.parse_args()

    try:
        import numpy as np
        import pandas as pd
        import torch  # noqa: F401
        from datasets import Dataset
        from transformers import (AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding,
                                  Trainer, TrainingArguments)
    except ImportError as e:  # pragma: no cover
        sys.exit(f"Missing dependency ({e}). Install: pip install torch transformers datasets accelerate sentencepiece")

    df = pd.read_csv(DATA / "responses.csv")
    split = json.loads((DATA / "split.json").read_text(encoding="utf-8"))
    labels = sorted(df.label.unique())
    label2id = {l: i for i, l in enumerate(labels)}
    df["text"] = "Answer: " + df.option_text + " | Explanation: " + df.explanation
    df["labels"] = df.label.map(label2id)

    train_df = df if args.all_items else df[df.item_id.isin(split["train_items"])]
    eval_df = df[df.item_id.isin(split["test_items"])]

    tok = AutoTokenizer.from_pretrained(args.model)
    enc = lambda b: tok(b["text"], truncation=True, max_length=128)  # noqa: E731
    train_ds = Dataset.from_pandas(train_df[["text", "labels"]]).map(enc, batched=True)
    eval_ds = Dataset.from_pandas(eval_df[["text", "labels"]]).map(enc, batched=True)

    model = AutoModelForSequenceClassification.from_pretrained(
        args.model, num_labels=len(labels),
        id2label={i: l for l, i in label2id.items()}, label2id=label2id)

    def compute_metrics(p):
        from sklearn.metrics import accuracy_score, f1_score
        preds = np.argmax(p.predictions, axis=1)
        return {"accuracy": accuracy_score(p.label_ids, preds),
                "macro_f1": f1_score(p.label_ids, preds, average="macro")}

    targs = TrainingArguments(
        output_dir=str(OUT / "checkpoints"), num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch, per_device_eval_batch_size=32,
        learning_rate=args.lr, weight_decay=0.01, warmup_ratio=0.06,
        eval_strategy="epoch", save_strategy="no", logging_steps=25, report_to=[],
    )
    trainer = Trainer(model=model, args=targs, train_dataset=train_ds, eval_dataset=eval_ds,
                      data_collator=DataCollatorWithPadding(tok), compute_metrics=compute_metrics)
    trainer.train()
    print(trainer.evaluate())
    OUT.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(OUT))
    tok.save_pretrained(str(OUT))
    print(f"Saved DeBERTa classifier to {OUT}. Restart the API to use it.")


if __name__ == "__main__":
    main()
