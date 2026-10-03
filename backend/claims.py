"""
Claim bank: things learners actually say, with a verdict and a reply to THAT claim.

The tutor reply is built by finding every claim in the learner's own sentence and answering
each one in the order they said it — so the response is about their understanding, not a
template about the topic.

Each entry: (regex, verdict, reply, misconceptions_it_signals)
    verdict: "true"   – correct physics, credit it
             "partly" – true fact, wrong conclusion drawn from it
             "false"  – the misconceived step
"""

from __future__ import annotations

import re

CLAIMS: list[tuple[str, str, str, list[str]]] = [
    # ---------------- velocity / acceleration at a turnaround ----------------
    (r"\b(velocity|speed)\s*(is|=|equals|becomes|reaches)\s*(zero|0|nothing)\b|\bzero (velocity|speed)\b|\bv\s*=\s*0\b",
     "partly", "the velocity really is zero for that instant — that part is correct", ["VA_CONFUSION"]),
    (r"\b(it|the \w+)\s+(stops|stopped|is stopped|comes to rest|is at rest|is stationary|is not moving|isn'?t moving|pauses|hangs|freezes)\b|\bis still(?=\s*($|[.,;]|at the|there|for a))",
     "partly", "yes, it is momentarily at rest — true", ["VA_CONFUSION"]),
    (r"\b(acceleration|accel\w*)\s*(is|=|must be|has to be|should be|would be|equals|becomes)\s*(also\s+)?(zero|0|nothing|nil)\b|\bno acceleration\b|\bnot accelerating\b|\bzero acceleration\b|\ba\s*=\s*0\b",
     "false", "this is the step that breaks: acceleration is not 'how fast it moves' but 'how fast the velocity is changing'. At that instant the velocity is changing from upward to downward — so the acceleration is a full 9.8 m/s² downward even though the speed is zero", ["VA_CONFUSION"]),
    (r"\bnothing (is )?(happening|changing|acting)\b|\bnothing (acts|is acting) on it\b|\bno force(s)? (act|acts|acting|on it)\b",
     "false", "something is acting: gravity never switches off. That is exactly why it starts falling a moment later", ["VA_CONFUSION", "IMPETUS"]),
    (r"\b(velocity|speed) (is )?(changing|about to change|reversing|turning around|going from up to down)\b|\bchang(es|ing) direction\b",
     "true", "right — the velocity is changing, and that change is what acceleration measures", []),
    (r"\bgravity (still|always|never stops|keeps|continues|is still)\b.{0,20}(act|pull|work|on)\b|\bgravity (does ?n'?t|never) (stop|switch|turn) off\b|\bgravity acts (the whole time|at every instant|all the time)\b",
     "true", "exactly — gravity acts at every instant, including the one where the ball is still", []),
    (r"\b9\.8\b.{0,20}\b(down|downward|throughout|whole time|always)\b|\b(a|acceleration)\s*(=|is)\s*(-?\s*g|-?\s*9\.8)\b",
     "true", "correct — the acceleration stays 9.8 m/s² downward throughout the flight", []),
    (r"\bacceleration (is )?(the )?(rate|change)\b|\brate of change of velocity\b|\bhow (fast|quickly) (the )?velocity changes\b",
     "true", "that definition is the key: acceleration is the rate of change of velocity, not the velocity itself", []),
    # ---------------- impetus ----------------
    (r"\b(throw|throwing|hand|hit|kick|flick|launch|push|cannon|engine|bowler)('?s)?\s+force\b|\bforce (of|from) the (throw|hand|hit|kick|flick|launch|push|cannon|engine|bowler)\b",
     "false", "here is the problem: a 'throw force' needs the hand to be touching the ball. After release no object is pushing it, so that force does not exist any more", ["IMPETUS"]),
    (r"\b(runs?|ran|running|wears?|wearing|dies?|dying|fades?|fading|used up|exhaust\w*|gets? weaker|decreas\w+)\s*(out|off|away|down)?\b.{0,30}\b(force|push|energy|impetus)\b|\b(force|push|energy)\b.{0,60}\b(runs?|ran|wears?|dies?|fades?|is used up|gets? weaker|weaker)\s*(out|off|away|down)?\b",
     "false", "a force cannot run out, because it was never stored inside the ball. What is really happening is that gravity keeps subtracting from the upward velocity until it reaches zero", ["IMPETUS"]),
    (r"\b(still|carries|carrying|carried|holds?|keeps?|inside|in it|with it|left ?over|stored|transferred|given to it)\b.{0,25}\b(force|push|momentum of the throw|energy of the throw)\b|\b(force|push)\b.{0,40}\b(still (in|inside|with) (it|the \w+)|carried|stored|left ?over|inside (it|the \w+))\b|\b(gave|gives|given|puts?|transfer\w*)\s+(it|the \w+)?\s*(a|some|its)?\s*(force|push|energy)\b",
     "false", "nothing travels inside the ball. Draw the forces a moment after release and the only arrow you can justify is gravity — the ball keeps rising because of inertia, not a push", ["IMPETUS"]),
    (r"\b(slows? down|slowing down|is slowing|decelerat\w+|loses? speed|losing speed)\b",
     "partly", "true, it is slowing down on the way up — but the reason is gravity acting against the motion, not a push fading", ["IMPETUS"]),
    (r"\b(gravity|weight) (takes over|wins|becomes (bigger|stronger|more)|overcomes|is (bigger|stronger|more) than)\b",
     "false", "gravity never has to 'take over' — it was the only force the whole time; there was nothing competing with it", ["IMPETUS"]),
    (r"\bonly (force|thing)( acting| on it)? is gravity\b|\bgravity (is )?the only force\b|\b(just|only) gravity\b|\bnothing (else )?(is )?(touching|pushing) it\b|\bno(thing)? (is )?(pushing|touching) it\b",
     "true", "correct — after release the only force is gravity", []),
    (r"\binertia\b|\bfirst law\b|\bkeeps? (on )?(moving|going) (because|since|as) (nothing|no force)|\bno (net )?force (is )?(needed|required)\b|\bobjects? in motion stay(s)? in motion\b",
     "true", "right — no force is needed to keep it moving; that is inertia (Newton's first law)", []),
    (r"\b(needs?|requires?|must have|has to have)\s+(a\s+)?(net\s+)?force\s+to\s+(keep|stay|carry on|continue)\s+(moving|going)\b|\bsomething (must|has to) (be )?push(ing)? it\b",
     "false", "this is the idea to drop: no force is needed to keep something moving. A force is needed to change motion, not to maintain it", ["FORCE_VELOCITY", "IMPETUS"]),
    # ---------------- force vs velocity ----------------
    (r"\bconstant (net )?(force|push)\b.{0,40}\bconstant (speed|velocity)\b|\bconstant (speed|velocity)\b.{0,40}\bconstant (net )?(force|push)\b|\bsteady (force|push)\b.{0,30}\bsteady (speed|velocity)\b",
     "false", "swap one word and it becomes true: a constant force gives constant *acceleration*. The velocity then keeps growing for as long as the force acts", ["FORCE_VELOCITY"]),
    (r"\b(net )?force (is|must be|has to be|points?|acts?)\s+(forward|forwards|in the direction (of|it is) (motion|moving|travel)|the way it('s| is) (going|moving))\b|\bforward (net )?force\b.{0,30}\b(because|since|as) it('s| is) moving\b",
     "false", "direction of motion and direction of net force are different things. At steady speed the forward push is exactly cancelled, so the net force is zero", ["FORCE_VELOCITY"]),
    (r"\b(engine|pedal\w*|pull|push|forward force|thrust)\b.{0,30}\b(bigger|larger|greater|more|stronger) than\b.{0,30}\b(friction|drag|air|resistance|backward)\b|\b(bigger|larger|greater|more) force forward\b",
     "false", "if the forward force were larger than the backward ones the car would be speeding up. Steady speed means they are exactly equal", ["FORCE_VELOCITY"]),
    (r"\b(double|twice|two times)\b.{0,20}\b(force|push)\b.{0,30}\b(double|twice|two times)\b.{0,20}\b(speed|velocity)\b",
     "false", "doubling the force doubles the *acceleration*, not the speed. Speed then builds up twice as fast", ["FORCE_VELOCITY"]),
    (r"\b(forces )?(balance|balanced|cancel|cancel out|add (up )?to zero)\b|\bnet force (is|=|equals) (zero|0)\b|\bzero net force\b|\bno net force\b",
     "true", "correct — balanced forces, zero net force, and so the velocity does not change", []),
    (r"\b(speed|velocity) (keeps? (on )?)?(increas\w+|grow\w+|rising|going up|gets? (bigger|faster|higher))\b|\bkeeps? (speeding up|accelerating)\b|\bfaster and faster\b",
     "true", "right — while the net force acts the velocity keeps increasing", []),
    (r"\bf\s*=\s*m\s*a\b|\bf\s*=\s*ma\b|\bforce (equals|=|is) mass times acceleration\b|\bsecond law\b",
     "true", "good — F = m·a: force is tied to acceleration, not to speed", []),
    (r"\b(f|force)\s*=\s*m\s*(x|\*|×|·)?\s*v\b|\bforce (equals|=|is) mass times (velocity|speed)\b",
     "false", "F = m·v is not a law. Mass times velocity is momentum; force relates to acceleration (F = m·a)", ["FORCE_VELOCITY"]),
    # ---------------- third law ----------------
    (r"\b(truck|bus|lorry|heavier|bigger|larger|more massive|faster|stronger|more powerful|earth|wall)\b.{0,40}\b(pushes|hits|exerts|applies|pulls)\b.{0,15}\b(harder|more|bigger|larger|greater|stronger)\b|\b(bigger|larger|greater|more|stronger) force (on|from) the (car|mosquito|smaller|lighter|apple|person)\b",
     "false", "this is the idea to let go of: the two forces in any interaction are exactly equal, whatever the masses or speeds. The *effects* differ because a = F/m", ["THIRD_LAW"]),
    (r"\b(car|mosquito|smaller|lighter|apple|person|pedestrian)\b.{0,40}\b(crushed|damaged|destroyed|wrecked|squashed|flung|thrown back|splat\w*|flies off|moves more)\b",
     "partly", "true, the lighter one gets wrecked — but damage shows *acceleration*, not force. Same force, much smaller mass, much bigger acceleration", ["THIRD_LAW"]),
    (r"\b(wall|ground|table|earth)\b.{0,30}\b(doesn'?t|does not|can'?t|cannot|won'?t)\s+(push|move|exert|pull)\b|\b(doesn'?t|does not|can'?t) push back\b",
     "false", "a wall that does not move still pushes back exactly as hard as you push it — if it did not, you would fall through", ["THIRD_LAW"]),
    (r"\b(wins?|winning|won)\b(?=.{0,40}\b(tug|rope|team|pull\w*)\b)|\b(tug|rope|team)\b.{0,40}\b(wins?|winning|won)\b|\bstronger team\b|\bpulls? (the rope )?harder\b",
     "false", "winning comes from friction with the ground, not from pulling the rope harder — rope tension is the same at both ends", ["THIRD_LAW"]),
    (r"\b(took|takes|taking|got|gets|received?) (the|a) (hit|blow|impact|force|push)\s+(harder|more|worse)\b|\b(explodes?|exploded|splatters?|gets? squashed)\b.{0,30}\b(harder|more force|bigger force)\b",
     "false", "taking more damage is not the same as taking more force. The forces on both were equal — the mosquito's tiny mass turned the same force into a huge acceleration", ["THIRD_LAW"]),
    (r"\b(moving|going|running|travelling|traveling)\s+fast(er)?\b.{0,25}\b(hits?|pushes|exerts)\b.{0,15}\b(more|harder|bigger|greater)\b",
     "false", "speed changes the *effect* of a collision, not the balance of forces. Whatever force she exerts on him, he exerts exactly the same on her", ["THIRD_LAW"]),
    (r"\b(more|bigger|larger|greater) momentum\b.{0,30}\b(more|bigger|larger|greater) force\b",
     "false", "momentum is not force. A fast truck has huge momentum, but the force pair between it and a car is still equal", ["THIRD_LAW"]),
    (r"\b(third law|action.{0,5}reaction|equal and opposite|same (size|force|magnitude)|forces are (the same|equal))\b",
     "true", "right — Newton's third law: the forces are equal in size and opposite in direction", []),
    (r"\b(less|smaller|lower|lighter) mass\b.{0,40}\b(accelerat\w+|moves?|flung|more|faster)\b|\baccelerates? (more|faster)\b.{0,30}\b(less|smaller|lighter) mass\b|\ba\s*=\s*f\s*/\s*m\b",
     "true", "exactly — same force, smaller mass, bigger acceleration", []),
    # ---------------- free fall ----------------
    (r"\b(heavier|heavy|bigger|more massive|more mass|more weight|weighs more)\b.{0,40}\b(falls?|lands?|drops?|hits|reaches|accelerates?|gets? there|goes|moves|speeds up|comes down)\b.{0,15}\b(faster|first|quicker|sooner|more|harder)\b|\bheavy things fall faster\b|\b(so|and|then) it (goes|falls|drops|gets there) (faster|first|quicker)\b",
     "false", "this is the misconception: heavier objects do NOT fall faster without air. The bigger pull is exactly cancelled by the bigger inertia, so every object accelerates at g", ["HEAVIER_FASTER"]),
    (r"\b(gravity|earth|the earth) (pulls|is|acts|tugs) (it |on it |them |down )?(with )?(harder|stronger|more)\b|\b(bigger|larger|greater|more) (gravitational )?(force|pull|weight)\b.{0,20}\b(heav\w+|bigger|more mass)\b|\bf\s*=\s*m\s*(x|\*|×|·)?\s*g\b|\bweight (is|=) m\s*g\b",
     "partly", "true — the pull on the heavier object really is bigger (F = m·g). The missing step is that it also has more inertia, so a = F/m comes out the same", ["HEAVIER_FASTER"]),
    (r"\b(light|lighter)\b.{0,30}\b(slow\w*|float\w*|longer|later|last)\b",
     "false", "light objects fall slowly only because of air. Remove the air — a vacuum tube, or the Moon — and the feather drops like the hammer", ["HEAVIER_FASTER"]),
    (r"\b(mass|m) cancels?\b|\bsame (acceleration|rate|g)\b|\b(both|all|every(thing)?)\b.{0,20}\b(accelerat\w+ at g|fall (at the same|together)|land (together|at the same time))\b|\ba\s*=\s*g\b.{0,20}\b(for )?(both|everything|all)\b",
     "true", "correct — the mass cancels: a = mg/m = g for everything", []),
    (r"\b(more|bigger|greater) inertia\b|\bharder to (get moving|accelerate|move)\b|\btakes more force to accelerate\b",
     "true", "yes — that extra inertia is exactly what cancels the extra pull", []),
    (r"\b(no air|without air|in a vacuum|vacuum|ignore air|on the moon)\b",
     "true", "right to note the vacuum — air is the only reason feathers fall slowly in everyday life", []),
    # ---------------- generic ----------------
    (r"\b(i think|maybe|probably|not sure|i guess|perhaps)\b",
     "note", "", []),
    # ---------------- additional phrasings seen in real student writing ----------------
    (r"\b(pull|push|force)\b.{0,15}\b(only |just )?(matched|matches|equals?|equal to|same as)\b.{0,15}\bfriction\b.{0,40}\b(wouldn'?t|would not|won'?t|can'?t|couldn'?t|not)\s+(go|move)\b",
     "false", "if the pull exactly matches friction the crate keeps moving at the speed it already has — balanced forces don't stop motion, they stop *changes* in motion", ["FORCE_VELOCITY"]),
    (r"\b(settles?|levels? off|stays|reaches|ends up)\b.{0,15}\b(at )?(a |the )?speed\b.{0,20}\b(matches|fits|equals|suits|goes with) the (force|push)\b",
     "false", "there is no speed that 'matches' a force. While the net force acts the speed keeps rising; it only levels off when the net force drops to zero", ["FORCE_VELOCITY"]),
    (r"\b(going|moving|travelling|traveling|heading)\s+(up|upwards?|forward|forwards?)\b.{0,20}\b(net )?force\s+(is|must be|points?|has to be)\s+(up|upwards?|forward|forwards?)\b|\b(net )?force\s+(is|points?)\s+(up|upwards?|forward)\b.{0,25}\b(because|since|as|cause)\s+(it'?s|it is|its)\s+(going|moving)\b",
     "false", "which way it moves and which way the net force points are different questions. Moving up at steady speed means the forces balance — net force zero", ["FORCE_VELOCITY"]),
    (r"\b(engine|motor|pedal\w*)\b.{0,25}\b(pushing|pushes|driving|drives) it (along|forward)\b.{0,30}\b(net force|that'?s the force)\b|\bthat'?s the net force\b",
     "false", "the engine force is real, but it is not the *net* force. Net force adds in drag and friction too — and at steady speed they cancel the engine exactly", ["FORCE_VELOCITY"]),
    (r"\bsame (push|force)\b.{0,10}\bsame (speed|velocity)\b|\b(need|have) to push harder to go faster\b|\bpush harder\b.{0,15}\bfaster\b",
     "false", "same push does not mean same speed — a steady push keeps *adding* speed. You push harder to accelerate faster, not to hold a higher speed", ["FORCE_VELOCITY"]),
    (r"\b(needs?|requires?|takes)\b.{0,15}\b(bigger|larger|more|greater|stronger) (net )?(force|push)\b.{0,25}\b(keep|maintain|hold|stay at|sustain)\b.{0,15}\b(speed|velocity|going|moving)\b",
     "false", "a bigger speed does not need a bigger force to keep it. Keeping any steady speed needs *zero* net force — the forward push only has to cancel the drag", ["FORCE_VELOCITY"]),
    (r"\b(still|keeps?|keep)\s+(going|moving|falling|heading)\s+(down|downwards?|forward)\b.{0,25}\b(so|therefore|means)\b.{0,25}\b(gravity|weight|force)\b.{0,15}\b(winning|wins|bigger|stronger|beating|more)\b",
     "false", "still moving down does not mean gravity is 'winning' — at terminal velocity the air pushes up exactly as hard as gravity pulls down, and the ball just keeps the speed it already has", ["FORCE_VELOCITY"]),
    (r"\ba (is|=) (0|zero)\b.{0,25}\b(i mean|or|same (thing|as)|=)\s*g\b|\b(0|zero)\b.{0,10}\b(i mean|same thing as)\b.{0,10}\bg\b",
     "false", "a = 0 and a = g are very different claims: g means the velocity is changing by 10 m/s every second; 0 means it is not changing at all. At terminal velocity it is 0 — the speed is steady", ["VA_CONFUSION"]),
    (r"\bconstant (thrust|pull|engine force)\b.{0,20}\bconstant (speed|velocity)\b",
     "false", "constant thrust gives constant *acceleration*; the speed keeps climbing for as long as the thrust exceeds the backward forces", ["FORCE_VELOCITY"]),
    (r"\b(car|mosquito|apple|person|pedestrian|smaller|lighter)\b.{0,20}\b(didn'?t|did not|doesn'?t|does not|can'?t|cannot|isn'?t|is not)\s+(do|doing|push|pushing|pull|hit|exert|apply)\b",
     "false", "it doesn't have to 'do' anything. The moment two objects touch, each pushes on the other with the same force — the force on the truck from the car appears automatically", ["THIRD_LAW"]),
    (r"\b(truck|bus|lorry|earth)\b.{0,10}\bdid the (hitting|pushing|pulling)\b|\b(bus|truck|lorry)('?s)? force is (enormous|huge|massive|way bigger|much bigger)\b|\bnothing in comparison\b|\b(is|are) (nothing|tiny|negligible)\b.{0,15}\bcompar\w*",
     "false", "in a collision there is no 'hitter' and 'hit' — both push on each other with exactly the same force. The bus feels 100% of what the mosquito feels; it just doesn't accelerate from it", ["THIRD_LAW"]),
    (r"\bwalls?\s+(don'?t|do not|can'?t|cannot|never)\s+push\b|\bjust sits? there\b|\b(apples?|mosquitos?|mosquitoes)\s+(don'?t|do not|can'?t|cannot)\s+(pull|push)\b",
     "false", "they do push — exactly as hard as they are pushed. If the wall pushed back with less, you would move it; if the apple didn't pull the Earth, gravity would be a one-way street, and it never is", ["THIRD_LAW"]),
    (r"\b(heavier|heavy|three times|twice|ten times|\d+ ?(times|x))\b.{0,40}\b(pulled|pulls?|gets?|goes|comes|brought)\s+(it\s+|him\s+|her\s+)?down\s+(faster|first|quicker|sooner)\b|\bgravity gets it down first\b",
     "false", "the heavier one is pulled down harder, yes — but 'pulled harder' does not mean 'moves faster', because it also has more mass to move. a = F/m is the same for both", ["HEAVIER_FASTER"]),
    (r"\b(twice|double|three times|ten times|\d+ times) the (mass|weight)\b.{0,30}\b(twice|double|three times|ten times|\d+ times|more) the (acceleration|accel|speed)\b|\btwice the gravity twice the acceleration\b",
     "false", "twice the mass does give twice the gravitational force — and the acceleration is that force divided by twice the mass. The twos cancel", ["HEAVIER_FASTER"]),
    (r"\b(only |just )?(a )?(tiny|little|slightly|bit|wee)\s*(bit )?faster\b",
     "false", "not even slightly: in a vacuum the two accelerations are identical to every decimal place", ["HEAVIER_FASTER"]),
    (r"\b(isn'?t|is not|stopped|not)\s+pushing\s+(it\s+)?(any ?more|anymore|now)?\b.{0,30}\b(force|push)\s+(is gone|has gone|disappears?|is lost)\b|\b(car|ship|puck|ball|its|it'?s)\s+(own )?force\s+(is gone|drains?|gradually|fades?|runs? out)\b",
     "false", "the object never had 'its own force' — the engine force ended at the same instant the engine stopped. What remains is velocity, and velocity needs no force to continue", ["IMPETUS"]),
    (r"\b(carrying|carries|carry) (it|the \w+) (up|along|forward|on)\b|\b(push|force|energy)\s+(is )?(still )?(carrying|carries)\b",
     "false", "nothing is 'carrying' it. Its own velocity does that, for free. A force would be needed only to change the velocity", ["IMPETUS"]),
    (r"\b(force|push|energy|curve|pull)\b.{0,15}\b(transferred|transfers|goes|went|stored|builds? up|put)\s+(into|in|inside)\b|\bstored in (the|its) (motion|ball|puck|object)\b",
     "false", "forces are not transferred into objects and stored. What the stick transfers is *velocity*; from then on nothing is pushing, and nothing needs to", ["IMPETUS"]),
    (r"\b(acceleration|accel)\s+(has to|must|should|will)\s+be\s+(up|upward|forward)\b.{0,30}\b(until|while|because|as|since)\b.{0,20}\b(throw|push|force|kick)\b",
     "false", "acceleration points the way the *net force* points, and after release that is down — gravity — even while the ball is still rising", ["IMPETUS"]),
    (r"\b(gradually |slowly )?(drains?|drifts? to a stop|comes? to a stop|slows? to a stop|peters? out|coasts? to a stop)\b",
     "false", "with nothing acting on it, it never slows. Slowing down needs a backward force — in deep space there isn't one", ["IMPETUS"]),
    (r"\b(wears? off|wear off|worn off|used up|runs? out|ran out)\b",
     "false", "nothing is wearing off — there is no stored force to wear off. What changes the motion is gravity, acting the whole time", ["IMPETUS"]),
    (r"\bnet force\b.{0,20}\bconstant\b.{0,20}\b(accelerat\w+)\b|\baccelerates? the whole (burn|time|way)\b",
     "true", "right — a constant net force means it keeps accelerating for as long as that force acts", []),
    (r"\b(upward|up) (pull|force|tension)\b.{0,15}\b(biggest|largest|maximum|greatest|most)\b|\ba is up\b|\bacceleration (is|points) up\b",
     "true", "yes — the net force there points up, so the acceleration points up even though the velocity is zero", []),
]


