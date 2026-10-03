"""
Decision rule that turns raw model outputs into a diagnosis (PRD §8).

    classifier probabilities
        -> answer prior   (up-weight labels the chosen option can produce)      [FR-3]
        -> unseen fallback (description-embedding similarity for labels the
                            classifier was never trained on)                   [FR-10]
        -> abstain         (below confidence threshold -> unknown)              [FR-9]
        -> status          correct | flawed_reasoning | misconception | unknown [FR-4]

Shared by ml/evaluate.py and backend/diagnosis.py so the numbers we publish are
the numbers the product actually uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field

NONE_LABEL = "NONE"


@dataclass
class DecisionConfig:
    prior_boost: float = 2.5          # multiplier for labels in the option's misconception map
    none_boost: float = 1.3           # multiplier for NONE when the chosen option is correct
    item_boost: float = 1.6           # correct option: mild boost for misconceptions the ITEM can surface (FR-4)
    abstain_threshold: float = 0.45   # below this confidence -> unknown
    min_words: int = 3                # explanations shorter than this -> unknown
    # Tuned by leave-one-misconception-out grid search (see ml/evaluate.py):
    # TPR 0.74 on rows of the held-out misconception, FPR 0.7% on rows of known ones.
    unseen_sim_threshold: float = 0.10   # embedder similarity needed to use an unseen label
    unseen_margin: float = 0.02          # ...and lead over the best known description
    unseen_max_classifier_conf: float = 0.97  # never override a near-certain classifier
    unseen_in_map_sim_threshold: float = 0.08  # relaxed gate when the option map lists the unseen label


@dataclass
class Decision:
    status: str                 # correct | flawed_reasoning | misconception | unknown
    label: str                  # misconception id, NONE, or UNKNOWN
    confidence: float
    probabilities: dict[str, float]
    source: str = "classifier"  # classifier | embedding | abstain
    notes: list[str] = field(default_factory=list)


def apply_prior(probs: dict[str, float], allowed: list[str], is_correct: bool, cfg: DecisionConfig,
                item_misconceptions: list[str] | None = None) -> dict[str, float]:
    out = dict(probs)
    for lab in out:
        if lab in allowed:
            out[lab] *= cfg.prior_boost
        if is_correct and lab == NONE_LABEL:
            out[lab] *= cfg.none_boost
        if is_correct and item_misconceptions and lab in item_misconceptions:
            out[lab] *= cfg.item_boost
    z = sum(out.values()) or 1.0
    return {k: v / z for k, v in out.items()}


def decide(
    probs: dict[str, float],
    *,
    explanation: str,
    is_correct: bool,
    option_misconceptions: list[str],
    similarities: dict[str, float] | None = None,
    cfg: DecisionConfig | None = None,
    item_misconceptions: list[str] | None = None,
) -> Decision:
    cfg = cfg or DecisionConfig()
    notes: list[str] = []
    n_words = len((explanation or "").split())

    # 1. answer prior
    probs = apply_prior(probs, option_misconceptions, is_correct, cfg, item_misconceptions)
    label, conf = max(probs.items(), key=lambda kv: kv[1])
    source = "classifier"

    # 2. unseen-misconception fallback: only for labels the classifier cannot output
    if similarities:
        known = set(probs.keys())
        unseen = {k: v for k, v in similarities.items() if k not in known}
        if unseen:
            top_lab, top_sim = max(unseen.items(), key=lambda kv: kv[1])
            others = [v for k, v in similarities.items() if k != top_lab]
            runner_up = max(others) if others else 0.0
            strict = (top_sim >= cfg.unseen_sim_threshold
                      and top_sim - runner_up >= cfg.unseen_margin
                      and conf < cfg.unseen_max_classifier_conf)
            relaxed = (top_lab in option_misconceptions
                       and top_sim >= cfg.unseen_in_map_sim_threshold
                       and top_sim >= runner_up)
            if strict or relaxed:
                label, conf, source = top_lab, float(min(0.95, 0.5 + top_sim)), "embedding"
                notes.append(f"matched description of unseen misconception {top_lab} (sim={top_sim:.2f})")

    # 3. abstain
    if n_words < cfg.min_words:
        return Decision("unknown", "UNKNOWN", conf, probs, "abstain",
                        notes + [f"explanation too short ({n_words} words)"])
    if conf < cfg.abstain_threshold:
        return Decision("unknown", "UNKNOWN", conf, probs, "abstain",
                        notes + [f"confidence {conf:.2f} below threshold {cfg.abstain_threshold}"])

    # 4. status
    if label == NONE_LABEL:
        if is_correct:
            return Decision("correct", NONE_LABEL, conf, probs, source, notes)
        # wrong answer but no misconception detected in the reasoning:
        # fall back to the strongest mapped misconception if it has real support, else ask for more
        mapped = {k: v for k, v in probs.items() if k in option_misconceptions}
        if mapped:
            m_lab, m_conf = max(mapped.items(), key=lambda kv: kv[1])
            if m_conf >= cfg.abstain_threshold * 0.6:
                return Decision("misconception", m_lab, m_conf, probs, source,
                                notes + ["reasoning read as sound but answer is wrong; using option map"])
        return Decision("unknown", "UNKNOWN", conf, probs, "abstain",
                        notes + ["answer is wrong but the reasoning does not reveal why"])
    if is_correct:
        return Decision("flawed_reasoning", label, conf, probs, source, notes)
    return Decision("misconception", label, conf, probs, source, notes)
