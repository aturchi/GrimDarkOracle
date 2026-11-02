"""Spell semantics: what each book spell
does in an attack, keyed by spell id AND the hash of its effect text, so
a spell whose text changes in Army Forge stops matching and shows up in
the coverage report. Same id with different texts exists
across books (30 ids), hence the composite key.

spells.json (grimdarkoracle-spells/1), entries keyed "<id>:<sha1[:10]>":

- kind "damage": the target takes 'hits' fixed hits (no roll, no 6s,
  Blast applies) carrying 'rules' ([name, rating] pairs, e.g.
  ["AP", 1], ["Bane", null]; "as if a unit of [1]" = Takedown); 'range'
  is the spell's range (Smash reads it); 'roll_sixes' (Storm of Power):
  each fixed hit rolls one die, a 6 makes it a six-hit;
- kind "mark": 'effects' / 'conditions' in the rules schema (rule ids),
  applied to friendly attacks against the target, like the Mark rules;
- kind "grant": 'grants' [{rule (name), to: models | weapons, attack}]
  ("<name>#effect": the own effects of that buff / debuff rule),
  kind "debuff": the same 'grants' given to an ENEMY unit,
  rules given to the friendly unit (on its models or on its weapons,
  optionally only for one attack type);
- kind "no_combat_effect".

Rule names resolve in the spell's book first for book rules, core first
for core rules (AP, Bane... keep their core ids, as weapons do).
"""
import json
import os
from dataclasses import dataclass

from grimdarkoracle import app_paths
from grimdarkoracle.data.af_book import RuleRef
from grimdarkoracle.rules.registry import _semantic, text_sha1
from grimdarkoracle.rules.vocab import EFFECT_SUFFIX

FORMAT = "grimdarkoracle-spells/1"
LEGACY_FORMATS = ("grimoracle-spells/1",)   # before the rename
KINDS = ("damage", "mark", "grant", "debuff", "no_combat_effect")
RESOURCE = os.path.join("rules", "spells.json")
PREFIX = "spell:"                   # registry ids of spell marks


def spell_key(spell) -> str:
    return f"{spell.id}:{text_sha1(spell.effect)[:10]}"


def load(path: str | None = None) -> dict:
    """spells.json: 'path', else the user's copy next to the program, else
    the shipped one (same rule as registry.load_semantics). Raises
    ValueError if invalid."""
    candidates = [path] if path else app_paths.resource(RESOURCE)
    for p in candidates:
        if p and os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                doc = json.load(fh)
            errors = validate(doc)
            if errors:
                raise ValueError(f"{p}: " + "; ".join(errors[:5]))
            return doc
    raise FileNotFoundError(f"no {RESOURCE} in {candidates}")


def validate(doc: dict) -> list[str]:
    errors = []
    if doc.get("format") not in (FORMAT,) + LEGACY_FORMATS:
        return [f"format must be {FORMAT!r}"]
    for key, e in doc.get("spells", {}).items():
        where = f"{key} ({e.get('name', '?')})"
        kind = e.get("kind")
        if kind not in KINDS:
            errors.append(f"{where}: unknown kind {kind!r}")
        if kind == "damage" and not (isinstance(e.get("hits"), int)
                                     and e["hits"] > 0):
            errors.append(f"{where}: 'hits' must be a positive integer")
        if kind == "damage" and not isinstance(e.get("range"), int):
            errors.append(f"{where}: 'range' must be an integer")
        if not isinstance(e.get("roll_sixes", False), bool) or (
                e.get("roll_sixes") and kind != "damage"):
            errors.append(f"{where}: 'roll_sixes' is a damage spell flag")
        if kind in ("grant", "debuff"):
            for g in e.get("grants", []):
                if g.get("to", "models") not in ("models", "weapons"):
                    errors.append(f"{where}: grant 'to' must be models or "
                                  "weapons")
        if kind == "mark" and not e.get("effects"):
            errors.append(f"{where}: a mark needs effects")
    return errors


