"""Army composition checks of the GF 3.6 core rules.

Always checked: the points limit and Unique Heroes (one copy of each
per army, a rule of the unit, not of Force Org). Force Org
(optional: the list's ``force_org`` flag disables it) - all
limits scale with the points LIMIT of the game, integer division:

- up to 1 Hero per 500 pts;
- up to 1+X copies of the same unit, X = 1 per 1000 pts (a combined unit
  counts as one copy);
- no single unit worth over 35% of the points;
- max 1 unit per 200 pts (a combined unit or a joined Hero is one entry);
- max 1 model or Tough per 20 pts: each model counts max(1, its Tough).
"""
from dataclasses import dataclass

from grimdarkoracle.data.list_resolve import is_hero, is_unique


@dataclass(frozen=True)
class Violation:
    kind: str          # points, unique, heroes, copies, unit_share,
                       # units, models
    message: str
    keys: tuple[str, ...] = ()
    force_org: bool = True   # False: always enforced


def limits(points_limit: int) -> dict:
    """The numeric limits for a game of 'points_limit' points."""
    return {"heroes": points_limit // 500,
            "copies": 1 + points_limit // 1000,
            "unit_points": points_limit * 35 // 100,
            "units": points_limit // 200,
            "models": points_limit // 20}


def check(army, result) -> list[Violation]:
    """Violations of 'army' given its ListResult. Force Org violations are
    returned only when army.force_org is set."""
    out = []
    total = result.points
    if total > army.points_limit:
        out.append(Violation("points", f"{total} pts exceed the limit of "
                             f"{army.points_limit}", (), force_org=False))
    entries = [(lu, result.entries[lu.key]) for lu in army.units
               if result.entries[lu.key].unit is not None]
    copies: dict = {}
    for lu, e in entries:
        copies.setdefault((lu.book, e.unit.unit_id), []).append(lu.key)
    for keys in copies.values():
        unit = result.entries[keys[0]].unit
        if len(keys) > 1 and is_unique(unit):
            out.append(Violation("unique", f"{len(keys)} copies of "
                                 f"{unit.name}, a Unique Hero (max 1)",
                                 tuple(keys), force_org=False))
    if not army.force_org:
        return out
    lim = limits(army.points_limit)

    heroes = [lu.key for lu, e in entries if is_hero(e.unit)]
    if len(heroes) > lim["heroes"]:
        out.append(Violation("heroes", f"{len(heroes)} Heroes, max "
                             f"{lim['heroes']}", tuple(heroes)))

    for keys in copies.values():
        if len(keys) > lim["copies"]:
            name = result.entries[keys[0]].unit.name
            out.append(Violation("copies", f"{len(keys)} copies of {name}, "
                                 f"max {lim['copies']}", tuple(keys)))

    for lu, e in entries:
        if e.unit.points > lim["unit_points"]:
            out.append(Violation("unit_share", f"{e.unit.name}: "
                                 f"{e.unit.points} pts, max "
                                 f"{lim['unit_points']} (35%)", (lu.key,)))

    if len(entries) > lim["units"]:
        out.append(Violation("units", f"{len(entries)} units, max "
                             f"{lim['units']}"))

    models = sum(max(1, m.tough) for _, e in entries for m in e.unit.models)
    if models > lim["models"]:
        out.append(Violation("models", f"{models} models/Tough, max "
                             f"{lim['models']}"))
    return out
