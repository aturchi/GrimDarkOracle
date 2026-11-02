"""Local books: home-made units in user files, read like Army Forge books.

A local book is a JSON document with the SUBSET of the Army Forge schema
that af_book reads, so resolve(), the option
panel and the engine treat its units like official ones. It lives in
``books_local/<uid>.json``; every uid it creates (book, unit, package,
section, option, rule) starts with ``local-`` so it can never shadow an
Army Forge uid. Unit, package, section and option uids
are scoped by book (as in Army Forge); rule ids are GLOBAL in the rule
registry, so custom rules also carry the book uid: '<book uid>-r<n>'.

Rules: a unit, weapon or item refers to rules by id, as Army Forge does:
an official rule (core or any loaded book: its semantics apply) or a
custom rule of the local book. A custom rule may name an official rule as
``aliasedRuleId``: it then behaves exactly like it (the registry follows
alias chains), e.g. "Lucky Charm" = Fearless. A custom rule without alias
has no combat effect and shows as 'unmapped' in the coverage report, unless
the Rules Mapper gave it semantics of its own: they are stored in the rule
definition under SEM_KEY (a GrimDarkOracle field, ignored by af_book), so they
travel with the book, sessions included.

Pure module: builders return plain dicts in Army Forge form; save / load
do the file I/O (atomic write). Army Forge books are never written here.
"""
import json
import os
import re

from grimdarkoracle.data import af_book as ab

PREFIX = "local-"
FORMAT_VERSION = "local-1"          # versionString of a local book
GAME_SYSTEM = 2
SEM_KEY = "grimdarkoracle_semantics"     # custom rule semantics
RETIRED_KEY = "grimdarkoracle_retired"  # uids removed from the book
# The same keys before the rename of the program.
LEGACY_KEYS = {"grimoracle_semantics": SEM_KEY,
               "grimoracle_retired": RETIRED_KEY}
_KIND = {"unit": "u", "package": "p", "section": "s", "option": "o",
         "rule": "r"}


class LocalBookError(ValueError):
    """A local book that af_book cannot read, or a bad edit."""


def migrate(raw: dict) -> dict:
    """'raw' with the keys written before the rename (LEGACY_KEYS) renamed
    in place: the book-level retired ids and each rule's semantics."""
    for d in [raw] + list(raw.get("specialRules", [])):
        for old, new in LEGACY_KEYS.items():
            if old in d:
                d.setdefault(new, d.pop(old))
    return raw


def is_local(uid: str) -> bool:
    return isinstance(uid, str) and uid.startswith(PREFIX)


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "book"


# --- builders ----------------------------------------------------------------

def new_book(name: str, uid: str | None = None) -> dict:
    """An empty local book (uid 'local-<slug of name>' by default)."""
    uid = uid or PREFIX + slug(name)
    if not is_local(uid):
        raise LocalBookError(f"local book uid must start with {PREFIX!r}")
    return {"uid": uid, "name": name, "versionString": FORMAT_VERSION,
            "gameSystemId": GAME_SYSTEM, "factionName": name,
            "factionRelation": None, "units": [], "upgradePackages": [],
            "specialRules": [], "spells": []}


def _stem(raw: dict, kind: str) -> str:
    # Rule ids are global (registry): they carry the book uid.
    return f"{raw['uid']}-r" if kind == "rule" else PREFIX + _KIND[kind]


def next_id(raw: dict, kind: str, reserved=()) -> str:
    """First free id of a kind in the book: 'local-u<n>', 'local-p<n>',
    'local-s<n>', 'local-o<n>'; custom rules '<book uid>-r<n>'. 'reserved'
    = ids that must not be reused (removed ones lists may still name)."""
    used = set(_ids(raw)) | set(reserved) | set(raw.get(RETIRED_KEY, ()))
    stem = _stem(raw, kind)
    n = 1
    while f"{stem}{n}" in used:
        n += 1
    return f"{stem}{n}"


def retire(raw: dict, ids) -> None:
    """Remember removed uids so they are never given to something else: a
    saved list naming one must report it missing, not link elsewhere."""
    old = raw.setdefault(RETIRED_KEY, [])
    old.extend(i for i in ids if i and i not in old)


