"""One side of the Analyzer as the user picked it: a unit (book + choices,
Combined copies, list overrides) and an optional joined Hero, taken from
a book or from an army list entry. Pure; the side picker (ui) edits it
and run() turns two of them into an analysis.
"""
from dataclasses import dataclass, replace

from grimdarkoracle.app import spells as SP
from grimdarkoracle.app.analyzer_core import Analysis, analyse
from grimdarkoracle.app.setup_model import Setup, SideSetup, make_side
from grimdarkoracle.app.unit_config import UnitConfig
from grimdarkoracle.data import links, overrides
from grimdarkoracle.data.list_resolve import (MAX_JOIN_TOUGH, is_hero,
                                              join_issues)
from grimdarkoracle.data.resolve import ResolvedUnit, combine, resolve


@dataclass
class UnitSpec:
    cfg: UnitConfig
    combined: bool = False
    cfg_b: UnitConfig | None = None         # copy B; None = same as copy A
    overrides: tuple = ()
    label: str = ""                         # list label (shown as the name)

    def resolved(self) -> ResolvedUnit:
        ru = self.cfg.resolved
        if self.combined:
            ru = combine(ru, (self.cfg_b or self.cfg).resolved)
        if self.overrides:
            ru = overrides.apply(ru, list(self.overrides))
        if self.label and self.label != ru.name:
            ru = replace(ru, name=self.label)
        return ru

    def with_choices(self, choices) -> "UnitSpec":
        """Same unit with copy A's choices replaced (variants)."""
        return replace(self, cfg=UnitConfig(self.cfg.book, self.cfg.unit.id,
                                            choices))


@dataclass
class SideSpec:
    unit: UnitSpec
    hero: UnitSpec | None = None

    def resolved(self) -> tuple[ResolvedUnit, ResolvedUnit | None]:
        return self.unit.resolved(), \
            (self.hero.resolved() if self.hero else None)

    def issues(self) -> list[str]:
        ru, hero = self.resolved()
        return [] if hero is None else \
            [f"{hero.name}: {x}" for x in join_issues(hero, ru)]

    @property
    def name(self) -> str:
        ru, hero = self.resolved()
        return ru.name if hero is None else f"{ru.name} + {hero.name}"


def book_side(book, unit_id: str) -> SideSpec:
    return SideSpec(UnitSpec(UnitConfig(book, unit_id)))


def hero_candidates(book) -> list:
    """Book units able to join a unit with their default choices."""
    out = []
    for u in book.units.values():
        ru = resolve(book, u.id)
        if is_hero(ru) and ru.size == 1 and \
                max(m.tough for m in ru.models) <= MAX_JOIN_TOUGH:
            out.append(u)
    return out


# --- army lists --------------------------------------------------------------


def _unit_spec(book, lu) -> tuple[UnitSpec, list[str]]:
    link = links.link_unit(book, lu)
    if link.unit_id is None:
        raise ValueError(f"{lu.label or lu.unit_name}: unit not found in "
                         f"{book.name}")
    cfg = UnitConfig(book, link.unit_id, [r.choice() for r in link.choices])
    cfg_b = None
    if lu.combined and link.choices_b is not None:
        cfg_b = UnitConfig(book, link.unit_id,
                           [r.choice() for r in link.choices_b])
    spec = UnitSpec(cfg, lu.combined, cfg_b, tuple(lu.overrides), lu.label)
    return spec, [f"{lu.label or lu.unit_name}: {x}" for x in link.invalid]


def entry_side(books: dict, army, key: str) -> tuple[SideSpec, list[str]]:
    """SideSpec of list entry 'key', with the Hero joined to it (if any);
    second item: choices of the list that could not be linked."""
    lu = army.unit(key)
    if lu is None or lu.book not in books:
        raise ValueError(f"entry {key!r}: unit or book missing")
    spec, notes = _unit_spec(books[lu.book], lu)
    hero = None
    guest = next((g for g in army.units if g.joined_to == key), None)
    if guest is not None and guest.book in books:
        hero, more = _unit_spec(books[guest.book], guest)
        notes += more
    return SideSpec(spec, hero), notes


def entry_labels(army, result) -> list[tuple[str, str]]:
    """(key, text) of the list entries that can be picked as a side: the
    hosts with their joined Hero, and every unit not joined to another."""
    guests = {u.joined_to: u for u in army.units if u.joined_to}
    out = []
    for u in army.units:
        if u.joined_to:
            continue
        e = result.entries.get(u.key)
        pts = e.points if e else 0
        g = guests.get(u.key)
        if g is not None:
            ge = result.entries.get(g.key)
            pts += ge.points if ge else 0
        name = u.label or u.unit_name or u.unit_id
        text = f"{name}" + (f" + {g.label or g.unit_name}" if g else "") + \
            (" [combined]" if u.combined else "") + f"  ({pts} pts)"
        if e is not None and not e.valid:
            text += "  [invalid]"
        out.append((u.key, text))
    return out


