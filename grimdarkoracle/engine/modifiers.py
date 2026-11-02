"""Modifier layer: two combatants + rule semantics + context -> the final
numbers of gf_math (AttackSpec per weapon group, TargetSpec per target model).

Per attacking model and weapon:

- attacker-side effects come from the weapon's rules, the model's own rules
  (scope model / default: that model only, never a joined Hero's host or
  vice versa), unit-scope effects of any model of the unit, Marks on
  the target, Spotter tokens and the chosen Versatile effects;
- defender-side effects come from the target's rules, once per unit;
- the same rule entry counts once, at its highest value;
- Unstoppable drops the NEGATIVE defender-side modifiers to hit, AP and
  range; cover is the target's bonus and stays;
- range modifiers are summed first, so Smash ("half of this weapon's
  range") uses the effective range;
- weapons that cannot attack (melee weapon when shooting, out of range,
  Crossing Strike, no line of sight without Indirect + Hold, Rush / Charge
  when shooting) are listed in AttackPlan.excluded with the reason;
  in a Crossing Strike attack only Crossing Strike weapons attack, with no
  range, action or line-of-sight limit, and the target gets no cover;
- activation bars exclude every weapon with the same reason: a Shaken
  attacker must stay idle (the user's flag); the attacker's permanent
  action limits (action_limit: Immobile, Cumbersome, Aircraft) against the
  action of the context; a charge on a unit that can't be charged.
  Strike back (action None) and spells (bare caster) are never barred.

Target Defense: Armor sets it per model; a joined Hero uses the Defense
most host models have while any host model is alive. Cover (+1, only
against shooting) is ignored by Blast and Anti-Cover, and by Indirect with
Hold against Sight Blockers, and in a Crossing Strike attack.
Fatigue only in melee.
"""
from dataclasses import dataclass, replace

from grimdarkoracle.data.af_book import Weapon
from grimdarkoracle.engine.context import ACTIONS, AttackContext, Combatant
from grimdarkoracle.engine.specs import AttackSpec, TargetSpec, game_auto
from grimdarkoracle.rules import effects as E
from grimdarkoracle.rules import vocab as V
from grimdarkoracle.rules.registry import RuleRegistry

MENU_HANDLERS = ("mark", "spotter", "versatile", "unpredictable")
CHOICE_HANDLERS = ("versatile", "unpredictable")    # chosen in ctx.versatile


def menu_items(sem) -> list[tuple[str | None, tuple[int, ...]]]:
    """Choices of a Versatile rule: (label or None, effect indices); the
    'choices' param groups effects, else each effect is a choice."""
    groups = dict(sem.params).get("choices")
    if groups:
        return [(label, tuple(ix)) for label, ix in groups]
    return [(None, (n,)) for n in range(len(sem.effects))]


def chosen_effects(sem, ctx) -> list[tuple[int, object]]:
    """(effect index, effect) of the choice made for a Versatile rule in
    'ctx' (by its entry id), none if no valid choice."""
    idx = dict(ctx.versatile).get(sem.rule_id)
    items = menu_items(sem)
    if idx is None or not 0 <= idx < len(items):
        return []
    return [(n, sem.effects[n]) for n in items[idx][1]]
NO_SHOOTING = ("rush", "charge")


@dataclass(frozen=True)
class AttackGroup:
    weapon: Weapon
    models: tuple[int, ...]         # positions in attacker.models
    spec: AttackSpec
    targets: tuple[TargetSpec, ...]  # one per target model, same order
    takedown: bool = False
    limited: bool = False
    counter: bool = False
    last: bool = False              # Unwieldy: strikes last when charging
    sources: tuple[str, ...] = ()   # audit of the modifiers applied

    @property
    def target(self) -> TargetSpec | None:
        """The TargetSpec when every target model has the same one."""
        return self.targets[0] if self.targets and \
            all(t == self.targets[0] for t in self.targets) else None


@dataclass(frozen=True)
class AttackPlan:
    groups: tuple[AttackGroup, ...]
    # (weapon, why, models)
    excluded: tuple[tuple[str, str, tuple[int, ...]], ...]
    warnings: tuple[str, ...]
    barred: str | None = None       # why the unit cannot attack at all


def _value(eff, held, warnings):
    """Effect value with "X" replaced by the rule's rating (None if bad)."""
    if eff.value != "X":
        return eff.value
    r = held.ref.rating
    if isinstance(r, int) and not isinstance(r, bool):
        return r
    warnings.add(f"{held.source}: rating {r!r} is not a number; ignored")
    return None


