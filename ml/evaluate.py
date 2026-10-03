"""
Evaluation suite (FR-11, M4). Reports every metric in PRD §10.

  * accuracy + macro-F1 on held-out QUESTIONS (split by item, never by row)
  * confusion matrix (json + png)
  * confusable-pair accuracy   – rows whose chosen option maps to 2+ misconceptions
  * flawed-reasoning recall    – right answer, wrong idea rows correctly flagged
  * unseen-misconception top-1 – leave-one-misconception-out, embedding fallback
  * calibration (ECE, 10 bins) on the confidence the product shows
  * hand-written transfer      – model trained on template rows only, tested on all hand rows
  * abstention                 – vague rows -> unknown; valid rows not abstained
  * latency                    – ms per diagnosis on this CPU

Writes ml/reports/metrics.json, confusion_matrix.png, report.md.
The API serves metrics.json at GET /api/metrics so judges can see it in the UI.

Usage:
    python ml/evaluate.py
"""

from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support

# Windows consoles may default to a legacy code page; keep ✓/✗/≥ printable.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.data import ITEM_INDEX, MISCONCEPTION_IDS, MISCONCEPTIONS, all_misconceptions_for_item, option_of  # noqa: E402
from ml.decision import NONE_LABEL, DecisionConfig, decide  # noqa: E402
from ml.model import MODEL_DIR, DescriptionEmbedder, MisconceptionClassifier  # noqa: E402

DATA = ROOT / "ml" / "data"
REPORTS = ROOT / "ml" / "reports"
LABELS = MISCONCEPTION_IDS + [NONE_LABEL]
TARGETS = {
    "macro_f1_heldout_questions": 0.80,
    "confusable_pair_accuracy": 0.75,
    "flawed_reasoning_recall": 0.70,
    "unseen_misconception_top1": 0.60,
    "ece": 0.10,
}


def option_map(row) -> tuple[list[str], bool]:
    item = ITEM_INDEX[row.item_id]
    if item.get("kind") == "working":
        return all_misconceptions_for_item(item), bool(row.correct)
    opt = option_of(item, row.option_key)
    return list(opt["misconceptions"]), bool(row.correct)


def served_or(clf):
    """Model for scoring real rows: trained on all synthetic data and never on real rows,
    even if the served model was retrained with `train.py --real`."""
    for name in ("classifier_synthetic.joblib", "classifier.joblib"):
        p = MODEL_DIR / name
        if p.exists():
            return MisconceptionClassifier.load(p)
    return clf


def run_pipeline(clf, df: pd.DataFrame, embedder: DescriptionEmbedder | None = None,
                 cfg: DecisionConfig | None = None) -> pd.DataFrame:
    """Full product decision rule on every row. Returns df with pred/conf/status columns."""
    probs = clf.predict_proba(df.explanation.tolist(), df.option_text.tolist())
    preds, confs, statuses, sources = [], [], [], []
    for row, p in zip(df.itertuples(), probs):
        allowed, is_correct = option_map(row)
        sims = embedder.similarities(row.explanation) if embedder else None
        d = decide(dict(zip(clf.classes_, map(float, p))), explanation=row.explanation,
                   is_correct=is_correct, option_misconceptions=allowed, similarities=sims, cfg=cfg,
                   item_misconceptions=all_misconceptions_for_item(ITEM_INDEX[row.item_id]))
        preds.append(d.label); confs.append(d.confidence); statuses.append(d.status); sources.append(d.source)
    out = df.copy()
    out["pred"], out["conf"], out["status"], out["source_rule"] = preds, confs, statuses, sources
    return out


