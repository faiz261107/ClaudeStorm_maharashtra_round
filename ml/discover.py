"""
Misconception discovery.

The abstain rule sends explanations the model cannot place to `unknown`. If several
learners produce *similar* unplaceable explanations, that is a candidate misconception the
taxonomy does not yet have. This module clusters those explanations and describes each
cluster so a teacher can name it (and then add it to backend/data.py — the embedding
fallback makes it work immediately, before any retraining).

Usage (standalone):  python ml/discover.py        # reads the SQLite store
Used by the API:     GET /api/discover
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from sklearn.cluster import KMeans  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402

from backend.data import MISCONCEPTIONS  # noqa: E402
from ml.model import DescriptionEmbedder, normalise  # noqa: E402

MIN_ROWS = 4


def discover_clusters(rows: list[dict], k: int = 3) -> dict:
    texts = [normalise(r["explanation"]) for r in rows]
    if len(texts) < MIN_ROWS:
        return {"clusters": [], "n": len(texts),
                "message": f"Need at least {MIN_ROWS} abstained explanations to look for patterns (have {len(texts)})."}
    k = max(1, min(k, len(texts) // 2))
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True, stop_words="english")
    X = vec.fit_transform(texts)
    km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(X)
    terms = np.array(vec.get_feature_names_out())
    descriptions = {m: v["description"] + " " + v["believes"] for m, v in MISCONCEPTIONS.items()}
    emb = DescriptionEmbedder().fit(descriptions, corpus=texts)

    clusters = []
    for c in range(k):
        idx = np.where(km.labels_ == c)[0]
        if len(idx) == 0:
            continue
        centre = km.cluster_centers_[c]
        top_terms = terms[np.argsort(centre)[::-1][:6]].tolist()
        # distance to centre -> most representative examples first
        d = np.asarray(X[idx].toarray() @ centre).ravel()
        order = idx[np.argsort(-d)]
        examples = [{"explanation": rows[i]["explanation"], "item_id": rows[i]["item_id"], "learner": rows[i]["learner"]}
                    for i in order[:5]]
        # how close is this cluster to an existing misconception description?
        joined = " ".join(texts[i] for i in idx)
        sims = emb.similarities(joined)
        nearest, sim = max(sims.items(), key=lambda kv: kv[1])
        clusters.append({
            "id": c, "size": int(len(idx)), "top_terms": top_terms, "examples": examples,
            "nearest_known": {"id": nearest, "name": MISCONCEPTIONS[nearest]["name"], "similarity": round(float(sim), 3)},
            "verdict": ("looks like a phrasing of a known idea — consider adding these phrasings to its description"
                        if sim >= 0.25 else "does not match any known misconception — candidate for a new entry"),
        })
    clusters.sort(key=lambda c: -c["size"])
    return {"clusters": clusters, "n": len(texts),
            "message": f"{len(texts)} abstained explanations grouped into {len(clusters)} pattern(s)."}


if __name__ == "__main__":
    from backend.learner_model import get_store
    import json
    print(json.dumps(discover_clusters(get_store().unknown_explanations()), indent=2))
