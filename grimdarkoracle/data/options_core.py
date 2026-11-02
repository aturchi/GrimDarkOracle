"""Upgrade-section semantics: what a section allows and how it changes models.

Pure module (no Tk, no Army Forge field names: it reads af_book objects).

A unit is held as a list of per-model loadouts (weapons and items with
counts), because several 3.6 mechanics depend on WHICH model carries what:
a weapon team gains Tough(3) on one model only, survivors strike back with
their own weapons, Takedown picks one model.

Section shapes (variant, per-model, affects, select) -> Caps; the table is
in :func:`caps` and was derived from the 22 shapes of the 49 official books.
Prices and caps were verified in the Army Forge UI on the reference
configurations and the rare shapes of tests/reference_configs.py
(2026-10-31).

Instance placement (Army Forge does not say which model takes an upgrade):
the user may pick the model of each instance;
otherwise it goes to the model that can still take it with the fewest
upgrades so far (ties: lowest index), so special weapons spread over models.
What one model can take is :func:`capacity`.
"""
import re
from dataclasses import dataclass, field, replace

from grimdarkoracle.data.af_book import Item, Section, Weapon

_COUNT_PREFIX = re.compile(r"^(\d+)x\s+", re.IGNORECASE)


# --- names -----------------------------------------------------------------

def parse_target(target: str) -> tuple[int, str]:
    """'2x Claw' -> (2, 'claw'); 'Rifles' -> (1, 'rifles')."""
    m = _COUNT_PREFIX.match(target.strip())
    n = int(m.group(1)) if m else 1
    return n, norm_name(target)


def norm_name(name: str) -> str:
    """Lower case, no count prefix, single spaces."""
    name = _COUNT_PREFIX.sub("", name.strip())
    return " ".join(name.lower().split())


def same_name(a: str, b: str) -> bool:
    """Equal up to case, count prefix and an English plural (-s / -es).
    Verified on all 2 786 targets of the official books: no false miss."""
    a, b = norm_name(a), norm_name(b)
    return a == b or a + "s" == b or b + "s" == a or \
        a + "es" == b or b + "es" == a


# --- caps --------------------------------------------------------------------

@dataclass(frozen=True)
class Caps:
    """What the option panel may offer for one section.

    mode: 'radio' (at most one option, count 1), 'check' (each option 0/1)
    or 'count' (spinbox per option). per_option / total bound the counts.
    expand_all: one purchase applies to every model (or every target).
    """
    mode: str
    per_option: int
    total: int
    expand_all: bool = False


def _q(quant):
    return (None, None) if quant is None else (quant.kind, quant.value)


def caps(section: Section, size: int, avail: int | None) -> Caps:
    """Caps of 'section' for a unit of 'size' models, where 'avail' is the
    number of target instances currently present (None: no targets)."""
    n_opt = max(1, len(section.options))
    a_kind, a_val = _q(section.affects)
    s_kind, s_val = _q(section.select)
    av = avail if avail is not None else size
    if section.variant == "replace":
        if a_kind is None:
            return Caps("radio", 1, 1)
        if a_kind == "all":
            return Caps("radio", 1, 1, expand_all=True)
        if a_kind == "exactly" and a_val == 1:
            return Caps("radio", 1, 1)
        k = av if a_kind == "any" else min(a_val or 0, av)
        return Caps("count", k, k)
    if section.variant == "attachment":
        if not section.model:
            return Caps("radio", 1, 1)
        # Verified in Army Forge (see tests/reference_configs.py): one
        # attachment per target weapon,
        # whatever the options - "one" and "any" differ only in wording.
        return Caps("count", av, av)
    # upgrade
    if not section.model:
        if s_kind == "exactly":
            return Caps("radio", 1, 1)
        if s_kind == "up to":
            # Verified: the same option may be taken twice.
            return Caps("count", s_val, s_val)
        return Caps("check", 1, n_opt)
    if a_kind == "all":
        if s_kind == "exactly":
            return Caps("radio", 1, 1, expand_all=True)
        return Caps("check", 1, n_opt, expand_all=True)
    if a_kind == "exactly":
        if s_kind == "exactly":
            return Caps("radio", 1, 1)
        return Caps("check", 1, n_opt)
    if a_kind == "up to":
        k = min(a_val, size)
        return Caps("count", k, k)
    # affects any: any number of models, each option on up to every model
    return Caps("count", size, size * n_opt)


