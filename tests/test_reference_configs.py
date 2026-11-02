"""On real data: reference configurations vs Army Forge.

Needs --real_data (OPR books are not in the repository); on synthetic data
it only checks that the reference table is well formed.
"""
import copy

import testpaths
import reference_configs as rc
from grimdarkoracle.data import army_list as al
from grimdarkoracle.data import links

ids = [r[0] for r in rc.REFS]
assert len(ids) == len(set(ids)) >= 10
for ref in rc.REFS:
    assert len(ref) == 7 and ref[3], ref[0]

if testpaths.USING_SYNTHETIC:
    print("reference configs: real data not selected, table checked only")
else:
    pending = []
    for ref in rc.REFS:
        rid, _, unit, _, computed, af_points, _ = ref
        _, _, ru = rc.run(ref)
        assert not ru.issues, (rid, ru.issues)
        assert ru.points == computed, (rid, ru.points, computed)
        # Label fingerprints re-link to the same uids after a uid change.
        book, unit, _ = rc.run(ref)
        choices = rc.build_choices(book, unit, ref[3])
        refs = [al.make_ref(book, unit, c) for c in choices]
        lu = al.ListUnit("k", book.uid, "stale-id", unit.name,
                         choices=copy.deepcopy(refs))
        for r in lu.choices:
            r.package, r.section, r.option = "x", "y", "z"
        lr = links.link_unit(book, lu)
        assert not lr.invalid, (rid, lr.invalid)
        assert [r.choice() for r in lr.choices] == choices, rid
        if af_points is None:
            pending.append(rid)
        else:
            assert ru.points == af_points, (rid, unit, ru.points, af_points)
    # The original R8 (2 rifles, 2 Plasma-Mods + 1 Flamer-Mod) is refused
    # by Army Forge: one attachment per rifle.
    r8 = next(r for r in rc.REFS if r[0] == "R8")
    spec = list(r8[3]) + [("Any model may take any Burst Battle Rifle "
                           "attachment", 1, "Flamer-Mod", 1)]
    book, unit, _ = rc.run(r8)
    from grimdarkoracle.data.resolve import resolve
    ru = resolve(book, unit.id, rc.build_choices(book, unit, spec))
    assert any("exceeds" in i for i in ru.issues), ru.issues
    print(f"reference configs: {len(rc.REFS)} resolved, "
          f"{len(rc.REFS) - len(pending)} confirmed by Army Forge"
          + (f", pending {pending}" if pending else ""))
