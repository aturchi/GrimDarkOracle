"""Coverage of the semantics registry over army books.

Lists every rule a book can put on the table (unit, weapon and item
rules, and everything any upgrade option can grant) with its status in
the registry: ok / changed / todo / unmapped / undefined. This is the
import-time report: after an Army Forge refresh, 'changed' and 'unmapped'
are exactly the rules to review.

'changed' is measured against the SEMANTICS, not against the previous
download: the text a book has now differs from the text the entry was
written for (its 'text_sha1' in semantics.json; an Army Forge alias
mapped through its target: the alias's own fingerprint, 'alias_sha1' of
the target's entry). Every book's own definition is checked, not only the
first one loaded. The previous download is compared by the update report
(data.book_diff, the *.prev.json copies).
"""
from collections import defaultdict
from dataclasses import dataclass, field

from grimdarkoracle.data.af_book import Item
from grimdarkoracle.data.local_books import PREFIX as LOCAL
from grimdarkoracle.rules.registry import text_sha1

STATUSES = ("ok", "todo", "changed", "unmapped", "undefined")


def used_rules(book) -> dict:
    """{rule id: (name, set of unit names using it)} for one book."""
    out: dict = {}

    def add(rules, unit):
        for r in rules:
            out.setdefault(r.id, (r.name, set()))[1].add(unit.name)

    def add_weapons(weapons, unit):
        for w in weapons:
            add(w.rules, unit)

    for u in book.units.values():
        add(u.rules, u)
        add_weapons(u.weapons, u)
        for it in u.items:
            add(it.rules, u)
            add_weapons(it.weapons, u)
        for pkg in book.unit_packages(u):
            for sec in pkg.sections:
                for opt in sec.options:
                    for g in opt.gains:
                        add(g.rules, u)
                        if isinstance(g, Item):
                            add_weapons(g.weapons, u)
    return out


@dataclass
class Coverage:
    # status -> {rule id: (name, {book name: n units})}
    by_status: dict = field(default_factory=lambda: {s: {} for s in STATUSES})
    # 'changed' rules: rule id -> (hash the semantics were written for,
    # {where the text differs (book name or "core rules"): its hash now})
    changed: dict = field(default_factory=dict)

    def count(self, status: str) -> int:
        return len(self.by_status[status])

    @property
    def clean(self) -> bool:
        """No rule left to review."""
        return all(not self.by_status[s] for s in STATUSES if s != "ok")


def _add_granted(registry, seen, names) -> None:
    """Rules granted by used rules (auras) count as used, transitively,
    with the books and unit counts of their granter."""
    todo = list(seen)
    while todo:
        rid = todo.pop()
        sem = registry.lookup(rid, names.get(rid, ""))
        for eff in sem.effects if sem else ():
            if eff.primitive != "grant_rule":
                continue
            target = eff.value["rule"]
            fresh = target not in seen
            where = seen.setdefault(target, {})
            for book, n in seen[rid].items():
                where[book] = max(where.get(book, 0), n)
            if fresh:
                d = registry.defs.get(target)
                names[target] = d.name if d else target
                todo.append(target)


def coverage(registry, books) -> Coverage:
    """Coverage of 'registry' over 'books' (books are added to it)."""
    cov = Coverage()
    seen: dict = defaultdict(dict)
    names: dict = {}
    for b in books:
        registry.add_book(b)
        for rid, (name, units) in used_rules(b).items():
            seen[rid][b.name] = len(units)
            names[rid] = name
    _add_granted(registry, seen, names)
    for rid, where in seen.items():
        st = registry.status(rid, names[rid])
        texts = _changed_texts(registry, rid, names[rid], books)
        if texts and st in ("ok", "todo"):
            st = "changed"              # a book loaded later changed it
        if st == "changed":
            sem = registry.lookup(rid, names[rid])
            exp = sem.expected_sha1(rid) if texts else sem.text_sha1
            if not texts:               # the target's own text changed
                d = registry.defs.get(sem.rule_id)
                texts = {f"{sem.name} (its target)": text_sha1(
                    d.description) if d else "(no definition)"}
            cov.changed[rid] = (exp or "(none)", texts)
        cov.by_status[st][rid] = (names[rid], where)
    return cov


def _changed_texts(registry, rid, name, books) -> dict:
    """{book name (or "core rules"): SHA-1 of its text} where the text of
    'rid' differs from the fingerprint its semantics expect: the entry's
    'text_sha1' for a rule mapped on its own id, the alias's 'alias_sha1'
    for an Army Forge alias (none stored = never reviewed: every text
    counts as changed). Each book's own definition counts; a custom rule
    of a local book aliased to an official one is the user's and has no
    fingerprint to check."""
    sem = registry.lookup(rid, name)
    if sem is None:
        return {}
    if rid in registry.core and sem.rule_id == rid:
        h = text_sha1(registry.core[rid].description)
        return {} if h == sem.text_sha1 else {"core rules": h}
    exp = sem.expected_sha1(rid)
    out = {}
    for b in books:
        if sem.rule_id != rid and getattr(b, "uid", "").startswith(LOCAL):
            continue
        d = b.rules.get(rid)
        if d is not None and text_sha1(d.description) != exp:
            out[b.name] = text_sha1(d.description)
    d = registry.defs.get(rid)
    if not out and d is not None and rid not in registry.core and \
            not (sem.rule_id != rid and rid.startswith(LOCAL)) and \
            text_sha1(d.description) != exp:
        out["(definition)"] = text_sha1(d.description)
    return out

def report(cov: Coverage, verbose: bool = False) -> str:
    """Text report: counts, then the rules to review (all if verbose)."""
    lines = ["Rule coverage: " + ", ".join(
        f"{s} {cov.count(s)}" for s in STATUSES)]
    for st in STATUSES:
        if st == "ok" and not verbose:
            continue
        for rid, (name, where) in sorted(cov.by_status[st].items(),
                                         key=lambda kv: kv[1][0]):
            books = ", ".join(f"{b} ({n})" for b, n in sorted(where.items()))
            lines.append(f"  {st:9s} {name:32s} {rid}  {books}")
            if st == "changed" and rid in cov.changed:
                mapped, texts = cov.changed[rid]
                now = ", ".join(f"{b} {h[:10]}"
                                for b, h in sorted(texts.items()))
                lines.append(f"            mapped text {mapped[:10]}, "
                             f"text now: {now}")
    return "\n".join(lines)
