# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for GrimDarkOracle (pattern: W40kDiviner.spec).

Builds self-contained one-file executables (Python, Tkinter and the
shipped data embedded; nothing to install on the target machine):

    AttackAnalyzer     exact attack / melee / morale laws      (window)
    ListEditor         army lists and home-made units          (window)
    af_fetch           download / update the Army Forge data   (console)
    update_report      what an update changed, what to review  (console)

Build from the repository root, with the Python the programs run on
(>= 3.14), on the operating system the executables are for:

    pip install pyinstaller
    pyinstaller GrimDarkOracle.spec          # -> dist/

WHAT LIVES NEXT TO THE EXECUTABLES (grimdarkoracle/app_paths.app_dir): a
one-file build unpacks into a temporary folder deleted on exit, so
everything the user creates or downloads is looked up beside the
executable, never inside the bundle:

    data/army_forge/   Army Forge download (run af_fetch first; personal
                       use only, never redistribute it)
    lists/             army lists (List Editor; checked by update_report)
    books_local/       home-made units (local books)
    sessions/          Analyzer sessions
    rules/semantics.json  optional user copies of the shipped rule / spell
    rules/spells.json     semantics: when present they win (app_paths.resource)

The shipped semantics.json and spells.json are embedded under
grimdarkoracle/rules/, where app_paths.bundle_dir() looks for them.

UPX is off: compressed one-file bootloaders trip some antivirus
heuristics. The tests are excluded (no stub toolkit in a build).
"""

DATAS = [("grimdarkoracle/rules/semantics.json", "grimdarkoracle/rules"),
         ("grimdarkoracle/rules/spells.json", "grimdarkoracle/rules")]

# (entry script, executable name, console)
PROGRAMS = [("attack_analyzer.py", "AttackAnalyzer", False),
            ("list_editor.py", "ListEditor", False),
            ("tools/af_fetch.py", "af_fetch", True),
            ("tools/update_report.py", "update_report", True)]


def build_exe(script, name, console):
    a = Analysis(
        [script],
        pathex=["."],                   # the grimdarkoracle package
        binaries=[],
        datas=DATAS,
        hiddenimports=[],
        hookspath=[],
        runtime_hooks=[],
        excludes=["tests", "tkstub", "tkhost", "testpaths", "unitkit",
                  "gamekit", "mc_support"],
        noarchive=False,
    )
    pyz = PYZ(a.pure)
    return EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=console,
        disable_windowed_traceback=False,
    )


for _script, _name, _console in PROGRAMS:
    build_exe(_script, _name, _console)