@dataclass(frozen=True)
class SpellSem:
    key: str
    name: str
    kind: str
    threshold: int
    effect: str                     # the book's text
    hits: int = 0
    range: int = 0
    rules: tuple[RuleRef, ...] = ()             # damage
    # (rule, to, attack) of each grant
    grants: tuple[tuple[RuleRef, str, str | None], ...] = ()
    roll_sixes: bool = False        # "roll as many dice as hits"

    @property
    def mark_id(self) -> str:
        return PREFIX + self.key


class SpellRegistry:
    """Spell semantics resolved against the loaded books; spell marks are
    added to the rule registry as native 'mark' entries (id 'spell:KEY')."""

    def __init__(self, doc: dict, reg, books=()):
        self.doc, self.reg = doc, reg
        self.entries = dict(doc.get("spells", {}))
        self._books = {b.uid: b for b in books}
        self._keys = {spell_key(sp) for b in books for sp in b.spells}
        for key, e in self.entries.items():
            if e.get("kind") == "mark":
                reg.entries[PREFIX + key] = _semantic(PREFIX + key, {
                    "name": e.get("name", key), "impl": "native:mark",
                    "text_sha1": e.get("text_sha1", ""),
                    "effects": e.get("effects", []),
                    "conditions": e.get("conditions", {})})

    def _rule(self, book, name: str, rating=None) -> RuleRef | None:
        if name.endswith(EFFECT_SUFFIX):    # a token rule's own effects
            base = self._rule(book, name[:-len(EFFECT_SUFFIX)])
            rid = base.id + EFFECT_SUFFIX if base else ""
            if base is None or self.reg.lookup(rid) is None:
                return None
            return RuleRef(rid, base.name, None, base.name)
        core = {d.name: d for d in self.reg.core.values()}
        own = {d.name: d for d in book.rules.values()} if book else {}
        d = core.get(name) or own.get(name)
        if d is None:       # another book's rule of that name, mapped
            d = next((x for x in self.reg.defs.values() if x.name == name
                      and self.reg.lookup(x.id, name) is not None), None)
        if d is None:
            return None
        label = name if rating is None else f"{name}({rating})"
        return RuleRef(d.id, name, rating, label)

    def status(self, book, spell) -> str:
        """ok / changed / unmapped / broken (a rule name that does not
        resolve). 'changed': a spell with this id is mapped and its mapped
        text is in no book any more (neither the registry's nor 'book'):
        the text changed. A same-id spell with other text while the mapped
        text is still there is a sub-faction variant: 'unmapped'."""
        key = spell_key(spell)
        if key in self.entries:
            return "ok" if self.lookup(book, spell) is not None else "broken"
        here = self._keys | {spell_key(sp) for sp in book.spells}
        mapped = [k for k in self.entries if k.split(":")[0] == spell.id]
        if mapped and not any(k in here for k in mapped):
            return "changed"
        return "unmapped"

    def lookup(self, book, spell) -> SpellSem | None:
        e = self.entries.get(spell_key(spell))
        if e is None:
            return None
        rules, grants = [], []
        for name, rating in e.get("rules", []):
            r = self._rule(book, name, rating)
            if r is None:
                return None
            rules.append(r)
        for g in e.get("grants", []):
            r = self._rule(book, g["rule"], g.get("rating"))
            if r is None:
                return None
            grants.append((r, g.get("to", "models"), g.get("attack")))
        return SpellSem(spell_key(spell), spell.name, e["kind"],
                        spell.threshold, spell.effect, e.get("hits", 0),
                        e.get("range", 0), tuple(rules), tuple(grants),
                        bool(e.get("roll_sixes", False)))

    def spells(self, book) -> list[SpellSem]:
        """Mapped spells of a book, in book order."""
        out = []
        for s in book.spells:
            sem = self.lookup(book, s)
            if sem is not None:
                out.append(sem)
        return out

    def coverage(self, books) -> list[tuple[str, str, str]]:
        """(book name, spell name, status) for every spell of 'books'."""
        return [(b.name, s.name, self.status(b, s)) for b in books
                for s in b.spells]
