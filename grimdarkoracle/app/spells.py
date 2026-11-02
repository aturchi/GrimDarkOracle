"""Spells in the Analyzer: the casting roll, the damage spell as a
fixed-hits weapon, and the buff spells as changes to the attack. Pure.

- Casting: one die + modifiers >= cast_on (Caster params, 4); 6
  always succeeds, 1 always fails; modifiers: Spell Amplifier and other
  cast_mod effects of the caster's side (once per rule, highest), +1 per
  friendly token, -1 per enemy token. Tokens are not tracked.
- Damage spells: a bare caster with one weapon carrying the
  spell's hits and rules, in an attack of type "spell" (fixed hits, no
  cover, no range check); the caster's own rules do not touch the hits.
- Buff spells: assumed cast. Marks of the attacker's book go into
  the context; grants of the attacker's book go on the attacker's unit,
  grants of the target's book on the target's unit, for this attack.
"""
from dataclasses import dataclass, replace

from grimdarkoracle.data.af_book import RuleRef, Weapon
from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine.specs import game_auto
from grimdarkoracle.rules import vocab as V
from grimdarkoracle.rules.coverage import used_rules

DEFAULT_CAST_ON = 4


@dataclass(frozen=True)
class SpellPlan:
    """What analyzer_core needs to resolve a damage spell."""
    name: str
    weapon: Weapon
    p_cast: object                  # probability of a successful cast
    roll_sixes: bool = False        # fixed hits rolled for 6s


@dataclass(frozen=True)
class Buff:
    side: str                       # "att": attacker's book; "def": target's
    key: str
    label: str
    kind: str                       # mark / grant


def _holds(reg, unit, handler=None, primitive=None):
    """(rule id, rating or effect value) of the rules held by the unit's
    models (unit rules and items) matching a handler or a primitive."""
    out = []
    for m in unit.models:
        for r in m.rules:
            sem = reg.lookup(r.id, r.name)
            if sem is None or sem.handler in V.TOKEN_HANDLERS:
                continue                    # a token rule: not its holder's
            if handler and sem.handler == handler:
                out.append((sem.rule_id, r.rating))
            if primitive:
                out += [(sem.rule_id, e.value) for e in sem.effects
                        if e.primitive == primitive]
    return out


def caster_group(reg, unit) -> int:
    """Caster Group: Caster(X) with X = the models of 'unit' holding it."""
    n = 0
    for i in range(len(unit.models)):
        for r in unit.models[i].rules:
            sem = reg.lookup(r.id, r.name)
            if sem is not None and sem.handler == "caster_group":
                n += 1
                break
    return n


def caster_rating(reg, unit, hero=None) -> int:
    """Highest Caster(X) of the side (0: no caster); Caster Group counts
    as Caster(models holding it)."""
    vals = [r for u in (unit, hero) if u is not None
            for _id, r in _holds(reg, u, handler="caster")
            if isinstance(r, int)]
    return max(vals + [caster_group(reg, unit)], default=0)


def conduit_mod(reg) -> int:
    """Casting modifier of a cast through a friendly Spell Conduit (its
    entry's 'cast_mod', 0 without the entry)."""
    return next((dict(e.params).get("cast_mod", 0)
                 for e in reg.entries.values()
                 if e.handler == "spell_conduit"), 0)


def cast_mod(reg, unit, hero=None) -> int:
    """Casting modifier of the side: each cast_mod rule once, highest."""
    best: dict = {}
    for u in (unit, hero):
        if u is not None:
            for rid, v in _holds(reg, u, primitive="cast_mod"):
                if isinstance(v, int):
                    best[rid] = max(best.get(rid, v), v, key=abs)
    return sum(best.values())


def cast_prob(reg, unit, hero=None, friendly: int = 0, enemy: int = 0,
              exact: bool = False, conduit: bool = False):
    """P(the spell is cast); conduit: cast through a friendly Spell
    Conduit."""
    on = next((dict(e.params).get("cast_on", DEFAULT_CAST_ON)
               for e in reg.entries.values() if e.handler == "caster"),
              DEFAULT_CAST_ON)
    mod = cast_mod(reg, unit, hero) + friendly - enemy + \
        (conduit_mod(reg) if conduit else 0)
    a = game_auto(reg.game)                     # semantics.json 'game'
    return G._p(G.success_faces(on, mod, (a["auto_success"],
                                          a["auto_fail"])), 6, exact)


def plan(sem, reg, unit, hero=None, friendly: int = 0, enemy: int = 0,
         exact: bool = False, conduit: bool = False) -> SpellPlan:
    """SpellPlan of a damage spell (rules.spells.SpellSem) cast by the
    side (unit, hero)."""
    if sem.kind != "damage":
        raise ValueError(f"{sem.name} is not a damage spell")
    # The spell's range is the weapon's: Smash reads it.
    w = Weapon(sem.name, 1, sem.range, sem.hits, sem.rules,
               f"{sem.name} ({sem.hits} hits)")
    return SpellPlan(sem.name, w, cast_prob(reg, unit, hero, friendly,
                                            enemy, exact, conduit),
                     sem.roll_sixes)


