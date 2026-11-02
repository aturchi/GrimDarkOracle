"""Setup panels of the Analyzer: thin Tk
views over app.setup_model.

SetupPanel edits a Setup: the attack (shooting / melee / a damage spell),
its circumstances, the melee options, the casting tokens, the token-rule
toggles (Marks on the target, Spotter tokens, Versatile choices of the
attacker) and the buff spells (assumed cast). Controls
that mean nothing for the current attack are greyed (Setup.relevant).

SidePanel edits the SideSetup of one unit: wounds already taken (placed
by the allocation order), not moved / Fatigued / Shaken, a friendly
Tough(9)+ Hero within 6" for Morale, and which weapons are switched off.
"""
import tkinter as tk
from tkinter import ttk

from grimdarkoracle.app import defense_choice as DC
from grimdarkoracle.app import setup_model as S
from grimdarkoracle.ui import ui_utils as ui

COVER_LABELS = {None: "none", "terrain": "Cover terrain",
                "sight_blocker": "Sight Blocker"}
TIE_LABELS = {"none": "nobody tests", "defender": "charged unit wins",
              "attacker": "charger wins"}
NO_HERO = "-"
HERO_QUALITIES = [NO_HERO] + [f"{q}+" for q in range(2, 7)]


def weapon_text(w) -> str:
    """Weapon profile on one line, built from its fields (Army Forge labels
    are missing on weapons granted by options and may carry an "Nx")."""
    bits = ([f'{w.range}"'] if w.range else []) + [f"A{w.attacks}"]
    bits += [r.label or r.name for r in w.rules]
    return f"{w.name} ({', '.join(bits)})"


def _key(mapping, label):
    return next(k for k, v in mapping.items() if v == label)


