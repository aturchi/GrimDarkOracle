"""Parry: one roll for all the hits a unit takes in one melee phase.

Rule (core rules API): "When this unit takes hits in melee, roll X dice per
model with this rule in it, up to as many dice as hits taken. For each 6+
one hit is ignored (defender picks which)."

Reading: one Parry roll per PHASE in which the
unit takes hits (Impact; the Counter strikes; the charger's strikes; the
strike back), pooling the hits of all the striking unit's weapons. So in a
phase with Parry:

1. every weapon (entry) rolls its hits first, with the AttackSpec and the
   models alive at the START of the phase (Blast too);
2. Parry: dice = min(X x living Parry models, total hits); each 6+ ignores
   one hit, the defender picking the hits with the highest expected wounds
   (ties: the later entry, six-hits before ordinary hits);
3. the remaining hits are blocked and allocated entry by entry in the
   usual order (Takedown, Deadly, others), with the unit TargetSpec of the
   state at that moment.

Entries are built by melee.py; exact resolution here, dice in dice_resolve.
"""
from dataclasses import dataclass
from itertools import product
from typing import Callable

from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine import kill_chain as K
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.specs import AttackSpec, TargetSpec
from grimdarkoracle.engine.target_state import Allocation


@dataclass(frozen=True)
class Entry:
    """One weapon of the phase."""
    spec: AttackSpec
    blast_models: int               # models for Blast when the hits roll
    target: Callable                # state -> TargetSpec at resolution
    model: int | None = None        # Takedown: the chosen model

    @property
    def split(self) -> bool:
        """Six-hits differ from ordinary hits (Rending AP)."""
        return self.spec.ap_on_6 != 0


def entries_for(seq, steps, state) -> list[Entry]:
    """Entries of 'steps' of an AttackSequence at the phase start."""
    out = []
    alive = seq.alloc.alive(state)
    for step in steps:
        if step.kind == "takedown":
            j = seq.takedown_target(state)
            part = None if j is None else seq.takedown_part(step, j)
            if part is not None:
                out.append(Entry(part[0], 1, lambda s, t=part[1]: t, j))
            continue
        for k, (spec, _t) in enumerate(seq.parts(step, state)):
            out.append(Entry(spec, len(alive),
                             lambda s, st=step, k=k: _target(seq, st, k, s)))
    return out


def _target(seq, step, k, state) -> TargetSpec | None:
    parts = seq.parts(step, state)
    return parts[min(k, len(parts) - 1)][1] if parts else None


def hit_law(e: Entry, exact: bool) -> dict:
    """{(ordinary, six) or (all,): p} of one entry."""
    if e.split:
        return G.weapon_hit_pairs(e.spec, e.blast_models, exact)
    return {(h,): p for h, p in enumerate(
        G.weapon_hits(e.spec, e.blast_models, exact)) if p}


def ranking(entries, state) -> list[tuple[int, int]]:
    """(entry, slot) classes in the order the defender ignores them:
    highest expected wounds per hit first (ties: later entry, six first).
    slot: 0 = ordinary (or all), 1 = six-hits."""
    keys = []
    for n, e in enumerate(entries):
        if e.spec.no_block:                 # wounds, not hits
            continue
        t = e.target(state) or TargetSpec()
        per_event = P.mean(G.event_wounds(e.spec, t))
        slots = ((0, False), (1, True)) if e.split else ((0, False),)
        for slot, six in slots:
            v = P.mean(G.hit_wounds(e.spec, t, six)) * per_event
            keys.append(((-v, -n, -slot), (n, slot)))
    return [c for _, c in sorted(keys)]


def remove(counts: list[list[int]], order, k: int) -> tuple:
    """Hit counts per entry after ignoring k hits in 'order'."""
    left = [list(c) for c in counts]
    for n, slot in order:
        if not k:
            break
        take = min(k, left[n][slot])
        left[n][slot] -= take
        k -= take
    return tuple(tuple(c) for c in left)


def save_prob(ignore_on: int, exact: bool):
    return G._p(7 - ignore_on, 6, exact)


def resolve(alloc: Allocation, entries, start, dice: int,
            ignore_on: int = 6, exact: bool = False) -> dict:
    """Exact law {state: p} of the receiving unit after the phase."""
    if not entries or not alloc.alive(start):
        return {start: 1}
    order = ranking(entries, start)
    q = save_prob(ignore_on, exact)
    left: dict = {}                         # hits per entry -> p
    for combo in product(*(hit_law(e, exact).items() for e in entries)):
        counts = [c for c, _ in combo]
        p = 1
        for _, x in combo:
            p *= x
        total = sum(sum(c) for c, e in zip(counts, entries)
                    if not e.spec.no_block)
        for k, pk in enumerate(P.binomial(min(dice, total), q)):
            if pk:
                key = remove(counts, order, k)
                left[key] = left.get(key, 0) + p * pk
    out: dict = {}
    for counts, p in left.items():
        dist = {start: p}
        for e, c in zip(entries, counts):
            dist = _apply_fixed(dist, alloc, e, c, exact)
        for s, x in dist.items():
            K._add(out, s, x)
    return out


def _apply_fixed(dist, alloc, e: Entry, counts, exact) -> dict:
    """One entry with its hits fixed, on every state."""
    plain, six = (counts[0], counts[1]) if e.split else (counts[0], 0)
    out: dict = {}
    for s, p in dist.items():
        t = e.target(s)
        if t is None or not alloc.alive(s) or (
                e.model is not None and alloc.left(s, e.model) <= 0):
            K._add(out, s, p)
            continue
        K.apply_events(out, s, p, alloc,
                       G.fixed_hits_events(e.spec, t, plain, six, exact),
                       G.event_wounds(e.spec, t, exact), e.spec.deadly,
                       e.model)
    return out
