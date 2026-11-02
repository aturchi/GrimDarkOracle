"""Weapons that a model's rule gives it.

Takedown Strike(X): "once per game, when it's this model's turn to strike
in melee, it may make X attacks at Quality 2+ with AP(2), Deadly(3), and
Takedown"; Takedown Shot(X): the same "when this model shoots ... against
the target". Each becomes a Limited weapon of the model, named after the
rule, so every program sees it like a book weapon (lists, weapon order,
Takedown aims, Limited weapons used up, sheets). Recognised by NAME like
Tough and Hero; the profile carries the core rules by their
global ids. Takedown Shot has no range of its own: it takes the longest
range of the model's ranged weapons (it attacks when the model shoots), and
a model without a ranged weapon does not get it.

Ravage(X) and Crossing Attack(X): X "wound dice" (each
6+ a wound with no Defense roll), a range-0 weapon carrying the rule
itself, whose semantics (handler wound_dice) tell the engine how it
strikes; Ravage comes first among the model's weapons ("before
attacking"); "once per round" is one use in the Analyzer's one exchange.

Auras giving a rule weapon: Ravage Aura, "this model and
its unit get Ravage(+1)", gives every model of the resolved unit (a
Combined Unit: both copies; a joined Hero and its host through
engine.context.combatant) Ravage(X+1), X = the model's own Ravage rating
(0 without one).
"""
from dataclasses import replace

from grimdarkoracle.data.af_book import RuleRef, Weapon

# Core rule ids (/api/rules/common/2; global in Army Forge)
_CORE = (("Zx4mWN0SbmK8", "Reliable", None), ("17crjK7P6_w6", "AP", 2),
         ("_mrPya5SXSqW", "Deadly", 3), ("8Hjy54TYtwb7", "Takedown", None),
         ("9042COVrLCsI", "Limited", None))
RULES = tuple(RuleRef(rid, name, r, name if r is None else f"{name}({r})")
              for rid, name, r in _CORE)
MELEE, RANGED, DICE = "melee", "ranged", "dice"
TOKENS = "tokens"                   # one die per token: the count is an
                                    # Analyzer input, not a rating
PROFILES = {"Takedown Strike": MELEE, "Takedown Shot": RANGED,
            "Ravage": DICE, "Crossing Attack": DICE,
            "Regenerative Strength": TOKENS, "Surprise Attack": "near"}
NEAR = 6                            # Surprise Attack: an enemy within 6"
FIRST = ("Ravage", "Regenerative Strength")     # "before attacking"
# aura name -> (granted rule id, its name, rating step)
AURAS = {"Ravage Aura": ("hnsVQyx3ylMf", "Ravage", 1)}


def weapon_for(rule: RuleRef, weapons) -> Weapon | None:
    """The weapon 'rule' gives a model carrying 'weapons', or None."""
    kind = PROFILES.get(rule.name)
    if kind == TOKENS:
        return Weapon(rule.name, 1, 0, 1, (rule,), label=rule.name)
    if kind is None or not isinstance(rule.rating, int) or rule.rating < 1:
        return None
    if kind in (DICE, "near"):
        return Weapon(rule.name, 1, NEAR if kind == "near" else 0,
                      rule.rating, (rule,),
                      label=f"{rule.name} ({rule.label or rule.name})")
    if kind == MELEE:
        rng = 0
    else:
        ranges = [w.range for w, _n in weapons if not w.melee]
        if not ranges:
            return None
        rng = max(ranges)
    return Weapon(rule.name, 1, rng, rule.rating, RULES,
                  label=f"{rule.name} ({rule.label or rule.name})")


def unit_auras(models) -> tuple:
    """(rule id, name, step) of the AURAS held by any of 'models'."""
    names = {r.name for m in models for r in m.rules}
    return tuple(AURAS[n] for n in sorted(names) if n in AURAS)


def _with_auras(rules, auras) -> list:
    """The model's rules with each aura's rule at its own rating + step."""
    out = list(rules)
    for rid, name, step in auras:
        own = [r for r in out if r.name == name]
        x = max((r.rating for r in own if isinstance(r.rating, int)),
                default=0) + step
        out = [r for r in out if r.name != name] + [
            RuleRef(own[0].id if own else rid, name, x, f"{name}({x})")]
    return out


def add(model, auras=()):
    """ResolvedModel with the weapons of its rules and of its unit's
    'auras' (idempotent: a weapon named after the rule is added once, and
    replaced when its profile changed, e.g. a Combined Unit's aura)."""
    weapons = list(model.weapons)
    first, extra, done = [], [], set()
    for r in _with_auras(model.rules, auras):
        w = weapon_for(r, model.weapons)
        if w is None or w.name in done:     # first rule of a name wins
            continue
        done.add(w.name)
        at = next((i for i, (x, _n) in enumerate(weapons)
                   if x.name == w.name), None)
        if at is None:
            (first if w.name in FIRST else extra).append((w, 1))
        elif weapons[at][0] != w:
            weapons[at] = (w, 1)
    weapons = tuple(first) + tuple(weapons) + tuple(extra)
    return model if weapons == model.weapons else \
        replace(model, weapons=weapons)


def add_models(models) -> tuple:
    """The models of one unit with their rule weapons and auras."""
    auras = unit_auras(models)
    return tuple(add(m, auras) for m in models)


def add_all(ru):
    """ResolvedUnit with the rule weapons of every model."""
    models = add_models(ru.models)
    return ru if models == ru.models else replace(ru, models=models)
