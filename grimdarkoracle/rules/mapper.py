"""Rules Mapper core: build, check and describe the semantics of a
CUSTOM rule (a rule written in a local book) from the primitives and
conditions of rules/vocab. Pure; the dialog edits plain dicts:

    e = mapper.entry(effects=[mapper.effect("hit_mod", 1, scope="model")],
                     conditions={"attack": "shooting", "range_over": 12})
    mapper.check(e, reg)          # [] = valid
    mapper.describe(e, reg)       # lines for the preview
    local_books.set_semantics(raw, rule_id, e); lib.put_local(raw)

Custom rules may be 'composed' (effects under conditions),
'no_combat_effect', or BEHAVE AS an existing native rule: a
copy of its handler, parameters, effects and conditions, with the custom
rule's own name and rating (Terror(2) as Fear, Psyker(1) as Caster):

    e = mapper.native_entry(reg, fear_id)    # {"impl": "native:fear",
                                              #  "behaves_as": fear_id, ...}

Never other numbers: native handlers read some numbers
per game, not per rule (Fearless 4+, Impact 2+...), so a copy with other
numbers would change the original. On load, refresh_native() takes the
copy again from the current native rule when it exists (so the two never
disagree), else keeps the stored copy. Tough and Hero cannot be copied:
the data layer recognises them by name (wound capacity, joining), so a
renamed copy would do nothing; such a rule uses an alias. A custom
rule that IS an official rule with another name still uses an alias.
"""
from grimdarkoracle.rules import registry as RG
from grimdarkoracle.rules import vocab as V

IMPLS = ("composed", "no_combat_effect")
NATIVE = "behaves as"                   # the dialog's third kind
NAME_BOUND = ("tough", "hero")          # recognised by name
AS_KEY = "behaves_as"

# Help texts and preview phrases ({v} = the value).
PRIMITIVES = {
    "hit_mod": ("{v:+} to hit rolls", "modifier to the attack's hit rolls"),
    "defense_mod": ("{v:+} to Defense rolls", "modifier to the block rolls"),
    "defense_set": ("counts as Defense {v}+", "Armor-like: a new Defense"),
    "ap_mod": ("AP {v:+}", "AP added to the weapons (negative: Fortified)"),
    "range_mod": ('{v:+}" range', "inches added to the weapons' range"),
    "quality_set": ("attacks at Quality {v}+", "Reliable-like"),
    "extra_hit_on_6": ("+{v} hit(s) on an unmodified 6 to hit", "Surge-like"),
    "ap_on_6": ("AP +{v} on hits from an unmodified 6", "Rending-like"),
    "extra_wound_on_def_1": ("+{v} wound(s) on an unmodified Defense 1",
                             "Shred-like"),
    "reroll_defense_6": ("the target re-rolls unmodified Defense 6",
                         "Bane-like"),
    "ignore_regen": ("ignores Regeneration", ""),
    "ignore_cover": ("ignores Cover", ""),
    "ignore_negative_mods": ("ignores negative modifiers not from its own "
                             "rules", "Unstoppable-like"),
    "ignore_defense_bonus": ("ignores the target's positive Defense "
                             "modifiers", "Pierce-like"),
    "range_floor": ('range reductions stop at {v}"',
                    "with a negative range_mod (Ranged Shrouding)"),
    "scourge": ("each unmodified block 1 counts {v} extra wounds",
                "melee result, shooting Morale"),
    "morale_mod": ("{v:+} to Morale Test rolls", ""),
    "cast_mod": ("{v:+} to casting rolls", ""),
    "grant_rule": ("gives {v}", "an aura or a buff: the rule given"),
    "reroll_defense_on": ("the target re-rolls successful unmodified "
                          "Defense {v}+", "Obliterate-like"),
    "extra_attack_on": ("an unmodified {v}+ that hits rolls one new attack",
                        "Predator-like"),
    "lift_distance": ("{v} acts at any distance",
                      "lifts its over 9\"/6\" conditions (Enhanced ...)"),
}
SIDES = {"attacker": "on its own attacks",
         "defender": "on attacks against its unit"}
