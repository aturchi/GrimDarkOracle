"""Local unit editor core: the forms of the editor as TEXT in the
syntax of the Army Forge labels, parsed into local_books dicts. Pure.

    rules:    Fearless, Tough(3), Lucky Charm
    weapons:  one per line, as on an Army Forge card:
              5x Las Rifle (24", A1, AP(1))     Knife (A1)
    gains of an option, separated by ';':
              Plasma Gun (24", A1, AP(4)); Tough(3)

Rule names resolve, in order, to the custom rules of the local book, the
core rules, then any loaded book's definition. A weapon line without "Nx" is
carried by every model of the unit (count = size). A unit's upgrade sections
live in ONE package of its own; uids of sections and options are kept when
edited, so saved lists stay linked.
"""
import re
from dataclasses import dataclass, field

from grimdarkoracle.data import af_book as ab
from grimdarkoracle.data import local_books as LB

_WEAPON = re.compile(r"^(?:(\d+)x\s+)?(.+?)\s+\((.*)\)\s*$", re.IGNORECASE)
_RULE = re.compile(r"^([^()]+?)\s*(?:\(([^()]*)\))?$")
_ATTACKS = re.compile(r"^A(\d+)$", re.IGNORECASE)
_RANGE = re.compile(r'^(\d+)\s*(?:"|in|”)$')


def split_top(text: str, sep: str = ",") -> list[str]:
    """Split on 'sep' outside parentheses; parts stripped, empty dropped."""
    out, depth, cur = [], 0, ""
    for ch in text:
        depth += (ch == "(") - (ch == ")")
        if ch == sep and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [p.strip() for p in out if p.strip()]


class RuleResolver:
    """Rule name -> (id, name): custom rules of the book, core, books."""

    def __init__(self, reg, raw: dict):
        self.custom = {r["name"].lower(): r["id"]
                       for r in LB.rules_of(raw)}
        self.core = {d.name.lower(): d.id for d in reg.core.values()}
        self.other: dict = {}
        for rid, d in sorted(reg.defs.items()):
            self.other.setdefault(d.name.lower(), rid)
        self.names = {**{k: v for k, v in self.other.items()},
                      **self.core, **self.custom}
        self._label = {}
        for r in LB.rules_of(raw):
            self._label[r["id"]] = r["name"]
        for rid, d in reg.defs.items():
            self._label.setdefault(rid, d.name)

    def find(self, name: str):
        rid = self.names.get(name.strip().lower())
        return (rid, self._label.get(rid, name.strip())) if rid else None


def _rating(text):
    t = (text or "").strip()
    if not t:
        return None
    return int(t) if t.lstrip("-").isdigit() else t


def parse_rule(token: str, res: RuleResolver):
    """(rule_ref dict, error)."""
    m = _RULE.match(token.strip())
    if not m:
        return None, f"cannot read rule {token!r}"
    hit = res.find(m.group(1))
    if hit is None:
        return None, f"unknown rule {m.group(1).strip()!r} (create it as a " \
                     "custom rule first)"
    return LB.rule_ref(hit[0], hit[1], _rating(m.group(2))), None


def parse_rules(text: str, res: RuleResolver):
    out, errors = [], []
    for tok in split_top(text):
        r, err = parse_rule(tok, res)
        (errors.append(err) if err else out.append(r))
    return out, errors


def parse_weapon(text: str, res: RuleResolver, default_count: int = 1):
    """(weapon dict, errors) of 'Nx Name (24", A1, AP(1))'."""
    m = _WEAPON.match(text.strip())
    if not m:
        return None, [f"cannot read weapon {text!r}: Name (24\", A1, rules)"]
    count = int(m.group(1)) if m.group(1) else default_count
    rng, attacks, rules, errors = 0, None, [], []
    for part in split_top(m.group(3)):
        if _RANGE.match(part):
            rng = int(_RANGE.match(part).group(1))
        elif _ATTACKS.match(part):
            attacks = int(_ATTACKS.match(part).group(1))
        else:
            r, err = parse_rule(part, res)
            (errors.append(err) if err else rules.append(r))
    if attacks is None:
        errors.append(f"{m.group(2)}: attacks missing (A1, A2...)")
    if errors:
        return None, errors
    try:
        return LB.weapon(m.group(2).strip(), rng, attacks, rules, count), []
    except LB.LocalBookError as exc:
        return None, [str(exc)]


