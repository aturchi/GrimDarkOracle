"""Attack Analyzer core: one attack of one unit on another, exact.
GUI-free: the Analyzer window, the variant comparison and the tests call
analyse() and read plain frozen dataclasses.

    side_a = Side(resolved_unit, hero=joined_hero_or_None, ...)
    side_b = Side(target_unit)
    a = analyse(registry, side_a, side_b, Options(ctx=AttackContext(...)))

Two kinds of analysis, chosen by the context:

- shooting (ctx.attack == "shooting"): the attacker's sequence on the
  target (kill_chain), then the target's Morale Test;
- melee (ctx.attack == "melee", action "charge"): the full exchange
  (melee.resolve: Impact, Counter, strikes, strike back), the melee
  result and both units' Morale.

Each weapon also gets a row of its own: that weapon ALONE against the
opposing unit as it stands at the start, in its phase (Parry included in
melee). The rows do not add up to the totals, which chain every
weapon into the same unit. Hits are reported per row only: in the chain
the hits of a weapon depend on what the previous ones left (Blast, the
strike back of the survivors), and the kill chain tracks wound states,
not hits.

An attack the rules forbid (Shaken attacker, the attacker's action limits,
a target that can't be charged) is analysed as no attack: every weapon is
skipped with the reason, nobody tests Morale because of it, and the
reason is the first warning.

A Side may start wounded (Side.wounds = wounds taken per model, dead
models at their capacity): the Combatant always holds every model as
fielded, so "half or less" counts the dead ones.
"""
from dataclasses import dataclass, field, replace
from math import comb

from grimdarkoracle.app import defense_choice as DC
from grimdarkoracle.app import mixture as MX
from grimdarkoracle.app import unpredictable as UP
from grimdarkoracle.app import points_metrics as PM
from grimdarkoracle.data.af_book import Weapon
from grimdarkoracle.data.resolve import ResolvedModel, ResolvedUnit
from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine import kill_chain as K
from grimdarkoracle.engine import melee as ML
from grimdarkoracle.engine import parry as PR
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine import scourge as SC
from grimdarkoracle.engine.context import (AttackContext, CombatModel,
                                           Combatant, combatant)
from grimdarkoracle.engine.morale import (TIES, MeleeWinner, Morale,
                                          MoraleOutcome, after_melee,
                                          after_shooting, half_or_less,
                                          melee_winner)
from grimdarkoracle.engine.sequence import AttackSequence, AuditPart
from grimdarkoracle.engine.target_state import Allocation

PHASES = ("shoot", "impact", "counter", "strike", "back", "last", "spell")
SIDES = ("att", "def")              # attacker / charger, target / charged


@dataclass(frozen=True)
class Side:
    """One unit of the analysis as the user set it up."""
    unit: ResolvedUnit
    hero: ResolvedUnit | None = None    # a joined Hero
    wounds: tuple | None = None         # start state; None = no wounds
    not_moved: bool = True
    fatigued: bool = False
    shaken: bool = False
    off: frozenset = frozenset()        # Weapons switched off by the user
    hero_quality: int | None = None     # Tough(9)+ Hero within 6"
    near_terrain: bool = False          # most models within 1"
    feat_used: bool = False             # uses its ward Feat

    @property
    def points(self) -> int:
        return self.unit.points + (self.hero.points if self.hero else 0)

    def combatant(self) -> Combatant:
        """Every model as fielded, minus the weapons switched off."""
        cb = combatant(self.unit, hero=self.hero, not_moved=self.not_moved,
                       fatigued=self.fatigued, shaken=self.shaken,
                       near_terrain=self.near_terrain,
                       feat_used=self.feat_used)
        if self.wounds is not None:             # start state
            al = Allocation.of(cb)
            cb = replace(cb, over_half=not half_or_less(
                al, al.check(self.wounds)))
        if not self.off:
            return cb
        models = tuple(replace(cm, model=replace(cm.model, weapons=tuple(
            (w, n) for w, n in cm.model.weapons if w not in self.off)))
            for cm in cb.models)
        return replace(cb, models=models)

    def values(self) -> tuple[float, ...]:
        return PM.model_values(self.unit, self.hero)