SCOPES = {None: "", "weapon": "this weapon", "model": "this model only",
          "unit": "this model and its unit"}
CONDITIONS = {
    "attack": "attack {v}", "action": "using {v} actions",
    "charging": "when charging", "charged": "when charged",
    "range_over": 'target over {v}"', "range_within": 'target within {v}"',
    "target_tough_min": "most target models Tough({v}) or more",
    "target_defense_min": "most target models Defense {v}+ or worse",
    "target_defense_max": "most target models Defense {v}+ or better",
    "target_in_cover": "target in cover", "most_models": "most models have it",
    "not_moved": "has not moved this round", "not_fatigued": "not Fatigued",
    "morale_from": "Morale Test after {v}",
    "morale_from_combat": "Morale Test after shooting or melee",
    "has_rule": "the model also has {v}",
    "range_over_half": "target over half the weapon's range",
    "charge_over": 'a charge from over {v}"',
    "ambushed_this_round": "deployed via Ambush this round",
    "most_have_rule": "most models of the unit have {v}",
    "target_shaken_or_fatigued": "the target is Shaken or Fatigued",
    "target_over_half": "the target above half its size or Tough",
    "near_terrain": 'most models within 1" of terrain',
    "target_near_terrain": 'the target within 1" of terrain',
}
assert set(PRIMITIVES) == set(V.PRIMITIVES) and set(CONDITIONS) == \
    set(V.CONDITIONS)


def effect(primitive: str, value, side: str = "attacker", scope=None,
           conditions: dict | None = None) -> dict:
    out = {"primitive": primitive, "value": value}
    if side != "attacker":
        out["side"] = side
    if scope is not None:
        out["scope"] = scope
    if conditions:
        out["conditions"] = dict(conditions)
    return out


def entry(impl: str = "composed", effects=(), conditions: dict | None = None,
          note: str = "") -> dict:
    """A semantics entry without name / text hash (local_books adds them)."""
    out = {"impl": impl, "effects": [dict(e) for e in effects]}
    if conditions:
        out["conditions"] = dict(conditions)
    if note:
        out["note"] = note
    return out


def natives(reg) -> dict[str, str]:
    """Name -> entry id of the native rules a custom rule may behave as:
    official entries (not custom, not spells) whose handler is not
    recognised by name; the first id wins for a repeated name."""
    out: dict = {}
    for rid, sem in sorted(reg.entries.items()):
        if sem.handler and sem.handler not in NAME_BOUND and \
                not rid.startswith("spell:") and not _custom(rid):
            out.setdefault(sem.name, rid)
    return dict(sorted(out.items()))


def _custom(rid: str) -> bool:
    from grimdarkoracle.data.local_books import is_local
    return is_local(rid)


def _copy(sem) -> dict:
    """The parts of a native entry a custom rule copies."""
    out = {"impl": sem.impl}
    if sem.params:
        out["params"] = {k: list(v) if isinstance(v, tuple) else v
                         for k, v in sem.params}
    if sem.effects:
        out["effects"] = [_effect_dict(x) for x in sem.effects]
    if sem.conditions:
        out["conditions"] = dict(sem.conditions)
    return out


def _effect_dict(x) -> dict:
    out = {"primitive": x.primitive, "value": x.value}
    if x.side != "attacker":
        out["side"] = x.side
    if x.scope is not None:
        out["scope"] = x.scope
    if x.conditions:
        out["conditions"] = dict(x.conditions)
    return out


def native_entry(reg, as_id: str, note: str = "") -> dict:
    """A custom-rule entry that behaves as the native rule 'as_id'."""
    sem = reg.entries.get(as_id)
    if sem is None or not sem.handler:
        raise ValueError(f"{as_id!r} is not a native rule")
    out = dict(_copy(sem), **{AS_KEY: as_id})
    if note:
        out["note"] = note
    return out


