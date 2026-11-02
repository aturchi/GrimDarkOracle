"""One unit as the program will play it: the content of the inspect dialog
and of the printable cheat sheet. Pure.

build() gathers the unit as configured (joined Hero, Combined copies and
list overrides included, i.e. a resolved side) into a Sheet: stat lines,
models grouped by loadout, weapons, every rule with its Army Forge text
and the state of its semantics (ok / changed / unmapped...), and the
spells of the book when the side has a Caster. Two renderers over the
same Sheet, so the text and the HTML cannot drift apart. The HTML is one
self-contained file with print styles (Ctrl-P in a browser).
"""
import html as _html
from dataclasses import dataclass, field

from grimdarkoracle.app import spells as SP


@dataclass
class Sheet:
    title: str
    stats: list = field(default_factory=list)      # (label, value)
    models: list = field(default_factory=list)     # (count, text)
    weapons: list = field(default_factory=list)    # (name, x, range, A, rules)
    rules: list = field(default_factory=list)      # (label, status, text)
    spells: list = field(default_factory=list)     # (name, tokens, effect, st)
    notes: list = field(default_factory=list)


def _weapon_rules(w) -> str:
    return ", ".join(r.label or r.name for r in w.rules)


def loadout(m) -> str:
    bits = [f"{n}x {w.name}" if n > 1 else w.name for w, n in m.weapons]
    bits += [f"{n}x {it.name}" if n > 1 else it.name for it, n in m.items]
    return ", ".join(bits) or "no equipment"


def _rule_rows(reg, units) -> list:
    seen, out = set(), []

    def add(r):
        key = (r.id, r.label or r.name)
        if key in seen:
            return
        seen.add(key)
        d = reg.defs.get(r.id)
        out.append((r.label or r.name, reg.status(r.id, r.name),
                    d.description if d else "(no text)"))

    for u in units:
        for m in u.models:
            for r in m.rules:
                add(r)
    for u in units:
        for w, _n in u.weapons():
            for r in w.rules:
                add(r)
    return out


def build(reg, unit, hero=None, book=None, sreg=None) -> Sheet:
    """Sheet of a resolved unit (and its joined Hero); 'book' and 'sreg'
    add the book's spells when the side has a Caster."""
    units = [u for u in (unit, hero) if u is not None]
    name = unit.name + (f" + {hero.name}" if hero else "")
    pts = sum(u.points for u in units)
    sheet = Sheet(f"{name}  [{sum(u.size for u in units)}]  {pts} pts")
    for u, role in ((unit, "Unit"), (hero, "Joined Hero")):
        if u is None:
            continue
        tough = max((m.tough for m in u.models), default=0)
        bits = [f"Quality {u.quality}+", f"Defense {u.defense}+",
                f"{u.size} model(s)", f"{u.points} pts"]
        if tough:
            bits.append(f"Tough({tough})")
        if u.combined:
            bits.append("Combined Unit")
        if u.modified:
            bits.append("overrides applied")
        sheet.stats.append((f"{role}: {u.name}", ", ".join(bits)))
        groups: dict = {}
        for m in u.models:
            key = loadout(m)
            groups[key] = groups.get(key, 0) + 1
        prefix = "Hero: " if role != "Unit" else ""
        sheet.models += [(n, prefix + k) for k, n in groups.items()]
        sheet.notes += [f"{u.name}: {x}" for x in u.issues]
    total: dict = {}
    for u in units:
        for w, n in u.weapons():
            total[w] = total.get(w, 0) + n
    sheet.weapons = [(w.name, n, f'{w.range}"' if w.range else "melee",
                      w.attacks, _weapon_rules(w)) for w, n in total.items()]
    sheet.rules = _rule_rows(reg, units)
    rating = SP.caster_rating(reg, unit, hero)
    if rating and book is not None and sreg is not None:
        mod = SP.cast_mod(reg, unit, hero)
        sheet.stats.append(("Caster", f"Caster({rating})" +
                            (f", {mod:+d} to cast" if mod else "")))
        sheet.spells = [(s.name, s.threshold, s.effect, sreg.status(book, s))
                        for s in book.spells]
    return sheet


# --- renderers ------------------------------------------------------------------------


def _flag(status) -> str:
    return "" if status == "ok" else f" [{status}]"


def rule_names(sheet: Sheet) -> str:
    """The rules on one line, their state flagged (rosters)."""
    return ", ".join(lb + _flag(st) for lb, st, _t in sheet.rules)