class _Mods:
    """Primitive effects for one (model, weapon), one per rule entry."""

    def __init__(self):
        self.vals: dict = {}        # key -> (primitive, value, foreign, label)

    def add(self, key, prim, value, foreign, label):
        old = self.vals.get(key)
        if old is None or abs(value) > abs(old[1]):
            self.vals[key] = (prim, value, foreign, label)

    def kept(self, prim, unstoppable) -> list:
        """Values of 'prim' left after Unstoppable: it drops the negative
        ones of foreign origin, the target's rules and the debuffs an
        enemy gave."""
        return [v for p, v, f, _ in self.vals.values() if p == prim and
                not (unstoppable and f and v < 0)]

    def total(self, prim, unstoppable=False) -> int:
        return sum(self.kept(prim, unstoppable))

    def any(self, prim) -> bool:
        return any(self.kept(prim, False))

    def sources(self, unstoppable) -> tuple:
        out = []
        for p, v, f, label in self.vals.values():
            if unstoppable and f and v < 0:
                continue
            out.append(f"{label}: {p}" if isinstance(v, bool)
                       else f"{label}: {p} {v:+d}")
        return tuple(sorted(out))


# --- target side -------------------------------------------------------------

def _target_defenses(view, warnings) -> tuple:
    """Defense of each target model: Armor (defense_set), joined Hero."""
    out = []
    for k, cm in enumerate(view.holder.models):
        sets = [_value(eff, h, warnings) for h in view.holds[k]
                for eff in h.sem.effects
                if eff.primitive == "defense_set" and eff.side == "defender"
                and E.applies(h.sem, eff, replace(view, model=k))]
        sets = [s for s in sets if s is not None]
        out.append(min(sets) if sets else cm.defense)
    hosts = [d for d, m in zip(out, view.holder.models) if not m.hero]
    if hosts and len(hosts) < len(out):
        common = max(hosts, key=lambda d: (hosts.count(d), -hosts.index(d)))
        out = [common if m.hero else d
               for d, m in zip(out, view.holder.models)]
    return tuple(out)


def _defender_effects(view, warnings) -> tuple[list, list]:
    """(unit-level foreign modifiers [(key, prim, value, label)], per-model
    defense_mod) from the target's own rules."""
    unit, per_model = {}, [0] * len(view.holds)
    for k, hs in enumerate(view.holds):
        v = replace(view, model=k)
        for h in hs:
            if h.sem.handler == "versatile":            # target's pick
                effs = chosen_effects(h.sem, view.ctx)
            elif h.sem.handler in MENU_HANDLERS:
                continue
            else:
                effs = list(enumerate(h.sem.effects))
            for n, eff in effs:
                if eff.side != "defender" or eff.primitive in \
                        ("defense_set",) + V.STRUCTURAL or \
                        not E.applies(h.sem, eff, v):
                    continue
                val = _value(eff, h, warnings)
                if val is None:
                    continue
                if eff.scope == "model" and eff.primitive == "defense_mod":
                    per_model[k] += val
                    continue
                old = unit.get((h.sem.rule_id, n))     # once, highest
                if old is None or abs(val) > abs(old[1]):
                    unit[(h.sem.rule_id, n)] = (eff.primitive, val, h.source)
    return [(k, p, v, s) for k, (p, v, s) in unit.items()], per_model


def regeneration(view) -> tuple[bool, int]:
    """(whether most living models of the view hold a Regeneration-type
    rule, the die result that ignores a wound). Public: the Game
    Assistant's Dangerous Terrain Test uses it too. The
    first such rule held decides the threshold."""
    entries = [h for hs in view.holds for h in hs
               if h.sem.handler == "regeneration"]
    if not entries:
        return False, 5
    sem = entries[0].sem
    on = dict(sem.params).get("ignore_on", 5)
    return E.majority(E.holders(view.holds, sem.rule_id), len(view.holds)), on


def _far(ctx) -> bool:
    """Shot from over 9" or charged from over 6"."""
    return (ctx.attack == "shooting" and ctx.dist > 9) or (
        ctx.melee and ctx.action == "charge" and ctx.charge_distance > 6)


def _shot_or_charged(ctx) -> bool:
    """Shot, or charged (Impact and the charger's strikes)."""
    return ctx.attack == "shooting" or (ctx.melee and ctx.action == "charge")


