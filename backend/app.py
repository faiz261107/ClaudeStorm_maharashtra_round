"""
Re:Learn API (FastAPI).

    GET  /                          single-page app
    GET  /api/health                model backend + config
    GET  /api/questions             question list WITHOUT answer keys
    GET  /api/misconceptions        taxonomy (names, beliefs, physics)
    POST /api/session/start         {learner, mode} -> session + question order + profile
    POST /api/diagnose              {learner, question_id, choice, explanation, confidence}
                                    -> status, misconception, intervention, transfer probe
    POST /api/reassess              {learner, misconception, probe_id, choice, explanation, confidence, phase}
                                    -> resolved true/false (null = inconclusive), next probe
    GET  /api/recheck/{learner}     delayed recheck probe if one is due (FR-7)
    GET  /api/profile/{learner}     learner model (FR-8)
    GET  /api/report/{learner}      session report (FR-13)
    POST /api/session/finish        {session_id}
    POST /api/feedback              "that's not what I meant" (PRD §15) -> stored as training data
    GET  /api/class                 teacher class view (FR-14)
    GET  /api/metrics               evaluation results from ml/reports/metrics.json (FR-11)
    DELETE /api/learner/{learner}   reset a learner (demo convenience)

Run:  python run.py     (or)   uvicorn backend.app:app --reload
"""

from __future__ import annotations

import json
import hmac
import math
import secrets
import time
import os
import random
import sys
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.data import (  # noqa: E402
    FBD_QUESTIONS, INTERVENTIONS, ITEM_INDEX, MISCONCEPTIONS, NONE_LABEL, PROBES, QUESTIONS,
    WORKING_QUESTIONS, public_item,
)
from backend.diagnosis import get_diagnoser  # noqa: E402
from backend.learner_model import MAX_PROBES, PROBES_REQUIRED, RECHECK_GAP, get_store  # noqa: E402
from backend.personalise import personalise  # noqa: E402
from backend.tutor_response import compose as compose_tutor, analyse as analyse_explanation  # noqa: E402
from backend import llm  # noqa: E402
from backend.chat_nlp import llm_chat, understand  # noqa: E402

FRONTEND = ROOT / "frontend"
REPORTS = ROOT / "ml" / "reports"

app = FastAPI(title="Re:Learn API", version="1.0.0",
              description="Adaptive multimodal learning environment – misconception diagnosis for intro mechanics.")
app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")

# A curated 8-question demo set that exercises every misconception and both confusable pairs.
QUICK_SET = ["Q01", "Q21", "Q27", "F02", "Q14", "W03", "Q07", "Q23", "Q05"]   # includes a diagram item and a working item
UPLOADS = ROOT / "backend" / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS)), name="uploads")
TOPICS = {q["topic"] for q in QUESTIONS}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class StartSession(BaseModel):
    learner: str = Field(min_length=1, max_length=60)
    mode: Literal["quick", "full", "topic", "working", "diagram"] = "quick"
    topic: Optional[str] = None


class DiagnoseIn(BaseModel):
    learner: str = Field(min_length=1, max_length=60)
    question_id: str
    choice: str = ""
    explanation: str = ""
    confidence: Literal["guessing", "fairly_sure", "certain"] = "fairly_sure"
    session_id: Optional[int] = None
    numeric_value: Optional[float] = None     # working mode
    diagram: Optional[list[dict]] = None      # free-body-diagram mode
    image_id: Optional[str] = None            # uploaded photo of handwritten working
    input_method: Optional[str] = None        # typed | voice | photo
    time_ms: Optional[int] = None             # struggle signal: time from question shown to submit
    edits: Optional[int] = None               # struggle signal: option changes + explanation rewrites


class ReassessIn(BaseModel):
    learner: str = Field(min_length=1, max_length=60)
    misconception: str
    probe_id: str
    choice: str
    explanation: str = ""
    confidence: Literal["guessing", "fairly_sure", "certain"] = "fairly_sure"
    phase: Literal["probe", "recheck"] = "probe"
    session_id: Optional[int] = None
    time_ms: Optional[int] = None
    edits: Optional[int] = None


