"""tools/rules_report.py and tools/af_survey.py: without --data
they read library.default_root() (the program folder, as af_fetch and
update_report do), not a path of their own. The default is patched to
the synthetic download, so the tools must find its one book."""
import contextlib
import importlib.util
import io
import os

import testpaths

TOOLS = os.path.join(testpaths.REPO_ROOT, "tools")


def tool(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(TOOLS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


for name, needle in (("rules_report", "1 books"), ("af_survey", "1 books,")):
    mod = tool(name)
    assert not hasattr(mod, "DEFAULT_DATA")
    mod.default_root = lambda: testpaths.SYNTHETIC_DIR
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        mod.main([])
    assert needle in out.getvalue(), (name, out.getvalue()[:200])
print("tools_defaults: OK")
