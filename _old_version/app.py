import sqlite3
import time
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from data import QUESTIONS, REASSESS, INTERVENTIONS, MISCONCEPTIONS, ALL
from model import diagnose

app = FastAPI(title="Re:Learn")
DB = "relearn.db"


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


with db() as con:
    con.execute("""CREATE TABLE IF NOT EXISTS attempts(
        id INTEGER PRIMARY KEY, learner TEXT, qid TEXT, phase TEXT, target TEXT,
        choice TEXT, explanation TEXT, correct INT, label TEXT, confidence REAL,
        resolved INT, ts REAL)""")


def public(q):  # never send the answer key to the browser
    return {k: q[k] for k in ("id", "topic", "text", "options")}


class Answer(BaseModel):
    learner: str
    qid: str
    choice: str
    explanation: str = ""
    target: Optional[str] = None


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.get("/api/questions")
def questions():
    return [public(q) for q in QUESTIONS]


@app.post("/api/diagnose")
def diagnose_answer(a: Answer):
    q = ALL.get(a.qid)
    if not q:
        raise HTTPException(404, "Unknown question")
    d = diagnose(q, a.choice, a.explanation)
    with db() as con:
        con.execute("INSERT INTO attempts(learner,qid,phase,choice,explanation,correct,label,confidence,ts) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (a.learner, a.qid, "diagnose", a.choice, a.explanation, d["correct"], d["label"],
                     d["confidence"], time.time()))
    if d["label"]:
        d["misconception"] = MISCONCEPTIONS[d["label"]]
        d["intervention"] = INTERVENTIONS[d["label"]]
        d["recheck"] = public(REASSESS[d["label"]])
    return d


@app.post("/api/reassess")
def reassess(a: Answer):
    q = ALL.get(a.qid)
    if not q or not a.target:
        raise HTTPException(400, "Missing question or target misconception")
    d = diagnose(q, a.choice, a.explanation)
    # Resolved only if the answer is right AND the reasoning no longer shows the same misconception
    resolved = d["correct"] and d["label"] != a.target
    with db() as con:
        con.execute("INSERT INTO attempts(learner,qid,phase,target,choice,explanation,correct,label,confidence,resolved,ts) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (a.learner, a.qid, "reassess", a.target, a.choice, a.explanation, d["correct"], d["label"],
                     d["confidence"], resolved, time.time()))
    return {**d, "resolved": resolved}


@app.get("/api/profile/{learner}")
def profile(learner: str):
    with db() as con:
        rows = con.execute("SELECT * FROM attempts WHERE learner=? ORDER BY ts", (learner,)).fetchall()
    stats = {}
    for r in rows:
        key = r["label"] if r["phase"] == "diagnose" else r["target"]
        if not key:
            continue
        s = stats.setdefault(key, {"id": key, "name": MISCONCEPTIONS[key]["name"],
                                   "detected": 0, "resolved": 0, "status": "active"})
        if r["phase"] == "diagnose":
            s["detected"] += 1
            s["status"] = "active"
        elif r["resolved"]:
            s["resolved"] += 1
            s["status"] = "resolved"
    for s in stats.values():
        if s["status"] == "active" and s["detected"] > 1:
            s["status"] = "recurring"
    answered = sum(r["phase"] == "diagnose" for r in rows)
    return {"answered": answered, "misconceptions": list(stats.values())}
