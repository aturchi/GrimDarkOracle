"""Vocabulary of the rule semantics registry (semantics.json).

Every rule id maps to one entry with an ``impl``:

- ``native:<handler>``  core mechanic coded in the engine (HANDLERS);
- ``composed``          a list of primitive effects under conditions;
- ``no_combat_effect``  stated explicitly (movement, deployment...), so the
                        coverage report stays clean;
- ``todo``              known but not implemented yet (reported).

A value written "X" means the rating of the rule (AP(2) -> 2). The total AP
of an attack never goes below 0 (Fortified: "to a min. of AP(0)").
``side``: "attacker" = modifies attacks made BY the holder (default);
"defender" = modifies attacks made AGAINST the holder.
``scope``: "weapon" (the weapon carrying the rule), "model" (the model),
"unit" (the holder's whole unit, i.e. "this model and its unit" / auras).
Default scope: weapon for weapon rules; for rules held
by a model (unit rules, items) attacker-side effects reach that model only
(a joined Hero's rules never reach its host, nor the host's the Hero) and
defender-side effects act on the whole target unit.
"""

FORMAT = "grimdarkoracle-semantics/1"
LEGACY_FORMATS = ("grimoracle-semantics/1",)  # before the rename (dec. 57)
IMPL_KINDS = ("composed", "no_combat_effect", "todo")
NATIVE_PREFIX = "native:"

# Mechanics implemented by name in the engine. Params are
# the numbers the code reads (an entry carries no other).
# action_limit (permanent action restrictions): params
# 'actions' = the actions the unit may use, 'shoot_when_moving' (default
# true), 'chargeable' (default true). Book handlers:
# crossing_strike (weapon usable only when moving through enemies),
# mark (an enemy unit marked: 'effects' = what friendly attacks get
# against it, an Analyzer toggle), spotter (tokens -> +X to hit),
# versatile (pick one of 'effects' per activation; param 'choices' =
# [[label, [effect indices]], ...] groups effects into one choice;
# defender-side effects = the target's pick, Versatile Defense), ward
# (each wound ignored on 'ignore_on'+, on 'spell_ignore_on'+ when from a
# spell; NOT cancelled by ignore_regen; 'far_only': the
# non-spell part only when shot / charged from over 9"/6"; 'replaces': the
# rule id of a ward it replaces, acting only when that ward does).
# wound_dice param 'tokens': N, one die per token, the count an Analyzer
# menu of 1..N (none = no die).
# versatile param 'state': the menu is game state (tokens), never picked
# for the target; none = no token. ward param 'state': a once-per-
# game ward (Protection Feat), acting only when its unit's "uses its Feat"
# input is on, for every wound of the activation.
# impact params:
# 'hit_on', 'ap'.
# rule_weapon (the data layer adds the weapon by name), caster_group
# (Caster(X), X = models holding it), spell_conduit ('cast_mod' of a cast
# made through it, a player's input). buff (a friendly unit gets the
# rules of its grant_rule effects, like a grant spell, and its own
# effects; param 'attack' limits them to one attack type). debuff
# (the same on an ENEMY unit).
# unpredictable (one die per unit and attack picks one of the choices, as
# Versatile's 'choices', each 'odds' faces of 6). wound_dice (a
# weapon of the rule's X dice, each 'on'+ a wound with no Defense roll;
# 'trigger' melee / crossing). retaliate (X hits back per wound taken
# in melee). indirect_any_action (Quick Throw: the model's Indirect
# weapons may shoot without line of sight after any shooting action, not
# only Hold; the cover part of Indirect stays Hold-only).
HANDLERS = (
    "action_limit", "assault", "blast", "brace", "caster", "counter",
    "unwieldy", "no_retreat", "self_destruct", "dice_hits", "deathstrike",
    "hazardous", "indirect_any_action",
    "crossing_strike", "deadly", "fear", "fearless", "hero", "impact",
    "indirect", "limited", "mark", "parry", "regeneration", "spotter",
    "takedown", "tough", "versatile", "ward", "rule_weapon", "caster_group",
    "spell_conduit", "buff", "unpredictable", "wound_dice", "retaliate",
    "debuff",
)
# Token rules act only through the units their tokens go on (Marks: the
# friendly attacks against the marked unit; buffs: a friendly unit;
# debuffs: an enemy unit), never on their holder. A buff's or
# debuff's own effects (not its grants) are held by that unit as the
# pseudo-rule '<rule id>#effect' (registry.lookup).
TOKEN_HANDLERS = ("mark", "buff", "debuff")
EFFECT_SUFFIX = "#effect"

