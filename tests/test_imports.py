"""Every module of the grimdarkoracle package imports cleanly.

Catches broken package imports left over from the flat W40kDiviner
layout, and any module that pulls in tkinter at import time on a
machine without it (tkstub stands in only when tkinter is missing).
"""
import importlib
import pkgutil
import warnings

import testpaths                                          # noqa: F401
import tkstub

tkstub.install_if_missing(quiet=True)
import grimdarkoracle                                         # noqa: E402

warnings.simplefilter("error", DeprecationWarning)
names = [m.name for m in pkgutil.walk_packages(grimdarkoracle.__path__,
                                               prefix="grimdarkoracle.")]
for name in names:
    importlib.import_module(name)
assert len(names) >= 20, names
print(f"imports: {len(names)} modules OK")