class AnalyseIn(BaseModel):
    text: str
    item_id: Optional[str] = None


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class AskIn(BaseModel):
    text: str = Field(max_length=1000)
    item_id: Optional[str] = None
    history: list[ChatTurn] = Field(default_factory=list)  # earlier turns of the tutor chat, oldest first


class LabelIn(BaseModel):
    attempt_id: int
    label: str
    labelled_by: str = "teacher"


class TeacherLogin(BaseModel):
    pin: str = Field(min_length=1, max_length=40)


class FinishSession(BaseModel):
    session_id: int


class FeedbackIn(BaseModel):
    learner: str
    attempt_id: int
    suggested_label: str
    note: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def misconception_card(m: str, confidence: float) -> dict:
    meta = MISCONCEPTIONS[m]
    return {"id": m, "name": meta["name"], "short": meta["short"], "believes": meta["believes"],
            "physics": meta["physics"], "colour": meta["colour"], "confidence": round(confidence, 3)}


def pick_probe(learner: str, m: str, exclude: list[str] | None = None) -> dict | None:
    store = get_store()
    used = store.probes_used(learner, m)
    pool = [p for p in PROBES[m] if p["id"] not in used and p["id"] not in (exclude or [])]
    if not pool:
        pool = [p for p in PROBES[m] if p["id"] not in (exclude or [])] or PROBES[m]
    return pool[0]


def next_probe_payload(learner: str, m: str, phase: str = "probe") -> dict | None:
    p = pick_probe(learner, m)
    if p is None:
        return None
    get_store().mark_probe_used(learner, m, p["id"])
    return {**public_item(p), "target": m, "phase": phase,
            "probes_required": PROBES_REQUIRED}


def wants_more_detail(status: str) -> bool:
    return status == "unknown"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/health")
def health():
    d = get_diagnoser()
    return {"ok": True, "model": d.info(), "llm": {"provider": llm.available(), "model": llm.model_name()},
            "probes_required": PROBES_REQUIRED, "recheck_gap": RECHECK_GAP,
            "questions": len(QUESTIONS), "misconceptions": len(MISCONCEPTIONS)}


@app.get("/api/questions")
def questions():
    return {"questions": [public_item(q) for q in QUESTIONS]}


@app.get("/api/misconceptions")
def misconceptions():
    return {m: {"id": m, "name": v["name"], "short": v["short"], "believes": v["believes"],
                "physics": v["physics"], "colour": v["colour"], "confusable_with": v["confusable_with"]}
            for m, v in MISCONCEPTIONS.items()}


@app.post("/api/session/start")
def start_session(body: StartSession):
    learner = body.learner.strip()
    store = get_store()
    if body.mode == "quick":
        order = list(QUICK_SET)
    elif body.mode == "working":
        order = [w["id"] for w in WORKING_QUESTIONS]
    elif body.mode == "diagram":
        order = [f["id"] for f in FBD_QUESTIONS]
    elif body.mode == "topic":
        if body.topic not in TOPICS:
            raise HTTPException(400, f"unknown topic; choose one of {sorted(TOPICS)}")
        order = [q["id"] for q in QUESTIONS if q["topic"] == body.topic] + [w["id"] for w in WORKING_QUESTIONS if w["topic"] == body.topic]
    else:
        order = [q["id"] for q in QUESTIONS]
        random.Random(hash(learner) & 0xFFFF).shuffle(order)
        order += [w["id"] for w in WORKING_QUESTIONS] + [f["id"] for f in FBD_QUESTIONS]
    previous = store.last_session(learner)
    sid = store.start_session(learner, order)
    profile = store.profile(learner)
    carried = [m for m in profile["misconceptions"] if m["state"] in ("active", "recurring", "improving")]
    to_verify = store.recheck_candidates(learner, session_id=sid)
    welcome = None
    if previous:
        welcome = {
            "returning": True,
            "sessions_before": store.session_count(learner) - 1,
            "last_session": previous,
            "open_ideas": [{"id": m["id"], "name": MISCONCEPTIONS[m["id"]]["name"], "state": m["state"]} for m in carried],
            "to_verify": [{"id": m, "name": MISCONCEPTIONS[m]["name"]} for m in to_verify],
            "message": ("Welcome back. " + (f"Last time you resolved {len(to_verify)} idea{'s' if len(to_verify) != 1 else ''} — "
                        "let's check they're still fixed before anything new." if to_verify else
                        "Picking up where you left off.")),
        }
    return {"session_id": sid, "learner": learner, "question_order": order,
            "questions": [public_item(ITEM_INDEX[i]) for i in order],
            "profile": profile, "welcome": welcome}


