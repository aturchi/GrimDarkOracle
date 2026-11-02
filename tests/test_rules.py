"""Rule semantics registry: validation, lookup (alias, core name), text
hashes, coverage report."""
import copy

import testpaths
import make_synthetic
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.rules import coverage, registry
from grimdarkoracle.rules import vocab as V
from grimdarkoracle.rules.registry import text_sha1

SYN = testpaths.SYNTHETIC_DIR
book = ab.load_book(testpaths.book_path(make_synthetic.BOOK_UID, SYN))
core = ab.load_core_rules(testpaths.rules_path(root=SYN))
AP, BLAST = make_synthetic.CORE["AP"], make_synthetic.CORE["Blast"]
SCOUT = make_synthetic.CORE["Scout"]

# --- the shipped semantics -------------------------------------------------------
shipped = registry.load_semantics()
assert registry.validate(shipped) == []
names = {e["name"] for e in shipped["rules"].values()}
assert set(make_synthetic.CORE) <= names, set(make_synthetic.CORE) - names
for rid, name in ((rid, e["name"]) for rid, e in shipped["rules"].items()
                  if e["name"] in make_synthetic.CORE):
    assert make_synthetic.CORE[name] == rid, name     # keyed by real ids

# --- validator ---------------------------------------------------------------------
assert text_sha1(" a\n b ") == text_sha1("a b")
assert registry.validate({"format": "x"}) == [f"format must be {V.FORMAT!r}"]
bad = {"format": V.FORMAT, "rules": {
    "r1": {"name": "A", "impl": "native:nope", "text_sha1": "0" * 40},
    "r2": {"name": "B", "impl": "composed", "text_sha1": "short",
           "effects": [{"primitive": "zap", "value": 1},
                       {"primitive": "hit_mod", "value": "two"},
                       {"primitive": "ignore_cover", "value": 1},
                       {"primitive": "hit_mod", "value": 1, "side": "x"},
                       {"primitive": "hit_mod", "value": 1,
                        "conditions": {"phase": 1}}],
           "conditions": {"attack": "psychic", "range_over": "9"}},
    "r3": {"name": "C", "impl": "composed", "text_sha1": "0" * 40},
    "r4": {"name": "D", "impl": "composed", "text_sha1": "0" * 40,
           "effects": [{"primitive": "grant_rule", "value": {"rule": "zz"}},
                       {"primitive": "grant_rule", "value": "r1"}],
           "conditions": {"has_rule": ""}}}}
errors = " | ".join(registry.validate(bad))
for needle in ("unknown handler", "text_sha1", "unknown primitive 'zap'",
               "integer or 'X'", "boolean expected", "bad side",
               "unknown condition 'phase'", "one of ('shooting', 'melee', 'spell')",
               "composed without effects", "granted rule 'zz' has no entry",
               "{'rule': id} expected", "rule id expected"):
    assert needle in errors, needle

# --- registry on the synthetic book (fixture hashed on synthetic text) -----------
marks = book.rules["synMarksman01"]
fixture = {"format": V.FORMAT, "rules": {
    AP: {"name": "AP", "impl": "composed", "text_sha1":
         text_sha1(core[AP].description),
         "effects": [{"primitive": "ap_mod", "value": "X"}]},
    "synMarksman01": {"name": "Marksman", "impl": "composed",
                      "text_sha1": text_sha1(marks.description),
                      # the faction alias's own text
                      "alias_sha1": {"synSharpshot1": text_sha1(
                          book.rules["synSharpshot1"].description)},
                      "effects": [{"primitive": "hit_mod", "value": 1}],
                      "conditions": {"attack": "shooting", "range_over": 9}},
    BLAST: {"name": "Blast", "impl": "native:blast",
            "text_sha1": "0" * 40},                      # outdated text
    # An aura-like rule granting a rule no unit carries directly.
    "synSplit00001": {"name": "Split", "impl": "composed",
                      "text_sha1": text_sha1(book.rules["synSplit00001"]
                                             .description),
                      "effects": [{"primitive": "grant_rule", "scope": "unit",
                                   "value": {"rule": SCOUT}}]},
    SCOUT: {"name": "Scout", "impl": "no_combat_effect",
            "text_sha1": text_sha1(core[SCOUT].description)},
}}
assert registry.validate(fixture) == []
reg = registry.RuleRegistry(fixture, core, [book])

