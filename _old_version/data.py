MISCONCEPTIONS = {
    "VA_CONFUSION": {
        "name": "Velocity–acceleration confusion",
        "desc": "Thinks zero velocity means zero acceleration.",
        "keywords": ["velocity is zero", "speed is zero", "not moving", "stops", "at rest", "stationary", "no velocity"],
    },
    "IMPETUS": {
        "name": "Impetus: motion carries a force",
        "desc": "Thinks a moving object carries a force that keeps it moving until it runs out.",
        "keywords": ["force of the throw", "throw force", "upward force", "runs out", "keeps it moving",
                     "force from the hand", "needs a force", "pushing it", "force is used up"],
    },
    "FORCE_VELOCITY": {
        "name": "Force causes constant speed",
        "desc": "Thinks a constant net force produces a constant speed.",
        "keywords": ["constant speed", "steady speed", "same speed", "constant velocity", "levels off", "proportional to speed"],
    },
    "THIRD_LAW": {
        "name": "Unequal action–reaction",
        "desc": "Thinks the heavier or faster object exerts the bigger force.",
        "keywords": ["heavier", "bigger", "more mass", "stronger", "faster", "more momentum"],
    },
    "HEAVIER_FASTER": {
        "name": "Heavier objects fall faster",
        "desc": "Thinks heavier objects accelerate faster in free fall.",
        "keywords": ["heavier", "more weight", "more mass", "pulled more", "more gravity"],
    },
}

# option_map: wrong option -> misconceptions that could produce it (several = needs the explanation to tell apart)
# hidden: misconceptions that can still show up in the explanation when the answer is correct
QUESTIONS = [
    {"id": "q1", "topic": "Kinematics",
     "text": "A ball is thrown straight up. At the very top of its path, what is its acceleration?",
     "options": {"A": "Zero", "B": "9.8 m/s² downward", "C": "9.8 m/s² upward", "D": "It depends on the ball's mass"},
     "correct": "B",
     "option_map": {"A": ["VA_CONFUSION", "IMPETUS"], "C": ["IMPETUS"], "D": ["HEAVIER_FASTER"]},
     "hidden": ["VA_CONFUSION", "IMPETUS"]},
    {"id": "q2", "topic": "Newton's third law",
     "text": "A heavy truck crashes into a small car. During the collision, how do the forces compare?",
     "options": {"A": "Truck pushes harder on the car", "B": "Both forces are equal",
                 "C": "Car pushes harder on the truck", "D": "Only the truck exerts a force"},
     "correct": "B",
     "option_map": {"A": ["THIRD_LAW"], "C": ["THIRD_LAW"], "D": ["THIRD_LAW"]},
     "hidden": ["THIRD_LAW"]},
    {"id": "q3", "topic": "Newton's first law",
     "text": "A hockey puck slides across frictionless ice at constant velocity. Which horizontal forces act on it?",
     "options": {"A": "A forward force that keeps it moving", "B": "No horizontal force",
                 "C": "A forward force that slowly runs out", "D": "A forward force slightly bigger than a backward one"},
     "correct": "B",
     "option_map": {"A": ["IMPETUS"], "C": ["IMPETUS"], "D": ["IMPETUS", "FORCE_VELOCITY"]},
     "hidden": ["IMPETUS"]},
    {"id": "q4", "topic": "Free fall",
     "text": "A 1 kg ball and a 10 kg ball are dropped together in a vacuum. Which lands first?",
     "options": {"A": "The 10 kg ball", "B": "They land together", "C": "The 1 kg ball"},
     "correct": "B",
     "option_map": {"A": ["HEAVIER_FASTER"], "C": []},
     "hidden": ["HEAVIER_FASTER"]},
    {"id": "q5", "topic": "Newton's second law",
     "text": "A constant horizontal force pushes a box across a frictionless floor. How does its speed change?",
     "options": {"A": "Stays constant", "B": "Increases steadily", "C": "Increases, then levels off", "D": "Decreases"},
     "correct": "B",
     "option_map": {"A": ["FORCE_VELOCITY"], "C": ["FORCE_VELOCITY", "IMPETUS"], "D": []},
     "hidden": ["FORCE_VELOCITY"]},
]

