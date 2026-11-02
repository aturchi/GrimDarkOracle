"""Pinned analyses and the matrix that compares them.

The most repeated gesture at the table is running the same attack twice
with one thing changed - a weapon switched off, cover on, another upgrade
(variants.py) - so a result page can be PINNED, and the pins are lined up
side by side with the difference against the first one.

No tkinter here: a pin is a plain dict of numbers and PMFs, the matrix is
a list of rows, and the CSV is a string. Every pin carries the context
that produced it, and the matrix marks the ones that differ from the
first pin: comparing analyses run under different conditions without
noticing is the easiest way to draw a wrong conclusion.
"""
from grimdarkoracle.app import analyzer_orders as AO
from grimdarkoracle.app import points_metrics as PM

# key, label, decimals (metrics() keys; melee-only keys are skipped when
# no pin has them)
METRICS = (
    ("wounds", "Wounds \u03bc", 2),
    ("wounds_med", "Wounds median", 0),
    ("killed", "Models killed \u03bc", 2),
    ("killed_med", "Models killed median", 0),
    ("cast", "P(spell cast) %", 1),
    ("destroyed", "P(destroyed) %", 1),
    ("test", "P(Morale Test) %", 1),
    ("shaken", "P(Shaken) %", 1),
    ("rout", "P(Rout) %", 1),
    ("points_removed", "Points removed \u03bc", 1),
    ("wounds_per100", "Wounds per 100 pts", 2),
    ("killed_per100", "Models killed per 100 pts", 2),
    ("points_per100", "Points removed per 100 pts", 1),
    ("win", "P(charger wins) %", 1),
    ("lose", "P(charger loses) %", 1),
    ("tie", "P(tie, no test) %", 1),
    ("att_wounds", "Charger wounds taken \u03bc", 2),
    ("att_killed", "Charger models lost \u03bc", 2),
    ("att_destroyed", "P(charger destroyed) %", 1),
    ("att_shaken", "P(charger Shaken) %", 1),
    ("att_rout", "P(charger Rout) %", 1),
    ("att_points_lost", "Charger points lost \u03bc", 1),
    ("points_net", "Net points (removed - lost)", 1),
)


def _side_bits(tag: str, s) -> list[str]:
    bits = []
    if s.wounds is not None and any(s.wounds):
        bits.append(f"{tag} wounded")
    for flag, on in (("moved", not s.not_moved), ("fatigued", s.fatigued),
                     ("shaken", s.shaken), ("near terrain", s.near_terrain),
                     ("Feat used", s.feat_used)):
        if on:
            bits.append(f"{tag} {flag}")
    if s.off:
        bits.append(f"{tag} {len(s.off)} weapon(s) off")
    if s.hero_quality is not None:
        bits.append(f"{tag} Hero Q{s.hero_quality}+ nearby")
    return bits


def context_signature(a) -> str:
    """Everything, besides the two units' profiles, that shaped the
    numbers of an analyzer_core.Analysis, as one short line."""
    c, o = a.opts.ctx, a.opts
    bits = [a.kind]
    if a.kind == "shooting":
        bits += [f'{c.distance}"', c.action or "no action"]
        if c.cover:
            bits.append(f"cover ({c.cover})")
        if not c.line_of_sight:
            bits.append("no line of sight")
        if c.crossing:
            bits.append("crossing")
    elif a.kind == "spell":
        bits += [o.spell.name, f'{c.distance}"']
    else:
        if not o.strike_back:
            bits.append("no strike back")
        bits.append(f"tie: {o.tie}")
    if c.marks:
        bits.append(f"{len(c.marks)} mark(s)")
    if c.spotter_tokens:
        bits.append(f"{c.spotter_tokens} spotter token(s)")
    if c.versatile:
        bits.append(f"{len(c.versatile)} versatile choice(s)")
    if o.weapon_order:
        bits.append(f"weapon order {AO.order_text(o.weapon_order)}")
    if o.takedown_targets:
        bits.append(f"Takedown {AO.takedown_text(o.takedown_targets)}")
    bits += _side_bits("att", a.attacker) + _side_bits("def", a.target)
    return ", ".join(bits)


