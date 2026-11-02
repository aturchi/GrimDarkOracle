"""Mixture of analyzer_core.Analysis results by probability: the exact
result of an attack whose effects depend on a die rolled before it
(Unpredictable). Every law and probability is the
weighted sum of the outcomes' ones; the audit keeps the parts of every
outcome; the warnings are merged. No tkinter.
"""
from dataclasses import fields, is_dataclass, replace

_KEEP = ("opts", "attacker", "target", "kind", "skipped")
_LAWS = ("hits", "wounds", "killed", "alive")


def _law(laws, weights) -> list:
    n = max(len(x) for x in laws)
    return [sum(w * (x[i] if i < len(x) else 0)
                for x, w in zip(laws, weights)) for i in range(n)]


def _value(vals, weights, name=""):
    v0 = vals[0]
    if all(v == v0 for v in vals[1:]):
        return v0
    if name in _LAWS or isinstance(v0, list):
        return _law(vals, weights)
    if isinstance(v0, bool) or v0 is None:
        return v0
    if isinstance(v0, (int, float)) or hasattr(v0, "denominator"):
        return sum(w * v for v, w in zip(vals, weights))
    if is_dataclass(v0):
        return replace(v0, **{f.name: _value([getattr(v, f.name)
                                              for v in vals], weights, f.name)
                              for f in fields(v0)})
    return v0


def _row(rows, weights):
    audit = tuple(dict.fromkeys(p for r in rows for p in r.audit))
    return replace(_value(rows, weights), audit=audit)


def mix(results, weights, note: str = ""):
    """One Analysis from 'results' (same attack, different dice) and their
    probabilities 'weights' (summing to 1)."""
    a0 = results[0]
    if len(results) == 1:
        return a0
    names = [tuple(r.name for r in a.rows) for a in results]
    if any(n != names[0] for n in names[1:]):
        raise ValueError("outcomes with different weapon rows")
    rows = tuple(_row([a.rows[i] for a in results], weights)
                 for i in range(len(a0.rows)))
    out = {f.name: (getattr(a0, f.name) if f.name in _KEEP else
                    _value([getattr(a, f.name) for a in results], weights,
                           f.name))
           for f in fields(a0) if f.name not in ("rows", "warnings")}
    warnings = tuple(dict.fromkeys(
        ((note,) if note else ()) + tuple(w for a in results
                                          for w in a.warnings)))
    return replace(a0, rows=rows, warnings=warnings, **out)