INT, BOOL, RULE, ID = "int", "bool", "rule", "id"
# primitive -> type of 'value'
PRIMITIVES = {
    "hit_mod": INT,                 # +/- to hit rolls
    "defense_mod": INT,             # +/- to Defense rolls (block)
    "defense_set": INT,             # counts as having Defense N+ (Armor)
    "ap_mod": INT,                  # AP added to the weapon
    "range_mod": INT,               # +/- inches of range
    "quality_set": INT,             # attacks at Quality N+ (Reliable)
    "extra_hit_on_6": INT,          # unmodified 6 to hit: N extra hits
    "ap_on_6": INT,                 # unmodified 6 to hit: those hits AP(+N)
    "extra_wound_on_def_1": INT,    # unmodified 1 to block: N extra wounds
    "reroll_defense_6": BOOL,       # target re-rolls unmodified Defense 6
    "ignore_regen": BOOL,           # ignores Regeneration
    "ignore_cover": BOOL,
    "ignore_negative_mods": BOOL,   # Unstoppable
    "ignore_defense_bonus": BOOL,   # Pierce: target's positive Defense
                                    # modifiers (cover included) dropped
    "scourge": INT,                 # extra wounds counted per unmodified
                                    # block 1 of its hits (Scourge)
    "range_floor": INT,             # defender: its range reductions stop
                                    # at N" (Ranged Shrouding)
    "morale_mod": INT,              # +/- to Morale Test rolls
    "cast_mod": INT,                # +/- to casting rolls
    "grant_rule": RULE,             # {"rule": id}: gives another rule
                                    # (auras); entry conditions restrict it
    "reroll_defense_on": INT,       # target re-rolls SUCCESSFUL unmodified
                                    # Defense N+ once (Obliterate)
    "extra_attack_on": INT,         # unmodified hit on N+: one new attack
                                    # (Predator; lowest N wins)
    "lift_distance": RULE,          # {"rule": id}: that rule's range_over
                                    # holds and its charge_over holds for
                                    # any charge ("Enhanced ...")
}

# Primitives that change which rules apply, not a number of the attack:
# never collected as modifiers.
STRUCTURAL = ("grant_rule", "lift_distance")

# semantics.json 'game': numbers of the core rules the engine reads,
# with their allowed range. Defaults = GF 3.6.
GAME_NUMBERS = {
    "quality_auto_success": (2, 6),     # a roll of N always succeeds
    "quality_auto_fail": (1, 5),        # a roll of N always fails
    "cover_defense_bonus": (0, 6),      # Defense bonus of cover
    "fatigue_hit_on": (1, 6),           # Fatigued: hits on unmodified N+
    "morale_half": (0, 1),              # "half or less" for Morale
}

SIDES = ("attacker", "defender")
SCOPES = ("weapon", "model", "unit")

# condition key -> allowed values (tuple) or a type name
CONDITIONS = {
    "attack": ("shooting", "melee", "spell"),
    "action": ("hold", "advance", "rush", "charge"),
    "charging": BOOL,               # holder charged this activation
    "charged": BOOL,                # holder is being charged
    "range_over": INT,              # target over N" away
    "range_within": INT,            # target within N"
    "target_tough_min": INT,        # target has Tough(N) or more
    "target_defense_min": INT,      # target Defense N+ or worse
    "target_defense_max": INT,      # target Defense N+ or better
    "target_in_cover": BOOL,
    "most_models": BOOL,            # most models of the holder's unit have it
    "not_moved": BOOL,              # holder has not moved this round
    "not_fatigued": BOOL,
    "morale_from": ("shooting", "melee", "spell"),
    "morale_from_combat": BOOL,     # Morale Test triggered by shooting / melee
    "has_rule": ID,                 # holder also has this rule (by id)
    "range_over_half": BOOL,        # target over half the weapon's range
    "charge_over": INT,             # a charge from over N" (both roles)
    "ambushed_this_round": BOOL,    # holder deployed via Ambush this round
    "target_shaken_or_fatigued": BOOL,  # the other unit
    "target_over_half": BOOL,       # the other unit above half its size /
                                    # Tough at the start of the attack
    "most_have_rule": ID,           # most models of the holder's unit have
                                    # this rule (by id or alias)
    "near_terrain": BOOL,           # most of the holder's models within 1"
                                    # of terrain, a table input
    "target_near_terrain": BOOL,    # the same for the other unit
}
