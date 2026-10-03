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
for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
    os.environ.pop(_k, None)  # tests never call a real LLM

from fastapi.testclient import TestClient  # noqa: E402

from backend import learner_model  # noqa: E402
from backend.app import TEACHER_PIN, app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    db = ROOT / "tests" / "_test.db"
    if db.exists():
        db.unlink()
    learner_model._store = None
    with TestClient(app) as c:
        token = c.post("/api/teacher/login", json={"pin": TEACHER_PIN}).json()["token"]
        c.headers.update({"X-Teacher-Token": token})  # teacher endpoints are PIN-protected
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


# ---------------------------------------------------------------- v2 features

def test_working_mode_diagnoses_from_the_working(client):
    r = diagnose_w(client, "Wk", "W03", 10000, "40000 / 4 = 10000 because the car is a quarter of the mass")
    assert r["status"] == "misconception" and r["label"] == "THIRD_LAW" and r["source"] == "working-rules"
    assert r["rule"]["why"] and r["worked"] and r["answer_shown"].startswith("40000")
    r2 = diagnose_w(client, "Wk", "W01", 12, "a = 6/2 = 3, v = 3 x 4 = 12")
    assert r2["status"] == "correct"
    r3 = diagnose_w(client, "Wk", "W02", 98, "a = m x g = 10 x 9.8 = 98")
    assert r3["status"] == "misconception" and r3["label"] == "HEAVIER_FASTER"


def diagnose_w(c, learner, qid, value, working):
    r = c.post("/api/diagnose", json={"learner": learner, "question_id": qid, "numeric_value": value, "explanation": working})
    assert r.status_code == 200, r.text
    return r.json()


def test_diagram_mode_and_sentence_tiebreak(client):
    gravity_normal = [{"force": "gravity", "direction": "down", "size": 2}, {"force": "normal force", "direction": "up", "size": 2}]
    r = client.post("/api/diagnose", json={"learner": "Dr", "question_id": "F02", "diagram": gravity_normal + [{"force": "forward push", "direction": "right", "size": 2}],
                                            "explanation": "it needs a push to keep going at the same speed"}).json()
    assert r["status"] == "misconception" and r["label"] == "FORCE_VELOCITY" and r["source"] == "diagram+text"
    assert r["diagram_feedback"]["extra"] == ["forward push"] and r["ideal_diagram"]
    ok = client.post("/api/diagnose", json={"learner": "Dr", "question_id": "F02", "diagram": gravity_normal, "explanation": ""}).json()
    assert ok["status"] == "correct"
    empty = client.post("/api/diagnose", json={"learner": "Dr", "question_id": "F04", "diagram": [], "explanation": ""}).json()
    assert empty["status"] == "misconception" and empty["label"] == "VA_CONFUSION"


def test_personalised_fix_quotes_the_learner(client):
    r = diagnose(client, "Pz", "Q01", "A", "The force of the throw has run out so it stops")
    p = r["personalised"]
    assert p["quote"].startswith("The force of the throw") and p["trigger"] == "force of the throw" and "applying that force" in p["bridge"]
    assert p["source"] in ("rules", "llm")


def test_struggle_signal_blocks_confidently_held(client):
    r = client.post("/api/diagnose", json={"learner": "Hz", "question_id": "Q21", "choice": "A", "explanation": "the truck is bigger so it pushes harder",
                                            "confidence": "certain", "time_ms": 120000, "edits": 9}).json()
    assert r["hesitant"] is True and r["confidently_held"] is False