@dataclass(frozen=True)
class Options:
    ctx: AttackContext = AttackContext()
    strike_back: bool = True            # melee
    tie: str = "none"                   # who wins a melee tie
    takedown_targets: tuple = ()        # target places, charger's
    weapon_order: tuple = ()            # weapon names; melee: charger
    exact: bool = False                 # Fractions (tests)
    spell: object = None                # app.spells.SpellPlan (attack "spell")
    back_versatile: tuple = ()          # the charged unit's choices

    def __post_init__(self):
        if self.tie not in TIES:
            raise ValueError(f"tie must be one of {TIES}")
        if (self.ctx.attack == "spell") != (self.spell is not None):
            raise ValueError("a spell analysis needs a spell, and only it")
        if self.ctx.melee and self.ctx.action != "charge":
            raise ValueError("a melee analysis is a charge (action 'charge')")


@dataclass(frozen=True)
class WeaponRow:
    """One weapon ALONE against the opposing unit at the start."""
    side: str                       # SIDES
    phase: str                      # PHASES
    weapon: Weapon | None           # None: Impact
    name: str
    count: int                      # copies firing (Impact: dice)
    attacks: int                    # dice rolled to hit
    hits: list                      # law of the hits (after Blast)
    wounds: list                    # law of the wounds allocated
    killed: list                    # law of the models killed
    destroyed: object               # P(no model left)
    flags: tuple[str, ...] = ()     # takedown, deadly, limited, counter
    audit: tuple = ()               # sequence.AuditPart at the start state


@dataclass(frozen=True)
class Skipped:
    side: str
    name: str
    count: int
    reason: str


@dataclass(frozen=True)
class Losses:
    """What one unit lost in the activation (exact laws)."""
    name: str
    points: int
    size: int                       # models as fielded
    wounds: list
    killed: list
    alive: list
    destroyed: object
    points_removed: float           # expected value of the models killed
    morale: MoraleOutcome


@dataclass(frozen=True)
class Analysis:
    kind: str                       # "shooting" / "melee"
    attacker: Side
    target: Side
    opts: Options
    rows: tuple[WeaponRow, ...]
    skipped: tuple[Skipped, ...]
    def_losses: Losses              # the target / charged unit
    att_losses: Losses | None       # the charger (melee)
    winner: MeleeWinner | None      # melee result
    warnings: tuple[str, ...]
    cast: object = None             # P(spell cast), spell analyses only
    hazard: list = field(default_factory=list)  # attacker's Hazardous wounds


# --- helpers -----------------------------------------------------------------


def _hazard(seq, exact: bool) -> list:
    """Law of the wounds the attacker's Hazardous weapons deal to their own
    models: each unmodified 1 to hit (1/6 per attack; fixed hits only when
    their dice are rolled) gives self_wounds_on_1 wounds; [] when
    none."""
    law = P.delta(0)
    q = G._p(1, 6, exact)
    for g in seq.plan(tuple(range(len(seq.target.models)))).groups:
        x, n = g.spec.self_wounds_on_1, g.spec.attacks
        if not x or (g.spec.auto_hit and not g.spec.auto_sixes):
            continue
        one = [0] * (x * n + 1)
        for k in range(n + 1):
            one[x * k] = comb(n, k) * q ** k * (1 - q) ** (n - k)
        law = P.convolve(law, one)
    return law if len(law) > 1 else []


def _start(alloc: Allocation, side: Side, who: str) -> tuple:
    state = alloc.fresh() if side.wounds is None else alloc.check(side.wounds)
    if not alloc.alive(state):
        raise ValueError(f"{who}: no model alive at the start")
    return state


def _by_weapon(steps) -> list[list]:
    """Steps grouped by weapon, in order of first appearance."""
    out: dict = {}
    for s in steps:
        out.setdefault(s.weapon, []).append(s)
    return list(out.values())


def _copies(unit: Combatant, weapon, models) -> int:
    return sum(n for i in models for w, n in unit.models[i].model.weapons
               if w == weapon)


