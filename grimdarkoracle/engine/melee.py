"""Melee exchange of GF 3.6: one charging unit against the charged unit.

Order (core rules MELEE, Impact, Brace, Counter):

1. Impact: the charger's living models roll their Impact(X) dice, minus
   the target's Brace(X), neither when its unit is Fatigued; each 2+ is a
   hit with no modifier, AP 0 (Heavy Impact: the AP of its source, the
   target's own AP modifiers apply) and no special rule;
2. Counter: the charged unit's Counter weapons strike first, unless it is
   Fatigued;
3. the charger's models strike with all their melee weapons (all within
   3" in the Analyzer);
4. strike back: the charged unit's survivors strike with their other
   weapons (all of them if Counter did not strike first); a Fatigued or
   Shaken unit does it Fatigued (Combatant.fatigued / .shaken);
5. last: the charger's Unwieldy strikes ("strikes last when charging"),
   after the strike back;
6. Self-Destruct(X): each model with it alive at the start of the exchange
   gives the enemy X hits (no rule, as Retaliate's), then the ones still
   alive are removed; that removal does not count as wounds taken for the
   melee result (keys with the Scourge counts, negative).

Each phase is an AttackSequence of the living strikers against the whole
opposing unit from its current state, resolved by kill_chain on every
joint state: the result is the exact law of (charger state, charged unit
state). Morale and the melee result are in engine.morale.

A charge the rules forbid (Shaken charger, action limits, a target that
can't be charged: MeleeSetup.barred) is no exchange at all: no Impact, no
strikes, no strike back.

Retaliate: after every phase (Impact included), each model with
Retaliate(X) of the unit that took wounds gives the striking unit X hits
per wound it took in that phase (AP 0, no special rule; the striking
unit's Defense, Regeneration, wards and Parry apply).

Parry: when the unit taking hits in a phase has Parry, that phase
is resolved by engine.parry (one roll for the pooled hits of the phase).
MeleeSetup is shared by resolve() here and dice_resolve.resolve_melee().
"""
from dataclasses import dataclass, replace

from grimdarkoracle.data.af_book import Weapon
from grimdarkoracle.data.resolve import ResolvedModel
from grimdarkoracle.engine import kill_chain as K
from grimdarkoracle.engine import parry as PR
from grimdarkoracle.engine import scourge as SC
from grimdarkoracle.engine.context import AttackContext, CombatModel, Combatant
from grimdarkoracle.engine.modifiers import activation_bar
from grimdarkoracle.engine.sequence import AttackSequence
from grimdarkoracle.engine.specs import AttackSpec, TargetSpec, game_auto
from grimdarkoracle.engine.target_state import Allocation
from grimdarkoracle.rules import effects as E
from grimdarkoracle.rules.registry import RuleRegistry

CHARGE = AttackContext("melee", action="charge")
STRIKE_BACK = AttackContext("melee", action=None)
_IMPACT_W = Weapon("Impact", 1, 0, 1)
# A rule-less striker: its plan gives the defender's own TargetSpec only.
_BARE = Combatant("Impact", (CombatModel(
    ResolvedModel(((_IMPACT_W, 1),), (), ()), 2, 6),))


def sub(unit: Combatant, alive) -> Combatant:
    """The unit reduced to the models at positions 'alive'."""
    return replace(unit, models=tuple(unit.models[i] for i in alive))


def _impacts(reg, unit, other) -> list[tuple[int, int]]:
    """Per model of the charger: (X, AP) of its Impact-type source with
    the highest X, then the highest AP ((0, 0) if none)."""
    view = E.View(reg, CHARGE, "attacker", unit, (), other,
                  tuple(m.defense for m in other.models))
    holds, _ = E.holdings(reg, view)
    return [max(((h.ref.rating, dict(h.sem.params).get("ap", 0))
                 for h in hs if h.sem.handler == "impact"
                 and isinstance(h.ref.rating, int)), default=(0, 0))
            for hs in holds]


def _scourge(reg, unit, other) -> bool:
    """Does a model of 'unit' hold a Scourge-type effect?"""
    view = E.View(reg, CHARGE, "attacker", unit, (), other,
                  tuple(m.defense for m in other.models))
    holds, _ = E.holdings(reg, view)
    return any(e.primitive == "scourge" for hs in holds for h in hs
               for e in h.sem.effects)


