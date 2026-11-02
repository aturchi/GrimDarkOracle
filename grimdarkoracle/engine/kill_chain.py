"""Exact law of the target's state after an attack sequence.

The state (target_state) holds the wounds taken by each model; the law is
a dict {state: probability}, floats or Fractions (exact=True). The
sequence (sequence.AttackSequence) gives the steps and, for each state,
the final numbers of the weapon; gf_math gives the weapon's laws.

Per step and per starting state:

- ordinary weapon (Deadly 1): each wound event inflicts 0 or 1 wound, so
  the order of the events does not matter and the wounds simply pass from
  model to model: new state = carry(state, gross wounds);
- Deadly(X): each event's wounds go to ONE model, the excess is lost
  (Deadly rule text; Regeneration per wound, not counted);
  events are i.i.d., so the law is the mixture over the number of events
  of the event step applied that many times;
- Takedown: the wounds go to the chosen model only, excess lost.

Blast counts the models alive at the start of the weapon.
"""
from dataclasses import dataclass

from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.sequence import AttackSequence, Step
from grimdarkoracle.engine.target_state import Allocation


def _add(out: dict, state, p) -> None:
    if p:
        out[state] = out.get(state, 0) + p


class _Laws:
    """weapon_law cache: the same spec meets the same unit size often."""

    def __init__(self, exact: bool):
        self.exact, self.cache = exact, {}

    def __call__(self, spec, target, models):
        key = (spec, target, models)
        law = self.cache.get(key)
        if law is None:
            law = self.cache[key] = G.weapon_law(spec, target, models,
                                                 self.exact)
        return law


def apply_weapon(dist: dict, alloc: Allocation, spec, target, laws) -> dict:
    """One weapon (AttackSpec, unit-level TargetSpec) on every state."""
    out: dict = {}
    for state, p in dist.items():
        n = len(alloc.alive(state))
        if not n:
            _add(out, state, p)
            continue
        law = laws(spec, target, n)
        apply_events(out, state, p, alloc, law.events, law.event, spec.deadly)
    return out


def apply_events(out: dict, state, p, alloc: Allocation, events: list,
                 event: list, deadly: int, model: int | None = None) -> None:
    """Add to 'out' the law of 'state' (probability p) after a number of
    wound events ~ 'events', each inflicting ~ 'event' wounds: on 'model'
    only (Takedown) or on the allocation order, carried over unless
    Deadly (Deadly rule text)."""
    if model is not None or deadly == 1:
        for g, pg in enumerate(P.compound(events, event)):
            nxt = alloc.carry(state, g) if model is None else \
                alloc.wound(state, model, g)
            _add(out, nxt, p * pg)
        return
    cur = {state: 1}                        # after k events
    for k, pk in enumerate(events):
        if pk:
            for s, q in cur.items():
                _add(out, s, p * pk * q)
        if k < len(events) - 1:
            cur = _one_event(cur, alloc, event)


def _one_event(dist: dict, alloc: Allocation, event: list) -> dict:
    """One Deadly event: its wounds on the first model only (rule text)."""
    out: dict = {}
    for s, q in dist.items():
        i = alloc.front(s)
        for d, pd in enumerate(event):
            _add(out, s if i is None else alloc.wound(s, i, d), q * pd)
    return out


def apply_takedown(dist: dict, seq: AttackSequence, step: Step,
                   laws) -> dict:
    """One attacking model's Takedown weapon on its chosen model."""
    out: dict = {}
    for state, p in dist.items():
        j = seq.takedown_target(state)
        part = None if j is None else seq.takedown_part(step, j)
        if part is None:
            _add(out, state, p)
            continue
        law = laws(part[0], part[1], 1)
        for g, pg in enumerate(law.gross):
            _add(out, seq.alloc.wound(state, j, g), p * pg)
    return out


@dataclass(frozen=True)
class ChainResult:
    alloc: Allocation
    start: tuple
    dist: dict                      # final state -> probability

    def _law(self, fn) -> list:
        out: dict = {}
        for s, p in self.dist.items():
            v = fn(s)
            out[v] = out.get(v, 0) + p
        return P.add([0], [out.get(v, 0) for v in range(max(out) + 1)])

    def killed(self) -> list:
        """Law of the models killed by the sequence."""
        k0 = self.alloc.killed(self.start)
        return self._law(lambda s: self.alloc.killed(s) - k0)

    def wounds(self) -> list:
        """Law of the wounds allocated (excess Deadly wounds excluded)."""
        w0 = self.alloc.taken(self.start)
        return self._law(lambda s: self.alloc.taken(s) - w0)

    def alive(self) -> list:
        """Law of the models alive at the end."""
        return self._law(lambda s: len(self.alloc.alive(s)))

    def destroyed(self):
        return self.alive()[0]


def resolve(seq: AttackSequence, start=None, exact: bool = False,
            steps=None) -> ChainResult:
    """Law of the target state after 'steps' (default: seq.steps) from
    'start' (default: no wounds)."""
    alloc = seq.alloc
    start = alloc.fresh() if start is None else alloc.check(start)
    laws = _Laws(exact)
    dist = {start: 1}
    for step in (seq.steps if steps is None else steps):
        if step.kind == "takedown":
            dist = apply_takedown(dist, seq, step, laws)
            continue
        out: dict = {}
        for state, p in dist.items():       # parts depend on the state
            cur = {state: p}
            for spec, target in seq.parts(step, state):
                cur = apply_weapon(cur, alloc, spec, target, laws)
            for s, q in cur.items():
                _add(out, s, q)
        dist = out
    return ChainResult(alloc, start, dist)