def _ids(raw):
    for u in raw.get("units", []):
        yield u["id"]
    for r in raw.get("specialRules", []):
        yield r["id"]
    for p in raw.get("upgradePackages", []):
        yield p["uid"]
        for s in p.get("sections", []):
            yield s["uid"]
            for o in s.get("options", []):
                yield o["uid"]


def rule_ref(rule_id: str, name: str, rating=None) -> dict:
    """A rule as attached to a unit, weapon or item."""
    label = name if rating is None else f"{name}({rating})"
    return {"type": "ArmyBookRule", "id": rule_id, "name": name,
            "rating": rating, "label": label}


def weapon_label(name: str, rng: int, attacks: int, rules=()) -> str:
    """Army Forge label: 'Rifle (24", A1, AP(1))', melee without range."""
    bits = ([f'{rng}"'] if rng else []) + [f"A{attacks}"] + \
        [r["label"] for r in rules]
    return f"{name} ({', '.join(bits)})"


def weapon(name: str, rng: int, attacks: int, rules=(), count: int = 1
           ) -> dict:
    """An ArmyBookWeapon (range 0 = melee)."""
    if rng < 0 or attacks < 1 or count < 1:
        raise LocalBookError(f"{name}: range >= 0, attacks and count >= 1")
    label = weapon_label(name, rng, attacks, rules)
    return {"type": "ArmyBookWeapon", "name": name, "count": count,
            "range": rng, "attacks": attacks, "specialRules": list(rules),
            "label": (f"{count}x " if count > 1 else "") + label}


def item(name: str, rules=(), weapons=(), count: int = 1) -> dict:
    """An ArmyBookItem: equipment with rules and / or weapons."""
    content = list(rules) + list(weapons)
    inner = ", ".join(c["label"] for c in content)
    return {"type": "ArmyBookItem", "name": name, "count": count,
            "content": content, "label": f"{name} ({inner})" if inner
            else name}


def unit(raw: dict, name: str, size: int, quality: int, defense: int,
         cost: int, rules=(), weapons=(), items=(), uid: str | None = None
         ) -> dict:
    """A unit dict with a fresh 'local-' id (not yet added)."""
    if size < 1 or not 2 <= quality <= 6 or not 2 <= defense <= 6 or cost < 0:
        raise LocalBookError(f"{name}: size >= 1, Quality / Defense 2-6, "
                             "cost >= 0")
    return {"id": uid or next_id(raw, "unit"), "name": name, "size": size,
            "quality": quality, "defense": defense, "cost": cost,
            "rules": list(rules), "weapons": list(weapons),
            "items": list(items), "upgrades": [], "disabledSections": []}


def custom_rule(raw: dict, name: str, description: str,
                alias_of: str | None = None, has_rating: bool = False) -> dict:
    """A custom rule definition (added to the book's specialRules)."""
    d = {"id": next_id(raw, "rule"), "name": name, "description": description,
         "hasRating": has_rating, "aliasedRuleId": alias_of,
         "originalName": None, "coreType": None}
    raw["specialRules"].append(d)
    return d


def find_rule(raw: dict, rule_id: str) -> dict:
    r = next((r for r in raw["specialRules"] if r["id"] == rule_id), None)
    if r is None:
        raise LocalBookError(f"no custom rule {rule_id!r} in {raw['name']}")
    return r


def set_semantics(raw: dict, rule_id: str, entry: dict) -> dict:
    """Store a semantics entry (rules.mapper) in a custom rule, hashed
    against its current text, so a later text edit shows as 'changed'."""
    from grimdarkoracle.rules.registry import text_sha1
    r = find_rule(raw, rule_id)
    if r.get("aliasedRuleId"):
        raise LocalBookError(f"{r['name']}: an aliased rule takes the "
                             "semantics of its alias")
    e = dict(entry, name=r["name"], text_sha1=text_sha1(r["description"]))
    r[SEM_KEY] = e
    return e


def clear_semantics(raw: dict, rule_id: str) -> None:
    find_rule(raw, rule_id).pop(SEM_KEY, None)


def semantics_of(raw: dict) -> dict:
    """{rule id: semantics entry} of the custom rules that have one."""
    return {r["id"]: r[SEM_KEY] for r in raw.get("specialRules", [])
            if r.get(SEM_KEY)}


def option(label: str, gains, costs: dict) -> dict:
    """An option; costs = {unit id: points} for every unit of the package."""
    return {"uid": "", "label": label, "gains": list(gains),
            "costs": [{"unitId": k, "cost": v} for k, v in costs.items()]}