def wards(view, spell: bool = False) -> tuple[int, ...]:
    """Die results of the ward rolls of the view's unit: one per ward rule
    (handler ward) most living models hold, in rule order; a spell's
    wounds use 'spell_ignore_on' when the rule has one. 'far_only':
    other wounds only when shot / charged from over 9"/6" (unless an
    "Enhanced" rule lifts it); 'replaces': takes the place of that ward,
    and acts only when it does. 'state': only when the unit uses
    its once-per-game Feat in this activation (Protection Feat)."""
    seen: dict = {}
    for hs in view.holds:
        for h in hs:
            if h.sem.handler == "ward":
                seen.setdefault(h.sem.rule_id, h.sem)
    act = {}
    for rid, sem in seen.items():
        if not E.majority(E.holders(view.holds, rid), len(view.holds)):
            continue
        p = dict(sem.params)
        if p.get("state") and not view.holder.feat_used:
            continue
        if spell and "spell_ignore_on" in p:
            act[rid] = (sem, p["spell_ignore_on"])
        elif not p.get("far_only") or _far(view.ctx) or (
                _shot_or_charged(view.ctx) and E.lifted(view, rid)):
            act[rid] = (sem, p.get("ignore_on", 6))
    for rid, (sem, _on) in list(act.items()):
        old = dict(sem.params).get("replaces")
        if old is None:
            continue
        gone = [r for r in act if r != rid
                and old in view.reg.alias_chain(r)]
        for r in gone:
            del act[r]
        if not gone:
            del act[rid]
    return tuple(on for _sem, on in act.values())


# --- attacker side -----------------------------------------------------------

def _attacker_entries(reg, view, i, w_holds, ctx):
    """(held, effect index, effect) of every attacker-side candidate."""
    out = [(h, n, e) for h in w_holds if h.sem.handler not in MENU_HANDLERS
           for n, e in enumerate(h.sem.effects)]
    for j, hs in enumerate(view.holds):
        for h in hs:
            if h.sem.handler in MENU_HANDLERS:
                continue
            out += [(h, n, e) for n, e in enumerate(h.sem.effects)
                    if (e.scope == "unit") or (j == i and e.scope != "unit")]
    for mid in ctx.marks:
        base, k = E.mark_parts(mid)                 # tokens: "<id>*k"
        sem = reg.lookup(base)
        if sem is not None and sem.handler == "mark":
            h = E.Held(E.RuleRef(base, sem.name, k), sem, f"{sem.name} (mark)")
            out += [(h, n, e) for n, e in enumerate(sem.effects)]
    seen = set()
    for h in list(view.holds[i]) + list(w_holds):   # w_holds: a Mark
        if h.sem.handler in CHOICE_HANDLERS and h.sem.rule_id not in seen:
            seen.add(h.sem.rule_id)              # Unpredictable: the die
            out += [(h, n, e) for n, e in chosen_effects(h.sem, ctx)]
    return [(h, n, e) for h, n, e in out
            if e.side == "attacker" and e.primitive not in V.STRUCTURAL]


# Natives a model rule may give to its weapons ("X on its weapons", an
# aura or a "... when Shooting" rule)
MODEL_TO_WEAPON = ("indirect",)


def _weapon_holds(reg, view, w, warnings, i=None):
    """Rules of a weapon plus the rules Marks grant to friendly weapons and
    the MODEL_TO_WEAPON natives its model holds (grants included)."""
    hs, miss = E.wrap(reg, w.rules)
    warnings |= miss
    for h in (view.holds[i] if i is not None else ()):
        if h.sem.handler in MODEL_TO_WEAPON and E.check(
                h.sem.conditions, replace(view, model=i),
                h.sem.rule_id) and not any(
                x.sem.rule_id == h.sem.rule_id for x in hs):
            hs.append(h)
    for mid in view.ctx.marks:
        sem = reg.lookup(E.mark_parts(mid)[0])
        for eff in (sem.effects if sem and sem.handler == "mark" else ()):
            if eff.primitive == "grant_rule" and E.applies(sem, eff, view):
                g = reg.lookup(eff.value["rule"])
                if g and not any(x.sem.rule_id == g.rule_id for x in hs):
                    hs.append(E.Held(E.RuleRef(g.rule_id, g.name), g,
                                     f"{g.name} (via {sem.name})"))
    return hs


