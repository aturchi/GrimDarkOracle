"""Best weapon order of one attacking unit.

The order can only move weapons WITHIN the classes the sequence keeps:
Takedown, then Deadly, then the others. The best order
maximises the expected number of models killed; ties: the probability to
destroy the unit, then the expected wounds. Every candidate is
scored with the exact kill chain (kill_chain laws, Parry included in
melee), floats.

Cost: the search is a depth-first walk over the orders that shares
every prefix (the law after the first weapons is computed once) and the
weapon laws (one cache). Two weapons of the "other" class COMMUTE when
both are plain: no Blast, no Deadly, against a target whose models are
all alike (same Defense, rules, items, Tough, no joined Hero): each one
then adds an independent number of wounds carried in the allocation
order, so only the slot of a plain weapon between the other weapons
matters and plain weapons keep their book order inside a slot (exact).
When the walk would exceed the budget, a greedy order improved by swaps
is returned instead, flagged as not exhaustive. A wall-clock limit is a
last safety net (the window must never freeze).

Problems are built by shooting(), melee() and the adapters of
app/order_advice; the search is search(problem).
"""
import time
from dataclasses import dataclass, field
from math import factorial

from grimdarkoracle.engine import kill_chain as K
from grimdarkoracle.engine import melee as ML
from grimdarkoracle.engine.sequence import KINDS

BUDGET = 1200                      # names applied (one walk node each)
TIME_LIMIT = 0.4                    # seconds, safety net
EPS = 1e-9


@dataclass(frozen=True)
class Score:
    killed: float = 0.0             # expected models killed
    destroyed: float = 0.0          # P(no model left)
    wounds: float = 0.0             # expected wounds allocated

    def key(self) -> tuple:
        return (self.killed, self.destroyed, self.wounds)

    def beats(self, other: "Score") -> bool:
        """Strictly better (Q2 order), beyond rounding."""
        for a, b in zip(self.key(), other.key()):
            if a > b + EPS:
                return True
            if a < b - EPS:
                return False
        return False


@dataclass(frozen=True)
class Suggestion:
    order: tuple[str, ...]          # best order found (every name)
    best: Score
    book: Score                     # book order (no weapon order)
    current: Score                  # the order asked about
    examined: int                   # complete orders scored
    total: int                      # distinct candidate orders
    exact: bool                     # every candidate examined

    @property
    def gain(self) -> float:
        """Expected models killed over the book order."""
        return self.best.killed - self.book.killed

    @property
    def improves(self) -> bool:
        return self.best.beats(self.book)

    def note(self) -> str:
        how = f"all {self.total} order(s)" if self.exact else \
            f"{self.examined} of {self.total} orders (greedy + swaps)"
        return (f"expected models killed {self.best.killed:.3f}, book "
                f"order {self.book.killed:.3f} ({self.gain:+.3f}); "
                f"searched {how}")


@dataclass
class Branch:
    """One attacking sequence against a law of target states: shooting
    has one; a melee phase one per set of living strikers."""
    seq: object                     # AttackSequence built WITHOUT an order
    steps: tuple                    # the phase's steps, in book order
    dist: dict                      # target state -> probability
    leaf: object = None             # (steps, state) -> dist, when the
    #                                 steps must be resolved together (Parry)


@dataclass
class Problem:
    branches: list
    start: tuple                    # target start state (killed from it)
    alloc: object                   # the target's Allocation
    rest: dict = field(default_factory=dict)   # states no order changes


# --- applying steps ----------------------------------------------------------


def _parts(dist, seq, step, laws) -> dict:
    out: dict = {}
    for state, p in dist.items():
        cur = {state: p}
        for spec, target in seq.parts(step, state):
            cur = K.apply_weapon(cur, seq.alloc, spec, target, laws)
        for s, q in cur.items():
            K._add(out, s, q)
    return out


def _apply(branch: Branch, dist, step, laws) -> dict:
    if step.kind == "takedown":
        return K.apply_takedown(dist, branch.seq, step, laws)
    return _parts(dist, branch.seq, step, laws)


def _ordered(steps, order) -> tuple:
    """The steps as AttackSequence sorts them with weapon_order 'order'."""
    rank = {n: k for k, n in enumerate(order)}
    return tuple(sorted(steps, key=lambda s: (
        KINDS.index(s.kind), rank.get(s.weapon.name, len(rank)),
        steps.index(s))))


def _score(problem: Problem, dists) -> Score:
    al = problem.alloc
    k0, w0 = al.killed(problem.start), al.taken(problem.start)
    k = d = w = 0.0
    for dist in list(dists) + [problem.rest]:
        for s, p in dist.items():
            k += p * (al.killed(s) - k0)
            w += p * (al.taken(s) - w0)
            d += p * (not al.alive(s))
    return Score(float(k), float(d), float(w))


