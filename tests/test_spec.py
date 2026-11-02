"""GrimDarkOracle.spec: run with stand-ins for PyInstaller's Analysis /
PYZ / EXE, so a renamed entry script or data file breaks a test instead
of a build: every entry script and every bundled data file exists, data
lands under grimdarkoracle/ (app_paths.bundle_dir), the GUI programs are
windowed and the tools are console programs, tests are excluded."""
import os

import testpaths

ROOT = testpaths.REPO_ROOT
calls = []


class Analysis:
    def __init__(self, scripts, **kw):
        self.scripts, self.kw = scripts, kw
        self.pure = self.binaries = self.datas = ()
        calls.append(self)


def PYZ(pure):
    return pure


def EXE(pyz, scripts, binaries, datas, extra, **kw):
    calls[-1].exe = kw


with open(os.path.join(ROOT, "GrimDarkOracle.spec"), encoding="utf-8") as fh:
    code = fh.read()
exec(compile(code, "GrimDarkOracle.spec", "exec"),
     {"Analysis": Analysis, "PYZ": PYZ, "EXE": EXE})

names = {c.exe["name"]: c for c in calls}
assert sorted(names) == ["AttackAnalyzer", "ListEditor", "af_fetch",
                         "update_report"]
for c in calls:
    (script,) = c.scripts
    assert os.path.isfile(os.path.join(ROOT, script)), script
    for src, dest in c.kw["datas"]:
        assert os.path.isfile(os.path.join(ROOT, src)), src
        assert os.path.normpath(dest) == os.path.dirname(
            os.path.normpath(src)) and dest.startswith("grimdarkoracle")
    assert "tests" in c.kw["excludes"] and not c.exe["upx"]
    assert c.exe["console"] == (c.exe["name"] in ("af_fetch",
                                                  "update_report"))
shipped = {os.path.join("grimdarkoracle", "rules", f) for f in
           os.listdir(os.path.join(ROOT, "grimdarkoracle", "rules"))
           if f.endswith(".json")}
assert {os.path.normpath(s) for s, _d in calls[0].kw["datas"]} == shipped
print("spec: OK")
