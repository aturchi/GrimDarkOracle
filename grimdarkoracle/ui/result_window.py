"""Analyzer result window and comparison window: thin Tk views over
app.result_rows and app.comparison (all numbers come from there).

ResultWindow: the table (click a statistic heading to read it as mean,
median, p25 or p75; double-click a row for its distribution), the
outcome lines (Morale, melee result, points), warnings, and the buttons
Distribution / Pin / Export CSV. Several stay open at once.

CompareWindow: pinned analyses side by side, differences against the
first pin, the context of each, survival curves of wounds or models
killed, CSV export.
"""
import tkinter as tk
from tkinter import ttk

from grimdarkoracle.app import audit as AU
from grimdarkoracle.app import comparison as C
from grimdarkoracle.app import result_rows as RR
from grimdarkoracle.ui import dist_view as dv
from grimdarkoracle.ui import ui_utils as ui
from grimdarkoracle.ui.inspect_dialog import TextWindow

SKIPPED_FG = "#888888"
TOTAL_BG = "#eef2f7"


class ResultWindow(tk.Toplevel):
    def __init__(self, parent, analysis, title: str, on_pin=None,
                 advice: str = ""):
        """advice: a line about the weapon order (app.order_advice)."""
        super().__init__(parent)
        self.a, self.on_pin, self.name = analysis, on_pin, title
        self.advice = advice
        self.stats: dict = {}
        self.sources: dict = {}         # tree item -> entries() source
        self.title(title)
        self.geometry("900x620")
        self._build()
        self.fill()

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=4)
        ttk.Button(bar, text="Close", command=self.destroy).pack(
            side=tk.RIGHT, padx=3)
        ui.tip(ttk.Button(bar, text="Export CSV...", command=self.cmd_export),
               "Write the table and the outcome lines to a CSV file, with "
               "the statistic each column shows").pack(side=tk.RIGHT, padx=3)
        self.pin_btn = ui.tip(
            ttk.Button(bar, text="Pin", command=self.cmd_pin),
            "Keep this analysis for the comparison window")
        self.pin_btn.pack(side=tk.RIGHT, padx=3)
        ui.tip(ttk.Button(bar, text="Audit", command=self.cmd_audit),
               "What the engine used for the selected weapon (all weapons "
               "if none is selected): final numbers and modifier sources"
               ).pack(side=tk.RIGHT, padx=3)
        ui.tip(ttk.Button(bar, text="Distribution", command=self.cmd_dist),
               "Distribution of the selected row (the first TOTAL if none)"
               ).pack(side=tk.RIGHT, padx=3)
        ttk.Label(self, text=self.name, font=ui.bold_font()).pack(
            anchor=tk.W, padx=6, pady=(6, 0))
        ttk.Label(self, text=C.context_signature(self.a),
                  foreground=ui.HINT_COLOR).pack(anchor=tk.W, padx=6)
        if self.advice:
            ttk.Label(self, text=self.advice, foreground=ui.HINT_COLOR,
                      wraplength=860, justify=tk.LEFT).pack(anchor=tk.W,
                                                            padx=6)
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self.tree = ttk.Treeview(frame, columns=RR.KEYS,
                                 show="tree headings", height=12)
        self.tree.heading("#0", text="Weapon")
        self.tree.column("#0", width=280)
        for key, _title, width in RR.COLUMNS:
            self.tree.heading(key, command=lambda k=key: self.cycle(k))
            self.tree.column(key, width=width, anchor=tk.E)
        self.tree.tag_configure("skipped", foreground=SKIPPED_FG)
        self.tree.tag_configure("total", background=TOTAL_BG,
                                font=ui.bold_font())
        ui.attach_yscroll(self.tree, frame)
        self.tree.bind("<Double-1>", lambda _e: self.cmd_dist())
        lines = RR.outcome_lines(self.a)
        box = ttk.Frame(self)
        box.pack(fill=tk.X, padx=6)
        self.outcome = ttk.Treeview(box, columns=("value",), show="tree",
                                    height=min(10, len(lines)))
        self.outcome.column("#0", width=320)
        self.outcome.column("value", width=120, anchor=tk.E)
        ui.attach_yscroll(self.outcome, box)
        for k, v in lines:
            self.outcome.insert("", tk.END, text=k, values=(v,))
        if self.a.warnings:
            ttk.Label(self, text="\n".join(self.a.warnings),
                      foreground=ui.WARN_COLOR, wraplength=860,
                      justify=tk.LEFT).pack(anchor=tk.W, padx=6, pady=2)

    # --- table --------------------------------------------------------------------

    def fill(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.sources.clear()
        for key in RR.KEYS:
            self.tree.heading(key, text=RR.heading(
                key, self.stats.get(key, "mean")))
        for row, src in RR.entries(self.a, self.stats):
            tags = (row.kind,) if row.kind in ("skipped", "total") else ()
            item = self.tree.insert("", tk.END, text=row.name,
                                    values=row.cells, tags=tags)
            self.sources[item] = src

    def cycle(self, key: str) -> None:
        """Click on a statistic heading: next statistic for that column."""
        if key in RR.STAT_KEYS:
            self.stats[key] = RR.next_stat(self.stats.get(key, "mean"))
            self.fill()

    def rows(self) -> list[tuple[str, tuple]]:
        """(name, cells) as shown (tests)."""
        return [(self.tree.item(i, "text"),
                 tuple(str(v) for v in self.tree.item(i, "values")))
                for i in self.tree.get_children()]

    # --- buttons ------------------------------------------------------------------

    def _selected_source(self):
        sel = self.tree.selection()
        if sel and sel[0] in self.sources:
            return self.sources[sel[0]]
        return ("total", "att")

    def cmd_dist(self):
        src = self._selected_source()
        series = RR.series(self.a, src)
        if not series:
            return None
        what = "TOTAL" if isinstance(src, tuple) else src.name
        return dv.open_distribution(self, f"{self.name} - {what}", series)

    def cmd_audit(self):
        sel = self.tree.selection()
        src = self.sources.get(sel[0]) if sel else None
        body = AU.row_text(src) if hasattr(src, "audit") else \
            AU.analysis_text(self.a)
        return TextWindow(self, f"Audit - {self.name}", body)

    def cmd_pin(self):
        if self.on_pin:
            self.on_pin(self.name, self.a)
            self.pin_btn.configure(state=tk.DISABLED, text="Pinned")

    def cmd_export(self):
        ui.save_text(self, RR.to_csv(self.a, self.stats),
                     title="Export analysis",
                     filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
                     initialfile="analysis.csv")


class CompareWindow(tk.Toplevel):
    CURVES = (("wounds", "wounds inflicted"), ("killed", "models killed"))

    def __init__(self, parent, pins, title="Comparison", on_clear=None):
        super().__init__(parent)
        self.pins, self.on_clear = list(pins), on_clear
        self.title(f"{title} - {len(self.pins)} analyses")
        self.geometry("1000x640")
        self.which = tk.StringVar(value="wounds")
        self._build()

    def _build(self):
        row = ttk.Frame(self)
        row.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=4)
        ttk.Label(row, text="Curves:").pack(side=tk.LEFT)
        for key, text in self.CURVES:
            ttk.Radiobutton(row, text=text, value=key, variable=self.which,
                            command=self.refresh).pack(side=tk.LEFT,
                                                       padx=(2, 8))
        ttk.Button(row, text="Close", command=self.destroy).pack(
            side=tk.RIGHT, padx=3)
        if self.on_clear:
            ui.tip(ttk.Button(row, text="Clear pins", command=self._clear),
                   "Drop every pinned analysis and close this window"
                   ).pack(side=tk.RIGHT, padx=3)
        ui.tip(ttk.Button(row, text="Export CSV...", command=self._export),
               "Write the comparison table to a CSV file"
               ).pack(side=tk.RIGHT, padx=3)
        self.canvas = dv.OverlayCanvas(self, height=200)
        self.canvas.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True,
                         padx=6, pady=(0, 6))
        ttk.Label(self, text="Every column past the first shows its "
                  "difference against the first one.",
                  foreground=ui.HINT_COLOR).pack(anchor=tk.W, padx=6,
                                                 pady=(6, 2))
        cols = tuple(f"c{i}" for i in range(len(self.pins)))
        self.tree = ttk.Treeview(self, columns=cols, show="tree headings",
                                 height=16)
        self.tree.heading("#0", text="Metric")
        self.tree.column("#0", width=230)
        for i, c in enumerate(cols):
            self.tree.heading(c, text=f"#{i + 1}")
            self.tree.column(c, width=170, anchor=tk.W)
        self.tree.tag_configure("head", background=TOTAL_BG,
                                font=ui.bold_font())
        self.tree.tag_configure("warn", foreground=ui.WARN_COLOR)
        for label, cells in C.context_rows(self.pins):
            tag = "warn" if label == "vs first" and "DIFFERENT" in cells \
                else "head"
            self.tree.insert("", tk.END, text=label, values=cells,
                             tags=(tag,))
        for label, cells in C.matrix(self.pins):
            self.tree.insert("", tk.END, text=label, values=cells)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=6)
        self.refresh()

    def refresh(self):
        self.canvas.set_data(C.overlay_series(self.pins, self.which.get()),
                             None)

    def _clear(self):
        if self.on_clear:
            self.on_clear()
        self.destroy()

    def _export(self):
        ui.save_text(self, C.to_csv(self.pins), title="Export comparison",
                     filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
                     initialfile="comparison.csv")
