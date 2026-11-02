"""resolve(): a unit of a book plus the user's choices -> ResolvedUnit.

Pure function of its inputs: never saved, recomputed on every change.
Invalid choices are kept out of the result AND reported in
``ResolvedUnit.issues``; nothing is pruned silently.

Evaluation order is the book order of the unit's packages and sections.
Within a section, instances placed by the user on a chosen model are
applied before the automatic ones, so these never take a model the user
asked for.
A section whose targets are not present yet is deferred and retried after
the others, until nothing changes: Army Forge chains are implicit and in
one official case (Machine Cults, Cult Leader) the granting section comes
AFTER the section that needs its weapon.
"""
from dataclasses import dataclass, replace

from grimdarkoracle.data import options_core as oc
from grimdarkoracle.data import rule_weapons
from grimdarkoracle.data.af_book import Book, Item, RuleRef, Weapon


@dataclass(frozen=True)
class Choice:
    """One option taken 'count' times. 'models': model index of each
    instance (None or missing = automatic placement). Label fingerprints
    for robust references live in the army list, not here."""
    package: str
    section: str
    option: str
    count: int = 1
    models: tuple = ()


@dataclass(frozen=True)
class ResolvedModel:
    weapons: tuple[tuple[Weapon, int], ...]
    items: tuple[tuple[Item, int], ...]
    rules: tuple[RuleRef, ...]      # unit rules + rules of carried items
    # Instances placed on this model and their points ("all models"
    # upgrades excluded): the Analyzer's removal order.
    upgrades: int = 0
    upgrade_points: int = 0

    @property
    def tough(self) -> int:
        """Sum of the integer Tough ratings (0 = not Tough)."""
        return sum(r.rating for r in self.rules
                   if r.name == "Tough" and isinstance(r.rating, int))


@dataclass(frozen=True)
class SectionState:
    """A section as the option panel must show it."""
    package: str
    uid: str
    label: str
    caps: oc.Caps
    avail: int | None               # target instances (None: no targets)
    enabled: bool
    counts: tuple[tuple[str, int], ...]   # (option uid, applied count)
    placeable: bool = False         # the user may pick the models
    placed: tuple[tuple[str, tuple[int, ...]], ...] = ()  # (option, models)


@dataclass(frozen=True)
class ResolvedUnit:
    book_uid: str
    unit_id: str
    name: str
    quality: int
    defense: int
    base_cost: int
    points: int
    models: tuple[ResolvedModel, ...]
    sections: tuple[SectionState, ...]
    issues: tuple[str, ...]
    modified: bool = False          # overrides applied (overrides.py)
    combined: bool = False          # two copies merged (combine)

    @property
    def size(self) -> int:
        return len(self.models)

    def weapons(self) -> list[tuple[Weapon, int]]:
        """Weapons of the whole unit with total counts, first-seen order."""
        total: dict = {}
        for m in self.models:
            for w, n in m.weapons:
                total[w] = total.get(w, 0) + n
        return list(total.items())

    def rule_models(self) -> dict[str, int]:
        """Rule label -> number of models having it."""
        out: dict = {}
        for m in self.models:
            for label in {r.label for r in m.rules}:
                out[label] = out.get(label, 0) + 1
        return out


def _group(book: Book, unit, choices, issues) -> dict:
    """Valid choices grouped by (package, section): {option uid: [model
    index or None per instance]}."""
    groups: dict = {}
    for c in choices:
        pkg = book.packages.get(c.package)
        if pkg is None or c.package not in unit.packages:
            issues.append(f"package {c.package!r} not available to the unit")
            continue
        sec = next((s for s in pkg.sections if s.uid == c.section), None)
        if sec is None:
            issues.append(f"section {c.section!r} not in package {c.package!r}")
            continue
        if sec.uid in unit.disabled_sections:
            issues.append(f"section {sec.label!r} is disabled for this unit")
            continue
        if not any(o.uid == c.option for o in sec.options):
            issues.append(f"option {c.option!r} not in section {sec.label!r}")
            continue
        if c.count < 1:
            issues.append(f"{sec.label!r}: count {c.count} ignored")
            continue
        if len(c.models) > c.count:
            issues.append(f"{sec.label!r}: {len(c.models)} models given for "
                          f"{c.count} instances; extra ones ignored")
        pl = (list(c.models) + [None] * c.count)[:c.count]
        groups.setdefault((c.package, c.section), {}) \
            .setdefault(c.option, []).extend(pl)
    return groups


