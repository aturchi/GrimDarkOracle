"""engine.gf_math: closed-form checks and an independent face-by-face
enumeration of one attack (exact Fractions)."""
from fractions import Fraction as F
from itertools import product

import testpaths                                          # noqa: F401
from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.specs import AttackSpec as A, TargetSpec as T
from grimdarkoracle.rules import registry

game = registry.load_semantics()["game"]
assert (G.AUTO_SUCCESS, G.AUTO_FAIL) == (game["quality_auto_success"],
                                         game["quality_auto_fail"])

# --- hit roll -----------------------------------------------------------------------
hp = lambda **kw: G.hit_probs(A(1, **kw), exact=True)
assert hp() == (F(1, 2), F(1, 3), F(1, 6))                 # Q4+
assert hp(quality=2) == (F(1, 6), F(2, 3), F(1, 6))        # Reliable
assert hp(hit_mod=3) == (F(1, 6), F(2, 3), F(1, 6))        # 1 always fails
assert hp(quality=6, hit_mod=-5) == (F(5, 6), 0, F(1, 6))  # 6 always hits
assert hp(quality=2, fatigued=True) == (F(5, 6), F(1, 6), 0)
assert hp(auto_hit=True, fatigued=True) == (0, 1, 0)
for bad in (dict(attacks=-1), dict(attacks=1, blast=0),
            dict(attacks=1, shred=-1)):
    try:
        A(**bad)
        raise AssertionError("ValueError expected")
    except ValueError:
        pass

# Surge + Blast(3) on 2 models: a 6 gives (1 six + 1 extra) x 2.
h = G.attack_hits(A(1, extra_hits_on_6=1, blast=3), models=2, exact=True)
assert h == {(0, 0): F(1, 2), (2, 0): F(1, 3), (2, 2): F(1, 6)}
assert G.blast_multiplier(A(1, blast=3), 0) == 1          # never below 1
wh = G.weapon_hits(A(3, extra_hits_on_6=1, blast=3), 5, exact=True)
assert P.mean(wh) == 3 * 3 * (F(1, 3) + 2 * F(1, 6))

# --- block roll ---------------------------------------------------------------------
bp = lambda d, ap=0, mod=0, rr=False: G.block_probs(T(d, mod), ap, rr, True)
assert bp(4) == (F(1, 2), F(1, 3), F(1, 6))
assert bp(4, ap=2) == (F(1, 6), F(2, 3), F(1, 6))          # 6 always blocks
assert bp(2, mod=1) == (F(5, 6), 0, F(1, 6))               # cover, 1 fails
assert bp(4, rr=True) == (F(15, 36), F(14, 36), F(7, 36))  # Bane
assert bp(6, ap=9, rr=True) == (F(1, 36), F(28, 36), F(7, 36))
assert G.effective_ap(A(1, ap=-1, ap_on_6=4), False) == 0  # Fortified floor
assert G.effective_ap(A(1, ap=-1, ap_on_6=4), True) == 3
assert G.hit_wounds(A(1, shred=2), T(4), False, True) == \
    [F(1, 2), F(1, 3), 0, F(1, 6)]

# --- event law: Deadly then Regeneration per wound -----------------------------------
assert G.event_wounds(A(1, deadly=3), T(4)) == [0, 0, 0, 1]
assert G.event_wounds(A(1, deadly=3), T(4, regeneration=True), True) == \
    P.binomial(3, F(2, 3))
assert G.event_wounds(A(1, deadly=3, ignores_regen=True),
                      T(4, regeneration=True)) == [0, 0, 0, 1]


# --- independent oracle: enumerate the dice of ONE attack ---------------------------
def oracle_attack(s: A, t: T, models: int) -> list:
    """Wound events of one attack by enumerating every face, written from
    the rule texts without gf_math helpers."""
    b = max(1, min(s.blast, models))
    out: dict = {}
    for f in range(1, 7):
        if s.auto_hit:
            hits = [False] * b
        elif f == 1 or (s.fatigued and f != 6):
            hits = []
        elif s.fatigued:
            hits = [False] * b
        elif f == 6:
            hits = ([True] + [False] * s.extra_hits_on_6) * b
        else:
            hits = [False] * b if f + s.hit_mod >= s.quality else []
        dice = 2 if s.reroll_defense_6 else 1
        w_face = F(1, 1 if s.auto_hit else 6) / 6 ** (dice * len(hits))
        counts: dict = {}
        for faces in product(range(1, 7), repeat=dice * len(hits)):
            wounds = 0
            for i, six in enumerate(hits):
                roll = faces[dice * i]
                if roll == 6 and s.reroll_defense_6:
                    roll = faces[dice * i + 1]
                ap = max(0, s.ap + (s.ap_on_6 if six else 0))
                if roll == 1:
                    wounds += 1 + s.shred
                elif roll != 6 and roll + t.defense_mod - ap < t.defense:
                    wounds += 1
            counts[wounds] = counts.get(wounds, 0) + 1
        for w, n in counts.items():
            out[w] = out.get(w, 0) + n * w_face
        if s.auto_hit:
            break
    return [out.get(i, 0) for i in range(max(out) + 1)]


cases = [
    (A(1), T(4), 1),
    (A(1, quality=3, hit_mod=-1, ap=1), T(5, 1), 3),
    (A(1, extra_hits_on_6=2, ap_on_6=4, ap=-1), T(3), 1),     # Rending+Fort.
    (A(1, blast=3, shred=1), T(4, -1), 2),
    (A(1, blast=3, shred=1, reroll_defense_6=True), T(2), 5),
    (A(1, extra_hits_on_6=1, ap_on_6=4, reroll_defense_6=True,
       shred=1), T(4), 1),
    (A(1, quality=2, fatigued=True, extra_hits_on_6=1, ap_on_6=4), T(4), 1),
    (A(1, auto_hit=True, blast=3, ap=1), T(4), 6),
]
for s, t, m in cases:
    got = P.trim(G.attack_wounds(s, t, m, exact=True))
    assert got == P.trim(oracle_attack(s, t, m)), (s, t, m)
    assert P.total(got) == 1

# --- whole weapon ---------------------------------------------------------------------
s, t = A(4, ap=1, blast=2, deadly=2), T(4, regeneration=True)
law = G.weapon_law(s, t, 3, exact=True)
per = G.attack_wounds(s, t, 3, exact=True)
assert law.events == P.power(per, 4) and P.total(law.gross) == 1
# Mean gross = attacks x E[hits] x P(fail) x X x P(not regenerated).
assert P.mean(law.gross) == 4 * (F(1, 2) * 2) * F(2, 3) * 2 * F(2, 3)
assert P.mean(law.hits) == 4 * F(1, 2) * 2
assert G.weapon_law(A(0), T(), 1).gross == [1]            # no attacks

# Floats agree with Fractions.
fl = G.weapon_law(s, t, 3)
assert all(abs(a - float(b)) < 1e-12 for a, b in zip(fl.gross, law.gross))
assert isinstance(fl.gross[1], float)
print("gf_math: OK")
