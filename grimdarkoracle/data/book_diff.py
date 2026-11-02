"""What changed between two revisions of an army book:
af_fetch keeps the previous copy (books/<uid>.prev.json), this compares
the two parsed Books. Pure; works on af_book objects only.

Units are matched by id, then by name (ids are expected to be stable,
the name catches a unit re-created under a new id). Options are compared
per unit by (section label, option label) with the unit's own price
; sections the unit does not get (disabled_sections) are left out.
Rule definitions and spells are compared by id (text changes matter: the
semantics are hashed against the text).
"""
from dataclasses import dataclass, field


@dataclass
class BookDiff:
    uid: str
    name: str
    old_version: str
    new_version: str
    units_added: list = field(default_factory=list)
    units_removed: list = field(default_factory=list)
    units: list = field(default_factory=list)       # (unit name, [changes])
    rules: list = field(default_factory=list)       # text lines
    spells: list = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.units_added or self.units_removed or self.units
                    or self.rules or self.spells)

    def lines(self) -> list[str]:
        head = f"{self.name}: {self.old_version} -> {self.new_version}" \
            if self.old_version != self.new_version else \
            f"{self.name} {self.new_version} (same version, new content)"
        out = [head]
        out += [f"  unit added: {n}" for n in self.units_added]
        out += [f"  unit removed: {n}" for n in self.units_removed]
        for name, changes in self.units:
            out += [f"  {name}: {c}" for c in changes]
        out += [f"  {x}" for x in self.rules + self.spells]
        if self.empty:
            out.append("  no difference in units, options, rules or spells")
        return out


# --- labels ----------------------------------------------------------------------------

def _rule(r) -> str:
    if r.label:
        return r.label
    return f"{r.name}({r.rating})" if r.rating is not None else r.name


def weapon_text(w) -> str:
    rng = f'{w.range}"' if w.range else "melee"
    bits = [rng, f"A{w.attacks}"] + [_rule(r) for r in w.rules]
    n = f"{w.count}x " if w.count > 1 else ""
    return f"{n}{w.name} ({', '.join(bits)})"


def _gear(u) -> set:
    out = {weapon_text(w) for w in u.weapons}
    for it in u.items:
        out.add(it.name if not it.weapons and not it.rules else
                f"{it.name} [" + ", ".join(
                    [_rule(r) for r in it.rules] +
                    [weapon_text(w) for w in it.weapons]) + "]")
    return out


def _options(book, u) -> dict:
    """{(section label, option label): points} of the unit's options."""
    out = {}
    for pkg in book.unit_packages(u):
        for sec in pkg.sections:
            if sec.uid in u.disabled_sections:
                continue
            for o in sec.options:
                pts = dict(o.costs).get(u.id)
                out.setdefault((sec.label, o.label), pts)
    return out


def _set_changes(what, old: set, new: set) -> list[str]:
    out = [f"{what} added: {x}" for x in sorted(new - old)]
    return out + [f"{what} removed: {x}" for x in sorted(old - new)]


def unit_changes(old_book, old, new_book, new) -> list[str]:
    out = []
    for label, a, b, fmt in (("models", old.size, new.size, "{}"),
                             ("Quality", old.quality, new.quality, "{}+"),
                             ("Defense", old.defense, new.defense, "{}+"),
                             ("points", old.cost, new.cost, "{}")):
        if a != b:
            out.append(f"{label} {fmt.format(a)} -> {fmt.format(b)}")
    out += _set_changes("rule", {_rule(r) for r in old.rules},
                        {_rule(r) for r in new.rules})
    out += _set_changes("equipment", _gear(old), _gear(new))
    oa, ob = _options(old_book, old), _options(new_book, new)
    for key in sorted(set(oa) | set(ob)):
        sec, opt = key
        if key not in ob:
            out.append(f"option removed: {sec} / {opt}")
        elif key not in oa:
            out.append(f"option added: {sec} / {opt} ({ob[key]} pts)")
        elif oa[key] != ob[key]:
            out.append(f"option price: {sec} / {opt}: {oa[key]} -> "
                       f"{ob[key]} pts")
    return out


# --- books ---------------------------------------------------------------------------------

def _defs(what, old: dict, new: dict, text) -> list[str]:
    """Added / removed / text changed, for rule definitions or spells
    keyed by id."""
    out = []
    for k in sorted(set(old) | set(new), key=lambda k: (new.get(k) or
                                                         old.get(k)).name):
        a, b = old.get(k), new.get(k)
        if a is None:
            out.append(f"{what} added: {b.name}")
        elif b is None:
            out.append(f"{what} removed: {a.name}")
        elif text(a) != text(b):
            out.append(f"{what} changed: {b.name}" +
                       (f" (was {a.name})" if a.name != b.name else ""))
    return out


def diff_books(old, new) -> BookDiff:
    d = BookDiff(new.uid, new.name, old.version, new.version)
    by_name = {u.name: u for u in old.units.values()}
    seen = set()
    for u in new.units.values():
        o = old.units.get(u.id) or by_name.get(u.name)
        if o is None or o.id in seen:
            d.units_added.append(u.name)
            continue
        seen.add(o.id)
        ch = unit_changes(old, o, new, u)
        if o.name != u.name:
            ch.insert(0, f"renamed from {o.name}")
        if ch:
            d.units.append((u.name, ch))
    d.units_removed = [u.name for u in old.units.values() if u.id not in seen]
    d.rules = _defs("rule", old.rules, new.rules,
                    lambda r: (r.name, r.description))
    d.spells = _defs("spell", {s.id: s for s in old.spells},
                     {s.id: s for s in new.spells},
                     lambda s: (s.name, s.threshold, s.effect))
    return d


def diff_core(old: dict, new: dict) -> list[str]:
    """Core special rules (rule id -> RuleDef) of two downloads."""
    return _defs("core rule", old, new, lambda r: (r.name, r.description))