def _excluded(ctx, w, natives, rng, any_action=False) -> str | None:
    """Why weapon w can't attack, or None; any_action: Quick Throw lifts
    Indirect's Hold condition for line of sight."""
    if "crossing_strike" in natives and not ctx.crossing:
        return "Crossing Strike: only when moving through enemies"
    if ctx.crossing:
        # The model moves through the target: no range, action or line of
        # sight limit; the (range 0) bombs attack "as if shooting".
        return None if "crossing_strike" in natives else \
            "not a Crossing Strike weapon"
    if ctx.attack == "spell":
        return None                 # the spell itself, no range limit
    assault = "assault" in natives
    if ctx.melee:
        return None if w.melee or assault else "ranged weapon"
    if ctx.action in NO_SHOOTING:
        return f"no shooting after {ctx.action}"
    if w.melee and not assault:
        return "melee weapon"
    if rng < ctx.distance:
        return f'out of range ({rng}")'
    if not ctx.line_of_sight and not ("indirect" in natives and (
            ctx.action == "hold" or any_action)):
        return "no line of sight"
    return None


def _rating(h, warnings) -> int:
    r = h.ref.rating
    if isinstance(r, int) and not isinstance(r, bool) and r >= 1:
        return r
    warnings.add(f"{h.source}: rating {r!r} is not a number; ignored")
    return 1


def _one(reg, aview, i, w, n, foreign, warnings):
    """(AttackSpec, ignore_cover, natives, sources) or (None, reason)."""
    ctx, cm = aview.ctx, aview.holder.models[i]
    w_holds = _weapon_holds(reg, aview, w, warnings, i)
    natives = {h.sem.handler: h for h in w_holds if h.sem.handler}
    entries = _attacker_entries(reg, aview, i, w_holds, ctx)
    dh = natives.get("dice_hits")
    if dh is not None:
        return _dice_hits(reg, aview, w, n, dh)
    wd = natives.get("wound_dice")
    if wd is not None:                          # Ravage, Crossing Attack
        return _wound_dice(reg, aview, w, n, wd)
    v0 = replace(aview, model=i, weapon_range=w.range)
    unstoppable = any(e.primitive == "ignore_negative_mods" and
                      E.applies(h.sem, e, v0) for h, _, e in entries)
    mods = _Mods()
    for key, prim, val, label in foreign:
        mods.add(key, prim, val, True, label)
    # Range first: Smash's "half of this weapon's range" needs it.
    rmods = _Mods()
    for h, k, e in entries:
        if e.primitive == "range_mod" and E.applies(h.sem, e, v0):
            val = _value(e, h, warnings)
            if val is not None:
                rmods.add((h.sem.rule_id, k), "range_mod", val, False,
                          h.source)
    rng = 0 if w.melee else _range(w.range + rmods.total("range_mod"),
                                   mods, unstoppable)
    model_natives = {h.sem.handler for h in aview.holds[i] if h.sem.handler}
    why = _excluded(ctx, w, natives, rng,
                    "indirect_any_action" in model_natives)
    if why:
        return None, why
    v1 = replace(v0, weapon_range=rng)
    for h, k, e in entries:
        if e.primitive != "range_mod" and E.applies(h.sem, e, v1):
            val = _value(e, h, warnings)
            if val is not None:
                mods.add((h.sem.rule_id, k), e.primitive, val,
                         h.ref.foreign, h.source)           # debuffs
    if ctx.spotter_tokens:
        mods.add(("spotter", 0), "hit_mod", ctx.spotter_tokens, False,
                 "Spotter tokens")
    if ctx.ap_spotter_tokens:
        mods.add(("spotter", 1), "ap_mod", ctx.ap_spotter_tokens, False,
                 "Piercing Spotter tokens")
    quality = min([cm.quality] + [v for p, v, _, _ in mods.vals.values()
                                  if p == "quality_set"])
    spec = AttackSpec(
        attacks=n * w.attacks, quality=quality,
        auto_hit=ctx.attack == "spell",
        hit_mod=mods.total("hit_mod", unstoppable),
        fatigued=(aview.holder.fatigued or aview.holder.shaken)
        and ctx.melee,
        extra_hits_on_6=mods.total("extra_hit_on_6"),
        extra_attack_on=min(mods.kept("extra_attack_on", False),
                            default=0),
        ap=mods.total("ap_mod", unstoppable), ap_on_6=mods.total("ap_on_6"),
        blast=_rating(natives["blast"], warnings) if "blast" in natives else 1,
        deadly=_rating(natives["deadly"], warnings)
        if "deadly" in natives else 1,
        reroll_defense_6=mods.any("reroll_defense_6"),
        reroll_defense_on=min(mods.kept("reroll_defense_on", False),
                              default=0),
        auto_sixes=ctx.attack == "spell" and ctx.spell_sixes,
        self_wounds_on_1=0 if "hazardous" not in natives else max(
            1, _rating(natives["blast"], warnings) if "blast" in natives
            else 1, _rating(natives["deadly"], warnings)
            if "deadly" in natives else 1),
        shred=mods.total("extra_wound_on_def_1"),
        scourge=mods.total("scourge"),
        ignores_regen=mods.any("ignore_regen"), name=w.name,
        fatigue_on=reg.game.get("fatigue_hit_on", 6),
        **game_auto(reg.game))                         # semantics.json 'game'
    nocover = "blast" in natives or mods.any("ignore_cover") or (
        "indirect" in natives and ctx.action == "hold"
        and ctx.cover == "sight_blocker") or ctx.crossing
    srcs = mods.sources(unstoppable) + rmods.sources(False) + tuple(
        f"{h.source}" for k, h in sorted(natives.items())
        if k in ("blast", "deadly", "takedown", "indirect", "limited"))
    flags = ("takedown" in natives, "limited" in natives,
             "counter" in natives or "counter" in model_natives,
             ctx.melee and ctx.action == "charge" and (
                 "unwieldy" in natives or "unwieldy" in model_natives))
    pierce = mods.any("ignore_defense_bonus")
    dm = sum(v for v in mods.kept("defense_mod", unstoppable)
             if not (pierce and v > 0))
    return (spec, nocover, flags, srcs, dm, pierce), None


