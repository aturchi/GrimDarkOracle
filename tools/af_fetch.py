#!/usr/bin/env python3
"""Download army books and core special rules from Army Forge (OPR).

Raw JSON is saved untouched, so the importer can be rewritten later
without downloading again:

    <out>/books/<uid>.json        one file per army book
    <out>/books/<uid>.prev.json   previous copy, kept when a book changes
    <out>/rules/common_<gs>.json  core special rules (+ .prev.json likewise)
    <out>/index.json              uid, name, version and file of each book

Standard library only. The data belongs to OPR: keep it for personal
use and do not commit it to the repository.

After a download that changed something, the update report is printed
(grimdarkoracle.app.update_check): what changed in each book
against its previous copy, the implemented rules and spells whose text
changed, the saved lists affected. --no-report skips it;
tools/update_report.py prints it again at any time.

Examples:
    python3 tools/af_fetch.py                         # all official GF books
                                                      # -> <repo>/data/army_forge
    python3 tools/af_fetch.py --only "DAO Union" 78qp9l5alslt6yj8
    python3 tools/af_fetch.py --force --delay 3
    python3 tools/af_fetch.py --lists ~/my_lists     # lists to check
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from grimdarkoracle import app_paths  # noqa: E402

BASE = "https://army-forge.onepagerules.com/api"
# Default output next to the program (repository root from source, the
# executable's folder in a build), whatever the working directory.
DEFAULT_OUT = os.path.join(app_paths.app_dir(), "data", "army_forge")
DEFAULT_LISTS = os.path.join(app_paths.app_dir(), "lists")
USER_AGENT = "GrimDarkOracle-af_fetch/0.1 (personal use)"


def get_json(url, delay):
    """GET a JSON document, then sleep 'delay' seconds (be polite)."""
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    time.sleep(delay)
    return data


def list_books(slug, filters, delay, max_pages=20):
    """Return the book listing, walking pages until one brings nothing new.

    The listing observed on 2026-10-31 returned all 49 official GF books
    on page 1; the loop also stops if the server ignores 'page'.
    """
    books, seen = [], set()
    for page in range(1, max_pages + 1):
        query = urllib.parse.urlencode({
            "filters": filters, "gameSystemSlug": slug, "searchText": "",
            "page": page, "unitCount": 0, "balanceValid": "false",
            "customRules": "true", "fans": "false", "sortBy": "null"})
        batch = get_json(f"{BASE}/army-books?{query}", delay)
        if not isinstance(batch, list):
            raise ValueError(f"unexpected listing payload on page {page}")
        new = [b for b in batch if b.get("uid") not in seen]
        if not new:
            break
        seen.update(b["uid"] for b in new)
        books.extend(new)
    return books


def save_json(path, data):
    """Atomic write: never leave a truncated file behind."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_local(path):
    """Parsed content of an already downloaded file, or None."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def local_version(path):
    """versionString of an already downloaded book, or None."""
    data = load_local(path)
    return data.get("versionString") if isinstance(data, dict) else None


def store_file(path, data):
    """Save a JSON file, rotating the old copy to .prev.json only if the content
    really changed: a forced refresh of identical content must not
    overwrite the previous revision. Returns True when the file changed."""
    old = load_local(path)
    if old == data:
        return False
    if old is not None:
        # Keep the previous copy: Army Forge serves no history.
        os.replace(path, path[:-len(".json")] + ".prev.json")
    save_json(path, data)
    return True


def merge_index(path, entries):
    """Update the existing index by uid, so a partial run (--only) does not
    drop the books downloaded earlier."""
    try:
        with open(path, encoding="utf-8") as f:
            old = {e["uid"]: e for e in json.load(f).get("books", [])}
    except (OSError, ValueError):
        old = {}
    old.update({e["uid"]: e for e in entries})
    return sorted(old.values(), key=lambda e: e["name"].lower())


def select(books, only):
    """Keep the books whose uid or name (case-insensitive) is in 'only'."""
    if not only:
        return books
    wanted = {o.strip().lower() for o in only}
    return [b for b in books
            if b["uid"].lower() in wanted or b["name"].lower() in wanted]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--gs", type=int, default=2, help="game system id (GF=2)")
    ap.add_argument("--slug", default="grimdark-future")
    ap.add_argument("--filters", default="official")
    ap.add_argument("--only", nargs="*", help="book names or uids")
    ap.add_argument("--delay", type=float, default=2.0,
                    help="seconds between requests")
    ap.add_argument("--force", action="store_true",
                    help="download even if the local version is the same")
    ap.add_argument("--lists", default=DEFAULT_LISTS,
                    help="folder of the army lists the report checks")
    ap.add_argument("--no-report", action="store_true",
                    help="do not print the update report")
    args = ap.parse_args(argv)

    try:
        books = select(list_books(args.slug, args.filters, args.delay),
                       args.only)
    except Exception as exc:  # network down, API changed...
        print(f"listing failed: {exc}", file=sys.stderr)
        return 1
    if args.only and not books:
        print("No book matches --only", file=sys.stderr)
        return 2

    rules_path = os.path.join(args.out, "rules", f"common_{args.gs}.json")
    try:
        rules = get_json(f"{BASE}/rules/common/{args.gs}", args.delay)
    except Exception as exc:
        print(f"core rules failed: {exc}", file=sys.stderr)
        return 1
    core_changed = store_file(rules_path, rules)
    print(f"core rules -> {rules_path}" if core_changed
          else "core rules unchanged")

    index, failed, changed = [], [], []
    for b in books:
        path = os.path.join(args.out, "books", f"{b['uid']}.json")
        entry = {"uid": b["uid"], "name": b["name"],
                 "versionString": b.get("versionString"),
                 "factionName": b.get("factionName"),
                 # Forward slashes: the index must read the same on any OS.
                 "file": f"books/{b['uid']}.json"}
        if not args.force and local_version(path) == b.get("versionString"):
            print(f"  = {b['name']} {b.get('versionString')} (up to date)")
            index.append(entry)
            continue
        try:
            data = get_json(f"{BASE}/army-books/{b['uid']}?gameSystem={args.gs}",
                            args.delay)
            new = store_file(path, data)
            index.append(entry)
            if new:
                changed.append(b["uid"])
            mark = "+" if new else "="
            print(f"  {mark} {b['name']} {b.get('versionString')}"
                  + ("" if new else " (content unchanged)"))
        except Exception as exc:  # report and keep going
            failed.append(b["name"])
            print(f"  ! {b['name']}: {exc}", file=sys.stderr)

    index_path = os.path.join(args.out, "index.json")
    save_json(index_path, {"game_system": args.gs,
                           "books": merge_index(index_path, index)})
    if (changed or core_changed) and not args.no_report:
        print(report(args.out, changed, args.lists))
    if failed:
        print(f"{len(failed)} failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


def report(out, uids, lists_dir) -> str:
    """The update report on the new download (never fails the fetch)."""
    try:
        from grimdarkoracle.app import update_check
        from grimdarkoracle.app.library import Library
        lib = Library.load(out)
        text = update_check.to_text(update_check.build(lib, set(uids),
                                                       lists_dir))
        return "\n".join(lib.warnings + [text]) if lib.warnings else text
    except Exception as exc:              # report only, the data is saved
        return f"update report not available: {exc}"


if __name__ == "__main__":
    sys.exit(main())
