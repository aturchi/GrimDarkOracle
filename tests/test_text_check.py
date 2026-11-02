"""'changed' rules: the text each book has NOW against the
text the semantics were written for (text_sha1; an alias: its own
fingerprint in the target's alias_sha1), every book's own definition
checked, not only the first one loaded; rules_report --text and
tools/fingerprint.py."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS

import testpaths
from grimdarkoracle.data.af_book import RuleDef
from grimdarkoracle.rules import coverage as CV
from grimdarkoracle.rules.registry import RuleRegistry, text_sha1, validate

TEXT = "Once per game, roll one die."
SEM = {"rules": {"r1": {"name": "Feat", "text_sha1": text_sha1(TEXT),
                        "impl": "no_combat_effect"}}}


def book(name, text):
    return NS(name=name, rules={"r1": RuleDef("r1", "Feat", text)})


same, other = book("A", TEXT), book("B", TEXT + " Changed.")
reg = RuleRegistry(SEM, {}, [same, other])     # A's definition loaded first
assert reg.status("r1") == "ok"                # the first definition only
assert CV._changed_texts(reg, "r1", "Feat", [same, other]) == {
    "B": text_sha1(TEXT + " Changed.")}
assert CV._changed_texts(reg, "r1", "Feat", [same]) == {}
assert CV._changed_texts(reg, "nope", "Nope", [same]) == {}

# an alias (a2 -> r1) is checked on its OWN text against alias_sha1
ALIAS = "If this model has Feat, roll two dice."
alias_doc = {"rules": {"r1": dict(SEM["rules"]["r1"],
                                  alias_sha1={"a2": text_sha1(ALIAS)})}}


def with_alias(text):
    b = NS(name="C", rules={"a2": RuleDef("a2", "Bold", text,
                                          aliased_rule_id="r1")})
    return b, RuleRegistry(alias_doc, {}, [same, b])


b, r2 = with_alias(ALIAS)
assert r2.lookup("a2").expected_sha1("a2") == text_sha1(ALIAS)
assert CV._changed_texts(r2, "a2", "Bold", [same, b]) == {}
b, r2 = with_alias(ALIAS + " More.")
assert CV._changed_texts(r2, "a2", "Bold", [same, b]) == {
    "C": text_sha1(ALIAS + " More.")}
b = NS(name="C", rules={"a2": RuleDef("a2", "Bold", ALIAS,
                                      aliased_rule_id="r1")})
r3 = RuleRegistry(SEM, {}, [same, b])          # no fingerprint stored
assert CV._changed_texts(r3, "a2", "Bold", [same, b]) == {
    "C": text_sha1(ALIAS)}
# never fingerprinted counts as changed even with the target's very text
b = NS(name="C", rules={"a2": RuleDef("a2", "Bold", TEXT,
                                      aliased_rule_id="r1")})
r3 = RuleRegistry(SEM, {}, [same, b])
assert r3.lookup("a2").expected_sha1("a2") is None
assert CV._changed_texts(r3, "a2", "Bold", [same, b]) == {"C": text_sha1(TEXT)}
bad = {"format": "grimdarkoracle-semantics/1",
       "rules": {"r1": dict(SEM["rules"]["r1"], alias_sha1={"a2": "x"})}}
assert any("alias_sha1" in e for e in validate(bad))

if not testpaths.USING_SYNTHETIC:
    tool = os.path.join(testpaths.REPO_ROOT, "tools", "rules_report.py")
    MC = "a6Ze2uaBlNHX"                         # Mind Control, in 3 books

    def run(data, *args):
        r = subprocess.run([sys.executable, tool, "--data", data, *args],
                           capture_output=True, text=True)
        return r.returncode, r.stdout

    code, out = run(testpaths.DATA_DIR, "--text", "Mind Control")
    assert code == 0 and "matches the semantics" in out, out
    assert "Daemons of Lust, Jackals, Soul-Snatcher Cults" in out, out
    assert run(testpaths.DATA_DIR, "--text", "No Such Rule")[0] == 2
    with tempfile.TemporaryDirectory() as tmp:
        data = os.path.join(tmp, "army_forge")
        shutil.copytree(testpaths.DATA_DIR, data)
        # change the text in the book loaded SECOND (Jackals): before the
        # per-book check this went unnoticed
        hits = []
        for f in sorted(os.listdir(os.path.join(data, "books"))):
            path = os.path.join(data, "books", f)
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
            for r in raw.get("specialRules", []):
                if r.get("id") == MC and raw.get("name") == "Jackals":
                    r["description"] += " Changed."
                    hits.append(f)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(raw, fh)
        assert len(hits) == 1, hits
        code, out = run(data)
        assert code == 1, out
        line = next(x for x in out.splitlines() if MC in x)
        assert line.split()[0] == "changed", line
        detail = out.splitlines()[out.splitlines().index(line) + 1]
        assert "text now: Jackals" in detail and "Daemons" not in detail, \
            detail
        code, out = run(data, "--text", MC)
        assert code == 1 and "DIFFERS from the semantics" in out, out
        # the update report names the book whose text changed
        sys.path.insert(0, testpaths.REPO_ROOT)
        from grimdarkoracle.app import update_check
        from grimdarkoracle.app.library import Library
        lines = update_check.review(Library.load(data))
        assert any("Mind Control" in x and "text changed in: Jackals;" in x
                   for x in lines), lines

    # aliases: every alias of the books is fingerprinted; a change of an
    # alias's own text (Enhanced Devout, Blessed Sisters) is reported, and
    # tools/fingerprint.py accepts it in a copy of the semantics
    fp = os.path.join(testpaths.REPO_ROOT, "tools", "fingerprint.py")

    def fingerprint(data, sem, *args):
        r = subprocess.run([sys.executable, fp, "--data", data,
                            "--semantics", sem, *args],
                           capture_output=True, text=True)
        return r.returncode, r.stdout

    ED = "w7sENXkksVpG"
    shipped = os.path.join(testpaths.REPO_ROOT, "grimdarkoracle", "rules",
                           "semantics.json")
    with tempfile.TemporaryDirectory() as tmp:
        sem = os.path.join(tmp, "semantics.json")
        shutil.copy(shipped, sem)
        code, out = fingerprint(testpaths.DATA_DIR, sem, "--aliases")
        assert (code, out.strip()) == (0, "nothing to do"), out
        data = os.path.join(tmp, "army_forge")
        shutil.copytree(testpaths.DATA_DIR, data)
        for f in os.listdir(os.path.join(data, "books")):
            path = os.path.join(data, "books", f)
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
            for r in raw.get("specialRules", []):
                if r.get("id") == ED:
                    r["description"] = r["description"].replace(
                        "always", "now always")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(raw, fh)
        code, out = run(data, "--semantics", sem)
        assert code == 1, out
        line = next(x for x in out.splitlines() if ED in x)
        assert line.split()[0] == "changed", line
        assert "text now: Blessed Sisters" in out.splitlines()[
            out.splitlines().index(line) + 1]
        code, out = run(data, "--semantics", sem, "--text", ED)
        assert code == 1 and "DIFFERS" in out and "alias of" in out, out
        code, out = fingerprint(data, sem, "Enhanced Devout")
        assert code == 0 and "alias of Enhanced Brutal" in out, out
        code, out = run(data, "--semantics", sem)
        assert code == 0, out                   # accepted: ok again
        with open(sem, encoding="utf-8") as fh:
            doc = json.load(fh)
        with open(shipped, encoding="utf-8") as fh:
            ref = json.load(fh)
        diff = [k for k in ref["rules"] if ref["rules"][k] != doc["rules"][k]]
        assert len(diff) == 1, diff             # only Enhanced Brutal's entry
        assert fingerprint(data, sem, "No Such Rule")[0] == 1

print("test_text_check OK")
