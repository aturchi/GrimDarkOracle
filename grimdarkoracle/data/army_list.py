"""Army lists: format ``grimdarkoracle-list/1``, dataclasses and JSON I/O.

A list stores only what the user chose (configurations), never resolved
profiles: resolution is recomputed from the books, so book updates
propagate. Every choice carries uids AND a label fingerprint (section
label, its occurrence among same-label sections of the unit, option label)
so it can be re-linked if Army Forge uids change (see links.py), and
optionally the model chosen for each instance (``models``: 0-based model
index, null = automatic; absent = all automatic).

Mutable dataclasses: the List Editor edits them in place.
"""
import json
import os
from dataclasses import dataclass, field

from grimdarkoracle.data.resolve import Choice

FORMAT = "grimdarkoracle-list/1"
LEGACY_FORMATS = ("grimoracle-list/1",)    # before the rename


class ListFormatError(ValueError):
    """Not a GrimDarkOracle army list, or an unsupported version."""


@dataclass
class ChoiceRef:
    package: str
    section: str
    option: str
    count: int = 1
    section_label: str = ""
    section_nth: int = 1            # occurrence among same-label sections
    option_label: str = ""
    models: list | None = None      # model index per instance (None: auto)

    def choice(self) -> Choice:
        return Choice(self.package, self.section, self.option, self.count,
                      tuple(self.models or ()))


@dataclass
class ListUnit:
    key: str                        # unique within the list
    book: str                       # book uid
    unit_id: str
    unit_name: str = ""
    label: str = ""                 # user's name for this unit
    combined: bool = False          # two copies (Combined Unit)
    joined_to: str | None = None    # key of the host unit (Hero join)
    choices: list[ChoiceRef] = field(default_factory=list)
    choices_b: list[ChoiceRef] | None = None   # copy B; None = same as A
    overrides: list[dict] = field(default_factory=list)
    notes: str = ""


@dataclass
class ArmyList:
    name: str = "New list"
    game_system: int = 2
    points_limit: int = 2000
    force_org: bool = True
    books: dict[str, str] = field(default_factory=dict)   # uid -> version
    units: list[ListUnit] = field(default_factory=list)

    def unit(self, key: str) -> ListUnit | None:
        return next((u for u in self.units if u.key == key), None)

    def new_key(self) -> str:
        """First free key u1, u2, ..."""
        used = {u.key for u in self.units}
        i = 1
        while f"u{i}" in used:
            i += 1
        return f"u{i}"


# --- fingerprints ------------------------------------------------------------

def norm_label(label: str) -> str:
    """Label as compared by the fingerprints: lower case, single spaces."""
    return " ".join(label.lower().split())


def make_ref(book, unit, choice: Choice) -> ChoiceRef:
    """ChoiceRef with the label fingerprint of 'choice' for 'unit'."""
    pkg = book.packages[choice.package]
    sec = next(s for s in pkg.sections if s.uid == choice.section)
    opt = next(o for o in sec.options if o.uid == choice.option)
    same = [s for p in book.unit_packages(unit) for s in p.sections
            if norm_label(s.label) == norm_label(sec.label)]   # as links
    nth = next(i for i, s in enumerate(same, 1) if s is sec)
    return ChoiceRef(choice.package, choice.section, choice.option,
                     choice.count, sec.label, nth, opt.label,
                     list(choice.models) if choice.models else None)


# --- dict / JSON -------------------------------------------------------------

def _ref_to_dict(r: ChoiceRef) -> dict:
    d = {"package": r.package, "section": r.section, "option": r.option,
         "count": r.count, "section_label": r.section_label,
         "section_nth": r.section_nth, "option_label": r.option_label}
    if r.models is not None:            # optional: absent = automatic
        d["models"] = list(r.models)
    return d


def _models(raw):
    if raw is None:
        return None
    if not isinstance(raw, list) or not all(
            m is None or (isinstance(m, int) and not isinstance(m, bool)
                          and m >= 0) for m in raw):
        raise ListFormatError(f"bad 'models' {raw!r}: list of model "
                              "indices >= 0 or null expected")
    return list(raw)


def _ref_from_dict(d: dict) -> ChoiceRef:
    return ChoiceRef(d.get("package", ""), d.get("section", ""),
                     d.get("option", ""), int(d.get("count", 1)),
                     d.get("section_label", ""), int(d.get("section_nth", 1)),
                     d.get("option_label", ""), _models(d.get("models")))


def to_dict(army: ArmyList) -> dict:
    units = []
    for u in army.units:
        units.append({
            "key": u.key, "book": u.book, "unit_id": u.unit_id,
            "unit_name": u.unit_name, "label": u.label,
            "combined": u.combined, "joined_to": u.joined_to,
            "choices": [_ref_to_dict(r) for r in u.choices],
            "choices_b": None if u.choices_b is None else
            [_ref_to_dict(r) for r in u.choices_b],
            "overrides": list(u.overrides), "notes": u.notes})
    return {"format": FORMAT, "name": army.name,
            "game_system": army.game_system,
            "points_limit": army.points_limit, "force_org": army.force_org,
            "books": dict(army.books), "units": units}


def from_dict(d: dict) -> ArmyList:
    if not isinstance(d, dict) or \
            d.get("format") not in (FORMAT,) + LEGACY_FORMATS:
        got = d.get("format") if isinstance(d, dict) else None
        raise ListFormatError(f"not a {FORMAT} file (format: {got!r})")
    units, keys = [], set()
    for x in d.get("units", []):
        key = x.get("key") or f"u{len(units) + 1}"
        if key in keys:
            raise ListFormatError(f"duplicate unit key {key!r}")
        keys.add(key)
        cb = x.get("choices_b")
        units.append(ListUnit(
            key=key, book=x.get("book", ""), unit_id=x.get("unit_id", ""),
            unit_name=x.get("unit_name", ""), label=x.get("label", ""),
            combined=bool(x.get("combined")), joined_to=x.get("joined_to"),
            choices=[_ref_from_dict(c) for c in x.get("choices", [])],
            choices_b=None if cb is None else [_ref_from_dict(c) for c in cb],
            overrides=list(x.get("overrides", [])), notes=x.get("notes", "")))
    return ArmyList(name=d.get("name", "Unnamed list"),
                    game_system=int(d.get("game_system", 2)),
                    points_limit=int(d.get("points_limit", 2000)),
                    force_org=bool(d.get("force_org", True)),
                    books=dict(d.get("books", {})), units=units)


def save(army: ArmyList, path: str) -> None:
    """Atomic write (a crash never leaves half a list behind)."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(to_dict(army), fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(tmp, path)


def load(path: str) -> ArmyList:
    with open(path, encoding="utf-8") as fh:
        return from_dict(json.load(fh))