def _retaliators(reg, unit, other) -> tuple[tuple[int, int], ...]:
    """(model place, X) of the unit's models holding Retaliate(X)."""
    return tuple((i, x) for i, x in enumerate(
        _ratings(reg, unit, "defender", other, "retaliate")) if x)


def _ratings(reg, unit, role, other, handler) -> list[int]:
    """Per model: the highest integer rating of its rules with 'handler'
    (auras included), 0 if none."""
    view = E.View(reg, CHARGE, role, unit, (), other,
                  tuple(m.defense for m in other.models))
    holds, _ = E.holdings(reg, view)
    out = []
    for hs in holds:
        r = [h.ref.rating for h in hs if h.sem.handler == handler
             and isinstance(h.ref.rating, int)]
        out.append(max(r, default=0))
    return out


class MeleeSetup:
    """Everything the exchange needs, cached per set of living strikers."""

    def __init__(self, reg: RuleRegistry, attacker: Combatant,
                 defender: Combatant, strike_back: bool = True,
                 charge_ctx: AttackContext = CHARGE,
                 back_ctx: AttackContext = STRIKE_BACK, aims_att=(),
                 aims_def=(), order_att=(), order_def=()):
        """aims_*: Takedown preferences of each side's strikers;
        order_*: weapon names each side strikes with first, within the
        classes Takedown / Deadly / others."""
        if not (charge_ctx.melee and back_ctx.melee):
            raise ValueError("melee contexts expected")
        self.reg, self.att, self.dfn = reg, attacker, defender
        self.a_alloc, self.d_alloc = Allocation.of(attacker), \
            Allocation.of(defender)
        self.aims = {"att": tuple(aims_att), "def": tuple(aims_def)}
        self.orders = {"att": tuple(order_att), "def": tuple(order_def)}
        self.charge_ctx, self.back_ctx = charge_ctx, back_ctx
        self.strike_back = strike_back
        self.barred = activation_bar(reg, attacker, defender, charge_ctx)
        # Counter is part of the defender's strikes: off with strike back.
        self.counter_first = strike_back and not (defender.fatigued or
                                                  defender.shaken)
        self._seqs: dict = {}
        self._impact: dict = {}
        brace = 0 if defender.fatigued else max(
            _ratings(reg, defender, "defender", attacker, "brace"), default=0)
        self.brace = brace
        self.hit_on = self._param("impact", "hit_on", 2)
        self.parry_on = self._param("parry", "ignore_on", 6)
        self._parry: dict = {}
        self.scourge = _scourge(reg, attacker, defender) or \
            _scourge(reg, defender, attacker)
        self._retaliators = {s: _retaliators(reg, u, o) for s, u, o in
                             (("att", attacker, defender),
                              ("def", defender, attacker))}
        self._destructors = {s: tuple((i, x, False) for i, x in enumerate(
            _ratings(reg, u, "defender", o, "self_destruct")) if x) + tuple(
            (i, x, True) for i, x in enumerate(
                _ratings(reg, u, "defender", o, "deathstrike")) if x)
            for s, u, o in (("att", attacker, defender),
                            ("def", defender, attacker))}
        self.self_destruct = any(self._destructors.values())

    def _param(self, handler, name, default):
        return next((dict(e.params).get(name, default)
                     for e in self.reg.entries.values()
                     if e.handler == handler), default)

    def alloc(self, side: str) -> Allocation:
        return self.a_alloc if side == "att" else self.d_alloc

    def parry_dice(self, side: str, state) -> int:
        """Parry dice of 'side' ('att' / 'def') when it takes hits: X per
        living model with Parry(X) (auras included)."""
        alive = self.alloc(side).alive(state)
        key = (side, alive)
        n = self._parry.get(key)
        if n is None:
            unit, other = (self.att, self.dfn) if side == "att" else \
                (self.dfn, self.att)
            n = sum(_ratings(self.reg, sub(unit, alive), "defender", other,
                             "parry")) if alive else 0
            self._parry[key] = n
        return n

    def phase(self, side: str, steps, seq, target_state, exact: bool):
        """Law of the receiving unit after 'steps' of 'side''s strikers."""
        other = "def" if side == "att" else "att"
        dice = self.parry_dice(other, target_state)
        if not dice:
            return K.resolve(seq, target_state, exact, steps).dist
        return PR.resolve(self.alloc(other),
                          PR.entries_for(seq, steps, target_state),
                          target_state, dice, self.parry_on, exact)

    # --- strikes ------------------------------------------------------------

    def seq(self, side: str, alive) -> AttackSequence:
        """'att': the charger's living models against the defender;
        'def': the defender's living models against the charger."""
        key = (side, tuple(alive))
        s = self._seqs.get(key)
        if s is None:
            if side == "att":
                s = AttackSequence(self.reg, sub(self.att, alive), self.dfn,
                                   self.charge_ctx, self.aims["att"],
                                   self.orders["att"])
            else:
                s = AttackSequence(self.reg, sub(self.dfn, alive), self.att,
                                   self.back_ctx, self.aims["def"],
                                   self.orders["def"])
            self._seqs[key] = s
        return s

    def steps(self, phase: str, seq: AttackSequence) -> list:
        """Steps of 'phase' (counter / strike / back) in 'seq'."""
        if self.barred:
            return []                   # no exchange
        if phase == "counter":
            return [s for s in seq.steps if s.counter] \
                if self.counter_first else []
        if phase == "back":
            if not self.strike_back:
                return []
            return [s for s in seq.steps
                    if not (self.counter_first and s.counter)]
        if phase == "last":
            return [s for s in seq.steps if s.last]
        return [s for s in seq.steps if not s.last]

    # --- Impact --------------------------------------------------------

    def impact_pools(self, a_state) -> tuple[tuple[int, int], ...]:
        """(AP, dice) of the charger's living models' Impact, one pool per
        AP, highest AP first; Brace removes the highest-AP dice first (the
        defender's best choice)."""
        if self.att.fatigued or self.barred:
            return ()
        alive = self.a_alloc.alive(a_state)
        pools = self._impact.get(alive)
        if pools is None:
            acc: dict = {}
            for x, ap in _impacts(self.reg, sub(self.att, alive), self.dfn):
                if x:
                    acc[ap] = acc.get(ap, 0) + x
            pools = self._impact[alive] = tuple(sorted(acc.items(),
                                                       reverse=True))
        out, brace = [], self.brace
        for ap, n in pools:
            cut = min(n, brace)
            brace -= cut
            if n - cut:
                out.append((ap, n - cut))
        return tuple(out)

    def impact_dice(self, a_state) -> int:
        """Impact dice of the charger's living models, minus Brace."""
        return sum(n for _, n in self.impact_pools(a_state))

    def _impact_part(self, d_state):
        """(AttackSpec of a rule-less striker, unit TargetSpec) against the
        defender: the TargetSpec, and the defender's own AP modifiers
        (Fortified) in the spec's AP."""
        seq = self._seqs.get("impact")
        if seq is None:
            seq = self._seqs["impact"] = AttackSequence(
                self.reg, _BARE, self.dfn, self.charge_ctx)
        parts = seq.parts(seq.steps[0], d_state) if seq.steps else []
        return parts[0] if parts else None

    def _bare_target(self, side: str, state) -> TargetSpec | None:
        """The unit TargetSpec of 'side' against hits with no rule."""
        key = ("bare", side)
        seq = self._seqs.get(key)
        if seq is None:
            unit, ctx = (self.dfn, self.charge_ctx) if side == "def" else \
                (self.att, self.back_ctx)
            seq = self._seqs[key] = AttackSequence(
                self.reg, _BARE, unit, ctx)
        parts = seq.parts(seq.steps[0], state) if seq.steps else []
        return parts[0][1] if parts else None

    def retaliation(self, hit_side: str, before, after) -> AttackSpec | None:
        """The hits the striking unit takes from 'hit_side''s Retaliate
        models for the wounds they took from 'before' to 'after'."""
        n = sum(x * max(0, after[i] - before[i])
                for i, x in self._retaliators[hit_side])
        return AttackSpec(n, auto_hit=True, name="Retaliate",
                          **game_auto(self.reg.game)) if n else None

    def retaliate(self, hit_side: str, before, after, striker_state,
                  exact: bool) -> dict:
        """Law of the striking unit's state after the Retaliate hits."""
        entry = self.retaliation_entry(hit_side, before, after, striker_state)
        if entry is None:
            return {striker_state: 1}
        s_side = "att" if hit_side == "def" else "def"
        return PR.resolve(self.alloc(s_side), [entry], striker_state,
                          self.parry_dice(s_side, striker_state),
                          self.parry_on, exact)

    def retaliation_entry(self, hit_side, before, after, striker_state):
        """The Retaliate hits as a Parry entry, None when there are none
        (shared with the dice oracle of the tests)."""
        spec = self.retaliation(hit_side, before, after)
        s_side = "att" if hit_side == "def" else "def"
        alloc = self.alloc(s_side)
        if spec is None or not alloc.alive(striker_state):
            return None
        return PR.Entry(spec, len(alloc.alive(striker_state)),
                        lambda s: self._bare_target(s_side, s))

    # --- Self-Destruct ---------------------------------------------

    def destruct_entry(self, side: str, start, enemy_state, now=None):
        """The hits 'side''s Self-Destruct models alive at 'start' give the
        enemy, and its Deathstrike models alive at 'start' but killed by
        'now', as a Parry entry, or None."""
        alive = set(self.alloc(side).alive(start))
        left = set(self.alloc(side).alive(now)) if now is not None else alive
        n = sum(x for i, x, killed in self._destructors[side]
                if i in alive and not (killed and i in left))
        enemy = "def" if side == "att" else "att"
        e_alive = self.alloc(enemy).alive(enemy_state)
        if not n or not e_alive:
            return None
        spec = AttackSpec(n, auto_hit=True, name="Self-Destruct",
                          **game_auto(self.reg.game))
        return PR.Entry(spec, len(e_alive),
                        lambda s: self._bare_target(enemy, s))

    def destruct_removal(self, side: str, start, state) -> tuple:
        """(state with 'side''s surviving Self-Destruct models removed,
        wounds that removal adds)."""
        al, out, w = self.alloc(side), list(state), 0
        alive0, now = set(al.alive(start)), set(al.alive(state))
        for i, _x, killed in self._destructors[side]:
            if not killed and i in alive0 and i in now:
                w += al.left(state, i)
                out[i] = al.infos[i].cap
        return tuple(out), w

    def impact_target(self, d_state) -> TargetSpec | None:
        """The defender's unit TargetSpec against Impact hits."""
        part = self._impact_part(d_state)
        return part[1] if part else None

    def impacts(self, a_state, d_state) -> list[tuple[AttackSpec,
                                                    TargetSpec]]:
        """(AttackSpec, unit TargetSpec) of each Impact pool (one per AP)."""
        pools = self.impact_pools(a_state)
        part = self._impact_part(d_state) if pools else None
        if part is None or not self.d_alloc.alive(d_state):
            return []
        return [(AttackSpec(n, quality=self.hit_on, ap=ap + part[0].ap,
                            name="Impact" + (f" AP({ap})" if ap else ""),
                            **game_auto(self.reg.game)), part[1])
                for ap, n in pools]

    def impact_entries(self, a_state, d_state) -> list[PR.Entry]:
        """Impact as Parry entries (a phase of its own)."""
        n = len(self.d_alloc.alive(d_state))
        return [PR.Entry(spec, n, self.impact_target)
                for spec, _t in self.impacts(a_state, d_state)]