def section(label: str, variant: str, options, targets=(), model=False,
            affects=None, select=None) -> dict:
    """A section; affects / select = ('exactly', n) | ('up to', n) |
    ('any',) | ('all',) or None, as in Army Forge."""
    if variant not in ab.VARIANTS:
        raise LocalBookError(f"variant must be one of {ab.VARIANTS}")

    def q(x):
        if x is None:
            return None
        if x[0] not in ab.QUANT_KINDS:
            raise LocalBookError(f"quantifier must be one of {ab.QUANT_KINDS}")
        return {"type": x[0], **({"value": x[1]} if len(x) > 1 else {})}
    return {"uid": "", "label": label, "variant": variant, "model": model,
            "affects": q(affects), "select": q(select),
            "targets": list(targets), "options": list(options)}


# --- edits -------------------------------------------------------------------

def find_unit(raw: dict, unit_id: str) -> dict:
    u = next((u for u in raw["units"] if u["id"] == unit_id), None)
    if u is None:
        raise LocalBookError(f"no unit {unit_id!r} in {raw['name']}")
    return u


def put_unit(raw: dict, u: dict) -> str:
    """Add the unit, or replace the one with its id; returns the id."""
    if not is_local(u["id"]):
        raise LocalBookError("local unit ids start with " + PREFIX)
    for i, old in enumerate(raw["units"]):
        if old["id"] == u["id"]:
            raw["units"][i] = dict(u, upgrades=old["upgrades"])
            return u["id"]
    raw["units"].append(u)
    return u["id"]


def remove_unit(raw: dict, unit_id: str) -> None:
    """Remove a unit; its packages stay if another unit uses them. Lists
    that use the unit will show it as missing (never pruned)."""
    u = find_unit(raw, unit_id)
    raw["units"].remove(u)
    used = {p for x in raw["units"] for p in x["upgrades"]}
    gone = [p for p in raw["upgradePackages"] if p["uid"] not in used]
    retire(raw, [unit_id] + [i for p in gone for i in _pkg_ids(p)])
    raw["upgradePackages"] = [p for p in raw["upgradePackages"]
                              if p["uid"] in used]


def _pkg_ids(p) -> list:
    return [p["uid"]] + [x for s in p["sections"]
                         for x in [s["uid"]] +
                         [o["uid"] for o in s["options"]]]


def add_package(raw: dict, unit_ids, sections, hint: str = "") -> str:
    """A package of 'sections' given to 'unit_ids' (fresh uids for the
    package, its sections and options); every option must price every
    unit of the package. Returns the package uid."""
    pu = next_id(raw, "package")
    pkg = {"uid": pu, "hint": hint, "sections": []}
    raw["upgradePackages"].append(pkg)          # so next_id sees its uids
    for src in sections:
        sec = dict(src, uid=next_id(raw, "section"), options=[])
        pkg["sections"].append(sec)
        for o in src["options"]:
            missing = set(unit_ids) - {c["unitId"] for c in o["costs"]}
            if missing:
                raw["upgradePackages"].remove(pkg)
                raise LocalBookError(f"option {o['label']!r} has no price "
                                     f"for {sorted(missing)}")
            sec["options"].append(dict(o, uid=next_id(raw, "option")))
    for uid in unit_ids:
        find_unit(raw, uid)["upgrades"].append(pu)
    return pu


# --- checks and files --------------------------------------------------------

