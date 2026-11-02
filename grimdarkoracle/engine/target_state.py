"""Wound state of a target unit and the order wounds are allocated in.

A state is a tuple with the wounds TAKEN by each model of the target
Combatant (same positions as ``Combatant.models``); a model is dead when
its wounds reach its capacity, max(1, Tough). States are hashable, so the
exact kill chain keeps a {state: probability} law and the dice resolver
walks one state.

Allocation order (core rules 3.6, Tough and Hero):

1. models without Tough first ("a model with Tough ... is removed last");
2. then Tough models, the one with the MOST wounds first ("continue to put
   wounds on the Tough model with most wounds ... until it is killed");
3. joined Heroes last, even if already wounded (most wounds first);
4. inside each group the defender chooses; the Analyzer removes models
   without upgrades first, then upgraded ones by the lowest upgrade points,
   ties: highest index first.

A wound event goes to the first model of the order. Ordinary wounds carry
over to the next model; Deadly wounds do not (Deadly rule text, see
kill_chain).
"""
from dataclasses import dataclass

from grimdarkoracle.engine.context import Combatant


@dataclass(frozen=True)
class ModelInfo:
    cap: int                        # wounds to kill it: max(1, Tough)
    tough: bool
    hero: bool                      # joined Hero
    upgrades: int = 0
    upgrade_points: int = 0


def model_infos(target: Combatant) -> tuple[ModelInfo, ...]:
    return tuple(ModelInfo(max(1, cm.model.tough), cm.model.tough > 0,
                           cm.hero, cm.model.upgrades,
                           cm.model.upgrade_points)
                 for cm in target.models)


class Allocation:
    """Allocation rules of one target unit (static model data)."""

    def __init__(self, infos):
        self.infos = tuple(infos)
        self._orders: dict = {}

    @classmethod
    def of(cls, target: Combatant) -> "Allocation":
        return cls(model_infos(target))

    @property
    def size(self) -> int:
        return len(self.infos)

    def fresh(self) -> tuple:
        return (0,) * len(self.infos)

    def check(self, state) -> tuple:
        """Validated copy of a state given by the caller."""
        state = tuple(state)
        if len(state) != len(self.infos) or any(
                not 0 <= w <= m.cap for w, m in zip(state, self.infos)):
            raise ValueError(f"bad state {state!r} for {len(self.infos)} "
                             "models")
        return state

    # --- reading a state ----------------------------------------------------

    def alive(self, state) -> tuple[int, ...]:
        """Indices of the models still alive, in index order."""
        return tuple(i for i, (w, m) in enumerate(zip(state, self.infos))
                     if w < m.cap)

    def left(self, state, i: int) -> int:
        return self.infos[i].cap - state[i]

    def killed(self, state) -> int:
        return len(self.infos) - len(self.alive(state))

    def taken(self, state) -> int:
        """Wounds on living models plus the capacity of the dead ones."""
        return sum(state)

    def _key(self, state, i):
        m = self.infos[i]
        group = 2 if m.hero else (1 if m.tough else 0)
        return (group, -state[i], m.upgrades > 0, m.upgrade_points, -i)

    def order(self, state) -> tuple[int, ...]:
        """Living models in allocation order (first = next to be wounded)."""
        out = self._orders.get(state)
        if out is None:
            out = tuple(sorted(self.alive(state),
                               key=lambda i: self._key(state, i)))
            self._orders[state] = out
        return out

    def front(self, state) -> int | None:
        o = self.order(state)
        return o[0] if o else None

    # --- changing a state ---------------------------------------------------

    def wound(self, state, i: int, d: int) -> tuple:
        """'d' wounds on model i, the excess is lost (Deadly, Takedown)."""
        if d <= 0 or state[i] >= self.infos[i].cap:
            return state
        s = list(state)
        s[i] = min(self.infos[i].cap, s[i] + d)
        return tuple(s)

    def carry(self, state, d: int) -> tuple:
        """'d' ordinary wounds: each on the first model of the order, so
        they pass on to the next model when one dies."""
        if d <= 0:
            return state
        s = list(state)
        for i in self.order(state):
            take = min(d, self.infos[i].cap - s[i])
            s[i] += take
            d -= take
            if not d:
                break
        return tuple(s)