def evaluate(problem: Problem, order, laws=None) -> Score:
    """Score of one complete order (weapon names)."""
    laws = laws or K._Laws(False)
    dists = []
    for b in problem.branches:
        steps = _ordered(b.steps, order)
        if b.leaf is not None:
            out: dict = {}
            for s, p in b.dist.items():
                for t, q in b.leaf(steps, s).items():
                    K._add(out, t, p * q)
            dists.append(out)
            continue
        dist = dict(b.dist)
        for st in steps:
            dist = _apply(b, dist, st, laws)
        dists.append(dist)
    return _score(problem, dists)


# --- the candidates ----------------------------------------------------------


def _alike(target) -> bool:
    """Every model of the target the same for the defence (no Hero)."""
    keys = {(cm.defense, cm.hero, cm.model.rules, cm.model.items,
             cm.model.tough) for cm in target.models}
    return len(keys) == 1 and not any(cm.hero for cm in target.models)


def _units(problem: Problem):
    """[(kind, [names in book order], plain names)] per class."""
    out = []
    for kind in KINDS:
        names = []
        for b in problem.branches:
            for s in b.steps:
                if s.kind == kind and s.weapon.name not in names:
                    names.append(s.weapon.name)
        if names:
            out.append([kind, names, set()])
    if out and out[-1][0] == "other" and all(
            _alike(b.seq.target) and b.leaf is None
            for b in problem.branches):
        cls = out[-1]
        cls[2] = {n for n in cls[1] if all(
            spec.blast == 1 and spec.deadly == 1
            for b in problem.branches for s in b.steps
            if s.weapon.name == n and s.kind == "other"
            for spec, _t in b.seq.parts(s, b.seq.alloc.fresh()))}
    return out


def _count(classes) -> int:
    """Distinct canonical orders: per class m! (m + 1)^p (plain weapons
    only choose their slot between the m others)."""
    total = 1
    for _k, names, plain in classes:
        m = len(names) - len(plain)
        total *= factorial(m) * (m + 1) ** len(plain)
    return total


def _next(cls, used, last_plain):
    """Names that may come next in class 'cls' (canonical: plain names
    in book order inside a run of plain names)."""
    _k, names, plain = cls
    free = [n for n in names if n not in used]
    if all(n in plain for n in free):   # one last run: increasing only
        ok = last_plain is None or names.index(free[0]) > last_plain
        return free[:1] if ok else []
    return [n for n in free if n not in plain or
            last_plain is None or names.index(n) > last_plain]


# --- the search --------------------------------------------------------------


class _Walk:
    """Cost = names applied to every branch (a full order costs one per
    name); the budget bounds it, the deadline is a safety net."""

    def __init__(self, problem, classes, budget, deadline):
        self.p, self.classes = problem, classes
        self.laws = K._Laws(False)
        self.budget, self.deadline = budget, deadline
        self.cost = self.leaves = 0
        self.size = sum(len(c[1]) for c in classes)
        self.pooled = any(b.leaf is not None for b in problem.branches)
        self.best = None                # (Score, order)
        self.cut = False

    def spent(self) -> bool:
        return self.cost >= self.budget or \
            time.perf_counter() > self.deadline

    def evaluate(self, order) -> Score:
        self.cost += self.size
        self.leaves += 1
        return evaluate(self.p, order, self.laws)

    def apply(self, dists, name, kind):
        self.cost += 1
        out = []
        for b, dist in zip(self.p.branches, dists):
            for st in b.steps:
                if st.kind == kind and st.weapon.name == name:
                    dist = _apply(b, dist, st, self.laws)
            out.append(dist)
        return out

    def leaf(self, dists, order):
        if self.pooled:
            sc = self.evaluate(order)
        else:
            self.leaves += 1
            sc = _score(self.p, dists)
        if self.best is None or sc.beats(self.best[0]):
            self.best = (sc, tuple(order))

    def run(self, dists, ci, used, last_plain, order):
        if ci == len(self.classes):
            self.leaf(dists, order)
            return
        cls = self.classes[ci]
        if len(used) == len(cls[1]):
            self.run(dists, ci + 1, set(), None, order)
            return
        if self.spent():                # before applying more names
            self.cut = True
            return
        for n in _next(cls, used, last_plain):
            lp = cls[1].index(n) if n in cls[2] else None
            nd = dists if self.pooled else self.apply(dists, n, cls[0])
            self.run(nd, ci, used | {n}, lp, order + [n])
            if self.cut:
                return


def _tree(classes, cap: int) -> int:
    """Nodes of the canonical walk (names applied), counted up to 'cap'."""
    n = 0

    def go(ci, used, last_plain):
        nonlocal n
        if n >= cap or ci == len(classes):
            return
        cls = classes[ci]
        if len(used) == len(cls[1]):
            go(ci + 1, set(), None)
            return
        for name in _next(cls, used, last_plain):
            n += 1
            go(ci, used | {name},
               cls[1].index(name) if name in cls[2] else None)
            if n >= cap:
                return
    go(0, set(), None)
    return n


def _book(classes) -> list:
    return [n for _k, names, _p in classes for n in names]


