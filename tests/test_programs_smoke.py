"""The two programs start and close as a user starts them.
The window tests drive the views; this one runs the SCRIPTS
(attack_analyzer.py, list_editor.py) in a subprocess, each closed by
itself after a moment, in:

* the repository (the Army Forge download, when present);
* a fresh folder with only the program and no data at all, as on a first
  start; there the List Editor opens a saved list (its books missing).

A run passes when it exits 0 with no traceback. Needs a display: with the
stub toolkit (no display) the test says so and passes.
"""
import os
import shutil
import subprocess
import sys
import tempfile

import testpaths
import realkit
from grimdarkoracle.data import army_list as AL

SCRIPTS = ("attack_analyzer.py", "list_editor.py")
# Message boxes are modal: they would wait for a click. The driver prints
# them instead ("[box] title: text") and answers "no" / "cancel".
DRIVER = """
import runpy, sys, tkinter as tk
from tkinter import messagebox as mb
def box(kind, answer):
    def show(title=None, message=None, **_kw):
        print("[box]", kind, title, ":", message)
        return answer
    return show
for k in ("showinfo", "showwarning", "showerror"):
    setattr(mb, k, box(k, "ok"))
for k, ans in (("askyesno", False), ("askyesnocancel", None),
               ("askokcancel", False), ("askquestion", "no")):
    setattr(mb, k, box(k, ans))
sys.path.insert(0, ".")
script = sys.argv[1]
sys.argv = sys.argv[1:]
real = tk.Misc.mainloop
def find(self):                             # Ctrl+F opens the search
    self.focus_force()
    self.update()
    self.event_generate("<Control-f>")
    holder = getattr(self, "search_holder", {})
    if holder.get("dlg") is not None:
        print("[find] ok")
def mainloop(self, *a):
    self.after(500, lambda: find(self))
    self.after(1200, self.destroy)
    real(self, *a)
tk.Misc.mainloop = mainloop
runpy.run_path(script, run_name="__main__")
"""


def display() -> bool:
    try:
        import tkinter
        tkinter.Tk().destroy()
        return True
    except Exception:                               # no display, or stub
        return False


def run(folder, script, *args) -> str:
    r = subprocess.run([sys.executable, "-c", DRIVER, script, *args],
                       cwd=folder, capture_output=True, text=True,
                       timeout=60)
    out = r.stdout + r.stderr
    assert r.returncode == 0 and "Traceback" not in out, \
        f"{script} {args} in {folder}:\n{out[-2000:]}"
    return out


def main():
    if not display():
        print("programs smoke: no display (stub toolkit), not run")
        return
    root = testpaths.REPO_ROOT
    for s in SCRIPTS:
        assert "[find] ok" in run(root, s), s       # Ctrl+F wired
    lib, (a, _b) = realkit.library()
    tmp = tempfile.mkdtemp()
    try:
        bare = os.path.join(tmp, "GrimDarkOracle")
        os.makedirs(bare)
        for name in SCRIPTS + ("grimdarkoracle",):
            src = os.path.join(root, name)
            (shutil.copytree if os.path.isdir(src) else shutil.copy)(
                src, os.path.join(bare, name))
        army = realkit.army(lib, a, 0)
        lpath = os.path.join(tmp, "list.json")
        AL.save(army, lpath)
        for s in SCRIPTS:
            run(bare, s)
        out = run(bare, "list_editor.py", lpath)
        assert "[box]" in out, out          # the missing books are told
        assert not os.path.isdir(os.path.join(bare, "data", "army_forge",
                                              "books")) or not os.listdir(
            os.path.join(bare, "data", "army_forge", "books"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"programs smoke: {len(SCRIPTS)} programs started and closed "
          "with the download and in an empty folder (a list opened "
          "there)")


if __name__ == "__main__":
    main()
