"""Rule semantics registry: rule id -> what the engine does with it.

Rule ids are global in Army Forge (same id, same text in every book), so
one registry serves all books. Lookup of a RuleRef, in order:

1. an entry for the rule's own id;
2. an entry for its alias target (faction rule renamed from a generic one,
   e.g. Targeting Visor -> Precision Marksman), following alias chains;
3. an entry for the CORE rule with the same name (books redefine AP with
   another id while weapons use the core one).

Each entry stores the SHA-1 of the rule text it was written against
(whitespace-normalised), and in 'alias_sha1' the SHA-1 of the own text of
each Army Forge alias mapped through it (tools/fingerprint.py); a
different current text marks the rule 'changed' (rules.coverage).
The Army Forge API text of the core rules is authoritative; the core
rules PDF only for the game sequence.
"""
import hashlib
import json
import os
from dataclasses import dataclass, replace

from grimdarkoracle import app_paths
from grimdarkoracle.rules import vocab as V

RESOURCE = os.path.join("rules", "semantics.json")


def text_sha1(text: str) -> str:
    """SHA-1 of a rule text with whitespace normalised."""
    return hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Effect:
    primitive: str
    value: object                   # int, bool, "X" or {"rule": ...}
    side: str = "attacker"
    scope: str | None = None
    # Extra conditions of this effect only (AND with the entry's).
    conditions: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True)
class Semantic:
    rule_id: str                    # id of the entry (may be an alias target)
    name: str
    impl: str
    text_sha1: str
    effects: tuple[Effect, ...] = ()
    conditions: tuple[tuple[str, object], ...] = ()
    params: tuple[tuple[str, object], ...] = ()
    # (alias id, SHA-1 of the alias's own text): the Army Forge aliases
    # mapped through this entry, each with the text it was reviewed for
    alias_sha1: tuple[tuple[str, str], ...] = ()

    def expected_sha1(self, rule_id: str) -> str | None:
        """Fingerprint the text of 'rule_id' should have: the entry's own
        for its id, the alias's for an alias (None: never fingerprinted)."""
        if rule_id == self.rule_id:
            return self.text_sha1
        return dict(self.alias_sha1).get(rule_id)

    @property
    def handler(self) -> str | None:
        return self.impl[len(V.NATIVE_PREFIX):] \
            if self.impl.startswith(V.NATIVE_PREFIX) else None


# --- validation --------------------------------------------------------------

def _check_value(kind, value, where, errors):
    if value == "X" and kind == V.INT:
        return
    if kind == V.INT and not (isinstance(value, int)
                              and not isinstance(value, bool)):
        errors.append(f"{where}: integer or 'X' expected, got {value!r}")
    elif kind == V.BOOL and not isinstance(value, bool):
        errors.append(f"{where}: boolean expected, got {value!r}")
    elif kind == V.RULE and not (isinstance(value, dict) and
                                 isinstance(value.get("rule"), str)):
        errors.append(f"{where}: {{'rule': id}} expected, got {value!r}")
    elif kind == V.ID and not (isinstance(value, str) and value):
        errors.append(f"{where}: rule id expected, got {value!r}")
    elif isinstance(kind, tuple) and value not in kind:
        errors.append(f"{where}: one of {kind} expected, got {value!r}")


def _check_conditions(conds, where, errors):
    if not isinstance(conds, dict):
        errors.append(f"{where}: conditions must be an object")
        return
    for key, value in conds.items():
        if key not in V.CONDITIONS:
            errors.append(f"{where}: unknown condition {key!r}")
        else:
            _check_value(V.CONDITIONS[key], value, f"{where} {key}", errors)


def _check_game(game, errors) -> None:
    """Game numbers read by the engine; other keys ignored."""
    if not isinstance(game, dict):
        errors.append("game must be an object")
        return
    for key, (lo, hi) in V.GAME_NUMBERS.items():
        v = game.get(key)
        if v is None:
            continue                # the engine default applies
        ok = isinstance(v, (int, float)) and not isinstance(v, bool) and \
            lo <= v <= hi and (isinstance(v, int) or key == "morale_half")
        if not ok:
            errors.append(f"game {key}: {v!r} not in [{lo}, {hi}]")
    s = game.get("quality_auto_success", 6)
    f = game.get("quality_auto_fail", 1)
    if isinstance(s, int) and isinstance(f, int) and f >= s:
        errors.append("game: quality_auto_fail must be below "
                      "quality_auto_success")


def validate(data: dict, known=()) -> list[str]:
    """Errors in a semantics document (empty list = valid); 'known' =
    entry ids outside the document that grant_rule may name."""
    errors = []
    if not isinstance(data, dict) or \
            data.get("format") not in (V.FORMAT,) + V.LEGACY_FORMATS:
        return [f"format must be {V.FORMAT!r}"]
    _check_game(data.get("game", {}), errors)
    entries = data.get("rules", {})
    for rid, e in entries.items():
        where = f"{rid} ({e.get('name', '?')})"
        impl = e.get("impl", "")
        if impl.startswith(V.NATIVE_PREFIX):
            if impl[len(V.NATIVE_PREFIX):] not in V.HANDLERS:
                errors.append(f"{where}: unknown handler {impl!r}")
        elif impl not in V.IMPL_KINDS:
            errors.append(f"{where}: unknown impl {impl!r}")
        sha = e.get("text_sha1", "")
        if len(sha) != 40:
            errors.append(f"{where}: text_sha1 missing or malformed")
        aliases = e.get("alias_sha1", {})
        if not isinstance(aliases, dict) or any(
                not isinstance(h, str) or len(h) != 40
                for h in aliases.values()):
            errors.append(f"{where}: alias_sha1 must map alias ids to "
                          "SHA-1 hex strings")
        if impl == "composed" and not e.get("effects"):
            errors.append(f"{where}: composed without effects")
        for i, eff in enumerate(e.get("effects", [])):
            w = f"{where} effect {i}"
            prim = eff.get("primitive")
            if prim not in V.PRIMITIVES:
                errors.append(f"{w}: unknown primitive {prim!r}")
                continue
            _check_value(V.PRIMITIVES[prim], eff.get("value"), w, errors)
            if prim == "grant_rule" and isinstance(eff.get("value"), dict):
                target = eff["value"].get("rule")
                if target not in entries and target not in known:
                    errors.append(f"{w}: granted rule {target!r} has no "
                                  "entry (grant the alias TARGET's id)")
            if eff.get("side", "attacker") not in V.SIDES:
                errors.append(f"{w}: bad side {eff.get('side')!r}")
            if eff.get("scope") not in (None,) + V.SCOPES:
                errors.append(f"{w}: bad scope {eff.get('scope')!r}")
            _check_conditions(eff.get("conditions", {}), w, errors)
        _check_conditions(e.get("conditions", {}), where, errors)
    return errors


