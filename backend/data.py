"""
Re:Learn content layer.

Everything the product knows about physics lives here:
  * MISCONCEPTIONS  – the v1 taxonomy (5 FCI-derived misconceptions)
  * QUESTIONS       – 30 multiple-choice items; every wrong option is mapped to
                      the misconception(s) that can produce it (FR-3)
  * INTERVENTIONS   – explanation, worked example and simulation per misconception (FR-5)
  * PROBES          – transfer questions in new contexts per misconception (FR-6 / FR-7)

Adding a misconception = add one entry to each of the four tables (extensibility NFR).
Answer keys never leave this module except through server-side checks.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. Taxonomy
# ---------------------------------------------------------------------------

MISCONCEPTIONS: dict[str, dict] = {
    "VA_CONFUSION": {
        "name": "Velocity–acceleration confusion",
        "short": "Zero velocity means zero acceleration",
        "believes": (
            "If an object is momentarily at rest, nothing is changing, so its "
            "acceleration must be zero too. Velocity and acceleration rise and fall together."
        ),
        "physics": (
            "Acceleration is the rate at which velocity changes, not the velocity itself. "
            "An object can be at rest for a single instant while its velocity is changing "
            "rapidly — so the acceleration is non-zero. A ball at the top of its flight has "
            "v = 0 but a = 9.8 m/s² downward, which is exactly why it starts falling."
        ),
        # Learner-style description used by the embedding fallback (FR-10).
        "description": (
            "it stops at the top so the acceleration is zero. at rest means no acceleration. "
            "velocity is zero so acceleration must be zero as well. it is not moving for that "
            "instant so nothing is happening to it. when the speed is zero everything is zero. "
            "acceleration and velocity go together, if one is zero the other is zero. "
            "it is momentarily stationary so there is no acceleration. no motion no acceleration."
        ),
        "confusable_with": ["IMPETUS"],
        "simulation": "throw_up",
        "colour": "#7c3aed",
    },
    "IMPETUS": {
        "name": "Impetus: motion carries a force",
        "short": "A moving object carries the force that launched it",
        "believes": (
            "When something is thrown or hit, the push is stored inside it and keeps it going. "
            "The object slows down or falls when that stored force runs out."
        ),
        "physics": (
            "A force only acts while the pusher is in contact. Once a ball leaves your hand "
            "the only force on it (ignoring air) is gravity. Nothing is 'used up' — the ball "
            "keeps moving because of inertia (Newton's first law), and it changes its motion "
            "only because gravity acts on it the whole time."
        ),
        "description": (
            "the force of the throw keeps it going up. the push is still in the ball. "
            "it slows down because the force from the hand is running out. the throw force "
            "wears off and then gravity takes over. the force of the hit is still acting on it. "
            "the ball carries the force that was given to it. the energy of the push is used up "
            "and that is when it falls. the upward force gets smaller than gravity."
        ),
        "confusable_with": ["VA_CONFUSION", "FORCE_VELOCITY"],
        "simulation": "forces_in_flight",
        "colour": "#ea580c",
    },
    "FORCE_VELOCITY": {
        "name": "Force causes constant speed",
        "short": "A constant net force gives a constant speed",
        "believes": (
            "Force and speed are proportional: a steady push produces a steady speed, "
            "a bigger push a bigger speed, and moving at constant speed needs a net force."
        ),
        "physics": (
            "Newton's second law links net force to acceleration, not to velocity: "
            "F_net = m·a. A constant net force makes velocity keep increasing. Constant "
            "velocity means the net force is zero — any forward push is exactly cancelled "
            "by friction or drag."
        ),
        "description": (
            "constant force gives constant speed. the net force is forward because it is moving "
            "forward. it moves at a steady speed because a steady force pushes it. if you push "
            "harder it goes faster, a constant push means constant velocity. you need a force to "
            "keep it moving at the same speed. the force is what the speed is. double the force "
            "and the speed doubles. there must be a net force in the direction it travels."
        ),
        "confusable_with": ["IMPETUS"],
        "simulation": "constant_force",
        "colour": "#0891b2",
    },
    "THIRD_LAW": {
        "name": "Unequal action–reaction",
        "short": "The heavier or faster object exerts the bigger force",
        "believes": (
            "In any interaction the bigger, heavier, faster or 'more active' object pushes "
            "harder than the other one. The winner of a collision exerted the bigger force."
        ),
        "physics": (
            "Newton's third law: forces always come in equal and opposite pairs. The truck "
            "and the car push on each other with exactly the same force; what differs is the "
            "effect of that force — the lighter object gets the larger acceleration (a = F/m)."
        ),
        "description": (
            "the truck is bigger so it pushes harder. the heavier one exerts more force. "
            "the faster one hits with more force. the big object wins so its force is larger. "
            "the car gets crushed so it must have received more force. the wall does not move "
            "so it does not push back. the earth pulls more than the apple pulls the earth. "
            "the team that wins pulls harder on the rope. the mosquito is tiny so its force is tiny."
        ),
        "confusable_with": ["HEAVIER_FASTER"],
        "simulation": "collision",
        "colour": "#be123c",
    },
    "HEAVIER_FASTER": {
        "name": "Heavier objects fall faster",
        "short": "Heavier objects accelerate faster in free fall",
        "believes": (
            "Gravity pulls harder on heavier things, so with no air in the way the heavier "
            "object must speed up faster and land first."
        ),
        "physics": (
            "Gravity does pull harder on a heavier object (F = m·g) — but that object also "
            "has more inertia to overcome. The two effects cancel exactly: a = F/m = g for "
            "everything. In a vacuum a hammer and a feather hit the ground together, as the "
            "Apollo 15 crew showed on the Moon."
        ),
        "description": (
            "heavier things fall faster. the heavier ball hits the ground first because gravity "
            "pulls it harder. more mass means more weight means it drops quicker. the bowling "
            "ball is heavier so it accelerates more. the feather is light so it falls slowly even "
            "with no air. the bigger force on the heavy one makes it speed up more. ten times the "
            "mass means it lands first. weight decides how fast something falls."
        ),
        "confusable_with": ["THIRD_LAW"],
        "simulation": "free_fall",
        "colour": "#15803d",
    },
}

MISCONCEPTION_IDS = list(MISCONCEPTIONS.keys())
NONE_LABEL = "NONE"

# Concept keys for correct reasoning (used by the dataset generator for NONE rows)
CONCEPTS = {
    "accel_is_g_at_rest": "Acceleration stays g even when velocity is momentarily zero",
    "only_gravity": "After release the only force (ignoring air) is gravity",
    "inertia": "No force is needed to keep an object moving at constant velocity",
    "net_force_zero_const_v": "Constant velocity ⇒ net force is zero",
    "const_force_accel": "Constant net force ⇒ constant acceleration, increasing speed",
    "third_law_equal": "Interaction forces are equal and opposite",
    "same_accel_free_fall": "All objects free-fall with the same acceleration g",
}

# ---------------------------------------------------------------------------
# 2. Question bank (30 items)
#    options: key, text, misconceptions (list) – empty list = "no specific misconception"
#    ctx: slot values used by the dataset generator's templates
# ---------------------------------------------------------------------------

QUESTIONS: list[dict] = [
    # ---------------- Kinematics: velocity vs acceleration ----------------
    {
        "id": "Q01", "topic": "kinematics", "concept": "accel_is_g_at_rest",
        "prompt": "A ball is thrown straight up. At the very top of its flight, what is its acceleration? (Ignore air resistance.)",
        "options": [
            {"key": "A", "text": "Zero — it is momentarily at rest", "misconceptions": ["VA_CONFUSION", "IMPETUS"]},
            {"key": "B", "text": "9.8 m/s² downward", "misconceptions": []},
            {"key": "C", "text": "9.8 m/s² upward", "misconceptions": ["IMPETUS"]},
            {"key": "D", "text": "It depends on how hard it was thrown", "misconceptions": ["IMPETUS"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the ball", "moment": "at the top", "agent": "the throw", "surface": "the ground"},
    },
    {
        "id": "Q02", "topic": "kinematics", "concept": "accel_is_g_at_rest",
        "prompt": "A pendulum bob swings to the end of its arc and is momentarily at rest. At that instant its acceleration is…",
        "options": [
            {"key": "A", "text": "Zero, because it has stopped", "misconceptions": ["VA_CONFUSION"]},
            {"key": "B", "text": "Non-zero, directed back along the arc", "misconceptions": []},
            {"key": "C", "text": "Non-zero, directed outward away from the pivot", "misconceptions": []},
            {"key": "D", "text": "Equal to its velocity", "misconceptions": ["VA_CONFUSION"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the bob", "moment": "at the end of the swing", "agent": "the push", "surface": "the floor"},
    },
    {
        "id": "Q03", "topic": "kinematics", "concept": "accel_is_g_at_rest",
        "prompt": "A car brakes and comes to rest at a red light. At the exact instant its speed reaches zero, before it starts moving again, which statement is true?",
        "options": [
            {"key": "A", "text": "Velocity is zero and acceleration is zero", "misconceptions": ["VA_CONFUSION"]},
            {"key": "B", "text": "Velocity is zero but acceleration can be non-zero", "misconceptions": []},
            {"key": "C", "text": "Velocity is non-zero because the car is about to move", "misconceptions": []},
            {"key": "D", "text": "Acceleration is zero because the engine is off", "misconceptions": ["VA_CONFUSION", "IMPETUS"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the car", "moment": "when it stops", "agent": "the engine", "surface": "the road"},
    },
    {
        "id": "Q04", "topic": "kinematics", "concept": "accel_is_g_at_rest",
        "prompt": "A toy cart rolls up a smooth ramp, stops for an instant, then rolls back down. At the turnaround point…",
        "options": [
            {"key": "A", "text": "Both velocity and acceleration are zero", "misconceptions": ["VA_CONFUSION"]},
            {"key": "B", "text": "Velocity is zero; acceleration points down the ramp", "misconceptions": []},
            {"key": "C", "text": "Velocity is zero; acceleration points up the ramp until the push runs out", "misconceptions": ["IMPETUS"]},
            {"key": "D", "text": "Acceleration is zero but velocity is not", "misconceptions": ["VA_CONFUSION"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the cart", "moment": "at the turnaround", "agent": "the push", "surface": "the ramp"},
    },
    {
        "id": "Q05", "topic": "kinematics", "concept": "accel_is_g_at_rest",
        "prompt": "A rock is tossed upward. Compare its acceleration on the way up, at the top, and on the way down (no air).",
        "options": [
            {"key": "A", "text": "Up: 9.8 m/s² down; top: zero; down: 9.8 m/s² down", "misconceptions": ["VA_CONFUSION"]},
            {"key": "B", "text": "The same 9.8 m/s² downward throughout", "misconceptions": []},
            {"key": "C", "text": "Up: upward acceleration; top: zero; down: downward acceleration", "misconceptions": ["IMPETUS", "VA_CONFUSION"]},
            {"key": "D", "text": "Larger on the way down than on the way up", "misconceptions": ["IMPETUS"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the rock", "moment": "at the top", "agent": "the toss", "surface": "the ground"},
    },
    {
        "id": "Q06", "topic": "kinematics", "concept": "accel_is_g_at_rest",
        "prompt": "A bungee jumper reaches the lowest point of the jump and is momentarily motionless. What is true about the jumper's acceleration there?",
        "options": [
            {"key": "A", "text": "It is zero because the jumper is not moving", "misconceptions": ["VA_CONFUSION"]},
            {"key": "B", "text": "It is upward and at its largest value", "misconceptions": []},
            {"key": "C", "text": "It is downward, equal to g", "misconceptions": []},
            {"key": "D", "text": "It equals the velocity, which is zero", "misconceptions": ["VA_CONFUSION"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the jumper", "moment": "at the lowest point", "agent": "the jump", "surface": "the river"},
    },
    # ---------------- Newton's first law / impetus ----------------
    {
        "id": "Q07", "topic": "newton1", "concept": "only_gravity",
        "prompt": "A coin is flicked straight up and is now rising, no longer touching the hand. Ignoring air, what force(s) act on it?",
        "options": [
            {"key": "A", "text": "Gravity only, downward", "misconceptions": []},
            {"key": "B", "text": "Gravity downward plus a decreasing upward force from the flick", "misconceptions": ["IMPETUS"]},
            {"key": "C", "text": "An upward force larger than gravity, since it is going up", "misconceptions": ["IMPETUS", "FORCE_VELOCITY"]},
            {"key": "D", "text": "No forces — it is in free flight", "misconceptions": []},
        ],
        "answer": "A",
        "ctx": {"obj": "the coin", "moment": "while rising", "agent": "the flick", "surface": "the table"},
    },
    {
        "id": "Q08", "topic": "newton1", "concept": "inertia",
        "prompt": "A hockey puck is struck and slides across frictionless ice. Why does it keep moving after the stick has lost contact?",
        "options": [
            {"key": "A", "text": "The force of the hit is still inside the puck, pushing it", "misconceptions": ["IMPETUS"]},
            {"key": "B", "text": "No force is needed — an object in motion stays in motion", "misconceptions": []},
            {"key": "C", "text": "The ice pushes it forward", "misconceptions": ["FORCE_VELOCITY"]},
            {"key": "D", "text": "Its weight pushes it along", "misconceptions": []},
        ],
        "answer": "B",
        "ctx": {"obj": "the puck", "moment": "after the hit", "agent": "the hit", "surface": "the ice"},
    },
    {
        "id": "Q09", "topic": "newton1", "concept": "inertia",
        "prompt": "A ball rolls through a curved tube lying flat on a table and exits the open end. Seen from above, what path does it follow after leaving the tube?",
        "options": [
            {"key": "A", "text": "A straight line", "misconceptions": []},
            {"key": "B", "text": "It keeps curving the same way for a while, then straightens", "misconceptions": ["IMPETUS"]},
            {"key": "C", "text": "It curves the opposite way", "misconceptions": []},
            {"key": "D", "text": "It keeps curving in a full circle", "misconceptions": ["IMPETUS"]},
        ],
        "answer": "A",
        "ctx": {"obj": "the ball", "moment": "after leaving the tube", "agent": "the tube", "surface": "the table"},
    },
    {
        "id": "Q10", "topic": "newton1", "concept": "only_gravity",
        "prompt": "A cannonball is at the highest point of its arc. Ignoring air, which forces act on it there?",
        "options": [
            {"key": "A", "text": "Gravity downward only", "misconceptions": []},
            {"key": "B", "text": "Gravity downward and a forward force from the cannon", "misconceptions": ["IMPETUS"]},
            {"key": "C", "text": "Gravity and an upward force that is just about to run out", "misconceptions": ["IMPETUS"]},
            {"key": "D", "text": "Zero net force, since it is at the top", "misconceptions": ["VA_CONFUSION"]},
        ],
        "answer": "A",
        "ctx": {"obj": "the cannonball", "moment": "at the top of the arc", "agent": "the cannon", "surface": "the ground"},
    },
    {
        "id": "Q11", "topic": "newton1", "concept": "inertia",
        "prompt": "A spacecraft in deep space (no gravity, no drag) switches its engine off. What happens to its motion?",
        "options": [
            {"key": "A", "text": "It gradually slows down and stops", "misconceptions": ["IMPETUS", "FORCE_VELOCITY"]},
            {"key": "B", "text": "It keeps moving at constant velocity", "misconceptions": []},
            {"key": "C", "text": "It stops immediately", "misconceptions": ["FORCE_VELOCITY"]},
            {"key": "D", "text": "It speeds up because nothing holds it back", "misconceptions": []},
        ],
        "answer": "B",
        "ctx": {"obj": "the spacecraft", "moment": "after the engine is off", "agent": "the engine", "surface": "space"},
    },
    {
        "id": "Q12", "topic": "newton1", "concept": "only_gravity",
        "prompt": "Why does a ball thrown upward eventually come back down?",
        "options": [
            {"key": "A", "text": "The throw's force runs out and then gravity takes over", "misconceptions": ["IMPETUS"]},
            {"key": "B", "text": "Gravity acts on it the whole time, so its upward velocity shrinks to zero and then becomes downward", "misconceptions": []},
            {"key": "C", "text": "Air pushes it back down", "misconceptions": []},
            {"key": "D", "text": "The upward force becomes smaller than gravity", "misconceptions": ["IMPETUS"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the ball", "moment": "on the way up", "agent": "the throw", "surface": "the ground"},
    },
    {
        "id": "Q13", "topic": "newton1", "concept": "only_gravity",
        "prompt": "Two identical balls leave a table edge at the same instant: one is dropped, one is thrown horizontally. Ignoring air, which hits the floor first?",
        "options": [
            {"key": "A", "text": "The dropped ball", "misconceptions": ["IMPETUS"]},
            {"key": "B", "text": "Both at the same time", "misconceptions": []},
            {"key": "C", "text": "The thrown ball", "misconceptions": ["FORCE_VELOCITY"]},
            {"key": "D", "text": "It depends on their mass", "misconceptions": ["HEAVIER_FASTER"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the thrown ball", "moment": "in flight", "agent": "the throw", "surface": "the floor"},
    },
    # ---------------- Newton's second law: force & velocity ----------------
    {
        "id": "Q14", "topic": "newton2", "concept": "const_force_accel",
        "prompt": "A box on a frictionless floor is pushed with a constant net force. What happens to its velocity?",
        "options": [
            {"key": "A", "text": "It stays constant", "misconceptions": ["FORCE_VELOCITY"]},
            {"key": "B", "text": "It increases steadily", "misconceptions": []},
            {"key": "C", "text": "It increases then levels off", "misconceptions": ["FORCE_VELOCITY"]},
            {"key": "D", "text": "It decreases", "misconceptions": []},
        ],
        "answer": "B",
        "ctx": {"obj": "the box", "moment": "while being pushed", "agent": "the push", "surface": "the floor"},
    },
    {
        "id": "Q15", "topic": "newton2", "concept": "net_force_zero_const_v",
        "prompt": "A lift (elevator) is moving upward at a steady 2 m/s. What is the net force on it?",
        "options": [
            {"key": "A", "text": "Upward, because it is moving up", "misconceptions": ["FORCE_VELOCITY"]},
            {"key": "B", "text": "Zero", "misconceptions": []},
            {"key": "C", "text": "Downward, because gravity acts", "misconceptions": []},
            {"key": "D", "text": "Upward and equal to its weight", "misconceptions": ["FORCE_VELOCITY"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the lift", "moment": "while moving up", "agent": "the cable", "surface": "the shaft"},
    },
    {
        "id": "Q16", "topic": "newton2", "concept": "net_force_zero_const_v",
        "prompt": "A car cruises along a straight highway at a constant 80 km/h. The net force on the car is…",
        "options": [
            {"key": "A", "text": "Forward, from the engine", "misconceptions": ["FORCE_VELOCITY"]},
            {"key": "B", "text": "Zero", "misconceptions": []},
            {"key": "C", "text": "Backward, from friction", "misconceptions": []},
            {"key": "D", "text": "Forward and proportional to 80 km/h", "misconceptions": ["FORCE_VELOCITY"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the car", "moment": "while cruising", "agent": "the engine", "surface": "the road"},
    },
    {
        "id": "Q17", "topic": "newton2", "concept": "const_force_accel",
        "prompt": "You double the constant force you apply to a trolley on a frictionless track. What happens?",
        "options": [
            {"key": "A", "text": "Its speed instantly doubles and stays there", "misconceptions": ["FORCE_VELOCITY"]},
            {"key": "B", "text": "Its acceleration doubles", "misconceptions": []},
            {"key": "C", "text": "Its mass halves", "misconceptions": []},
            {"key": "D", "text": "Its speed becomes constant at a higher value", "misconceptions": ["FORCE_VELOCITY"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the trolley", "moment": "while pushed", "agent": "the push", "surface": "the track"},
    },
    {
        "id": "Q18", "topic": "newton2", "concept": "net_force_zero_const_v",
        "prompt": "A skydiver has reached terminal velocity and falls at a constant speed. Which is true?",
        "options": [
            {"key": "A", "text": "Gravity is larger than air drag, which is why she keeps falling", "misconceptions": ["FORCE_VELOCITY"]},
            {"key": "B", "text": "Gravity and air drag are equal, so the net force is zero", "misconceptions": []},
            {"key": "C", "text": "Air drag is larger than gravity", "misconceptions": []},
            {"key": "D", "text": "Her acceleration is g", "misconceptions": ["VA_CONFUSION"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the skydiver", "moment": "at terminal velocity", "agent": "gravity", "surface": "the air"},
    },
    {
        "id": "Q19", "topic": "newton2", "concept": "net_force_zero_const_v",
        "prompt": "A crate is dragged across a rough floor at constant velocity by a rope. How does the rope's pull compare with friction?",
        "options": [
            {"key": "A", "text": "Pull is larger than friction — otherwise it would not move", "misconceptions": ["FORCE_VELOCITY"]},
            {"key": "B", "text": "Pull equals friction", "misconceptions": []},
            {"key": "C", "text": "Friction is larger than the pull", "misconceptions": []},
            {"key": "D", "text": "Pull is larger, and the extra force is stored in the crate", "misconceptions": ["IMPETUS", "FORCE_VELOCITY"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the crate", "moment": "while dragged", "agent": "the rope", "surface": "the floor"},
    },
    {
        "id": "Q20", "topic": "newton2", "concept": "const_force_accel",
        "prompt": "A model rocket's engine provides a constant thrust greater than its weight. While the engine burns, the rocket's speed…",
        "options": [
            {"key": "A", "text": "Is constant, matching the constant thrust", "misconceptions": ["FORCE_VELOCITY"]},
            {"key": "B", "text": "Keeps increasing", "misconceptions": []},
            {"key": "C", "text": "Increases only until the thrust is 'used up'", "misconceptions": ["IMPETUS"]},
            {"key": "D", "text": "Is zero until thrust exceeds weight by a lot", "misconceptions": []},
        ],
        "answer": "B",
        "ctx": {"obj": "the rocket", "moment": "while the engine burns", "agent": "the engine", "surface": "the ground"},
    },
    # ---------------- Newton's third law ----------------
    {
        "id": "Q21", "topic": "newton3", "concept": "third_law_equal",
        "prompt": "A large truck collides head-on with a small car. During the collision, how do the forces compare?",
        "options": [
            {"key": "A", "text": "The truck exerts a larger force on the car", "misconceptions": ["THIRD_LAW"]},
            {"key": "B", "text": "The forces are equal in size and opposite in direction", "misconceptions": []},
            {"key": "C", "text": "The car exerts a larger force on the truck", "misconceptions": []},
            {"key": "D", "text": "The truck exerts a force, the car only receives one", "misconceptions": ["THIRD_LAW"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the truck", "other": "the car", "moment": "during the crash", "agent": "the truck", "surface": "the road"},
    },
    {
        "id": "Q22", "topic": "newton3", "concept": "third_law_equal",
        "prompt": "A mosquito splats against the windscreen of a bus moving at 60 km/h. Compare the force of the bus on the mosquito with the force of the mosquito on the bus.",
        "options": [
            {"key": "A", "text": "The bus exerts a much larger force", "misconceptions": ["THIRD_LAW"]},
            {"key": "B", "text": "They are equal", "misconceptions": []},
            {"key": "C", "text": "The mosquito exerts a larger force because it is the one that gets destroyed", "misconceptions": ["THIRD_LAW"]},
            {"key": "D", "text": "The mosquito exerts no force on the bus", "misconceptions": ["THIRD_LAW"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the bus", "other": "the mosquito", "moment": "at impact", "agent": "the bus", "surface": "the windscreen"},
    },
    {
        "id": "Q23", "topic": "newton3", "concept": "third_law_equal",
        "prompt": "The Earth pulls on a falling apple with gravity. How does the apple's pull on the Earth compare?",
        "options": [
            {"key": "A", "text": "The apple pulls much less because it is so small", "misconceptions": ["THIRD_LAW", "HEAVIER_FASTER"]},
            {"key": "B", "text": "The apple pulls with exactly the same force", "misconceptions": []},
            {"key": "C", "text": "The apple does not pull the Earth at all", "misconceptions": ["THIRD_LAW"]},
            {"key": "D", "text": "The apple pulls more because it is the one accelerating", "misconceptions": []},
        ],
        "answer": "B",
        "ctx": {"obj": "the Earth", "other": "the apple", "moment": "while falling", "agent": "the Earth", "surface": "the ground"},
    },
    {
        "id": "Q24", "topic": "newton3", "concept": "third_law_equal",
        "prompt": "You push as hard as you can on a solid wall and it does not move. Which is true?",
        "options": [
            {"key": "A", "text": "The wall pushes back on you with an equal force", "misconceptions": []},
            {"key": "B", "text": "The wall does not push back, which is why it does not move", "misconceptions": ["THIRD_LAW"]},
            {"key": "C", "text": "You push harder than the wall pushes back", "misconceptions": ["THIRD_LAW"]},
            {"key": "D", "text": "The wall pushes back harder, which is why you cannot move it", "misconceptions": ["THIRD_LAW"]},
        ],
        "answer": "A",
        "ctx": {"obj": "the wall", "other": "you", "moment": "while pushing", "agent": "you", "surface": "the floor"},
    },
    {
        "id": "Q25", "topic": "newton3", "concept": "third_law_equal",
        "prompt": "In a tug-of-war, Team A drags Team B across the line. During the pull, compare the force of A on the rope with the force of B on the rope.",
        "options": [
            {"key": "A", "text": "A pulls the rope harder than B", "misconceptions": ["THIRD_LAW"]},
            {"key": "B", "text": "Equal — A wins because of a larger friction force from the ground", "misconceptions": []},
            {"key": "C", "text": "B pulls harder but slips", "misconceptions": []},
            {"key": "D", "text": "A pulls harder because A is heavier", "misconceptions": ["THIRD_LAW", "HEAVIER_FASTER"]},
        ],
        "answer": "B",
        "ctx": {"obj": "Team A", "other": "Team B", "moment": "during the pull", "agent": "Team A", "surface": "the ground"},
    },
    {
        "id": "Q26", "topic": "newton3", "concept": "third_law_equal",
        "prompt": "A fast-moving cyclist bumps into a stationary pedestrian. During the contact…",
        "options": [
            {"key": "A", "text": "The cyclist exerts a larger force because of her speed", "misconceptions": ["THIRD_LAW"]},
            {"key": "B", "text": "The forces on each are equal and opposite", "misconceptions": []},
            {"key": "C", "text": "The pedestrian exerts a larger force because he was still", "misconceptions": []},
            {"key": "D", "text": "The cyclist exerts a larger force because she has more momentum", "misconceptions": ["THIRD_LAW"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the cyclist", "other": "the pedestrian", "moment": "during contact", "agent": "the cyclist", "surface": "the pavement"},
    },
    # ---------------- Free fall ----------------
    {
        "id": "Q27", "topic": "freefall", "concept": "same_accel_free_fall",
        "prompt": "A bowling ball and a tennis ball are dropped from the same height in a vacuum chamber. Which lands first?",
        "options": [
            {"key": "A", "text": "The bowling ball", "misconceptions": ["HEAVIER_FASTER"]},
            {"key": "B", "text": "They land at the same time", "misconceptions": []},
            {"key": "C", "text": "The tennis ball", "misconceptions": []},
            {"key": "D", "text": "The bowling ball, but only by a tiny amount", "misconceptions": ["HEAVIER_FASTER"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the bowling ball", "other": "the tennis ball", "moment": "while falling", "agent": "gravity", "surface": "the floor"},
    },
    {
        "id": "Q28", "topic": "freefall", "concept": "same_accel_free_fall",
        "prompt": "On the Moon an astronaut drops a hammer and a feather together. What happens?",
        "options": [
            {"key": "A", "text": "The hammer lands first", "misconceptions": ["HEAVIER_FASTER"]},
            {"key": "B", "text": "They land together", "misconceptions": []},
            {"key": "C", "text": "The feather floats and never lands", "misconceptions": []},
            {"key": "D", "text": "The feather lands first because it is lighter", "misconceptions": []},
        ],
        "answer": "B",
        "ctx": {"obj": "the hammer", "other": "the feather", "moment": "while falling", "agent": "gravity", "surface": "the lunar surface"},
    },
    {
        "id": "Q29", "topic": "freefall", "concept": "same_accel_free_fall",
        "prompt": "Ball X has twice the mass of ball Y. Both are released from rest (no air). The acceleration of X is…",
        "options": [
            {"key": "A", "text": "Twice that of Y", "misconceptions": ["HEAVIER_FASTER"]},
            {"key": "B", "text": "The same as Y", "misconceptions": []},
            {"key": "C", "text": "Half that of Y", "misconceptions": []},
            {"key": "D", "text": "Larger than Y, because gravity pulls it harder", "misconceptions": ["HEAVIER_FASTER", "THIRD_LAW"]},
        ],
        "answer": "B",
        "ctx": {"obj": "ball X", "other": "ball Y", "moment": "while falling", "agent": "gravity", "surface": "the ground"},
    },
    {
        "id": "Q30", "topic": "freefall", "concept": "same_accel_free_fall",
        "prompt": "A 90 kg adult and a 30 kg child jump off a diving platform at the same moment (ignore air). Who reaches the water first?",
        "options": [
            {"key": "A", "text": "The adult", "misconceptions": ["HEAVIER_FASTER"]},
            {"key": "B", "text": "They reach it together", "misconceptions": []},
            {"key": "C", "text": "The child", "misconceptions": []},
            {"key": "D", "text": "The adult, because the Earth pulls three times harder", "misconceptions": ["HEAVIER_FASTER", "THIRD_LAW"]},
        ],
        "answer": "B",
        "ctx": {"obj": "the adult", "other": "the child", "moment": "while falling", "agent": "gravity", "surface": "the water"},
    },
]

# ---------------------------------------------------------------------------
# 3. Interventions (FR-5)
# ---------------------------------------------------------------------------

INTERVENTIONS: dict[str, dict] = {
    "VA_CONFUSION": {
        "headline": "Velocity says where you are going. Acceleration says how that is changing.",
        "explanation": [
            "Picture the ball's velocity as an arrow. On the way up the arrow points up and shrinks; at the top it has length zero; on the way down it points down and grows. Something is changing that arrow the whole time — and the thing that changes velocity is acceleration.",
            "Gravity does not switch off at the top. It pulls down at every instant, so the acceleration is 9.8 m/s² downward at every instant, including the one where the velocity happens to be zero.",
            "Rule of thumb: zero velocity tells you nothing about acceleration. Ask instead 'is the velocity about to change?' If yes, acceleration is not zero.",
        ],
        "worked_example": {
            "title": "A ball thrown up at 10 m/s",
            "steps": [
                "t = 0 s: v = +10 m/s (up). a = −9.8 m/s².",
                "t = 0.5 s: v = 10 − 9.8·0.5 = +5.1 m/s. a = −9.8 m/s².",
                "t ≈ 1.02 s: v = 0 (the top). a = −9.8 m/s² — unchanged.",
                "t = 1.5 s: v = 10 − 9.8·1.5 = −4.7 m/s (down). a = −9.8 m/s².",
                "The velocity passes through zero; the acceleration never does.",
            ],
        },
        "check_yourself": "Can something be at rest and accelerating at the same time? (Yes — any turnaround point.)",
        "simulation": "throw_up",
    },
    "IMPETUS": {
        "headline": "A force acts only while something is pushing. Nothing is stored in the ball.",
        "explanation": [
            "While your hand is in contact with the ball, your hand pushes it. The instant it leaves your hand, that push is over — there is no 'throw force' travelling inside the ball.",
            "So why does the ball keep rising? Not because of a force, but because of inertia: objects keep their velocity unless a force changes it (Newton's first law). The only force left is gravity, which is what reduces the upward velocity, stops it, and reverses it.",
            "Test: draw the forces on the ball a moment after release. If you drew an arrow for 'the throw', ask what object is applying it right now. No object → no force.",
        ],
        "worked_example": {
            "title": "Free-body diagram of a thrown ball",
            "steps": [
                "List every object touching the ball after release: none (ignoring air).",
                "List non-contact forces: gravity from the Earth, mg downward.",
                "Net force = mg downward ⇒ acceleration = g downward on the way up, at the top, and on the way down.",
                "The ball slows because the net force points opposite to its velocity, not because a stored force is fading.",
            ],
        },
        "check_yourself": "A puck on frictionless ice keeps gliding forever. What force keeps it going? (None — no force is needed.)",
        "simulation": "forces_in_flight",
    },
    "FORCE_VELOCITY": {
        "headline": "Force changes velocity. It does not set velocity.",
        "explanation": [
            "Newton's second law is F_net = m·a. The quantity on the right is acceleration — the rate of change of velocity. A steady net force means velocity keeps changing at a steady rate; it does not mean a steady velocity.",
            "Constant velocity is the signature of zero net force. A car cruising at 80 km/h has an engine force, yes — but it is exactly balanced by drag and friction, so the net force is zero.",
            "If something moves at constant speed and you can see a forward force, look for the equal backward force. It is always there.",
        ],
        "worked_example": {
            "title": "A 2 kg box, 4 N net force, frictionless floor",
            "steps": [
                "a = F/m = 4 / 2 = 2 m/s², constant.",
                "After 1 s: v = 2 m/s. After 2 s: v = 4 m/s. After 3 s: v = 6 m/s.",
                "The force never changed; the velocity never stopped growing.",
                "To hold v fixed at 6 m/s you would have to reduce the net force to zero.",
            ],
        },
        "check_yourself": "A lift rises at a steady 2 m/s. What is the net force on it? (Zero.)",
        "simulation": "constant_force",
    },
    "THIRD_LAW": {
        "headline": "Forces come in equal pairs. The effects do not.",
        "explanation": [
            "Whenever object A pushes on object B, B pushes back on A with exactly the same force, in the opposite direction. It does not matter which one is heavier, faster or 'winning'. This is Newton's third law and there are no exceptions.",
            "What differs is the outcome. The same force on a mosquito and on a bus produces a huge acceleration for the mosquito (a = F/m with tiny m) and an unmeasurable one for the bus.",
            "The damage you see tells you about mass and acceleration, not about which force was bigger.",
        ],
        "worked_example": {
            "title": "Truck (4000 kg) hits car (1000 kg), contact force 40 000 N",
            "steps": [
                "Force on car from truck: 40 000 N. Force on truck from car: 40 000 N (third law).",
                "Car acceleration: 40 000 / 1000 = 40 m/s².",
                "Truck acceleration: 40 000 / 4000 = 10 m/s².",
                "Equal forces, four-times-different accelerations — that is why the car is wrecked.",
            ],
        },
        "check_yourself": "You push a wall and nothing moves. How hard does the wall push you? (Exactly as hard as you push it.)",
        "simulation": "collision",
    },
    "HEAVIER_FASTER": {
        "headline": "Heavier objects are pulled harder — and are harder to get moving. It cancels exactly.",
        "explanation": [
            "Gravity really does pull harder on a bowling ball than on a tennis ball: the force is m·g, so ten times the mass means ten times the force.",
            "But acceleration is force divided by mass (a = F/m). Ten times the force divided by ten times the mass is the same acceleration: g. Every object in free fall accelerates at 9.8 m/s².",
            "In everyday life a feather falls slowly only because air drag matters a lot for a light, wide object. Remove the air and it drops like the hammer — as filmed on the Moon in 1971.",
        ],
        "worked_example": {
            "title": "Bowling ball (7 kg) vs tennis ball (0.06 kg)",
            "steps": [
                "Force on bowling ball: 7 × 9.8 = 68.6 N. Acceleration: 68.6 / 7 = 9.8 m/s².",
                "Force on tennis ball: 0.06 × 9.8 = 0.59 N. Acceleration: 0.59 / 0.06 = 9.8 m/s².",
                "Both fall 5 m in √(2·5/9.8) ≈ 1.01 s.",
                "Different forces, identical accelerations, same landing time.",
            ],
        },
        "check_yourself": "If mass doubles, what happens to the gravitational force, and to the acceleration? (Force doubles; acceleration unchanged.)",
        "simulation": "free_fall",
    },
}

# ---------------------------------------------------------------------------
# 4. Transfer probes (FR-6 / FR-7) – new contexts, same idea
#    Each misconception has 3 probes; probe wrong options are mapped like questions.
# ---------------------------------------------------------------------------

PROBES: dict[str, list[dict]] = {
    "VA_CONFUSION": [
        {
            "id": "P_VA_1", "context": "A pendulum",
            "prompt": "A child on a swing reaches the highest point of the swing and pauses for an instant. What is the child's acceleration at that moment?",
            "options": [
                {"key": "A", "text": "Zero, since the child is momentarily still", "misconceptions": ["VA_CONFUSION"]},
                {"key": "B", "text": "Non-zero, directed back toward the bottom of the swing", "misconceptions": []},
                {"key": "C", "text": "Equal to the velocity", "misconceptions": ["VA_CONFUSION"]},
                {"key": "D", "text": "Non-zero, directed upward away from the ground", "misconceptions": []},
            ],
            "answer": "B",
            "ctx": {"obj": "the child", "moment": "at the top of the swing", "agent": "the push", "surface": "the ground"},
        },
        {
            "id": "P_VA_2", "context": "A spring",
            "prompt": "A mass on a spring bounces up and down. At the lowest point it is momentarily at rest. Its acceleration there is…",
            "options": [
                {"key": "A", "text": "Zero", "misconceptions": ["VA_CONFUSION"]},
                {"key": "B", "text": "Maximum, pointing upward", "misconceptions": []},
                {"key": "C", "text": "Maximum, pointing downward", "misconceptions": []},
                {"key": "D", "text": "The same as its velocity, i.e. zero", "misconceptions": ["VA_CONFUSION"]},
            ],
            "answer": "B",
            "ctx": {"obj": "the mass", "moment": "at the lowest point", "agent": "the spring", "surface": "the floor"},
        },
        {
            "id": "P_VA_3", "context": "A bouncing ball",
            "prompt": "A rubber ball hits a hard floor and, at the instant of maximum squash, is momentarily motionless. Which is true at that instant?",
            "options": [
                {"key": "A", "text": "Velocity zero, acceleration zero", "misconceptions": ["VA_CONFUSION"]},
                {"key": "B", "text": "Velocity zero, large upward acceleration", "misconceptions": []},
                {"key": "C", "text": "Velocity zero, acceleration g downward", "misconceptions": []},
                {"key": "D", "text": "Velocity non-zero because it is about to bounce", "misconceptions": []},
            ],
            "answer": "B",
            "ctx": {"obj": "the ball", "moment": "at maximum squash", "agent": "the floor", "surface": "the floor"},
        },
    ],
    "IMPETUS": [
        {
            "id": "P_IM_1", "context": "A bowling ball on ice",
            "prompt": "A bowling ball rolls across perfectly smooth ice after being released. Which forces act on it horizontally?",
            "options": [
                {"key": "A", "text": "A forward force from the bowler that gradually dies away", "misconceptions": ["IMPETUS"]},
                {"key": "B", "text": "No horizontal force at all", "misconceptions": []},
                {"key": "C", "text": "A constant forward force equal to its weight", "misconceptions": ["FORCE_VELOCITY"]},
                {"key": "D", "text": "A forward force from the ice", "misconceptions": ["FORCE_VELOCITY"]},
            ],
            "answer": "B",
            "ctx": {"obj": "the bowling ball", "moment": "after release", "agent": "the bowler", "surface": "the ice"},
        },
        {
            "id": "P_IM_2", "context": "A satellite",
            "prompt": "A satellite coasts in orbit with its thrusters off. Why does it not slow down?",
            "options": [
                {"key": "A", "text": "The launch rocket's force is still carried by it", "misconceptions": ["IMPETUS"]},
                {"key": "B", "text": "No force opposes its motion, so its speed stays the same", "misconceptions": []},
                {"key": "C", "text": "Gravity pushes it forward along the orbit", "misconceptions": ["FORCE_VELOCITY"]},
                {"key": "D", "text": "It does slow down, very gradually, as the launch force fades", "misconceptions": ["IMPETUS"]},
            ],
            "answer": "B",
            "ctx": {"obj": "the satellite", "moment": "in orbit", "agent": "the rocket", "surface": "space"},
        },
        {
            "id": "P_IM_3", "context": "A kicked football",
            "prompt": "A football has just been kicked and is rising through the air. Ignoring air, what force(s) act on it?",
            "options": [
                {"key": "A", "text": "Gravity only", "misconceptions": []},
                {"key": "B", "text": "Gravity plus the force of the kick, which is fading", "misconceptions": ["IMPETUS"]},
                {"key": "C", "text": "The force of the kick only, until it runs out", "misconceptions": ["IMPETUS"]},
                {"key": "D", "text": "An upward force larger than gravity", "misconceptions": ["IMPETUS", "FORCE_VELOCITY"]},
            ],
            "answer": "A",
            "ctx": {"obj": "the football", "moment": "while rising", "agent": "the kick", "surface": "the pitch"},
        },
    ],
    "FORCE_VELOCITY": [
        {
            "id": "P_FV_1", "context": "A cyclist",
            "prompt": "A cyclist pedals along a flat road at a constant 20 km/h. The net force on the bicycle is…",
            "options": [
                {"key": "A", "text": "Forward, from the pedalling", "misconceptions": ["FORCE_VELOCITY"]},
                {"key": "B", "text": "Zero", "misconceptions": []},
                {"key": "C", "text": "Backward, from air resistance", "misconceptions": []},
                {"key": "D", "text": "Forward, and larger the faster she goes", "misconceptions": ["FORCE_VELOCITY"]},
            ],
            "answer": "B",
            "ctx": {"obj": "the bicycle", "moment": "while pedalling", "agent": "the pedalling", "surface": "the road"},
        },
        {
            "id": "P_FV_2", "context": "A sled",
            "prompt": "A sled on frictionless ice is pulled with a constant 10 N force for 5 seconds. During those 5 seconds its speed…",
            "options": [
                {"key": "A", "text": "Jumps to one value and stays there", "misconceptions": ["FORCE_VELOCITY"]},
                {"key": "B", "text": "Increases steadily the whole time", "misconceptions": []},
                {"key": "C", "text": "Increases, then becomes constant once the force 'settles in'", "misconceptions": ["FORCE_VELOCITY"]},
                {"key": "D", "text": "Stays zero because 10 N is small", "misconceptions": []},
            ],
            "answer": "B",
            "ctx": {"obj": "the sled", "moment": "while pulled", "agent": "the pull", "surface": "the ice"},
        },
        {
            "id": "P_FV_3", "context": "A parachutist",
            "prompt": "A parachutist descends at a steady 5 m/s. Compare the upward drag force with her weight.",
            "options": [
                {"key": "A", "text": "Weight is larger, which is why she is moving down", "misconceptions": ["FORCE_VELOCITY"]},
                {"key": "B", "text": "They are equal", "misconceptions": []},
                {"key": "C", "text": "Drag is larger", "misconceptions": []},
                {"key": "D", "text": "Weight is larger and the difference sets her speed", "misconceptions": ["FORCE_VELOCITY"]},
            ],
            "answer": "B",
            "ctx": {"obj": "the parachutist", "moment": "while descending", "agent": "gravity", "surface": "the air"},
        },
    ],
    "THIRD_LAW": [
        {
            "id": "P_TL_1", "context": "A mosquito and a truck",
            "prompt": "A mosquito flies into the front of a moving truck. During the impact, how do the forces compare?",
            "options": [
                {"key": "A", "text": "The truck's force on the mosquito is far larger", "misconceptions": ["THIRD_LAW"]},
                {"key": "B", "text": "The forces are equal and opposite", "misconceptions": []},
                {"key": "C", "text": "Only the truck exerts a force", "misconceptions": ["THIRD_LAW"]},
                {"key": "D", "text": "The mosquito's force is larger because it is the one destroyed", "misconceptions": ["THIRD_LAW"]},
            ],
            "answer": "B",
            "ctx": {"obj": "the truck", "other": "the mosquito", "moment": "at impact", "agent": "the truck", "surface": "the road"},
        },
        {
            "id": "P_TL_2", "context": "A rocket in space",
            "prompt": "An astronaut (80 kg) floating in space pushes off a 400 kg satellite. Compare the force on the astronaut with the force on the satellite.",
            "options": [
                {"key": "A", "text": "The satellite experiences more force because it is heavier", "misconceptions": ["THIRD_LAW", "HEAVIER_FASTER"]},
                {"key": "B", "text": "The forces are equal; the astronaut accelerates five times more", "misconceptions": []},
                {"key": "C", "text": "The astronaut experiences more force because she did the pushing", "misconceptions": ["THIRD_LAW"]},
                {"key": "D", "text": "Only the astronaut feels a force, since the satellite barely moves", "misconceptions": ["THIRD_LAW"]},
            ],
            "answer": "B",
            "ctx": {"obj": "the astronaut", "other": "the satellite", "moment": "during the push", "agent": "the astronaut", "surface": "space"},
        },
        {
            "id": "P_TL_3", "context": "A book on a table",
            "prompt": "A heavy book rests on a table. The Earth pulls the book down with 20 N. How hard does the book pull the Earth up?",
            "options": [
                {"key": "A", "text": "Much less than 20 N — the Earth is enormous", "misconceptions": ["THIRD_LAW", "HEAVIER_FASTER"]},
                {"key": "B", "text": "Exactly 20 N", "misconceptions": []},
                {"key": "C", "text": "Zero — the book is not moving", "misconceptions": ["THIRD_LAW"]},
                {"key": "D", "text": "20 N, but only while the book is falling", "misconceptions": ["THIRD_LAW"]},
            ],
            "answer": "B",
            "ctx": {"obj": "the Earth", "other": "the book", "moment": "at rest", "agent": "the Earth", "surface": "the table"},
        },
    ],
    "HEAVIER_FASTER": [
        {
            "id": "P_HF_1", "context": "Coins in a vacuum tube",
            "prompt": "A 1-rupee coin and a 10-rupee coin (much heavier) are released together inside an evacuated tube. Which reaches the bottom first?",
            "options": [
                {"key": "A", "text": "The 10-rupee coin", "misconceptions": ["HEAVIER_FASTER"]},
                {"key": "B", "text": "Both at the same time", "misconceptions": []},
                {"key": "C", "text": "The 1-rupee coin", "misconceptions": []},
                {"key": "D", "text": "The 10-rupee coin, but only slightly", "misconceptions": ["HEAVIER_FASTER"]},
            ],
            "answer": "B",
            "ctx": {"obj": "the 10-rupee coin", "other": "the 1-rupee coin", "moment": "while falling", "agent": "gravity", "surface": "the bottom"},
        },
        {
            "id": "P_HF_2", "context": "Lorry vs scooter off a cliff",
            "prompt": "A lorry and a scooter drive off a cliff edge at the same speed, side by side (ignore air). Which hits the ground first?",
            "options": [
                {"key": "A", "text": "The lorry", "misconceptions": ["HEAVIER_FASTER"]},
                {"key": "B", "text": "They hit at the same time", "misconceptions": []},
                {"key": "C", "text": "The scooter", "misconceptions": []},
                {"key": "D", "text": "The lorry, because gravity's pull on it is stronger", "misconceptions": ["HEAVIER_FASTER", "THIRD_LAW"]},
            ],
            "answer": "B",
            "ctx": {"obj": "the lorry", "other": "the scooter", "moment": "while falling", "agent": "gravity", "surface": "the ground"},
        },
        {
            "id": "P_HF_3", "context": "Two stones in a well",
            "prompt": "A 5 kg stone and a 1 kg stone are dropped into a deep well together. Compare their accelerations (ignore air).",
            "options": [
                {"key": "A", "text": "The 5 kg stone accelerates five times faster", "misconceptions": ["HEAVIER_FASTER"]},
                {"key": "B", "text": "Both accelerate at g", "misconceptions": []},
                {"key": "C", "text": "The 1 kg stone accelerates faster", "misconceptions": []},
                {"key": "D", "text": "The 5 kg stone accelerates faster because the pull on it is bigger", "misconceptions": ["HEAVIER_FASTER", "THIRD_LAW"]},
            ],
            "answer": "B",
            "ctx": {"obj": "the 5 kg stone", "other": "the 1 kg stone", "moment": "while falling", "agent": "gravity", "surface": "the water"},
        },
    ],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

QUESTION_INDEX: dict[str, dict] = {q["id"]: q for q in QUESTIONS}
PROBE_INDEX: dict[str, dict] = {p["id"]: p for plist in PROBES.values() for p in plist}
ITEM_INDEX: dict[str, dict] = {**QUESTION_INDEX, **PROBE_INDEX}

# Sentence starters shown in the UI to reduce vague explanations (risk mitigation)
SENTENCE_STARTERS = [
    "I chose this because…",
    "The force(s) acting here are…",
    "At that moment the velocity is… and the acceleration is…",
    "The heavier/faster object…",
]


def public_item(item: dict) -> dict:
    """Strip the answer key and misconception maps before sending to the browser (privacy NFR)."""
    return {
        "id": item["id"],
        "topic": item.get("topic", "transfer"),
        "context": item.get("context"),
        "prompt": item["prompt"],
        "options": [{"key": o["key"], "text": o["text"]} for o in item["options"]],
    }


def option_of(item: dict, key: str) -> dict | None:
    for o in item["options"]:
        if o["key"] == key:
            return o
    return None


def all_misconceptions_for_item(item: dict) -> list[str]:
    seen: list[str] = []
    for o in item["options"]:
        for m in o["misconceptions"]:
            if m not in seen:
                seen.append(m)
    return seen
