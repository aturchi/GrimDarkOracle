"""Re-link saved list entries to the current books.

1. match unit / section / option by uid;
2. if a uid is missing, match by label within the same book (unit name;
   section label + occurrence; option label), accept only a unique match
   and report the rewritten uids ("relinked");
3. otherwise the choice is INVALID: kept in the list, reported, and not
   passed to resolve() - never pruned silently.

Pure module: returns new ChoiceRefs; the caller decides whether to store
the rewritten uids (the List Editor does, on save).
"""
from dataclasses import dataclass, field, replace

from grimdarkoracle.data.army_list import ChoiceRef, ListUnit
from grimdarkoracle.data.army_list import norm_label as _norm


@dataclass
class LinkResult:
    unit_id: str | None                     # None: unit not found
    choices: list[ChoiceRef] = field(default_factory=list)    # valid, A
    choices_b: list[ChoiceRef] | None = None                  # valid, B
    relinked: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    # The refs that did not link (A, B), kept so an editor can store them
    # back untouched (never pruned silently).
    lost: list[ChoiceRef] = field(default_factory=list)
    lost_b: list[ChoiceRef] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.relinked)


def find_unit(book, unit_id: str, unit_name: str):
    """(unit, relinked?) or (None, False)."""
    if unit_id in book.units:
        return book.units[unit_id], False
    named = [u for u in book.units.values()
             if _norm(u.name) == _norm(unit_name)]
    return (named[0], True) if len(named) == 1 else (None, False)


def _by_uid(book, unit, ref: ChoiceRef):
    if ref.package not in unit.packages or ref.package not in book.packages:
        return None
    sec = next((s for s in book.packages[ref.package].sections
                if s.uid == ref.section), None)
    if sec is None or not any(o.uid == ref.option for o in sec.options):
        return None
    return ref


def _by_label(book, unit, ref: ChoiceRef):
    """Unique (package, section, option) matching the fingerprint."""
    same = [(p.uid, s) for p in book.unit_packages(unit) for s in p.sections
            if _norm(s.label) == _norm(ref.section_label)]
    # Prefer the stored occurrence; fall back to any same-label section
    # holding exactly one option with the stored label.
    ordered = ([same[ref.section_nth - 1]] if 0 < ref.section_nth <= len(same)
               else []) + same
    for pu, sec in ordered:
        opts = [o for o in sec.options
                if _norm(o.label) == _norm(ref.option_label)]
        if len(opts) == 1:
            return replace(ref, package=pu, section=sec.uid,
                           option=opts[0].uid)
    return None


def _link_choices(book, unit, refs, tag, result, lost):
    out = []
    for ref in refs:
        hit = _by_uid(book, unit, ref)
        if hit is None and ref.section_label and ref.option_label:
            hit = _by_label(book, unit, ref)
            if hit is not None:
                result.relinked.append(
                    f"{tag}{ref.section_label!r} / {ref.option_label!r}")
        if hit is None:
            result.invalid.append(f"{tag}choice {ref.section_label!r} / "
                                  f"{ref.option_label!r} no longer exists")
            lost.append(ref)
        else:
            out.append(hit)
    return out


def link_unit(book, lu: ListUnit) -> LinkResult:
    """Link one list entry to 'book' (None if the book is missing)."""
    if book is None:
        return LinkResult(None, invalid=[f"book {lu.book!r} not available"])
    unit, renamed = find_unit(book, lu.unit_id, lu.unit_name)
    if unit is None:
        return LinkResult(None, invalid=[f"unit {lu.unit_name!r} "
                                         f"({lu.unit_id}) no longer exists"])
    result = LinkResult(unit.id)
    if renamed:
        result.relinked.append(f"unit {lu.unit_name!r}")
    result.choices = _link_choices(book, unit, lu.choices, "", result,
                                   result.lost)
    if lu.choices_b is not None:
        result.choices_b = _link_choices(book, unit, lu.choices_b,
                                         "copy B: ", result, result.lost_b)
    return result