@app.post("/api/diagnose")
def diagnose(body: DiagnoseIn):
    item = ITEM_INDEX.get(body.question_id)
    if item is None:
        raise HTTPException(404, "unknown question")
    diag = get_diagnoser()
    store = get_store()
    working_mode = item.get("kind") == "working"
    fbd_mode = item.get("kind") == "fbd"
    if body.numeric_value is not None and not math.isfinite(body.numeric_value):
        raise HTTPException(400, "your answer must be an ordinary number")
    matched_rule = None
    fbd_feedback = None
    try:
        if fbd_mode:
            d, latency, fbd_feedback = diag.diagnose_fbd(item, body.diagram or [], body.explanation)
            correct = d.status == "correct"
            choice = ",".join(f"{a.get('force')}:{a.get('direction')}:{a.get('size', 2)}" for a in (body.diagram or []))
        elif working_mode:
            d, latency, matched_rule = diag.diagnose_working(item, body.numeric_value, body.explanation)
            correct = body.numeric_value is not None and diag.working_is_correct(item, body.numeric_value)
            choice = "" if body.numeric_value is None else str(body.numeric_value)
        else:
            d, latency = diag.diagnose(item, body.choice, body.explanation)
            correct = diag.is_correct(item, body.choice)
            choice = body.choice
    except ValueError as e:
        raise HTTPException(400, str(e))
    label = d.label if d.label in MISCONCEPTIONS else d.label

    attempt_id = store.record_attempt(
        learner=body.learner, session_id=body.session_id, phase="question", item_id=item["id"], choice=choice,
        correct=int(correct), explanation=body.explanation, self_confidence=body.confidence, status=d.status,
        label=label, model_confidence=d.confidence, target=None, resolved=None, latency_ms=latency,
        time_ms=body.time_ms, edits=body.edits, mode="fbd" if fbd_mode else ("working" if working_mode else "choice"),
        numeric_value=body.numeric_value, image_id=body.image_id, input_method=body.input_method)

    hesitant = bool((body.edits or 0) >= 6 or (body.time_ms or 0) > 90_000)
    out = {
        "attempt_id": attempt_id, "status": d.status, "correct": correct, "label": label,
        "confidence": round(d.confidence, 3), "source": d.source, "notes": d.notes, "latency_ms": round(latency, 1),
        "probabilities": {k: round(v, 3) for k, v in sorted(d.probabilities.items(), key=lambda kv: -kv[1])},
        "self_confidence": body.confidence, "mode": "fbd" if fbd_mode else ("working" if working_mode else "choice"), "hesitant": hesitant,
    }
    if fbd_mode:
        out["diagram_feedback"] = fbd_feedback
        out["ideal_diagram"] = item["ideal"] if d.status != "unknown" else None
    if working_mode:
        out["worked"] = item["worked"] if d.status != "unknown" else None
        out["answer_shown"] = (f"{item['answer_value']:g} {item['unit']}") if d.status != "unknown" else None
        if matched_rule:
            out["rule"] = {"why": matched_rule["why"]}
    card_for_tutor = misconception_card(label, d.confidence) if label in MISCONCEPTIONS else None
    out["tutor"] = compose_tutor(d.status, label, body.explanation, item, card_for_tutor,
                                 INTERVENTIONS.get(label), correct, d.confidence,
                                 mode=out["mode"], learner=body.learner)
    if d.status in ("misconception", "flawed_reasoning"):
        confidently_held = body.confidence == "certain" and not hesitant
        state = store.on_detected(body.learner, label, confidently_held)
        card = misconception_card(label, d.confidence)
        out.update({
            "misconception": card,
            "intervention": INTERVENTIONS[label],
            "personalised": personalise(label, body.explanation, card, INTERVENTIONS[label], item["prompt"]),
            "state": state,
            "confidently_held": confidently_held,
            "probe": next_probe_payload(body.learner, label),
        })
    elif d.status == "unknown":
        if fbd_mode:
            miss = (fbd_feedback or {}).get("missing", [])
            out["ask"] = ("Your diagram is missing " + ", ".join(miss) + ". Add it and check again." if miss else
                          "Check each arrow's direction and try again.")
        elif working_mode:
            out["ask"] = ("Your number is right, but show the working — which formula, which values." if correct else
                          "That number is off, and the working doesn't show me where it went wrong. Write each step: "
                          "what you computed first, which formula, then the arithmetic.")
        else:
            out["ask"] = ("Your answer is right, but I can't tell what you were thinking. Could you add a sentence about *why*?"
                          if correct else
                          "I can't tell from this what led you to that answer. Add a sentence or two about why — "
                          "what forces act, or what the velocity and acceleration are doing.")
    else:
        out["message"] = "Right answer, sound reasoning."
    out["profile"] = store.profile(body.learner)
    return out


