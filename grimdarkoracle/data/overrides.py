"""Overrides: house rules, errata and proxies applied AFTER resolve().

Stored apart from the choices, so a book update still propagates to
everything the user did not patch. Each override is a small dict:

    {"op": "set", "path": "quality" | "defense" | "points" | "name",
     "value": ...}
    {"op": "add_rule", "rule": {"id": ..., "name": ..., "rating": ...}}
    {"op": "remove_rule", "name": "Fearless"}
    {"op": "weapon_set", "weapon": "Rifle", "field": "attacks" | "range",
     "value": 2}
    {"op": "weapon_add_rule", "weapon": "Rifle", "rule": {...}}
    {"op": "weapon_remove_rule", "weapon": "Rifle", "name": "AP"}

Rules are added to / removed from every model; weapons are matched by
name on every model. An override that matches nothing, or an unknown op,
is reported in the unit's issues and otherwise ignored.
"""
from dataclasses import replace

from grimdarkoracle.data import rule_weapons
from grimdarkoracle.data.af_book import RuleRef
from grimdarkoracle.data.options_core import same_name

SET_PATHS = ("quality", "defense", "points", "name")
WEAPON_FIELDS = ("attacks", "range")


def _rule(d: dict) -> RuleRef:
    rating = d.get("rating")
    label = d.get("label") or (d["name"] if rating is None
                               else f"{d['name']}({rating})")
    return RuleRef(d.get("id", ""), d["name"], rating, label)


def _map_weapons(models, name, fn):
    """Apply fn to every weapon named 'name'; returns (models, hits)."""
    hits, out = 0, []
    for m in models:
        weapons = []
        for w, n in m.weapons:
            if same_name(w.name, name):
                w, hits = fn(w), hits + 1
            weapons.append((w, n))
        out.append(replace(m, weapons=tuple(weapons)))
    return tuple(out), hits


def _map_rules(models, fn):
    return tuple(replace(m, rules=tuple(fn(m.rules))) for m in models)


def _apply_one(ru, ov: dict):
    """(new unit, error message or None)."""
    op = ov.get("op")
    if op == "set":
        path = ov.get("path")
        if path not in SET_PATHS:
            return ru, f"override: cannot set {path!r}"
        return replace(ru, **{path: ov.get("value")}), None
    if op == "add_rule":
        rule = _rule(ov["rule"])
        return replace(ru, models=_map_rules(
            ru.models, lambda rs: list(rs) + [rule])), None
    if op == "remove_rule":
        name = ov.get("name", "")
        if not any(r.name == name for m in ru.models for r in m.rules):
            return ru, f"override: no rule {name!r} to remove"
        return replace(ru, models=_map_rules(
            ru.models, lambda rs: [r for r in rs if r.name != name])), None
    if op in ("weapon_set", "weapon_add_rule", "weapon_remove_rule"):
        if op == "weapon_set":
            fld = ov.get("field")
            if fld not in WEAPON_FIELDS:
                return ru, f"override: cannot set weapon field {fld!r}"
            fn = lambda w: replace(w, **{fld: ov.get("value")})  # noqa: E731
        elif op == "weapon_add_rule":
            rule = _rule(ov["rule"])
            fn = lambda w: replace(w, rules=w.rules + (rule,))   # noqa: E731
        else:
            name = ov.get("name", "")
            fn = lambda w: replace(                               # noqa: E731
                w, rules=tuple(r for r in w.rules if r.name != name))
        models, hits = _map_weapons(ru.models, ov.get("weapon", ""), fn)
        if not hits:
            return ru, f"override: no weapon {ov.get('weapon')!r}"
        return replace(ru, models=models), None
    return ru, f"override: unknown op {op!r}"


def apply(ru, overrides):
    """ResolvedUnit with 'overrides' applied, in order; 'modified' is set
    when at least one override took effect."""
    if not overrides:
        return ru
    issues, applied = list(ru.issues), 0
    for ov in overrides:
        try:
            ru, err = _apply_one(ru, ov)
        except (KeyError, TypeError) as exc:
            err = f"override {ov!r} malformed ({exc})"
        if err:
            issues.append(err)
        else:
            applied += 1
    ru = rule_weapons.add_all(ru)       # a rule added by an override
    return replace(ru, issues=tuple(issues), modified=ru.modified or
                   applied > 0)
