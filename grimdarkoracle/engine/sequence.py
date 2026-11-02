"""One unit's attack on another as an ordered list of weapon steps, with
the final numbers of each step for any state of the target.

Shared by the exact kill chain and the dice resolver, so both follow the
same steps and read the same specs:

- steps are the groups of the plan against the full target, in the order
  Takedown, Deadly, others; inside each class, plan order
  (attacking models, then their weapons in book order) unless the caller
  gives one. A Takedown group is split into one step per attacking model,
  each against its own chosen model;
- rules are checked for the models alive at the START of each weapon
  (Blast, "most models", Tough(N)+ ...): build_plan is re-run on the
  living models and cached per set of living models;
- block rolls are made by the unit for all hits of one weapon, with the
  TargetSpec most living models have (ties: the model next in the
  allocation order); a Takedown attack uses the chosen model's own,
  as a unit of one.
"""
from dataclasses import dataclass, replace

from grimdarkoracle.data.af_book import Weapon
from grimdarkoracle.engine.context import AttackContext, Combatant
from grimdarkoracle.engine.modifiers import AttackPlan, build_plan
from grimdarkoracle.engine.specs import AttackSpec, TargetSpec
from grimdarkoracle.engine.target_state import Allocation
from grimdarkoracle.rules.registry import RuleRegistry

KINDS = ("takedown", "deadly", "other")


@dataclass(frozen=True)
class AuditPart:
    """What the engine uses for one part of a step at one state (audit)."""
    spec: AttackSpec
    target: TargetSpec              # unit-level (Takedown: the model's)
    sources: tuple[str, ...]        # modifiers applied, as the plan wrote them
    models: int                     # target models for Blast
    takedown_model: int | None = None


@dataclass(frozen=True)
class Step:
    weapon: Weapon
    models: tuple[int, ...]         # attacking model positions
    kind: str                       # KINDS
    limited: bool = False
    counter: bool = False           # may strike first when charged (melee)
    last: bool = False              # strikes after the strike back


class AttackSequence:
    """Steps of 'attacker' against 'target' in 'ctx'.

    takedown_targets: target model positions in order of preference for
    Takedown attacks; default: the reverse of the allocation order of the
    fresh unit (the model the defender would lose last first).
    weapon_order: optional weapon names; listed weapons go first within
    their class, in that order."""

    def __init__(self, reg: RuleRegistry, attacker: Combatant,
                 target: Combatant, ctx: AttackContext,
                 takedown_targets=(), weapon_order=()):
        self.reg, self.attacker, self.target, self.ctx = \
            reg, attacker, target, ctx
        self.alloc = Allocation.of(target)
        self._plans: dict = {}
        plan = self.plan(tuple(range(len(target.models))))
        self.excluded, self.warnings = plan.excluded, plan.warnings
        self.barred = plan.barred       # no attack at all
        self.takedown_targets = tuple(takedown_targets) or \
            tuple(reversed(self.alloc.order(self.alloc.fresh())))
        rank = {name: k for k, name in enumerate(weapon_order)}
        steps = []
        for n, g in enumerate(plan.groups):
            kind = "takedown" if g.takedown else \
                "deadly" if g.spec.deadly > 1 else "other"
            pos = (KINDS.index(kind), rank.get(g.weapon.name, len(rank)), n)
            ms = [(i,) for i in g.models] if g.takedown else [g.models]
            steps += [(pos, Step(g.weapon, m, kind, g.limited, g.counter,
                                 g.last))
                      for m in ms]
        self.steps = tuple(s for _, s in sorted(steps, key=lambda x: x[0]))

    # --- plans ------------------------------------------------------------

    def plan(self, alive: tuple[int, ...]) -> AttackPlan:
        """build_plan against the target models at positions 'alive'."""
        p = self._plans.get(alive)
        if p is None:
            sub = replace(self.target, models=tuple(self.target.models[i]
                                                    for i in alive))
            p = build_plan(self.reg, self.attacker, sub, self.ctx)
            self._plans[alive] = p
        return p

    def _attacks(self, weapon: Weapon, models) -> int:
        return sum(n * weapon.attacks for i in models
                   for w, n in self.attacker.models[i].model.weapons
                   if w == weapon)

    def _groups(self, step: Step, alive):
        """(AttackSpec restricted to the step's models, group) pairs."""
        out = []
        for g in self.plan(alive).groups:
            ms = set(g.models) & set(step.models)
            if g.weapon == step.weapon and ms:
                out.append((replace(g.spec, attacks=self._attacks(
                    step.weapon, sorted(ms))), g))
        return out

    # --- specs for a state --------------------------------------------------

    def unit_target(self, targets, state) -> TargetSpec:
        """TargetSpec most living models have; ties: the model first in
        the allocation order. 'targets' follows alive(state)."""
        alive = self.alloc.alive(state)
        by_model = dict(zip(alive, targets))
        counts: dict = {}
        for t in targets:
            counts[t] = counts.get(t, 0) + 1
        best = max(counts.values())
        return next(by_model[i] for i in self.alloc.order(state)
                    if counts[by_model[i]] == best)

    def parts(self, step: Step, state) -> list[tuple[AttackSpec, TargetSpec]]:
        """(AttackSpec, TargetSpec) of a non-Takedown step at 'state'
        (usually one; several if the step's models now differ)."""
        alive = self.alloc.alive(state)
        if not alive:
            return []
        return [(spec, self.unit_target(g.targets, state))
                for spec, g in self._groups(step, alive)]

    def takedown_target(self, state) -> int | None:
        """Model picked by the next Takedown attack."""
        alive = set(self.alloc.alive(state))
        for j in self.takedown_targets:
            if j in alive:
                return j
        order = self.alloc.order(state)
        return order[-1] if order else None

    def audit(self, step: Step, state) -> list[AuditPart]:
        """The specs and the modifier sources of a step at 'state'."""
        alive = self.alloc.alive(state)
        if not alive:
            return []
        if step.kind == "takedown":
            j = self.takedown_target(state)
            gs = self._groups(step, (j,)) if j is not None else []
            return [AuditPart(spec, g.targets[0], g.sources, 1, j)
                    for spec, g in gs[:1]]
        return [AuditPart(spec, self.unit_target(g.targets, state), g.sources,
                          len(alive))
                for spec, g in self._groups(step, alive)]

    def takedown_part(self, step: Step, j: int):
        """(AttackSpec, TargetSpec) of a Takedown step against model j,
        resolved as a unit of one; None if the weapon cannot."""
        gs = self._groups(step, (j,))
        return (gs[0][0], gs[0][1].targets[0]) if gs else None