def _dice_hits(reg, aview, w, n, held):
    """Dice that each give one hit on 'on'+ (no modifier) with a fixed AP,
    blocked as usual: Surprise Attack(X) at the first activation, read as
    a once-per-game shooting weapon within its range."""
    ctx = aview.ctx
    if ctx.attack != "shooting" or ctx.crossing:
        return None, "ranged weapon"
    if w.range < ctx.distance:                  # any action: at activation
        return None, f'out of range ({w.range}")'
    if not ctx.line_of_sight:
        return None, "no line of sight"
    p = dict(held.sem.params)
    spec = AttackSpec(attacks=n * w.attacks, quality=p.get("on", 2),
                      ap=p.get("ap", 0), name=w.name, **game_auto(reg.game))
    return (spec, False, (False, True, False, False), (held.source,), 0,
            False), None


def _wound_dice(reg, aview, w, n, held):
    """A wound-dice weapon (data.rule_weapons): X dice, each 'on'+ (no
    modifier) one wound with no Defense roll; Regeneration and wards
    apply. Ravage strikes in melee unless its unit is Fatigued (a Shaken
    unit strikes as Fatigued); Crossing Attack only in a crossing attack."""
    ctx, p = aview.ctx, dict(held.sem.params)
    if p.get("trigger") == "crossing":
        if not ctx.crossing:
            return None, f"{held.sem.name}: only when moving through enemies"
    else:
        if not ctx.melee or ctx.crossing:
            return None, "melee weapon"
        if aview.holder.fatigued or aview.holder.shaken:
            return None, f"{held.sem.name}: not when Fatigued"
    if "tokens" in p:                   # dice = tokens, the user's
        k = dict(ctx.versatile).get(held.sem.rule_id)
        if k is None:
            return None, f"{held.sem.name}: no token"
        n *= k + 1
    spec = AttackSpec(attacks=n * w.attacks, quality=p.get("on", 6),
                      name=w.name, no_block=True, **game_auto(reg.game))
    return (spec, True, (False, False, False), (held.source,), 0,
            False), None


def _range(own: int, mods, unstoppable: bool) -> int:
    """Effective range: the weapon's range with its own side's modifiers
    ('own'), then the target's (foreign) ones; a target's range_floor
    stops its reductions at N", never below 'own' if 'own' is shorter."""
    rng = own + mods.total("range_mod", unstoppable)
    floors = [v for p, v, f, _ in mods.vals.values() if p == "range_floor"]
    if floors and rng < own:
        rng = max(rng, min(own, max(floors)))
    return max(0, rng)


# --- activation bars ----------------------------------------------------

def _limits(holds) -> list[tuple[str, dict]]:
    """(name, params) of the action_limit rules held by any model (the
    unit moves as one), once per rule."""
    seen: dict = {}
    for hs in holds:
        for h in hs:
            if h.sem.handler == "action_limit":
                seen.setdefault(h.sem.rule_id,
                                (h.sem.name, dict(h.sem.params)))
    return list(seen.values())


