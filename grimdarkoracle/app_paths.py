"""Where the program's files are, running from source or from a build.

Two folders that are the same thing while running from source and two
DIFFERENT things inside a PyInstaller build:

- :func:`app_dir` - the folder the user sees: the one holding the
  executable, or the repository root when running from source. Army
  lists (``lists/``), downloaded Army Forge data (``data/``) and user
  overrides of shipped files live here.
- :func:`bundle_dir` - where the files SHIPPED with the program are: the
  ``grimdarkoracle`` package folder, i.e. ``<repo>/grimdarkoracle`` from source
  and ``<sys._MEIPASS>/grimdarkoracle`` in a build. The PyInstaller spec must
  therefore add shipped data under ``grimdarkoracle/...`` (e.g.
  ``grimdarkoracle/rules/semantics.json``), mirroring the source tree.

Why this module exists at all: a one-file build unpacks into a
temporary folder with a different name on every run, and the frozen
modules' ``__file__`` points INSIDE it. Anything found relative to
``__file__`` therefore lands in a directory the user has never seen and
that is deleted on exit - so "keep your lists next to the executable"
and "a user copy of a shipped file wins" quietly stop being true the
moment the program is built, while continuing to work perfectly in every
test run from source. That is the kind of difference no test catches by
accident, which is why the two folders are named apart here instead of
being derived at each call site.
"""

import os
import sys

# This module sits at the top of the package: its folder IS the package.
_PKG = os.path.dirname(os.path.abspath(__file__))
_PKG_NAME = os.path.basename(_PKG)


def frozen() -> bool:
    """Whether this is running inside a PyInstaller build. PyInstaller
    sets sys.frozen itself; nothing else in the suite writes it."""
    return bool(getattr(sys, "frozen", False))


def fetch_command() -> str:
    """How the user runs the Army Forge download: the af_fetch executable
    next to the programs when frozen, the script otherwise."""
    return "af_fetch" if frozen() else "tools/af_fetch.py"


def app_dir() -> str:
    """The folder the user launches the program from: the one holding
    the executable when frozen, the repository root otherwise (the
    package folder is one level below it)."""
    if frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(_PKG)


def bundle_dir() -> str:
    """The folder holding the files shipped with the program.

    ``<sys._MEIPASS>/grimdarkoracle`` in a build (PyInstaller >= 6 sets
    _MEIPASS in one-dir builds too); if _MEIPASS is missing, the folder
    beside the executable is the fallback rather than an error.
    """
    if frozen():
        root = getattr(sys, "_MEIPASS", None) or app_dir()
        return os.path.join(root, _PKG_NAME)
    return _PKG


def resource(name) -> list:
    """The places a shipped but user-overridable file may be, in the
    order they must be tried: the user's own copy next to the program
    first, the bundled one second. Getting that order backwards would
    make the shipped file impossible to override."""
    return [os.path.join(app_dir(), name), os.path.join(bundle_dir(), name)]