@app.post("/api/reassess")
def reassess(body: ReassessIn):
    probe = ITEM_INDEX.get(body.probe_id)
    if probe is None or body.probe_id not in {p["id"] for p in PROBES.get(body.misconception, [])}:
        raise HTTPException(404, "unknown probe for that misconception")
    target = body.misconception
    diag = get_diagnoser()
    store = get_store()
    try:
        d, latency = diag.diagnose(probe, body.choice, body.explanation)
    except ValueError as e:
        raise HTTPException(400, str(e))
    correct = diag.is_correct(probe, body.choice)

    # Resolution rule (FR-6): correct answer AND the targeted misconception absent from the reasoning.
    target_present = d.label == target
    inconclusive = d.status == "unknown" and correct    # right answer, too little reasoning to judge
    if inconclusive:
        resolved: bool | None = None
    else:
        resolved = bool(correct and not target_present)

    attempt_id = store.record_attempt(
        learner=body.learner, session_id=body.session_id, phase=body.phase, item_id=probe["id"], choice=body.choice,
        correct=int(correct), explanation=body.explanation, self_confidence=body.confidence, status=d.status,
        label=d.label, model_confidence=d.confidence, target=target,
        resolved=None if resolved is None else int(resolved), latency_ms=latency, time_ms=body.time_ms, edits=body.edits)

    tutor_label = target if (d.status in ("misconception", "flawed_reasoning") and d.label == target) else d.label
    tutor_status = d.status if resolved is not None else "unknown"
    if resolved:
        tutor_status = "correct"
    tutor = compose_tutor(tutor_status, tutor_label, body.explanation, probe,
                          misconception_card(tutor_label, d.confidence) if tutor_label in MISCONCEPTIONS else None,
                          INTERVENTIONS.get(tutor_label), correct, d.confidence, learner=body.learner)
    if resolved is False and not target_present and d.label not in MISCONCEPTIONS:
        tutor = {"text": f"{body.learner.split()[0]}, the reasoning is clean — no trace of “{MISCONCEPTIONS[target]['short'].lower()}” — "
                         f"but the answer itself is off, so I can't count this as fixed yet. Look at the idea once more and try another context.",
                 "source": "rules", "signals": tutor.get("signals", {})}
    out = {
        "attempt_id": attempt_id, "resolved": resolved, "correct": correct, "status": d.status, "label": d.label, "tutor": tutor,
        "confidence": round(d.confidence, 3), "source": d.source, "notes": d.notes, "latency_ms": round(latency, 1),
        "target": target, "phase": body.phase, "target_present": target_present,
        "probabilities": {k: round(v, 3) for k, v in sorted(d.probabilities.items(), key=lambda kv: -kv[1])},
    }

    if resolved is None:
        out["ask"] = "Right answer — but to count this as fixed I need to see your reasoning. One more sentence?"
        out["state"] = store.get_state(body.learner, target)["state"]
        out["profile"] = store.profile(body.learner)
        return out

    res = store.on_probe(body.learner, target, resolved, phase=body.phase, session_id=body.session_id)
    out.update(res)
    out["probes_required"] = PROBES_REQUIRED

    # A different misconception surfaced in the probe reasoning -> track it too
    if d.status in ("misconception", "flawed_reasoning") and d.label != target:
        store.on_detected(body.learner, d.label, body.confidence == "certain")
        out["new_misconception"] = misconception_card(d.label, d.confidence)
        out["new_intervention"] = INTERVENTIONS[d.label]

    if body.phase == "recheck":
        st = store.get_state(body.learner, target)
        across = bool(st and st["held_across_sessions"])
        out["held_across_sessions"] = across
        out["message"] = (("Still fixed in a new session — that's the strongest evidence of learning we have." if across else
                           "Still fixed after a delay — that's real learning.") if resolved
                          else "It came back. Marked as recurring; let's revisit the idea.")
        if not resolved:
            out["intervention"] = INTERVENTIONS[target]
            out["misconception"] = misconception_card(target, d.confidence)
            out["probe"] = next_probe_payload(body.learner, target)
    elif resolved and not res["resolved_now"]:
        used = len(store.probes_used(body.learner, target))
        if used >= MAX_PROBES:
            store.schedule_recheck(body.learner, target)
            out["message"] = ("Clear in this context. You've seen every transfer question for this idea, so I'll mark it "
                              "improving and re-check it a little later in the session.")
            out["probe"] = None
        else:
            out["message"] = f"Good — {res['probes_passed']} of {PROBES_REQUIRED} contexts clear. One more, in a new setting."
            out["probe"] = next_probe_payload(body.learner, target)
    elif resolved and res["resolved_now"]:
        out["message"] = (f"Resolved: right answer and clean reasoning across {PROBES_REQUIRED} contexts. "
                          f"I'll quietly re-check this later in the session.")
    else:
        used = len(store.probes_used(body.learner, target))
        if correct and target_present:
            out["message"] = "Right answer, but the same idea is still in your reasoning — so it isn't fixed yet."
        else:
            out["message"] = "Not yet. Let's look at the idea again from another angle."
        out["intervention"] = INTERVENTIONS[target]
        out["misconception"] = misconception_card(target, d.confidence)
        if target_present:
            out["personalised"] = personalise(target, body.explanation, out["misconception"], INTERVENTIONS[target], probe["prompt"])
        out["probe"] = next_probe_payload(body.learner, target) if used < MAX_PROBES else None
        if out["probe"] is None:
            out["message"] += " We'll leave this open and come back to it in a later session."
    out["profile"] = store.profile(body.learner)
    return out