@dataclass(frozen=True)
class MeleeResult:
    setup: MeleeSetup
    start: tuple                    # (charger state, defender state)
    dist: dict                      # (charger state, defender state) -> p
    extra: dict | None = None       # Scourge: (a, d, a's extra, d's) -> p

    def _side(self, k: int) -> K.ChainResult:
        out: dict = {}
        for st, p in self.dist.items():
            out[st[k]] = out.get(st[k], 0) + p
        alloc = self.setup.a_alloc if k == 0 else self.setup.d_alloc
        return K.ChainResult(alloc, self.start[k], out)

    def attacker(self) -> K.ChainResult:
        return self._side(0)

    def defender(self) -> K.ChainResult:
        return self._side(1)


def _strike(dist, setup, side, phase, exact):
    """One phase: the living strikers of 'side' against the other side.
    Keys (charger, charged) or, counting Scourge, (charger, charged,
    charger's extra, charged unit's extra)."""
    out: dict = {}
    for key, p in dist.items():
        a, d, x = key[0], key[1], key[2:]
        me, other = (a, d) if side == "att" else (d, a)
        my_alloc = setup.a_alloc if side == "att" else setup.d_alloc
        alive = my_alloc.alive(me)
        seq = setup.seq(side, alive) if alive else None
        steps = setup.steps(phase, seq) if seq else []
        if not steps:
            K._add(out, key, p)
            continue
        hit_side = "def" if side == "att" else "att"
        if x and not setup.parry_dice(hit_side, other):
            law = SC.resolve_extra(seq, other, exact, steps)
        else:                               # Parry: block 1s not counted
            law = {(t, 0): q for t, q in
                   setup.phase(side, steps, seq, other, exact).items()}
        for (t, e), q in law.items():
            for m, r in setup.retaliate(hit_side, other, t, me,
                                        exact).items():
                if not x:
                    nk = (m, t) if side == "att" else (t, m)
                elif side == "att":         # the charged unit counts them
                    nk = (m, t, x[0], x[1] + e)
                else:
                    nk = (t, m, x[0] + e, x[1])
                K._add(out, nk, p * q * r)
    return out