def check(raw: dict, known_rules=()) -> list[str]:
    """Problems of a local book: unreadable by af_book (raised), non-local
    uids, duplicate ids, rule ids that are neither in the book nor in
    'known_rules' (ids of the loaded core and books)."""
    try:
        book = ab.parse_book(raw)
    except (ab.BookFormatError, KeyError, TypeError) as exc:
        raise LocalBookError(f"not readable as an army book: {exc}") from exc
    out = list(book.warnings)
    ids = list(_ids(raw)) + [raw.get("uid", "")]
    out += [f"uid {i!r} does not start with {PREFIX!r}"
            for i in ids if not is_local(i)]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    out += [f"duplicate uid {i!r}" for i in dup]
    out += [f"custom rule id {r['id']!r} must start with "
            f"{raw.get('uid', '')!r}-" for r in raw.get("specialRules", [])
            if not str(r.get("id", "")).startswith(f"{raw.get('uid', '')}-")]
    known = set(known_rules) | set(book.rules)
    units = book.units.values()
    refs = [r for u in units for r in u.rules] + \
        [r for u in units for w in u.weapons for r in w.rules] + \
        [r for u in units for it in u.items for r in it.rules]
    for p in book.packages.values():
        for s in p.sections:
            for o in s.options:
                for g in o.gains:
                    refs += list(g.rules)
                    refs += [r for w in getattr(g, "weapons", ())
                             for r in w.rules]
    out += sorted({f"rule {r.name!r} ({r.id}) is not defined"
                   for r in refs if r.id not in known})
    for d in book.rules.values():
        if d.aliased_rule_id and d.aliased_rule_id not in known:
            out.append(f"rule {d.name!r}: alias {d.aliased_rule_id!r} "
                       "is not defined")
    return out


def path_for(folder: str, uid: str) -> str:
    return os.path.join(folder, f"{uid}.json")


def save(raw: dict, folder: str) -> str:
    """Atomic write of a local book into 'folder'; returns the path."""
    if not is_local(raw.get("uid", "")):
        raise LocalBookError("only local books can be saved here")
    ab.parse_book(raw)                          # never write unreadable data
    os.makedirs(folder, exist_ok=True)
    path = path_for(folder, raw["uid"])
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def delete(folder: str, uid: str) -> None:
    if not is_local(uid):
        raise LocalBookError("only local books can be deleted")
    os.remove(path_for(folder, uid))


def rename_rule(raw: dict, rule_id: str, name: str) -> None:
    """Rename a custom rule and every reference to it in the book."""
    find_rule(raw, rule_id)["name"] = name

    def walk(x):
        if isinstance(x, list):
            for v in x:
                walk(v)
            return
        if not isinstance(x, dict):
            return
        if x.get("type") == "ArmyBookRule" and x.get("id") == rule_id:
            r = x.get("rating")
            x["name"] = name
            x["label"] = name if r is None else f"{name}({r})"
        for v in x.values():
            walk(v)
        # Labels that show the rule: rebuilt after their parts.
        if x.get("type") == "ArmyBookWeapon":
            n = x.get("count", 1)
            x["label"] = (f"{n}x " if n > 1 else "") + weapon_label(
                x["name"], x["range"], x["attacks"], x["specialRules"])
        elif x.get("type") == "ArmyBookItem":
            x["label"] = item(x["name"], (), (), x.get("count", 1))["label"] \
                if not x["content"] else \
                f"{x['name']} ({', '.join(c['label'] for c in x['content'])})"
        elif "gains" in x and "costs" in x:
            x["label"] = "; ".join(g["label"] for g in x["gains"])
    walk(raw["units"])
    walk(raw["upgradePackages"])


def rule_used(raw: dict, rule_id: str) -> bool:
    """Whether a unit, weapon, item or option of the book refers to it."""
    return f'"id": "{rule_id}"' in json.dumps(
        [raw["units"], raw["upgradePackages"]])


# --- accessors (the other modules never name Army Forge fields) --------------

def rules_of(raw: dict) -> list:
    """The custom rule definitions of a book (in place)."""
    return raw.setdefault("specialRules", [])


def packages_of(raw: dict) -> list:
    """The upgrade packages of a book (in place)."""
    return raw.setdefault("upgradePackages", [])


def alias_of(rule: dict) -> str | None:
    return rule.get("aliasedRuleId") or None


def edit_rule(raw: dict, rule_id: str, description: str,
              alias_of_id: str | None) -> None:
    """New text and alias of a custom rule; an alias drops its own
    semantics (the alias decides)."""
    r = find_rule(raw, rule_id)
    r["description"], r["aliasedRuleId"] = description, alias_of_id
    if alias_of_id:
        r.pop(SEM_KEY, None)


def delete_rule(raw: dict, rule_id: str) -> None:
    """Remove an unused custom rule (its id is retired)."""
    if rule_used(raw, rule_id):
        raise LocalBookError("the rule is used by a unit or an option")
    find_rule(raw, rule_id)
    raw["specialRules"] = [r for r in raw["specialRules"]
                           if r["id"] != rule_id]
    retire(raw, [rule_id])
