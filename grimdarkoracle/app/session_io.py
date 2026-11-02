"""Analyzer sessions: the state of the two sides and the setup,
saved with a copy of the books and core rules they use (Army Forge keeps
no history). Pinned results are not saved (user decision). Pure; the
window reads and applies a Session.

File (grimdarkoracle-session/1):

    {"format": "grimdarkoracle-session/1", "program": "attack_analyzer",
     "flipped": false,
     "setup": {Setup fields},
     "orders": {"weapon_order": [names], "takedown_targets": [places]},
     "sides": {"left": side | null, "right": side | null},
     "books": {uid: Army Forge book JSON}, "core_rules": core JSON | null}

    side = {"source": "book" | "list", "list_path": str | null,
            "units": [ListUnit dicts: the unit "u1" and its Hero "u2"
                      joined to it, as in an army list],
            "state": {SideSetup fields, "off": [weapon profiles]}}

The units reuse the army-list format, so choices are re-linked by uid
then by label and a session survives small book edits.
On load each book is the library's when its content is identical, else
the session's copy, with a note (Library.adopt); the core rules are
always the current ones. "orders" (the attacker's
weapon order and the Takedown preferences on the target) is optional:
sessions saved before it load with the defaults.
"""
import json
import os
from dataclasses import asdict, dataclass, fields

from grimdarkoracle.app.analyzer_orders import Orders
from grimdarkoracle.app.library import digest
from grimdarkoracle.app.setup_model import Setup, SideSetup
from grimdarkoracle.app.side_spec import SideSpec, UnitSpec, entry_side
from grimdarkoracle.data import army_list as AL
from grimdarkoracle.data.army_list import ArmyList, ListUnit, make_ref

FORMAT = "grimdarkoracle-session/1"
LEGACY_FORMATS = ("grimoracle-session/1",)  # before the rename
SIDES = ("left", "right")


class SessionFormatError(ValueError):
    pass


@dataclass
class SideState:
    spec: SideSpec
    side_setup: SideSetup
    source: str = "book"            # book / list
    list_path: str | None = None


@dataclass
class Session:
    setup: Setup
    sides: dict                     # "left" / "right" -> SideState | None
    flipped: bool = False
    orders: Orders = Orders()       # attacker's weapon / Takedown orders


# --- units <-> army-list entries ---------------------------------------------


def _list_unit(spec: UnitSpec, key: str, joined_to=None) -> ListUnit:
    book, unit = spec.cfg.book, spec.cfg.unit
    refs = [make_ref(book, unit, c) for c in spec.cfg.choices]
    refs_b = None if spec.cfg_b is None else \
        [make_ref(book, unit, c) for c in spec.cfg_b.choices]
    return ListUnit(key, book.uid, unit.id, unit.name, spec.label,
                    spec.combined, joined_to, refs, refs_b,
                    list(spec.overrides))


def side_army(spec: SideSpec) -> ArmyList:
    units = [_list_unit(spec.unit, "u1")]
    if spec.hero is not None:
        units.append(_list_unit(spec.hero, "u2", "u1"))
    books = {u.book: "" for u in units}
    return ArmyList("session side", books=books, units=units)


# --- weapons switched off ----------------------------------------------------


def weapon_profile(w) -> dict:
    return {"name": w.name, "range": w.range, "attacks": w.attacks,
            "rules": [r.label or r.name for r in w.rules]}


def weapons_matching(profiles, unit, hero) -> frozenset:
    """Weapons of the restored side matching the saved profiles."""
    want = [json.dumps(p, sort_keys=True) for p in profiles]
    out = set()
    for u in (unit, hero):
        if u is None:
            continue
        for w, _n in u.weapons():
            if json.dumps(weapon_profile(w), sort_keys=True) in want:
                out.add(w)
    return frozenset(out)


# --- to / from dict ----------------------------------------------------------


def _setup_dict(s: Setup) -> dict:
    return json.loads(json.dumps(asdict(s)))        # tuples -> lists


def _setup_from(d: dict) -> Setup:
    names = {f.name for f in fields(Setup)}
    kw = {k: v for k, v in d.items() if k in names}
    for k in ("marks",):
        kw[k] = tuple(kw.get(k, ()))
    for k in ("versatile", "buffs"):
        kw[k] = tuple(tuple(x) for x in kw.get(k, ()))
    return Setup(**kw)


def _side_dict(st: SideState) -> dict:
    ss = st.side_setup
    state = {f.name: getattr(ss, f.name) for f in fields(SideSetup)
             if f.name != "off"}
    state["off"] = [weapon_profile(w)
                    for w in sorted(ss.off, key=lambda w: w.name)]
    return {"source": st.source, "list_path": st.list_path,
            "units": AL.to_dict(side_army(st.spec))["units"], "state": state}


def to_dict(session: Session, lib) -> dict:
    books = {}
    for st in session.sides.values():
        if st is None:
            continue
        for u in (st.spec.unit, st.spec.hero):
            if u is not None:
                raw = lib.raw_book(u.cfg.book)
                if raw is None:
                    raise ValueError(f"no source for book {u.cfg.book.name}")
                books[u.cfg.book.uid] = raw
    return {"format": FORMAT, "program": "attack_analyzer",
            "flipped": session.flipped, "setup": _setup_dict(session.setup),
            "orders": session.orders.to_dict(),
            "sides": {k: None if session.sides.get(k) is None else
                      _side_dict(session.sides[k]) for k in SIDES},
            "books": books, "core_rules": lib.core_raw()}


def _side_from(d: dict, books: dict, notes: list) -> SideState:
    army = AL.from_dict({"format": AL.FORMAT, "units": d.get("units", [])})
    spec, more = entry_side(books, army, "u1")
    notes += more
    ru, hero = spec.resolved()
    st = dict(d.get("state", {}))
    off = weapons_matching(st.pop("off", []), ru, hero)
    names = {f.name for f in fields(SideSetup)}
    ss = SideSetup(off=off, **{k: v for k, v in st.items() if k in names})
    return SideState(spec, ss, d.get("source", "book"), d.get("list_path"))


def from_dict(d: dict, lib) -> tuple[Session, list[str]]:
    """Session from a document, with the notes of the load (books taken
    from the session, choices that could not be re-linked...)."""
    if not isinstance(d, dict) or \
            d.get("format") not in (FORMAT,) + LEGACY_FORMATS:
        raise SessionFormatError(f"not a {FORMAT} file")
    notes: list[str] = []
    books = dict(lib.books)
    for uid, raw in (d.get("books") or {}).items():
        book, note = lib.adopt(raw)
        books[uid] = book
        if note:
            notes.append(note)
    core = d.get("core_rules")
    if core is not None and lib.core_raw() is not None:
        if digest(core) != digest(lib.core_raw()):
            notes.append("core rules changed since the session was saved: "
                         "the current ones are used")
    sides = {}
    for k in SIDES:
        sd = (d.get("sides") or {}).get(k)
        try:
            sides[k] = None if sd is None else _side_from(sd, books, notes)
        except (ValueError, KeyError) as exc:
            notes.append(f"{k} side not restored: {exc}")
            sides[k] = None
    return Session(_setup_from(d.get("setup", {})), sides,
                   bool(d.get("flipped")),
                   Orders.from_dict(d.get("orders"))), notes


def save(session: Session, lib, path: str) -> None:
    """Atomic write."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(to_dict(session, lib), fh, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def load(path: str, lib) -> tuple[Session, list[str]]:
    with open(path, encoding="utf-8") as fh:
        return from_dict(json.load(fh), lib)
