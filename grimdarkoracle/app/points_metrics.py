"""Points metrics of an analysis: what the attack is worth
in points, on both sides of the table. Pure functions of the resolved
units and of the end-state laws of the engine.

Value of one model: Army Forge prices units, not models,
so a model is worth an equal share of what the unit paid for everything
not placed on a specific model (base cost, "all models" upgrades, unit
upgrades) plus the upgrades placed on it (ResolvedModel.upgrade_points).
A joined Hero is worth its own unit's points. The values add up to the
points of the unit (and of the Hero): a destroyed unit is worth exactly
its points.

Points removed = value of the models killed by the attack; a wounded
Tough model that survives counts nothing (a wounded model fights at full
strength; the damage shows in the wound metrics). Per 100 pts metrics divide
by the FULL points of the attacking unit (joined Hero included), even if
some of its models were already lost.
"""
from grimdarkoracle.data.resolve import ResolvedUnit
from grimdarkoracle.engine import dist_stats as ds


def model_values(unit: ResolvedUnit, hero: ResolvedUnit | None = None
                 ) -> tuple[float, ...]:
    """Value of each model, in Combatant order (the unit, then the Hero)."""
    placed = sum(m.upgrade_points for m in unit.models)
    share = (unit.points - placed) / unit.size if unit.size else 0.0
    out = [share + m.upgrade_points for m in unit.models]
    if hero is not None:
        out.append(float(hero.points))
    return tuple(out)


def removed_points(values, alloc, start, dist) -> float:
    """Expected value of the models killed between 'start' and the end
    states of 'dist' ({state: p}, alloc = target_state.Allocation)."""
    before = set(alloc.alive(start))
    total = 0.0
    for state, p in dist.items():
        dead = before - set(alloc.alive(state))
        total += float(p) * sum(values[i] for i in dead)
    return total


def per100(value: float, points: int) -> float | None:
    """'value' per 100 points (None without points)."""
    return value * 100.0 / points if points else None


def mean(pmf) -> float:
    return float(sum(v * p for v, p in enumerate(pmf)))


def _pct(x) -> float:
    return float(x) * 100.0


def metrics(a) -> dict:
    """Headline numbers of an analyzer_core.Analysis, all floats: means,
    medians, percentages (0-100) and the points metrics. Keys of the
    charger's own losses and of the melee result are present only for a
    melee analysis."""
    d, pts = a.def_losses, a.attacker.points
    out = {"wounds": mean(d.wounds), "wounds_med": ds.percentile(d.wounds, .5),
           "killed": mean(d.killed), "killed_med": ds.percentile(d.killed, .5),
           "destroyed": _pct(d.destroyed), "test": _pct(d.morale.test),
           "shaken": _pct(d.morale.shaken), "rout": _pct(d.morale.rout),
           "points_removed": d.points_removed}
    out["wounds_per100"] = per100(out["wounds"], pts)
    out["killed_per100"] = per100(out["killed"], pts)
    out["points_per100"] = per100(d.points_removed, pts)
    if getattr(a, "cast", None) is not None:
        out["cast"] = _pct(a.cast)
    if a.att_losses is not None:
        c, w = a.att_losses, a.winner
        out.update({"win": _pct(w.charger), "lose": _pct(w.charged),
                    "tie": _pct(w.none), "att_wounds": mean(c.wounds),
                    "att_killed": mean(c.killed),
                    "att_destroyed": _pct(c.destroyed),
                    "att_shaken": _pct(c.morale.shaken),
                    "att_rout": _pct(c.morale.rout),
                    "att_points_lost": c.points_removed,
                    "points_net": d.points_removed - c.points_removed})
    return out
