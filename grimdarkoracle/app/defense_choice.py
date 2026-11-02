"""The target's own choices against an attack: Versatile Defense.

A Versatile rule with DEFENDER-side effects is the target's pick (each time
it is attacked). The Analyzer takes the choice from
the context (AttackContext.versatile, by rule id); when none is given, the
program picks the one that minimises the attacker's expected kills (ties:
P(destroyed), then the first choice), via an 'evaluate' callback that runs
the attack with a given context. Menus whose effects cannot apply to this
attack (shot within 9", strike back...) are not offered and need no pick.
No tkinter.
"""
from dataclasses import replace
from itertools import product

from grimdarkoracle.engine.modifiers import menu_items
from grimdarkoracle.rules import effects as E


def _label(sem, k: int, items) -> str:
    label, ix = items[k]
    e = sem.effects[ix[0]]
    return label or f"{e.primitive} {e.value}"


BEST = "best"                       # the program picks (shown first)


def menus(reg, target, attacker, ctx, check: bool = True
          ) -> list[tuple[str, str, list[str]]]:
    """(rule id, name, choice labels) of the target's defender-side
    Versatile rules (auras included) whose effects can apply to this
    attack; check=False lists them all (a panel built once per target)."""
    defs = tuple(m.defense for m in attacker.models)
    view = E.View(reg, ctx, "defender", target, (), attacker, defs)
    holds, _ = E.holdings(reg, view)
    view = replace(view, holds=holds)
    out, seen = [], set()
    for k, hs in enumerate(holds):
        for h in hs:
            sem = h.sem
            if sem.handler != "versatile" or sem.rule_id in seen or \
                    not any(e.side == "defender" for e in sem.effects):
                continue
            seen.add(sem.rule_id)
            v = replace(view, model=k)
            if check and not any(E.applies(sem, e, v) for e in sem.effects):
                continue
            items = menu_items(sem)
            out.append((sem.rule_id, sem.name,
                        [_label(sem, i, items) for i in range(len(items))]))
    return out


def is_state(reg, rule_id: str) -> bool:
    """A menu of game state (tokens gained so far: Defensive Frenzy), not a
    pick: never chosen for the target; none = no token."""
    sem = reg.entries.get(rule_id)
    return bool(sem and dict(sem.params).get("state"))


def pick(reg, target, attacker, ctx, evaluate):
    """(context with a choice for every open target menu, notes). Menus
    already chosen in ctx.versatile are kept. evaluate(ctx) -> (expected
    models killed, P(destroyed)) of the attack with that context."""
    chosen = dict(ctx.versatile)
    open_ = [m for m in menus(reg, target, attacker, ctx)
             if m[0] not in chosen and not is_state(reg, m[0])]
    if not open_:
        return ctx, []
    best = None
    for combo in product(*(range(len(labels)) for _r, _n, labels in open_)):
        c = replace(ctx, versatile=tuple(ctx.versatile) + tuple(
            (rid, k) for (rid, _n, _l), k in zip(open_, combo)))
        score = evaluate(c)
        if best is None or score < best[0]:
            best = (score, c, combo)
    notes = [f"{name}: {labels[k]} (picked as the best for the target)"
             for (_r, name, labels), k in zip(open_, best[2])]
    return best[1], notes


def mean(law) -> float:
    """Expected value of a law (list of probabilities by value)."""
    return sum(i * p for i, p in enumerate(law))