def _step_hits(seq: AttackSequence, step, state, exact: bool) -> list:
    """Law of one step's hits against 'state' (Blast: models alive)."""
    alive = seq.alloc.alive(state)
    out = P.delta(0)
    if not alive:
        return out
    if step.kind == "takedown":
        j = seq.takedown_target(state)
        part = None if j is None else seq.takedown_part(step, j)
        return G.weapon_hits(part[0], 1, exact) if part else out
    for spec, _target in seq.parts(step, state):
        out = P.convolve(out, G.weapon_hits(spec, len(alive), exact))
    return out


def _row(side, phase, seq, steps, start, dist, exact) -> WeaponRow:
    weapon = steps[0].weapon
    ch = K.ChainResult(seq.alloc, start, dist)
    hits = P.delta(0)
    for s in steps:
        hits = P.convolve(hits, _step_hits(seq, s, start, exact))
    count = sum(_copies(seq.attacker, weapon, s.models) for s in steps)
    flags = tuple(f for f, on in (
        ("takedown", any(s.kind == "takedown" for s in steps)),
        ("deadly", any(s.kind == "deadly" for s in steps)),
        ("limited", any(s.limited for s in steps)),
        ("counter", any(s.counter for s in steps))) if on)
    audit = tuple(p for s in steps for p in seq.audit(s, start))
    return WeaponRow(side, phase, weapon, weapon.name, count,
                     count * weapon.attacks, hits, ch.wounds(), ch.killed(),
                     ch.destroyed(), flags, audit)


def _skipped(side, unit: Combatant, seq, s: Side, alive) -> list[Skipped]:
    """Weapons the plan excluded (with its reason) and the ones the user
    switched off, counted on the living models."""
    out = [Skipped(side, name, sum(n for i in models
                                   for w, n in unit.models[i].model.weapons
                                   if w.name == name), why)
           for name, why, models in seq.excluded]
    if s.off:
        full = combatant(s.unit, hero=s.hero)
        for w in sorted(s.off, key=lambda w: w.name):
            n = sum(k for i in alive for v, k in full.models[i].model.weapons
                    if v == w)
            if n:
                out.append(Skipped(side, w.name, n, "switched off"))
    return out


def _losses(side: Side, cb: Combatant, alloc, start, dist,
            morale: MoraleOutcome) -> Losses:
    ch = K.ChainResult(alloc, start, dist)
    return Losses(cb.name, side.points, alloc.size, ch.wounds(), ch.killed(),
                  ch.alive(), ch.destroyed(),
                  PM.removed_points(side.values(), alloc, start, dist),
                  morale)


def _issues(*sides: Side) -> list[str]:
    out = []
    for s in sides:
        for u in (s.unit, s.hero):
            if u is not None:
                out += [f"{u.name}: {x}" for x in u.issues]
    return out


# --- analyses ------------------------------------------------------------------


def analyse(reg, attacker: Side, target: Side,
            opts: Options = Options()) -> Analysis:
    """Shooting or melee analysis, by opts.ctx.attack. A target's
    Versatile Defense without a choice in opts.ctx gets the best one for
    the target, named in the warnings."""
    if opts.ctx.attack != "spell":
        done: dict = {}

        def evaluate(ctx):
            a = done[ctx] = _mixed(reg, attacker, target,
                                   replace(opts, ctx=ctx))
            return DC.mean(a.def_losses.killed), a.def_losses.destroyed
        ctx, notes = DC.pick(reg, target.combatant(), attacker.combatant(),
                             opts.ctx, evaluate)
        if notes:
            a = done[ctx]
            return replace(a, warnings=tuple(notes) + a.warnings)
        return _mixed(reg, attacker, target, opts)
    return _dispatch(reg, attacker, target, opts)


