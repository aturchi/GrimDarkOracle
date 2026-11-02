"""Shared spell fixture (was gamekit.py until the Game Assistant was
removed): the synthetic book with four mapped spells (Bolt
damage, Ward / Ammo grants, Hex mark) and a library holding it."""
from dataclasses import replace

import testpaths
from unitkit import SEM, CORE, resolved
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.rules import registry, spells as S

book = ab.load_book(testpaths.book_path("synthetic00book01",
                                        testpaths.SYNTHETIC_DIR))
hex_ = ab.Spell("sp3", "Hex", 1, "Synthetic: enemy marked, AP(1).")
ammo = ab.Spell("sp4", "Ammo", 1, "Synthetic: Shred when shooting, once.")
book = replace(book, spells=book.spells + (hex_, ammo))
K = {s.name: S.spell_key(s) for s in book.spells}
DOC = {"format": S.FORMAT, "spells": {
    K["Bolt"]: {"name": "Bolt", "kind": "damage", "hits": 2, "range": 12,
                "rules": [["AP", 1]]},
    K["Ward"]: {"name": "Ward", "kind": "grant",
                "grants": [{"rule": "Fearless"},
                           {"rule": "Shred", "to": "weapons",
                            "attack": "shooting"}]},
    K["Hex"]: {"name": "Hex", "kind": "mark",
               "conditions": {"attack": "shooting"},
               "effects": [{"primitive": "ap_mod", "value": 1}]},
    K["Ammo"]: {"name": "Ammo", "kind": "grant",
                "grants": [{"rule": "Shred", "to": "weapons",
                            "attack": "shooting"}]}}}


class Lib:
    def __init__(self):
        self.reg = registry.RuleRegistry(SEM, CORE, [book])
        self.books = {book.uid: book}
        self.sreg = S.SpellRegistry(DOC, self.reg, [book])


lib = Lib()
B = book.uid
REF = {n: f"{k}@{B}" for n, k in K.items()}


def ru(cb, name):
    """A ResolvedUnit of the Combatant 'cb' from the synthetic book."""
    return replace(resolved(cb, 100, name), book_uid=B)