def _bar(ctx: AttackContext, attacker: Combatant, a_holds, t_holds):
    """Why 'attacker' cannot make this attack at all, or None."""
    if ctx.attack == "spell" or ctx.action is None:
        return None
    if attacker.shaken:
        return "Shaken: must stay idle"
    for name, p in _limits(a_holds):
        acts = p.get("actions", ACTIONS)
        if ctx.action not in acts:
            return f"{name}: may only use " + \
                " / ".join(a.title() for a in acts) + " actions"
        if not ctx.melee and ctx.action != "hold" and \
                not p.get("shoot_when_moving", True):
            return f"{name}: can't shoot when moving"
    if ctx.charging:
        for name, p in _limits(t_holds):
            if not p.get("chargeable", True):
                return f"the target ({name}) can't be charged"
    return None


def action_bar(reg: RuleRegistry, unit: Combatant, action: str) -> str | None:
    """Why the unit's permanent action limits forbid 'action' (a move
    without attack), or None."""
    defs = tuple(m.defense for m in unit.models)
    holds, _ = E.holdings(reg, E.View(reg, AttackContext(action=action),
                                      "attacker", unit, (), unit, defs))
    for name, p in _limits(holds):
        acts = p.get("actions", ACTIONS)
        if action not in acts:
            return f"{name}: may only use " + \
                " / ".join(a.title() for a in acts) + " actions"
    return None


def activation_bar(reg: RuleRegistry, attacker: Combatant, target: Combatant,
                   ctx: AttackContext) -> str | None:
    """Why 'attacker' cannot attack 'target' in 'ctx' at all (None: it
    can)."""
    a_def = tuple(m.defense for m in attacker.models)
    t_def = tuple(m.defense for m in target.models)
    t_holds, _ = E.holdings(reg, E.View(reg, ctx, "defender", target, (),
                                        attacker, a_def))
    a_holds, _ = E.holdings(reg, E.View(reg, ctx, "attacker", attacker, (),
                                        target, t_def))
    return _bar(ctx, attacker, a_holds, t_holds)


def build_plan(reg: RuleRegistry, attacker: Combatant, target: Combatant,
               ctx: AttackContext) -> AttackPlan:
    """Every weapon of 'attacker' against 'target' in 'ctx'."""
    warnings: set = set()
    a_def0 = tuple(m.defense for m in attacker.models)
    tview = E.View(reg, ctx, "defender", target, (), attacker, a_def0)
    t_holds, miss = E.holdings(reg, tview)
    tview = replace(tview, holds=t_holds)
    warnings |= miss
    t_def = _target_defenses(tview, warnings)
    aview = E.View(reg, ctx, "attacker", attacker, (), target, t_def)
    a_holds, miss = E.holdings(reg, aview)
    aview = replace(aview, holds=a_holds)
    warnings |= miss
    foreign, per_model_dmod = _defender_effects(tview, warnings)
    regen, regen_on = regeneration(tview)
    ward_ons = wards(tview, ctx.attack == "spell")
    cover = reg.game.get("cover_defense_bonus", 1)
    bar = _bar(ctx, attacker, a_holds, t_holds)

    groups: dict = {}
    excluded: dict = {}
    for i, cm in enumerate(attacker.models):
        for w, n in cm.model.weapons:
            res, why = (None, bar) if bar else \
                _one(reg, aview, i, w, n, foreign, warnings)
            if why:
                excluded.setdefault((w.name, why), []).append(i)
                continue
            spec, nocover, flags, srcs, dm, pierce = res   # dm: both sides
            if ctx.cover and ctx.attack == "shooting" and not nocover \
                    and not pierce:
                dm += cover
            targets = tuple(TargetSpec(
                d, dm + (min(0, per_model_dmod[k]) if pierce
                         else per_model_dmod[k]), regen, regen_on,
                wards=ward_ons, **game_auto(reg.game))
                for k, d in enumerate(t_def))
            key = (w, replace(spec, attacks=0), targets, flags, srcs)
            models, attacks = groups.get(key, ((), 0))
            groups[key] = (models + (i,), attacks + spec.attacks)
    out = tuple(AttackGroup(k[0], models, replace(k[1], attacks=att), k[2],
                            *k[3], sources=k[4])
                for k, (models, att) in groups.items())
    exc = tuple((name, why, tuple(ms)) for (name, why), ms in excluded.items())
    return AttackPlan(out, exc, tuple(sorted(warnings)), bar)