def _mixed(reg, attacker: Side, target: Side, opts: Options) -> Analysis:
    """The analysis mixed over the dice of the Unpredictable rules not
    chosen in the options: the attacker's in its attack, and in melee the
    charged unit's in its strike back (one die per unit)."""
    acb, tcb = attacker.combatant(), target.combatant()
    chosen = dict(opts.ctx.versatile)
    m_att = [m for m in UP.menus(reg, acb, tcb, opts.ctx)
             if m[0] not in chosen]
    m_def = []
    if opts.ctx.melee and opts.strike_back:
        back = dict(opts.back_versatile)
        m_def = [m for m in UP.menus(reg, tcb, acb, ML.STRIKE_BACK)
                 if m[0] not in back]
    if not (m_att or m_def):
        return _dispatch(reg, attacker, target, opts)
    results, weights = [], []
    for p, ch in UP.outcomes(m_att):
        for q, chd in UP.outcomes(m_def):
            o = replace(opts, ctx=replace(opts.ctx, versatile=tuple(
                opts.ctx.versatile) + ch), back_versatile=tuple(
                opts.back_versatile) + chd)
            results.append(_dispatch(reg, attacker, target, o))
            weights.append(p * q)
    names = ", ".join(n for _r, n, _o in m_att + m_def)
    a = MX.mix(results, weights, f"{names}: the result mixes every die "
               "outcome by its probability")
    return replace(a, opts=opts)


def _dispatch(reg, attacker: Side, target: Side, opts: Options) -> Analysis:
    if opts.ctx.melee:
        return _melee(reg, attacker, target, opts)
    if opts.ctx.attack == "spell":
        return _spell(reg, attacker, target, opts)
    return _shooting(reg, attacker, target, opts)


def _shooting(reg, att: Side, tgt: Side, opts: Options) -> Analysis:
    ex = opts.exact
    acb, tcb = att.combatant(), tgt.combatant()
    a_alloc = Allocation.of(acb)
    alive = a_alloc.alive(_start(a_alloc, att, "attacker"))
    shooter = ML.sub(acb, alive)
    seq = AttackSequence(reg, shooter, tcb, opts.ctx, opts.takedown_targets,
                         opts.weapon_order)
    t0 = _start(seq.alloc, tgt, "target")
    rows = tuple(_row("att", "shoot", seq, st, t0,
                      K.resolve(seq, t0, ex, st).dist, ex)
                 for st in _by_weapon(seq.steps))
    chain = K.resolve(seq, t0, ex)
    extra = SC.resolve_extra(seq, t0, ex) if any(
        g.spec.scourge for g in seq.plan(tuple(range(
            len(tcb.models)))).groups) else None
    morale = after_shooting(Morale(reg, tcb, tgt.hero_quality, opts.ctx),
                            chain, ex, extra=extra)
    return Analysis(
        "shooting", att, tgt, opts, rows,
        tuple(_skipped("att", shooter, seq, att, alive)),
        _losses(tgt, tcb, seq.alloc, t0, chain.dist, morale), None, None,
        _barred(seq.barred) + tuple(_issues(att, tgt)) + tuple(seq.warnings),
        hazard=_hazard(seq, ex))


def _barred(why) -> tuple[str, ...]:
    return (f"no attack: {why}",) if why else ()


def _impact_row(setup, a0, d0, ex) -> WeaponRow | None:
    imps = setup.impacts(a0, d0)
    if not imps:
        return None
    dist = PR.resolve(setup.d_alloc, setup.impact_entries(a0, d0), d0,
                      setup.parry_dice("def", d0), setup.parry_on, ex)
    ch = K.ChainResult(setup.d_alloc, d0, dist)
    n = sum(spec.attacks for spec, _ in imps)
    why = f"Impact: {n} dice of the living models" + (
        f", Brace({setup.brace}) removed" if setup.brace else "")
    models = len(setup.d_alloc.alive(d0))
    parts = tuple(AuditPart(spec, t, (why,), models) for spec, t in imps)
    hits = P.delta(0)
    for spec, _ in imps:                        # one pool per AP
        hits = P.convolve(hits, G.weapon_hits(spec, 1, ex))
    return WeaponRow("att", "impact", None, "Impact", n, n, hits,
                     ch.wounds(), ch.killed(), ch.destroyed(), (), parts)


