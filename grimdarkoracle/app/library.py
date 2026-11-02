"""Everything the programs read from disk at start-up: the Army Forge books
and core rules downloaded by tools/af_fetch.py, the rules semantics and
the registry built on them, plus army lists on request.

Local books (home-made units, data.local_books) are read from
books_local/ next to the program, or from the folder given to load(); a
file whose uid does not start with 'local-' is refused.

Loading the 49 official books takes ~0.3 s, so they are all loaded at
once and the registry knows every book rule. Missing or broken files do
not stop the program: they end up in Library.warnings (the window shows
them) and the library is simply smaller. The adapter's lenient-parsing
notes stay on each Book (Book.warnings), for the rules / survey reports.
"""
import glob
import hashlib
import json
import os
from dataclasses import dataclass, field

from grimdarkoracle import app_paths
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.data import army_list, list_resolve
from grimdarkoracle.data import local_books as LB
from grimdarkoracle.rules import registry, spells

GAME_SYSTEM = 2


def default_root() -> str:
    """<program folder>/data/army_forge (af_fetch's default output)."""
    return os.path.join(app_paths.app_dir(), "data", "army_forge")


def default_local_dir() -> str:
    """<program folder>/books_local (home-made units)."""
    return os.path.join(app_paths.app_dir(), "books_local")


@dataclass(frozen=True)
class BookInfo:
    uid: str
    name: str
    version: str
    units: int


