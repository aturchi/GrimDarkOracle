"""Probability mass functions on the non-negative integers.

A PMF is a list of probabilities indexed by value: ``p[3]`` is P(X == 3).
Primitives ported from W40kDiviner's attack_math (delta, convolve, mix,
transform, binomial_thin) plus power, compound and moments.

Every function is generic in the number type: accumulators start from the
integer 0, so PMFs of ``fractions.Fraction`` stay exact (the tests use this
for closed-form equality) and PMFs of floats stay floats. Inputs are never
modified. Trailing zeros are allowed and harmless.
"""
from math import comb


def delta(v: int = 0) -> list:
    """Point mass at v (delta(0) is the identity of convolve)."""
    if v < 0:
        raise ValueError(f"negative value {v}")
    out = [0] * (v + 1)
    out[v] = 1
    return out


def bernoulli(p_one) -> list:
    """X = 1 with probability p_one, else 0."""
    return [1 - p_one, p_one]


def binomial(n: int, p) -> list:
    """Number of successes in n independent trials of probability p."""
    return [comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(n + 1)]


def total(p: list):
    """Total mass (1 for a probability law)."""
    return sum(p)


def mean(p: list):
    return sum(i * x for i, x in enumerate(p))


def variance(p: list):
    m = mean(p)
    return sum((i - m) ** 2 * x for i, x in enumerate(p))


def trim(p: list) -> list:
    """Copy without trailing exact zeros (at least one element kept)."""
    n = len(p)
    while n > 1 and not p[n - 1]:
        n -= 1
    return list(p[:n])


def add(a: list, b: list) -> list:
    """Term-by-term sum of two SUB-probability laws (disjoint parts of
    one law), not a mixture."""
    out = [0] * max(len(a), len(b))
    for src in (a, b):
        for i, x in enumerate(src):
            out[i] += x
    return out


def mix(pairs) -> list:
    """Weighted mixture: pairs = [(weight, pmf), ...]."""
    pairs = list(pairs)
    out = [0] * max(len(p) for _w, p in pairs)
    for w, p in pairs:
        for i, x in enumerate(p):
            out[i] += w * x
    return out


def convolve(a: list, b: list) -> list:
    """Law of X + Y for independent X ~ a, Y ~ b."""
    out = [0] * (len(a) + len(b) - 1)
    for i, pa in enumerate(a):
        if pa:
            for j, pb in enumerate(b):
                if pb:
                    out[i + j] += pa * pb
    return out


def power(p: list, n: int) -> list:
    """Law of the sum of n independent copies of X ~ p (n >= 0)."""
    if n < 0:
        raise ValueError(f"negative power {n}")
    out, base = delta(0), trim(p)
    while n:
        if n & 1:
            out = convolve(out, base)
        n >>= 1
        if n:
            base = convolve(base, base)
    return out


def compound(count: list, size: list) -> list:
    """Law of S = Y_1 + ... + Y_N with N ~ count and Y_i ~ size, all
    independent (random sum)."""
    count, size = trim(count), trim(size)
    if size[-1] == 1 and not any(size[:-1]):    # point mass: rescale
        k = len(size) - 1
        return transform(count, lambda n: n * k)
    out, cur = [0], delta(0)
    for k, pk in enumerate(count):
        if pk:
            out = add(out, [pk * x for x in cur])
        if k < len(count) - 1:
            cur = convolve(cur, size)
    return out


def binomial_thin(p: list, keep) -> list:
    """Law of Binomial(X, keep) for X ~ p: each unit kept independently."""
    return compound(p, bernoulli(keep))


def transform(p: list, fn) -> list:
    """Law of fn(X) for an integer-valued, non-negative fn."""
    vals: dict = {}
    for i, x in enumerate(p):
        if x:
            v = fn(i)
            vals[v] = vals.get(v, 0) + x
    if not vals:
        return [0]
    out = [0] * (max(vals) + 1)
    for v, x in vals.items():
        out[v] = x
    return out
