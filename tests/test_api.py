"""
End-to-end API tests. Run:  python -m pytest -q tests

Covers the PRD's demo milestone (M7): all four statuses, a resolved case, a
not-resolved case, recurrence after a delayed recheck, confusable-pair
differentiation (the A / R / S example from PRD §1), and the privacy NFR.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["RELEARN_DB"] = str(ROOT / "tests" / "_test.db")
os.environ.setdefault("RELEARN_BACKEND", "sklearn")

from fastapi.testclient import TestClient  # noqa: E402

from backend import learner_model  # noqa: E402
from backend.app import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    db = ROOT / "tests" / "_test.db"
    if db.exists():
        db.unlink()
    learner_model._store = None
    with TestClient(app) as c:
        yield c
    if learner_model._store is not None:  # Windows can't delete an open SQLite file
        learner_model._store.conn.close()
        learner_model._store = None
    if db.exists():
        db.unlink()


def diagnose(c, learner, qid, choice, expl, conf="fairly_sure"):
    r = c.post("/api/diagnose", json={"learner": learner, "question_id": qid, "choice": choice,
                                      "explanation": expl, "confidence": conf})
    assert r.status_code == 200, r.text
    return r.json()


def reassess(c, learner, m, probe_id, choice, expl, phase="probe"):
    r = c.post("/api/reassess", json={"learner": learner, "misconception": m, "probe_id": probe_id,
                                      "choice": choice, "explanation": expl, "phase": phase})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- basics

def test_health_and_questions(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["questions"] == 30 and h["misconceptions"] == 5
    q = client.get("/api/questions").json()
    assert len(q["questions"]) == 30


def test_answer_keys_never_sent_to_browser(client):
    """Privacy NFR: no answer keys or misconception maps in any public payload."""
    q = client.get("/api/questions").json()["questions"][0]
    assert "answer" not in q
    assert all("misconceptions" not in o for o in q["options"])
    s = client.post("/api/session/start", json={"learner": "priv", "mode": "quick"}).json()
    assert all("answer" not in item for item in s["questions"])


# ---------------------------------------------------------------- PRD §1: A / R / S

def test_same_wrong_answer_different_misconceptions(client):
    a = diagnose(client, "A", "Q01", "A", "It stops at the top, so velocity is zero.")
    r = diagnose(client, "R", "Q01", "A", "The force of the throw has run out.")
    assert a["status"] == "misconception" and a["label"] == "VA_CONFUSION"
    assert r["status"] == "misconception" and r["label"] == "IMPETUS"


def test_flawed_reasoning_behind_correct_answer(client):
    s = diagnose(client, "S", "Q01", "B", "It is still slowing down because of the throw force.")
    assert s["correct"] is True
    assert s["status"] == "flawed_reasoning" and s["label"] == "IMPETUS"
    assert "intervention" in s and s["probe"]["target"] == "IMPETUS"


def test_correct_with_sound_reasoning(client):
    r = diagnose(client, "C", "Q21", "B", "Newton's third law: equal and opposite forces, the car just accelerates more.")
    assert r["status"] == "correct" and r["label"] == "NONE"


def test_unknown_when_explanation_is_vague(client):
    r = diagnose(client, "U", "Q27", "A", "idk")
    assert r["status"] == "unknown" and "ask" in r
    r2 = diagnose(client, "U", "Q27", "A", "the bowling ball is heavier so gravity pulls it harder and it falls faster")
    assert r2["status"] == "misconception" and r2["label"] == "HEAVIER_FASTER"


def test_confidence_always_present_and_bounded(client):
    r = diagnose(client, "K", "Q14", "A", "same push same speed, constant force means constant velocity")
    assert 0.0 <= r["confidence"] <= 1.0 and r["label"] == "FORCE_VELOCITY"
    assert r["latency_ms"] < 1000


# ---------------------------------------------------------------- resolution (FR-6 / FR-7)

def test_resolution_requires_two_clean_probes_then_recheck(client):
    L = "Resolver"
    d = diagnose(client, L, "Q01", "A", "It stops at the top, so velocity is zero.", conf="certain")
    assert d["state"] == "active" and d["confidently_held"] is True
    p1 = d["probe"]
    r1 = reassess(client, L, "VA_CONFUSION", p1["id"], "B",
                  "velocity is zero for an instant but gravity still acts so the acceleration is not zero")
    assert r1["resolved"] is True and r1["state"] == "improving" and r1["probe"] is not None
    p2 = r1["probe"]
    assert p2["id"] != p1["id"], "second probe must be a different context"
    r2 = reassess(client, L, "VA_CONFUSION", p2["id"], "B",
                  "net force is not zero at the lowest point so there is a large acceleration even though v = 0")
    assert r2["resolved"] is True and r2["state"] == "resolved" and r2["resolved_now"] is True
    # Delayed recheck not due immediately
    assert client.get(f"/api/recheck/{L}").json()["probe"] is None
    # ...but due after RECHECK_GAP more attempts
    diagnose(client, L, "Q21", "B", "equal and opposite forces, third law")
    diagnose(client, L, "Q27", "B", "same acceleration g for both, mass cancels")
    rc = client.get(f"/api/recheck/{L}").json()
    assert rc["probe"] is not None and rc["probe"]["phase"] == "recheck"
    r3 = reassess(client, L, "VA_CONFUSION", rc["probe"]["id"], "A", "it is not moving so there is no acceleration", phase="recheck")
    assert r3["resolved"] is False and r3["state"] == "recurring"
    prof = client.get(f"/api/profile/{L}").json()
    m = next(x for x in prof["misconceptions"] if x["id"] == "VA_CONFUSION")
    assert m["state"] == "recurring" and m["detected"] == 2


def test_correct_answer_with_misconception_still_present_is_not_resolved(client):
    L = "Sticky"
    d = diagnose(client, L, "Q21", "A", "the truck is bigger so it pushes harder on the car")
    assert d["label"] == "THIRD_LAW"
    r = reassess(client, L, "THIRD_LAW", d["probe"]["id"], "B",
                 "equal I guess, although the truck still pushes harder because it is heavier")
    assert r["correct"] is True and r["resolved"] is False and r["target_present"] is True
    assert r["probe"] is not None  # offered another context


def test_inconclusive_probe_asks_for_reasoning(client):
    L = "Quiet"
    d = diagnose(client, L, "Q27", "A", "heavy things fall faster, the bowling ball is heavier")
    r = reassess(client, L, "HEAVIER_FASTER", d["probe"]["id"], "B", "yes")
    assert r["resolved"] is None and "ask" in r


# ---------------------------------------------------------------- report / class / feedback / metrics

def test_report_and_class_view(client):
    rep = client.get("/api/report/Resolver").json()
    assert rep["summary"]["answered"] == 3 and rep["summary"]["recurring"] == 1
    cls = client.get("/api/class").json()
    assert cls["learners"] >= 5 and "VA_CONFUSION" in cls["misconceptions"]


def test_feedback_is_stored(client):
    d = diagnose(client, "F", "Q07", "B", "the flick's force is still in the coin pushing it up")
    r = client.post("/api/feedback", json={"learner": "F", "attempt_id": d["attempt_id"], "suggested_label": "NONE", "note": ""})
    assert r.status_code == 200
    rows = client.get("/api/feedback/export").json()["rows"]
    assert any(x["suggested_label"] == "NONE" and x["model_label"] == "IMPETUS" for x in rows)


def test_metrics_endpoint(client):
    m = client.get("/api/metrics").json()
    if m.get("available"):
        assert m["heldout_questions_only"]["macro_f1"] > 0.5
        assert "confusion_matrix" in m