_COMPILED = [(re.compile(p, re.IGNORECASE), v, r, m) for p, v, r, m in CLAIMS]


def find_claims(text: str, priority: list[str] | None = None) -> list[dict]:
    """Return claims found in the learner's text, in order of appearance, with the exact words they used.
    `priority` = misconceptions relevant to the current item; claims tied to other misconceptions are tried last,
    so a sentence on a free-fall question is read with free-fall claims first."""
    t = text or ""
    found: list[dict] = []
    taken: list[tuple[int, int]] = []
    plist = list(priority or [])
    pri = set(plist)

    def rank(c):  # diagnosed misconception first, then the item's other misconceptions, unlabelled facts, then the rest
        if not c[3]:
            return 3
        hits = [plist.index(l) for l in c[3] if l in pri]
        return (min(hits) + 1) * 2 if hits else 1000

    ordered = sorted(_COMPILED, key=rank)
    for rx, verdict, reply, labels in ordered:
        # A claim written for a misconception that this item cannot test is read only as a fallback:
        # it is kept when nothing relevant to the item explained the sentence, never when something did.
        off_topic = bool(pri) and bool(labels) and not (pri & set(labels))
        if off_topic and any(c["verdict"] in ("false", "partly") for c in found):
            continue
        for m in rx.finditer(t):
            if verdict == "note":
                break
            span = (m.start(), m.end())
            if any(not (span[1] <= a or span[0] >= b) for a, b in taken):
                continue
            taken.append(span)
            found.append({"quote": t[m.start():m.end()].strip(" ,."), "verdict": verdict, "reply": reply, "labels": labels, "pos": m.start()})
            break
    found.sort(key=lambda c: c["pos"])
    return found