def test_cross_session_recheck(client):
    L = "Cross"
    s1 = client.post("/api/session/start", json={"learner": L}).json()
    assert s1["welcome"] is None
    d = client.post("/api/diagnose", json={"learner": L, "session_id": s1["session_id"], "question_id": "Q07", "choice": "B",
                                            "explanation": "the flick's force is still in the coin pushing it up"}).json()
    assert d["label"] == "IMPETUS"
    p1 = reassess(client, L, "IMPETUS", d["probe"]["id"], "B", "no horizontal force, nothing is pushing it, inertia keeps it moving")
    r = client.post("/api/reassess", json={"learner": L, "session_id": s1["session_id"], "misconception": "IMPETUS", "probe_id": p1["probe"]["id"],
                                            "choice": "B", "explanation": "no force opposes it so it keeps its speed, the launch force ended long ago"}).json()
    assert r["state"] == "resolved"
    client.post("/api/session/finish", json={"session_id": s1["session_id"]})
    s2 = client.post("/api/session/start", json={"learner": L}).json()
    assert s2["welcome"]["returning"] and [m["id"] for m in s2["welcome"]["to_verify"]] == ["IMPETUS"]
    rc = client.get(f"/api/recheck/{L}?session_id={s2['session_id']}").json()
    assert rc["probe"] and rc["cross_session"] is True
    y = client.post("/api/reassess", json={"learner": L, "session_id": s2["session_id"], "misconception": "IMPETUS", "probe_id": rc["probe"]["id"],
                                            "choice": "A", "explanation": "gravity only, the kick force is gone the moment it leaves the foot", "phase": "recheck"}).json()
    assert y["resolved"] is True and y["held_across_sessions"] is True
    assert client.get(f"/api/recheck/{L}?session_id={s2['session_id']}").json()["probe"] is None
    assert client.get(f"/api/report/{L}").json()["summary"]["held_across_sessions"] == 1


def test_labelling_pipeline_and_pdf(client):
    pend = client.get("/api/labels/pending").json()
    assert pend["rows"] and "NONE" in pend["labels"]
    r = client.post("/api/labels", json={"attempt_id": pend["rows"][0]["id"], "label": "IMPETUS"}).json()
    assert r["ok"]
    real = ROOT / "ml" / "data" / "real_responses.csv"
    saved = real.read_bytes() if real.exists() else None  # never clobber real exported labels
    try:
        e = client.post("/api/labels/export").json()
        assert e["rows"] >= 1 and e["path"].endswith("real_responses.csv")
    finally:
        real.write_bytes(saved) if saved is not None else real.unlink(missing_ok=True)
    pdf = client.get("/api/report/Cross/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content[:4] == b"%PDF"


def test_discovery_clusters_abstained_explanations(client):
    vague = ["the spin energy holds it there for a bit", "spinning energy keeps it hanging", "its rotation energy makes it float",
             "spin makes it hover a moment", "momentum zero at top so nothing happens", "no momentum means nothing acts on it"]
    for i, e in enumerate(vague):
        client.post("/api/diagnose", json={"learner": f"V{i}", "question_id": "Q02", "choice": "D", "explanation": e})
    d = client.get("/api/discover").json()
    assert "clusters" in d and d["n"] >= 0


def test_upload_image(client):
    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (30, 30), "white").save(buf, "PNG")
    r = client.post("/api/upload", files={"file": ("w.png", buf.getvalue(), "image/png")}).json()
    assert r["image_id"].endswith(".png") and client.get(r["url"]).status_code == 200
    (ROOT / "backend" / "uploads" / r["image_id"]).unlink(missing_ok=True)


def test_upload_rejects_non_images(client):
    for name, data in [("notes.png", b"definitely not an image"), ("empty.png", b"")]:
        r = client.post("/api/upload", files={"file": (name, data, "image/png")})
        assert r.status_code == 400, name


