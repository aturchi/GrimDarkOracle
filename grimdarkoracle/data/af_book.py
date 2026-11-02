"""Army Forge adapter: raw army-book / core-rules JSON -> typed, immutable views.

This is the ONLY module that knows Army Forge field names. Everything else
(options_core, resolve, the registry, the UI) works on the dataclasses
below, so an Army Forge schema change is fixed here and nowhere else.

Facts encoded here (verified on the 49 official GF 3.6.0 books, 2026-10-31):

- uids of units, packages, sections and options are unique WITHIN a book
  only (packages are shared by uid between related books with different
  content), so they are always scoped by book.
- Section ``id`` is regenerated on every request: never read. Options are
  taken from their section's ``options`` list (``parentSectionUid`` is
  stale in ~20% of the options; ``parentSectionId`` is redundant).
- Points: ``costs[]`` entry whose ``unitId`` is the unit (``option.cost``
  is often null or wrong because packages are shared between units).
- Weapon attacks: ``attacks`` as printed in the label; ``attacksMultiplier``
  is NOT a multiplier of it and is ignored.
- Rule ``rating`` may be an int, a string (``Split(Changelings [10])``),
  a numeric string (``Tough`` "3" on weapon teams: converted to int) or
  absent. Weapon ``range`` may be null (one melee lance): treated as
  0 with a warning.
- Option gains are ``ArmyBookWeapon``, ``ArmyBookItem`` (content: rules
  and/or weapons) or ``ArmyBookRule`` (a bare rule, stored as an Item).
- Sub-faction books (``factionRelation`` Detachment / Aspect / Disciples)
  are served already transformed and self-contained; ``transforms`` only
  records how they were derived and is ignored.

Parsing is lenient on unknown values (recorded in ``Book.warnings`` for the
import report) and strict on missing structure (``BookFormatError``).
"""

import json
from dataclasses import dataclass, field

# Quantifier kinds seen in section 'affects' / 'select'.
QUANT_KINDS = ("exactly", "up to", "any", "all")
VARIANTS = ("upgrade", "replace", "attachment")


class BookFormatError(ValueError):
    """The JSON lacks a field the adapter cannot do without."""


@dataclass(frozen=True)
class RuleRef:
    """A rule as attached to a unit, weapon, item or gain."""
    id: str
    name: str
    rating: int | str | None = None
    label: str = ""
    # Not an Army Forge field: set when an ENEMY rule gives this rule (a
    # debuff), so Unstoppable drops its negative modifiers.
    foreign: bool = False


@dataclass(frozen=True)
class Weapon:
    name: str
    count: int
    range: int                       # 0 = melee
    attacks: int
    rules: tuple[RuleRef, ...] = ()
    label: str = ""
    weapon_id: str = ""

    @property
    def melee(self) -> bool:
        return self.range == 0


@dataclass(frozen=True)
class Item:
    """An equipment item, or a bare rule gained by an option (is_rule)."""
    name: str
    count: int
    rules: tuple[RuleRef, ...] = ()
    weapons: tuple[Weapon, ...] = ()
    label: str = ""
    is_rule: bool = False


@dataclass(frozen=True)
class Quant:
    """Section quantifier: kind in QUANT_KINDS, value for exactly / up to."""
    kind: str
    value: int | None = None


@dataclass(frozen=True)
class Option:
    uid: str
    label: str
    gains: tuple[Weapon | Item, ...]
    costs: tuple[tuple[str, int], ...]      # (unit id, points)

    def cost_for(self, unit_id: str) -> int | None:
        """Points of this option for 'unit_id', None if not priced for it."""
        for uid, pts in self.costs:
            if uid == unit_id:
                return pts
        return None


@dataclass(frozen=True)
class Section:
    uid: str
    label: str
    variant: str
    model: bool                      # per-model upgrade
    affects: Quant | None
    select: Quant | None
    targets: tuple[str, ...]
    options: tuple[Option, ...]
    hero_only: bool = False
    low_prio: bool = False


