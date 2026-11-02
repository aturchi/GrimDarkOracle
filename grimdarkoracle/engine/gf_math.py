"""Exact per-weapon laws of Grimdark Future 3.6 shooting / melee dice.

One weapon (AttackSpec) against one target (TargetSpec) with 'models'
models alive at the start of the weapon (Blast uses them).

Sequence (core rules 3.6 + rule texts of /api/rules/common/2):

1. Hit: one Quality test per attack. Unmodified 6 always hits, 1 always
   fails, otherwise roll + hit_mod >= Q. Fatigued: hits on
   unmodified 6 only, and that hit is not "a 6" for special rules.
   A 6 gives one "six-hit" (AP + ap_on_6, Rending) plus extra_hits_on_6
   ordinary hits (Surge / Relentless / Furious add up; only the
   original hit counts as a 6). Spells: fixed hits, no roll.
   Predator (extra_attack_on): an unmodified result of
   extra_attack_on or more that hits rolls ONE new attack of the weapon,
   resolved like any attack (its 6s count for Surge, Rending...) but never
   triggering Predator again; not when Fatigued (no "6" then) or for fixed
   hits.
2. Blast(X): after the other rules every hit is multiplied by
   B = min(X, models), at least 1; copies keep the kind of the
   hit they copy. Takedown: models = 1.
3. Block: one Defense roll per hit. Unmodified 6 always blocks, 1 always
   fails, otherwise roll + defense_mod - AP >= D, with AP = max(0, ...)
   per hit kind. Bane / Smash: an unmodified 6 is re-rolled once and
   the re-roll stands; a re-rolled 1 triggers Shred. Obliterate
   (reroll_defense_on N): every SUCCESSFUL unmodified result of N or more
   is re-rolled the same way; with Bane the lower face applies.
4. Wounds: each failed block is a wound EVENT, Shred extras included as
   separate events. Deadly(X) multiplies each wound by X; Regeneration
   then rolls for each resulting wound, and each ward rule after it,
  so one event inflicts Binomial(X, P(no roll ignores it)) wounds.

Allocation (Tough, Deadly without carry-over, Heroes last) is kill_chain's
job: here the 'gross' law is the total wounds inflicted before allocation.

Probabilities are floats, or Fractions with exact=True (tests). Faces are
counted as integers and divided once, so both modes share the code.
"""
from dataclasses import dataclass
from fractions import Fraction

from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.specs import AttackSpec, TargetSpec

# GF 3.6 defaults; the specs carry the numbers of semantics.json 'game',
# these only serve callers without specs.
AUTO_SUCCESS, AUTO_FAIL = 6, 1
FACES = range(1, 7)


def _p(count: int, den: int, exact: bool):
    return Fraction(count, den) if exact else count / den


def passes(face: int, target: int, mod: int, auto=(AUTO_SUCCESS, AUTO_FAIL)
           ) -> bool:
    """'face + mod >= target', with the automatic success / failure faces
    auto = (success, fail): 6 / 1 in GF 3.6."""
    return face >= auto[0] or (face > auto[1] and face + mod >= target)


def success_faces(target: int, mod: int, auto=(AUTO_SUCCESS, AUTO_FAIL)
                  ) -> int:
    """Faces of one d6 that pass 'roll + mod >= target' (auto faces)."""
    return sum(1 for f in FACES if passes(f, target, mod, auto))


def auto_of(spec) -> tuple[int, int]:
    return spec.auto_success, spec.auto_fail


def blast_multiplier(spec: AttackSpec, models: int) -> int:
    """Hits multiplier: Blast(X) up to the models in the target (>= 1)."""
    return max(1, min(spec.blast, models))


# --- 1-2. hits -------------------------------------------------------------------

def hit_probs(spec: AttackSpec, exact: bool = False) -> tuple:
    """(P(miss), P(ordinary hit), P(six-hit)) of one attack, before Blast."""
    if spec.auto_hit and spec.auto_sixes:
        return _p(0, 6, exact), _p(5, 6, exact), _p(1, 6, exact)
    if spec.auto_hit:
        return _p(0, 6, exact), _p(6, 6, exact), _p(0, 6, exact)
    if spec.fatigued:
        f = 7 - spec.fatigue_on                         # unmodified faces
        return _p(6 - f, 6, exact), _p(f, 6, exact), _p(0, 6, exact)
    ok = success_faces(spec.quality, spec.hit_mod, auto_of(spec))  # with the 6
    return _p(6 - ok, 6, exact), _p(ok - 1, 6, exact), _p(1, 6, exact)


