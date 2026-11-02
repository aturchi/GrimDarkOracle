"""Unpredictable rules (Unpredictable, Unpredictable Fighter / Shooter):
"roll one die and apply one effect to all models with this rule: on a
1-3 they get AP(+1), on a 4-6 +1 to hit".

One die per unit and attack (a shooting, or a whole melee exchange for
each of the two units). The choices are a Versatile-like menu (handler
'unpredictable', param 'choices'), passed to the engine in
AttackContext.versatile; each choice covers 'odds' faces of the die
(default: the six faces split evenly). The Analyzer mixes the exact
results of every outcome by their probability (app.mixture). No tkinter.
"""
from dataclasses import replace
from fractions import Fraction
from itertools import product

from grimdarkoracle.engine.modifiers import menu_items
from grimdarkoracle.rules import effects as E


def menus(reg, unit, other, ctx) -> list[tuple[str, str, tuple[int, ...]]]:
    """(rule id, name, faces per choice) of the Unpredictable rules held
    by the models of 'unit' (auras included) or given to its weapons by a
    Mark on the target in 'ctx', that apply to its attacks in
    'ctx'."""
    defs = tuple(m.defense for m in other.models)
    view = E.View(reg, ctx, "attacker", unit, (), other, defs)
    holds, _ = E.holdings(reg, view)
    view = replace(view, holds=holds)
    out, seen = [], set()
    pairs = [(k, h) for k, hs in enumerate(holds) for h in hs]
    pairs += [(0, g) for g in (_mark_grants(reg, mid, replace(view, model=0))
                               for mid in ctx.marks) if g is not None]
    for k, h in pairs:
        sem = h.sem
        if sem.handler != "unpredictable" or sem.rule_id in seen:
            continue
        seen.add(sem.rule_id)
        if not E.check(sem.conditions, replace(view, model=k),
                       sem.rule_id):
            continue
        n = len(menu_items(sem))
        odds = tuple(dict(sem.params).get("odds", ())) or \
            tuple(6 // n + (i < 6 % n) for i in range(n))
        out.append((sem.rule_id, sem.name, odds))
    return out


def _mark_grants(reg, mark_id, view):
    """The Unpredictable rule a Mark gives the attacking weapons, as a
    Held, or None."""
    sem = reg.lookup(E.mark_parts(mark_id)[0])
    if sem is None or sem.handler != "mark":
        return None
    for eff in sem.effects:
        if eff.primitive == "grant_rule" and E.applies(sem, eff, view):
            g = reg.lookup(eff.value["rule"])
            if g is not None and g.handler == "unpredictable":
                return E.Held(E.RuleRef(g.rule_id, g.name), g,
                              f"{g.name} (via {sem.name})")
    return None


def outcomes(menus_) -> list[tuple[Fraction, tuple[tuple[str, int], ...]]]:
    """(probability, choices) of every combination of the dice."""
    out = []
    for combo in product(*(range(len(o)) for _r, _n, o in menus_)):
        p = Fraction(1)
        for (_r, _n, odds), k in zip(menus_, combo):
            p *= Fraction(odds[k], 6)
        out.append((p, tuple((rid, k) for (rid, _n, _o), k in
                             zip(menus_, combo))))
    return out
