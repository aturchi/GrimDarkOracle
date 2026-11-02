"""Army lists built automatically from a whole book: every unit
with a deterministic set of upgrades, one Hero joined to a host and one
Combined Unit. Used by the file round trips and the undo property test,
on DAO Union / Battle Brothers with --real_data, else on the synthetic
book.
"""
import os

import testpaths
from grimdarkoracle.app.library import Library
from grimdarkoracle.app.unit_config import UnitConfig
from grimdarkoracle.data import army_list as AL
from grimdarkoracle.data import list_resolve as LR

DAO, BB = "z8205ez2boggzs22", "78qp9l5alslt6yj8"
SYNTH = "synthetic00book01"
# Upgrades the random configurations always take when offered, so the
# real lists have Casters and a Mend unit (Elder Sage; Master Archivist,
# Engineer). Unknown uids are simply never offered.
PREFER = frozenset({"rJaHv", "be5c8HnP", "1_U_a7vn"})


def library():
    """(Library, the two book uids to use: real DAO / BB or synthetic)."""
    if testpaths.USING_SYNTHETIC:
        return Library.load(testpaths.SYNTHETIC_DIR), (SYNTH, SYNTH)
    return Library.load(testpaths.DATA_DIR), (DAO, BB)


def rich_config(book, unit_id: str, salt: int) -> UnitConfig:
    """A configuration with an option in most sections; which option and
    which sections vary with 'salt'. Choices resolve() would not apply
    are dropped, so the configuration is valid."""
    cfg = UnitConfig(book, unit_id)
    for _pass in range(3):                  # sections enabled by others
        for i, sv in enumerate(cfg.sections()):
            opts = [o for o in sv.options if o.limit > 0]
            pref = [o for o in opts if o.uid in PREFER]
            if not sv.enabled or not opts or any(o.wanted for o in
                                                 sv.options) \
                    or (salt + i) % 4 == 0 and not pref:
                continue
            o = pref[0] if pref else opts[(salt + i) % len(opts)]
            n = o.limit if sv.mode == "count" else 1
            try:
                cfg.set_count(sv.package, sv.uid, o.uid, n)
            except (ValueError, KeyError):
                continue
    cfg.prune()
    return cfg


def army(lib, book_uid: str, salt: int = 0, name: str = "") -> AL.ArmyList:
    """Every unit of the book once, upgraded by rich_config(); the first
    Hero that can join is joined to the first host it can join, and the
    first other multi-model unit is a Combined Unit. No Force Org."""
    book = lib.books[book_uid]
    al = AL.ArmyList(name or book.name, points_limit=100_000,
                     force_org=False, books={book_uid: book.version})
    units = sorted(book.units.values(), key=lambda u: u.id)
    for n, unit in enumerate(units):
        cfg = rich_config(book, unit.id, salt + n)
        al.units.append(AL.ListUnit(
            al.new_key(), book_uid, unit.id, unit.name,
            choices=[AL.make_ref(book, unit, c) for c in cfg.choices]))
    res = LR.resolve_list(al, lib.books)
    ru = {k: e.unit for k, e in res.entries.items()}
    heroes = [lu for lu in al.units if LR.is_hero(ru[lu.key])]
    hosts = [lu for lu in al.units if ru[lu.key].size > 1
             and not LR.is_hero(ru[lu.key])]
    joined = None
    for h in heroes:
        host = next((x for x in hosts
                     if not LR.join_issues(ru[h.key], ru[x.key])), None)
        if host is not None:
            h.joined_to, joined = host.key, host.key
            break
    combo = next((x for x in hosts if x.key != joined), None)
    if combo is not None:
        combo.combined = True
    return al


def tmpdir_copy(lib_root: str, dest: str, uids) -> str:
    """Copy the core rules and the books 'uids' of an Army Forge folder."""
    import shutil
    out = os.path.join(dest, "army_forge")
    os.makedirs(os.path.join(out, "books"))
    shutil.copytree(os.path.join(lib_root, "rules"),
                    os.path.join(out, "rules"),
                    ignore=shutil.ignore_patterns("*.prev.json"))
    for uid in set(uids):
        shutil.copy(os.path.join(lib_root, "books", f"{uid}.json"),
                    os.path.join(out, "books"))
    return out