@app.get("/api/recheck/{learner}")
def recheck(learner: str, session_id: Optional[int] = None):
    cands = get_store().recheck_candidates(learner, session_id=session_id)
    if not cands:
        return {"probe": None}
    m = cands[0]
    st = get_store().get_state(learner, m)
    cross = bool(st and st["resolved_session"] is not None and session_id is not None and st["resolved_session"] != session_id)
    return {"probe": next_probe_payload(learner, m, phase="recheck"), "misconception": misconception_card(m, 0.0),
            "cross_session": cross}


@app.get("/api/profile/{learner}")
def profile(learner: str):
    return get_store().profile(learner)


@app.get("/api/report/{learner}")
def report(learner: str):
    p = get_store().profile(learner)
    ms = p["misconceptions"]
    summary = {
        "answered": p["answered"],
        "right_first_time": p["right_first_time"],
        "found": len(ms),
        "fixed": sum(1 for m in ms if m["state"] == "resolved"),
        "improving": sum(1 for m in ms if m["state"] == "improving"),
        "still_open": sum(1 for m in ms if m["state"] in ("active",)),
        "recurring": sum(1 for m in ms if m["state"] == "recurring"),
        "flawed_reasoning": p["flawed_reasoning"],
        "confidently_held": sum(1 for m in ms if m["confidently_held"]),
        "held_across_sessions": sum(1 for m in ms if m.get("held_across_sessions")),
        "explained_share": p["explained_share"],
        "sessions": p["sessions"], "avg_time_s": p["avg_time_s"], "hesitant": p["hesitant"],
    }
    details = [{**m, "name": MISCONCEPTIONS[m["id"]]["name"], "short": MISCONCEPTIONS[m["id"]]["short"],
                "physics": MISCONCEPTIONS[m["id"]]["physics"], "colour": MISCONCEPTIONS[m["id"]]["colour"]} for m in ms]
    return {"learner": learner, "summary": summary, "misconceptions": details, "timeline": p["timeline"]}