@dataclass(frozen=True)
class Package:
    uid: str
    hint: str
    sections: tuple[Section, ...]


@dataclass(frozen=True)
class Unit:
    id: str
    name: str
    size: int
    quality: int
    defense: int
    cost: int
    rules: tuple[RuleRef, ...]
    weapons: tuple[Weapon, ...]
    items: tuple[Item, ...]
    packages: tuple[str, ...]        # package uids, in book order
    disabled_sections: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RuleDef:
    """A rule definition (book specialRules or core rules)."""
    id: str
    name: str
    description: str
    has_rating: bool = False
    aliased_rule_id: str | None = None
    original_name: str | None = None
    core_type: int | None = None     # meaning unknown, unused


@dataclass(frozen=True)
class Spell:
    id: str
    name: str
    threshold: int
    effect: str


@dataclass(frozen=True)
class Book:
    uid: str
    name: str
    version: str
    game_system: int
    faction_name: str | None
    faction_relation: str | None
    units: dict[str, Unit]
    packages: dict[str, Package]
    rules: dict[str, RuleDef]
    spells: tuple[Spell, ...]
    warnings: tuple[str, ...] = field(default=())

    def unit_packages(self, unit: Unit) -> list[Package]:
        """The packages of 'unit', in book order (missing uids skipped:
        they are reported in warnings at load time)."""
        return [self.packages[p] for p in unit.packages if p in self.packages]


# --- parsing ---------------------------------------------------------------

def _req(d, key, where):
    if not isinstance(d, dict) or key not in d:
        raise BookFormatError(f"{where}: missing '{key}'")
    return d[key]


def _rule_ref(d) -> RuleRef:
    rating = d.get("rating")
    if isinstance(rating, str) and rating.strip().isdigit():
        rating = int(rating)        # e.g. Weapon Team gains Tough "3"
    return RuleRef(d["id"], d["name"], rating, d.get("label") or d["name"])


def _weapon(d, warn, where) -> Weapon:
    rng = d.get("range")
    if rng is None:
        warn.append(f"{where}: weapon '{d.get('name')}' has no range, "
                    "taken as melee")
        rng = 0
    return Weapon(name=_req(d, "name", where), count=d.get("count", 1),
                  range=rng, attacks=_req(d, "attacks", where),
                  rules=tuple(_rule_ref(r) for r in d.get("specialRules", [])),
                  label=d.get("label", ""), weapon_id=d.get("weaponId", ""))


def _item(d, warn, where) -> Item:
    rules, weapons = [], []
    for c in d.get("content", []):
        kind = c.get("type")
        if kind == "ArmyBookRule":
            rules.append(_rule_ref(c))
        elif kind == "ArmyBookWeapon":
            weapons.append(_weapon(c, warn, where))
        else:
            warn.append(f"{where}: unknown item content type {kind!r}")
    return Item(d["name"], d.get("count", 1), tuple(rules), tuple(weapons),
                d.get("label", d["name"]))


def _gain(d, warn, where) -> Weapon | Item | None:
    kind = d.get("type")
    if kind == "ArmyBookWeapon":
        return _weapon(d, warn, where)
    if kind == "ArmyBookItem":
        return _item(d, warn, where)
    if kind == "ArmyBookRule":
        return Item(d["name"], d.get("count", 1), (_rule_ref(d),), (),
                    d.get("label", d["name"]), is_rule=True)
    warn.append(f"{where}: unknown gain type {kind!r} ignored")
    return None


def _quant(d, warn, where) -> Quant | None:
    if not d:
        return None
    kind = d.get("type")
    if kind not in QUANT_KINDS:
        warn.append(f"{where}: unknown quantifier {kind!r}")
    return Quant(kind, d.get("value"))


