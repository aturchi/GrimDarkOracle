"""Morale of GF 3.6: Morale Tests after shooting and the melee result.

Core rules MORALE + rule texts:

- Morale Test = Quality test (6 / 1 automatic) with the unit's Morale
  modifiers (Banner, Bravery Aura: once per rule, highest); the
  unit's Quality, or a joined Hero's if better while the Hero lives, or a
  Tough(9)+ Hero within 6" (Analyzer option); Fearless (most living
  models): a failed test is passed on 4+; a Shaken unit always fails and
  Fearless cannot change it;
- shooting: test when the activation dealt wounds and the unit ends at
  half or less (size, or Tough for single models); fail = Shaken;
- melee: no tests from wounds; the unit with more wounds taken in the
  exchange (+ the enemy's Fear) loses and tests; tie as chosen;
  fail = Rout if at half or less, else Shaken. A destroyed unit does not
  test. melee_winner() gives the law of who won (a destroyed unit can
  win or lose: only the wounds compare).

All laws are exact over the end states of kill_chain / melee: floats, or
Fractions when the inputs are.
"""
from dataclasses import dataclass, field, replace
from fractions import Fraction
from math import comb

from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine.context import ATTACKS, AttackContext, Combatant
from grimdarkoracle.engine.specs import game_auto
from grimdarkoracle.engine.target_state import Allocation
from grimdarkoracle.rules import effects as E

TIES = ("none", "defender", "attacker")      # who WINS a tie
_CTX = {a: AttackContext(a, action=None) for a in ATTACKS}


@dataclass(frozen=True)
class MoraleOutcome:
    """Probabilities for one unit after one activation."""
    destroyed: object = 0           # killed by the attack itself
    test: object = 0                # had to take a Morale Test
    shaken: object = 0              # Shaken at the end (new or already)
    rout: object = 0                # routed (melee only)
    held: object = 0                # No Retreat: failed, counted passed
    self_wounds: list = field(default_factory=list)  # their wounds


HALF = Fraction(1, 2)                       # semantics.json morale_half


def half_or_less(alloc: Allocation, state, half=HALF) -> bool:
    """Down to 'half' or less of its total size, or of its Tough value
    for a single-model unit; a joined Hero counts as a model."""
    if alloc.size == 1:
        return alloc.left(state, 0) <= half * alloc.infos[0].cap
    return len(alloc.alive(state)) <= half * alloc.size


class Morale:
    """Morale Tests of one unit (its rules, read on its living models)."""

    def __init__(self, reg, unit: Combatant, hero_quality: int | None = None,
                 ctx: AttackContext | None = None):
        """'ctx': the attack the unit took, from the attacker's side, so
        Morale modifiers read its distance and charge (Valiant)."""
        self.reg, self.unit, self.hero_quality = reg, unit, hero_quality
        self.ctx = ctx
        self.alloc = Allocation.of(unit)
        game = reg.game                                  # semantics.json 'game'
        self.half = Fraction(str(game.get("morale_half", HALF)))
        g = game_auto(game)
        self.auto = (g["auto_success"], g["auto_fail"])
        self.fearless_on = 4
        for e in reg.entries.values():
            if e.handler == "fearless":
                self.fearless_on = dict(e.params).get("pass_on", 4)
        self._cache: dict = {}

    def _holds(self, alive, attack):
        sub = replace(self.unit, models=tuple(self.unit.models[i]
                                              for i in alive))
        ctx = _CTX[attack] if self.ctx is None else \
            replace(self.ctx, attack=attack)
        view = E.View(self.reg, ctx, "defender", sub, (), sub,
                      tuple(m.defense for m in sub.models))
        holds, _ = E.holdings(self.reg, view)
        return sub, replace(view, holds=holds)

    def numbers(self, state, attack: str) -> tuple[int, int, bool]:
        """(Quality, total modifier, Fearless applies) of a Morale Test in
        'state' after 'attack'."""
        alive = self.alloc.alive(state)
        key = ("n", alive, attack)
        if key in self._cache:
            return self._cache[key]
        sub, view = self._holds(alive, attack)
        mods: dict = {}
        for k, hs in enumerate(view.holds):
            for h in hs:
                for n, eff in enumerate(h.sem.effects):
                    if eff.primitive == "morale_mod" and \
                            E.applies(h.sem, eff, replace(view, model=k)):
                        v = eff.value if eff.value != "X" else h.ref.rating
                        if isinstance(v, int):
                            old = mods.get((h.sem.rule_id, n), 0)
                            mods[(h.sem.rule_id, n)] = max(old, v, key=abs)
        q = min(m.quality for m in sub.models)       # joined Hero [Hero]
        if self.hero_quality is not None:
            q = min(q, self.hero_quality)
        fearless = [h for hs in view.holds for h in hs
                    if h.sem.handler == "fearless"]
        brave = bool(fearless) and E.majority(
            E.holders(view.holds, fearless[0].sem.rule_id), len(view.holds))
        out = self._cache[key] = (q, sum(mods.values()), brave)
        return out

    def pass_prob(self, state, attack: str, exact: bool = False):
        """P(the unit passes a Morale Test) in 'state' after 'attack'."""
        if self.unit.shaken:
            return G._p(0, 6, exact)                 # always fails
        q, mod, brave = self.numbers(state, attack)
        ok = G._p(G.success_faces(q, mod, self.auto), 6, exact)
        if brave:
            ok = ok + (1 - ok) * G._p(7 - self.fearless_on, 6, exact)
        return ok

    def no_retreat(self, state, attack: str) -> bool:
        """Most living models hold No Retreat (and the unit isn't already
        Shaken: its test causes nothing)."""
        alive = self.alloc.alive(state)
        if self.unit.shaken or not alive:
            return False
        _sub, view = self._holds(alive, attack)
        ids = {h.sem.rule_id for hs in view.holds for h in hs
               if h.sem.handler == "no_retreat"}
        return any(E.majority(E.holders(view.holds, r), len(view.holds))
                   for r in ids)

    def fail(self, o: dict, s, p, key: str, attack: str, exact: bool):
        """Add a failed test of probability p in state s to outcome o: key
        ('shaken' / 'rout'), or No Retreat's passed test and its wounds,
        one die per wound left, each 1-3 a wound."""
        if not p:
            return
        if not self.no_retreat(s, attack):
            o[key] += p
            return
        o["held"] += p
        n = sum(self.alloc.left(s, i) for i in self.alloc.alive(s))
        law = o.setdefault("self_wounds", [])
        half = G._p(1, 2, exact)
        for k in range(n + 1):
            q = p * comb(n, k) * half ** n
            law.extend([0] * (k + 1 - len(law)))
            law[k] += q

    def fear(self, state) -> int:
        """Fear(X) of the living models, added up."""
        alive = self.alloc.alive(state)
        _sub, view = self._holds(alive, "melee") if alive else (None, None)
        if view is None:
            return 0
        return sum(max([h.ref.rating for h in hs if h.sem.handler == "fear"
                        and isinstance(h.ref.rating, int)], default=0)
                   for hs in view.holds)


