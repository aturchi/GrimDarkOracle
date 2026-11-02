"""Rules held by the models of a unit, auras included, and the
holder-relative evaluation of semantics.json conditions.

Holding: each model holds its own rules (unit rules + rules of its items);
a ``grant_rule`` effect whose conditions hold gives the granted rule to the
holder model, or to every model of its unit with scope "unit" (auras),
transitively. The same rule entry is held once per model.

Conditions are read from the HOLDER's point of view: "action" / "charging"
are the holder's when it attacks; "charged" is true for a defender being
charged; target_* conditions look at the other unit. "Most models" is a
strict majority of the models alive, also for target_*
conditions, which read the Defense after Armor.
"""
from dataclasses import dataclass, replace

from grimdarkoracle.data.af_book import RuleRef
from grimdarkoracle.rules import vocab as V
from grimdarkoracle.rules.registry import RuleRegistry, Semantic

MAX_GRANT_DEPTH = 4
TOKEN_HANDLERS = V.TOKEN_HANDLERS           # never act on their holder


@dataclass(frozen=True)
class Held:
    ref: RuleRef
    sem: Semantic
    source: str                     # audit label ("X (via Y)" for grants)


@dataclass(frozen=True)
class View:
    """Everything a condition may look at."""
    reg: RuleRegistry
    ctx: object                     # engine.context.AttackContext
    role: str                       # "attacker" | "defender" (the holder)
    holder: object                  # engine.context.Combatant
    holds: tuple                    # per holder model: tuple[Held, ...]
    target: object                  # the other Combatant
    target_defenses: tuple          # per target model, Armor applied
    model: int | None = None        # holder model the effect is for
    weapon_range: int | None = None  # effective range (range_over_half)


def majority(count: int, total: int) -> bool:
    """Strict majority ("most models")."""
    return 2 * count > total


def holders(holds, entry_id: str) -> int:
    """Models holding the semantic entry 'entry_id'."""
    return sum(1 for hs in holds if any(h.sem.rule_id == entry_id
                                        for h in hs))


def _cond(key, val, v: View, entry_id: str) -> bool:
    ctx, atk = v.ctx, v.role == "attacker"
    tm = v.target.models
    match key:
        case "attack":
            return ctx.attack == val
        case "action":
            return atk and ctx.action == val
        case "charging":
            return (atk and ctx.charging) == val
        case "charged":
            return (not atk and ctx.charging) == val
        case "range_over":
            return ctx.dist > val or lifted(v, entry_id)
        case "range_within":
            return ctx.dist <= val
        case "charge_over":
            return (ctx.melee and ctx.action == "charge"
                    and (ctx.charge_distance > val or lifted(v, entry_id)))
        case "ambushed_this_round":
            return (atk and ctx.ambushed) == val
        case "range_over_half":
            r = v.weapon_range or 0
            return (r > 0 and ctx.dist > r / 2) == val
        case "target_tough_min":
            return majority(sum(m.model.tough >= val for m in tm), len(tm))
        case "target_defense_min":
            return majority(sum(d >= val for d in v.target_defenses), len(tm))
        case "target_defense_max":
            return majority(sum(d <= val for d in v.target_defenses), len(tm))
        case "target_in_cover":
            return (ctx.cover is not None) == val
        case "most_models":
            return majority(holders(v.holds, entry_id), len(v.holds)) == val
        case "not_moved":
            return v.holder.not_moved == val
        case "not_fatigued":
            return (not v.holder.fatigued) == val
        case "morale_from":
            return ctx.attack == val    # what triggered the Morale Test
        case "morale_from_combat":
            return (ctx.attack in ("shooting", "melee")) == val
        case "target_shaken_or_fatigued":
            return (v.target.shaken or v.target.fatigued) == val
        case "target_over_half":
            return v.target.over_half == val
        case "near_terrain":
            return v.holder.near_terrain == val
        case "target_near_terrain":
            return v.target.near_terrain == val
        case "most_have_rule":
            return majority(sum(1 for hs in v.holds if any(
                h.sem.rule_id == val or val in v.reg.alias_chain(h.ref.id)
                for h in hs)), len(v.holds))
        case "has_rule":
            hs = v.holds[v.model] if v.model is not None else ()
            return any(h.sem.rule_id == val
                       or val in v.reg.alias_chain(h.ref.id) for h in hs)
    raise ValueError(f"unknown condition {key!r}")


