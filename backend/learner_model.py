"""
Learner model (FR-8) + resolution logic (FR-6, FR-7) on SQLite.

States per (learner, misconception):
    active      detected, not yet fixed
    improving   passed 1 of PROBES_REQUIRED transfer probes
    resolved    passed PROBES_REQUIRED probes in different contexts
    recurring   detected again after being resolved (or failed the delayed recheck)

Every attempt is stored (learner, phase, item, choice, explanation, label,
confidence, resolved) so the profile is always recomputable.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

PROBES_REQUIRED = int(os.environ.get("RELEARN_PROBES_REQUIRED", 2))   # FR-7: 2–3 probes
MAX_PROBES = 3
RECHECK_GAP = int(os.environ.get("RELEARN_RECHECK_GAP", 2))           # attempts to wait before delayed recheck

DB_PATH = Path(os.environ.get("RELEARN_DB", Path(__file__).resolve().parent / "relearn.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, learner TEXT NOT NULL, started REAL NOT NULL,
    finished REAL, question_order TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, learner TEXT NOT NULL, session_id INTEGER, ts REAL NOT NULL,
    phase TEXT NOT NULL, item_id TEXT NOT NULL, choice TEXT NOT NULL, correct INTEGER NOT NULL,
    explanation TEXT NOT NULL, self_confidence TEXT, status TEXT NOT NULL, label TEXT NOT NULL,
    model_confidence REAL NOT NULL, target TEXT, resolved INTEGER, latency_ms REAL
);
CREATE TABLE IF NOT EXISTS misconception_state (
    learner TEXT NOT NULL, misconception TEXT NOT NULL, state TEXT NOT NULL,
    detected_count INTEGER DEFAULT 0, resolved_count INTEGER DEFAULT 0,
    probes_passed INTEGER DEFAULT 0, probes_failed INTEGER DEFAULT 0, probes_used TEXT DEFAULT '[]',
    confidently_held INTEGER DEFAULT 0, first_detected REAL, last_detected REAL, resolved_at REAL,
    recheck_due_after INTEGER, recheck_done INTEGER DEFAULT 0,
    PRIMARY KEY (learner, misconception)
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT, learner TEXT, attempt_id INTEGER, suggested_label TEXT,
    note TEXT, ts REAL
);
"""