def after_shooting(morale: Morale, chain, exact: bool = False,
                   attack: str = "shooting", extra=None) -> MoraleOutcome:
    """Morale of the target after a shooting (or spell, attack='spell')
    ChainResult; extra: {(state, Scourge count): p}."""
    a, start = morale.alloc, chain.start
    out = dict(destroyed=0, test=0, shaken=0, held=0)
    dist = extra or {(s, 0): p for s, p in chain.dist.items()}
    for (s, x), p in dist.items():
        if not a.alive(s):
            out["destroyed"] += p
            continue
        # Scourge, reading (b): its block 1s trigger the test of a unit at
        # half or less even with no wound
        tests = (a.taken(s) > a.taken(start) or x > 0) and \
            half_or_less(a, s, morale.half)
        if tests:
            out["test"] += p
            morale.fail(out, s, p * (1 - morale.pass_prob(s, attack, exact)),
                        "shaken", attack, exact)
        elif morale.unit.shaken:
            out["shaken"] += p
    return _outcome(out)


def _outcome(o: dict) -> MoraleOutcome:
    """MoraleOutcome with No Retreat's law made whole (P(0 wounds) for
    the rest)."""
    law = o.get("self_wounds")
    if law:
        law[0] += 1 - sum(law)
    return MoraleOutcome(**o)


def _losers(m_att: Morale, m_def: Morale, result, tie: str):
    """(joint state, probability, loser) per end state of the exchange:
    loser 0 = charger, 1 = charged unit, None = nobody tests. The unit
    with more wounds taken in the exchange plus the enemy's Fear loses
    (a destroyed unit included); ties as chosen."""
    if tie not in TIES:
        raise ValueError(f"tie must be one of {TIES}")
    a0, d0 = result.start
    fear_a, fear_d = m_att.fear(a0), m_def.fear(d0)
    dist = getattr(result, "extra", None) or result.dist   # Scourge
    for key, p in dist.items():
        (a, d), x = key[:2], (key[2:] or (0, 0))
        took = (m_att.alloc.taken(a) - m_att.alloc.taken(a0) + fear_d + x[0],
                m_def.alloc.taken(d) - m_def.alloc.taken(d0) + fear_a + x[1])
        yield (a, d), p, loser_of(took, tie)


def loser_of(took: tuple, tie: str):
    """Who lost a melee from (charger's, charged unit's) wounds taken plus
    the enemy's Fear: 0 = charger, 1 = charged unit, None = nobody tests
    (a tie with tie="none")."""
    if took[0] != took[1]:
        return 0 if took[0] > took[1] else 1
    return {"none": None, "defender": 0, "attacker": 1}[tie]


@dataclass(frozen=True)
class MeleeWinner:
    """Law of the melee result: who won (the other side lost)."""
    charger: object = 0             # the charged unit lost
    charged: object = 0             # the charger lost
    none: object = 0                # tie, nobody takes a Morale Test


def melee_winner(m_att: Morale, m_def: Morale, result,
                 tie: str = "none") -> MeleeWinner:
    """Who wins the exchange of a MeleeResult."""
    acc = {0: 0, 1: 0, None: 0}
    for _s, p, loser in _losers(m_att, m_def, result, tie):
        acc[loser] += p
    return MeleeWinner(charger=acc[1], charged=acc[0], none=acc[None])


def after_melee(m_att: Morale, m_def: Morale, result, tie: str = "none",
                exact: bool = False) -> tuple[MoraleOutcome, MoraleOutcome]:
    """(charger, charged unit) Morale after a MeleeResult."""
    acc = [dict(destroyed=0, test=0, shaken=0, rout=0, held=0)
           for _ in range(2)]
    for states, p, loser in _losers(m_att, m_def, result, tie):
        for k, m in enumerate((m_att, m_def)):
            o, s = acc[k], states[k]
            if not m.alloc.alive(s):
                o["destroyed"] += p
            elif k == loser:
                o["test"] += p
                fail = p * (1 - m.pass_prob(s, "melee", exact))
                m.fail(o, s, fail, "rout" if half_or_less(m.alloc, s, m.half)
                       else "shaken", "melee", exact)
            elif m.unit.shaken:
                o["shaken"] += p
    return _outcome(acc[0]), _outcome(acc[1])