sem = reg.lookup("synSharpshot1")                        # alias
assert sem.rule_id == "synMarksman01" and sem.effects[0].value == 1
assert dict(sem.conditions) == {"attack": "shooting", "range_over": 9}
assert reg.alias_chain("synSharpshot1") == ["synSharpshot1", "synMarksman01"]
assert reg.lookup("bookOwnApId", "AP").rule_id == AP     # core name fallback
assert reg.status("synSharpshot1") == "ok"
assert reg.status(BLAST) == "changed"
assert reg.status(make_synthetic.CORE["Tough"]) == "unmapped"
assert reg.status("nowhere") == "undefined"
assert reg.lookup(BLAST).handler == "blast"

# alias loops do not hang
loop = copy.deepcopy(book)
loop.rules["synMarksman01"] = ab.RuleDef("synMarksman01", "Marksman", "t",
                                         aliased_rule_id="synSharpshot1")
reg2 = registry.RuleRegistry({"format": V.FORMAT, "rules": {}}, core, [loop])
assert reg2.alias_chain("synSharpshot1") == ["synSharpshot1", "synMarksman01"]

# --- coverage ---------------------------------------------------------------------
used = coverage.used_rules(book)
assert used["synSharpshot1"][1] == {"Line Troopers", "Jet Riders"}
assert "Musician" in {n for n, _ in used.values()}      # bare-rule gain
cov = coverage.coverage(registry.RuleRegistry(fixture, core), [book])
assert set(cov.by_status["ok"]) == {AP, "synSharpshot1", "synSplit00001",
                                    SCOUT}
assert SCOUT not in used                               # only granted
assert cov.by_status["ok"][SCOUT] == ("Scout", {"Synthetic Legion": 1})
assert set(cov.by_status["changed"]) == {BLAST}
assert make_synthetic.CORE["Tough"] in cov.by_status["unmapped"]
assert not cov.clean
text = coverage.report(cov)
assert text.startswith("Rule coverage: ok 4, todo 0, changed 1")
assert "Sharpshot" not in text and "Sharpshot" in coverage.report(cov, True)

# --- real data: every core rule is mapped against the current text ---------------
if not testpaths.USING_SYNTHETIC:
    real_core = ab.load_core_rules(testpaths.rules_path())
    reg = registry.RuleRegistry(shipped, real_core)
    stats = {rid: reg.status(rid) for rid in real_core}
    assert set(stats.values()) == {"ok"}, stats
    print(f"rules: {len(stats)} core rules ok against the current text")
    # every rule DAO Union and Battle Brothers can field
    # (directly or through an aura) is mapped against its current text.
    dev = [ab.load_book(testpaths.book_path(u))
           for u in ("z8205ez2boggzs22", "78qp9l5alslt6yj8")]
    cov = coverage.coverage(registry.RuleRegistry(shipped, real_core), dev)
    assert cov.clean, coverage.report(cov)
    print(f"rules: DAO + BB coverage clean ({cov.count('ok')} rules)")
# --- every params key is one the code reads: a new key needs code ----
READ = {"actions", "shoot_when_moving", "chargeable", "choices", "odds",
        "on", "trigger", "hit_on", "ap", "cast_on", "pass_on", "ignore_on",
        "spell_ignore_on", "cast_mod", "attack", "far_only", "replaces", "state", "tokens"}
keys = {k for e in shipped["rules"].values() for k in e.get("params", {})}
assert keys <= READ, keys - READ
assert not any(e["impl"] == "native:" + h for e in shipped["rules"].values()
               for h in ("mend", "steadfast", "transport", "forced_morale"))
print("rules: OK")
