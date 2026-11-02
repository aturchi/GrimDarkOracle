"""Rows of the Analyzer's result table, as plain strings (no tkinter), so
the table is tested headless and exported to CSV without the window.

Every column backed by a distribution can be read as a mean, a median or
a percentile; the heading says which (STATS). Nothing is summed down a
column: a TOTAL row reads the side's own laws from the analysis (the
chained attack), so its median or percentile is right, and it is NOT the
sum of the weapon rows above it, which are each weapon ALONE against the
unit at the start.

Layout: shooting = weapon rows, skipped rows, TOTAL. Melee = the
charger's rows (Impact, strikes) and its TOTAL (the charged unit's
losses), then the charged unit's rows (Counter, strike back) and its
TOTAL (the charger's losses). outcome_lines() gives the Morale, melee
result and points metrics under the table.
"""
from dataclasses import dataclass

from grimdarkoracle.app import points_metrics as PM
from grimdarkoracle.engine import dist_stats as ds

STATS = ("mean", "median", "lo", "hi")
STAT_LABEL = dict(zip(("lo", "hi"), ds.SPREAD_LABELS),
                  **{"mean": "\u03bc", "median": "med"})
STAT_Q = {"median": 0.5, "lo": ds.SPREAD[0], "hi": ds.SPREAD[1]}

# key, heading title, column width in pixels
COLUMNS = (("count", "xN", 44),
           ("attacks", "Attacks", 66),
           ("hits", "Hits", 66),
           ("wounds", "Wounds", 72),
           ("killed", "Killed", 66),
           ("destroyed", "Destroyed %", 88),
           ("per100", "Wounds/100pts", 100))
KEYS = tuple(k for k, _t, _w in COLUMNS)
TITLES = {k: t for k, t, _w in COLUMNS}
STAT_KEYS = ("hits", "wounds", "killed")      # columns read off a PMF
PHASE_LABEL = {"shoot": "", "impact": "", "counter": "Counter: ",
               "strike": "", "back": "Strike back: ", "last": "Strikes last: ",
               "spell": "Spell: "}
FLAG_LABEL = {"takedown": "Takedown", "deadly": "Deadly",
              "limited": "Limited", "counter": "Counter"}


@dataclass(frozen=True)
class Row:
    name: str
    cells: tuple[str, ...]          # one per KEYS entry
    kind: str                       # weapon / skipped / total


def next_stat(stat: str) -> str:
    """The statistic a click on the heading moves to."""
    return STATS[(STATS.index(stat) + 1) % len(STATS)] \
        if stat in STATS else STATS[0]


def heading(key: str, stat: str = "mean") -> str:
    title = TITLES.get(key, key)
    return f"{title} {STAT_LABEL[stat]}" if key in STAT_KEYS else title


def _f(x, nd: int = 2) -> str:
    return "" if x is None else f"{float(x):.{nd}f}"


def _stat(pmf, stat: str) -> str:
    """Means keep two decimals; medians and percentiles are values the
    dice can produce, printed as integers."""
    if not pmf:
        return ""
    if stat == "mean":
        return _f(PM.mean(pmf))
    return str(ds.percentile(pmf, STAT_Q[stat]))


def _cells(values: dict, stats) -> tuple[str, ...]:
    stats = stats or {}
    out = []
    for k in KEYS:
        v = values.get(k)
        out.append(_stat(v, stats.get(k, "mean")) if k in STAT_KEYS
                   else ("" if v is None else str(v)))
    return tuple(out)


def weapon_name(r) -> str:
    flags = [FLAG_LABEL[f] for f in r.flags
             if f in FLAG_LABEL and not (f == "counter"
                                         and r.phase == "counter")]
    tail = f"  [{', '.join(flags)}]" if flags else ""
    return f"{PHASE_LABEL.get(r.phase, '')}{r.name}{tail}"


def weapon_row(r, stats=None) -> Row:
    return Row(weapon_name(r), _cells({
        "count": r.count, "attacks": r.attacks, "hits": r.hits,
        "wounds": r.wounds, "killed": r.killed,
        "destroyed": _f(r.destroyed * 100, 1)}, stats), "weapon")


def skipped_row(s) -> Row:
    """A weapon that does not attack: the reason goes with its name (a
    narrow number column would cut it), only the count is shown."""
    return Row(f"{s.name}  ({s.reason})",
               (str(s.count),) + ("",) * (len(KEYS) - 1), "skipped")


def totals_row(a, side: str, stats=None) -> Row:
    """TOTAL of one side: the OTHER unit's losses in the chained attack
    (no hits: see analyzer_core), wounds per 100 pts of this side."""
    loss, pts = (a.def_losses, a.attacker.points) if side == "att" else \
        (a.att_losses, a.target.points)
    rows = [r for r in a.rows if r.side == side and r.phase != "impact"]
    label = "TOTAL" + (f" ({pts} pts)" if pts else "") + f" -> {loss.name}"
    per = PM.per100(PM.mean(loss.wounds), pts)
    return Row(label, _cells({
        "count": sum(r.count for r in rows),
        "wounds": loss.wounds, "killed": loss.killed,
        "destroyed": _f(loss.destroyed * 100, 1),
        "per100": _f(per)}, stats), "total")


