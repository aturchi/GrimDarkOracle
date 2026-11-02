"""app.audit and app.unit_sheet: the audit lines read the specs the
engine used (cover, Rending, Blast, Takedown, Deadly, Shred, Regeneration,
Fatigue, spells, Impact); the unit sheet (models, weapons, rule texts and
statuses, Hero, spells) and its text / HTML renderers. Real DAO / BB
sheets and audits with --real_data."""
from unitkit import R, REG, W, CCW, cm, unit, ctx, resolved
import testpaths
from grimdarkoracle.app import audit as AU
from grimdarkoracle.app import unit_sheet as US
from grimdarkoracle.app.analyzer_core import Options, Side, analyse
from grimdarkoracle.data.resolve import ResolvedUnit

# --- audit ----------------------------------------------------------------------------
rifle = W("Rifle", 24, 1)
a = analyse(REG, Side(resolved(unit(2, (rifle,)))),
            Side(resolved(unit(5))), Options(ctx=ctx(cover="terrain")))
t = AU.row_text(a.rows[0])
assert t.startswith("Rifle  (2 x, 2 attacks, phase shoot)")
assert "hits on 4+ (50.0%)" in t
assert "Defense 4+, modifier +1 (cover included) -> blocks on 3+ (66.7%)" in t
assert "Sources" not in t                       # no modifier applied
gun = W("Gun", 24, 1, R("AP", 1), R("Rending"), R("Blast", 3), R("Deadly", 2),
        R("Bane"))
b = analyse(REG, Side(resolved(unit(1, (gun,), rules=[R("Good Shot")]))),
            Side(resolved(unit(2, rules=[R("Regeneration")]))), Options())
t = AU.row_text(b.rows[0])
for needle in ("modifier +1 -> hits on 3+ (66.7%); on a 6: AP +4",
               "Blast   x2 (Blast(3), 2 model(s) in the target)",
               "AP 1 -> blocks on 5+", "hits from a 6: Defense 4+, AP 5",
               "a 6 is re-rolled", "Deadly  x2", "Regen   ignored by this "
               "weapon", "Good Shot: hit_mod +1"):
    assert needle in t, (needle, t)
sh = analyse(REG, Side(resolved(unit(1, (W("Saw", 0, 2, R("Shred")),))),
                       fatigued=True),
             Side(resolved(unit(3, rules=[R("Regeneration")]))),
             Options(ctx=ctx(attack="melee", action="charge")))
t = AU.row_text(sh.rows[0])
assert "Fatigued: hits only on an unmodified 6" in t and "Shred   +1" in t
assert "Regen   each wound ignored on 5+" in t
rel = analyse(REG, Side(resolved(unit(1, (W("Flamer", 12, 1, R("Reliable")),),
                                      rules=[R("Good Shot")]))),
              Side(resolved(unit(2, d=2))), Options(ctx=ctx(cover="terrain")))
t = AU.row_text(rel.rows[0])
assert "hits on 2+ (83.3%)" in t and "blocks on 2+ (83.3%)" in t   # 1 fails
td = analyse(REG, Side(resolved(unit(1, (W("Sniper", 24, 1, R("Takedown")),)))),
             Side(resolved(unit(3))), Options())
assert "Target  Takedown on model #1" in AU.row_text(td.rows[0])   # removed last
imp = analyse(REG, Side(resolved(unit(2, (CCW,), rules=[R("Impact", 2)]))),
              Side(resolved(unit(3, (CCW,), rules=[R("Brace", 1)]))),
              Options(ctx=ctx(attack="melee", action="charge")))
t = AU.row_text(imp.rows[0])
assert "Impact: 3 dice of the living models, Brace(1) removed" in t
from grimdarkoracle.app.spells import SpellPlan  # noqa: E402
sp = analyse(REG, Side(resolved(unit(1))), Side(resolved(unit(3))),
             Options(ctx=ctx(attack="spell"),
                     spell=SpellPlan("Zap", W("Zap", 12, 3), 1)))