def expected_calibration_error(conf: np.ndarray, correct: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (conf > lo) & (conf <= hi)
        if mask.any():
            ece += mask.mean() * abs(correct[mask].mean() - conf[mask].mean())
    return float(ece)


def plot_confusion(cm: np.ndarray, labels: list[str], path: Path, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.2, 6))
    im = ax.imshow(cm, cmap="Purples")
    ax.set_xticks(range(len(labels))); ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=9); ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Predicted"); ax.set_ylabel("True"); ax.set_title(title)
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, int(cm[i, j]), ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "#1b1f3b", fontsize=9)
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA / "responses.csv")
    vague = pd.read_csv(DATA / "vague.csv")
    split = json.loads((DATA / "split.json").read_text(encoding="utf-8"))
    cfg = DecisionConfig()
    metrics: dict = {"targets": TARGETS, "decision_config": cfg.__dict__,
                     "dataset": {"rows": int(len(df)), "items": int(df.item_id.nunique()),
                                 "hand_rows": int((df.source == "hand").sum()),
                                 "label_counts": df.label.value_counts().to_dict()},
                     "split": split}

    # ---------------- 1. held-out items ----------------
    clf = MisconceptionClassifier.load(MODEL_DIR / "classifier_heldout.joblib")
    test = df[df.item_id.isin(split["test_items"])]
    res = run_pipeline(clf, test, embedder=None, cfg=cfg)
    answered = res[res.status != "unknown"]

    def scores(frame: pd.DataFrame) -> dict:
        if len(frame) == 0:
            return {"n": 0}
        return {
            "n": int(len(frame)),
            "accuracy": float(accuracy_score(frame.label, frame.pred)),
            "macro_f1": float(f1_score(frame.label, frame.pred, labels=LABELS, average="macro", zero_division=0)),
        }

    metrics["heldout_all_items"] = scores(answered)
    metrics["heldout_questions_only"] = scores(answered[answered.item_kind == "question"])
    metrics["heldout_probes_only"] = scores(answered[answered.item_kind == "probe"])
    metrics["heldout_hand_rows"] = scores(answered[answered.source == "hand"])
    metrics["abstain_rate_on_valid_rows"] = float((res.status == "unknown").mean())

    p, r, f, s = precision_recall_fscore_support(answered.label, answered.pred, labels=LABELS, zero_division=0)
    metrics["per_label"] = {lab: {"precision": float(pi), "recall": float(ri), "f1": float(fi), "support": int(si)}
                            for lab, pi, ri, fi, si in zip(LABELS, p, r, f, s)}

    cm = confusion_matrix(answered.label, answered.pred, labels=LABELS)
    metrics["confusion_matrix"] = {"labels": LABELS, "matrix": cm.tolist()}
    plot_confusion(cm, LABELS, REPORTS / "confusion_matrix.png", "Held-out items (split by question)")

    # ---------------- 2. confusable pairs ----------------
    conf_mask = [len(option_map(r)[0]) >= 2 and not option_map(r)[1] for r in answered.itertuples()]
    confusable = answered[conf_mask]
    metrics["confusable_pair_accuracy"] = float(accuracy_score(confusable.label, confusable.pred)) if len(confusable) else None
    metrics["confusable_pair_n"] = int(len(confusable))

    # ---------------- 3. flawed-reasoning recall ----------------
    flawed = res[(res.correct == 1) & (res.label != NONE_LABEL)]
    flagged = flawed[flawed.status == "flawed_reasoning"]
    metrics["flawed_reasoning_recall"] = float(len(flagged) / len(flawed)) if len(flawed) else None
    metrics["flawed_reasoning_exact_label"] = float((flagged.pred == flagged.label).sum() / len(flawed)) if len(flawed) else None
    metrics["flawed_reasoning_n"] = int(len(flawed))
    # false alarms: correct answer + correct reasoning flagged as flawed
    clean = res[(res.correct == 1) & (res.label == NONE_LABEL)]
    metrics["flawed_reasoning_false_alarm_rate"] = float((clean.status == "flawed_reasoning").mean()) if len(clean) else None

    # ---------------- 4. calibration ----------------
    conf = answered.conf.to_numpy(); hit = (answered.pred == answered.label).to_numpy().astype(float)
    metrics["ece"] = expected_calibration_error(conf, hit)
    bins = np.linspace(0, 1, 11)
    metrics["reliability"] = [
        {"bin": f"{lo:.1f}-{hi:.1f}", "n": int(((conf > lo) & (conf <= hi)).sum()),
         "confidence": float(conf[(conf > lo) & (conf <= hi)].mean()) if ((conf > lo) & (conf <= hi)).any() else None,
         "accuracy": float(hit[(conf > lo) & (conf <= hi)].mean()) if ((conf > lo) & (conf <= hi)).any() else None}
        for lo, hi in zip(bins[:-1], bins[1:])
    ]

    # ---------------- 5. unseen misconceptions (leave-one-out + embedding fallback) ----------------
    descriptions = {k: v["description"] + " " + v["believes"] for k, v in MISCONCEPTIONS.items()}
    unseen: dict[str, dict] = {}
    for held in MISCONCEPTION_IDS:
        train = df[(df.label != held) & (df.item_id.isin(split["train_items"]))]
        sub = MisconceptionClassifier().fit(train.explanation, train.option_text, train.label)
        emb = DescriptionEmbedder().fit(descriptions, corpus=train.explanation.tolist())
        target = df[(df.label == held) & (df.item_id.isin(split["test_items"]))]
        if len(target) == 0:
            target = df[df.label == held].sample(min(60, int((df.label == held).sum())), random_state=0)
        out = run_pipeline(sub, target, embedder=emb, cfg=cfg)
        detected = out[out.status != "unknown"]
        # false positives: rows of KNOWN labels wrongly routed to the unseen label
        known_rows = df[(df.label != held) & (df.item_id.isin(split["test_items"]))]
        kout = run_pipeline(sub, known_rows, embedder=emb, cfg=cfg)
        unseen[held] = {"n": int(len(target)),
                        "top1": float((out.pred == held).mean()),
                        "top1_when_answered": float((detected.pred == held).mean()) if len(detected) else 0.0,
                        "abstained": float((out.status == "unknown").mean()),
                        "false_positive_rate": float((kout.pred == held).mean())}
    metrics["unseen_misconception"] = unseen
    metrics["unseen_misconception_top1"] = float(np.mean([v["top1"] for v in unseen.values()]))
    metrics["unseen_misconception_fpr"] = float(np.mean([v["false_positive_rate"] for v in unseen.values()]))

    # ---------------- 6. hand-written transfer (template-only model) ----------------
    tclf = MisconceptionClassifier.load(MODEL_DIR / "classifier_template.joblib")
    hand = df[df.source == "hand"]
    hres = run_pipeline(tclf, hand, cfg=cfg)
    hans = hres[hres.status != "unknown"]
    metrics["hand_rows_template_only_model"] = {**scores(hans), "abstained": float((hres.status == "unknown").mean())}

    # ---------------- 6b. REAL learner rows (labelled by a teacher in the app, exported via /api/labels/export) ----------------
    real_path = DATA / "real_responses.csv"
    if real_path.exists():
        real = pd.read_csv(real_path)
        real = real[real.item_id.isin(ITEM_INDEX.keys())]
        other = real[real.label == "OTHER"]  # labeller: fits none of the known misconceptions
        real = real[real.label != "OTHER"]
        other_false_alarm = None
        if len(other):  # how often the model invents a known misconception where the labeller saw none
            ores = run_pipeline(served_or(clf), other, cfg=cfg)
            other_false_alarm = float(ores.status.isin(["misconception", "flawed_reasoning"]).mean())
        if len(real):
            rres = run_pipeline(served_or(clf), real, cfg=cfg)
            rans = rres[rres.status != "unknown"]
            metrics["real_rows"] = {**scores(rans), "abstained": float((rres.status == "unknown").mean()),
                                    "total": int(len(real)), "other_excluded": int(len(other)),
                                    "other_false_alarm": other_false_alarm}
    else:
        metrics["real_rows"] = None

    # ---------------- 7. abstention on vague input ----------------
    vres = run_pipeline(clf, vague, cfg=cfg)
    metrics["vague_abstain_rate"] = float((vres.status == "unknown").mean())
    metrics["vague_n"] = int(len(vague))

    # ---------------- 8. latency ----------------
    served = MisconceptionClassifier.load(MODEL_DIR / "classifier.joblib")
    sample = df.sample(200, random_state=1)
    t0 = time.perf_counter()
    for row in sample.itertuples():
        served.predict_one(row.explanation, row.option_text)
    metrics["latency_ms_per_diagnosis"] = float((time.perf_counter() - t0) / len(sample) * 1000)
    metrics["machine"] = f"{platform.machine()} / {platform.python_implementation()} {platform.python_version()}"

    # ---------------- pass/fail ----------------
    metrics["targets_met"] = {
        "macro_f1_heldout_questions": metrics["heldout_questions_only"]["macro_f1"] >= TARGETS["macro_f1_heldout_questions"],
        "confusable_pair_accuracy": (metrics["confusable_pair_accuracy"] or 0) >= TARGETS["confusable_pair_accuracy"],
        "flawed_reasoning_recall": (metrics["flawed_reasoning_recall"] or 0) >= TARGETS["flawed_reasoning_recall"],
        "unseen_misconception_top1": metrics["unseen_misconception_top1"] >= TARGETS["unseen_misconception_top1"],
        "ece": metrics["ece"] <= TARGETS["ece"],
    }

    (REPORTS / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    write_report(metrics)
    print_summary(metrics)


def write_report(m: dict) -> None:
    tick = lambda ok: "✅" if ok else "❌"  # noqa: E731
    lines = [
        "# Re:Learn evaluation report", "",
        f"Dataset: {m['dataset']['rows']} rows, {m['dataset']['items']} items, {m['dataset']['hand_rows']} hand-written. "
        f"Split by item: {len(m['split']['train_items'])} train / {len(m['split']['test_items'])} test items.", "",
        "| Metric | Value | Target | |", "|---|---|---|---|",
        f"| Diagnosis macro-F1 (held-out questions) | {m['heldout_questions_only']['macro_f1']:.3f} | ≥ 0.80 | {tick(m['targets_met']['macro_f1_heldout_questions'])} |",
        f"| Confusable-pair accuracy (n={m['confusable_pair_n']}) | {m['confusable_pair_accuracy']:.3f} | ≥ 0.75 | {tick(m['targets_met']['confusable_pair_accuracy'])} |",
        f"| Flawed-reasoning recall (n={m['flawed_reasoning_n']}) | {m['flawed_reasoning_recall']:.3f} | ≥ 0.70 | {tick(m['targets_met']['flawed_reasoning_recall'])} |",
        f"| Unseen-misconception top-1 (leave-one-out) | {m['unseen_misconception_top1']:.3f} | ≥ 0.60 | {tick(m['targets_met']['unseen_misconception_top1'])} |",
        f"| Calibration ECE | {m['ece']:.3f} | ≤ 0.10 | {tick(m['targets_met']['ece'])} |",
        f"| Latency per diagnosis | {m['latency_ms_per_diagnosis']:.1f} ms | < 1000 ms | ✅ |",
        "",
        "## Secondary",
        f"- Held-out accuracy, all items: {m['heldout_all_items']['accuracy']:.3f} (n={m['heldout_all_items']['n']})",
        f"- Held-out hand-written rows: acc {m['heldout_hand_rows'].get('accuracy', float('nan')):.3f} (n={m['heldout_hand_rows']['n']})",
        f"- Template-only model on ALL hand-written rows: acc {m['hand_rows_template_only_model'].get('accuracy', float('nan')):.3f}, "
        f"macro-F1 {m['hand_rows_template_only_model'].get('macro_f1', float('nan')):.3f}, abstained {m['hand_rows_template_only_model']['abstained']:.0%}",
        f"- Flawed-reasoning false-alarm rate: {m['flawed_reasoning_false_alarm_rate']:.3f}",
        f"- Vague explanations sent to *unknown*: {m['vague_abstain_rate']:.0%} (n={m['vague_n']}); abstain rate on valid rows: {m['abstain_rate_on_valid_rows']:.0%}",
        (f"- **Real learner rows** (teacher-labelled in the app): acc {m['real_rows'].get('accuracy', float('nan')):.3f}, macro-F1 {m['real_rows'].get('macro_f1', float('nan')):.3f}, n={m['real_rows']['total']}, abstained {m['real_rows']['abstained']:.0%}, {m['real_rows'].get('other_excluded', 0)} labelled OTHER (excluded)"
         + (f"; on OTHER rows the model still named a misconception {m['real_rows']['other_false_alarm']:.0%} of the time"
            if m['real_rows'].get('other_false_alarm') is not None else "")
         if m.get("real_rows") else "- Real learner rows: none labelled yet (Teacher tab → Label real responses → Export)"),
        "",
        "## Unseen misconception (leave-one-misconception-out, embedding fallback)",
        "| Held out | n | top-1 | top-1 when answered | abstained | false-positive rate |", "|---|---|---|---|---|---|",
    ]
    for k, v in m["unseen_misconception"].items():
        lines.append(f"| {k} | {v['n']} | {v['top1']:.2f} | {v['top1_when_answered']:.2f} | {v['abstained']:.0%} | {v['false_positive_rate']:.1%} |")
    lines += ["", "## Per-label (held-out)", "| Label | P | R | F1 | n |", "|---|---|---|---|---|"]
    for k, v in m["per_label"].items():
        lines.append(f"| {k} | {v['precision']:.2f} | {v['recall']:.2f} | {v['f1']:.2f} | {v['support']} |")
    lines += ["", "![confusion matrix](confusion_matrix.png)", ""]
    (REPORTS / "report.md").write_text("\n".join(lines), encoding="utf-8")


def print_summary(m: dict) -> None:
    print("\n=== Re:Learn evaluation ===")
    print(f"held-out questions   macro-F1 {m['heldout_questions_only']['macro_f1']:.3f}  acc {m['heldout_questions_only']['accuracy']:.3f}  (n={m['heldout_questions_only']['n']})")
    print(f"confusable pairs     acc {m['confusable_pair_accuracy']:.3f}  (n={m['confusable_pair_n']})")
    print(f"flawed reasoning     recall {m['flawed_reasoning_recall']:.3f}  false-alarm {m['flawed_reasoning_false_alarm_rate']:.3f}")
    print(f"unseen misconception top-1 {m['unseen_misconception_top1']:.3f}  " +
          " ".join(f"{k}={v['top1']:.2f}" for k, v in m['unseen_misconception'].items()))
    print(f"calibration          ECE {m['ece']:.3f}")
    print(f"hand rows (template-only model)  acc {m['hand_rows_template_only_model'].get('accuracy', 0):.3f}")
    print(f"vague -> unknown     {m['vague_abstain_rate']:.0%}   valid abstained {m['abstain_rate_on_valid_rows']:.0%}")
    print(f"latency              {m['latency_ms_per_diagnosis']:.2f} ms / diagnosis")
    print("targets met          " + "  ".join(f"{k}={'✓' if v else '✗'}" for k, v in m["targets_met"].items()))
    print(f"\nReports -> {REPORTS}/metrics.json, report.md, confusion_matrix.png")


if __name__ == "__main__":
    main()
