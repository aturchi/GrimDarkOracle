"""The attacker's weapon order and Takedown target preferences in the
Analyzer window. Pure.

- Weapon order: weapon names of the attacking side (Hero included); the
  listed weapons attack first within their class, Takedown, Deadly, the
  others; in melee it is the charger's order. () = book order.
- Takedown targets: ONE preference list of the TARGET's model places
  (Combatant places: the host's models, then the joined Hero), first
  choice first, used by every Takedown weapon of the attack (shooting,
  the charger's strikes, a damage spell "as a unit of [1]"); a dead pick
  passes to the next. () = the default (the model the allocation
  order would remove last first).

Both reach analyzer_core.Options through side_spec.run(**Orders.kw()).
The preferences belong to the target as configured: follow() resets them
when the target's configuration changes and drops weapon names the
attacker no longer has.
"""
from dataclasses import dataclass

from grimdarkoracle.app import unit_labels as UL
from grimdarkoracle.engine.context import combatant
from grimdarkoracle.engine.target_state import Allocation


@dataclass(frozen=True)
class Orders:
    weapon_order: tuple[str, ...] = ()
    takedown_targets: tuple[int, ...] = ()

    def kw(self) -> dict:
        """Keyword arguments of setup_model.Setup.options / side_spec.run."""
        return {"weapon_order": self.weapon_order,
                "takedown_targets": self.takedown_targets}

    def to_dict(self) -> dict:
        return {"weapon_order": list(self.weapon_order),
                "takedown_targets": list(self.takedown_targets)}

    @classmethod
    def from_dict(cls, d) -> "Orders":
        """Lenient: a missing or malformed part is the default."""
        d = d if isinstance(d, dict) else {}
        names = d.get("weapon_order")
        places = d.get("takedown_targets")
        names = tuple(dict.fromkeys(n for n in names if isinstance(n, str))) \
            if isinstance(names, list) else ()
        places = tuple(dict.fromkeys(
            p for p in places if isinstance(p, int) and not isinstance(p, bool)
            and p >= 0)) if isinstance(places, list) else ()
        return cls(names, places)


@dataclass(frozen=True)
class Info:
    """What the two dialogs need, for the current sides and setup."""
    names: tuple[str, ...] = ()     # attacker's weapon names
    labels: tuple[str, ...] = ()    # target's model labels, by place
    default: tuple[int, ...] = ()   # default Takedown preference
    takedown: bool = False          # the attack has Takedown
    weapons: bool = False           # a weapon order means something
    target: str = ""                # target configuration signature


def default_takedown(unit, hero=None) -> tuple[int, ...]:
    """Default: the reverse of the fresh unit's allocation order (as
    engine.sequence.AttackSequence uses without preferences)."""
    al = Allocation.of(combatant(unit, hero=hero))
    return tuple(reversed(al.order(al.fresh())))


def _unit_sig(u) -> tuple:
    if u is None:
        return ()
    cfg = u.cfg
    return (cfg.book.uid, cfg.unit.id, cfg.choices, u.combined,
            None if u.cfg_b is None else u.cfg_b.choices,
            repr(u.overrides), u.label)


def signature(spec) -> str:
    """The configuration of a side (book, unit, choices, Combined copy,
    overrides, joined Hero); '' without a unit. Its start state is not
    part of it."""
    return "" if spec is None else repr((_unit_sig(spec.unit),
                                         _unit_sig(spec.hero)))


def spell_takedown(reg, sreg, book, key) -> bool:
    """Whether the damage spell 'key' of 'book' has Takedown."""
    sem = next((s for s in sreg.spells(book) if s.key == key), None) \
        if sreg is not None and book is not None and key else None
    return sem is not None and UL.rules_have_takedown(reg, sem.rules)


def info(reg, sreg, att, tgt, setup) -> Info:
    """Info of the attacker 'att' and the target 'tgt' (side_spec.SideSpec
    or None) under 'setup' (setup_model.Setup)."""
    names, takedown = (), False
    if att is not None:
        ru, hero = att.resolved()
        names = tuple(UL.weapon_names(ru, hero))
        if setup.attack == "spell":
            takedown = spell_takedown(reg, sreg, att.unit.cfg.book,
                                      setup.spell)
        else:
            takedown = UL.has_takedown(reg, ru, hero)
    labels, default = (), ()
    if tgt is not None:
        ru, hero = tgt.resolved()
        labels = tuple(UL.model_labels(ru, hero))
        default = default_takedown(ru, hero)
    return Info(names, labels, default, takedown and tgt is not None,
                bool(names) and setup.attack != "spell", signature(tgt))


def clean(orders: Orders, info_: Info) -> Orders:
    """Orders restricted to the current sides: weapon names the attacker
    has, target places that exist."""
    return Orders(tuple(n for n in orders.weapon_order if n in info_.names),
                  tuple(p for p in orders.takedown_targets
                        if p < len(info_.labels)))


def follow(orders: Orders, old: Info | None, new: Info) -> Orders:
    """Orders after the sides changed from 'old' to 'new': Takedown
    preferences reset when the target's configuration changed."""
    if old is None or old.target != new.target:
        orders = Orders(orders.weapon_order, ())
    return clean(orders, new)


def order_text(names) -> str:
    return " > ".join(names) if names else "book order"


def takedown_text(places) -> str:
    """1-based model numbers, as the dialogs show them (m1 = first
    model)."""
    return " > ".join(f"m{p + 1}" for p in places) if places \
        else "default (removed last first)"


def describe(orders: Orders, info_: Info) -> str:
    """One line under the buttons."""
    bits = [f"Weapon order: {order_text(orders.weapon_order)}"]
    if info_.takedown:
        bits.append(f"Takedown: {takedown_text(orders.takedown_targets)}")
    return "; ".join(bits)


def moved(order, place: int, delta: int) -> list[int]:
    """'order' with 'place' moved by 'delta' positions (clamped): the Up /
    Down of ui.order_dialog."""
    order = list(order)
    i = order.index(place)
    j = max(0, min(len(order) - 1, i + delta))
    order.insert(j, order.pop(i))
    return order
