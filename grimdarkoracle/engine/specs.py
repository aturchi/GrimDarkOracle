"""Numeric inputs of the dice engine: one weapon's attacks and its target.

These are FINAL numbers. Rules, auras, conditions and the attack context
(range, action, cover, Unstoppable...) are turned into them upstream by the
modifier layer, so the engine never reads rule names. Only three things
stay in the engine because they depend on the single hit or on the target
state: the AP floor (total AP never below 0, applied separately to ordinary
hits and to hits from a 6), Blast capped by the models alive, and the
automatic success / failure of 6 / 1.

The game numbers of semantics.json 'game' travel in the
specs: auto_success / auto_fail (quality_auto_success / _fail) and
fatigue_on (fatigue_hit_on). The defaults are the GF 3.6 values; the
modifier layer copies the registry's.

Takedown is not a field: the caller resolves the weapon against a unit of
one model (models=1), which also caps Blast at 1.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AttackSpec:
    attacks: int                    # dice rolled (count x A); hits if auto_hit
    quality: int = 4                # Q+ to hit (Reliable already set to 2)
    hit_mod: int = 0                # net modifier to hit rolls
    auto_hit: bool = False          # fixed hits (spells): no roll, no 6s
    fatigued: bool = False          # hits on unmodified 6 only, never "a 6"
    extra_hits_on_6: int = 0        # Surge + Relentless + Furious (they add)
    ap: int = 0                     # net AP, may be < 0 (Fortified)
    ap_on_6: int = 0                # Rending: hits from a 6 get AP(+N)
    blast: int = 1                  # Blast(X), 1 = none
    deadly: int = 1                 # Deadly(X), 1 = none
    reroll_defense_6: bool = False  # Bane, Smash
    shred: int = 0                  # extra wounds per unmodified block 1
    ignores_regen: bool = False     # Bane, Rending, Unstoppable, Puncture
    scourge: int = 0                # extra wounds counted per unmodified
                                    # block 1 (Scourge)
    no_block: bool = False          # wound dice (Ravage): no Defense roll,
                                    # each hit is a wound
    reroll_defense_on: int = 0      # the target re-rolls SUCCESSFUL
                                    # unmodified Defense results of this
                                    # face or more once (Obliterate)
    auto_sixes: bool = False        # fixed hits: one die each, a 6 makes a
                                    # six-hit (Storm of Power)
    self_wounds_on_1: int = 0       # Hazardous: wounds its model takes per
                                    # unmodified 1 to hit
    extra_attack_on: int = 0        # Predator: an unmodified hit on this
                                    # face or more rolls one new attack,
                                    # which never triggers it (0 = none)
    name: str = ""
    auto_success: int = 6           # die face that always succeeds (game)
    auto_fail: int = 1              # die face that always fails (game)
    fatigue_on: int = 6             # Fatigued: hits on this face or more

    def __post_init__(self):
        for f in ("attacks", "extra_hits_on_6", "ap_on_6", "shred"):
            if getattr(self, f) < 0:
                raise ValueError(f"{f} must be >= 0")
        for f in ("blast", "deadly"):
            if getattr(self, f) < 1:
                raise ValueError(f"{f} must be >= 1")
        _check_auto(self.auto_success, self.auto_fail)
        if not 1 <= self.fatigue_on <= 6:
            raise ValueError("fatigue_on must be a die face")
        if self.reroll_defense_on and not 2 <= self.reroll_defense_on <= 6:
            raise ValueError("reroll_defense_on must be 0 or a face 2-6")
        if self.extra_attack_on and not 2 <= self.extra_attack_on <= 6:
            raise ValueError("extra_attack_on must be 0 or a face 2-6")


@dataclass(frozen=True)
class TargetSpec:
    defense: int = 4                # D+ to block (Armor already applied)
    defense_mod: int = 0            # net modifier to Defense rolls, cover
                                    # included, AP excluded
    regeneration: bool = False      # most models have Regeneration
    regen_on: int = 5               # wound ignored on this roll or higher
    wards: tuple[int, ...] = ()     # ward rolls (Protected, Spell Resistance
                                    # ...): each ignores a wound on N+, not
                                    # cancelled by ignores_regen
    auto_success: int = 6           # Defense roll: always blocks (game)
    auto_fail: int = 1              # Defense roll: always fails (game)

    def __post_init__(self):
        _check_auto(self.auto_success, self.auto_fail)


def _check_auto(success: int, fail: int) -> None:
    if not 1 <= fail < success <= 6:
        raise ValueError("auto_fail < auto_success must be die faces")


def game_auto(game: dict) -> dict:
    """auto_success / auto_fail keyword arguments from semantics.json
    'game'."""
    return {"auto_success": game.get("quality_auto_success", 6),
            "auto_fail": game.get("quality_auto_fail", 1)}
