"""Resolve a whole army list against the loaded books.

For every entry: link (links.py) -> resolve() each copy -> combine() when
combined -> overrides -> checks of Hero joins. Pure: the books are passed
in as {uid: Book}; nothing is read from disk here.
"""
from dataclasses import dataclass, field

from grimdarkoracle.data import links, overrides
from grimdarkoracle.data.resolve import ResolvedUnit, combine, resolve

HERO = "Hero"
UNIQUE_HERO = "Unique Hero"      # counts as having Hero, once per army
HERO_NAMES = (HERO, UNIQUE_HERO)  # recognised by name
MAX_JOIN_TOUGH = 6          # Hero rule 3.6: "Heroes with up to Tough(6)"


@dataclass
class EntryResult:
    key: str
    unit: ResolvedUnit | None               # None: unit or book missing
    link: links.LinkResult
    issues: list[str] = field(default_factory=list)   # entry-level

    @property
    def points(self) -> int:
        return self.unit.points if self.unit else 0

    @property
    def valid(self) -> bool:
        return self.unit is not None and not self.link.invalid


@dataclass
class ListResult:
    entries: dict[str, EntryResult]
    issues: list[str] = field(default_factory=list)   # list-level

    @property
    def points(self) -> int:
        return sum(e.points for e in self.entries.values())


def is_hero(ru: ResolvedUnit) -> bool:
    return any(r.name in HERO_NAMES for m in ru.models for r in m.rules)


def is_unique(ru: ResolvedUnit) -> bool:
    """The unit may be taken once per army (Unique Hero)."""
    return any(r.name == UNIQUE_HERO for m in ru.models for r in m.rules)


def _resolve_entry(lu, book) -> EntryResult:
    link = links.link_unit(book, lu)
    if link.unit_id is None:
        return EntryResult(lu.key, None, link, list(link.invalid))
    ru = resolve(book, link.unit_id, [r.choice() for r in link.choices])
    if lu.combined:
        refs_b = link.choices if link.choices_b is None else link.choices_b
        ru = combine(ru, resolve(book, link.unit_id,
                                 [r.choice() for r in refs_b]))
    ru = overrides.apply(ru, lu.overrides)
    return EntryResult(lu.key, ru, link, list(link.invalid))


def join_issues(hero: ResolvedUnit, host: ResolvedUnit) -> list[str]:
    """Why 'hero' cannot join 'host' (core 3.6 Hero rule); empty when
    it can. Chains and one Hero per host are list-level (_check_joins)."""
    out = []
    if not is_hero(hero):
        out.append("only Heroes may join a unit")
    if max(m.tough for m in hero.models) > MAX_JOIN_TOUGH:
        out.append(f"Heroes above Tough({MAX_JOIN_TOUGH}) cannot join a unit")
    if hero.size != 1:
        out.append("a joining Hero must be a single model")
    if host.size < 2:
        out.append("Heroes may only join multi-model units")
    if is_hero(host):
        out.append("the host unit already has a Hero")
    return out


def _check_joins(army, entries) -> None:
    """Hero joins (core 3.6): a Hero with up to Tough(6) joins one
    multi-model unit that has no other Hero; no chains of joins."""
    hosts: dict[str, list[str]] = {}
    for lu in army.units:
        if lu.joined_to is None:
            continue
        e = entries[lu.key]
        host = entries.get(lu.joined_to)
        host_lu = army.unit(lu.joined_to)
        if host is None or host.unit is None:
            e.issues.append(f"joined to missing unit {lu.joined_to!r}")
            continue
        if e.unit is None:
            continue
        e.issues.extend(join_issues(e.unit, host.unit))
        if host_lu.joined_to is not None:
            e.issues.append("cannot join a unit that is itself joined")
        hosts.setdefault(lu.joined_to, []).append(lu.key)
    for host_key, guests in hosts.items():
        if len(guests) > 1:
            for k in guests:
                entries[k].issues.append(
                    f"unit {host_key!r} already has another Hero joined")


def resolve_list(army, books: dict) -> ListResult:
    """Resolve every entry of 'army' with the books {uid: Book}."""
    entries = {lu.key: _resolve_entry(lu, books.get(lu.book))
               for lu in army.units}
    _check_joins(army, entries)
    issues = []
    for uid, version in army.books.items():
        b = books.get(uid)
        if b is None:
            issues.append(f"book {uid} not loaded")
        elif version and b.version != version:
            issues.append(f"{b.name}: list saved with {version}, "
                          f"book is now {b.version}")
    return ListResult(entries, issues)
