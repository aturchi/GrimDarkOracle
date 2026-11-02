"""app.comparison (GF rewrite): pins from analyses, context
signature, matrix with deltas, CSV, overlay series."""
from dataclasses import replace

from unitkit import REG, RIFLE, unit, ctx, resolved as ru
from grimdarkoracle.app import comparison as C
from grimdarkoracle.app.analyzer_core import Options, Side, analyse

att, tgt = Side(ru(unit(5), 100, "A")), Side(ru(unit(5), 100, "T"))
base = analyse(REG, att, tgt, Options())
cover = analyse(REG, att, tgt, Options(ctx=ctx(cover="terrain")))
off = analyse(REG, replace(att, off=frozenset({RIFLE}), fatigued=True), tgt,
              Options())
mel = analyse(REG, att, tgt, Options(ctx=ctx(attack="melee", action="charge"),
                                     tie="attacker", strike_back=False))

assert C.context_signature(base) == 'shooting, 12", hold'
assert C.context_signature(cover) == 'shooting, 12", hold, cover (terrain)'
assert C.context_signature(off) == \
    'shooting, 12", hold, att fatigued, att 1 weapon(s) off'
assert C.context_signature(mel) == "melee, no strike back, tie: attacker"
wounded = analyse(REG, att, replace(tgt, wounds=(1, 0, 0, 0, 0)), Options())
assert C.context_signature(wounded).endswith("def wounded")

pins = [C.make_pin("base", base), C.make_pin("cover", cover),
        C.make_pin("melee", mel, context="custom")]
assert pins[0]["points"] == 100 and pins[0]["target"] == "T"
assert pins[2]["context"] == "custom"
assert abs(pins[0]["values"]["wounds"] - 1.25) < 1e-12
assert abs(sum(pins[0]["pmfs"]["killed"]) - 1) < 1e-12

rows = dict(C.matrix(pins))
assert rows["Wounds \u03bc"][0] == "1.25"
w1 = 5 / 2 * 1 / 3                                      # cover: block on 3+
assert rows["Wounds \u03bc"][1] == f"{w1:.2f}  ({w1 - 1.25:+.2f})"
assert rows["P(charger wins) %"][0] == ""               # melee-only metric
assert "P(charger wins) %" not in dict(C.matrix(pins[:2]))
same = dict(C.matrix([pins[0], pins[0]]))
assert same["Wounds \u03bc"][1] == "1.25  (=)"
assert dict(C.matrix(pins, deltas=False))["Wounds \u03bc"][1] == f"{w1:.2f}"

ctx_rows = dict(C.context_rows(pins))
assert ctx_rows["vs first"] == ["-", "DIFFERENT", "DIFFERENT"]
assert ctx_rows["Points"] == ["100"] * 3

csv = C.to_csv(pins).splitlines()
assert csv[0] == "Metric,base,cover,melee"
assert csv[1].startswith("Target,T,T,T") and csv[2].startswith("Context,")
assert any(line.startswith("Wounds \u03bc,1.25,") for line in csv)
assert "  (" not in "\n".join(csv)                       # no deltas in CSV
assert not any(line.startswith("vs first") for line in csv)

ov = C.overlay_series(pins, "killed")
assert [s["name"] for s in ov] == ["base", "cover", "melee"]
assert ov[0]["pmf"] == pins[0]["pmfs"]["killed"]
assert C.summary(pins[:1]).startswith("base: wounds 1.25, killed 1.25")
print("comparison: OK")