# --- per-model state ---------------------------------------------------------

@dataclass(eq=False)
class ModelState:
    weapons: dict = field(default_factory=dict)    # Weapon -> count
    items: dict = field(default_factory=dict)      # Item -> count
    load: int = 0                                  # upgrades placed here
    points: int = 0                                # their price (resolve)


def profile(thing):
    """One copy of a weapon / item as a dict key: count 1 and no "Nx "
    label prefix, so a base 'Hand Weapon' (count 5) and a gained one
    (count 1) are the same key."""
    return replace(thing, count=1, label=_COUNT_PREFIX.sub("", thing.label))


def _add(bag: dict, key, n: int) -> None:
    key = profile(key)
    bag[key] = bag.get(key, 0) + n
    if bag[key] <= 0:
        del bag[key]


def _spread(models: list, key, total: int, bag: str) -> None:
    """Base allocation: 'total' copies over the models, evenly, extra
    copies on the first models (a count-1 weapon goes to model 0)."""
    per, rem = divmod(total, len(models))
    for i, m in enumerate(models):
        n = per + (1 if i < rem else 0)
        if n:
            _add(getattr(m, bag), key, n)


def base_models(unit) -> list[ModelState]:
    """Per-model loadouts of the unit as printed in the book."""
    models = [ModelState() for _ in range(max(1, unit.size))]
    for w in unit.weapons:
        _spread(models, w, w.count, "weapons")
    for it in unit.items:
        _spread(models, it, it.count, "items")
        for w in it.weapons:
            _spread(models, w, w.count * it.count, "weapons")
    return models


def _held(model: ModelState, name: str) -> tuple[str, list, int]:
    """('weapons' | 'items', matching keys, total count) held by 'model'.
    Weapons are searched first; profiles with the same name add up."""
    for bag in ("weapons", "items"):
        keys = [k for k in getattr(model, bag) if same_name(k.name, name)]
        if keys:
            return bag, keys, sum(getattr(model, bag)[k] for k in keys)
    return "", [], 0


