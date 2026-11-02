"""Upgrade variants of one unit, analysed side by side.

A variant is the same unit with a different set of choices. The usual
question - "which option of this section is worth its points?" - is
answered by section_variants(): one variant per option of a section, the
other choices unchanged. compare() runs the same
analysis on every variant and returns comparison pins, so the comparison
matrix shows the points-efficiency metrics with their differences
against the first variant.

Pure: the caller passes the book and a function that analyses a Variant
(it decides whether the variant attacks or is the target).
"""
from dataclasses import dataclass

from grimdarkoracle.app import comparison
from grimdarkoracle.data.af_book import Book
from grimdarkoracle.data.resolve import Choice, ResolvedUnit, resolve

NONE_LABEL = "(none)"


@dataclass(frozen=True)
class Variant:
    label: str
    choices: tuple[Choice, ...]
    unit: ResolvedUnit


def _section(book: Book, package: str, section: str):
    pkg = book.packages.get(package)
    sec = None if pkg is None else next(
        (s for s in pkg.sections if s.uid == section), None)
    if sec is None:
        raise ValueError(f"section {section!r} not in package {package!r}")
    return sec


def section_variants(book: Book, unit_id: str, choices, package: str,
                     section: str, include_none: bool = True
                     ) -> list[Variant]:
    """One variant per option of a section, with the other 'choices'
    kept: radio / check sections take the option once, count
    sections take it as many times as the section allows on the unit
    without this section's choices. 'include_none' adds the unit without
    any option of the section. Choices made invalid by the change (a
    chain that needed the removed option) stay in each variant's
    ResolvedUnit.issues."""
    sec = _section(book, package, section)
    base = tuple(c for c in choices
                 if not (c.package == package and c.section == section))
    ru0 = resolve(book, unit_id, base)
    st = next((s for s in ru0.sections
               if s.package == package and s.uid == section), None)
    if st is None or not st.enabled:
        raise ValueError(f"section {sec.label!r} is not available to the "
                         "unit with these choices")
    out = [Variant(NONE_LABEL, base, ru0)] if include_none else []
    n = st.caps.per_option if st.caps.mode == "count" else 1
    for opt in sec.options:
        cs = base + (Choice(package, section, opt.uid, n),)
        label = opt.label if n == 1 else f"{n}x {opt.label}"
        out.append(Variant(label, cs, resolve(book, unit_id, cs)))
    return out


def compare(variants, run, context: str = "") -> list[dict]:
    """Pins of 'run(variant)' (an analyzer_core.Analysis) for every variant,
    in order: comparison.matrix() shows them against the first. 'run'
    receives the Variant, so it can rebuild a Combined Unit or a joined
    side from variant.choices, or use variant.unit directly."""
    return [comparison.make_pin(v.label, run(v), context) for v in variants]