assert "fixed hits: no roll" in AU.row_text(sp.rows[0])
full = AU.analysis_text(b)
assert full == AU.row_text(b.rows[0])
dead = analyse(REG, Side(resolved(unit(2, (rifle,)))),
               Side(resolved(unit(1, (CCW,)))), Options())
assert dead.rows[0].audit                       # the target is alive at start

# --- unit sheet ----------------------------------------------------------------------------
host = resolved(unit(3, (rifle, CCW), rules=[R("Fearless")], extra=(
    cm((rifle,), rules=[R("Fearless"), R("Tough", 3)]),)), 120, "Squad <A>")
hero = ResolvedUnit("bk", "h", "Captain", 3, 4, 60, 60,
                    (cm((W("Sword", 0, 3, R("AP", 1)), rifle),
                        rules=[R("Hero"), R("Tough", 3), R("Caster", 2)]).model,),
                    (), ("odd choice",))
s = US.build(REG, host, hero)
assert s.title == "Squad <A> + Captain  [5]  180 pts"
assert s.stats[0] == ("Unit: Squad <A>", "Quality 4+, Defense 4+, 4 model(s), "
                      "120 pts, Tough(3)")
assert s.stats[1][0] == "Joined Hero: Captain"
assert s.models == [(3, "Rifle, Hand Weapon"), (1, "Rifle"),
                    (1, "Hero: Sword, Rifle")]
assert ("Rifle", 5, '24"', 1, "") in s.weapons and \
    ("Sword", 1, "melee", 3, "AP(1)") in s.weapons
labels = [r[0] for r in s.rules]
assert labels.count("Fearless") == 1 and "AP(1)" in labels
assert all(st in ("ok", "changed", "unmapped", "undefined", "todo")
           for _l, st, _t in s.rules)
assert s.notes == ["Captain: odd choice"] and s.spells == []   # no book
txt = US.to_text(s)
assert "  3 x Rifle, Hand Weapon" in txt and "Notes\n  Captain: odd choice" in txt
html = US.to_html(s)
assert html.startswith("<!DOCTYPE html>") and html.rstrip().endswith("</html>")
assert "Squad &lt;A&gt;" in html and "Squad <A>" not in html
assert US.render(s, "x.HTML") == html and US.render(s, "x.txt") == txt

# Spells of the book for a Caster side (synthetic book, fixture semantics).
from grimdarkoracle.data import af_book as ab  # noqa: E402
from grimdarkoracle.rules import spells as S  # noqa: E402
book = ab.load_book(testpaths.book_path("synthetic00book01",
                                        testpaths.SYNTHETIC_DIR))
doc = {"format": S.FORMAT, "spells": {S.spell_key(book.spells[0]): {
    "name": "Bolt", "kind": "damage", "hits": 2, "range": 12,
    "rules": [["AP", 1]]}}}
sreg = S.SpellRegistry(doc, REG, [book])
s2 = US.build(REG, host, hero, book, sreg)
assert [(n, st) for n, _t, _e, st in s2.spells] == [("Bolt", "ok"),
                                                    ("Ward", "unmapped")]
assert ("Caster", "Caster(2)") in s2.stats
assert US.build(REG, host, None, book, sreg).spells == []      # no Caster
assert "[unmapped]" in US.to_text(s2) and "[unmapped]" in US.to_html(s2)

if not testpaths.USING_SYNTHETIC:
    from grimdarkoracle.app.library import Library
    from grimdarkoracle.data.resolve import resolve
    lib = Library.load(testpaths.DATA_DIR)
    n = 0
    for uid in ("z8205ez2boggzs22", "78qp9l5alslt6yj8"):
        rb = lib.books[uid]
        units = [resolve(rb, u) for u in rb.units]
        for ru in units:
            sheet = US.build(lib.reg, ru, None, rb, lib.sreg)
            assert all(st == "ok" for _l, st, _t in sheet.rules), sheet.rules
            assert US.to_html(sheet).count("<table>") >= 3
            r = analyse(lib.reg, Side(ru), Side(units[0]), Options())
            AU.analysis_text(r)
            n += 1
    print(f"audit_sheet: {n} real sheets and audits")
print("audit_sheet: OK")
