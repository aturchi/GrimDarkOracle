"""engine.pmf: exact identities on Fraction PMFs, float behaviour."""
from fractions import Fraction as F
from itertools import product

import testpaths                                          # noqa: F401
from grimdarkoracle.engine import pmf as P

d6 = [0] + [F(1, 6)] * 6                                  # one die, 1..6

# --- basics -------------------------------------------------------------------------
assert P.delta(0) == [1] and P.delta(2) == [0, 0, 1]
assert P.bernoulli(F(1, 3)) == [F(2, 3), F(1, 3)]
assert P.total(d6) == 1 and P.mean(d6) == F(7, 2)
assert P.variance(d6) == F(35, 12)
assert P.trim([F(1), 0, 0]) == [1] and P.trim([0]) == [0]
assert P.add([F(1, 4)], [0, F(1, 2)]) == [F(1, 4), F(1, 2)]
assert P.mix([(F(1, 2), P.delta(0)), (F(1, 2), P.delta(2))]) == \
    [F(1, 2), 0, F(1, 2)]
for bad in (lambda: P.delta(-1), lambda: P.power(d6, -1)):
    try:
        bad()
        raise AssertionError("ValueError expected")
    except ValueError:
        pass

# --- convolution and powers against brute-force enumeration ----------------------
two = P.convolve(d6, d6)
brute = [0] * 13
for a, b in product(range(1, 7), repeat=2):
    brute[a + b] += F(1, 36)
assert two == brute and P.convolve(d6, P.delta(0)) == d6
assert P.power(d6, 0) == [1] and P.power(d6, 1) == d6
assert P.power(d6, 2) == brute
assert P.trim(P.power(d6, 5)) == P.trim(
    P.convolve(P.power(d6, 2), P.power(d6, 3)))
assert P.mean(P.power(d6, 7)) == 7 * F(7, 2)
assert P.variance(P.power(d6, 7)) == 7 * F(35, 12)

# --- binomial, compound, thinning --------------------------------------------------
b = P.binomial(4, F(1, 3))
assert P.total(b) == 1 and P.mean(b) == F(4, 3)
assert b == P.power(P.bernoulli(F(1, 3)), 4)
# Thinning Binomial(n, p) by q gives Binomial(n, p q).
assert P.trim(P.binomial_thin(P.binomial(5, F(1, 2)), F(2, 3))) == \
    P.trim(P.binomial(5, F(1, 3)))
# Random sum: E[S] = E[N] E[Y], Var[S] = E[N] Var[Y] + Var[N] E[Y]^2.
s = P.compound(d6, P.binomial(2, F(1, 2)))
assert P.total(s) == 1 and P.mean(s) == F(7, 2) * 1
assert P.variance(s) == F(7, 2) * F(1, 2) + F(35, 12) * 1
assert P.compound([F(1, 2), 0, F(1, 2)], P.delta(1)) == [F(1, 2), 0, F(1, 2)]
assert P.compound(d6, P.delta(0)) == [1]
assert P.compound(d6, P.delta(2)) == P.trim(P.mix(
    (pn, P.power(P.delta(2), n)) for n, pn in enumerate(d6)))  # fast path
assert P.compound([F(1, 2), F(1, 2)], [0, F(1, 2)]) == [F(1, 2), F(1, 4)]
# transform: parity of one die
assert P.transform(d6, lambda v: v % 2) == [F(1, 2), F(1, 2)]
assert P.transform([0], lambda v: v) == [0]

# --- floats stay floats, inputs untouched -------------------------------------------
f6 = [0.0] + [1 / 6] * 6
copy = list(f6)
x = P.power(f6, 10)
assert f6 == copy and isinstance(x[30], float)
assert abs(P.total(x) - 1) < 1e-12 and abs(P.mean(x) - 35) < 1e-9
print("pmf: OK")