def impact_phase(setup, a0, d0, exact: bool, extra=()) -> dict:
    """Law of (charger, charged unit[, extras]) after Impact and its
    Retaliate; extra=(0, 0) keeps the Scourge counts in the keys."""
    dist = {(a0, d0) + tuple(extra): 1}
    entries = setup.impact_entries(a0, d0)
    if not entries:
        return dist
    out: dict = {}
    for t, q in PR.resolve(setup.d_alloc, entries, d0,
                           setup.parry_dice("def", d0), setup.parry_on,
                           exact).items():
        for m, r in setup.retaliate("def", d0, t, a0, exact).items():
            K._add(out, (m, t) + tuple(extra), q * r)
    return out


def destruct_phase(setup, dist, a0, d0, exact: bool) -> dict:
    """Self-Destruct after both sides struck; keys gain (charger's,
    charged unit's) counts, the removals' wounds negative."""
    out: dict = {}
    for key, p in dist.items():
        a, d = key[:2]
        x = key[2:] or (0, 0)
        laws = []
        for side, me, other in (("att", a, d), ("def", d, a)):
            enemy = "def" if side == "att" else "att"
            entry = setup.destruct_entry(side, a0 if side == "att" else d0,
                                         other, me)
            laws.append({other: 1} if entry is None else PR.resolve(
                setup.alloc(enemy), [entry], other,
                setup.parry_dice(enemy, other), setup.parry_on, exact))
        for d2, q in laws[0].items():               # the charger's hits
            for a2, r in laws[1].items():           # the charged unit's
                a3, wa = setup.destruct_removal("att", a0, a2)
                d3, wd = setup.destruct_removal("def", d0, d2)
                K._add(out, (a3, d3, x[0] - wa, x[1] - wd), p * q * r)
    return out


def resolve(setup: MeleeSetup, start=None, exact: bool = False) -> MeleeResult:
    """Exact law of both units' states after the exchange."""
    a0, d0 = start or (None, None)
    a0 = setup.a_alloc.fresh() if a0 is None else setup.a_alloc.check(a0)
    d0 = setup.d_alloc.fresh() if d0 is None else setup.d_alloc.check(d0)
    extra = (0, 0) if setup.scourge else ()
    dist = impact_phase(setup, a0, d0, exact, extra)       # 1. Impact
    dist = _strike(dist, setup, "def", "counter", exact)   # 2. Counter
    dist = _strike(dist, setup, "att", "strike", exact)    # 3. strikes
    dist = _strike(dist, setup, "def", "back", exact)      # 4. strike back
    dist = _strike(dist, setup, "att", "last", exact)      # 5. Unwieldy
    if setup.self_destruct:                                # 6.
        dist = destruct_phase(setup, dist, a0, d0, exact)
        extra = (0, 0)
    if not extra:
        return MeleeResult(setup, (a0, d0), dist)
    flat: dict = {}
    for key, p in dist.items():
        K._add(flat, key[:2], p)
    return MeleeResult(setup, (a0, d0), flat, dist)