def _one_attack(spec: AttackSpec, models: int, exact: bool) -> dict:
    """{(ordinary hits, six-hits): p} of one attack, Predator left out."""
    miss, plain, six = hit_probs(spec, exact)
    b = blast_multiplier(spec, models)
    out: dict = {}
    for key, p in (((0, 0), miss), ((b, 0), plain),
                   ((b * spec.extra_hits_on_6, b), six)):
        if p:
            out[key] = out.get(key, 0) + p
    return out


def _predator_faces(spec: AttackSpec) -> int:
    """Faces of an ordinary (non-6) hit that roll a new attack."""
    return sum(1 for f in range(spec.extra_attack_on, 6)
               if passes(f, spec.quality, spec.hit_mod, auto_of(spec)))


def attack_hits(spec: AttackSpec, models: int, exact: bool = False) -> dict:
    """Joint law of one attack's hits after Blast, with the new attack a
    Predator result rolls: {(ordinary hits, six-hits): probability}."""
    base = _one_attack(spec, models, exact)
    if not spec.extra_attack_on or spec.auto_hit or spec.fatigued:
        return base
    b = blast_multiplier(spec, models)
    trig = _predator_faces(spec)
    plain_ok = success_faces(spec.quality, spec.hit_mod, auto_of(spec)) - 1
    parts = (((0, 0), _p(6 - plain_ok - 1, 6, exact), False),
             ((b, 0), _p(plain_ok - trig, 6, exact), False),
             ((b, 0), _p(trig, 6, exact), True),
             ((b * spec.extra_hits_on_6, b), _p(1, 6, exact), True))
    out: dict = {}
    for (a, s), p, more in parts:
        if not p:
            continue
        for (da, ds), q in (base.items() if more else (((0, 0), 1),)):
            k = (a + da, s + ds)
            out[k] = out.get(k, 0) + p * q
    return out


def weapon_hits(spec: AttackSpec, models: int, exact: bool = False) -> list:
    """Law of the weapon's total hits (all attacks, after Blast)."""
    per = [0]
    for (a, s), p in attack_hits(spec, models, exact).items():
        per = P.add(per, [0] * (a + s) + [p])
    return P.power(per, spec.attacks)


def weapon_hit_pairs(spec: AttackSpec, models: int,
                     exact: bool = False) -> dict:
    """Joint law of the weapon's (ordinary hits, six-hits) after Blast:
    {(ordinary, six): p} (Parry needs the kinds before the blocks)."""
    per = attack_hits(spec, models, exact)
    out: dict = {(0, 0): 1}
    for _ in range(spec.attacks):
        nxt: dict = {}
        for (a, s), p in out.items():
            for (da, ds), q in per.items():
                k = (a + da, s + ds)
                nxt[k] = nxt.get(k, 0) + p * q
        out = nxt
    return out


# --- 3. blocks -------------------------------------------------------------------

def effective_ap(spec: AttackSpec, six: bool) -> int:
    """AP of an ordinary hit or of a six-hit, floored at 0."""
    return max(0, spec.ap + (spec.ap_on_6 if six else 0))


def reroll_face(spec: AttackSpec) -> int:
    """Lowest unmodified Defense face re-rolled when it succeeds: 6 for
    Bane / Smash, reroll_defense_on (Obliterate), 0 for none."""
    faces = [f for f in (6 if spec.reroll_defense_6 else 0,
                         spec.reroll_defense_on) if f]
    return min(faces, default=0)


