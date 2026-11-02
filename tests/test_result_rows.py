"""app.result_rows: table layout for shooting and melee, statistic
cycling, totals = chained losses, outcome lines, CSV export."""

from unitkit import CCW, R, W, REG, unit, ctx, resolved as ru
from grimdarkoracle.app import result_rows as RR
from grimdarkoracle.app.analyzer_core import Options, Side, analyse

assert RR.next_stat("mean") == "median" and RR.next_stat("hi") == "mean"
assert RR.next_stat("bogus") == "mean"
assert RR.heading("wounds", "median") == "Wounds med"
assert RR.heading("count", "median") == "xN"             # not a statistic

# --- shooting: weapon row, skipped row, TOTAL -----------------------------------
a = analyse(REG, Side(ru(unit(5), 100, "Shooters")),
            Side(ru(unit(5), 100, "Targets")), Options(exact=True))
rows = RR.table(a)
assert [r.kind for r in rows] == ["weapon", "skipped", "total"]
w, s, t = rows
assert all(len(r.cells) == len(RR.KEYS) for r in rows)
col = dict(zip(RR.KEYS, w.cells))
assert (col["count"], col["attacks"], col["hits"], col["wounds"]) == \
    ("5", "5", "2.50", "1.25")
assert col["destroyed"] == "0.1" and col["per100"] == ""
assert s.name == "Hand Weapon  (melee weapon)" and s.cells == ("5",) + ("",) * 6
tc = dict(zip(RR.KEYS, t.cells))
assert t.name == "TOTAL (100 pts) -> Targets"
assert tc["hits"] == "" and tc["wounds"] == "1.25" and tc["per100"] == "1.25"
# Median of Binomial(5, 1/4) is 1; p75 is 2.
med = dict(zip(RR.KEYS, RR.weapon_row(a.rows[0], {"wounds": "median",
                                                  "killed": "hi"}).cells))
assert med["wounds"] == "1" and med["killed"] == "2"

lines = dict(RR.outcome_lines(a))
assert lines["Targets takes a Morale Test"] == "10.3 %"   # 105/1024
assert lines["Points removed"] == "25.0" and "Charger wins" not in lines

csv = RR.to_csv(a, {"wounds": "median"})
head = csv.splitlines()[0]
assert head.startswith("Weapon,xN") and "Wounds med" in head
assert "TOTAL (100 pts) -> Targets" in csv and "Points removed,25.0" in csv
q = RR.to_csv(analyse(REG, Side(ru(unit(5), 100, "A")),
                      Side(ru(unit(5), 100, 'T, "x"')), Options()))
assert '\n"TOTAL (100 pts) -> T, ""x""",' in q            # quoted cell
assert "\nPoints removed per 100 pts," in q              # no comma: plain

# --- melee: both sides, phase labels, flags --------------------------------------
spear = W("Spear", 0, 1, R("Counter"))
m = analyse(REG, Side(ru(unit(2, (CCW,), rules=[R("Impact", 1)]), 60, "C")),
            Side(ru(unit(3, (spear, CCW)), 45, "D")),
            Options(ctx=ctx(attack="melee", action="charge")))
names = [(r.kind, r.name) for r in RR.table(m)]
assert names == [("weapon", "Impact"), ("weapon", "Hand Weapon"),
                 ("total", "TOTAL (60 pts) -> D"),
                 ("weapon", "Counter: Spear"),
                 ("weapon", "Strike back: Hand Weapon"),
                 ("total", "TOTAL (45 pts) -> C")]
tot = dict(zip(RR.KEYS, RR.table(m)[2].cells))
assert tot["count"] == "2"                               # Impact dice excluded
lines = [k for k, _v in RR.outcome_lines(m)]
assert lines[:3] == ["Charger wins", "Charger loses", "Tie (nobody tests)"]
assert "C Routs" in lines and "Net points (removed - lost)" in lines
td = W("Sniper", 24, 1, R("Takedown"), R("Limited"))
x = analyse(REG, Side(ru(unit(1, (td,)))), Side(ru(unit(3))), Options())
assert RR.table(x)[0].name == "Sniper  [Takedown, Limited]"
# Sources and distribution series behind the rows.
src = [x for _r, x in RR.entries(m)]
assert src[2] == ("total", "att") and src[-1] == ("total", "def")
sr = RR.series(m, src[1])
assert [x["key"] for x in sr] == ["wounds", "killed", "hits"]
assert sr[1]["threshold"] == 3 and sr[0]["pmf"] == [float(p)
                                                     for p in m.rows[1].wounds]
assert [x["key"] for x in RR.series(m, src[-1])] == ["wounds", "killed"]
assert RR.series(m, src[-1])[1]["threshold"] == 2       # the charger's size
assert RR.series(a, RR.entries(a)[1][1]) == []          # skipped weapon
print("result_rows: OK")
