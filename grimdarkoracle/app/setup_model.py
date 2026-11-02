"""What the setup panel edits, as plain values, and how it becomes the
inputs of analyzer_core (Options, Side). No tkinter.

Setup: the attack (shooting / melee), its circumstances (distance, action,
cover, line of sight, Crossing Strike) and the token rules that are
Analyzer toggles: Marks on the target, Spotter
tokens, Versatile choices. Melee is always a charge; strike back and the
tie option apply to melee only.

SideSetup: the state of one unit at the start. Wounds already taken are
entered as one number and placed by the allocation order (Tough rules,
Heroes last), which is how the defender would have taken them.
In melee the token toggles act on the charger only: the strike back
context carries none.
"""
from dataclasses import dataclass, field, replace

from grimdarkoracle.app.analyzer_core import Options, Side
from grimdarkoracle.engine.context import ACTIONS, COVERS, AttackContext
from grimdarkoracle.engine.modifiers import menu_items
from grimdarkoracle.engine.morale import TIES
from grimdarkoracle.engine.target_state import Allocation
from grimdarkoracle.rules.spells import PREFIX as SPELL_PREFIX

SHOOT_ACTIONS = ("hold", "advance")         # Rush / Charge: no shooting
SHOOT_ONLY = ("action", "cover", "line_of_sight", "crossing")
MELEE_ONLY = ("strike_back", "tie", "charge_distance")
SPELL_ONLY = ("spell", "friendly_tokens", "enemy_tokens", "conduit")
ATTACKS = ("shooting", "melee", "spell")
_PRIM = {"hit_mod": "{v:+d} to hit", "ap_mod": "AP {v:+d}",
         "range_mod": '{v:+d}" range', "defense_mod": "{v:+d} Defense"}


@dataclass(frozen=True)
class Setup:
    attack: str = "shooting"
    distance: int = 12
    action: str = "hold"
    cover: str | None = None
    line_of_sight: bool = True
    crossing: bool = False
    marks: tuple[str, ...] = ()             # rule ids of Marks on the target
    spotter_tokens: int = 0
    ap_spotter_tokens: int = 0              # Piercing Spotter
    versatile: tuple[tuple[str, int], ...] = ()
    strike_back: bool = True
    tie: str = "none"
    spell: str | None = None                # spell key (attack "spell")
    friendly_tokens: int = 0                # casting help
    enemy_tokens: int = 0
    buffs: tuple[tuple[str, str], ...] = ()  # (side, spell key)
    charge_distance: int = 6                # melee: charge from N"
    ambushed: bool = False                  # attacker deployed via Ambush
    conduit: bool = False                   # spell cast via Spell Conduit

    def __post_init__(self):
        if self.attack not in ATTACKS:
            raise ValueError(f"attack must be one of {ATTACKS}")
        if min(self.friendly_tokens, self.enemy_tokens,
               self.charge_distance) < 0:
            raise ValueError("tokens and charge distance must be >= 0")
        if self.action not in ACTIONS or self.cover not in COVERS + (None,):
            raise ValueError("bad action or cover")
        if self.tie not in TIES:
            raise ValueError(f"tie must be one of {TIES}")

    def relevant(self, name: str) -> bool:
        """Whether a control means anything for this attack (the panel
        greys out the others)."""
        if name in SHOOT_ONLY:
            return self.attack == "shooting"
        if name in MELEE_ONLY:
            return self.attack == "melee"
        if name in SPELL_ONLY:
            return self.attack == "spell"
        if name == "distance":
            return self.attack != "melee"   # spells: Smash reads it
        if name == "ambushed":
            return self.attack != "spell"
        return True

    def context(self) -> AttackContext:
        if self.attack == "melee":
            return AttackContext("melee", action="charge", marks=self.marks,
                                 spotter_tokens=self.spotter_tokens,
                                 ap_spotter_tokens=self.ap_spotter_tokens,
                                 versatile=self.versatile,
                                 charge_distance=self.charge_distance,
                                 ambushed=self.ambushed)
        if self.attack == "spell":
            return AttackContext("spell", self.distance, "hold",
                                 marks=self.marks)
        return AttackContext("shooting", self.distance, self.action,
                             self.cover, self.line_of_sight, self.crossing,
                             self.marks, self.spotter_tokens, self.versatile,
                             ambushed=self.ambushed,
                             ap_spotter_tokens=self.ap_spotter_tokens)

    def options(self, **kw) -> Options:
        """analyzer_core.Options; kw: takedown_targets, weapon_order, exact."""
        return Options(self.context(), self.strike_back, self.tie, **kw)


