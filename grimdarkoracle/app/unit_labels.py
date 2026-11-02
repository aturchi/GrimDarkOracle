"""Names and labels of a resolved unit with its joined Hero, for the
Analyzer. Pure.

- weapon_names: the distinct weapon names a weapon order lists;
- model_labels: one label per Combatant place (the host's models in
  order, then the joined Hero), for Takedown preferences and removal
  orders;
- has_takedown / rules_have_takedown: whether a unit's weapons (or a
  spell's rules) carry Takedown, resolved through the rule registry.
"""
from grimdarkoracle.app.unit_sheet import loadout


def weapon_names(unit, hero=None) -> list[str]:
    """Distinct weapon names of the unit and its Hero, first-seen order."""
    out = []
    for ru in (unit, hero):
        for w, _n in (ru.weapons() if ru else ()):
            if w.name not in out:
                out.append(w.name)
    return out


def model_labels(unit, hero=None) -> list[str]:
    """One label per Combatant place: loadout, Tough, joined Hero."""
    out = []
    for ru, is_hero in ((unit, False), (hero, True)):
        if ru is None:
            continue
        for m in ru.models:
            bits = [loadout(m)]
            if m.tough:
                bits.append(f"Tough({m.tough})")
            out.append((f"{ru.name}: " if is_hero else "") + ", ".join(bits))
    return out


def rules_have_takedown(reg, rules) -> bool:
    """Whether any RuleRef of 'rules' maps to the Takedown handler."""
    return any((s := reg.lookup(r.id, r.name)) is not None
               and s.handler == "takedown" for r in rules)


def has_takedown(reg, unit, hero=None) -> bool:
    """Whether a weapon of the unit or of its Hero carries Takedown."""
    return any(rules_have_takedown(reg, w.rules)
               for ru in (unit, hero) if ru for w, _n in ru.weapons())