def is_weapon_text(token: str) -> bool:
    m = _WEAPON.match(token.strip())
    return bool(m) and any(_ATTACKS.match(p) for p in split_top(m.group(3)))


def parse_gains(text: str, res: RuleResolver):
    """(gains, errors) of 'weapon; rule; ...' (an option)."""
    out, errors = [], []
    for tok in split_top(text, ";"):
        if is_weapon_text(tok):
            w, errs = parse_weapon(tok, res, 1)
            errors += errs
            if w:
                out.append(w)
        else:
            r, err = parse_rule(tok, res)
            (errors.append(err) if err else out.append(r))
    return out, errors


def gains_text(gains) -> str:
    return "; ".join(g["label"] for g in gains)


def parse_quant(text: str):
    """'' -> None; 'all' / 'any' -> (kind,); 'up to 2'; '1' -> exactly."""
    t = " ".join(text.lower().split())
    if not t:
        return None, None
    if t in ("all", "any"):
        return (t,), None
    if t.startswith("up to ") and t[6:].isdigit():
        return ("up to", int(t[6:])), None
    if t.isdigit():
        return ("exactly", int(t)), None
    return None, f"quantity {text!r}: empty, a number, 'up to N', any, all"


def quant_text(q) -> str:
    if not q:
        return ""
    if q["type"] == "exactly":
        return str(q.get("value"))
    if q["type"] == "up to":
        return f"up to {q.get('value')}"
    return q["type"]


@dataclass
class OptionDraft:
    gains: str                      # parse_gains syntax
    cost: int = 0
    uid: str = ""


@dataclass
class SectionDraft:
    label: str
    variant: str = "upgrade"        # upgrade / replace / attachment
    targets: str = ""               # comma-separated weapon names
    model: bool = False             # per-model section
    affects: str = ""               # parse_quant syntax
    select: str = ""
    options: list = field(default_factory=list)
    uid: str = ""


@dataclass
class UnitDraft:
    name: str = "New unit"
    size: int = 1
    quality: int = 4
    defense: int = 4
    cost: int = 0
    rules: str = ""
    weapons: str = ""               # one weapon per line
    sections: list = field(default_factory=list)
    uid: str = ""

    @classmethod
    def from_raw(cls, raw: dict, unit_id: str) -> "UnitDraft":
        u = LB.find_unit(raw, unit_id)
        secs = []
        for p in LB.packages_of(raw):
            if p["uid"] not in u["upgrades"]:
                continue
            for s in p["sections"]:
                secs.append(SectionDraft(
                    s["label"], s["variant"], ", ".join(s.get("targets", [])),
                    bool(s.get("model")), quant_text(s.get("affects")),
                    quant_text(s.get("select")),
                    [OptionDraft(gains_text(o["gains"]), next(
                        (c["cost"] for c in o["costs"] if c["unitId"] ==
                         unit_id), 0), o["uid"]) for o in s["options"]],
                    s["uid"]))
        return cls(u["name"], u["size"], u["quality"], u["defense"],
                   u["cost"], ", ".join(r["label"] for r in u["rules"]),
                   "\n".join(w["label"] for w in u["weapons"]), secs,
                   u["id"])