class SetupPanel(ttk.LabelFrame):
    """on_change(setup) after every edit."""

    def __init__(self, parent, on_change=None):
        super().__init__(parent, text="Attack")
        self.on_change = on_change
        self.v = {"attack": tk.StringVar(value="shooting"),
                  "distance": tk.StringVar(value="12"),
                  "action": tk.StringVar(value="hold"),
                  "cover": tk.StringVar(value=COVER_LABELS[None]),
                  "line_of_sight": tk.BooleanVar(value=True),
                  "crossing": tk.BooleanVar(value=False),
                  "strike_back": tk.BooleanVar(value=True),
                  "tie": tk.StringVar(value=TIE_LABELS["none"]),
                  "spotter_tokens": tk.StringVar(value="0"),
                  "ap_spotter_tokens": tk.StringVar(value="0"),
                  "spell": tk.StringVar(value=""),
                  "friendly_tokens": tk.StringVar(value="0"),
                  "enemy_tokens": tk.StringVar(value="0"),
                  "charge_distance": tk.StringVar(value="6"),
                  "ambushed": tk.BooleanVar(value=False),
                  "conduit": tk.BooleanVar(value=False)}
        self.spell_keys: dict = {}          # label -> spell key
        self.buff_vars: dict = {}           # (side, key) -> BooleanVar
        self.w: dict = {}
        self.mark_vars: dict = {}           # rule id -> BooleanVar
        self.versatile_vars: dict = {}      # rule id -> (StringVar, labels)
        self.versatile_first: dict = {}
        self._build()
        self._sync()

    # --- building ------------------------------------------------------------

    def _row(self, label, widget_fn, name, tip=None):
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=4, pady=1)
        ttk.Label(row, text=label, width=16).pack(side=tk.LEFT)
        w = widget_fn(row)
        w.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.w[name] = w
        if tip:
            ui.tip(w, tip)
        return w

    def _build(self):
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=4, pady=2)
        for value, text in (("shooting", "Shooting"),
                            ("melee", "Melee (charge)"), ("spell", "Spell")):
            ttk.Radiobutton(row, text=text, value=value,
                            variable=self.v["attack"],
                            command=self._edited).pack(side=tk.LEFT, padx=4)
        v = self.v
        self._row("Distance (\")", lambda r: ttk.Spinbox(
            r, from_=0, to=96, width=5, textvariable=v["distance"],
            command=self._edited), "distance")
        self._row("Action", lambda r: ttk.Combobox(
            r, values=S.SHOOT_ACTIONS, textvariable=v["action"],
            state="readonly", width=10), "action",
            "Rush and Charge do not allow shooting")
        self._row("Target cover", lambda r: ttk.Combobox(
            r, values=list(COVER_LABELS.values()), textvariable=v["cover"],
            state="readonly", width=14), "cover",
            "Cover terrain: +1 to Defense against shooting; Blast ignores "
            "it, Indirect with Hold ignores Sight Blockers")
        self._row("", lambda r: ttk.Checkbutton(
            r, text="Line of sight", variable=v["line_of_sight"],
            command=self._edited), "line_of_sight",
            "Without line of sight only Indirect weapons with Hold shoot")
        self._row("", lambda r: ttk.Checkbutton(
            r, text="Crossing Strike attack", variable=v["crossing"],
            command=self._edited), "crossing",
            "Only Crossing Strike weapons attack, the target gets no cover")
        self._row("", lambda r: ttk.Checkbutton(
            r, text="Strike back", variable=v["strike_back"],
            command=self._edited), "strike_back",
            "The charged unit strikes back (and uses Counter weapons)")
        self._row("Melee tie", lambda r: ttk.Combobox(
            r, values=list(TIE_LABELS.values()), textvariable=v["tie"],
            state="readonly", width=16), "tie")
        self._row("Charge from (\")", lambda r: ttk.Spinbox(
            r, from_=0, to=24, width=5, textvariable=v["charge_distance"],
            command=self._edited), "charge_distance",
            "How far the charger moved: rules acting on charges from over "
            "6\" (Changebound, Warbound, Versatile Defense)")
        self._row("", lambda r: ttk.Checkbutton(
            r, text="Deployed via Ambush this round", variable=v["ambushed"],
            command=self._edited), "ambushed",
            "The attacker deployed via Ambush this round (Ambushing "
            "Piercing Shot)")
        self._row("Spotter tokens", lambda r: ttk.Spinbox(
            r, from_=0, to=12, width=5, textvariable=v["spotter_tokens"],
            command=self._edited), "spotter_tokens",
            "Precision Spotter tokens on the target removed by this attack: "
            "+1 to hit each")
        self._row("AP spotter tokens", lambda r: ttk.Spinbox(
            r, from_=0, to=12, width=5, textvariable=v["ap_spotter_tokens"],
            command=self._edited), "ap_spotter_tokens",
            "Piercing Spotter tokens on the target removed by this attack: "
            "+AP(1) each")
        self._row("Spell", lambda r: ttk.Combobox(
            r, textvariable=v["spell"], state="readonly", width=30), "spell",
            "Damage spells of the attacker's book (a Caster is needed)")
        self.caster_info = ttk.Label(self, text="", foreground=ui.HINT_COLOR)
        self.caster_info.pack(anchor=tk.W, padx=4)
        self._row("Friendly tokens", lambda r: ttk.Spinbox(
            r, from_=0, to=12, width=5, textvariable=v["friendly_tokens"],
            command=self._edited), "friendly_tokens",
            "Spell tokens spent by friendly models within 18\": +1 each")
        self._row("Enemy tokens", lambda r: ttk.Spinbox(
            r, from_=0, to=12, width=5, textvariable=v["enemy_tokens"],
            command=self._edited), "enemy_tokens",
            "Spell tokens spent by enemy models within 18\": -1 each")
        self._row("", lambda r: ttk.Checkbutton(
            r, text="Cast via Spell Conduit", variable=v["conduit"],
            command=self._edited), "conduit",
            "The caster casts from a friendly Spell Conduit's position "
            "(+1 to the casting roll)")
        for name in ("action", "cover", "tie", "spell"):
            self.w[name].bind("<<ComboboxSelected>>",
                              lambda _e: self._edited())
        for name in ("distance", "spotter_tokens", "ap_spotter_tokens",
                     "friendly_tokens",
                     "enemy_tokens", "charge_distance"):
            self.w[name].bind("<Return>", lambda _e: self._edited())
            self.w[name].bind("<FocusOut>", lambda _e: self._edited())
        self.marks_box = ttk.LabelFrame(self, text="Marks on the target")
        self.marks_box.pack(fill=tk.X, padx=4, pady=2)
        self.versatile_box = ttk.LabelFrame(self, text="Versatile")
        self.versatile_box.pack(fill=tk.X, padx=4, pady=2)
        self.buffs_box = ui.tip(ttk.LabelFrame(
            self, text="Spell effects (assumed cast)"),
            "Buff spells of the attacker's book (on the attacker or marking "
            "the target) and of the target's book (protecting the target)")
        self.buffs_box.pack(fill=tk.X, padx=4, pady=2)

    def set_marks(self, marks) -> None:
        """marks: (rule id, name) pairs (setup_model.marks)."""
        old = {rid: v.get() for rid, v in self.mark_vars.items()}
        for w in self.marks_box.winfo_children():
            w.destroy()
        self.mark_vars = {}
        for rid, name in marks:
            var = tk.BooleanVar(value=old.get(rid, False))
            ttk.Checkbutton(self.marks_box, text=name, variable=var,
                            command=self._edited).pack(anchor=tk.W, padx=4)
            self.mark_vars[rid] = var

    def set_versatile(self, menu, defense=()) -> None:
        """menu: (rule id, name, choice labels) of the ATTACKER's Versatile
        rules (setup_model.versatile), 'none' first; defense: the target's
        Versatile Defense menus (app.defense_choice), 'best' first."""
        old = {rid: var.get()
               for rid, (var, _l) in self.versatile_vars.items()}
        for w in self.versatile_box.winfo_children():
            w.destroy()
        self.versatile_vars = {}
        self.versatile_first = {}           # rule id -> "none" / "best"
        if not menu and not defense:
            ttk.Label(self.versatile_box, text="(none)",
                      foreground=ui.HINT_COLOR).pack(anchor=tk.W, padx=4)
        items = [(m, "none") for m in menu] + \
            [((rid, f"{name} [target]", labels), DC.BEST)
             for rid, name, labels in defense]
        for (rid, name, labels), first in items:
            row = ttk.Frame(self.versatile_box)
            row.pack(fill=tk.X, padx=4)
            ttk.Label(row, text=name, width=16).pack(side=tk.LEFT)
            var = tk.StringVar(value=old.get(rid, first))
            if var.get() not in [first] + list(labels):
                var.set(first)
            cb = ttk.Combobox(row, values=[first] + list(labels),
                              textvariable=var, state="readonly", width=16)
            cb.pack(side=tk.LEFT)
            cb.bind("<<ComboboxSelected>>", lambda _e: self._edited())
            self.versatile_vars[rid] = (var, list(labels))
            self.versatile_first[rid] = first

    def set_spells(self, spells, info: str = "") -> None:
        """spells: (key, label) of the attacker's damage spells; info: a
        line about the caster (rating, casting modifier)."""
        old = self.spell_keys.get(self.v["spell"].get())
        self.spell_keys = {label: key for key, label in spells}
        self.w["spell"].configure(values=list(self.spell_keys))
        keep = next((lb for lb, k in self.spell_keys.items() if k == old), "")
        self.v["spell"].set(keep or (spells[0][1] if spells else ""))
        self.caster_info.configure(text=info)

    def set_buffs(self, buffs) -> None:
        """buffs: app.spells.Buff list; ticks kept for the same (side, key)."""
        old = {k: v.get() for k, v in self.buff_vars.items()}
        for w in self.buffs_box.winfo_children():
            w.destroy()
        self.buff_vars = {}
        if not buffs:
            ttk.Label(self.buffs_box, text="(none)",
                      foreground=ui.HINT_COLOR).pack(anchor=tk.W, padx=4)
        for b in buffs:
            k = (b.side, b.key)
            var = tk.BooleanVar(value=old.get(k, False))
            who = "attacker" if b.side == "att" else "target"
            ttk.Checkbutton(self.buffs_box, text=f"{b.label} [{who}]",
                            variable=var, command=self._edited
                            ).pack(anchor=tk.W, padx=4)
            self.buff_vars[k] = var

    # --- state ---------------------------------------------------------------

    @staticmethod
    def _int(var, lo, hi, default):
        try:
            return max(lo, min(hi, int(var.get())))
        except (TypeError, ValueError):
            return default

    def get_setup(self) -> S.Setup:
        v = self.v
        versatile = tuple((rid, labels.index(var.get()))
                          for rid, (var, labels) in self.versatile_vars.items()
                          if var.get() in labels)
        action = v["action"].get()
        return S.Setup(
            attack=v["attack"].get(),
            distance=self._int(v["distance"], 0, 96, 12),
            action=action if action in S.SHOOT_ACTIONS else "hold",
            cover=_key(COVER_LABELS, v["cover"].get()),
            line_of_sight=bool(v["line_of_sight"].get()),
            crossing=bool(v["crossing"].get()),
            marks=tuple(rid for rid, var in self.mark_vars.items()
                        if var.get()),
            spotter_tokens=self._int(v["spotter_tokens"], 0, 12, 0),
            ap_spotter_tokens=self._int(v["ap_spotter_tokens"], 0, 12, 0),
            versatile=versatile,
            strike_back=bool(v["strike_back"].get()),
            tie=_key(TIE_LABELS, v["tie"].get()),
            spell=self.spell_keys.get(v["spell"].get()),
            friendly_tokens=self._int(v["friendly_tokens"], 0, 12, 0),
            enemy_tokens=self._int(v["enemy_tokens"], 0, 12, 0),
            buffs=tuple(k for k, var in self.buff_vars.items() if var.get()),
            charge_distance=self._int(v["charge_distance"], 0, 24, 6),
            ambushed=bool(v["ambushed"].get()),
            conduit=bool(v["conduit"].get()))

    def set_setup(self, s: S.Setup) -> None:
        v = self.v
        v["attack"].set(s.attack)
        v["distance"].set(str(s.distance))
        v["action"].set(s.action if s.action in S.SHOOT_ACTIONS else "hold")
        v["cover"].set(COVER_LABELS[s.cover])
        v["line_of_sight"].set(s.line_of_sight)
        v["crossing"].set(s.crossing)
        v["strike_back"].set(s.strike_back)
        v["tie"].set(TIE_LABELS[s.tie])
        v["spotter_tokens"].set(str(s.spotter_tokens))
        v["ap_spotter_tokens"].set(str(s.ap_spotter_tokens))
        v["charge_distance"].set(str(s.charge_distance))
        v["ambushed"].set(s.ambushed)
        v["conduit"].set(s.conduit)
        for rid, var in self.mark_vars.items():
            var.set(rid in s.marks)
        v["friendly_tokens"].set(str(s.friendly_tokens))
        v["enemy_tokens"].set(str(s.enemy_tokens))
        v["spell"].set(next((lb for lb, k in self.spell_keys.items()
                             if k == s.spell), ""))
        for k, var in self.buff_vars.items():
            var.set(k in s.buffs)
        chosen = dict(s.versatile)
        for rid, (var, labels) in self.versatile_vars.items():
            i = chosen.get(rid)
            first = self.versatile_first.get(rid, "none")
            var.set(labels[i] if i is not None and i < len(labels) else first)
        self._sync()

    def _sync(self) -> None:
        s = self.get_setup()
        for name, w in self.w.items():
            ok = s.relevant(name)
            if isinstance(w, ttk.Combobox):
                w.configure(state="readonly" if ok else tk.DISABLED)
            else:
                w.configure(state=tk.NORMAL if ok else tk.DISABLED)

    def _edited(self) -> None:
        self._sync()
        if self.on_change:
            self.on_change(self.get_setup())