def refresh_native(e: dict, reg) -> dict:
    """A stored 'behaves as' entry with the CURRENT copy of its native
    rule when the registry has it (same handler), else unchanged."""
    sem = reg.entries.get(e.get(AS_KEY)) if isinstance(e, dict) else None
    if sem is None or sem.impl != e.get("impl"):
        return e
    keep = {k: v for k, v in e.items()
            if k in ("name", "text_sha1", "note", AS_KEY)}
    return dict(_copy(sem), **keep)


def _check_native(e: dict, reg) -> list[str]:
    handler = e["impl"][len(V.NATIVE_PREFIX):]
    if handler in NAME_BOUND:
        return [f"{handler.title()} is recognised by its name: use an "
                "alias of the official rule instead"]
    as_id = e.get(AS_KEY)
    sem = reg.entries.get(as_id) if as_id else None
    if sem is None:
        return ["behaves as: no such native rule"
                + (f" ({as_id})" if as_id else "")]
    if _custom(as_id) or as_id.startswith("spell:") or \
            sem.handler in NAME_BOUND or not sem.handler:
        return [f"{sem.name} cannot be copied"]
    want = _copy(sem)
    got = {k: e[k] for k in ("impl", "params", "effects", "conditions")
           if k in e and e[k] not in ({}, [])}
    if got != want:
        return [f"a copy of {sem.name} must keep its handler and numbers "
                "(no other parameters, effects or conditions)"]
    return []


def check(e: dict, reg, rule_id: str = "rule") -> list[str]:
    """Why an entry is not usable (empty = valid): the registry checks
    plus the custom-rule limits."""
    errors = []
    native = str(e.get("impl", "")).startswith(V.NATIVE_PREFIX)
    if native:
        errors += _check_native(e, reg)
    elif e.get("impl") not in IMPLS:
        errors.append(f"impl must be one of {IMPLS} or a native copy for "
                      "a custom rule")
    if e.get("impl") == "no_combat_effect" and e.get("effects"):
        errors.append("no_combat_effect takes no effects")
    full = dict(e, name=e.get("name", rule_id),
                text_sha1=e.get("text_sha1", "0" * 40))
    doc = {"format": V.FORMAT, "rules": {rule_id: full}}
    errors += [x.split(": ", 1)[-1] if x.startswith(rule_id) else x
               for x in RG.validate(doc, known=reg.entries)]
    return errors


def _rule_name(reg, rid) -> str:
    sem = reg.lookup(rid) if rid else None
    return sem.name if sem else str(rid)


def _value(prim, v, reg) -> str:
    if prim in V.STRUCTURAL:
        return _rule_name(reg, v.get("rule") if isinstance(v, dict) else v)
    return "X (the rating)" if v == "X" else v


def _phrase(prim, v, reg) -> str:
    fmt = PRIMITIVES[prim][0]
    val = _value(prim, v, reg)
    if isinstance(val, int) and not isinstance(val, bool):
        return fmt.format(v=val)
    return fmt.replace("{v:+}", "{v}").format(v=val)


def _conds(conds: dict, reg) -> list[str]:
    out = []
    for k, v in conds.items():
        text = CONDITIONS.get(k, k)
        if k in ("has_rule", "most_have_rule"):
            v = _rule_name(reg, v)
        if isinstance(v, bool):
            out.append(text if v else f"not ({text})")
        else:
            out.append(text.format(v=v.title() if isinstance(v, str) and
                                   k not in ("has_rule", "most_have_rule")
                                   else v))
    return out