def _sections(draft: UnitDraft, res, errors) -> list:
    out = []
    for n, sd in enumerate(draft.sections, 1):
        where = f"section {n} ({sd.label or 'no label'})"
        if not sd.label.strip():
            errors.append(f"{where}: label missing")
        if sd.variant not in ab.VARIANTS:
            errors.append(f"{where}: variant must be one of {ab.VARIANTS}")
        targets = split_top(sd.targets)
        if sd.variant in ("replace", "attachment") and not targets:
            errors.append(f"{where}: {sd.variant} needs targets")
        if sd.variant == "upgrade" and targets:
            errors.append(f"{where}: upgrade sections have no targets")
        aff, e1 = parse_quant(sd.affects)
        sel, e2 = parse_quant(sd.select)
        errors += [f"{where}: {e}" for e in (e1, e2) if e]
        if not sd.options:
            errors.append(f"{where}: no options")
        opts = []
        for od in sd.options:
            gains, errs = parse_gains(od.gains, res)
            errors += [f"{where}: {e}" for e in errs]
            if not gains and not errs:
                errors.append(f"{where}: an option without gains")
            if od.cost < 0:
                errors.append(f"{where}: negative cost")
            opts.append((od, gains))
        out.append((sd, targets, aff, sel, opts))
    return out


def save_unit(raw: dict, draft: UnitDraft, res: RuleResolver
              ) -> tuple[str | None, list[str]]:
    """Write the draft into the local book (new or existing unit, its own
    package rebuilt with stable uids). Nothing changes if any error."""
    errors = []
    rules, errs = parse_rules(draft.rules, res)
    errors += errs
    weapons = []
    for line in (x for x in draft.weapons.splitlines() if x.strip()):
        w, errs = parse_weapon(line, res, draft.size)
        errors += errs
        if w:
            weapons.append(w)
    secs = _sections(draft, res, errors)
    try:
        unit = LB.unit(raw, draft.name.strip(), draft.size, draft.quality,
                       draft.defense, draft.cost, rules, weapons,
                       uid=draft.uid or None)
    except LB.LocalBookError as exc:
        errors.append(str(exc))
    if not draft.name.strip():
        errors.append("name missing")
    if errors:
        return None, errors
    uid = LB.put_unit(raw, unit)
    _package(raw, uid, secs)
    return uid, []


def _package(raw, uid, secs) -> None:
    u = LB.find_unit(raw, uid)
    others = {p for x in raw["units"] if x["id"] != uid for p in x["upgrades"]}
    own = [p for p in LB.packages_of(raw)
           if p["uid"] in u["upgrades"] and p["uid"] not in others]
    pkg = own[0] if own else None
    old_s = {s["uid"]: s for s in pkg["sections"]} if pkg else {}
    old_o = {o["uid"] for s in old_s.values() for o in s["options"]}
    if pkg is None and secs:
        pkg = {"uid": LB.next_id(raw, "package"), "hint": u["name"],
               "sections": []}
        LB.packages_of(raw).append(pkg)
        u["upgrades"].append(pkg["uid"])
    if pkg is None:
        return
    pkg["sections"] = []
    # Removed sections / options keep their uids reserved: a saved list
    # naming one must not link to a new, different choice.
    reserved = set(old_s) | old_o
    for sd, targets, aff, sel, opts in secs:
        s = LB.section(sd.label.strip(), sd.variant, [], targets, sd.model,
                       aff, sel)
        s["uid"] = sd.uid if sd.uid in old_s else \
            LB.next_id(raw, "section", reserved)
        pkg["sections"].append(s)
        for od, gains in opts:
            label = "; ".join(g["label"] for g in gains)
            o = LB.option(label, gains, {uid: od.cost})
            o["uid"] = od.uid if od.uid in old_o else \
                LB.next_id(raw, "option", reserved)
            s["options"].append(o)
    kept = {x for s in pkg["sections"]
            for x in [s["uid"]] + [o["uid"] for o in s["options"]]}
    LB.retire(raw, sorted(reserved - kept))
    if not pkg["sections"]:
        LB.retire(raw, [pkg["uid"]])
        LB.packages_of(raw).remove(pkg)
        u["upgrades"].remove(pkg["uid"])
