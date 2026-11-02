#!/usr/bin/env python3
"""Store text fingerprints in semantics.json: the SHA-1 of the
rule text a mapping was reviewed for.

    python3 tools/fingerprint.py --aliases          # aliases not yet stored
    python3 tools/fingerprint.py "Mind Control"     # accept the CURRENT text

--aliases stores, for every Army Forge alias (a book rule mapped through
another entry: Enhanced Devout -> Enhanced Brutal) that has none yet, the
fingerprint of its own text in the target's 'alias_sha1'. Run it after
mapping new books. A RULE (name or id) is accepted after its new text was
reviewed and found to mean the same: its fingerprint ('text_sha1', or
'alias_sha1' for an alias) becomes the hash of the text the books have now.
Never accept a text whose meaning changed: rewrite the semantics instead.
Spells are keyed by their text hash and are not handled here.

The file written is --semantics, else the one the programs read (a user
copy next to the program when present, else the shipped one).
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from grimdarkoracle import app_paths  # noqa: E402
from grimdarkoracle.app.library import default_root  # noqa: E402
from grimdarkoracle.data import af_book  # noqa: E402
from grimdarkoracle.rules import registry  # noqa: E402


def semantics_path(path: str | None) -> str:
    if path:
        return path
    for p in app_paths.resource(registry.RESOURCE):
        if p and os.path.isfile(p):
            return p
    raise FileNotFoundError("no semantics.json found")


def texts(core, books) -> dict:
    """{rule id: {sha1: [where]}} of every definition."""
    out: dict = {}
    for where, rules in [("core rules", core)] + [(b.name, b.rules)
                                                  for b in books]:
        for d in rules.values():
            out.setdefault(d.id, {}).setdefault(
                registry.text_sha1(d.description), []).append(where)
    return out


def store(doc, sem, rid: str, sha: str) -> str | None:
    """Write 'sha' as the fingerprint of 'rid' in the entry 'sem'; the old
    value (None if there was none)."""
    e = doc["rules"][sem.rule_id]
    if rid == sem.rule_id:
        old, e["text_sha1"] = e["text_sha1"], sha
        return old
    aliases = e.setdefault("alias_sha1", {})
    old, aliases[rid] = aliases.get(rid), sha
    e["alias_sha1"] = dict(sorted(aliases.items()))
    return old


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rules", nargs="*", help="rule names or ids to accept")
    ap.add_argument("--aliases", action="store_true",
                    help="store the missing alias fingerprints")
    ap.add_argument("--data", default=default_root(),
                    help="Army Forge download (af_fetch --out)")
    ap.add_argument("--semantics", default=None,
                    help="semantics.json to update")
    args = ap.parse_args(argv)
    if not args.aliases and not args.rules:
        ap.error("give --aliases or rule names")
    path = semantics_path(args.semantics)
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    core = af_book.load_core_rules(os.path.join(args.data, "rules",
                                                "common_2.json"))
    books = [af_book.load_book(p) for p in sorted(glob.glob(
        os.path.join(args.data, "books", "*.json")))
        if not p.endswith(".prev.json")]
    reg = registry.RuleRegistry(doc, core, books)
    by_id = texts(core, books)
    names = {d.name.lower(): d.id for b in books for d in b.rules.values()}
    names.update({d.name.lower(): d.id for d in core.values()})
    todo, errors = [], 0
    if args.aliases:
        for rid in sorted(by_id):
            sem = reg.lookup(rid)
            if sem is not None and sem.rule_id != rid and \
                    sem.expected_sha1(rid) is None:
                todo.append(rid)
    for r in args.rules:
        rid = r if r in by_id else names.get(r.lower())
        if rid is None:
            print(f"no rule {r!r} in the core rules or the books")
            errors += 1
            continue
        todo.append(rid)
    for rid in todo:
        sem, found = reg.lookup(rid), by_id[rid]
        if sem is None:
            print(f"{rid}: not mapped, nothing to fingerprint")
            errors += 1
            continue
        if len(found) > 1:
            print(f"{rid}: the books have {len(found)} different texts ("
                  + "; ".join(", ".join(w) for w in found.values())
                  + "): review each, nothing written")
            errors += 1
            continue
        sha = next(iter(found))
        old = store(doc, sem, rid, sha)
        name = reg.defs[rid].name if rid in reg.defs else rid
        kind = "text" if rid == sem.rule_id else f"alias of {sem.name}"
        print(f"{name} ({rid}, {kind}): {old[:10] if old else 'none'} -> "
              f"{sha[:10]}")
    if todo and errors < len(todo):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, indent=1, ensure_ascii=True) + "\n")
        print(f"written: {path}")
    elif not todo:
        print("nothing to do")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