def _melee(reg, att: Side, dfn: Side, opts: Options) -> Analysis:
    ex = opts.exact
    acb, dcb = att.combatant(), dfn.combatant()
    setup = ML.MeleeSetup(reg, acb, dcb, opts.strike_back,
                          charge_ctx=opts.ctx, back_ctx=replace(
                              ML.STRIKE_BACK, versatile=tuple(
                                  opts.back_versatile)),
                          order_att=opts.weapon_order,
                          aims_att=opts.takedown_targets)   # A7 pattern
    a0 = _start(setup.a_alloc, att, "charger")
    d0 = _start(setup.d_alloc, dfn, "charged unit")
    a_alive, d_alive = setup.a_alloc.alive(a0), setup.d_alloc.alive(d0)
    seq_a, seq_d = setup.seq("att", a_alive), setup.seq("def", d_alive)
    rows = [r for r in (_impact_row(setup, a0, d0, ex),) if r]
    for side, phase, seq, other in (("att", "strike", seq_a, d0),
                                    ("def", "counter", seq_d, a0),
                                    ("def", "back", seq_d, a0),
                                    ("att", "last", seq_a, d0)):
        for st in _by_weapon(setup.steps(phase, seq)):
            rows.append(_row(side, phase, seq, st, other,
                             setup.phase(side, st, seq, other, ex), ex))
    result = ML.resolve(setup, (a0, d0), ex)
    m_att = Morale(reg, acb, att.hero_quality, setup.back_ctx)
    m_def = Morale(reg, dcb, dfn.hero_quality, opts.ctx)
    tie = "none" if setup.barred else opts.tie   # no exchange: no test
    mo_a, mo_d = after_melee(m_att, m_def, result, tie, ex)
    skipped = _skipped("att", seq_a.attacker, seq_a, att, a_alive) + \
        (_skipped("def", seq_d.attacker, seq_d, dfn, d_alive)
         if opts.strike_back else [])
    rows = tuple(rows)
    return Analysis(
        "melee", att, dfn, opts, rows, tuple(skipped),
        _losses(dfn, dcb, setup.d_alloc, d0, result.defender().dist, mo_d),
        _losses(att, acb, setup.a_alloc, a0, result.attacker().dist, mo_a),
        melee_winner(m_att, m_def, result, tie),
        _barred(setup.barred) + tuple(_issues(att, dfn)) + tuple(
            dict.fromkeys(seq_a.warnings + seq_d.warnings)),
        hazard=_hazard(seq_a, ex) if not setup.barred else [])


def _spell(reg, caster: Side, tgt: Side, opts: Options) -> Analysis:
    """A damage spell: a bare caster model with the spell weapon;
    the row is the spell IF CAST, the target's losses include P(cast)."""
    ex, plan = opts.exact, opts.spell
    acb, tcb = caster.combatant(), tgt.combatant()
    _start(Allocation.of(acb), caster, "caster")
    bare = Combatant(plan.name, (CombatModel(
        ResolvedModel(((plan.weapon, 1),), (), ()), 2, 6),))
    ctx = replace(opts.ctx, spell_sixes=plan.roll_sixes)
    seq = AttackSequence(reg, bare, tcb, ctx, opts.takedown_targets)
    t0 = _start(seq.alloc, tgt, "target")
    hit = K.resolve(seq, t0, ex)
    rows = tuple(_row("att", "spell", seq, st, t0, hit.dist, ex)
                 for st in _by_weapon(seq.steps))
    p = 0 if caster.shaken else plan.p_cast     # Shaken: idle
    dist = {s: q * p for s, q in hit.dist.items()}
    dist[t0] = dist.get(t0, 0) + (1 - p)
    chain = K.ChainResult(seq.alloc, t0, dist)
    morale = after_shooting(Morale(reg, tcb, tgt.hero_quality, ctx),
                            chain, ex, attack="spell")
    return Analysis(
        "spell", caster, tgt, opts, rows, (),
        _losses(tgt, tcb, seq.alloc, t0, dist, morale), None, None,
        _barred("Shaken: must stay idle" if caster.shaken else None)
        + tuple(_issues(caster, tgt)) + tuple(seq.warnings), p,
        hazard=_hazard(seq, ex))
