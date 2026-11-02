"""Weapon order suggestions for the Analyzer: the problem of
engine.best_order built exactly as the attack would be resolved, the
search, and the line shown to the user. Pure.

The shooting or the charger's strikes of an analysis (analyzer_core.Side
x2 + Options, as side_spec.prepare gives them), with the Takedown
preferences of the options; spells: no order.
"""
from grimdarkoracle.engine import best_order as BO
from grimdarkoracle.engine import melee as ML
from grimdarkoracle.engine.sequence import AttackSequence
from grimdarkoracle.engine.target_state import Allocation


def _state(side, cb):
    al = Allocation.of(cb)
    st = al.fresh() if side.wounds is None else al.check(side.wounds)
    if not al.alive(st):
        raise ValueError("no model alive at the start")
    return st


def analyzer(reg, att, tgt, opts, **kw) -> BO.Suggestion | None:
    """Suggestion for an Analyzer attack; None when no order applies
    (a spell, an attack the rules forbid)."""
    if opts.ctx.attack == "spell":
        return None
    acb, tcb = att.combatant(), tgt.combatant()
    a0, t0 = _state(att, acb), _state(tgt, tcb)
    try:
        if opts.ctx.melee:
            setup = ML.MeleeSetup(reg, acb, tcb, opts.strike_back,
                                  charge_ctx=opts.ctx,
                                  aims_att=opts.takedown_targets)
            problem = BO.melee(setup, (a0, t0))
        else:
            shooter = ML.sub(acb, Allocation.of(acb).alive(a0))
            seq = AttackSequence(reg, shooter, tcb, opts.ctx,
                                 opts.takedown_targets)
            problem = BO.shooting(seq, t0)
    except ValueError:
        return None                     # barred
    return BO.search(problem, opts.weapon_order, **kw)


def line(sg: BO.Suggestion | None, current=()) -> str:
    """One line for the results / the order dialogs."""
    if sg is None:
        return ""
    how = "every order checked" if sg.exact else \
        f"{sg.examined} of {sg.total} orders checked, not exhaustive"
    if not sg.improves:
        return (f"Weapon order: the book order is already the best "
                f"({how}).")
    text = (f"Best weapon order: {' > '.join(sg.order)}: expected models "
            f"killed {sg.best.killed:.2f} (book order {sg.book.killed:.2f}, "
            f"{sg.gain:+.2f}")
    if current:
        text += f"; your order {sg.current.killed:.2f}"
    return text + f"; {how})."


def for_dialog(sg: BO.Suggestion | None, current=()) -> tuple:
    """(names first in the suggested order, or None for the book order;
    the line) for ui.order_dialog's Suggest; no suggestion keeps the
    current order."""
    if sg is None:
        return (list(current) or None,
                "No weapon order to suggest for this attack.")
    return (list(sg.order) if sg.improves else None, line(sg, current))
