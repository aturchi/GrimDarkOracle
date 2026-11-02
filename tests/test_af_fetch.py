"""Offline tests of tools/af_fetch.py (no network: get_json is faked)."""
import copy
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout

import testpaths

sys.path.insert(0, os.path.join(testpaths.REPO_ROOT, "tools"))
import af_fetch as af                                     # noqa: E402

BOOKS = [{"uid": "aaa", "name": "Alpha", "versionString": "3.6.0"},
         {"uid": "bbb", "name": "Beta", "versionString": "3.6.0"}]
SERVER = {"rules": {"rules": [{"id": "r1", "name": "AP"}], "traits": []},
          "aaa": {"uid": "aaa", "versionString": "3.6.0", "units": [1]},
          "bbb": {"uid": "bbb", "versionString": "3.6.0", "units": [2]}}
CALLS = []


def fake_get_json(url, delay):
    """Serve the listing (page 1 only, repeated if the page is ignored),
    the core rules and the books from SERVER."""
    CALLS.append(url)
    if "/army-books?" in url:
        return list(BOOKS)
    if "/rules/common/" in url:
        return SERVER["rules"]
    uid = url.split("/army-books/")[1].split("?")[0]
    return regen_section_ids(SERVER[uid])


def regen_section_ids(book):
    """As Army Forge does: a new section 'id' at every request (the
    section 'uid' stays)."""
    book = copy.deepcopy(book)
    for p in book.get("upgradePackages", []):
        for s in p["sections"]:
            s["id"] = f"id{len(CALLS)}"
    return book


af.get_json = fake_get_json

# select(): by uid or name, case-insensitive
assert [b["uid"] for b in af.select(BOOKS, ["BETA"])] == ["bbb"]
assert [b["uid"] for b in af.select(BOOKS, ["aaa"])] == ["aaa"]
assert af.select(BOOKS, None) == BOOKS

# list_books(): stops when a page brings nothing new (server ignores page)
CALLS.clear()
assert len(af.list_books("grimdark-future", "official", 0)) == 2
assert len(CALLS) == 2, CALLS

TMP = tempfile.mkdtemp(prefix="grimdarkoracle_fetch_")
try:
    out = os.path.join(TMP, "af")
    assert af.main(["--out", out, "--delay", "0"]) == 0
    idx = json.load(open(os.path.join(out, "index.json")))
    assert [e["file"] for e in idx["books"]] == ["books/aaa.json",
                                                 "books/bbb.json"]
    assert os.path.isfile(os.path.join(out, "rules", "common_2.json"))

    # Same version: nothing downloaded again.
    CALLS.clear()
    assert af.main(["--out", out, "--delay", "0"]) == 0
    assert not any("/army-books/aaa" in c for c in CALLS)

    # Forced refresh of identical content: no .prev.json is created.
    assert af.main(["--out", out, "--delay", "0", "--force"]) == 0
    assert not os.path.exists(os.path.join(out, "books", "aaa.prev.json"))

    # Volatile section ids: a forced refresh does not rotate .prev.json;
    # a real change of a section does.
    PKG = {"uid": "p1", "sections": [{"uid": "s1", "label": "Replace"}]}
    SERVER["bbb"] = {"uid": "bbb", "versionString": "3.6.0", "units": [2],
                     "upgradePackages": [PKG]}
    bprev = os.path.join(out, "books", "bbb.prev.json")
    assert af.main(["--out", out, "--delay", "0", "--force",
                    "--only", "Beta", "--no-report"]) == 0
    assert json.load(open(bprev))["units"] == [2]       # rotated once
    os.remove(bprev)
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert af.main(["--out", out, "--delay", "0", "--force",
                        "--only", "Beta", "--no-report"]) == 0
    assert "(content unchanged)" in buf.getvalue(), buf.getvalue()
    assert not os.path.exists(bprev)
    PKG["sections"][0]["label"] = "Upgrade"
    assert af.main(["--out", out, "--delay", "0", "--force",
                    "--only", "Beta", "--no-report"]) == 0
    assert json.load(open(bprev))["upgradePackages"][0]["sections"][0][
        "label"] == "Replace"
    assert af.stable_view({"rules": []}) == {"rules": []}

    # Changed content: the old copy is rotated to .prev.json.
    SERVER["aaa"] = {"uid": "aaa", "versionString": "3.6.0", "units": [9]}
    assert af.main(["--out", out, "--delay", "0", "--force",
                    "--only", "Alpha"]) == 0
    prev = json.load(open(os.path.join(out, "books", "aaa.prev.json")))
    assert prev["units"] == [1]
    # A partial run keeps the other books in the index.
    idx = json.load(open(os.path.join(out, "index.json")))
    assert {e["uid"] for e in idx["books"]} == {"aaa", "bbb"}

    # The update report follows a download that changed something: a
    # book, or the core rules alone; never with --no-report, never when
    # nothing changed.
    lists = os.path.join(TMP, "lists")
    for argv, shown in ((["--force", "--only", "Beta"], False),
                        (["--force", "--no-report"], False),
                        ([], True)):
        if shown:
            SERVER["rules"] = {"rules": [{"id": "r1", "name": "AP",
                                          "description": "new"}],
                               "traits": []}
        buf = io.StringIO()
        with redirect_stdout(buf):
            assert af.main(["--out", out, "--delay", "0", "--lists", lists]
                           + argv) == 0
        assert ("== Saved army lists" in buf.getvalue()) == shown, argv

    # Unknown --only: exit code 2.
    assert af.main(["--out", out, "--delay", "0", "--only", "zzz"]) == 2
finally:
    shutil.rmtree(TMP, ignore_errors=True)
print("af_fetch: OK")
