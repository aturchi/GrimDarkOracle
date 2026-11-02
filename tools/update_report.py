#!/usr/bin/env python3
"""Update report: what changed in the downloaded books
against the previous copies af_fetch kept, the implemented rules and
spells whose Army Forge text changed (their semantics must be reviewed),
and the saved army lists affected. Exit code 1 when something needs a
look (rules / spells to review, lists, unreadable copies).

    python3 tools/update_report.py                    # every book
    python3 tools/update_report.py --only "DAO Union" --lists ~/lists
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from grimdarkoracle import app_paths  # noqa: E402
from grimdarkoracle.app import update_check  # noqa: E402
from grimdarkoracle.app.library import Library, default_root  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=default_root(),
                    help="Army Forge download (af_fetch --out)")
    ap.add_argument("--lists", default=os.path.join(app_paths.app_dir(),
                                                    "lists"))
    ap.add_argument("--only", nargs="*", help="book names or uids")
    args = ap.parse_args(argv)
    lib = Library.load(args.data)
    uids = None
    if args.only:
        wanted = {o.lower() for o in args.only}
        uids = {u for u, b in lib.books.items()
                if u.lower() in wanted or b.name.lower() in wanted}
        if not uids:
            print("No book matches --only", file=sys.stderr)
            return 2
    for w in lib.warnings:
        print(f"!! {w}")
    rep = update_check.build(lib, uids, args.lists)
    print(update_check.to_text(rep), end="")
    return 0 if rep.clean else 1


if __name__ == "__main__":
    sys.exit(main())
