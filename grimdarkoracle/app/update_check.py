"""Update check after an Army Forge refresh. Pure.

Three questions, one report:

1. what changed in the books and the core rules: each book against the
   previous copy af_fetch kept (books/<uid>.prev.json), data.book_diff;
2. which RULES and SPELLS the program implements changed text (registry
   status 'changed', spell status 'changed' / 'broken'): their semantics
   were written against the old text and must be reviewed. Rules or
   spells that are simply not mapped (out of scope) are
   counted, and listed only for the books asked about;
3. which saved army lists are affected: choices re-linked by label or
   lost, entries that no longer resolve, books of another version.

startup_note() is the cheap part (2) for the programs' status line.
"""
import glob
import os
from dataclasses import dataclass, field

from grimdarkoracle.data import af_book as ab
from grimdarkoracle.data import army_list, book_diff, list_resolve
from grimdarkoracle.rules import coverage
from grimdarkoracle.rules import spells as SP

PREV = ".prev.json"


@dataclass
class Report:
    books: list = field(default_factory=list)        # BookDiff
    core: list = field(default_factory=list)         # lines
    unreadable: list = field(default_factory=list)   # lines
    review: list = field(default_factory=list)       # rules / spells
    unmapped: list = field(default_factory=list)     # of the books asked
    unmapped_total: int = 0
    lists: list = field(default_factory=list)        # (list name, [notes])

    @property
    def clean(self) -> bool:
        """Nothing the user must act on (unmapped rules are known)."""
        return not (self.review or self.lists or self.unreadable)


def prev_path(path: str) -> str:
    return path[:-len(".json")] + PREV


def book_diffs(lib, uids=None) -> tuple[list, list]:
    """(BookDiff of every official book with a previous copy, or of
    'uids' only; lines about copies that could not be read)."""
    diffs, bad = [], []
    for uid, path in sorted(lib.paths.items()):
        if uid in lib.local or (uids is not None and uid not in uids):
            continue
        prev = prev_path(path)
        if not os.path.exists(prev):
            continue
        try:
            old = ab.load_book(prev)
        except (OSError, ValueError, KeyError, TypeError) as e:
            bad.append(f"{os.path.basename(prev)}: not readable ({e})")
            continue
        diffs.append(book_diff.diff_books(old, lib.books[uid]))
    return diffs, bad


def core_diff(lib) -> tuple[list, list]:
    path = os.path.join(lib.root, "rules", "common_2.json")
    if not os.path.exists(prev_path(path)):
        return [], []
    try:
        old = ab.load_core_rules(prev_path(path))
    except (OSError, ValueError, KeyError, TypeError) as e:
        return [], [f"previous core rules not readable ({e})"]
    return book_diff.diff_core(old, lib.core), []


def review(lib, books=None) -> list[str]:
    """Implemented rules and spells whose Army Forge text changed."""
    books = list(lib.books.values() if books is None else books)
    cov = coverage.coverage(lib.reg, books)
    out = [f"rule {name} ({rid}): its text differs from the one its "
           "semantics were written for, review them [text changed in: "
           f"{', '.join(sorted(cov.changed.get(rid, ('', {}))[1]) or where)}"
           f"; used in: {', '.join(sorted(where))}]"
           for rid, (name, where) in sorted(cov.by_status["changed"].items(),
                                            key=lambda kv: kv[1][0])]
    return out + spell_review(lib, books)


def spell_review(lib, books) -> list[str]:
    """Mapped spells (keys "id:text hash") whose text no book has any more
    while a spell with the same id is still there: the text changed. A
    sub-faction spell sharing the id with other text is a variant, not
    mapped, and not a change (it never had semantics). A mapped spell
    still present whose rules no longer resolve is 'broken'."""
    present, by_id = {}, {}
    for b in books:
        for sp in b.spells:
            present.setdefault(SP.spell_key(sp), (b, sp))
            by_id.setdefault(sp.id, (b, sp))
    out = []
    for key, e in sorted(lib.sreg.entries.items(),
                         key=lambda kv: kv[1].get("name", kv[0])):
        if key in present:
            b, sp = present[key]
            if lib.sreg.status(b, sp) == "broken":
                out.append(f"spell {sp.name} ({b.name}): a rule it names "
                           "no longer resolves")
        elif key.split(":")[0] in by_id:
            b, sp = by_id[key.split(":")[0]]
            out.append(f"spell {e.get('name', sp.name)} ({b.name}): text "
                       "changed, review its semantics")
    return out