@app.post("/api/session/finish")
def finish_session(body: FinishSession):
    get_store().finish_session(body.session_id)
    return {"ok": True}


@app.post("/api/feedback")
def feedback(body: FeedbackIn):
    if body.suggested_label not in MISCONCEPTIONS and body.suggested_label != NONE_LABEL:
        raise HTTPException(400, "unknown label")
    fid = get_store().add_feedback(body.learner, body.attempt_id, body.suggested_label, body.note)
    return {"ok": True, "feedback_id": fid, "message": "Thanks — stored as a candidate training example."}


# ---------------------------------------------------------------------------
# Teacher PIN: the class data (names, explanations, labelling) is for the teacher only.
# Set RELEARN_TEACHER_PIN to change it (default 1234). Tokens live in memory, so a server
# restart simply asks the teacher for the PIN again.
# ---------------------------------------------------------------------------

TEACHER_PIN = os.environ.get("RELEARN_TEACHER_PIN", "1234")
_teacher_tokens: set[str] = set()


def require_teacher(x_teacher_token: Optional[str] = Header(default=None)) -> None:
    if not x_teacher_token or x_teacher_token not in _teacher_tokens:
        raise HTTPException(401, "teacher PIN required")


@app.post("/api/teacher/login")
def teacher_login(body: TeacherLogin):
    if not hmac.compare_digest(body.pin.strip().encode(), TEACHER_PIN.encode()):
        time.sleep(0.4)  # slow down guessing
        raise HTTPException(401, "wrong PIN")
    token = secrets.token_urlsafe(24)
    _teacher_tokens.add(token)
    return {"token": token}


@app.post("/api/teacher/logout", dependencies=[Depends(require_teacher)])
def teacher_logout(x_teacher_token: Optional[str] = Header(default=None)):
    _teacher_tokens.discard(x_teacher_token)
    return {"ok": True}


@app.get("/api/activity", dependencies=[Depends(require_teacher)])
def activity(limit: int = 15):
    """Live feed: the latest answers across the class."""
    rows = get_store().recent_activity(max(1, min(limit, 50)))
    for r in rows:
        lab = r["target"] if r["phase"] != "question" else r["label"]
        r["name"] = MISCONCEPTIONS[lab]["name"] if lab in MISCONCEPTIONS else None
        r["colour"] = MISCONCEPTIONS[lab]["colour"] if lab in MISCONCEPTIONS else None
    return {"rows": rows, "now": time.time()}


@app.get("/api/feedback/export", dependencies=[Depends(require_teacher)])
def feedback_export():
    return {"rows": get_store().export_feedback_rows()}


@app.get("/api/class", dependencies=[Depends(require_teacher)])
def class_view():
    data = get_store().class_view()
    data["taxonomy"] = {m: {"name": v["name"], "colour": v["colour"]} for m, v in MISCONCEPTIONS.items()}
    return data


@app.get("/api/metrics")
def metrics():
    path = REPORTS / "metrics.json"
    if not path.exists():
        return JSONResponse({"available": False, "hint": "run: python ml/evaluate.py"}, status_code=200)
    m = json.loads(path.read_text(encoding="utf-8"))
    return {"available": True, **m}