def test_working_rejects_non_finite_number(client):
    r = client.post("/api/diagnose", content=b'{"learner":"Nan","question_id":"W01","numeric_value":NaN,"explanation":"a = f/m"}',
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 400


# ---------------------------------------------------------------- tutor response (NLP reply to the explanation)

def test_tutor_response_on_every_status(client):
    r = diagnose(client, "Tt", "Q01", "B", "It is still slowing down because of the throw force, definitely")
    t = r["tutor"]
    assert r["status"] == "flawed_reasoning" and t["source"] in ("rules", "llm")
    assert "throw force" in t["text"] and "Tt" in t["text"] and "force" in t["signals"]["concepts"]
    c = diagnose(client, "Tt", "Q21", "B", "third law, equal and opposite, the car just accelerates more")
    assert c["status"] == "correct" and c["tutor"]["text"] and "third_law" in c["tutor"]["signals"]["concepts"]
    u = diagnose(client, "Tt", "Q27", "A", "idk")
    assert u["status"] == "unknown" and "why" in u["tutor"]["text"].lower()
    p = r["probe"]
    pr = reassess(client, "Tt", "IMPETUS", p["id"], "B", "nothing pushes it after release, only gravity acts, inertia keeps it moving")
    assert pr["resolved"] is True and pr["tutor"]["text"]


# ---------------------------------------------------------------- voice explanation NLP + Ask the tutor

def test_nlp_analyse_live_readout(client):
    r = client.post("/api/nlp/analyse", json={"text": "it stops so the velocity is zero"}).json()
    assert "velocity" in r["concepts"] and r["has_reason"] is True and r["ready"] is True
    short = client.post("/api/nlp/analyse", json={"text": "it stops"}).json()
    assert short["ready"] is False and short["nudge"]


def test_ask_the_tutor(client):
    q = client.post("/api/ask", json={"text": "what is acceleration?", "item_id": "Q01"}).json()
    assert q["intent"] == "question" and "velocity" in q["reply"].lower()
    a = client.post("/api/ask", json={"text": "A because it stops", "item_id": "Q01"}).json()
    assert a["intent"] == "redirect"
    assert client.post("/api/ask", json={"text": "hi"}).json()["intent"] == "greeting"


# ---------------------------------------------------------------- teacher PIN

def test_teacher_endpoints_need_pin(client):
    anon = TestClient(app)
    for path in ["/api/class", "/api/labels/pending", "/api/discover", "/api/activity", "/api/feedback/export"]:
        assert anon.get(path).status_code == 401, path
    assert anon.post("/api/labels", json={"attempt_id": 1, "label": "IMPETUS"}).status_code == 401
    assert anon.post("/api/teacher/login", json={"pin": "wrong"}).status_code == 401
    assert anon.get("/api/questions").status_code == 200  # learner side stays open
    tok = anon.post("/api/teacher/login", json={"pin": TEACHER_PIN}).json()["token"]
    assert anon.get("/api/activity", headers={"X-Teacher-Token": tok}).status_code == 200
    assert anon.post("/api/teacher/logout", headers={"X-Teacher-Token": tok}).status_code == 200
    assert anon.get("/api/activity", headers={"X-Teacher-Token": tok}).status_code == 401


def test_live_activity_feed(client):
    diagnose(client, "Feed", "Q01", "A", "It stops at the top, so velocity is zero.")
    rows = client.get("/api/activity").json()["rows"]
    assert rows[0]["learner"] == "Feed" and rows[0]["name"] == "Velocity–acceleration confusion"


def test_tutor_answers_capability_questions(client):
    r = client.post("/api/ask", json={"text": "what all can u explain"}).json()
    assert r["intent"] == "capabilities" and "Newton" in r["reply"]


# ---------------------------------------------------------------- AI tutor (LLM), faked: tests never hit the network

def test_ask_uses_llm_with_history_and_falls_back(client, monkeypatch):
    from backend import llm
    seen = {}

    def fake_generate(prompt, max_tokens=400, system=None, history=None):
        seen.update(prompt=prompt, system=system, history=history)
        return "**Inertia** is resistance to a change in motion."

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm, "generate", fake_generate)
    hist = [{"role": "user", "content": "what is a force?"}, {"role": "assistant", "content": "A push or a pull."}]
    r = client.post("/api/ask", json={"text": "and what is inertia?", "item_id": "Q01", "history": hist}).json()
    assert r["generated"] and r["reply"] == "Inertia is resistance to a change in motion."  # markdown stripped
    assert seen["history"] == hist and "do not answer it" in seen["prompt"] and "NEVER say which option" in seen["system"]

    monkeypatch.setattr(llm, "generate", lambda *a, **k: None)  # LLM down -> offline knowledge base
    r = client.post("/api/ask", json={"text": "what is inertia?"}).json()
    assert not r["generated"] and "inertia" in r["reply"].lower()


def test_no_key_means_offline_tutor(client):
    r = client.post("/api/ask", json={"text": "what is inertia?"}).json()
    assert r["generated"] is False
