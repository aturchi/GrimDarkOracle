"""Editing state of one unit's upgrade choices: the pure model behind the
option panel (shared by the Analyzer, the List Editor and the Game
Assistant). No tkinter.

    cfg = UnitConfig(book, unit_id, choices)
    for sv in cfg.sections(): ...          # what the panel shows
    cfg.set_count(package, section, option, n)
    cfg.resolved, cfg.points, cfg.issues, cfg.choices

Panel modes come from options_core.caps: 'radio' =
at most one option, count 1 (a combobox); 'check' = each option 0 / 1;
'count' = a spinbox per option, bounded per option and per section.
Every change re-runs resolve(). Sections the book disables for the unit
are hidden; sections whose targets are absent are shown disabled. A
choice that no longer applies (its chain was undone) is KEPT and
reported, never pruned silently: prune() removes such
choices on request. Per-model placement (Choice.models) is preserved
while an option's count is unchanged; changing the count returns it to
automatic placement (the placement editor belongs to the List Editor).
"""
from dataclasses import dataclass

from grimdarkoracle.data.af_book import Book
from grimdarkoracle.data.resolve import Choice, ResolvedUnit, resolve


@dataclass(frozen=True)
class OptionView:
    uid: str
    label: str
    cost: int | None                # points for this unit (None: unpriced)
    wanted: int                     # count asked for
    applied: int                    # count resolve() applied
    limit: int                      # highest count the panel offers now


@dataclass(frozen=True)
class SectionView:
    package: str
    uid: str
    label: str
    mode: str                       # radio / check / count
    total: int                      # cap on the sum of the counts
    enabled: bool                   # targets present (or a choice applied)
    options: tuple[OptionView, ...]

    @property
    def selected(self) -> str | None:
        """Radio: the option asked for, if any."""
        return next((o.uid for o in self.options if o.wanted), None)


class UnitConfig:
    def __init__(self, book: Book, unit_id: str, choices=()):
        if unit_id not in book.units:
            raise KeyError(f"unit {unit_id!r} not in {book.name}")
        self.book, self.unit = book, book.units[unit_id]
        self._choices = [c for c in choices]
        self._resolved: ResolvedUnit | None = None

    # --- state -------------------------------------------------------------------

    @property
    def choices(self) -> tuple[Choice, ...]:
        return tuple(self._choices)

    @property
    def resolved(self) -> ResolvedUnit:
        if self._resolved is None:
            self._resolved = resolve(self.book, self.unit.id, self._choices)
        return self._resolved

    @property
    def points(self) -> int:
        return self.resolved.points

    @property
    def issues(self) -> tuple[str, ...]:
        return self.resolved.issues

    def _wanted(self, package, section) -> dict:
        return {c.option: c.count for c in self._choices
                if (c.package, c.section) == (package, section)}

    def _section(self, package, section):
        pkg = self.book.packages.get(package)
        return None if pkg is None else next(
            (s for s in pkg.sections if s.uid == section), None)

    # --- what the panel shows -------------------------------------------------------

    def sections(self) -> list[SectionView]:
        out = []
        for st in self.resolved.sections:
            if st.uid in self.unit.disabled_sections:
                continue
            sec = self._section(st.package, st.uid)
            wanted = self._wanted(st.package, st.uid)
            applied = dict(st.counts)
            caps = st.caps
            used = sum(wanted.values())
            opts = []
            for o in sec.options:
                w = wanted.get(o.uid, 0)
                if caps.mode == "count":
                    limit = max(0, min(caps.per_option,
                                       caps.total - used + w))
                else:
                    limit = 1
                opts.append(OptionView(o.uid, o.label,
                                       o.cost_for(self.unit.id), w,
                                       applied.get(o.uid, 0), limit))
            out.append(SectionView(st.package, st.uid, st.label, caps.mode,
                                   caps.total, st.enabled, tuple(opts)))
        return out

    def section(self, package: str, section: str) -> SectionView:
        return next(s for s in self.sections()
                    if (s.package, s.uid) == (package, section))

    # --- changes ---------------------------------------------------------------------

    def set_count(self, package: str, section: str, option: str,
                  n: int) -> int:
        """Ask for 'option' n times; returns the count actually set after
        the panel caps (radio: picking an option drops the others)."""
        sv = self.section(package, section)
        ov = next((o for o in sv.options if o.uid == option), None)
        if ov is None:
            raise KeyError(f"option {option!r} not in section {sv.label!r}")
        n = max(0, min(int(n), ov.limit))
        if n and not sv.enabled:
            raise ValueError(f"section {sv.label!r} is not available")
        kept = []
        for c in self._choices:
            same = (c.package, c.section) == (package, section)
            if same and (c.option == option or sv.mode == "radio" and n):
                continue
            kept.append(c)
        if n:
            old = next((c for c in self._choices
                        if (c.package, c.section, c.option) ==
                        (package, section, option)), None)
            models = old.models if old is not None and old.count == n else ()
            kept.append(Choice(package, section, option, n, models))
        self._set(kept)
        return n

    def select(self, package: str, section: str, option: str | None) -> None:
        """Radio / check helper: option None clears the section."""
        if option is None:
            self._set([c for c in self._choices
                       if (c.package, c.section) != (package, section)])
        else:
            self.set_count(package, section, option, 1)

    def clear(self) -> None:
        self._set([])

    def invalid(self) -> list[Choice]:
        """Choices asked for that resolve() did not apply in full."""
        applied = {(st.package, st.uid, o): n for st in self.resolved.sections
                   for o, n in st.counts}
        return [c for c in self._choices
                if applied.get((c.package, c.section, c.option), 0) < c.count]

    def prune(self) -> list[Choice]:
        """Drop the invalid choices (explicit user action); returns them.
        resolve() applies an option all or nothing, so an invalid choice
        is dropped whole."""
        bad = self.invalid()
        self._set([c for c in self._choices if c not in bad])
        return bad

    def _set(self, choices) -> None:
        """New choices, kept in book order (sections, then options) so a
        saved list does not depend on the order of the clicks."""
        rank = {}
        for p in self.book.unit_packages(self.unit):
            for s in p.sections:
                for o in s.options:
                    rank.setdefault((p.uid, s.uid, o.uid), len(rank))
        self._choices = sorted(choices, key=lambda c: rank.get(
            (c.package, c.section, c.option), len(rank)))
        self._resolved = None
