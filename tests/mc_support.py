"""Monte Carlo cross-validation helpers for the parity tests.

The exact engine (kill_chain) gives a full law; the dice engine
(dice_resolve) gives samples. They are compared the way the maths says,
not with a tolerance picked by eye (ported from W40kDiviner):

- MEAN: the sample mean of n draws has standard error sqrt(Var / n), with
  Var taken from the EXACT law; the check fails beyond SIGMA errors;
- DISTRIBUTION: at every support point the empirical CDF is a binomial
  proportion with standard error sqrt(F (1 - F) / n); the same bound is
  applied point by point, corrected for the number of points (Bonferroni)
  so that many points do not fire on noise.

SIGMA is the single tolerance knob; TRIALS trades runtime for resolution
(the detectable difference shrinks as 1 / sqrt(TRIALS)); the seed is
fixed so the suite never flickers.
"""
import math
import random
from collections import Counter
from statistics import NormalDist

import dice_resolve
from grimdarkoracle.engine import kill_chain

SIGMA = 4.0
TRIALS = 6000
SEED = 20261031


def moments(pmf):
    mean = sum(i * p for i, p in enumerate(pmf))
    second = sum(i * i * p for i, p in enumerate(pmf))
    return mean, max(0.0, second - mean * mean)


def mean_deviation(pmf, samples):
    """(z, exact mean, sample mean)."""
    n = len(samples)
    exact, var = moments(pmf)
    got = sum(samples) / n
    se = math.sqrt(var / n)
    if se <= 0.0:
        return (0.0 if abs(got - exact) < 1e-12 else math.inf), exact, got
    return abs(got - exact) / se, exact, got


def family_limit(sigma, comparisons: int) -> float:
    """SIGMA corrected for 'comparisons' simultaneous checks."""
    comparisons = max(1, int(comparisons))
    if comparisons == 1:
        return sigma
    p_each = max(2.0 * (1.0 - NormalDist().cdf(sigma)) / comparisons, 1e-15)
    return NormalDist().inv_cdf(1.0 - p_each / 2.0)


def cdf_deviation(pmf, samples):
    """(worst z, at value, points compared) between the CDFs."""
    n, counts = len(samples), Counter(samples)
    top = max(len(pmf) - 1, max(samples))
    ce = co = 0.0
    worst, at = 0.0, 0
    for v in range(top + 1):
        ce += pmf[v] if v < len(pmf) else 0.0
        co += counts.get(v, 0) / n
        se = math.sqrt(max(ce * (1.0 - ce), 1.0 / n) / n)   # floored tails
        z = abs(co - ce) / se
        if z > worst:
            worst, at = z, v
    return worst, at, top + 1


def parity(name, pmf, samples, sigma=SIGMA):
    """(ok, message): mean AND distribution within 'sigma'."""
    zm, exact, got = mean_deviation(pmf, samples)
    zc, at, points = cdf_deviation(pmf, samples)
    limit = family_limit(sigma, points)
    ok = zm <= sigma and zc <= limit
    msg = (f"{name:30s} exact={exact:7.4f} mc={got:7.4f} "
           f"z(mean)={zm:4.2f} z(cdf)={zc:4.2f}/{limit:.1f}@{at}")
    return ok, msg + ("" if ok else "   <== PARITY BROKEN")


def check(name, seq, trials=TRIALS, seed=SEED, start=None):
    """Exact vs dice on models killed AND wounds allocated."""
    res = kill_chain.resolve(seq, start)
    rng = random.Random(seed)
    alloc = seq.alloc
    s0 = alloc.fresh() if start is None else start
    kills, wounds = [], []
    for _ in range(trials):
        s, _log = dice_resolve.resolve(seq, s0, rng)
        kills.append(alloc.killed(s) - alloc.killed(s0))
        wounds.append(alloc.taken(s) - alloc.taken(s0))
    out = [parity(name + " killed", res.killed(), kills),
           parity(name + " wounds", res.wounds(), wounds)]
    return all(ok for ok, _ in out), [m for _, m in out]


def check_melee(name, setup, trials=TRIALS, seed=SEED, start=None):
    """Exact vs dice for a melee exchange: wounds of each side and their
    difference (what the melee result compares)."""
    from grimdarkoracle.engine import melee
    res = melee.resolve(setup, start)
    rng = random.Random(seed)
    aa, da = setup.a_alloc, setup.d_alloc
    a0, d0 = res.start
    wa, wd, diff = [], [], []
    for _ in range(trials):
        a, d, _log = dice_resolve.resolve_melee(setup, start, rng)
        x, y = aa.taken(a) - aa.taken(a0), da.taken(d) - da.taken(d0)
        wa.append(x)
        wd.append(y)
        diff.append(y - x)
    exact_diff: dict = {}
    for (a, d), p in res.dist.items():
        v = (da.taken(d) - da.taken(d0)) - (aa.taken(a) - aa.taken(a0))
        exact_diff[v] = exact_diff.get(v, 0) + p
    off = -min(min(exact_diff), min(diff))
    pmf = [exact_diff.get(v - off, 0) for v in range(max(exact_diff) + off + 1)]
    out = [parity(name + " charger wounds", res.attacker().wounds(), wa),
           parity(name + " target wounds", res.defender().wounds(), wd),
           parity(name + " difference", pmf, [v + off for v in diff])]
    return all(ok for ok, _ in out), [m for _, m in out]
