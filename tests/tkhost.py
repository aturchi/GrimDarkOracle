"""A Tk root for view tests: the real toolkit when a display answers,
otherwise the stub (tkstub), saying which on stdout. Import BEFORE any
grimdarkoracle.ui module."""
import testpaths                                    # noqa: F401 (sys.path)
import tkstub

REAL = not tkstub.install_if_missing()
ROOT = None
if REAL:
    import tkinter as _tk
    try:
        ROOT = _tk.Tk()
        ROOT.withdraw()
    except Exception as exc:                        # no display
        print(f"[tkhost] tkinter imports but no display answers ({exc}): "
              "falling back to the stub")
        tkstub.install()
        REAL = False
if ROOT is None:
    import tkinter as _tk
    ROOT = _tk.Tk()
print(f"[tkhost] {'real Tk' if REAL else 'tkstub'}")


def packed(widget) -> bool:
    """Whether a geometry manager holds 'widget' (real Tk: even while the
    test root is withdrawn and nothing is mapped)."""
    return bool(widget.winfo_manager()) if REAL else widget.winfo_ismapped()
