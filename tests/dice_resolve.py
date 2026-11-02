"""Attack resolution with real dice, one die at a time.

Reads the same AttackSpec / TargetSpec as gf_math and the same steps as
the kill chain (sequence.AttackSequence), but rolls every die and applies
every wound event literally, so the Monte Carlo parity tests compare two
independent derivations of the same rules (Monte Carlo is a
test oracle only). It was the dice engine of the Game Assistant until its
removal and now lives with the tests.
resolve_melee() rolls a whole melee exchange (engine.melee.MeleeSetup).

Rules applied per die: quality test with 6 / 1
automatic; Fatigue hits on an unmodified 6 only, which is then not
"a 6"; a 6 gives a six-hit plus extra_hits_on_6 ordinary hits;
Blast multiplies every hit, copies keep their kind; Defense roll
per hit with AP floored at 0 per kind, Bane / Smash re-roll an
unmodified 6 once; a block failed on an unmodified 1 adds Shred
events; each event inflicts Deadly(X) wounds, each ignored on a
Regeneration roll. Each event goes to the first model of the
allocation order, or to the Takedown model, and its excess is lost.
"""
import random
from dataclasses import dataclass

from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine import parry as PR
from grimdarkoracle.engine.sequence import AttackSequence, Step
from grimdarkoracle.engine.specs import AttackSpec, TargetSpec


def d6(rng) -> int:
    return rng.randint(1, 6)


@dataclass(frozen=True)
class WeaponRoll:
    """Dice outcome of one weapon (before allocation)."""
    name: str
    attacks: int
    hits: int                       # all hits after Blast
    six_hits: int                   # of which from an unmodified 6
    events: tuple[int, ...]         # wounds of each event (Deadly, Regen)
    extra: int = 0                  # Scourge count (unmodified block 1s)




def roll_hits(spec: AttackSpec, models: int, rng) -> tuple[int, int]:
    """(ordinary hits, six-hits) after Blast; a Predator result rolls one
    new attack that never triggers it again."""
    b = G.blast_multiplier(spec, models)
    plain = six = 0
    todo = [True] * spec.attacks            # True: may trigger Predator
    while todo:
        original = todo.pop()
        if spec.auto_hit and spec.auto_sixes:
            if d6(rng) == 6:
                six += 1
                plain += spec.extra_hits_on_6
            else:
                plain += 1
            continue
        if spec.auto_hit:
            plain += 1
            continue
        r = d6(rng)
        if spec.fatigued:
            plain += r >= spec.fatigue_on
            continue
        hit = r == 6 or G.passes(r, spec.quality, spec.hit_mod,
                                 G.auto_of(spec))
        if r == 6:
            six += 1
            plain += spec.extra_hits_on_6
        elif hit:
            plain += 1
        if hit and original and spec.extra_attack_on and \
                r >= spec.extra_attack_on:
            todo.append(False)
    return plain * b, six * b


def roll_event(spec: AttackSpec, target: TargetSpec, rng) -> int:
    """Wounds inflicted by one wound event: each of its Deadly wounds rolls
    Regeneration, then each ward, until one ignores it."""
    ons = G.wound_save_ons(spec, target)
    if not ons:
        return spec.deadly
    return sum(1 for _ in range(spec.deadly)
               if all(d6(rng) < on for on in ons))


def roll_weapon(spec: AttackSpec, target: TargetSpec, models: int,
                rng) -> WeaponRoll:
    plain, six = roll_hits(spec, models, rng)
    events, ones = _blocks(spec, target, plain, six, rng)
    return WeaponRoll(spec.name, spec.attacks, plain + six, six, events,
                      spec.scourge * ones)


def roll_blocks(spec: AttackSpec, target: TargetSpec, plain: int, six: int,
                rng) -> tuple[int, ...]:
    """Wounds of each event from 'plain' ordinary hits and 'six' six-hits."""
    return _blocks(spec, target, plain, six, rng)[0]


def _blocks(spec, target, plain, six, rng):
    """(wounds of each event, unmodified block 1s)."""
    if spec.no_block:                           # wound dice
        return tuple(roll_event(spec, target, rng)
                     for _ in range(plain + six)), 0
    n_events = ones = 0
    for is_six, count in ((False, plain), (True, six)):
        ap = G.effective_ap(spec, is_six)
        for _ in range(count):
            r = d6(rng)
            on = G.reroll_face(spec)
            if on and r >= on and G.passes(r, target.defense,
                                           target.defense_mod - ap,
                                           G.auto_of(target)):
                r = d6(rng)                         # the re-roll stands
            if G.passes(r, target.defense, target.defense_mod - ap,
                        G.auto_of(target)):
                continue
            n_events += 1 + (spec.shred if r == 1 else 0)
            ones += r == 1
    return tuple(roll_event(spec, target, rng) for _ in range(n_events)), \
        ones


@dataclass(frozen=True)
class Resolved:
    step: Step
    roll: WeaponRoll
    model: int | None = None        # Takedown target