def text_lines(sheet: Sheet, texts: bool = True) -> list[str]:
    """Text of a sheet; texts=False: rule names on one line and no spells
    (a roster prints the texts once, at the end)."""
    out = [sheet.title, "=" * len(sheet.title)]
    out += [f"{k}: {v}" for k, v in sheet.stats]
    out += ["", "Models"] + [f"  {n} x {t}" for n, t in sheet.models]
    out += ["", "Weapons"]
    for name, n, rng, att, rules in sheet.weapons:
        out.append(f"  {n} x {name}  {rng}  A{att}" +
                   (f"  {rules}" if rules else ""))
    if not texts:
        out += ["", f"Rules: {rule_names(sheet)}"]
    else:
        out += ["", "Rules"]
        out += [f"  {lb}{_flag(st)}: {tx}" for lb, st, tx in sheet.rules]
    if sheet.spells and texts:
        out += ["", "Spells"]
        out += [f"  {name} ({tok}){_flag(st)}: {eff}"
                for name, tok, eff, st in sheet.spells]
    if sheet.notes:
        out += ["", "Notes"] + [f"  {x}" for x in sheet.notes]
    return out


def to_text(sheet: Sheet) -> str:
    return "\n".join(text_lines(sheet)) + "\n"


_CSS = """body{font-family:sans-serif;font-size:11pt;margin:1.5em}
h1{font-size:15pt;margin:0 0 .4em}h2{font-size:12pt;margin:.9em 0 .3em}
h3{font-size:11pt;margin:.6em 0 .2em}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #999;padding:2px 5px;text-align:left;vertical-align:top}
th{background:#eee}.warn{color:#a03000}.dim{color:#666}
.entry{page-break-inside:avoid;margin-bottom:1.2em}
@media print{body{margin:0}h2{page-break-after:avoid}tr{page-break-inside:avoid}}"""


def esc(x) -> str:
    return _html.escape(str(x))


def table(head, rows) -> str:
    """HTML table; 'rows' cells are already escaped."""
    h = "".join(f"<th>{esc(c)}</th>" for c in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
                   for r in rows)
    return f"<table><tr>{h}</tr>{body}</table>"


def status_html(status) -> str:
    return "" if status == "ok" else \
        f' <span class="warn">[{esc(status)}]</span>'


def rules_table(rows) -> str:
    return table(("Rule", "Text"), [(esc(lb) + status_html(st), esc(tx))
                                    for lb, st, tx in rows])


def spells_table(rows) -> str:
    return table(("Spell", "Tokens", "Effect"),
                 [(esc(n) + status_html(st), esc(t), esc(eff))
                  for n, t, eff, st in rows])


def html_parts(sheet: Sheet, texts: bool = True, level: int = 1
               ) -> list[str]:
    """HTML of a sheet; 'level' of its title (sections one below);
    texts=False as in text_lines."""
    h, sub = f"h{level}", f"h{level + 1}"
    parts = [f"<{h}>{esc(sheet.title)}</{h}>",
             table(("", ""), [(esc(k), esc(v)) for k, v in sheet.stats]),
             f"<{sub}>Models</{sub}>",
             table(("x", "Loadout"), [(esc(n), esc(t))
                                      for n, t in sheet.models]),
             f"<{sub}>Weapons</{sub}>",
             table(("Weapon", "x", "Range", "A", "Rules"),
                   [tuple(esc(c) for c in w) for w in sheet.weapons])]
    if texts:
        parts += [f"<{sub}>Rules</{sub}>", rules_table(sheet.rules)]
    else:
        parts.append("<p><b>Rules:</b> " + ", ".join(
            esc(lb) + status_html(st) for lb, st, _t in sheet.rules) +
            "</p>")
    if sheet.spells and texts:
        parts += [f"<{sub}>Spells</{sub}>", spells_table(sheet.spells)]
    if sheet.notes:
        parts += [f"<{sub}>Notes</{sub}>", "<ul>" + "".join(
            f'<li class="warn">{esc(x)}</li>' for x in sheet.notes) +
            "</ul>"]
    return parts


def page(title: str, parts, footer: str) -> str:
    """One self-contained HTML page with the print styles."""
    return ("<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">"
            f"<title>{esc(title)}</title><style>{_CSS}</style></head>"
            "<body>" + "\n".join(parts) +
            f'<p class="dim">{esc(footer)}</p></body></html>\n')


def to_html(sheet: Sheet) -> str:
    return page(sheet.title, html_parts(sheet), "GrimDarkOracle cheat sheet")


def render(sheet: Sheet, path: str) -> str:
    """HTML for a .htm / .html path, text otherwise (ui.save_text)."""
    return to_html(sheet) if path.lower().endswith((".html", ".htm")) \
        else to_text(sheet)
