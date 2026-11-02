#!/usr/bin/env python3
"""Survey downloaded Army Forge books: parse warnings and section shapes.

Run after every af_fetch refresh: a new section shape or a parse warning
is exactly what options_core and the import report must learn about.

    python3 tools/af_survey.py                    # all downloaded books
    python3 tools/af_survey.py --data DIR --examples 2
"""
import argparse
import collections
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from grimdarkoracle.app.library import default_root  # noqa: E402
from grimdarkoracle.data import af_book  # noqa: E402


def quant(q):
    """Compact text of a Quant: '-', 'all', 'any', '=1', '<=2'."""
    if q is None:
        return "-"
    return {"exactly": f"={q.value}", "up to": f"<={q.value}"}.get(q.kind,
                                                                  q.kind)


def shape(s):
    """Section shape key: variant, per-model, affects, select, targets."""
    return (s.variant, "model" if s.model else "unit", quant(s.affects),
            quant(s.select), "targets" if s.targets else "-")


def survey(books, examples):
    """Print section shapes (count + examples), then all parse warnings."""
    shapes = collections.Counter()
    seen = collections.defaultdict(list)
    for b in books:
        for p in b.packages.values():
            for s in p.sections:
                k = shape(s)
                shapes[k] += 1
                if len(seen[k]) < examples:
                    seen[k].append(f"{b.name}: {s.label}")
    print(f"{len(books)} books, {len(shapes)} section shapes")
    for k, n in shapes.most_common():
        print(f"{n:6d}  {' | '.join(k)}")
        for e in seen[k]:
            print(f"        {e}")
    rel = [(b.name, b.faction_relation, b.faction_name)
           for b in books if b.faction_relation]
    print(f"\n{len(rel)} sub-faction books (self-contained, transforms ignored)")
    warnings = [(b.name, w) for b in books for w in b.warnings]
    print(f"\n{len(warnings)} parse warnings")
    for name, w in warnings:
        print(f"  {name}: {w}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=default_root(),
                    help="Army Forge download (af_fetch --out)")
    ap.add_argument("--examples", type=int, default=1)
    args = ap.parse_args(argv)
    paths = sorted(p for p in glob.glob(os.path.join(args.data, "books",
                                                     "*.json"))
                   if not p.endswith(".prev.json"))
    if not paths:
        print(f"no books under {args.data}", file=sys.stderr)
        return 1
    survey([af_book.load_book(p) for p in paths], args.examples)
    return 0


if __name__ == "__main__":
    sys.exit(main())