def _section(d, warn, where) -> Section:
    uid = _req(d, "uid", where)
    where = f"{where}/{uid}"
    variant = d.get("variant")
    if variant not in VARIANTS:
        warn.append(f"{where}: unknown variant {variant!r}")
    options = []
    for o in d.get("options", []):
        ow = f"{where}/{o.get('uid')}"
        gains = (_gain(g, warn, ow) for g in o.get("gains", []))
        options.append(Option(
            uid=_req(o, "uid", ow), label=o.get("label", ""),
            gains=tuple(g for g in gains if g is not None),
            costs=tuple((c["unitId"], c["cost"]) for c in o.get("costs", []))))
    return Section(uid=uid, label=d.get("label", ""), variant=variant,
                   model=bool(d.get("model")),
                   affects=_quant(d.get("affects"), warn, where),
                   select=_quant(d.get("select"), warn, where),
                   targets=tuple(d.get("targets") or ()),
                   options=tuple(options),
                   hero_only=bool(d.get("isHeroUpgrade")),
                   low_prio=bool(d.get("isLowPrio")))


def _unit(d, warn) -> Unit:
    uid = _req(d, "id", "unit")
    where = f"unit {d.get('name')!r} ({uid})"
    return Unit(
        id=uid, name=_req(d, "name", where), size=_req(d, "size", where),
        quality=_req(d, "quality", where), defense=_req(d, "defense", where),
        cost=_req(d, "cost", where),
        rules=tuple(_rule_ref(r) for r in d.get("rules", [])),
        weapons=tuple(_weapon(w, warn, where) for w in d.get("weapons", [])),
        items=tuple(_item(i, warn, where) for i in d.get("items", [])),
        packages=tuple(d.get("upgrades") or ()),
        disabled_sections=frozenset(d.get("disabledSections") or ()))


def _rule_def(d) -> RuleDef:
    return RuleDef(id=d["id"], name=d["name"],
                   description=d.get("description", ""),
                   has_rating=bool(d.get("hasRating")),
                   aliased_rule_id=d.get("aliasedRuleId") or None,
                   original_name=d.get("originalName"),
                   core_type=d.get("coreType"))


def parse_book(raw: dict) -> Book:
    """Typed view of an Army Forge army book JSON (as saved by af_fetch)."""
    warn: list[str] = []
    uid = _req(raw, "uid", "book")
    units = {}
    for u in _req(raw, "units", f"book {uid}"):
        unit = _unit(u, warn)
        units[unit.id] = unit
    packages = {}
    for p in raw.get("upgradePackages", []):
        pu = _req(p, "uid", f"book {uid} package")
        packages[pu] = Package(pu, p.get("hint", ""), tuple(
            _section(s, warn, f"package {pu}") for s in p.get("sections", [])))
    for unit in units.values():
        for p in unit.packages:
            if p not in packages:
                warn.append(f"unit {unit.name!r}: unknown package {p!r}")
    spells = tuple(Spell(s["id"], s["name"], s.get("threshold", 0),
                         s.get("effect", "")) for s in raw.get("spells", []))
    return Book(uid=uid, name=raw.get("name", uid),
                version=raw.get("versionString", ""),
                game_system=raw.get("gameSystemId", 0),
                faction_name=raw.get("factionName") or None,
                faction_relation=raw.get("factionRelation") or None,
                units=units, packages=packages,
                rules={r["id"]: _rule_def(r)
                       for r in raw.get("specialRules", [])},
                spells=spells, warnings=tuple(warn))


def parse_core_rules(raw: dict) -> dict[str, RuleDef]:
    """Core special rules (``/api/rules/common/<gs>``); traits are ignored."""
    return {r["id"]: _rule_def(r) for r in _req(raw, "rules", "core rules")}


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_book(path) -> Book:
    return parse_book(_load(path))


def load_core_rules(path) -> dict[str, RuleDef]:
    return parse_core_rules(_load(path))