def _improve(classes, order, walk) -> tuple:
    """Local search: swap two names of the same class while it helps,
    within the walk's budget."""
    best = walk.evaluate(order)
    spans, i = [], 0
    for _k, names, _p in classes:
        spans.append(range(i, i + len(names)))
        i += len(names)
    changed = True
    while changed and not walk.spent():
        changed = False
        for span in spans:
            for a in span:
                for b in span:
                    if b <= a or walk.spent():
                        continue
                    cand = list(order)
                    cand[a], cand[b] = cand[b], cand[a]
                    sc = walk.evaluate(cand)
                    if sc.beats(best):
                        best, order, changed = sc, cand, True
    return best, tuple(order)


def _greedy(problem, classes, walk) -> list:
    """Each next name: the one with the best score once applied."""
    order, dists = [], [b.dist for b in problem.branches]
    for kind, names, _p in classes:
        left = list(names)
        while left:
            if len(left) == 1:
                pick = left[0]
            else:
                pick = max(left, key=lambda n: (_score(
                    problem, walk.apply(dists, n, kind)).key(),
                    -names.index(n)))
            dists = walk.apply(dists, pick, kind)
            order.append(pick)
            left.remove(pick)
    return order


def search(problem: Problem, current=(), budget: int = BUDGET,
           time_limit: float = TIME_LIMIT) -> Suggestion:
    """Best order of the problem's weapons within the budget;
    'current' = the order to compare with (the user's)."""
    classes = _units(problem)
    t0 = time.perf_counter()
    walk = _Walk(problem, classes, budget, t0 + time_limit)
    book = evaluate(problem, (), walk.laws)
    cur = book if not current else evaluate(problem, current, walk.laws)
    total = _count(classes)
    walk.best = (book, tuple(_book(classes)))
    size = walk.size if walk.pooled else 1
    if _tree(classes, budget + 1) * size > budget or \
            (walk.pooled and total * walk.size > budget):
        walk.cut = True                 # too big: straight to the fallback
    else:
        walk.run([b.dist for b in problem.branches], 0, set(), None, [])
    exact = not walk.cut
    if not exact:                       # the fallback gets its own budget
        walk.budget = walk.cost + budget
        walk.deadline = max(walk.deadline, time.perf_counter()) + \
            time_limit / 2
        start = _greedy(problem, classes, walk)
        sc, order = _improve(classes, start, walk)
        if sc.beats(walk.best[0]):
            walk.best = (sc, order)
    sc, order = walk.best
    true = evaluate(problem, order, walk.laws)  # names in several classes
    if not true.beats(book):
        sc, order = book, ()
    else:
        sc = true
    return Suggestion(tuple(order), sc, book, cur,
                      walk.leaves, total, exact)


# --- problems ----------------------------------------------------------------


def shooting(seq, start=None) -> Problem:
    """A shooting (or the charger's strikes without Parry): 'seq' built
    WITHOUT a weapon order."""
    if seq.barred:
        raise ValueError(f"no attack: {seq.barred}")
    start = seq.alloc.fresh() if start is None else seq.alloc.check(start)
    return Problem([Branch(seq, tuple(seq.steps), {start: 1.0})], start,
                   seq.alloc)


def melee(setup, start=None, side: str = "att") -> Problem:
    """The strikes of the charger (side 'att', the defender's law after
    Impact and Counter) or the strike back of the charged unit (side
    'def', after the charger's strikes) of a MeleeSetup whose order for
    'side' is empty."""
    if setup.orders[side]:
        raise ValueError("the searched side must have no weapon order")
    if setup.barred:
        raise ValueError(f"no attack: {setup.barred}")
    a0, d0 = start or (None, None)
    a0 = setup.a_alloc.fresh() if a0 is None else setup.a_alloc.check(a0)
    d0 = setup.d_alloc.fresh() if d0 is None else setup.d_alloc.check(d0)
    dist = ML.impact_phase(setup, a0, d0, False)
    dist = ML._strike(dist, setup, "def", "counter", False)
    phase, me, other = "strike", 0, 1
    if side == "def":
        dist = ML._strike(dist, setup, "att", "strike", False)
        phase, me, other = "back", 1, 0
    my_alloc = setup.a_alloc if side == "att" else setup.d_alloc
    groups: dict = {}
    rest: dict = {}
    for st, p in dist.items():
        alive = my_alloc.alive(st[me])
        K._add(groups.setdefault(alive, {}) if alive else rest, st[other], p)
    branches = []
    for alive, law in groups.items():
        seq = setup.seq(side, alive)
        steps = tuple(setup.steps(phase, seq))
        if not steps:
            for t, q in law.items():
                K._add(rest, t, q)
            continue
        parry = any(setup.parry_dice("def" if side == "att" else "att", t)
                    for t in law)

        def leaf(steps_, t, seq=seq):
            return setup.phase(side, list(steps_), seq, t, False)
        branches.append(Branch(seq, steps, law, leaf if parry else None))
    start, alloc = (d0, setup.d_alloc) if side == "att" else \
        (a0, setup.a_alloc)
    return Problem(branches, start, alloc, rest=rest)
