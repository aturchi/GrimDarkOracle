"""Scourge: "for each unmodified result of 1 to block hits, enemies count
as having taken 2 extra wounds when checking who won melee, or if shooting
wounds would trigger Morale Tests".

AttackSpec.scourge is the extra count per unmodified block 1 (2). The kill
chain gives the law of the target's state; here the same sequence gives the
JOINT law of (state, extra count), weapon by weapon: one hit is blocked,
fails on 2-5, or fails on an unmodified 1 (Shred included); Deadly,
Regeneration and wards act on the wound events as in kill_chain.
"""
from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine import kill_chain as K
from grimdarkoracle.engine import pmf as P


def hit_pairs(spec, target, six: bool, exact: bool) -> dict:
    """{(wound events, unmodified block 1s): p} of ONE hit."""
    if spec.no_block:
        return {(1, 0): 1}
    block, fail, fail_1 = G.block_probs(target, G.effective_ap(spec, six),
                                        G.reroll_face(spec), exact)
    return {(0, 0): block, (1, 0): fail, (1 + spec.shred, 1): fail_1}


def _times(law: dict, other: dict) -> dict:
    out: dict = {}
    for (e1, o1), p in law.items():
        for (e2, o2), q in other.items():
            k = (e1 + e2, o1 + o2)
            out[k] = out.get(k, 0) + p * q
    return out


def weapon_pairs(spec, target, models: int, exact: bool) -> dict:
    """{(wound events, block 1s): p} of one weapon (Blast included)."""
    out: dict = {}
    hits = G.weapon_hit_pairs(spec, models, exact)
    per = {six: hit_pairs(spec, target, six, exact) for six in (False, True)}
    for (plain, six), p in hits.items():
        law = {(0, 0): p}
        for _ in range(plain):
            law = _times(law, per[False])
        for _ in range(six):
            law = _times(law, per[True])
        for k, q in law.items():
            out[k] = out.get(k, 0) + q
    return out


def resolve_extra(seq, start, exact: bool = False, steps=None) -> dict:
    """{(target state, extra count): p} after the steps; the extra count is
    the sum of spec.scourge x unmodified block 1s (0 for other weapons)."""
    alloc = seq.alloc
    dist = {(start, 0): 1}
    for step in (seq.steps if steps is None else steps):
        out: dict = {}
        for (state, x), p in dist.items():
            if step.kind == "takedown":
                j = seq.takedown_target(state)
                part = None if j is None else seq.takedown_part(step, j)
                parts = [] if part is None else [(part[0], part[1], j)]
            else:
                parts = [(s, t, None) for s, t in seq.parts(step, state)]
            cur = {(state, x): p}
            for spec, target, j in parts:
                cur = _weapon(cur, alloc, spec, target, j, exact)
            for k, q in cur.items():
                K._add(out, k, q)
        dist = out
    return dist


def _weapon(dist, alloc, spec, target, model, exact) -> dict:
    out: dict = {}
    event = G.event_wounds(spec, target, exact)
    for (state, x), p in dist.items():
        if not alloc.alive(state) or (model is not None and
                                      alloc.left(state, model) <= 0):
            K._add(out, (state, x), p)
            continue
        n = 1 if model is not None else len(alloc.alive(state))
        for (ev, ones), q in weapon_pairs(spec, target, n, exact).items():
            if not q:
                continue
            tmp: dict = {}
            K.apply_events(tmp, state, p * q, alloc, P.delta(ev), event,
                           spec.deadly, model)
            for s, r in tmp.items():
                K._add(out, (s, x + spec.scourge * ones), r)
    return out
