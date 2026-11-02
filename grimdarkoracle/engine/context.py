"""Combat state read by the modifier layer: the two units and the
circumstances of one attack. Pure dataclasses plus a builder from
resolved units (data.resolve)."""
from dataclasses import dataclass, replace

from grimdarkoracle.data import rule_weapons
from grimdarkoracle.data.resolve import ResolvedModel, ResolvedUnit

ATTACKS = ("shooting", "melee", "spell")   # spell: fixed hits
ACTIONS = ("hold", "advance", "rush", "charge")
COVERS = ("terrain", "sight_blocker")


@dataclass(frozen=True)
class CombatModel:
    model: ResolvedModel
    quality: int
    defense: int                    # printed Defense (Armor applied later)
    hero: bool = False              # a Hero joined to this unit


@dataclass(frozen=True)
class Combatant:
    """A unit as it stands now: only the models still alive."""
    name: str
    models: tuple[CombatModel, ...]
    not_moved: bool = True          # has not moved this round (Artillery)
    over_half: bool = True          # above half its size / Tough at the
                                    # start of the attack (Decimate)
    fatigued: bool = False          # attacked in melee this round
    shaken: bool = False            # strikes back as Fatigued, fails Morale
    near_terrain: bool = False      # most models within 1" of terrain
    feat_used: bool = False         # uses its once-per-game ward Feat in
                                    # this activation (Protection Feat)


def combatant(unit: ResolvedUnit, alive=None, hero: ResolvedUnit | None = None,
              hero_alive: bool = True, **flags) -> Combatant:
    """Combatant from a resolved unit: 'alive' = indices of the models still
    on the table (default all); 'hero' = a joined Hero (single model)."""
    idx = range(unit.size) if alive is None else alive
    models = [CombatModel(unit.models[i], unit.quality, unit.defense)
              for i in idx]
    name = unit.name
    if hero is not None:
        name = f"{unit.name} + {hero.name}"
        if hero_alive:
            models.append(CombatModel(hero.models[0], hero.quality,
                                      hero.defense, hero=True))
        # a rule-weapon aura reaches the joined Hero and back
        armed = rule_weapons.add_models([c.model for c in models])
        models = [replace(c, model=m) for c, m in zip(models, armed)]
    return Combatant(name, tuple(models), **flags)


@dataclass(frozen=True)
class AttackContext:
    """Circumstances of one attack, from the attacker's point of view.

    marks / spotter_tokens / versatile are the Analyzer toggles of the
    native token rules: the rule ids of the Marks placed on the target,
    the Spotter tokens the attacker removes, and (rule id, choice index)
    choices of Versatile rules, the attacker's and the target's (Versatile
    Defense; no choice = the best for the target, app.defense_choice).
    charge_distance and ambushed are table inputs."""
    attack: str = "shooting"
    distance: int = 12              # inches to the target (melee: unused)
    action: str | None = "hold"     # attacker's action (None: strike back)
    cover: str | None = None        # target in cover: COVERS
    line_of_sight: bool = True
    crossing: bool = False          # Crossing Strike attack
    marks: tuple[str, ...] = ()
    spotter_tokens: int = 0
    versatile: tuple[tuple[str, int], ...] = ()
    charge_distance: int = 6        # inches the charger moved (charge_over)
    ambushed: bool = False          # attacker deployed via Ambush this round
    ap_spotter_tokens: int = 0      # Piercing Spotter tokens: +AP(1) each
    spell_sixes: bool = False       # damage spell rolling its fixed hits
                                    # for 6s (Storm of Power)

    def __post_init__(self):
        if self.attack not in ATTACKS:
            raise ValueError(f"attack must be one of {ATTACKS}")
        if self.action not in ACTIONS + (None,):
            raise ValueError(f"action must be one of {ACTIONS} or None")
        if self.cover not in COVERS + (None,):
            raise ValueError(f"cover must be one of {COVERS} or None")
        if min(self.distance, self.spotter_tokens, self.charge_distance) < 0:
            raise ValueError("distance, spotter_tokens and charge_distance "
                             "must be >= 0")

    @property
    def melee(self) -> bool:
        return self.attack == "melee"

    @property
    def dist(self) -> int:
        """Distance used by range conditions (0 in melee)."""
        return 0 if self.melee else self.distance

    @property
    def charging(self) -> bool:
        """The attacker charged this activation."""
        return self.melee and self.action == "charge"