@app.delete("/api/learner/{learner}")
def reset_learner(learner: str):
    get_store().reset_learner(learner)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Real-data pipeline, discovery, PDF report
# ---------------------------------------------------------------------------

@app.get("/api/labels/pending", dependencies=[Depends(require_teacher)])
def labels_pending(limit: int = 100):
    rows = get_store().unlabelled_attempts(limit)
    for r in rows:
        item = ITEM_INDEX.get(r["item_id"])
        r["prompt"] = item["prompt"] if item else ""
        opt = next((o for o in item.get("options", []) if o["key"] == r["choice"]), None) if item else None
        r["option_text"] = opt["text"] if opt else r["choice"]
    return {"rows": rows, "labels": [NONE_LABEL] + list(MISCONCEPTIONS.keys()) + ["OTHER"]}


@app.post("/api/labels", dependencies=[Depends(require_teacher)])
def set_label(body: LabelIn):
    if body.label not in MISCONCEPTIONS and body.label not in (NONE_LABEL, "OTHER"):
        raise HTTPException(400, "unknown label")
    get_store().set_label(body.attempt_id, body.label, body.labelled_by)
    return {"ok": True, "labelled": len(get_store().labelled_rows())}


@app.post("/api/labels/export", dependencies=[Depends(require_teacher)])
def export_labels():
    """Write labelled real responses to ml/data/real_responses.csv (evaluate.py reports on it; train.py --real adds it)."""
    import csv
    rows = get_store().labelled_rows()
    path = ROOT / "ml" / "data" / "real_responses.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["row_id", "item_id", "item_kind", "question", "option_key", "option_text", "correct", "explanation", "label", "source"])
        for r in rows:
            item = ITEM_INDEX.get(r["item_id"], {})
            opt = next((o for o in item.get("options", []) if o["key"] == r["choice"]), None)
            w.writerow([f"REAL{r['attempt_id']:05d}", r["item_id"], item.get("kind", "question") if item.get("kind") else "question",
                        item.get("prompt", ""), r["choice"], opt["text"] if opt else r["choice"], r["correct"],
                        r["explanation"], r["label"], "real"])
    return {"ok": True, "rows": len(rows), "path": str(path.relative_to(ROOT))}


@app.get("/api/discover", dependencies=[Depends(require_teacher)])
def discover(k: int = 3):
    """Misconception discovery: cluster explanations the model abstained on and surface candidate new ideas."""
    from ml.discover import discover_clusters
    rows = get_store().unknown_explanations()
    return discover_clusters(rows, k=k)


@app.get("/api/report/{learner}/pdf")
def report_pdf(learner: str):
    from backend.report_pdf import build_report_pdf
    data = report(learner)
    pdf = build_report_pdf(data)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="relearn-report-{learner}.pdf"'})


@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    """Photo of handwritten working. Saved locally; transcribed by an LLM if ANTHROPIC_API_KEY is set,
    otherwise the browser runs OCR (Tesseract.js) and the learner edits the transcript."""
    import base64
    import secrets
    import io
    from PIL import Image, UnidentifiedImageError
    data = await file.read()
    if len(data) > 8_000_000:
        raise HTTPException(413, "image too large (8 MB max)")
    # Trust the bytes, not the filename: only real PNG / JPEG / WebP images are stored and served back.
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = (img.format or "").upper()
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise HTTPException(400, "that file isn't an image — upload a photo (PNG, JPEG or WebP)")
    ext = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}.get(fmt)
    if ext is None:
        raise HTTPException(400, f"{fmt or 'this'} images aren't supported — upload a PNG, JPEG or WebP photo")
    image_id = secrets.token_hex(8) + "." + ext
    (UPLOADS / image_id).write_bytes(data)
    transcript = None
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        try:
            import anthropic  # type: ignore
            client = anthropic.Anthropic(api_key=key)
            media = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
            msg = client.messages.create(
                model=os.environ.get("RELEARN_LLM_MODEL", "claude-sonnet-4-5"), max_tokens=400,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media, "data": base64.b64encode(data).decode()}},
                    {"type": "text", "text": "Transcribe this handwritten physics working/explanation exactly as written, as plain text. "
                                             "Keep equations on their own lines. Output only the transcription."}]}])
            transcript = "".join(getattr(b, "text", "") for b in msg.content).strip() or None
        except Exception:
            transcript = None
    return {"image_id": image_id, "url": f"/uploads/{image_id}", "transcript": transcript,
            "ocr": "server" if transcript else "browser"}