@dataclass(frozen=True)
class SideSetup:
    wounds_taken: int = 0
    not_moved: bool = True
    fatigued: bool = False
    shaken: bool = False
    hero_quality: int | None = None
    off: frozenset = field(default_factory=frozenset)
    near_terrain: bool = False      # table input
    feat_used: bool = False         # once-per-game ward Feat used


def max_wounds(unit, hero=None) -> int:
    """Most wounds a unit can have taken and still have a model alive."""
    caps = [max(1, m.tough) for m in unit.models]
    if hero is not None:
        caps += [max(1, m.tough) for m in hero.models]
    return sum(caps) - 1


def make_side(unit, hero=None, ss: SideSetup = SideSetup()) -> Side:
    """analyzer_core.Side with the wounds placed by the allocation order."""
    side = Side(unit, hero, None, ss.not_moved, ss.fatigued, ss.shaken,
                frozenset(ss.off), ss.hero_quality,
                near_terrain=ss.near_terrain, feat_used=ss.feat_used)
    n = max(0, min(ss.wounds_taken, max_wounds(unit, hero)))
    if n:
        alloc = Allocation.of(side.combatant())
        side = replace(side, wounds=alloc.carry(alloc.fresh(), n))
    return side


# --- token rules offered as toggles -------------------------------------


def effect_label(eff, reg) -> str:
    """Short text of one effect of a menu rule (Versatile choice)."""
    if eff.primitive == "grant_rule":
        rid = eff.value.get("rule") if isinstance(eff.value, dict) else None
        d = reg.defs.get(rid) if rid else None
        return f"gains {d.name if d else rid}"
    fmt = _PRIM.get(eff.primitive)
    if fmt and isinstance(eff.value, int):
        return fmt.format(v=eff.value)
    return f"{eff.primitive} {eff.value}"


def marks(reg) -> list[tuple[str, str]]:
    """(rule id, name) of every Mark RULE the registry knows, by name (the
    spell marks are offered with the spells, app.spells.buff_menu)."""
    out = []
    for e in reg.entries.values():
        if e.handler != "mark" or e.rule_id.startswith(SPELL_PREFIX):
            continue
        n = dict(e.params).get("tokens")
        out += [(e.rule_id, e.name)] if not n else [
            (f"{e.rule_id}*{k}", f"{e.name} ({k} token{'s' * (k > 1)})")
            for k in range(1, n + 1)]
    return sorted(out, key=lambda x: x[1])


def versatile(reg, unit) -> list[tuple[str, str, list[str]]]:
    """(rule id, name, choice labels) of the ATTACKER-side Versatile rules
    held by the models of 'unit' (ResolvedUnit), in first-seen order (the
    target's Versatile Defense: app.defense_choice); the name is the
    unit's (Watchborn, not its alias target Versatile Warrior)."""
    out, seen = [], set()
    for m in unit.models:
        for r in m.rules:
            sem = reg.lookup(r.id, r.name)
            if sem is not None and sem.rule_id not in seen and \
                    "tokens" in dict(sem.params):
                seen.add(sem.rule_id)
                n = dict(sem.params)["tokens"]
                out.append((sem.rule_id, r.name, [
                    f"{k} token{'s' if k > 1 else ''}"
                    for k in range(1, n + 1)]))
                continue
            if sem is None or sem.handler != "versatile" or \
                    sem.rule_id in seen or \
                    any(e.side == "defender" for e in sem.effects):
                continue
            seen.add(sem.rule_id)
            out.append((sem.rule_id, r.name,       # the book's name
                        [label or effect_label(sem.effects[ix[0]], reg)
                         for label, ix in menu_items(sem)]))
    return out