def mark_parts(mark_id: str) -> tuple[str, int | None]:
    """(rule id, tokens) of a Mark toggle: "<id>" or "<id>*k", k tokens
    (Vengeance: +X to hit, X the tokens)."""
    base, _, k = mark_id.partition("*")
    return base, (int(k) if k else None)


def lifted(v: View, entry_id: str) -> bool:
    """A lift_distance effect whose conditions hold, held by the model the
    check is for (any model when none), names this entry or a rule it is
    an alias of: its distance conditions are lifted ("Enhanced ...")."""
    chain = v.reg.alias_chain(entry_id)
    for i in (range(len(v.holds)) if v.model is None else (v.model,)):
        for h in v.holds[i]:
            if any(e.primitive == "lift_distance" and e.value["rule"] in chain
                   for e in h.sem.effects) and check(
                    h.sem.conditions, replace(v, model=i), h.sem.rule_id):
                return True
    return False


def check(conditions, v: View, entry_id: str) -> bool:
    """All 'conditions' ((key, value) pairs) hold."""
    return all(_cond(k, val, v, entry_id) for k, val in conditions)


def applies(sem: Semantic, eff, v: View) -> bool:
    """Entry conditions AND effect conditions."""
    return check(sem.conditions, v, sem.rule_id) and \
        check(eff.conditions, v, sem.rule_id)


def wrap(reg: RuleRegistry, refs, label: str = "") -> tuple[list, set]:
    """Held rules for 'refs' and the names of the rules with no semantics."""
    out, missing = [], set()
    for ref in refs:
        sem = reg.lookup(ref.id, ref.name)
        if sem is None or sem.impl == "todo":
            missing.add(ref.name)
            continue
        if sem.handler in TOKEN_HANDLERS:
            continue
        out.append(Held(ref, sem, (ref.label or ref.name) + label))
    return out, missing


def _grant(reg: RuleRegistry, rule_id: str, via: str,
           foreign: bool = False) -> Held | None:
    """A granted rule; it is foreign when its giver is."""
    sem = reg.lookup(rule_id)
    return Held(RuleRef(rule_id, sem.name, foreign=foreign), sem,
                f"{sem.name} (via {via})") if sem else None


def holdings(reg: RuleRegistry, view: View) -> tuple[tuple, set]:
    """(per-model Held tuples with grants applied, unmapped rule names) of
    view.holder. 'view.holds' is ignored and rebuilt."""
    holds, missing = [], set()
    for cm in view.holder.models:
        hs, miss = wrap(reg, cm.model.rules)
        holds.append(hs)
        missing |= miss
    for _ in range(MAX_GRANT_DEPTH):
        added = False
        for i in range(len(holds)):
            v = View(reg, view.ctx, view.role, view.holder,
                     tuple(map(tuple, holds)), view.target,
                     view.target_defenses, model=i)
            for h in list(holds[i]):
                for eff in h.sem.effects:
                    if eff.primitive != "grant_rule" or \
                            not applies(h.sem, eff, v):
                        continue
                    g = _grant(reg, eff.value["rule"], h.source,
                               h.ref.foreign)
                    if g is None:
                        missing.add(eff.value["rule"])
                        continue
                    for j in (range(len(holds)) if eff.scope == "unit"
                              else (i,)):
                        if not any(x.sem.rule_id == g.sem.rule_id
                                   for x in holds[j]):
                            holds[j].append(g)
                            added = True
        if not added:
            break
    return tuple(map(tuple, holds)), missing
