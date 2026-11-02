"""app.variants: one variant per option of a section, the other
choices kept, points per variant, invalid chains reported, comparison
pins. Synthetic book; real DAO / BB units with --real_data."""
from unitkit import REG, unit, resolved as ru
import testpaths
from grimdarkoracle.app import comparison as C
from grimdarkoracle.app import variants as V
from grimdarkoracle.app.analyzer_core import Options, Side, analyse
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.data.resolve import Choice, resolve

book = ab.load_book(testpaths.book_path("synthetic00book01")) \
    if testpaths.USING_SYNTHETIC else None
if book is not None:
    U = "uTroop1"
    chain = (Choice("PA", "sRepOne", "oRepOneA"), Choice("PA", "sChain",
                                                         "oChain"))
    vs = V.section_variants(book, U, chain, "PA", "sRepOne")
    assert [v.label for v in vs][0] == V.NONE_LABEL and len(vs) == 4
    # The other choices are kept; without the Sgt. Pistol the chained
    # choice is invalid and reported, not silently dropped.
    assert all(Choice("PA", "sChain", "oChain") in v.choices for v in vs)
    assert vs[1].unit.issues == () and vs[2].unit.issues != ()
    assert vs[0].unit.issues != ()
    for v in vs[1:]:
        sec = book.packages["PA"].sections
        opt = next(o for s in sec for o in s.options
                   if o.uid == v.choices[-1].option)
        assert v.label == opt.label
    # Count section: each option as many times as the section allows.
    vc = V.section_variants(book, U, (), "PA", "sRepAny", include_none=False)
    st = next(s for s in resolve(book, U).sections if s.uid == "sRepAny")
    assert all(v.choices[-1].count == st.caps.per_option for v in vc)
    assert all(v.label.startswith(f"{st.caps.per_option}x ") for v in vc)
    base = resolve(book, U).points
    for v in vc:
        opt = next(o for s in book.packages["PA"].sections
                   for o in s.options if o.uid == v.choices[-1].option)
        assert v.unit.points == base + opt.cost_for(U) * st.caps.per_option
    for sec in ("sChain", "nope"):
        try:
            V.section_variants(book, U, (), "PA", sec)
            raise AssertionError(f"{sec} accepted")
        except ValueError:
            pass
    # compare(): pins in variant order, analysed by the caller's function.
    tgt = Side(ru(unit(10), 100, "T"))
    pins = V.compare(vs[:2], lambda v: analyse(REG, Side(v.unit), tgt,
                                                Options()))
    assert [p["name"] for p in pins] == [v.label for v in vs[:2]]
    assert pins[1]["points"] == vs[1].unit.points
    assert C.matrix(pins)[0][0] == "Wounds \u03bc"
else:
    from grimdarkoracle.rules import registry
    from unitkit import SEM
    books = [ab.load_book(testpaths.book_path(u))
             for u in ("z8205ez2boggzs22", "78qp9l5alslt6yj8")]
    real = registry.RuleRegistry(SEM, ab.load_core_rules(testpaths.rules_path()),
                                 books)
    tgt = Side(resolve(books[1], next(iter(books[1].units))))
    n = 0
    for b in books:
        for uid in b.units:
            for st in resolve(b, uid).sections:
                if not st.enabled:
                    continue
                vs = V.section_variants(b, uid, (), st.package, st.uid)
                assert vs[0].unit.points == b.units[uid].cost
                pins = V.compare(vs, lambda v: analyse(real, Side(v.unit), tgt,
                                                       Options()))
                assert len(pins) == len(vs)
                n += len(vs)
    print(f"variants: {n} real variants analysed")
print("variants: OK")