class SidePanel(ttk.LabelFrame):
    """State of one unit at the start of the analysis."""

    def __init__(self, parent, title="Unit state", on_change=None):
        super().__init__(parent, text=title)
        self.on_change = on_change
        self.wounds = tk.StringVar(value="0")
        self.flags = {"moved": tk.BooleanVar(value=False),
                      "fatigued": tk.BooleanVar(value=False),
                      "shaken": tk.BooleanVar(value=False),
                      "terrain": tk.BooleanVar(value=False),
                      "feat": tk.BooleanVar(value=False)}
        self.hero_q = tk.StringVar(value=NO_HERO)
        self.weapon_vars: dict = {}         # Weapon -> BooleanVar (on)
        self._max = 0
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=4, pady=1)
        ttk.Label(row, text="Wounds taken").pack(side=tk.LEFT)
        self.wounds_box = ui.tip(ttk.Spinbox(
            row, from_=0, to=0, width=4, textvariable=self.wounds,
            command=self._edited),
            "Wounds already taken, placed as the defender would (models "
            "without Tough first, Heroes last)")
        self.wounds_box.pack(side=tk.LEFT, padx=4)
        self.wounds_box.bind("<Return>", lambda _e: self._edited())
        self.wounds_box.bind("<FocusOut>", lambda _e: self._edited())
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=4, pady=1)
        for key, text in (("moved", "Moved"), ("fatigued", "Fatigued"),
                          ("shaken", "Shaken")):
            ttk.Checkbutton(row, text=text, variable=self.flags[key],
                            command=self._edited).pack(side=tk.LEFT)
        row = ttk.Frame(self)                   # table inputs
        row.pack(fill=tk.X, padx=4, pady=1)
        for key, text, tip in (
                ("terrain", 'Near terrain',
                 'Most models within 1" of terrain (Demolish, Grounded '
                 'rules)'),
                ("feat", "Feat used",
                 "Uses its once-per-game ward Feat in this activation "
                 "(Protection Feat: every wound of the activation)")):
            ui.tip(ttk.Checkbutton(row, text=text, variable=self.flags[key],
                                   command=self._edited), tip
                   ).pack(side=tk.LEFT)
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=4, pady=1)
        ttk.Label(row, text="Tough(9)+ Hero within 6\"").pack(side=tk.LEFT)
        cb = ui.tip(ttk.Combobox(row, values=HERO_QUALITIES, width=4,
                                 textvariable=self.hero_q, state="readonly"),
                    "Quality of a friendly Hero the unit may use for Morale "
                    "Tests (distances are not modelled)")
        cb.pack(side=tk.LEFT, padx=4)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._edited())
        self.weapons_box = ttk.LabelFrame(self, text="Weapons")
        self.weapons_box.pack(fill=tk.X, padx=4, pady=2)

    def set_unit(self, unit, hero=None) -> None:
        """New unit: weapons all on, wounds capped (kept if still valid)."""
        self._max = S.max_wounds(unit, hero) if unit is not None else 0
        self.wounds_box.configure(to=self._max)
        self.wounds.set(str(min(self._wounds(), self._max)))
        for w in self.weapons_box.winfo_children():
            w.destroy()
        old = {w: v.get() for w, v in self.weapon_vars.items()}
        self.weapon_vars = {}
        units = [u for u in (unit, hero) if u is not None]
        for u in units:
            for weapon, n in u.weapons():
                if weapon in self.weapon_vars:
                    continue
                var = tk.BooleanVar(value=old.get(weapon, True))
                ttk.Checkbutton(self.weapons_box,
                                text=f"{n}x {weapon_text(weapon)}",
                                variable=var, command=self._edited
                                ).pack(anchor=tk.W, padx=4)
                self.weapon_vars[weapon] = var

    def set_side(self, ss: S.SideSetup) -> None:
        """Show a SideSetup (after set_unit for the same unit)."""
        self.wounds.set(str(min(ss.wounds_taken, self._max)))
        self.flags["moved"].set(not ss.not_moved)
        self.flags["fatigued"].set(ss.fatigued)
        self.flags["shaken"].set(ss.shaken)
        self.flags["terrain"].set(ss.near_terrain)
        self.flags["feat"].set(ss.feat_used)
        self.hero_q.set(NO_HERO if ss.hero_quality is None
                        else f"{ss.hero_quality}+")
        for w, var in self.weapon_vars.items():
            var.set(w not in ss.off)

    def _wounds(self) -> int:
        try:
            return max(0, int(self.wounds.get()))
        except (TypeError, ValueError):
            return 0

    def get_side(self) -> S.SideSetup:
        q = self.hero_q.get()
        return S.SideSetup(
            wounds_taken=min(self._wounds(), self._max),
            not_moved=not self.flags["moved"].get(),
            fatigued=bool(self.flags["fatigued"].get()),
            shaken=bool(self.flags["shaken"].get()),
            near_terrain=bool(self.flags["terrain"].get()),
            feat_used=bool(self.flags["feat"].get()),
            hero_quality=None if q == NO_HERO else int(q.rstrip("+")),
            off=frozenset(w for w, v in self.weapon_vars.items()
                          if not v.get()))

    def _edited(self) -> None:
        if self.on_change:
            self.on_change(self.get_side())
