"""
Model layer shared by the trainer, the evaluator and the API.

Two components:

  MisconceptionClassifier
      Text -> misconception label + calibrated probabilities.
      Default backend: TF-IDF (word + char n-grams) + logistic regression.
      Trains in seconds on a laptop CPU, predicts in < 5 ms (latency NFR).
      Optional backend: fine-tuned DeBERTa-v3 (see train_deberta.py); loaded
      automatically if ml/models/deberta/ exists and `transformers` is installed.

  DescriptionEmbedder  (FR-10)
      Scores an explanation against every misconception *description* so a new
      misconception can be added by writing a description – no retraining.
      Default backend: TF-IDF cosine similarity.  Optional: sentence-transformers
      (`pip install sentence-transformers`, set RELEARN_EMBEDDER=st).

Input format (PRD §8): "Q: {question} | Answer: {option text} | Explanation: {reasoning}"
The classifier is trained mainly on the explanation; the option text is a weak
side-feature; the question text is deliberately *not* used so the model cannot
learn question-specific shortcuts (we split by question).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

ML_DIR = Path(__file__).resolve().parent
MODEL_DIR = ML_DIR / "models"
DEFAULT_MODEL_PATH = MODEL_DIR / "classifier.joblib"
DEBERTA_DIR = MODEL_DIR / "deberta"


def normalise(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"[^a-z0-9°²=/+\-.,'?! ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def make_frame(explanations, option_texts) -> pd.DataFrame:
    return pd.DataFrame({
        "explanation": [normalise(e) for e in explanations],
        "option_text": [normalise(o) for o in option_texts],
    })


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class MisconceptionClassifier:
    def __init__(self, C: float = 6.0):
        self.C = C
        self.pipeline: Pipeline | None = None
        self.classes_: list[str] = []

    @staticmethod
    def _build(C: float) -> Pipeline:
        explanation_features = FeatureUnion([
            ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)),
        ])
        features = ColumnTransformer([
            ("expl", explanation_features, "explanation"),
            ("opt", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True), "option_text"),
        ], transformer_weights={"expl": 1.0, "opt": 0.35})
        clf = LogisticRegression(C=C, max_iter=3000, class_weight="balanced")
        return Pipeline([("features", features), ("clf", clf)])

    def fit(self, explanations, option_texts, labels) -> "MisconceptionClassifier":
        self.pipeline = self._build(self.C)
        self.pipeline.fit(make_frame(explanations, option_texts), list(labels))
        self.classes_ = list(self.pipeline.named_steps["clf"].classes_)
        return self

    def predict_proba(self, explanations, option_texts) -> np.ndarray:
        assert self.pipeline is not None, "classifier not trained/loaded"
        return self.pipeline.predict_proba(make_frame(explanations, option_texts))

    def predict_one(self, explanation: str, option_text: str) -> dict[str, float]:
        probs = self.predict_proba([explanation], [option_text])[0]
        return dict(zip(self.classes_, map(float, probs)))

    def save(self, path: Path = DEFAULT_MODEL_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"pipeline": self.pipeline, "classes": self.classes_, "C": self.C}, path)

    @classmethod
    def load(cls, path: Path = DEFAULT_MODEL_PATH) -> "MisconceptionClassifier":
        blob = joblib.load(path)
        obj = cls(C=blob.get("C", 6.0))
        obj.pipeline = blob["pipeline"]
        obj.classes_ = blob["classes"]
        return obj


class DebertaClassifier:
    """Optional transformer backend (PRD §8). Same interface as MisconceptionClassifier."""

    def __init__(self, model_dir: Path = DEBERTA_DIR):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore
        import torch  # type: ignore

        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(str(model_dir))
        self.model = AutoModelForSequenceClassification.from_pretrained(str(model_dir)).eval()
        self.classes_ = [self.model.config.id2label[i] for i in range(self.model.config.num_labels)]

    def predict_proba(self, explanations, option_texts) -> np.ndarray:
        texts = [f"Answer: {o} | Explanation: {e}" for e, o in zip(explanations, option_texts)]
        with self.torch.no_grad():
            enc = self.tok(texts, padding=True, truncation=True, max_length=128, return_tensors="pt")
            logits = self.model(**enc).logits
            return self.torch.softmax(logits, dim=-1).cpu().numpy()

    def predict_one(self, explanation: str, option_text: str) -> dict[str, float]:
        probs = self.predict_proba([explanation], [option_text])[0]
        return dict(zip(self.classes_, map(float, probs)))


def load_best_classifier():
    """DeBERTa if trained + installed, else the sklearn model. Returns (model, backend_name)."""
    if DEBERTA_DIR.exists() and os.environ.get("RELEARN_BACKEND", "auto") != "sklearn":
        try:
            return DebertaClassifier(), "deberta-v3"
        except Exception:  # transformers not installed, or model incomplete
            pass
    return MisconceptionClassifier.load(), "tfidf-logreg"


# ---------------------------------------------------------------------------
# Description embedder (unseen-misconception fallback, FR-10)
# ---------------------------------------------------------------------------

class DescriptionEmbedder:
    def __init__(self, backend: str | None = None):
        self.backend = backend or os.environ.get("RELEARN_EMBEDDER", "tfidf")
        self.labels: list[str] = []
        self.vectorizer = None
        self.desc_matrix = None
        self.st_model = None
        if self.backend == "st":
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
                self.st_model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception:
                self.backend = "tfidf"

    def fit(self, descriptions: dict[str, str], corpus: list[str] | None = None) -> "DescriptionEmbedder":
        self.labels = list(descriptions.keys())
        texts = [normalise(descriptions[k]) for k in self.labels]
        if self.backend == "st" and self.st_model is not None:
            self.desc_matrix = self.st_model.encode(texts, normalize_embeddings=True)
        else:
            self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
            fit_corpus = texts + [normalise(c) for c in (corpus or [])]
            self.vectorizer.fit(fit_corpus)
            self.desc_matrix = self.vectorizer.transform(texts)
        return self

    def similarities(self, explanation: str) -> dict[str, float]:
        text = normalise(explanation)
        if self.backend == "st" and self.st_model is not None:
            v = self.st_model.encode([text], normalize_embeddings=True)
            sims = (self.desc_matrix @ v.T).ravel()
        else:
            v = self.vectorizer.transform([text])
            sims = (self.desc_matrix @ v.T).toarray().ravel()
        return {lab: float(s) for lab, s in zip(self.labels, sims)}

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"backend": self.backend, "labels": self.labels, "vectorizer": self.vectorizer,
                     "desc_matrix": self.desc_matrix if self.backend != "st" else None}, path)

    @classmethod
    def load(cls, path: Path, descriptions: dict[str, str] | None = None) -> "DescriptionEmbedder":
        blob = joblib.load(path)
        obj = cls(backend=blob["backend"])
        if obj.backend == "st" and descriptions:
            return obj.fit(descriptions)
        obj.labels, obj.vectorizer, obj.desc_matrix = blob["labels"], blob["vectorizer"], blob["desc_matrix"]
        return obj