def entries(a, stats=None) -> list[tuple[Row, object]]:
    """(Row, source) for the whole table: the source is the WeaponRow, the
    Skipped entry, or ("total", side) - what a view needs to open the
    distribution behind a row (series())."""
    sides = ("att", "def") if a.kind == "melee" else ("att",)
    out = []
    for side in sides:
        out += [(weapon_row(r, stats), r) for r in a.rows if r.side == side]
        out += [(skipped_row(s), s) for s in a.skipped if s.side == side]
        out.append((totals_row(a, side, stats), ("total", side)))
    return out


def table(a, stats=None) -> list[Row]:
    """The whole table of an analyzer_core.Analysis."""
    return [r for r, _src in entries(a, stats)]


def series(a, src) -> list[dict]:
    """Distribution series (dist_view.DistributionFrame) of one source of
    entries(): wounds, models killed and, for a weapon, its hits. Empty
    for a skipped weapon."""
    if isinstance(src, tuple):
        loss = a.def_losses if src[1] == "att" else a.att_losses
        laws = [("wounds", loss.wounds, None), ("killed", loss.killed,
                                                loss.size)]
    elif hasattr(src, "wounds"):
        size = (a.def_losses if src.side == "att" else a.att_losses).size
        laws = [("wounds", src.wounds, None), ("killed", src.killed, size),
                ("hits", src.hits, None)]
    else:
        return []
    names = {"wounds": "wounds inflicted", "killed": "models killed",
             "hits": "hits"}
    return [{"key": k, "label": names[k], "pmf": [float(p) for p in pmf],
             "unit": names[k], "threshold": thr} for k, pmf, thr in laws]


def _morale(tag: str, loss, melee: bool) -> list[tuple[str, str]]:
    m = loss.morale
    out = [(f"{tag} destroyed", _f(loss.destroyed * 100, 1) + " %"),
           (f"{tag} takes a Morale Test", _f(m.test * 100, 1) + " %"),
           (f"{tag} Shaken", _f(m.shaken * 100, 1) + " %")]
    if melee:
        out.append((f"{tag} Routs", _f(m.rout * 100, 1) + " %"))
    if m.held:
        out.append((f"{tag} No Retreat: failed test counted passed",
                    _f(m.held * 100, 1) + " %"))
        out.append((f"{tag} No Retreat: wounds it takes (mean)",
                    _f(sum(k * p for k, p in enumerate(m.self_wounds)), 2)))
    return out


def _hazard_lines(a) -> list[tuple[str, str]]:
    """The attacker's Hazardous wounds to itself."""
    law = getattr(a, "hazard", None)
    if not law:
        return []
    return [("Hazardous: wounds the attacker takes (mean)",
             _f(sum(k * p for k, p in enumerate(law)), 2)),
            ("Hazardous: P(at least one)", _f((1 - law[0]) * 100, 1) + " %")]


def outcome_lines(a) -> list[tuple[str, str]]:
    """(label, value) lines under the table: Morale, melee result and
    points metrics (always means)."""
    v = PM.metrics(a)
    melee = a.kind == "melee"
    out = _morale(a.def_losses.name, a.def_losses, melee)
    if a.cast is not None:
        out.insert(0, ("Spell cast (weapon row: if cast)",
                       _f(v["cast"], 1) + " %"))
    out.append(("Points removed", _f(v["points_removed"], 1)))
    out.append(("Points removed per 100 pts", _f(v["points_per100"], 1)))
    out.append(("Models killed per 100 pts", _f(v["killed_per100"])))
    if melee:
        out = [("Charger wins", _f(v["win"], 1) + " %"),
               ("Charger loses", _f(v["lose"], 1) + " %"),
               ("Tie (nobody tests)", _f(v["tie"], 1) + " %")] + out
        out += _morale(a.att_losses.name, a.att_losses, True)
        out.append(("Charger points lost", _f(v["att_points_lost"], 1)))
        out.append(("Net points (removed - lost)", _f(v["points_net"], 1)))
    return out + _hazard_lines(a)


def _csv(v) -> str:
    v = str(v)
    return '"' + v.replace('"', '""') + '"' if ("," in v or '"' in v) else v


def to_csv(a, stats=None) -> str:
    """Table and outcome lines as CSV; headings carry the statistic."""
    stats = stats or {}
    lines = [",".join(["Weapon"] + [_csv(heading(k, stats.get(k, "mean")))
                                    for k in KEYS])]
    lines += [",".join(_csv(c) for c in (r.name,) + r.cells)
              for r in table(a, stats)]
    lines.append("")
    lines += [f"{_csv(k)},{_csv(v)}" for k, v in outcome_lines(a)]
    return "\n".join(lines) + "\n"