# --- buff rules (Regeneration Buff...) ---------------------------------

RULE_BUFF = "rule:"                 # key of a buff / debuff rule toggle


def rule_buff_grants(reg, rule_id: str) -> list:
    """Grants ((RuleRef, "models", attack) triples) of a buff or debuff
    RULE: the rules its grant_rule effects give the unit, and its own
    effects as the pseudo-rule '<id>#effect'; param 'attack'
    limits them to one attack type."""
    sem = reg.lookup(rule_id)
    if sem is None or sem.handler not in ("buff", "debuff"):
        return []
    attack = dict(sem.params).get("attack")
    out = []
    for e in sem.effects:
        if e.primitive != "grant_rule":
            continue
        d = reg.defs.get(e.value["rule"])
        name = d.name if d else e.value["rule"]
        out.append((RuleRef(e.value["rule"], name, None, name), "models",
                    attack))
    eff = reg.lookup(rule_id + V.EFFECT_SUFFIX)  # its own effects
    if eff is not None:
        out.append((RuleRef(eff.rule_id, sem.name, None, sem.name),
                    "models", attack))
    return out


def rule_buffs(reg, book, handler: str = "buff") -> list[tuple[str, str]]:
    """(rule id, name) of the buff (or 'debuff') rules the units of 'book'
    can hold."""
    out = {}
    for rid, (name, _units) in used_rules(book).items():
        sem = reg.lookup(rid, name)
        if sem is not None and sem.handler == handler:
            out[sem.rule_id] = sem.name
    return sorted(out.items(), key=lambda x: x[1])


# --- buff spells --------------------------------------------------------


def buff_menu(sreg, att_book, def_book) -> list[Buff]:
    """Buff toggles: marks and grants of the attacker's book, grants of the
    target's book (they protect the target; grants that only add weapon
    rules for shooting are left out, the target never shoots here); the
    debuff rules of each book, which go on the OTHER side."""
    out = []
    for side, book, kinds in (("att", att_book, ("mark", "grant", "debuff")),
                              ("def", def_book, ("grant", "debuff"))):
        if book is None:
            continue
        out += [Buff(side, RULE_BUFF + rid, f"{name} (rule)", "grant")
                for rid, name in rule_buffs(sreg.reg, book)]
        out += [Buff(side, RULE_BUFF + rid, f"{name} (rule, on the "
                     f"{'target' if side == 'att' else 'attacker'})",
                     "debuff")
                for rid, name in rule_buffs(sreg.reg, book, "debuff")]
        for s in sreg.spells(book):
            if s.kind not in kinds or (side == "def" and _shooting_only(s)):
                continue
            label = f"{s.name} ({s.kind})" if s.kind != "debuff" else \
                f"{s.name} (debuff, on the " \
                f"{'target' if side == 'att' else 'attacker'})"
            out.append(Buff(side, s.key, label, s.kind))
    return out


def _shooting_only(sem) -> bool:
    """A grant that only adds weapon rules for shooting: useless to the
    target, which never shoots in an analysis."""
    return bool(sem.grants) and all(to == "weapons" and a == "shooting"
                                    for _r, to, a in sem.grants)


def _add_rule(rules, ref):
    return rules if any(r.id == ref.id for r in rules) else rules + (ref,)


def grant(unit, grants, attack: str):
    """'unit' (ResolvedUnit) with the rules of 'grants' ((RuleRef, to,
    attack-or-None) triples) added to every model or every weapon; a grant
    limited to another attack type is skipped."""
    if unit is None:
        return None
    to_models = [r for r, to, a in grants if to == "models"
                 and a in (None, attack)]
    to_weapons = weapon_grants(grants, attack)
    if not (to_models or to_weapons):
        return unit
    models = []
    for m in unit.models:
        rules = m.rules
        for r in to_models:
            rules = _add_rule(rules, r)
        weapons = tuple((grant_weapon(w, to_weapons), n) for w, n in m.weapons)
        models.append(replace(m, rules=rules, weapons=weapons))
    return replace(unit, models=tuple(models))


def weapon_grants(grants, attack: str) -> list:
    """The RuleRefs of 'grants' that go on weapons in this attack."""
    return [r for r, to, a in grants
            if to == "weapons" and a in (None, attack)]


def grant_weapon(w, refs):
    """Weapon 'w' with the rules 'refs' added (a weapon switched off by the
    user is mapped the same way, so it stays off)."""
    rules = w.rules
    for r in refs:
        rules = _add_rule(rules, r)
    return w if rules == w.rules else replace(w, rules=rules)