@dataclass
class Library:
    root: str
    books: dict = field(default_factory=dict)       # uid -> Book
    core: dict = field(default_factory=dict)        # rule id -> RuleDef
    reg: registry.RuleRegistry | None = None
    sreg: spells.SpellRegistry | None = None
    warnings: list = field(default_factory=list)
    paths: dict = field(default_factory=dict)       # uid -> book file
    snapshots: list = field(default_factory=list)   # (Book, raw) from sessions
    local_dir: str | None = None                    # folder of local books
    local: set = field(default_factory=set)         # uids of local books

    @classmethod
    def load(cls, root: str | None = None, semantics: dict | None = None,
             local_dir: str | None = None) -> "Library":
        """Books, rules and semantics. Local books: 'local_dir', else
        books_local/ next to the program when 'root' is the default
        (an explicit root, as in the tests, reads no local book unless
        'local_dir' is given)."""
        lib = cls(root or default_root())
        lib.local_dir = local_dir or (default_local_dir() if root is None
                                      else None)
        rules = os.path.join(lib.root, "rules", f"common_{GAME_SYSTEM}.json")
        try:
            lib.core = ab.load_core_rules(rules)
        except (OSError, ValueError) as e:
            lib.warnings.append(f"core rules not loaded ({e}); run "
                                f"{app_paths.fetch_command()}")
        paths = sorted(p for p in glob.glob(os.path.join(lib.root, "books",
                                                         "*.json"))
                       if not p.endswith(".prev.json"))
        if not paths:
            lib.warnings.append(f"no army books in {lib.root}; run "
                                f"{app_paths.fetch_command()}")
        for p in paths:
            try:
                b = ab.load_book(p)
            except (OSError, ValueError) as e:
                lib.warnings.append(f"{os.path.basename(p)}: {e}")
                continue
            if b.game_system != GAME_SYSTEM:
                continue
            lib.books[b.uid] = b
            lib.paths[b.uid] = p
        lib._load_local()
        sem = semantics if semantics is not None else \
            registry.load_semantics()
        lib.reg = registry.RuleRegistry(sem, lib.core, lib.books.values())
        for uid in sorted(lib.local):
            lib._install(lib.raw_book(lib.books[uid]))
        try:
            doc = spells.load()
        except (OSError, ValueError) as e:
            lib.warnings.append(f"spells not loaded ({e})")
            doc = {"format": spells.FORMAT, "spells": {}}
        lib.sreg = spells.SpellRegistry(doc, lib.reg, lib.books.values())
        return lib

    def _load_local(self) -> None:
        if not self.local_dir or not os.path.isdir(self.local_dir):
            return
        for p in sorted(glob.glob(os.path.join(self.local_dir, "*.json"))):
            try:
                b = ab.load_book(p)
            except (OSError, ValueError, KeyError, TypeError) as e:
                self.warnings.append(f"local book {os.path.basename(p)}: {e}")
                continue
            if not LB.is_local(b.uid) or b.uid in self.books:
                self.warnings.append(f"local book {os.path.basename(p)}: uid "
                                     f"{b.uid!r} refused (needs the "
                                     f"{LB.PREFIX!r} prefix, unique)")
                continue
            self.books[b.uid], self.paths[b.uid] = b, p
            self.local.add(b.uid)

    def put_local(self, raw: dict):
        """Save a local book (data.local_books.save) and make it live:
        the library, the rule registry (its rules replaced) and the
        spells see the new content. Returns the Book."""
        if not self.local_dir:
            raise ValueError("no folder for local books")
        path = LB.save(raw, self.local_dir)
        book = ab.parse_book(raw)
        self.books[book.uid], self.paths[book.uid] = book, path
        self.local.add(book.uid)
        if self.reg is not None:
            for rid in book.rules:              # semantics removed or changed
                if LB.is_local(rid):
                    self.reg.uninstall(rid)
            self.reg.add_book(book, replace=True)
            self._install(raw)
        return book

    def _install(self, raw, replace: bool = True) -> None:
        """Semantics of the custom rules of a local book; a broken
        entry is reported and left out. replace=False (session snapshots)
        keeps the entries already known, as add_book keeps definitions."""
        if self.reg is None or raw is None:
            return
        from grimdarkoracle.rules import mapper as MP
        for rid, entry in LB.semantics_of(raw).items():
            if not replace and rid in self.reg.entries:
                continue
            try:
                self.reg.install(rid, MP.refresh_native(entry, self.reg))
            except ValueError as e:
                self.warnings.append(f"{raw.get('name')}: rule {rid}: {e}")

    def drop_local(self, uid: str) -> None:
        """Delete a local book file and forget it."""
        if uid not in self.local:
            raise ValueError(f"{uid!r} is not a local book")
        LB.delete(self.local_dir, uid)
        self.local.discard(uid)
        self.books.pop(uid, None)
        self.paths.pop(uid, None)

    # --- catalogue -----------------------------------------------------------

    def catalogue(self) -> list[BookInfo]:
        """Books sorted by name."""
        return sorted((BookInfo(b.uid, b.name, b.version, len(b.units))
                       for b in self.books.values()),
                      key=lambda i: (i.name.lower(), i.uid))

    def units(self, uid: str) -> list:
        """Units of a book in book order (af_book.Unit)."""
        b = self.books.get(uid)
        return list(b.units.values()) if b else []

    # --- raw books (session snapshots) ---------------------------------------

    def core_raw(self) -> dict | None:
        p = os.path.join(self.root, "rules", f"common_{GAME_SYSTEM}.json")
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def raw_book(self, book) -> dict | None:
        """The Army Forge JSON a Book was parsed from (library file or
        session snapshot), None if unknown."""
        for b, raw in self.snapshots:
            if b is book:
                return raw
        if self.books.get(book.uid) is book and book.uid in self.paths:
            with open(self.paths[book.uid], encoding="utf-8") as fh:
                raw = json.load(fh)
            return LB.migrate(raw) if LB.is_local(book.uid) else raw
        return None

    def adopt(self, raw: dict):
        """Book for a snapshot: the library's own when identical, else the
        snapshot itself (kept, its rules added to the registries).
        Returns (Book, note or "")."""
        uid = raw.get("uid", "")
        if LB.is_local(uid):
            raw = LB.migrate(raw)               # files of the old program name
        live = self.books.get(uid)
        if live is not None and digest(self.raw_book(live)) == digest(raw):
            return live, ""
        for b, r in self.snapshots:
            if digest(r) == digest(raw):
                return b, _note(b, live)
        book = ab.parse_book(raw)
        self.snapshots.append((book, raw))
        if self.reg is not None:
            self.reg.add_book(book)
            if LB.is_local(book.uid):
                self._install(raw, replace=False)
        return book, _note(book, live)

    # --- army lists ----------------------------------------------------------

    def load_list(self, path: str):
        """(ArmyList, ListResult) of a saved list resolved on this library."""
        army = army_list.load(path)
        return army, list_resolve.resolve_list(army, self.books)


def digest(raw) -> str:
    """Content hash of a JSON document (key order ignored)."""
    return hashlib.sha1(json.dumps(raw, sort_keys=True).encode("utf-8")
                        ).hexdigest()


def _note(book, live) -> str:
    now = "not in the library" if live is None else \
        f"library has {live.version}" + (" (different content)"
                                          if live.version == book.version
                                          else "")
    return f"{book.name} {book.version}: the session's copy is used ({now})"