def make_pin(name: str, analysis, context: str = "") -> dict:
    """Freeze one analysis into a pin: the metrics, the PMFs the
    comparison plots, and the context that produced it ('' = derived)."""
    d = analysis.def_losses
    return {"name": name,
            "context": context or context_signature(analysis),
            "values": PM.metrics(analysis),
            "pmfs": {"wounds": [float(p) for p in d.wounds],
                     "killed": [float(p) for p in d.killed]},
            "points": analysis.attacker.points,
            "target": d.name}


def _fmt(value, nd: int) -> str:
    if value is None:
        return ""
    return f"{value:.{nd}f}" if nd else f"{value:.0f}"


def _delta(value, base, nd: int) -> str:
    """Difference against the first pin, signed ('=' when it rounds to 0)."""
    if value is None or base is None:
        return ""
    d = value - base
    if abs(d) < 0.5 * 10 ** -nd:
        return "="
    return f"{d:+.{nd}f}" if nd else f"{d:+.0f}"


def _metrics(pins):
    return [m for m in METRICS
            if any(p["values"].get(m[0]) is not None for p in pins)]


def matrix(pins, deltas: bool = True) -> list:
    """Rows of the comparison table: (label, [cell per pin]); with deltas
    every column past the first carries its difference to the first pin."""
    rows = []
    for key, label, nd in _metrics(pins):
        base = pins[0]["values"].get(key)
        cells = []
        for i, p in enumerate(pins):
            v = p["values"].get(key)
            text = _fmt(v, nd)
            if deltas and i and text:
                text += f"  ({_delta(v, base, nd)})"
            cells.append(text)
        rows.append((label, cells))
    return rows


def context_rows(pins) -> list:
    """Header rows: what each pin was and whether its context differs
    from the first one."""
    rows = [("Analysis", [p["name"] for p in pins]),
            ("Target", [p.get("target", "") for p in pins])]
    ctx = [p.get("context", "") for p in pins]
    rows.append(("Context", list(ctx)))
    if len(pins) > 1:
        rows.append(("vs first", ["-"] + ["same" if c == ctx[0]
                                          else "DIFFERENT" for c in ctx[1:]]))
    rows.append(("Points", [str(p.get("points") or "") for p in pins]))
    return rows


def summary(pins) -> str:
    """One line per pin, for a caption or a log entry."""
    out = []
    for p in pins:
        v = p["values"]
        out.append(f"{p['name']}: wounds {_fmt(v.get('wounds'), 2)}, "
                   f"killed {_fmt(v.get('killed'), 2)}, "
                   f"destroyed {_fmt(v.get('destroyed'), 1)}%")
    return "\n".join(out)


def _csv_cell(v) -> str:
    v = str(v)
    return '"' + v.replace('"', '""') + '"' if ("," in v or '"' in v) else v


def to_csv(pins) -> str:
    """The comparison as CSV: same rows, no delta annotations."""
    lines = [",".join(_csv_cell(c) for c in ["Metric"]
                      + [p["name"] for p in pins])]
    for label, cells in context_rows(pins)[1:]:
        if label != "vs first":
            lines.append(",".join(_csv_cell(c) for c in [label] + cells))
    for key, label, nd in _metrics(pins):
        lines.append(",".join(_csv_cell(c) for c in [label] + [
            _fmt(p["values"].get(key), nd) for p in pins]))
    return "\n".join(lines) + "\n"


def overlay_series(pins, key: str = "wounds") -> list:
    """The same PMF ('wounds' / 'killed') from every pin, for one chart."""
    return [{"name": p["name"], "pmf": p["pmfs"].get(key) or []}
            for p in pins]