def _semantic(rid: str, e: dict) -> Semantic:
    effects = tuple(Effect(x["primitive"], x.get("value"),
                           x.get("side", "attacker"), x.get("scope"),
                           tuple(sorted(x.get("conditions", {}).items())))
                    for x in e.get("effects", []))
    return Semantic(rid, e.get("name", ""), e["impl"], e["text_sha1"],
                    effects, tuple(sorted(e.get("conditions", {}).items())),
                    tuple(sorted((k, _freeze(v))
                                 for k, v in e.get("params", {}).items())),
                    tuple(sorted(e.get("alias_sha1", {}).items())))


def _freeze(v):
    """JSON lists as tuples, nested ones too (Semantic is frozen)."""
    return tuple(_freeze(x) for x in v) if isinstance(v, list) else v


def load_semantics(path: str | None = None) -> dict:
    """Read semantics.json: 'path', else the user's copy next to the
    program, else the shipped one. Raises ValueError if invalid."""
    candidates = [path] if path else app_paths.resource(RESOURCE)
    for p in candidates:
        if p and os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
            errors = validate(data)
            if errors:
                raise ValueError(f"{p}: " + "; ".join(errors[:5]))
            return data
    raise FileNotFoundError(f"no {RESOURCE} in {candidates}")


# --- registry ----------------------------------------------------------------

class RuleRegistry:
    """Rule definitions (core + books) and their semantics."""

    def __init__(self, semantics: dict, core: dict, books=()):
        self.entries = {rid: _semantic(rid, e)
                        for rid, e in semantics.get("rules", {}).items()}
        self.game = dict(semantics.get("game", {}))
        self.core = dict(core)
        self.defs = dict(core)
        for b in books:
            self.add_book(b)
        self._core_by_name = {d.name: d.id for d in core.values()}

    def add_book(self, book, replace: bool = False) -> None:
        """Add the rule definitions of a book; 'replace' updates the ones
        already known (a local book edited in the List Editor)."""
        for rid, d in book.rules.items():
            if replace:
                self.defs[rid] = d
            else:
                self.defs.setdefault(rid, d)

    def install(self, rule_id: str, entry: dict) -> Semantic:
        """Add or replace one entry (custom rules of local books, Rules
        Mapper); ValueError with the reasons if it is not valid."""
        doc = {"format": V.FORMAT, "rules": {rule_id: entry}}
        errors = validate(doc, known=self.entries)
        if errors:
            raise ValueError("; ".join(errors))
        sem = self.entries[rule_id] = _semantic(rule_id, entry)
        return sem

    def uninstall(self, rule_id: str) -> None:
        self.entries.pop(rule_id, None)

    def alias_chain(self, rule_id: str) -> list[str]:
        """[rule_id, alias target, its target, ...] (loops broken)."""
        chain = [rule_id]
        while True:
            d = self.defs.get(chain[-1])
            nxt = d.aliased_rule_id if d else None
            if not nxt or nxt in chain:
                return chain
            chain.append(nxt)

    def lookup(self, rule_id: str, name: str = "") -> Semantic | None:
        """Semantics of a rule by id (alias, then core-name fallback);
        '<id>#effect' is the pseudo-rule of a token rule's own effects."""
        if rule_id.endswith(V.EFFECT_SUFFIX):
            return self._effect_of(rule_id)
        for rid in self.alias_chain(rule_id):
            if rid in self.entries:
                return self.entries[rid]
        d = self.defs.get(rule_id)
        core_id = self._core_by_name.get(name or (d.name if d else ""))
        return self.entries.get(core_id) if core_id else None

    def _effect_of(self, rule_id: str) -> Semantic | None:
        """The effects (not the grants) of a buff / debuff entry as a plain
        composed rule, the one the buffed or debuffed unit holds."""
        base = self.lookup(rule_id[:-len(V.EFFECT_SUFFIX)])
        if base is None or base.handler not in V.TOKEN_HANDLERS:
            return None
        effects = tuple(e for e in base.effects
                        if e.primitive != "grant_rule")
        return replace(base, rule_id=rule_id, impl="composed",
                       effects=effects, params=()) if effects else None

    def status(self, rule_id: str, name: str = "") -> str:
        """'ok', 'changed' (text differs from the hashed one), 'todo',
        'unmapped' or 'undefined' (no definition anywhere)."""
        sem = self.lookup(rule_id, name)
        if sem is None:
            return "unmapped" if rule_id in self.defs else "undefined"
        d = self.defs.get(sem.rule_id)
        if d is None or text_sha1(d.description) != sem.text_sha1:
            return "changed"
        return "todo" if sem.impl == "todo" else "ok"