def block_probs(target: TargetSpec, ap: int, reroll=False,
                exact: bool = False) -> tuple:
    """(P(block), P(fail, not on 1), P(fail on unmodified 1)) of one hit;
    'reroll': the lowest face re-rolled when it succeeds (True = 6)."""
    # The faces passing, the 6 always among them and the 1 never (the specs
    # enforce 1 <= auto_fail < auto_success <= 6).
    mod, auto = target.defense_mod - ap, auto_of(target)
    n = success_faces(target.defense, mod, auto)
    on = 6 if reroll is True else int(reroll or 0)
    r = sum(1 for f in FACES if on and f >= on
            and passes(f, target.defense, mod, auto))
    if not r:
        return _p(n, 6, exact), _p(5 - n, 6, exact), _p(1, 6, exact)
    # The r re-rolled faces (1/6 each) are rolled again: the re-roll stands.
    block, fail_1 = 6 * (n - r) + r * n, 6 + r
    return (_p(block, 36, exact), _p(36 - block - fail_1, 36, exact),
            _p(fail_1, 36, exact))


def hit_wounds(spec: AttackSpec, target: TargetSpec, six: bool,
               exact: bool = False) -> list:
    """Law of the wound events from ONE hit (0, 1 or 1 + shred)."""
    if spec.no_block:                           # wound dice
        return [0, 1]
    block, fail, fail_1 = block_probs(target, effective_ap(spec, six),
                                      reroll_face(spec), exact)
    out = [block, fail] + [0] * spec.shred
    out[1 + spec.shred] += fail_1
    return out


# --- 4. wounds -------------------------------------------------------------------

def attack_wounds(spec: AttackSpec, target: TargetSpec, models: int,
                  exact: bool = False) -> list:
    """Law of the wound events from ONE attack."""
    laws = {False: hit_wounds(spec, target, False, exact),
            True: hit_wounds(spec, target, True, exact)}
    pairs = [(p, P.convolve(P.power(laws[False], a), P.power(laws[True], s)))
             for (a, s), p in attack_hits(spec, models, exact).items()]
    return P.mix(pairs)


def weapon_wounds(spec: AttackSpec, target: TargetSpec, models: int,
                  exact: bool = False) -> list:
    """Law of the weapon's wound events (before Deadly and Regeneration)."""
    return P.power(attack_wounds(spec, target, models, exact), spec.attacks)


def fixed_hits_events(spec: AttackSpec, target: TargetSpec, plain: int,
                      six: int, exact: bool = False) -> list:
    """Law of the wound events of exactly 'plain' ordinary hits and 'six'
    six-hits (hits already decided, e.g. after Parry)."""
    return P.convolve(P.power(hit_wounds(spec, target, False, exact), plain),
                      P.power(hit_wounds(spec, target, True, exact), six))


def regen_applies(spec: AttackSpec, target: TargetSpec) -> bool:
    return target.regeneration and not spec.ignores_regen


def wound_save_ons(spec: AttackSpec, target: TargetSpec) -> tuple:
    """Die results that ignore a wound, one per roll the target makes for
    each wound: Regeneration (unless ignored), then the wards."""
    regen = (target.regen_on,) if regen_applies(spec, target) else ()
    return regen + tuple(target.wards)


def wound_through(ons, exact: bool = False):
    """P(a wound survives one roll per threshold in 'ons')."""
    num, den = 1, 1
    for on in ons:
        num *= sum(1 for f in FACES if f < on)
        den *= 6
    return _p(num, den, exact)


def event_wounds(spec: AttackSpec, target: TargetSpec,
                 exact: bool = False) -> list:
    """Law of the wounds one wound event inflicts: Deadly(X) multiplies,
    then each wound is ignored on a Regeneration or ward success."""
    ons = wound_save_ons(spec, target)
    if not ons:
        return P.delta(spec.deadly)
    return P.binomial(spec.deadly, wound_through(ons, exact))


@dataclass(frozen=True)
class WeaponLaw:
    """Exact laws of one weapon against one target state."""
    hits: list          # total hits after Blast
    events: list        # wound events (failed blocks + Shred extras)
    event: list         # wounds inflicted by one event (Deadly, Regen)
    gross: list         # total wounds inflicted, before allocation


def weapon_law(spec: AttackSpec, target: TargetSpec, models: int,
               exact: bool = False) -> WeaponLaw:
    events = weapon_wounds(spec, target, models, exact)
    event = event_wounds(spec, target, exact)
    return WeaponLaw(weapon_hits(spec, models, exact), events, event,
                     P.compound(events, event))