# --- running -----------------------------------------------------------------


OTHER = {"att": "def", "def": "att"}


def _buffs(sreg, setup, books, warnings) -> tuple[tuple, list, list]:
    """(extra marks, attacker grants, target grants) of the buff toggles;
   a toggle whose spell is not in the side's book is reported."""
    marks, grants = [], {"att": [], "def": []}
    for side, key in setup.buffs:
        if key.startswith(SP.RULE_BUFF):                # a buff rule
            rid = key[len(SP.RULE_BUFF):]
            g = SP.rule_buff_grants(sreg.reg, rid)
            if not g:
                warnings.append(f"buff rule {key!r} has no semantics")
            sem = sreg.reg.lookup(rid)
            debuff = sem is not None and sem.handler == "debuff"
            grants[OTHER[side] if debuff else side] += \
                _foreign(g) if debuff else g
            continue
        book = books[side]
        sem = next((s for s in sreg.spells(book) if s.key == key),
                   None) if book is not None else None
        if sem is None:
            warnings.append(f"spell {key!r} not found in the {side} book")
        elif sem.kind == "mark" and side == "att":
            marks.append(sem.mark_id)
        elif sem.kind == "grant":
            grants[side] += list(sem.grants)
        elif sem.kind == "debuff":                      # the enemy
            grants[OTHER[side]] += _foreign(sem.grants)
    return tuple(marks), grants["att"], grants["def"]


def _foreign(grants) -> list:
    """Grants given by an ENEMY rule or spell (debuffs): their rules are
    marked foreign, so Unstoppable drops their negative modifiers."""
    return [(replace(r, foreign=True), to, a) for r, to, a in grants]


def _granted(ru, hero, ss: SideSetup, grants, attack):
    if not grants:
        return ru, hero, ss
    refs = SP.weapon_grants(grants, attack)
    off = frozenset(SP.grant_weapon(w, refs) for w in ss.off)
    return SP.grant(ru, grants, attack), SP.grant(hero, grants, attack), \
        replace(ss, off=off)


def prepare(reg, att: SideSpec, att_ss: SideSetup, tgt: SideSpec,
            tgt_ss: SideSetup, setup: Setup, sreg=None, **kw):
    """(attacker Side, target Side, Options, notes) of an analysis: the
    spells of the setup (sreg: rules.spells.SpellRegistry) applied (buff
    toggles; the damage spell when setup.attack == 'spell'); notes: join
    problems and unknown spells."""
    a_ru, a_h = att.resolved()
    t_ru, t_h = tgt.resolved()
    notes = att.issues() + tgt.issues()
    marks, plan = (), None
    if sreg is not None:
        books = {"att": att.unit.cfg.book, "def": tgt.unit.cfg.book}
        marks, g_att, g_def = _buffs(sreg, setup, books, notes)
        a_ru, a_h, att_ss = _granted(a_ru, a_h, att_ss, g_att, setup.attack)
        t_ru, t_h, tgt_ss = _granted(t_ru, t_h, tgt_ss, g_def, setup.attack)
        if setup.attack == "spell":
            sem = next((s for s in sreg.spells(books["att"])
                        if s.key == setup.spell), None)
            if sem is None or sem.kind != "damage":
                raise ValueError("pick a damage spell of the attacker's book")
            plan = SP.plan(sem, reg, a_ru, a_h, setup.friendly_tokens,
                           setup.enemy_tokens, kw.get("exact", False),
                           setup.conduit)
    if setup.attack == "spell" and plan is None:
        raise ValueError("spells need the spell semantics (spells.json)")
    opts = setup.options(spell=plan, **kw)
    if marks:
        opts = replace(opts, ctx=replace(opts.ctx,
                                         marks=opts.ctx.marks + marks))
    return make_side(a_ru, a_h, att_ss), make_side(t_ru, t_h, tgt_ss), \
        opts, notes


def run(reg, att: SideSpec, att_ss: SideSetup, tgt: SideSpec,
        tgt_ss: SideSetup, setup: Setup, sreg=None, **kw) -> Analysis:
    """analyzer_core.analyse() on two picked sides (prepare()); join
    problems and unknown spells are added to the warnings (the analysis
    still runs)."""
    a_side, t_side, opts, notes = prepare(reg, att, att_ss, tgt, tgt_ss,
                                          setup, sreg, **kw)
    a = analyse(reg, a_side, t_side, opts)
    return replace(a, warnings=tuple(notes) + a.warnings) if notes else a