def _todo(sec, wanted, models, unit, issues):
    """The options of a section that fit its caps: (caps, avail, todo =
    [(option, n, placements, price)], points, applied counts)."""
    avail = oc.available(models, sec.targets)
    cap = oc.caps(sec, len(models), avail)
    placeable = oc.placeable(sec, len(models))
    points, total, applied, todo = 0, 0, [], []
    for opt in sec.options:                     # book order of the options
        pl = wanted.get(opt.uid, [])
        n = len(pl)
        if not n:
            continue
        if n > cap.per_option or total + n > cap.total:
            issues.append(f"{sec.label!r}: {opt.label!r} x{n} exceeds the "
                          f"limit ({cap.per_option} per option, {cap.total} "
                          "in total); not applied")
            continue
        price = opt.cost_for(unit.id)
        if price is None:
            issues.append(f"{opt.label!r} has no price for this unit")
            price = 0
        if not placeable and any(p not in (None, 0) for p in pl):
            issues.append(f"{sec.label!r}: {opt.label!r} cannot be placed "
                          "on a chosen model; placement ignored")
        todo.append((opt, n, pl if placeable else [None] * n, price))
        points += price * n
        total += n
        applied.append((opt.uid, n))
    return cap, avail, todo, points, applied


def _apply_section(sec, wanted, models, unit, issues):
    """Apply the wanted {option uid: placements} of one section within its
    caps. Returns (points, caps, avail, applied counts, placed models)."""
    cap, avail, todo, points, applied = _todo(sec, wanted, models, unit,
                                              issues)
    used: dict = {}
    placed = {o.uid: () for o, _, _, _ in todo}
    for explicit in (True, False):              # chosen models first
        for opt, n, pl, price in todo:
            sel = [p for p in pl if (p is not None) == explicit]
            if sel:
                got, why = oc.apply_option(sec, opt, len(sel), models,
                                           sel if explicit else None, used)
                placed[opt.uid] += got
                for i in got:
                    models[i].points += price
                issues.extend(why)
    return points, cap, avail, applied, tuple(placed.items())


def _order(ordered, groups, models):
    """Yield the chosen sections in the order they apply; the caller applies
    each one before the next is picked (availability changes). Returns the
    sections whose targets never appeared."""
    pending = [(pu, s) for pu, s in ordered if (pu, s.uid) in groups]
    progress = True
    while pending and progress:
        progress, later = False, []
        for pu, sec in pending:
            if sec.targets and not oc.available(models, sec.targets):
                later.append((pu, sec))         # chain not satisfied yet
                continue
            yield pu, sec
            progress = True
        pending = later
    return pending


def placement_candidates(book: Book, unit_id: str, choices, index: int,
                         picks) -> list[tuple[int, ...]] | None:
    """Models able to take each instance of choices[index] if its
    placement were 'picks' (model index or None per instance): for each
    instance, the models with capacity left at the moment resolve() would
    apply it as an explicit pick (chosen instances first, options
    in book order, earlier picks consumed). None: the section is not
    placeable or never applies (targets absent)."""
    unit = book.units[unit_id]
    choices = list(choices)
    target = choices[index]
    picks = (list(picks) + [None] * target.count)[:target.count]
    choices[index] = replace(target, models=tuple(picks))
    issues: list[str] = []
    models = oc.base_models(unit)
    groups = _group(book, unit, choices, issues)
    key = (target.package, target.section)
    offset = sum(c.count for c in choices[:index]
                 if (c.package, c.section, c.option) ==
                 (target.package, target.section, target.option))
    ordered = [(p.uid, s) for p in book.unit_packages(unit)
               for s in p.sections]
    for pu, sec in _order(ordered, groups, models):
        if (pu, sec.uid) != key:
            _apply_section(sec, groups[(pu, sec.uid)], models, unit, issues)
            continue
        if not oc.placeable(sec, len(models)):
            return None
        _cap, _av, todo, _pts, _ap = _todo(sec, groups[key], models, unit,
                                           issues)
        out = [()] * target.count
        used: dict = {}
        for opt, _n, pl, _price in todo:
            for k, p in enumerate(pl):
                mine = opt.uid == target.option and \
                    offset <= k < offset + target.count
                if mine:
                    out[k - offset] = tuple(
                        i for i in range(len(models))
                        if oc.capacity(sec, opt, models, i, used) > 0)
                if p is not None:
                    oc.apply_option(sec, opt, 1, models, [p], used)
        return out
    return None


