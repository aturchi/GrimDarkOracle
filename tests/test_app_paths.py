"""app_paths: source layout and both PyInstaller layouts.

A frozen build points __file__ inside a temporary folder, so user files
must be found relative to the EXECUTABLE. sys.frozen / sys._MEIPASS are
set here the way PyInstaller sets them, and every layout is asserted.
"""
import os
import sys

import testpaths
from grimdarkoracle import app_paths
from grimdarkoracle.ui import roster_picker_core as rp

REPO = testpaths.REPO_ROOT
PKG = os.path.join(REPO, "grimdarkoracle")


class Frozen:
    """Install PyInstaller's markers for the duration of a block."""

    def __init__(self, exe_dir, meipass=None):
        self.exe = os.path.join(exe_dir, "GrimDarkOracle.exe")
        self.meipass = meipass

    def __enter__(self):
        self._saved = (getattr(sys, "frozen", None), sys.executable,
                       getattr(sys, "_MEIPASS", None))
        sys.frozen = True
        sys.executable = self.exe
        if self.meipass is None:
            if hasattr(sys, "_MEIPASS"):
                del sys._MEIPASS
        else:
            sys._MEIPASS = self.meipass
        return self

    def __exit__(self, *exc):
        was_frozen, sys.executable, meipass = self._saved
        if was_frozen is None:
            del sys.frozen
        else:
            sys.frozen = was_frozen
        if meipass is None:
            if hasattr(sys, "_MEIPASS"):
                del sys._MEIPASS
        else:
            sys._MEIPASS = meipass
        return False


# From source: app dir = repo root, bundle dir = package folder.
assert app_paths.frozen() is False
assert app_paths.app_dir() == REPO, app_paths.app_dir()
assert app_paths.bundle_dir() == PKG, app_paths.bundle_dir()
assert app_paths.fetch_command() == "tools/af_fetch.py"
assert app_paths.resource("rules/x.json") == [
    os.path.join(REPO, "rules/x.json"), os.path.join(PKG, "rules/x.json")]

# One-file build: shipped files under <_MEIPASS>/grimdarkoracle.
EXE_DIR = os.path.join(os.sep, "opt", "dist")
MEI = os.path.join(os.sep, "tmp", "_MEI123")
with Frozen(EXE_DIR, MEI):
    assert app_paths.frozen() is True
    assert app_paths.app_dir() == EXE_DIR
    assert app_paths.bundle_dir() == os.path.join(MEI, "grimdarkoracle")
    # The default list folder follows the executable, not __file__.
    assert rp.ROSTERS_DIR == "lists"
    assert app_paths.fetch_command() == "af_fetch"      # the executable

# Build without _MEIPASS: fall back beside the executable.
with Frozen(EXE_DIR):
    assert app_paths.bundle_dir() == os.path.join(EXE_DIR, "grimdarkoracle")

assert app_paths.frozen() is False
print("app_paths: OK")