# ---------------------------------------------------------------------------
# Voice explanation NLP + small "Ask the tutor" voice chatbot
# ---------------------------------------------------------------------------

NUDGES = {
    "no_reason": "Say *why* — start with “because…”.",
    "short": "A little more: which forces act, or what the velocity and acceleration are doing.",
    "no_physics": "Name the physics: a force, gravity, velocity, acceleration, mass…",
    "ok": "That's enough for me to work with.",
}


@app.post("/api/nlp/analyse")
def nlp_analyse(body: AnalyseIn):
    """Live NLP readout for the voice explanation: concepts heard, reason clause, hedging, and a nudge."""
    sig = analyse_explanation(body.text)
    if sig["n_words"] < 3:
        nudge = "short"
    elif not sig["concepts"]:
        nudge = "no_physics"
    elif not sig["has_reason_clause"] and sig["n_words"] < 8:
        nudge = "no_reason"
    else:
        nudge = "ok"
    return {"concepts": sig["concepts"], "has_reason": sig["has_reason_clause"], "hedged": sig["hedged"],
            "certain": sig["certain_words"], "words": sig["n_words"], "ready": nudge == "ok", "nudge": NUDGES[nudge]}


@app.post("/api/ask")
def ask_tutor(body: AskIn):
    """Small voice chatbot: physics questions answered from the knowledge base; everything else redirected politely."""
    item = ITEM_INDEX.get(body.item_id) if body.item_id else None
    u = understand(body.text, item, phase="ask", context=item["prompt"] if item else "")
    if u["intent"] != "command" and body.text.strip() and llm.available():
        history = [{"role": t.role, "content": t.content[:800]} for t in body.history[-8:]]
        reply = llm_chat(body.text.strip(), history, item)
        if reply:
            return {"reply": reply, "intent": "llm", "sources": [], "generated": True}
        # LLM down or out of quota: fall through to the offline knowledge base below
    if u["intent"] == "question":
        return {"reply": u["reply"], "intent": "question",
                "sources": [MISCONCEPTIONS[x]["name"] if x in MISCONCEPTIONS else x for x in u.get("sources", [])],
                "generated": bool(u.get("generated"))}
    if u["intent"] == "greeting":
        return {"reply": "Hi! Ask me anything about forces, velocity, acceleration or free fall.", "intent": "greeting"}
    if u["intent"] == "thanks":
        return {"reply": "You're welcome — keep going.", "intent": "thanks"}
    if u["intent"] == "confused":
        return {"reply": "That's fine. Tell me what you think happens, even if you're unsure — put it in the explanation box and I'll find the idea behind it.", "intent": "confused"}
    if u["intent"] == "capabilities":
        return {"reply": "I can explain mechanics: velocity vs acceleration, forces and Newton's three laws, free fall and gravity, "
                         "inertia, friction, and why common ideas like 'a moving object needs a force' are wrong. Try: "
                         "“why is acceleration not zero at the top?” or “what is inertia?”", "intent": "capabilities"}
    if u["intent"] == "who":
        return {"reply": "I'm Re:Learn's tutor. I find the idea behind your answers and fix exactly that.", "intent": "who"}
    if u["intent"] == "command":
        return {"reply": "This corner is for questions. Use the buttons on the page to move on, or speak your answer in the explanation box.", "intent": "command"}
    # looks like an answer or chat: don't grade it here
    return {"reply": "That sounds like your answer — say it in the explanation box under the question and I'll diagnose it. Ask me a physics question here instead.", "intent": "redirect"}