def resolve(book: Book, unit_id: str, choices=()) -> ResolvedUnit:
    """Resolve 'unit_id' of 'book' with 'choices' (iterable of Choice).
    Raises KeyError for an unknown unit (the army list flags it)."""
    unit = book.units[unit_id]
    issues: list[str] = []
    models = oc.base_models(unit)
    groups = _group(book, unit, choices, issues)
    ordered = [(p.uid, s) for p in book.unit_packages(unit)
               for s in p.sections]
    done: dict = {}
    points = unit.cost
    order = _order(ordered, groups, models)
    while True:
        try:
            pu, sec = next(order)
        except StopIteration as stop:
            pending = stop.value
            break
        pts, cap, avail, applied, placed = _apply_section(
            sec, groups[(pu, sec.uid)], models, unit, issues)
        points += pts
        done[(pu, sec.uid)] = (cap, avail, tuple(applied), placed)
    for pu, sec in pending:
        issues.append(f"{sec.label!r}: targets {list(sec.targets)} absent; "
                      "choice not applied")

    sections = []
    for pu, sec in ordered:
        if (pu, sec.uid) in done:
            cap, avail, applied, placed = done[(pu, sec.uid)]
        else:
            avail = oc.available(models, sec.targets)
            cap, applied, placed = oc.caps(sec, len(models), avail), (), ()
        enabled = sec.uid not in unit.disabled_sections and \
            (not sec.targets or bool(avail) or bool(applied))
        sections.append(SectionState(pu, sec.uid, sec.label, cap, avail,
                                     enabled, applied,
                                     oc.placeable(sec, len(models)), placed))

    resolved_models = []
    for m in models:
        rules = list(unit.rules)
        for it in m.items:
            rules.extend(it.rules)
        resolved_models.append(ResolvedModel(
            tuple(m.weapons.items()), tuple(m.items.items()), tuple(rules),
            m.load, m.points))
    resolved_models = rule_weapons.add_models(resolved_models)
    return ResolvedUnit(book.uid, unit.id, unit.name, unit.quality,
                        unit.defense, unit.cost, points,
                        resolved_models, tuple(sections),
                        tuple(issues))


def all_model_choices(ru: ResolvedUnit) -> set:
    """(section uid, option uid) pairs applied to every model at once."""
    return {(s.uid, o) for s in ru.sections if s.caps.expand_all
            for o, _ in s.counts}


def combine(a: ResolvedUnit, b: ResolvedUnit) -> ResolvedUnit:
    """Combined Unit (core rules 3.6): two copies of the same multi-model
    unit as one. Upgrades that apply to all models must be bought for
    both; a mismatch is reported, not refused, so the list stays editable.
    The section states are those of the first copy."""
    issues = list(a.issues) + [f"copy B: {i}" for i in b.issues]
    if (a.book_uid, a.unit_id) != (b.book_uid, b.unit_id):
        issues.append("combined copies are different units")
    if a.size < 2:
        issues.append("only multi-model units can be combined")
    if all_model_choices(a) != all_model_choices(b):
        issues.append("combined copies differ in upgrades that apply to "
                      "all models")
    return rule_weapons.add_all(replace(        # auras reach both
        a, points=a.points + b.points, models=a.models + b.models,
        issues=tuple(issues), combined=True))
