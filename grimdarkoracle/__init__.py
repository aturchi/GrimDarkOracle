"""GrimDarkOracle: exact attack and melee mathematics for Grimdark Future 3.6.

Sub-packages:
    data    Army Forge adapter, configurations, army lists, overrides
    rules   rule semantics registry and coverage report
    engine  probability mass functions and combat resolution
    app     Tk-free application logic shared by the two programs
    ui      Tkinter widgets and views
"""

#: Rules edition the semantics are written against.
GAME_VERSION = "3.6.0"