def model_instances(model: ModelState, targets) -> int:
    """How many times all 'targets' can be taken from this one model."""
    if not targets:
        return 0
    counts = []
    for t in targets:
        n, name = parse_target(t)
        counts.append(_held(model, name)[2] // n)
    return min(counts)


def available(models, targets) -> int | None:
    """Target instances present in the unit (None for target-less
    sections). Per model first; if no model holds every target (targets
    spread over models), fall back to unit totals."""
    if not targets:
        return None
    per_model = sum(model_instances(m, targets) for m in models)
    if per_model:
        return per_model
    totals = []
    for t in targets:
        n, name = parse_target(t)
        totals.append(sum(_held(m, name)[2] for m in models) // n)
    return min(totals)


def _remove_target(models, model, target) -> None:
    """Remove one instance of 'target' from 'model' (or any holder)."""
    n, name = parse_target(target)
    for m in [model] + [x for x in models if x is not model]:
        bag, keys, have = _held(m, name)
        if have < n:
            continue
        left = n
        for key in keys:                    # take from each profile in turn
            take = min(left, getattr(m, bag)[key])
            _add(getattr(m, bag), key, -take)
            if bag == "items":
                for w in key.weapons:
                    _add(m.weapons, w, -w.count * take)
            left -= take
            if not left:
                return
    raise ValueError(f"target {target!r} not present")


def give(model: ModelState, gains, times: int = 1) -> None:
    """Add the gains of an option to one model, 'times' times."""
    for g in gains:
        if isinstance(g, Weapon):
            _add(model.weapons, g, g.count * times)
        elif isinstance(g, Item):
            _add(model.items, g, g.count * times)
            for w in g.weapons:
                _add(model.weapons, w, w.count * g.count * times)


def placeable(section: Section, size: int) -> bool:
    """Whether the user may choose the model of each instance: not for
    single models, unit-level upgrades (single models only) or
    sections applied to every model / every target."""
    if size < 2 or (section.variant == "upgrade" and not section.model):
        return False
    return not caps(section, size, None).expand_all


def _one_per_model(section: Section) -> bool:
    """'... with one': a model takes at most one option of the section."""
    q = section.select
    return q is not None and q.kind == "exactly" and q.value == 1


def capacity(section: Section, option, models, i: int, used: dict) -> int:
    """Instances of 'option' model i can still take in this section.
   'used' counts the instances already placed in the
    section: {(i, None): all options, (i, option uid): that option}."""
    m = models[i]
    if section.targets:
        n = model_instances(m, section.targets)
        if not any(model_instances(x, section.targets) for x in models):
            k, name = parse_target(section.targets[0])   # targets spread
            n = _held(m, name)[2] // k
        if section.variant != "replace":    # attachments keep the target
            n -= used.get((i, None), 0)
        return max(0, n)
    if not section.model:
        return 1 << 30                      # unit-level: single models
    # "Upgrade one model / up to N models": the options of the section go
    # on at most N distinct models.
    q = section.affects
    if q is not None and q.kind in ("exactly", "up to") and q.value:
        taken = {j for (j, o), n in used.items() if o is None and n}
        if i not in taken and len(taken) >= q.value:
            return 0
    key = (i, None) if _one_per_model(section) else (i, option.uid)
    return max(0, 1 - used.get(key, 0))


def _pick(models, section, option, used) -> int:
    """Default model of the next instance: fewest upgrades among the
    models that can take it (ties: lowest index)."""
    ok = [i for i in range(len(models))
          if capacity(section, option, models, i, used) > 0]
    return min(ok or range(len(models)), key=lambda i: (models[i].load, i))


def apply_option(section: Section, option, count: int, models,
                 placement=None, used: dict | None = None):
    """Apply 'count' purchases of 'option' of 'section' to 'models' (caps
    already checked by the caller). 'placement': model index per instance
    (None = automatic); 'used' is shared by the calls of one section.
    Returns (model index of each instance, issues)."""
    size = len(models)
    used = {} if used is None else used
    expand = caps(section, size, available(models, section.targets)).expand_all
    consume = section.variant == "replace"
    if expand and section.targets:          # replace all
        for m in models:
            k = model_instances(m, section.targets)
            for _ in range(k):
                for t in section.targets:
                    _remove_target(models, m, t)
            give(m, option.gains, k)
        return (), []
    if expand:                              # upgrade all models
        for m in models:
            give(m, option.gains)
        return (), []
    placed, issues = [], []
    for n in range(count):
        want = placement[n] if placement and n < len(placement) else None
        if not section.model and section.variant == "upgrade":
            i = 0                           # unit-level upgrade
        elif want is not None and 0 <= want < size and \
                capacity(section, option, models, want, used) > 0:
            i = want
        else:
            if want is not None:
                issues.append(f"{section.label!r}: model {want + 1} cannot "
                              f"take {option.label!r}; placed automatically")
            i = _pick(models, section, option, used)
        m = models[i]
        if consume:
            for t in section.targets:
                _remove_target(models, m, t)
        give(m, option.gains)
        m.load += 1
        for key in ((i, None), (i, option.uid)):
            used[key] = used.get(key, 0) + 1
        placed.append(i)
    return tuple(placed), issues