class LearnerStore:
    def __init__(self, path: Path = DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------------- sessions ----------------
    def start_session(self, learner: str, question_order: list[str]) -> int:
        cur = self.conn.execute("INSERT INTO sessions(learner, started, question_order) VALUES (?,?,?)",
                                (learner, time.time(), json.dumps(question_order)))
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_session(self, session_id: int) -> None:
        self.conn.execute("UPDATE sessions SET finished=? WHERE id=?", (time.time(), session_id))
        self.conn.commit()

    # ---------------- attempts ----------------
    def record_attempt(self, **kw) -> int:
        cols = ["learner", "session_id", "ts", "phase", "item_id", "choice", "correct", "explanation",
                "self_confidence", "status", "label", "model_confidence", "target", "resolved", "latency_ms"]
        kw.setdefault("ts", time.time())
        cur = self.conn.execute(
            f"INSERT INTO attempts({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [kw.get(c) for c in cols])
        self.conn.commit()
        return int(cur.lastrowid)

    def attempt_count(self, learner: str) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM attempts WHERE learner=?", (learner,)).fetchone()[0])

    # ---------------- misconception state ----------------
    def get_state(self, learner: str, m: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM misconception_state WHERE learner=? AND misconception=?",
                                 (learner, m)).fetchone()

    def all_states(self, learner: str) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM misconception_state WHERE learner=? ORDER BY first_detected",
                                 (learner,)).fetchall()

    def on_detected(self, learner: str, m: str, confidently_held: bool) -> str:
        """Misconception detected in a question/probe answer. Returns the new state."""
        now = time.time()
        row = self.get_state(learner, m)
        if row is None:
            self.conn.execute(
                "INSERT INTO misconception_state(learner, misconception, state, detected_count, confidently_held, first_detected, last_detected)"
                " VALUES (?,?,?,?,?,?,?)", (learner, m, "active", 1, int(confidently_held), now, now))
            state = "active"
        else:
            state = "recurring" if row["state"] in ("resolved",) else "active"
            self.conn.execute(
                "UPDATE misconception_state SET state=?, detected_count=detected_count+1, last_detected=?,"
                " probes_passed=0, confidently_held=MAX(confidently_held, ?), recheck_due_after=NULL, recheck_done=0"
                " WHERE learner=? AND misconception=?", (state, now, int(confidently_held), learner, m))
        self.conn.commit()
        return state

    def probes_used(self, learner: str, m: str) -> list[str]:
        row = self.get_state(learner, m)
        return json.loads(row["probes_used"]) if row else []

    def mark_probe_used(self, learner: str, m: str, probe_id: str) -> None:
        used = self.probes_used(learner, m)
        if probe_id not in used:
            used.append(probe_id)
        self.conn.execute("UPDATE misconception_state SET probes_used=? WHERE learner=? AND misconception=?",
                          (json.dumps(used), learner, m))
        self.conn.commit()

    def on_probe(self, learner: str, m: str, passed: bool, phase: str = "probe") -> dict:
        """Apply a transfer-probe result. Returns {state, probes_passed, probes_failed, resolved_now}."""
        row = self.get_state(learner, m)
        if row is None:
            self.on_detected(learner, m, False)
            row = self.get_state(learner, m)
        now = time.time()
        resolved_now = False
        if phase == "recheck":
            if passed:
                state = "resolved"
                newly = row["state"] != "resolved"
                self.conn.execute(
                    "UPDATE misconception_state SET recheck_done=1, state=?,"
                    " resolved_count=resolved_count+?, resolved_at=COALESCE(resolved_at, ?) WHERE learner=? AND misconception=?",
                    (state, int(newly), now, learner, m))
            else:
                state = "recurring"
                self.conn.execute(
                    "UPDATE misconception_state SET state=?, detected_count=detected_count+1, last_detected=?, probes_passed=0,"
                    " recheck_done=1, recheck_due_after=NULL WHERE learner=? AND misconception=?", (state, now, learner, m))
            self.conn.commit()
            return {"state": state, "probes_passed": row["probes_passed"], "probes_failed": row["probes_failed"], "resolved_now": False}

        if passed:
            passed_n = row["probes_passed"] + 1
            if passed_n >= PROBES_REQUIRED:
                state, resolved_now = "resolved", True
                due = self.attempt_count(learner) + RECHECK_GAP
                self.conn.execute(
                    "UPDATE misconception_state SET state=?, probes_passed=?, resolved_count=resolved_count+1, resolved_at=?,"
                    " recheck_due_after=?, recheck_done=0 WHERE learner=? AND misconception=?",
                    (state, passed_n, now, due, learner, m))
            else:
                state = "improving"
                self.conn.execute("UPDATE misconception_state SET state=?, probes_passed=? WHERE learner=? AND misconception=?",
                                  (state, passed_n, learner, m))
            failed_n = row["probes_failed"]
        else:
            failed_n = row["probes_failed"] + 1
            passed_n = 0
            state = "recurring" if row["state"] == "recurring" else "active"
            self.conn.execute(
                "UPDATE misconception_state SET state=?, probes_failed=?, probes_passed=0, last_detected=? WHERE learner=? AND misconception=?",
                (state, failed_n, now, learner, m))
        self.conn.commit()
        return {"state": state, "probes_passed": passed_n, "probes_failed": failed_n, "resolved_now": resolved_now}

    def schedule_recheck(self, learner: str, m: str) -> None:
        """Used when probes are exhausted while 'improving': settle it with a delayed recheck."""
        due = self.attempt_count(learner) + RECHECK_GAP
        self.conn.execute("UPDATE misconception_state SET recheck_due_after=?, recheck_done=0 WHERE learner=? AND misconception=?",
                          (due, learner, m))
        self.conn.commit()

    def recheck_candidates(self, learner: str) -> list[str]:
        n = self.attempt_count(learner)
        rows = self.conn.execute(
            "SELECT misconception FROM misconception_state WHERE learner=? AND state IN ('resolved','improving') AND recheck_done=0"
            " AND recheck_due_after IS NOT NULL AND recheck_due_after <= ? ORDER BY last_detected", (learner, n)).fetchall()
        return [r["misconception"] for r in rows]

    # ---------------- feedback (open question §15) ----------------
    def add_feedback(self, learner: str, attempt_id: int, suggested_label: str, note: str) -> int:
        cur = self.conn.execute("INSERT INTO feedback(learner, attempt_id, suggested_label, note, ts) VALUES (?,?,?,?,?)",
                                (learner, attempt_id, suggested_label, note, time.time()))
        self.conn.commit()
        return int(cur.lastrowid)

    def export_feedback_rows(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT f.suggested_label, a.item_id, a.choice, a.explanation, a.label AS model_label FROM feedback f"
            " JOIN attempts a ON a.id = f.attempt_id").fetchall()
        return [dict(r) for r in rows]

    # ---------------- profile / report ----------------
    def profile(self, learner: str) -> dict:
        attempts = self.conn.execute("SELECT * FROM attempts WHERE learner=? ORDER BY id", (learner,)).fetchall()
        states = self.all_states(learner)
        questions = [a for a in attempts if a["phase"] == "question"]
        # group by item: an "unknown -> elaborate" resubmission is the same question, not a new one
        by_item: dict[str, list] = {}
        for a in questions:
            by_item.setdefault(a["item_id"], []).append(a)
        first = [grp[0] for grp in by_item.values()]
        final = [grp[-1] for grp in by_item.values()]
        return {
            "learner": learner,
            "answered": len(by_item),
            "attempts": len(attempts),
            "right_first_time": sum(1 for a in first if a["status"] == "correct"),
            "flawed_reasoning": sum(1 for a in final if a["status"] == "flawed_reasoning"),
            "unknown": sum(1 for a in questions if a["status"] == "unknown"),
            "elaborated": sum(1 for grp in by_item.values() if len(grp) > 1),
            "explained_share": (sum(1 for a in attempts if len(a["explanation"].split()) >= 3) / len(attempts)) if attempts else None,
            "misconceptions": [
                {
                    "id": s["misconception"], "state": s["state"],
                    "detected": s["detected_count"], "resolved": s["resolved_count"],
                    "probes_passed": s["probes_passed"], "probes_failed": s["probes_failed"],
                    "probes_required": PROBES_REQUIRED,
                    "confidently_held": bool(s["confidently_held"]),
                    "recheck_pending": bool(s["state"] == "resolved" and not s["recheck_done"]),
                    "first_detected": s["first_detected"], "last_detected": s["last_detected"],
                }
                for s in states
            ],
            "timeline": [
                {"id": a["id"], "phase": a["phase"], "item_id": a["item_id"], "status": a["status"], "label": a["label"],
                 "confidence": a["model_confidence"], "target": a["target"], "resolved": a["resolved"],
                 "self_confidence": a["self_confidence"], "ts": a["ts"]}
                for a in attempts
            ],
        }

    def class_view(self) -> dict:
        learners = [r[0] for r in self.conn.execute("SELECT DISTINCT learner FROM attempts").fetchall()]
        rows = self.conn.execute(
            "SELECT misconception, state, COUNT(*) n, SUM(confidently_held) ch FROM misconception_state GROUP BY misconception, state").fetchall()
        freq: dict[str, dict] = {}
        for r in rows:
            d = freq.setdefault(r["misconception"], {"active": 0, "improving": 0, "resolved": 0, "recurring": 0, "confidently_held": 0, "total": 0})
            d[r["state"]] += r["n"]
            d["total"] += r["n"]
            d["confidently_held"] += r["ch"] or 0
        status_counts = dict(self.conn.execute(
            "SELECT status, COUNT(*) FROM attempts WHERE phase='question' GROUP BY status").fetchall())
        return {"learners": len(learners), "learner_names": learners, "misconceptions": freq,
                "question_status_counts": status_counts,
                "attempts": self.attempt_count_all()}

    def attempt_count_all(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0])

    def reset_learner(self, learner: str) -> None:
        for t in ("attempts", "misconception_state", "sessions"):
            self.conn.execute(f"DELETE FROM {t} WHERE learner=?", (learner,))
        self.conn.commit()


_store: LearnerStore | None = None


def get_store() -> LearnerStore:
    global _store
    if _store is None:
        _store = LearnerStore()
    return _store