def unmapped(lib, books) -> list[str]:
    books = list(books)
    cov = coverage.coverage(lib.reg, books)
    out = [f"rule {name} ({rid})" for rid, (name, _w) in
           sorted(cov.by_status["unmapped"].items(), key=lambda kv: kv[1][0])]
    return out + [f"spell {sp.name} ({b.name})" for b in books
                  for sp in b.spells if SP.spell_key(sp) not in
                  lib.sreg.entries]


def list_notes(lib, lists_dir: str | None) -> list:
    """(list name, notes) of the saved lists that need a look."""
    out = []
    if not lists_dir or not os.path.isdir(lists_dir):
        return out
    for p in sorted(glob.glob(os.path.join(lists_dir, "*.json"))):
        try:
            army = army_list.load(p)
        except (OSError, ValueError, KeyError, TypeError) as e:
            out.append((os.path.basename(p), [f"not readable ({e})"]))
            continue
        res = list_resolve.resolve_list(army, lib.books)
        notes = list(res.issues)
        for lu in army.units:
            e = res.entries.get(lu.key)
            if e is None:
                continue
            who = lu.label or lu.unit_name or lu.key
            if e.unit is None and not e.link.invalid:
                notes.append(f"{who}: unit not found")
            notes += [f"{who}: re-linked {x}" for x in e.link.relinked]
            notes += [f"{who}: lost choice {x}" for x in e.link.invalid]
        if notes:
            out.append((f"{army.name} ({os.path.basename(p)})", notes))
    return out


def build(lib, uids=None, lists_dir: str | None = None) -> Report:
    """The report; uids: the books just updated (None: every book with a
    previous copy)."""
    r = Report()
    r.books, r.unreadable = book_diffs(lib, uids)
    r.core, bad = core_diff(lib)
    r.unreadable += bad
    r.review = review(lib)
    official = [b for u, b in lib.books.items() if u not in lib.local]
    r.unmapped_total = len(unmapped(lib, official))
    asked = official if uids is None else [lib.books[u] for u in uids
                                           if u in lib.books]
    if uids is not None:
        r.unmapped = unmapped(lib, asked)
    r.lists = list_notes(lib, lists_dir)
    return r


def to_text(r: Report) -> str:
    out = []
    if r.books or r.core:
        out.append("== Changes since the previous download")
        for d in r.books:
            out += d.lines()
        out += [f"  {x}" for x in r.core]
    out += [f"!! {x}" for x in r.unreadable]
    out.append("== Implemented rules and spells to review")
    out += [f"  {x}" for x in r.review] or ["  none"]
    if r.unmapped:
        out.append("== Not mapped in the updated books (no effect computed)")
        out += [f"  {x}" for x in r.unmapped]
    out.append(f"   ({r.unmapped_total} rules / spells of the official books "
               "are not mapped: out of scope, see tools/rules_report.py)")
    out.append("== Saved army lists")
    for name, notes in r.lists:
        out.append(f"  {name}")
        out += [f"    {n}" for n in notes]
    if not r.lists:
        out.append("  nothing to check")
    return "\n".join(out) + "\n"


def startup_note(lib) -> str:
    """One line for the programs' status bar when implemented rules or
    spells changed text, else ''."""
    n = len(review(lib))
    return "" if not n else (
        f"{n} implemented rule(s) / spell(s) changed text in Army Forge: "
        "their results may be outdated (run tools/update_report.py)")


def status_text(lib, ok_text: str) -> tuple[str, bool]:
    """(text, is a warning) for the status line of a program: the
    library's warnings and the startup note, else 'ok_text'."""
    lines = list(lib.warnings) + [x for x in (startup_note(lib),) if x]
    return ("; ".join(lines), True) if lines else (ok_text, False)
