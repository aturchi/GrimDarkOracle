#!/usr/bin/env python3
"""Rule and spell coverage report: which rules and spells of the downloaded
books the semantics implement, and which changed text or are unmapped.

    python3 tools/rules_report.py                         # all books
    python3 tools/rules_report.py --only "DAO Union" "Battle Brothers" -v
    python3 tools/rules_report.py --text "Mind Control"   # a rule's texts

'changed' = the text a book has NOW differs from the text the semantics
were written for (the entry's text_sha1), whatever the previous download
said; tools/update_report.py compares with the previous download.
Exit code 0 only when every rule and spell of the books is ok.
"""
import argparse
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from grimdarkoracle.app.library import default_root  # noqa: E402
from grimdarkoracle.data import af_book  # noqa: E402
from grimdarkoracle.rules import coverage, registry, spells  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=default_root(),
                    help="Army Forge download (af_fetch --out)")
    ap.add_argument("--semantics", default=None,
                    help="semantics.json (default: the shipped one)")
    ap.add_argument("--spells", default=None,
                    help="spells.json (default: the shipped one)")
    ap.add_argument("--only", nargs="*", help="book names or uids")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="also list the rules that are ok")
    ap.add_argument("--text", metavar="RULE",
                    help="print the current text of a rule (name or id) in "
                         "every book, with its hash and the mapped one")
    args = ap.parse_args(argv)
    core = af_book.load_core_rules(os.path.join(args.data, "rules",
                                                "common_2.json"))
    every = [af_book.load_book(p) for p in sorted(glob.glob(
        os.path.join(args.data, "books", "*.json")))
        if not p.endswith(".prev.json")]
    books = every
    if args.only:
        wanted = {o.lower() for o in args.only}
        books = [b for b in every
                 if b.uid.lower() in wanted or b.name.lower() in wanted]
    # Every book's rule definitions: a rule a book only receives (an aura,
    # a buff) may be defined in another book; coverage stays on 'books'.
    reg = registry.RuleRegistry(registry.load_semantics(args.semantics), core,
                                every)
    if args.text:
        return show_text(reg, core, every, args.text)
    cov = coverage.coverage(reg, books)
    print(f"{len(books)} books")
    print(coverage.report(cov, args.verbose))
    # Every book's spell texts: a same-id spell of an unchosen book is not
    # a changed text; coverage stays on 'books'.
    sreg = spells.SpellRegistry(spells.load(args.spells), reg, every)
    rows = sreg.coverage(books)
    counts: dict = {}
    for _b, _s, st in rows:
        counts[st] = counts.get(st, 0) + 1
    print("spells: " + ", ".join(f"{k} {v}"
                                 for k, v in sorted(counts.items())))
    for b, s, st in rows:
        if st != "ok" or args.verbose:
            print(f"  [{st}] {b}: {s}")
    return 0 if cov.clean and set(counts) <= {"ok"} else 1


def show_text(reg, core, books, rule: str) -> int:
    """The texts of 'rule' (name or id) in the core rules and the books,
    grouped by text, each with its SHA-1; the semantics entry's hash and
    whether it matches. Exit code 0 when every text matches, else 1."""
    key = rule.lower()
    found: dict = {}                    # (id, sha1) -> (text, [where])
    sources = [("core rules", core)] + [(b.name, b.rules) for b in books]
    for where, rules in sources:
        for d in rules.values():
            if key in (d.id.lower(), d.name.lower()):
                h = registry.text_sha1(d.description)
                found.setdefault((d.id, h), (d.description, []))[1].append(
                    where)
    if not found:
        print(f"no rule {rule!r} in the core rules or the books")
        return 2
    ok = True
    for (rid, h), (text, where) in sorted(found.items()):
        sem = reg.lookup(rid)
        mapped = sem.expected_sha1(rid) if sem is not None else None
        alias = f" (alias of {sem.name})" if sem is not None and \
            sem.rule_id != rid else ""
        if sem is None:
            state, ok = "not mapped", False
        elif mapped is None:
            state, ok = f"no fingerprint stored{alias}", False
        elif mapped == h:
            state = f"matches the semantics{alias}"
        else:
            state, ok = f"DIFFERS from the semantics ({mapped[:10]}){alias}", \
                False
        print(f"{rid}  sha1 {h[:10]}  {state}\n  in: {', '.join(where)}\n"
              f"  {text}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