# Transfer questions: same idea, new situation. Used to check the misconception is actually gone.
REASSESS = {
    "VA_CONFUSION": {"id": "r_va", "topic": "Recheck",
        "text": "A pendulum bob stops for an instant at the end of its swing. Is its acceleration zero at that instant?",
        "options": {"A": "Yes, it isn't moving", "B": "No, it is still accelerating", "C": "Only if the bob is light"},
        "correct": "B", "option_map": {"A": ["VA_CONFUSION"], "C": []}, "hidden": ["VA_CONFUSION"]},
    "IMPETUS": {"id": "r_imp", "topic": "Recheck",
        "text": "A spacecraft in deep space (no gravity, no air) switches off its engine while moving. What happens?",
        "options": {"A": "It slows down and stops", "B": "It keeps moving at the same velocity", "C": "It speeds up"},
        "correct": "B", "option_map": {"A": ["IMPETUS"], "C": []}, "hidden": ["IMPETUS"]},
    "FORCE_VELOCITY": {"id": "r_fv", "topic": "Recheck",
        "text": "A cart on a frictionless track is pulled by a constant 2 N force for 5 s. What does its speed–time graph look like?",
        "options": {"A": "A flat line", "B": "A straight line going up", "C": "Rises, then goes flat"},
        "correct": "B", "option_map": {"A": ["FORCE_VELOCITY"], "C": ["FORCE_VELOCITY"]}, "hidden": ["FORCE_VELOCITY"]},
    "THIRD_LAW": {"id": "r_3l", "topic": "Recheck",
        "text": "A mosquito hits the windscreen of a moving bus. How do the forces compare?",
        "options": {"A": "Bus on mosquito is larger", "B": "They are equal", "C": "Mosquito on bus is larger"},
        "correct": "B", "option_map": {"A": ["THIRD_LAW"], "C": ["THIRD_LAW"]}, "hidden": ["THIRD_LAW"]},
    "HEAVIER_FASTER": {"id": "r_hf", "topic": "Recheck",
        "text": "On the Moon (no air), an astronaut drops a hammer and a feather together. What happens?",
        "options": {"A": "The hammer lands first", "B": "They land together", "C": "The feather lands first"},
        "correct": "B", "option_map": {"A": ["HEAVIER_FASTER"], "C": []}, "hidden": ["HEAVIER_FASTER"]},
}

INTERVENTIONS = {
    "VA_CONFUSION": {
        "explain": "Acceleration is how fast velocity is changing, not how big velocity is. At the top, velocity passes through zero while still changing: +2 m/s, then 0, then −2 m/s. Gravity never switches off, so acceleration stays 9.8 m/s² downward.",
        "example": "If acceleration really were zero at the top, velocity would stop changing and the ball would hang in the air forever."},
    "IMPETUS": {
        "explain": "Objects don't store a force that keeps them moving. Once something leaves your hand, only the forces acting on it right now matter, like gravity or friction. With no net force, a moving object keeps its velocity.",
        "example": "A puck on an air-hockey table glides at nearly steady speed with nothing pushing it. It only slows down because of friction, which is a real force."},
    "FORCE_VELOCITY": {
        "explain": "Net force sets acceleration (F = ma), not speed. A constant net force means the speed keeps rising at a constant rate.",
        "example": "2 N on a 1 kg cart: 2 m/s after 1 s, 4 m/s after 2 s, 6 m/s after 3 s. The speed never levels off while the force acts."},
    "THIRD_LAW": {
        "explain": "Forces come in pairs. When A pushes B, B pushes A back with exactly the same size of force. Mass decides how much each object accelerates, not how big the force is.",
        "example": "Truck and car feel equal forces. The car's smaller mass gives it a much bigger acceleration (a = F/m), which is why it gets damaged more."},
    "HEAVIER_FASTER": {
        "explain": "Gravity pulls a heavier object harder, but it is also harder to accelerate by exactly the same factor. Weight ÷ mass = g for every object, so without air everything falls together.",
        "example": "10 kg feels 98 N, 1 kg feels 9.8 N. Divide by mass: both get 9.8 m/s²."},
}

ALL = {q["id"]: q for q in QUESTIONS + list(REASSESS.values())}
