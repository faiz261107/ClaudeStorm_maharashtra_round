# Re:Learn — 3-minute judge demo (M7)

Covers all four diagnosis statuses, a resolved case, a not-resolved case, the delayed recheck,
the teacher view and the evaluation page. Every input below is tested in `tests/test_api.py`.

Before the demo: `python run.py` and, for a clean slate, `curl -X DELETE http://127.0.0.1:8000/api/learner/Aiman`
(or just use a new name).

---

## 0 · The pitch (15 s)

> "Most platforms grade right or wrong and show the solution. That throws away the most useful thing a wrong
> answer carries: *which mistaken idea produced it*. Re:Learn reads the answer **and** the explanation, names the
> misconception, fixes exactly that, and then proves the fix stuck."

Start a **Quick (8 questions)** session as **Aiman**.

## 1 · Same wrong answer, two different diagnoses (45 s)

**Q1 — ball at the top of its flight.** Pick **A (zero)**, confidence **certain**, explain:

> It stops at the top, so velocity is zero.

→ **Misconception found · Velocity–acceleration confusion** (≈98 %). Point out: *held with certainty* badge,
confidence meter, candidate bars, "That's not what I meant".

Now say: *"A second student picks the same option but writes…"* — open a second tab, start as **Riya**, Q1, pick **A**:

> The force of the throw has run out.

→ **Impetus: motion carries a force.** Same option, different fix. A traditional LMS marks both identically.

## 2 · Right answer, wrong idea (20 s)

In Riya's tab, hit Learn → start as **Sam**, Q1, pick **B (9.8 m/s² down — the correct one)**:

> It is still slowing down because of the throw force.

→ **Right answer, wrong idea · Impetus.** The LMS would mark this fully correct.

## 3 · The fix (30 s)

Back in Aiman's tab. Scroll the intervention:
- *What your reasoning suggests* vs *what physics says*
- Animation: velocity arrow shrinks to zero at the top, acceleration arrow never changes.
  Tick **"Show what the belief predicts"** — red ghost shows the acceleration wrongly vanishing.
- Worked example, check-yourself.

Click **Test the fix in a new situation →**

## 4 · Verify: resolved only with clean reasoning, twice (40 s)

**Probe 1 — child on a swing.** Pick **B**, explain:

> the velocity is zero for an instant but gravity still acts so the acceleration is not zero

→ *Clear in this context* · improving · 1/2. Click **Next context**.

**Probe 2 — mass on a spring.** Pick **B**:

> net force is not zero at the lowest point so there is a large acceleration even though v = 0

→ **Resolved** — right answer and clean reasoning across 2 contexts. "I'll quietly re-check this later."

*Not-resolved variant (if time):* answer probe 2 with **B** but write
> the velocity is zero so the acceleration must be zero too, but B seemed right
→ *Answer ✓ but the same idea is still in your reasoning — not fixed yet.* Another context is offered.

## 5 · Unknown → ask, don't guess (15 s)

**Q2 — truck vs car.** Pick **B**, explain `equal and opposite forces, third law` → **Correct**. Next.
**Q3 — bowling ball vs tennis ball.** Pick **A**, explain just:

> idk

→ **Tell me more** — the model abstains and asks for a sentence. Add:

> the bowling ball is heavier so gravity pulls it harder and it falls faster

→ **Heavier objects fall faster.** Continue through the probes (pick **B**, write `a = F/m = g for both, mass cancels`).

## 6 · Delayed recheck → recurring (20 s)

After two more questions the app injects a **Quick recheck** for Velocity–acceleration confusion.
Answer it *wrong on purpose* — pick **A**, write `it is not moving so no acceleration` →
**It came back · recurring.** The thinking map re-opens the idea. "A correct follow-up is not proof of learning —
and neither is a fix that fades."

## 7 · Report, teacher view, evidence (15 s)

- Sidebar → **Finish & see report**: right first time / found / fixed / recurring, timeline ribbon.
- **Teacher** tab: which ideas the class holds (Aiman, Riya, Sam), by state.
- **Evaluation** tab: held-out macro-F1 0.99, confusable-pair accuracy 0.97, flawed-reasoning recall 0.98,
  unseen-misconception top-1 0.85, ECE 0.05, confusion matrix — all PRD targets met, split by question.

## Closing line

> "Diagnose the idea, not the answer. Fix the idea, not the score. And never call it learned until it survives a
> new context and a delay."

---

### Backup inputs per misconception (any question that lists them)

| Misconception | Wrong-option explanation | Clean probe explanation |
|---|---|---|
| VA_CONFUSION | it stops so the acceleration is zero | v is zero for an instant but gravity still acts, a = g |
| IMPETUS | the force of the throw is still in the ball, running out | only gravity acts after release; inertia keeps it moving |
| FORCE_VELOCITY | constant force means constant speed, net force is forward | constant velocity means zero net force, forces balance |
| THIRD_LAW | the truck is bigger so it pushes harder | forces are equal and opposite, the lighter one accelerates more |
| HEAVIER_FASTER | heavier so gravity pulls it harder and it falls faster | a = F/m = g for both, more weight but more inertia |