def describe(e: dict, reg) -> list[str]:
    """Readable lines of an entry, for the Mapper preview."""
    if e.get("impl") == "no_combat_effect":
        return ["no combat effect"]
    if str(e.get("impl", "")).startswith(V.NATIVE_PREFIX):
        sem = reg.entries.get(e.get(AS_KEY))
        name = sem.name if sem else e.get(AS_KEY, "?")
        out = [f"behaves as {name} (engine rule "
               f"'{e['impl'][len(V.NATIVE_PREFIX):]}'), with this rule's "
               "own name and rating"]
        out += [f"- {k}: {v}" for k, v in sorted(e.get("params", {}).items())]
        rest = describe({k: v for k, v in e.items()
                         if k in ("effects", "conditions")}, reg) \
            if e.get("effects") else []
        return out + rest
    head = _conds(e.get("conditions", {}), reg)
    out = ["when " + " and ".join(head)] if head else []
    for x in e.get("effects", []):
        if x.get("primitive") not in PRIMITIVES:
            out.append(f"? {x.get('primitive')}")
            continue
        side = "" if x["primitive"] in V.STRUCTURAL else \
            SIDES.get(x.get("side", "attacker"), "")   # the given rule says
        bits = [_phrase(x["primitive"], x.get("value"), reg), side]
        scope = SCOPES.get(x.get("scope"), "")
        if scope:
            bits.append(f"({scope})")
        c = _conds(x.get("conditions", {}), reg)
        if c:
            bits.append("if " + " and ".join(c))
        out.append("- " + " ".join(b for b in bits if b))
    return out


# --- text forms used by the dialog ----------------------------------------------------

def entry_names(reg) -> dict[str, str]:
    """Rule name -> entry id of every rule with semantics (grant targets,
    has_rule); the first id wins for a repeated name."""
    out: dict = {}
    for rid, sem in sorted(reg.entries.items()):
        if not rid.startswith("spell:"):
            out.setdefault(sem.name, rid)
    return out


def _typed(kind, text: str, reg, what: str):
    """(value, error) of a text for a vocab type."""
    t = text.strip()
    if kind == V.INT:
        if t.upper() == "X":
            return "X", None
        try:
            return int(t), None
        except ValueError:
            return None, f"{what}: a whole number or X expected, got {t!r}"
    if kind == V.BOOL:
        if t.lower() in ("", "yes", "true", "1"):
            return True, None
        if t.lower() in ("no", "false", "0"):
            return False, None
        return None, f"{what}: yes / no expected, got {t!r}"
    if kind in (V.RULE, V.ID):
        rid = entry_names(reg).get(t)
        if rid is None:
            return None, f"{what}: no rule with semantics named {t!r}"
        return ({"rule": rid} if kind == V.RULE else rid), None
    low = t.lower()
    if low not in kind:
        return None, f"{what}: one of {', '.join(kind)} expected, got {t!r}"
    return low, None


def parse_value(primitive: str, text: str, reg):
    """(value, error) of an effect value typed in the dialog."""
    if primitive not in V.PRIMITIVES:
        return None, f"unknown primitive {primitive!r}"
    return _typed(V.PRIMITIVES[primitive], text, reg, primitive)


def value_text(primitive: str, value, reg) -> str:
    if isinstance(value, dict):
        return _rule_name(reg, value.get("rule"))
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def parse_conditions(text: str, reg) -> tuple[dict, list[str]]:
    """'attack=shooting, range_over=12, charging' -> ({...}, errors); a
    bare key means yes; rule names for has_rule."""
    out, errors = {}, []
    for part in (p.strip() for p in text.split(",")):
        if not part:
            continue
        key, _, val = part.partition("=")
        key = key.strip()
        if key not in V.CONDITIONS:
            errors.append(f"unknown condition {key!r}")
            continue
        v, err = _typed(V.CONDITIONS[key], val, reg, key)
        if err:
            errors.append(err)
        else:
            out[key] = v
    return out, errors


def conditions_text(conds: dict, reg) -> str:
    parts = []
    for k, v in conds.items():
        if v is True:
            parts.append(k)
        elif k == "has_rule":
            parts.append(f"{k}={_rule_name(reg, v)}")
        else:
            parts.append(f"{k}={value_text(k, v, reg)}")
    return ", ".join(parts)