def resolve(seq: AttackSequence, start=None, rng=None, steps=None):
    """(final state, [Resolved, ...]) of one attack sequence."""
    rng = rng or random.Random()
    alloc = seq.alloc
    state = alloc.fresh() if start is None else alloc.check(start)
    log = []
    for step in (seq.steps if steps is None else steps):
        if not alloc.alive(state):
            break
        if step.kind == "takedown":
            j = seq.takedown_target(state)
            part = seq.takedown_part(step, j)
            if part is None:
                continue
            roll = roll_weapon(part[0], part[1], 1, rng)
            for d in roll.events:
                state = alloc.wound(state, j, d)
            log.append(Resolved(step, roll, j))
            continue
        for spec, target in seq.parts(step, state):
            roll = roll_weapon(spec, target, len(alloc.alive(state)), rng)
            for d in roll.events:
                i = alloc.front(state)
                if i is None:
                    break
                state = alloc.wound(state, i, d)
            log.append(Resolved(step, roll))
    return state, log


def resolve_parry_phase(alloc, entries, start, dice: int, ignore_on: int,
                        rng):
    """(state, log) of a melee phase with Parry (engine.parry): all hits
    first, one Parry roll, then the blocks entry by entry."""
    state = start
    if not entries or not alloc.alive(state):
        return state, []
    counts = []
    for e in entries:
        plain, six = roll_hits(e.spec, e.blast_models, rng)
        counts.append([plain, six] if e.split else [plain + six])
    total = sum(sum(c) for c, e in zip(counts, entries)
                if not e.spec.no_block)
    saved = sum(1 for _ in range(min(dice, total)) if d6(rng) >= ignore_on)
    counts = PR.remove(counts, PR.ranking(entries, start), saved)
    log = [("parry", saved)]
    for e, c in zip(entries, counts):
        t = e.target(state)
        if t is None or not alloc.alive(state) or (
                e.model is not None and alloc.left(state, e.model) <= 0):
            continue
        plain, six = (c[0], c[1]) if e.split else (c[0], 0)
        events = roll_blocks(e.spec, t, plain, six, rng)
        for d in events:
            i = e.model if e.model is not None else alloc.front(state)
            if i is None:
                break
            state = alloc.wound(state, i, d)
        log.append((e.spec.name, plain + six, events))
    return state, log


def _retaliate(setup, hit_side, before, after, striker, rng):
    """(striking unit's state, log) after the Retaliate hits of the
    wounds 'hit_side' took in a phase."""
    entry = setup.retaliation_entry(hit_side, before, after, striker)
    if entry is None:
        return striker, []
    s_side = "att" if hit_side == "def" else "def"
    striker, sub_log = resolve_parry_phase(
        setup.alloc(s_side), [entry], striker,
        setup.parry_dice(s_side, striker), setup.parry_on, rng)
    return striker, [("retaliate", x) for x in sub_log]


def resolve_melee(setup, start=None, rng=None):
    """(charger state, defender state, log) of one melee exchange, in the
    order of engine.melee: Impact, Counter, strikes, strike back."""
    rng = rng or random.Random()
    a0, d0 = start or (None, None)
    a = setup.a_alloc.fresh() if a0 is None else setup.a_alloc.check(a0)
    d = setup.d_alloc.fresh() if d0 is None else setup.d_alloc.check(d0)
    log = []
    entries = setup.impact_entries(a, d)
    if entries:
        d_before = d
        d, sub_log = resolve_parry_phase(
            setup.d_alloc, entries, d, setup.parry_dice("def", d),
            setup.parry_on, rng)
        log += [("impact", x) for x in sub_log]
        a, more = _retaliate(setup, "def", d_before, d, a, rng)
        log += more
    for side, phase in (("def", "counter"), ("att", "strike"),
                        ("def", "back"), ("att", "last")):
        me, other = (a, d) if side == "att" else (d, a)
        alive = (setup.a_alloc if side == "att" else setup.d_alloc).alive(me)
        if not alive:
            continue
        seq = setup.seq(side, alive)
        steps = setup.steps(phase, seq)
        if not steps:
            continue
        dice = setup.parry_dice("def" if side == "att" else "att", other)
        before = other
        if dice:
            other, sub_log = resolve_parry_phase(
                setup.alloc("def" if side == "att" else "att"),
                PR.entries_for(seq, steps, other), other, dice,
                setup.parry_on, rng)
        else:
            other, sub_log = resolve(seq, other, rng, steps)
        log += [(phase, r) for r in sub_log]
        me, more = _retaliate(setup, "def" if side == "att" else "att",
                              before, other, me, rng)
        log += more
        a, d = (me, other) if side == "att" else (other, me)
    if setup.self_destruct:
        a_start, d_start = (setup.a_alloc.fresh() if a0 is None else
                            setup.a_alloc.check(a0),
                            setup.d_alloc.fresh() if d0 is None else
                            setup.d_alloc.check(d0))
        ea = setup.destruct_entry("att", a_start, d, a)
        ed = setup.destruct_entry("def", d_start, a, d)
        if ea is not None:
            d, sub = resolve_parry_phase(setup.d_alloc, [ea], d,
                                         setup.parry_dice("def", d),
                                         setup.parry_on, rng)
            log += [("self_destruct", x) for x in sub]
        if ed is not None:
            a, sub = resolve_parry_phase(setup.a_alloc, [ed], a,
                                         setup.parry_dice("att", a),
                                         setup.parry_on, rng)
            log += [("self_destruct", x) for x in sub]
        a = setup.destruct_removal("att", a_start, a)[0]
        d = setup.destruct_removal("def", d_start, d)[0]
    return a, d, log
