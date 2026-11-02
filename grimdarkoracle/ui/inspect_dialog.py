"""Read-only windows of the Analyzer: the profile of a unit as the
program will play it (app.unit_sheet), with "Save cheat sheet..." (HTML
or text, by the extension chosen), and the audit of a result row
(app.audit). Several may stay open."""
import tkinter as tk
from tkinter import ttk

from grimdarkoracle.app import unit_sheet as US
from grimdarkoracle.ui import ui_utils as ui


class TextWindow(tk.Toplevel):
    """A read-only text with Close (and optional extra buttons)."""

    def __init__(self, parent, title: str, body: str, size="820x620"):
        super().__init__(parent)
        self.title(title)
        self.geometry(size)
        self.bar = ttk.Frame(self)
        self.bar.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=4)
        ttk.Button(self.bar, text="Close", command=self.destroy).pack(
            side=tk.RIGHT, padx=3)
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 0))
        self.text = tk.Text(frame, wrap=tk.WORD, height=30, width=100)
        ui.attach_yscroll(self.text, frame)
        self.text.insert("1.0", body)
        self.text.configure(state=tk.DISABLED)

    def body(self) -> str:
        return self.text.get("1.0", tk.END)


class InspectDialog(TextWindow):
    def __init__(self, parent, sheet: US.Sheet):
        super().__init__(parent, f"Inspect - {sheet.title}",
                         US.to_text(sheet))
        self.sheet = sheet
        ui.tip(ttk.Button(self.bar, text="Save cheat sheet...",
                          command=self.cmd_save),
               "One printable page: .html opens in a browser (Ctrl-P), "
               ".txt is plain text").pack(side=tk.RIGHT, padx=3)

    def cmd_save(self):
        return ui.save_text(self, lambda path: US.render(self.sheet, path),
                            title="Save cheat sheet", defaultextension=".html",
                            filetypes=[("HTML", "*.html"), ("Text", "*.txt"),
                                       ("All files", "*.*")],
                            initialfile="cheat_sheet.html")
