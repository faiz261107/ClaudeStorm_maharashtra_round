from data import MISCONCEPTIONS


def _hits(mid, text):
    return sum(k in text for k in MISCONCEPTIONS[mid]["keywords"])


def diagnose(question, choice, explanation):
    """Placeholder. Replace with the trained model (model_trained.py), same signature and return shape."""
    text = (explanation or "").lower()
    correct = choice == question["correct"]
    pool = question.get("hidden", []) if correct else question["option_map"].get(choice, [])
    scored = sorted(((_hits(m, text), m) for m in pool), key=lambda x: -x[0])

    if correct:
        if scored and scored[0][0] > 0:  # right answer, wrong reasoning
            return {"correct": True, "status": "flawed_reasoning", "label": scored[0][1],
                    "confidence": round(min(0.5 + 0.15 * scored[0][0], 0.9), 2)}
        return {"correct": True, "status": "correct", "label": None, "confidence": 0.9}

    if not scored:
        return {"correct": False, "status": "unknown", "label": None, "confidence": 0.0}

    hits, top = scored[0]
    ambiguous = len(scored) > 1 and scored[0][0] == scored[1][0]
    conf = 0.35 if ambiguous else min(0.55 + 0.15 * hits, 0.95)
    return {"correct": False, "status": "misconception", "label": top, "confidence": round(conf, 2)}
