"""Hand-built combatants carrying real rule ids (shipped semantics), for the
engine tests: no Army Forge book needed."""
import testpaths                                    # noqa: F401 (sys.path)
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.data.af_book import RuleRef, Weapon
from grimdarkoracle.data.resolve import ResolvedModel
from grimdarkoracle.engine.context import AttackContext, CombatModel, Combatant
from grimdarkoracle.rules import registry

SEM = registry.load_semantics()
IDS = {e["name"]: rid for rid, e in SEM["rules"].items()}
CORE = ab.load_core_rules(testpaths.rules_path(root=testpaths.SYNTHETIC_DIR))
REG = registry.RuleRegistry(SEM, CORE)


def R(name, rating=None):
    return RuleRef(IDS[name], name, rating,
                   name if rating is None else f"{name}({rating})")


def W(name, rng, att, *rules, count=1):
    return Weapon(name, count, rng, att, tuple(rules))


RIFLE = W("Rifle", 24, 1)
CCW = W("Hand Weapon", 0, 1)


def model(weapons=(RIFLE, CCW), rules=(), upgrades=0, points=0):
    return ResolvedModel(tuple((w, 1) for w in weapons), (), tuple(rules),
                         upgrades, points)


def cm(weapons=(RIFLE, CCW), rules=(), q=4, d=4, hero=False, **kw):
    return CombatModel(model(weapons, rules, **kw), q, d, hero)


def unit(n=5, weapons=(RIFLE, CCW), rules=(), q=4, d=4, extra=(), **flags):
    """n identical models, then the CombatModels in 'extra'."""
    ms = tuple(cm(weapons, rules, q, d) for _ in range(n))
    return Combatant("u", ms + tuple(extra), **flags)


def ctx(**kw):
    return AttackContext(**kw)


def resolved(cb, points=100, name="u", issues=()):
    """A ResolvedUnit carrying the models of a Combatant (Analyzer tests)."""
    from grimdarkoracle.data.resolve import ResolvedUnit
    m0 = cb.models[0]
    return ResolvedUnit("bk", name, name, m0.quality, m0.defense, points,
                        points, tuple(c.model for c in cb.models), (),
                        tuple(issues))
