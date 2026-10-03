"""
Generate the labelled misconception dataset (FR-1, M2).

Each row: (item, chosen option, explanation) -> misconception label (or NONE).

Strategy (from the PRD dataset plan):
  * hand-written seed explanations (source = "hand")      -> reported separately in evaluation
  * template-based student-style paraphrases per (question, option, misconception)
    with surface noise (typos, fillers, casing)             (source = "template")
  * NONE rows with correct reasoning
  * hard cases on purpose:
      - same wrong option, different misconceptions (confusable pairs)
      - correct option + misconceived reasoning (flawed reasoning)
      - short / vague explanations -> written to vague.csv (used to test abstention)

Rows are generated for the 30 questions AND the 15 transfer probes so the
classifier is competent on both. The trainer splits by item id, never by row.

Usage:
    python ml/generate_dataset.py            # writes ml/data/responses.csv and vague.csv
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

# Windows consoles may default to a legacy code page; keep ✓/✗/≥ printable.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.data import (  # noqa: E402
    NONE_LABEL,
    PROBES,
    QUESTIONS,
    all_misconceptions_for_item,
)

OUT_DIR = Path(__file__).resolve().parent / "data"
SEED = 42

# ---------------------------------------------------------------------------
# Template banks. Slots: {obj} {other} {moment} {agent} {surface}
# ---------------------------------------------------------------------------

MISC_TEMPLATES: dict[str, list[str]] = {
    "VA_CONFUSION": [
        "{obj} stops {moment}, so the velocity is zero and that means the acceleration is zero too",
        "it is not moving {moment} so there is no acceleration",
        "velocity is zero {moment} which means acceleration has to be zero as well",
        "since {obj} is at rest for that instant nothing is changing so acceleration is 0",
        "no movement means no acceleration",
        "acceleration and velocity are both zero when something is stationary",
        "the speed is 0 so a = 0",
        "{obj} is momentarily still so it can't be accelerating",
        "if it isn't moving it isn't accelerating",
        "acceleration is zero because the velocity is zero {moment}",
        "when something stops both velocity and acceleration are zero",
        "the acceleration goes down with the velocity and hits zero {moment}",
        "acceleration is basically the speed and the speed is zero there",
        "{obj} is frozen for a moment {moment}, nothing is happening to it, so no acceleration",
        "for that split second {obj} has stopped, so it isn't speeding up or slowing down",
        "acceleration follows velocity, zero velocity gives zero acceleration",
        "there is a point where {obj} is still and at that point everything is zero",
        "it has come to rest so its acceleration must also be at rest, i.e. zero",
        "velocity = 0 therefore acceleration = 0",
        "it stops {moment} and a stopped thing has no acceleration",
        "at that instant the speed is zero so there can't be any acceleration",
        "{obj} isn't going anywhere {moment} so nothing is accelerating it",
    ],
    "IMPETUS": [
        "{agent} gives {obj} a force that keeps it going until the force runs out",
        "the force from {agent} is still inside {obj} pushing it along",
        "{obj} carries the force of {agent} and slows down as that force gets used up",
        "the force of {agent} fades away and then gravity takes over",
        "{obj} still has the push from {agent} in it",
        "the upward force from {agent} is getting weaker as it goes up",
        "there is a force from {agent} that is being used up gradually",
        "the energy of {agent} is stored in {obj} and keeps it moving till it's gone",
        "{agent} put a force into {obj} and that force is still acting on it",
        "it keeps moving because of the force of {agent} that was transferred to it",
        "the force of {agent} eventually dies out which is why {obj} stops",
        "{obj} has the force of {agent} in it, and that force slowly runs out",
        "the push is still with {obj}, that is what keeps it going",
        "{agent} gave it a force and that force is wearing off",
        "the force that was given to {obj} is still acting on it after it left {agent}",
        "the throw force is bigger than gravity at first, then gravity becomes bigger",
        "its force is running down so it slows",
        "the force of {agent} keeps acting on {obj} until it is exhausted",
        "{obj} moves because it is carrying the force of {agent} with it",
        "the force from {agent} is still there but getting smaller and smaller",
        "{obj} has leftover force from {agent}",
        "motion needs a force so the force of {agent} must still be in {obj}",
    ],
    "FORCE_VELOCITY": [
        "a constant force means a constant speed",
        "{obj} moves at a steady speed so there must be a net force pushing it forward",
        "the force from {agent} is what gives {obj} its speed, more force means more speed",
        "to keep going at the same speed you need a force in that direction",
        "{agent} pushes forward so the net force is forward",
        "if the force is steady the velocity is steady",
        "it is moving forward so the net force has to be forward",
        "speed is proportional to force, same force same speed",
        "double the force and you double the speed",
        "a steady push gives a steady velocity",
        "{obj} needs a net force to keep moving, otherwise it would stop",
        "the force is what the velocity is, bigger force bigger velocity",
        "force in the direction of motion keeps the speed constant",
        "velocity stays the same because the force stays the same",
        "{obj} is going at a constant speed which means a constant force is acting on it",
        "there has to be a net force forward because that's the way {obj} is travelling",
        "the forward force from {agent} must be bigger than the backward forces or it wouldn't be moving",
        "constant force equals constant velocity, that's newton's law",
        "the force sets the speed, so a fixed force gives a fixed speed",
        "if the net force was zero {obj} would not be moving at all",
        "for {obj} to move forward there must be more force forward than backward",
        "velocity depends directly on the force applied",
    ],
    "THIRD_LAW": [
        "{obj} is bigger so it pushes harder on {other}",
        "{other} gets damaged so it must have felt the bigger force",
        "{obj} is moving faster so its force is larger",
        "{other} is tiny so it can't push back with much force",
        "the one that wins exerts more force",
        "{obj} has more mass so it exerts more force on {other}",
        "{other} doesn't move so it isn't pushing back",
        "the heavier object always pushes harder than the lighter one",
        "{obj} is the one doing the hitting so its force is bigger",
        "{other} is small so the force it exerts is small",
        "{obj} is more powerful so it applies more force",
        "{other} barely does anything to {obj}, so its force is much smaller",
        "the force depends on the size, {obj} is bigger so bigger force",
        "{obj} is the active one, {other} just receives the force",
        "{other} is crushed which proves it got more force than it gave",
        "{obj} wins the interaction so it must be pushing harder",
        "the faster or heavier one always exerts the greater force",
        "{other} can't exert a force on something as big as {obj}",
        "{obj} has more momentum so it hits with more force",
        "{other} is too light to push back with the same force",
        "{obj} does the pushing, {other} only gets pushed",
        "the big thing exerts the big force and the small thing exerts the small force",
    ],
    "HEAVIER_FASTER": [
        "{obj} is heavier so gravity pulls it harder and it falls faster",
        "more mass means more weight so {obj} lands before {other}",
        "the heavier one accelerates more because the force on it is bigger",
        "heavy things fall faster than light things",
        "gravity is stronger on {obj} so it speeds up more",
        "{obj} weighs more so it drops faster",
        "{other} is lighter so it falls more slowly",
        "the bigger the mass the faster it falls",
        "{obj} has more weight pulling it down so it reaches {surface} first",
        "a heavier object gets to the ground quicker because it is pulled harder",
        "{obj} accelerates faster because it has more mass",
        "gravity acts more strongly on heavier objects so they fall faster",
        "the force of gravity on {obj} is bigger so its acceleration is bigger",
        "{other} is light so it takes longer to fall",
        "weight decides how fast something falls, {obj} is heavier",
        "{obj} falls faster because there is more mass for gravity to pull on",
        "heavier means a bigger gravitational force which means a bigger acceleration",
        "{obj} would hit {surface} first since it's the heavy one",
        "a bigger mass is pulled down faster",
        "the heavier object always lands first when there's no air",
        "gravity pulls on {obj} more than on {other}, so {obj} falls faster",
        "more weight equals more speed when falling",
    ],
}

NONE_TEMPLATES: dict[str, list[str]] = {
    "accel_is_g_at_rest": [
        "velocity is zero {moment} but gravity still acts, so acceleration is still 9.8 down",
        "acceleration is the rate of change of velocity, and the velocity is changing from up to down, so it isn't zero",
        "gravity doesn't switch off {moment}, the acceleration stays g the whole time",
        "the only force is gravity so a = g at every point, including when v = 0",
        "velocity and acceleration are different things, v is zero for an instant but a stays constant",
        "{obj} is about to start moving again, so its velocity is changing, so it is accelerating",
        "net force is not zero {moment} so by F = ma the acceleration is not zero",
        "the speed is zero for an instant but it's changing, which is exactly what acceleration measures",
        "gravity gives a constant acceleration of 9.8 m/s² regardless of the velocity",
        "zero velocity doesn't mean zero acceleration, the velocity is reversing direction",
        "there's a net force on {obj} {moment} so it must be accelerating even though it's momentarily at rest",
        "a = dv/dt and v is passing through zero with a non-zero slope",
    ],
    "only_gravity": [
        "after release the only force is gravity, {agent} is no longer touching {obj}",
        "{agent} only exerts a force while in contact, once it leaves the only force is its weight",
        "no object is pushing {obj} up any more, so the only force is gravity downward",
        "ignoring air the only force on {obj} is its weight",
        "{obj} keeps moving because of inertia, not because of a force, and gravity is the only force acting",
        "a force needs something to apply it, nothing is applying an upward force so gravity is all there is",
        "forces come from interactions, the only interaction left is with the Earth, so gravity only",
        "newton's first law, it keeps its velocity unless a force acts, and the only force is gravity",
        "the hand's force ended at release, after that it's just mg downward",
        "the only thing acting on {obj} is the Earth's pull, which is why it slows going up",
        "gravity acts the whole time and nothing else does, that's what brings it back down",
        "once released {obj} is in free fall and the only force is gravity",
    ],
    "inertia": [
        "no force is needed to keep {obj} moving, newton's first law",
        "an object in motion stays in motion unless a net force acts on it",
        "with no friction there's nothing to slow {obj} down so it keeps going at the same velocity",
        "{obj} keeps its velocity because there is no net force to change it",
        "inertia keeps {obj} moving, forces only change motion they don't maintain it",
        "nothing is pushing it and nothing is stopping it, so it just keeps going",
        "there's no net force, so no acceleration, so the velocity stays the same",
        "it moves in a straight line at constant speed because no force acts on it",
        "forces cause changes in velocity, no force means no change, it keeps moving",
        "with zero net force the motion continues unchanged forever",
        "a body continues in uniform motion unless acted on by a force",
        "once {obj} is moving it needs no force to stay moving, only to change its motion",
    ],
    "net_force_zero_const_v": [
        "constant velocity means zero net force, the forces are balanced",
        "no acceleration so by F = ma the net force must be zero",
        "the forward force from {agent} is exactly cancelled by friction or drag",
        "steady speed in a straight line means the forces balance out",
        "velocity isn't changing so there is no net force on {obj}",
        "the push equals the resistance so the net force is zero and the speed stays constant",
        "if there were a net force {obj} would be accelerating, but it isn't",
        "balanced forces, zero acceleration, constant velocity",
        "a net force would change the velocity, the velocity is constant, so the net force is zero",
        "the forces add to zero, which is why the speed doesn't change",
        "there's a forward force and an equal backward force so they cancel",
        "constant v means a = 0 means F_net = 0",
    ],
    "const_force_accel": [
        "a constant force gives a constant acceleration so the velocity keeps increasing",
        "F = ma, constant F means constant a, and constant a means speed grows steadily",
        "force causes acceleration not velocity, so the speed keeps rising",
        "as long as the net force acts, {obj} keeps speeding up",
        "doubling the force doubles the acceleration, not the speed",
        "the force changes the velocity continuously, it doesn't fix it at one value",
        "with a steady net force the velocity increases at a steady rate",
        "acceleration is proportional to net force, so velocity keeps growing",
        "newton's second law says force gives acceleration, so {obj} gets faster and faster",
        "the velocity will keep increasing linearly while the force is applied",
        "constant force, constant acceleration, increasing velocity",
        "the net force is not zero so {obj} must accelerate, meaning its speed changes",
    ],
    "third_law_equal": [
        "newton's third law, forces are equal and opposite, {other} just accelerates more because of its smaller mass",
        "the forces are the same size, what's different is the acceleration because the masses are different",
        "action and reaction are always equal, it doesn't matter which one is bigger or faster",
        "both experience the same force, {other} is damaged more because it has less mass",
        "every force has an equal and opposite reaction force, so they are equal",
        "the force of {obj} on {other} equals the force of {other} on {obj}",
        "equal forces, different masses, so different accelerations and different damage",
        "forces come in pairs of equal magnitude regardless of size or speed",
        "third law pair, same magnitude, opposite direction",
        "the forces are equal, the heavier one just doesn't accelerate as much",
        "interaction forces are always equal in size, the effects differ because a = F/m",
        "{other} pushes back on {obj} with exactly the same force",
    ],
    "same_accel_free_fall": [
        "a = F/m = g for both, the extra weight is cancelled by the extra inertia",
        "all objects fall with the same acceleration g when there's no air",
        "gravity pulls harder on {obj} but it also has more mass to accelerate, so a is the same",
        "the force is mg and the mass is m so the acceleration is g for everything",
        "without air resistance mass doesn't matter, both accelerate at 9.8 m/s²",
        "the heavier one has a bigger force but also more inertia, they cancel out",
        "like the hammer and feather on the moon, they fall together",
        "free fall acceleration is independent of mass",
        "F = mg and F = ma so a = g regardless of m",
        "both start from rest with the same acceleration so they stay level and land together",
        "mass cancels out in the equation, so they fall at the same rate",
        "g is the same for all objects, so {obj} and {other} land at the same time",
    ],
}

# Vague / insufficient explanations: the model should abstain (status = unknown)
VAGUE = [
    "idk", "not sure", "just a guess", "it seemed right", "because physics", "i think so",
    "gut feeling", "we learned this", "obviously", "it makes sense", "common sense", "no idea",
    "guessing", "because", "it's the answer", "i remember this", "that one", "logic", "because yes",
    "my teacher said", "seems logical", "trust me", "cant explain", "it just is", "the usual",
]

PREFIXES = ["", "", "", "i think ", "because ", "well, ", "i chose this because ", "honestly ", "basically ",
            "i picked it since ", "my reasoning is that ", "so ", "i guess ", "obviously "]
SUFFIXES = ["", "", "", "", " i think", " right?", " i guess", ".", "!", " so yeah", " that's why", " imo"]


def _typo(word: str, rng: random.Random) -> str:
    if len(word) < 4 or rng.random() > 0.12:
        return word
    i = rng.randrange(len(word) - 1)
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]


def noisy(text: str, rng: random.Random) -> str:
    """Student-style surface noise."""
    t = text
    if rng.random() < 0.35:
        t = t.replace("'", "")
    if rng.random() < 0.3:
        t = t.replace("because", rng.choice(["cuz", "coz", "bc", "because"]))
    words = [_typo(w, rng) for w in t.split()]
    t = " ".join(words)
    t = rng.choice(PREFIXES) + t + rng.choice(SUFFIXES)
    r = rng.random()
    if r < 0.15:
        t = t.capitalize()
    elif r < 0.2:
        t = t.upper() if len(t) < 40 else t
    return t.strip()


def fill(template: str, ctx: dict) -> str:
    d = {"obj": "the object", "other": "the other object", "moment": "at that moment",
         "agent": "the push", "surface": "the ground"}
    d.update(ctx)
    return template.format(**d)


# ---------------------------------------------------------------------------
# Hand-written seed rows (varied, natural phrasing; not template-derived)
# ---------------------------------------------------------------------------

HAND_ROWS: list[tuple[str, str, str, str]] = [
    # (item_id, option_key, explanation, label)
    ("Q01", "A", "It stops at the top, so velocity is zero.", "VA_CONFUSION"),
    ("Q01", "A", "The force of the throw has run out.", "IMPETUS"),
    ("Q01", "B", "It is still slowing down because of the throw force.", "IMPETUS"),
    ("Q01", "B", "Gravity never stops acting; v is zero for an instant but it's changing.", NONE_LABEL),
    ("Q01", "C", "Its going up so the acceleration has to be up until the throw wears off", "IMPETUS"),
    ("Q02", "A", "at the end of the swing the bob hangs there for a sec, nothing is happening", "VA_CONFUSION"),
    ("Q02", "B", "gravity and tension don't cancel there so there's a net force along the arc", NONE_LABEL),
    ("Q03", "A", "the car is stopped. stopped = no accel", "VA_CONFUSION"),
    ("Q03", "D", "engine isn't pushing anymore so the cars force is gone", "IMPETUS"),
    ("Q04", "A", "it pauses so velocity 0 and accel 0, simple", "VA_CONFUSION"),
    ("Q04", "C", "the push is still carrying it up the ramp a bit until it's used up", "IMPETUS"),
    ("Q05", "A", "on the way up and down gravity acts but at the top it pauses so a is 0 there", "VA_CONFUSION"),
    ("Q06", "A", "lowest point, jumper is stationary, hence a = 0", "VA_CONFUSION"),
    ("Q06", "B", "the cord is stretched the most there so the upward pull is biggest, a is up", NONE_LABEL),
    ("Q07", "B", "the flick put a force in the coin, that force is still pushing it up but fading", "IMPETUS"),
    ("Q07", "C", "if it's going up something must be pushing it up more than gravity pulls down", "IMPETUS"),
    ("Q07", "A", "nothing touches the coin anymore. only gravity.", NONE_LABEL),
    ("Q08", "A", "the stick's force transferred into the puck and keeps pushing it", "IMPETUS"),
    ("Q08", "C", "something has to push it forward for it to move forward, the ice does", "FORCE_VELOCITY"),
    ("Q08", "B", "frictionless means no net force so it just keeps its velocity", NONE_LABEL),
    ("Q09", "B", "the curve of the tube gets stored in the ball's motion and slowly wears off", "IMPETUS"),
    ("Q10", "B", "the cannon's force is still carrying it forward", "IMPETUS"),
    ("Q10", "D", "at the peak it's momentarily not moving up or down so net force is zero", "VA_CONFUSION"),
    ("Q11", "A", "without the engine the ship's force gradually drains away and it drifts to a stop", "IMPETUS"),
    ("Q11", "C", "no force no motion. engine off means it stops", "FORCE_VELOCITY"),
    ("Q12", "A", "you throw it, it has your force, the force runs out, down it comes", "IMPETUS"),
    ("Q12", "B", "gravity is on it the whole flight, it just takes a while to reverse the velocity", NONE_LABEL),
    ("Q13", "A", "the thrown one has extra force from the throw holding it up longer", "IMPETUS"),
    ("Q13", "D", "if one is heavier it falls faster so it depends", "HEAVIER_FASTER"),
    ("Q14", "A", "same push, same speed. you'd need to push harder to go faster", "FORCE_VELOCITY"),
    ("Q14", "C", "it speeds up at first then settles at the speed that matches the force", "FORCE_VELOCITY"),
    ("Q14", "B", "no friction so the force keeps accelerating it, v goes up and up", NONE_LABEL),
    ("Q15", "A", "it's going up so the net force is up, duh", "FORCE_VELOCITY"),
    ("Q15", "B", "steady speed, no acceleration, tension equals weight", NONE_LABEL),
    ("Q16", "A", "the engine is pushing it along, that's the net force", "FORCE_VELOCITY"),
    ("Q16", "D", "faster car needs a bigger net force to keep that speed", "FORCE_VELOCITY"),
    ("Q17", "A", "twice the force twice the speed", "FORCE_VELOCITY"),
    ("Q17", "B", "F=ma, m fixed, so a doubles", NONE_LABEL),
    ("Q18", "A", "she's still going down so gravity must be winning over the air", "FORCE_VELOCITY"),
    ("Q18", "D", "terminal velocity means it's steady... so a is 0 i mean g, same thing", "VA_CONFUSION"),
    ("Q19", "A", "if the pull only matched friction it wouldn't go anywhere", "FORCE_VELOCITY"),
    ("Q19", "D", "the extra pull builds up inside the crate as motion", "IMPETUS"),
    ("Q20", "A", "constant thrust constant speed", "FORCE_VELOCITY"),
    ("Q20", "C", "the thrust gets used up over time and then it stops speeding up", "IMPETUS"),
    ("Q21", "A", "truck is way heavier, it obviously hits the car harder", "THIRD_LAW"),
    ("Q21", "D", "the car didn't do anything, the truck did the hitting", "THIRD_LAW"),
    ("Q21", "B", "third law. the car just has less mass so it gets flung", NONE_LABEL),
    ("Q22", "A", "a bus vs a mosquito, come on, the bus force is enormous in comparison", "THIRD_LAW"),
    ("Q22", "C", "the mosquito is the one that explodes so it took the hit harder", "THIRD_LAW"),
    ("Q22", "D", "a mosquito can't push a bus", "THIRD_LAW"),
    ("Q23", "A", "the earth is massive, the apple's pull is nothing in comparison", "THIRD_LAW"),
    ("Q23", "A", "bigger mass bigger pull, earth has way more mass", "HEAVIER_FASTER"),
    ("Q23", "C", "apples don't pull planets", "THIRD_LAW"),
    ("Q24", "B", "walls don't push, they just sit there, that's why nothing moves", "THIRD_LAW"),
    ("Q24", "D", "the wall is stronger than me so it pushes harder which is why I can't move it", "THIRD_LAW"),
    ("Q24", "A", "reaction force from the wall equals my push, I don't move because friction holds my feet", NONE_LABEL),
    ("Q25", "A", "A won so A was pulling harder, that's literally what winning means", "THIRD_LAW"),
    ("Q25", "D", "the heavier team pulls harder", "THIRD_LAW"),
    ("Q25", "B", "rope tension is the same both ways, the win comes from the ground friction", NONE_LABEL),
    ("Q26", "A", "she's moving fast so she hits him with more force than he hits her", "THIRD_LAW"),
    ("Q26", "D", "more momentum = more force on the other person", "THIRD_LAW"),
    ("Q27", "A", "bowling ball is heavy so it drops faster", "HEAVIER_FASTER"),
    ("Q27", "D", "heavier wins but only by a little since both are in a vacuum", "HEAVIER_FASTER"),
    ("Q27", "B", "no air, so mass doesn't matter, both at g", NONE_LABEL),
    ("Q28", "A", "hammer is heavier so gravity gets it down first", "HEAVIER_FASTER"),
    ("Q28", "B", "the apollo video shows them landing together, no air on the moon", NONE_LABEL),
    ("Q29", "A", "twice the mass twice the gravity twice the acceleration", "HEAVIER_FASTER"),
    ("Q29", "D", "X is heavier so the earth pulls it with more force and it goes faster", "HEAVIER_FASTER"),
    ("Q29", "D", "the heavier one exerts a bigger force so it must accelerate more", "THIRD_LAW"),
    ("Q29", "B", "weight is bigger but so is inertia, a = g for both", NONE_LABEL),
    ("Q30", "A", "adult is three times heavier so he gets pulled down faster", "HEAVIER_FASTER"),
    ("Q30", "B", "same g for everyone, they splash together", NONE_LABEL),
    ("Q30", "D", "the earth pulls the adult harder and so his force is bigger and he wins", "THIRD_LAW"),
    # Flawed reasoning behind correct answers
    ("Q14", "B", "the force keeps pushing it until the force is all used up, so it speeds up until then", "IMPETUS"),
    ("Q21", "B", "both forces are equal... though the truck is still pushing harder really", "THIRD_LAW"),
    ("Q27", "B", "same time, i guess the heavier one is only a tiny bit faster so it looks the same", "HEAVIER_FASTER"),
    ("Q16", "B", "net force is zero. the engine force is zero because it's not accelerating", NONE_LABEL),
    ("Q15", "B", "zero net force because its speed is constant, the cable just matches the weight", NONE_LABEL),
    ("Q05", "B", "g the whole way, even at the top where v=0", NONE_LABEL),
    ("Q11", "B", "newton's first law, nothing acts so nothing changes", NONE_LABEL),
    ("Q07", "A", "only gravity, my hand stopped touching it", NONE_LABEL),
    ("Q13", "B", "the horizontal throw doesn't change the vertical fall, both have a = g down", NONE_LABEL),
    ("Q26", "B", "equal and opposite, speed doesn't change the pair of forces", NONE_LABEL),
    ("Q09", "A", "once it's out, nothing is bending its path, so straight line", NONE_LABEL),
    ("Q20", "B", "net force up is constant so it accelerates the whole burn", NONE_LABEL),
]


def generate(seed: int = SEED, n_per_combo: int = 9, n_none: int = 11, n_flawed: int = 3) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    rows: list[dict] = []
    vague_rows: list[dict] = []

    items = [("question", q) for q in QUESTIONS] + [("probe", p) for plist in PROBES.values() for p in plist]

    for kind, item in items:
        ctx = item["ctx"]
        concept = item.get("concept")
        correct_key = item["answer"]
        present = all_misconceptions_for_item(item)

        for opt in item["options"]:
            is_correct = opt["key"] == correct_key
            base = {
                "item_id": item["id"], "item_kind": kind, "question": item["prompt"],
                "option_key": opt["key"], "option_text": opt["text"], "correct": int(is_correct),
            }
            if is_correct:
                # NONE rows: correct reasoning
                templates = NONE_TEMPLATES.get(concept) or _none_templates_for_probe(item)
                for t in rng.sample(templates, k=min(n_none, len(templates))):
                    rows.append({**base, "explanation": noisy(fill(t, ctx), rng), "label": NONE_LABEL, "source": "template"})
                # Flawed-reasoning rows: correct option, misconceived explanation (FR-4)
                for m in present:
                    for t in rng.sample(MISC_TEMPLATES[m], k=n_flawed):
                        rows.append({**base, "explanation": noisy(fill(t, ctx), rng), "label": m, "source": "template"})
            else:
                for m in opt["misconceptions"]:
                    for t in rng.sample(MISC_TEMPLATES[m], k=n_per_combo):
                        rows.append({**base, "explanation": noisy(fill(t, ctx), rng), "label": m, "source": "template"})
                # vague rows on wrong options -> abstention test set
                for v in rng.sample(VAGUE, k=1):
                    vague_rows.append({**base, "explanation": v, "label": "UNKNOWN", "source": "vague"})

    # Hand-written seed rows
    from backend.data import ITEM_INDEX, option_of
    for item_id, key, expl, label in HAND_ROWS:
        item = ITEM_INDEX[item_id]
        opt = option_of(item, key)
        rows.append({
            "item_id": item_id, "item_kind": "question", "question": item["prompt"],
            "option_key": key, "option_text": opt["text"], "correct": int(key == item["answer"]),
            "explanation": expl, "label": label, "source": "hand",
        })

    rng.shuffle(rows)
    for i, r in enumerate(rows):
        r["row_id"] = f"R{i:05d}"
    return rows, vague_rows


def _none_templates_for_probe(item: dict) -> list[str]:
    """Probes carry no concept key; infer from the misconception they target."""
    target = all_misconceptions_for_item(item)[0]
    return {
        "VA_CONFUSION": NONE_TEMPLATES["accel_is_g_at_rest"],
        "IMPETUS": NONE_TEMPLATES["only_gravity"] + NONE_TEMPLATES["inertia"],
        "FORCE_VELOCITY": NONE_TEMPLATES["net_force_zero_const_v"] + NONE_TEMPLATES["const_force_accel"],
        "THIRD_LAW": NONE_TEMPLATES["third_law_equal"],
        "HEAVIER_FASTER": NONE_TEMPLATES["same_accel_free_fall"],
    }[target]


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["row_id", "item_id", "item_kind", "question", "option_key", "option_text", "correct",
            "explanation", "label", "source"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    rows, vague_rows = generate()
    for i, r in enumerate(vague_rows):
        r["row_id"] = f"V{i:04d}"
    write_csv(OUT_DIR / "responses.csv", rows)
    write_csv(OUT_DIR / "vague.csv", vague_rows)

    from collections import Counter
    labels = Counter(r["label"] for r in rows)
    sources = Counter(r["source"] for r in rows)
    print(f"Wrote {len(rows)} labelled rows -> {OUT_DIR / 'responses.csv'}")
    print("  by label :", dict(labels))
    print("  by source:", dict(sources))
    print(f"  items    : {len({r['item_id'] for r in rows})}")
    print(f"Wrote {len(vague_rows)} vague rows -> {OUT_DIR / 'vague.csv'}")


if __name__ == "__main__":
    main()
