"""The reasoning behind a weapon row, in words.

Lines like

    Hit     Quality 4+, modifier +1 -> hits on 3+ (66.7%); a 6: +1 hit
    Block   Defense 4+, AP 1, cover +1 -> blocks on 4+ (50.0%)
    Sources Targeting Visor: hit_mod +1; Rending; Blast(3)

show what the engine actually used for one weapon at the start of the
attack (analyzer_core.WeaponRow.audit = sequence.AuditPart): nothing here
recomputes a modifier, it only reads the final AttackSpec / TargetSpec
and the sources the modifier layer wrote. That is how a flag left ticked
from an earlier analysis gets caught. Pure; the window shows the text.
"""
from grimdarkoracle.engine import gf_math as G


def _pct(p) -> str:
    return f"{float(p) * 100:.1f}%"


def _needed(target: int, mod: int, spec) -> str:
    """The roll needed, as the player reads it (auto faces of 'spec')."""
    return f"{7 - G.success_faces(target, mod, G.auto_of(spec))}+"


def _hit(spec) -> str:
    if spec.auto_hit:
        return "fixed hits: no roll, no 6s (spell)"
    if spec.fatigued:
        f = spec.fatigue_on
        return f"Fatigued: hits only on an unmodified {f}" + \
            ("" if f == 6 else "+") + f" ({_pct((7 - f) / 6)}), no special " \
            "rule triggers"
    miss, plain, six = G.hit_probs(spec)
    mod = f", modifier {spec.hit_mod:+d}" if spec.hit_mod else ""
    out = f"Quality {spec.quality}+{mod} -> hits on " \
          f"{_needed(spec.quality, spec.hit_mod, spec)} ({_pct(plain + six)})"
    extra = []
    if spec.extra_hits_on_6:
        extra.append(f"+{spec.extra_hits_on_6} hit(s)")
    if spec.ap_on_6:
        extra.append(f"AP +{spec.ap_on_6}")
    if extra:
        out += "; on a 6: " + ", ".join(extra)
    return out


def _block(spec, target, six: bool = False) -> str:
    ap = G.effective_ap(spec, six)
    on = G.reroll_face(spec)
    block, _fail, _one = G.block_probs(target, ap, on)
    bits = [f"Defense {target.defense}+"]
    if ap:
        bits.append(f"AP {ap}")
    if target.defense_mod:
        bits.append(f"modifier {target.defense_mod:+d} (cover included)")
    need = _needed(target.defense, target.defense_mod - ap, target)
    out = ", ".join(bits) + f" -> blocks on {need} ({_pct(block)})"
    if on:
        out += "; a 6 is re-rolled" if on == 6 else \
            f"; a successful {on}+ is re-rolled"
    return out


def part_lines(part, attacks: int | None = None) -> list[str]:
    """Lines of one AuditPart."""
    s, t = part.spec, part.target
    out = [f"Attacks {attacks if attacks is not None else s.attacks}",
           f"Hit     {_hit(s)}"]
    b = G.blast_multiplier(s, part.models)
    if s.blast > 1:
        out.append(f"Blast   x{b} (Blast({s.blast}), {part.models} model(s) "
                   "in the target)")
    if part.takedown_model is not None:
        out.append(f"Target  Takedown on model #{part.takedown_model + 1} "
                   "(as a unit of one)")
    out.append(f"Block   {_block(s, t)}")
    if s.ap_on_6 and not s.auto_hit and not s.fatigued:
        out.append(f"        hits from a 6: {_block(s, t, six=True)}")
    if s.shred:
        out.append(f"Shred   +{s.shred} wound(s) per unmodified 1 on a block")
    if s.deadly > 1:
        out.append(f"Deadly  x{s.deadly} per wound, on one model, no carry")
    if t.regeneration:
        out.append("Regen   ignored by this weapon" if s.ignores_regen else
                   f"Regen   each wound ignored on {t.regen_on}+")
    for on in t.wards:
        out.append(f"Ward    each wound ignored on {on}+")
    if part.sources:
        out.append("Sources " + "; ".join(part.sources))
    return out


def row_text(row) -> str:
    """The audit of one analyzer_core.WeaponRow (all its parts)."""
    head = f"{row.name}  ({row.count} x, {row.attacks} attacks, "\
           f"phase {row.phase})"
    if not row.audit:
        return head + "\n  nothing attacks at the start (no living models)"
    lines = [head]
    for k, part in enumerate(row.audit):
        if len(row.audit) > 1:
            lines.append(f"  part {k + 1}")
        lines += ["  " + x for x in part_lines(part)]
    return "\n".join(lines)


def analysis_text(analysis) -> str:
    """Every weapon row of an analysis, for an export or a log."""
    return "\n\n".join(row_text(r) for r in analysis.rows)
