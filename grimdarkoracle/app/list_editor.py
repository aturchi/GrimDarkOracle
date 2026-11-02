"""List Editor core: edit an army list in memory. No tkinter.

    ed = ListEditor(lib)                      # new list, or ListEditor.open
    key = ed.add_unit(book_uid, unit_id)
    cfg = ed.config(key)                      # app.unit_config.UnitConfig
    cfg.set_count(...); ed.commit(key, cfg)   # choices back into the list
    ed.join(hero_key, key); ed.set_combined(key, True)
    ed.rows(), ed.violations(), ed.points; ed.undo(); ed.save(path)

The list stores configurations only; everything shown is
recomputed with list_resolve from the books, so book updates propagate.
Rules of the editor:

- choices that no longer link are KEPT and flagged: commit()
  writes the panel's choices plus the lost refs untouched; drop_invalid()
  removes them on request;
- on open, re-linked uids are rewritten in memory and the list is
  marked modified, so the next save stores them;
- a join is refused when the core rules forbid it (join_issues);
  Combined only for multi-model units; removing a host frees its Hero;
- every edit is one undo step (a snapshot of the list).
"""
import copy
import os
from dataclasses import dataclass, field

from grimdarkoracle.app import undo_stack as U
from grimdarkoracle.app.unit_config import UnitConfig
from grimdarkoracle.data import army_list as AL
from grimdarkoracle.data import force_org, links, list_resolve, overrides
from grimdarkoracle.data.list_resolve import join_issues
from grimdarkoracle.data.resolve import placement_candidates

COPIES = ("a", "b")


@dataclass(frozen=True)
class Row:
    """One entry as the editor lists it."""
    key: str
    label: str                      # user's label, else the unit name
    unit_name: str
    book: str                       # book name
    points: int
    size: int
    combined: bool
    joined_to: str | None
    valid: bool                     # unit found and every choice linked
    issues: tuple[str, ...] = ()    # link, resolve, join, override notes


@dataclass
class OpenResult:
    editor: "ListEditor"
    notes: list = field(default_factory=list)   # re-links, invalid choices


class ListEditor:
    def __init__(self, lib, army: AL.ArmyList | None = None,
                 path: str | None = None):
        self.lib = lib
        self.army = army if army is not None else AL.ArmyList()
        self.path = path
        self.dirty = False
        self.history = U.UndoStack()
        self._result = None

    # --- files ------------------------------------------------------------------------

    @classmethod
    def open(cls, lib, path: str) -> OpenResult:
        """Load a list and re-link it to the current books."""
        ed = cls(lib, AL.load(path), path)
        notes = ed._relink()
        ed.history.clear()
        return OpenResult(ed, notes)

    def save(self, path: str | None = None) -> str:
        path = path or self.path
        if not path:
            raise ValueError("no file name")
        AL.save(self.army, path)
        self.path, self.dirty = path, False
        return path

    @property
    def title(self) -> str:
        name = os.path.basename(self.path) if self.path else "(not saved)"
        return f"{self.army.name} - {name}" + (" *" if self.dirty else "")

    def _relink(self) -> list[str]:
        notes = []
        for lu in self.army.units:
            book = self.lib.books.get(lu.book)
            link = links.link_unit(book, lu)
            tag = lu.label or lu.unit_name or lu.unit_id
            notes += [f"{tag}: {x}" for x in link.invalid]
            if not link.relinked:
                continue
            notes += [f"{tag}: re-linked {x}" for x in link.relinked]
            lu.unit_id = link.unit_id
            lu.unit_name = book.units[link.unit_id].name
            lu.choices = link.choices + link.lost
            if lu.choices_b is not None:
                lu.choices_b = link.choices_b + link.lost_b
            self.dirty = True
        return notes

    # --- reading ----------------------------------------------------------------------

    def result(self) -> list_resolve.ListResult:
        if self._result is None:
            self._result = list_resolve.resolve_list(self.army, self.lib.books)
        return self._result

    def books_changed(self) -> None:
        """A book was edited (local books): resolve the list again."""
        self._result = None

    @property
    def points(self) -> int:
        return self.result().points

    def violations(self) -> list:
        return force_org.check(self.army, self.result())

    def rows(self) -> list[Row]:
        """Entries in list order, each joined Hero right after its host."""
        res, out = self.result(), []
        guests = {u.joined_to: u for u in self.army.units if u.joined_to}
        order = []
        for u in self.army.units:
            if u.joined_to is None or self.army.unit(u.joined_to) is None:
                order.append(u)
                if u.key in guests:
                    order.append(guests[u.key])
        for u in order:
            e = res.entries[u.key]
            book = self.lib.books.get(u.book)
            ru = e.unit
            issues = tuple(e.issues) + (tuple(ru.issues) if ru else ())
            out.append(Row(u.key, u.label or u.unit_name, u.unit_name,
                           book.name if book else u.book, e.points,
                           ru.size if ru else 0, u.combined, u.joined_to,
                           e.valid, issues))
        return out

    def entry(self, key: str) -> AL.ListUnit:
        lu = self.army.unit(key)
        if lu is None:
            raise KeyError(f"no entry {key!r}")
        return lu

    # --- edits ------------------------------------------------------------------------

    def _edit(self, label: str, fn):
        """Run fn() as one undo step; returns what fn returns."""
        before = AL.to_dict(self.army)
        try:
            out = fn()
        except Exception:
            self.army = AL.from_dict(before)    # an edit is all or nothing
            self._result = None
            raise
        after = AL.to_dict(self.army)
        if self.history.push_changes(label, [U.change(None, None, "list",
                                                      before, after)]):
            self.dirty = True
        self._result = None
        return out

    def _set(self, _side, _iid, _field, value) -> None:
        self.army = AL.from_dict(copy.deepcopy(value))
        self._result = None
        self.dirty = True

    def undo(self) -> bool:
        act = self.history.undo()
        if act:
            U.apply_action(act, self._set, undo=True)
        return bool(act)

    def redo(self) -> bool:
        act = self.history.redo()
        if act:
            U.apply_action(act, self._set, undo=False)
        return bool(act)

    def set_meta(self, name=None, points_limit=None, force_org_on=None):
        if points_limit is not None and int(points_limit) <= 0:
            raise ValueError("points limit must be positive")

        def fn():
            if name is not None:
                self.army.name = name
            if points_limit is not None:
                self.army.points_limit = int(points_limit)
            if force_org_on is not None:
                self.army.force_org = bool(force_org_on)
        self._edit("list settings", fn)

    def add_unit(self, book_uid: str, unit_id: str, label: str = "") -> str:
        book = self.lib.books.get(book_uid)
        if book is None or unit_id not in book.units:
            raise KeyError(f"unit {unit_id!r} not in book {book_uid!r}")

        def fn():
            key = self.army.new_key()
            self.army.units.append(AL.ListUnit(
                key, book_uid, unit_id, book.units[unit_id].name, label))
            self.army.books[book_uid] = book.version
            return key
        return self._edit("add unit", fn)

    def remove(self, key: str) -> None:
        self.entry(key)

        def fn():
            self.army.units = [u for u in self.army.units if u.key != key]
            for u in self.army.units:
                if u.joined_to == key:
                    u.joined_to = None
            used = {u.book for u in self.army.units}
            self.army.books = {k: v for k, v in self.army.books.items()
                               if k in used}
        self._edit("remove unit", fn)

    def duplicate(self, key: str) -> str:
        src = self.entry(key)

        def fn():
            lu = copy.deepcopy(src)
            lu.key, lu.joined_to = self.army.new_key(), None
            if lu.label:
                lu.label += " (copy)"
            self.army.units.append(lu)
            return lu.key
        return self._edit("duplicate unit", fn)

    def move(self, key: str, delta: int) -> None:
        """Move an entry up (-1) or down (+1) in the list."""
        lu = self.entry(key)

        def fn():
            us = self.army.units
            i = us.index(lu)
            j = max(0, min(len(us) - 1, i + delta))
            us.insert(j, us.pop(i))
        self._edit("move unit", fn)

    def set_label(self, key: str, label: str) -> None:
        lu = self.entry(key)
        self._edit("rename", lambda: setattr(lu, "label", label.strip()))

    def set_notes(self, key: str, notes: str) -> None:
        lu = self.entry(key)
        self._edit("notes", lambda: setattr(lu, "notes", notes))

    # --- Combined Units and Hero joins ---------------------------------------

    def set_combined(self, key: str, on: bool) -> None:
        lu = self.entry(key)
        ru = self.result().entries[key].unit
        if on and (ru is None or self._single(lu)):
            raise ValueError("only multi-model units can be combined")
        if on and lu.joined_to:
            raise ValueError("a joined Hero cannot be combined")

        def fn():
            lu.combined = bool(on)
            if not on:
                lu.choices_b = None
        self._edit("combined", fn)

    def _single(self, lu) -> bool:
        book = self.lib.books.get(lu.book)
        u = book.units.get(lu.unit_id) if book else None
        return u is None or u.size < 2

    def set_copy_b(self, key: str, separate: bool) -> None:
        """Copy B with its own choices (a copy of A's to start), or the
        same as copy A."""
        lu = self.entry(key)
        if not lu.combined:
            raise ValueError("only a Combined unit has a copy B")

        def fn():
            if separate and lu.choices_b is None:
                lu.choices_b = copy.deepcopy(lu.choices)
            elif not separate:
                lu.choices_b = None
        self._edit("copy B", fn)

    def join(self, guest: str, host: str) -> None:
        g, h = self.entry(guest), self.entry(host)
        res = self.result()
        why = []
        if guest == host:
            why.append("a unit cannot join itself")
        if h.joined_to:
            why.append("cannot join a unit that is itself joined")
        if any(u.joined_to == guest for u in self.army.units):
            why.append("a unit with a Hero joined cannot join another")
        other = next((u for u in self.army.units
                      if u.joined_to == host and u.key != guest), None)
        if other is not None:
            why.append(f"{host!r} already has a Hero joined ({other.key!r})")
        gu, hu = res.entries[guest].unit, res.entries[host].unit
        if gu is None or hu is None:
            why.append("unit missing from its book")
        else:
            why += join_issues(gu, hu)
        if g.combined:
            why.append("a Combined unit cannot join")
        if why:
            raise ValueError("; ".join(why))
        self._edit("join Hero", lambda: setattr(g, "joined_to", host))

    def unjoin(self, guest: str) -> None:
        g = self.entry(guest)
        self._edit("leave unit", lambda: setattr(g, "joined_to", None))

    # --- choices ------------------------------------------------------------------------

    def _refs(self, lu, copy_: str):
        if copy_ not in COPIES:
            raise ValueError(f"copy must be one of {COPIES}")
        if copy_ == "b":
            if not lu.combined or lu.choices_b is None:
                raise ValueError("copy B uses copy A's choices")
            return lu.choices_b
        return lu.choices

    def config(self, key: str, copy_: str = "a") -> UnitConfig:
        """UnitConfig of one copy, with the choices that link."""
        lu = self.entry(key)
        self._refs(lu, copy_)
        book = self.lib.books.get(lu.book)
        link = links.link_unit(book, lu)
        if link.unit_id is None:
            raise ValueError("; ".join(link.invalid))
        refs = link.choices if copy_ == "a" else link.choices_b
        return UnitConfig(book, link.unit_id, [r.choice() for r in refs])

    def invalid(self, key: str, copy_: str = "a") -> list[AL.ChoiceRef]:
        """Choices of a copy that no longer link to the book."""
        lu = self.entry(key)
        self._refs(lu, copy_)
        link = links.link_unit(self.lib.books.get(lu.book), lu)
        if link.unit_id is None:
            return list(self._refs(lu, copy_))
        return link.lost if copy_ == "a" else link.lost_b

    def commit(self, key: str, cfg: UnitConfig, copy_: str = "a") -> None:
        """Store the choices of 'cfg' in the entry; the refs that do not
        link are kept after them."""
        lu = self.entry(key)
        self._refs(lu, copy_)
        if (cfg.book.uid, cfg.unit.id) != (lu.book, lu.unit_id):
            raise ValueError("the configuration is for another unit")
        lost = self.invalid(key, copy_)
        refs = [AL.make_ref(cfg.book, cfg.unit, c) for c in cfg.choices]

        def fn():
            if copy_ == "a":
                lu.choices = refs + lost
            else:
                lu.choices_b = refs + lost
        self._edit("upgrades", fn)

    def drop_invalid(self, key: str, copy_: str = "a") -> int:
        """Remove the choices that no longer link (explicit user action)."""
        lu = self.entry(key)
        lost = self.invalid(key, copy_)
        if not lost:
            return 0

        def fn():
            keep = [r for r in self._refs(lu, copy_) if r not in lost]
            if copy_ == "a":
                lu.choices = keep
            else:
                lu.choices_b = keep
        self._edit("drop invalid choices", fn)
        return len(lost)

    def set_models(self, key: str, index: int, models, copy_: str = "a"
                   ) -> None:
        """Placement of the instances of the index-th choice: a model index
        (0-based) or None (automatic) per instance. A placement
        resolve() cannot honour is reported, not refused."""
        lu = self.entry(key)
        ref = self._refs(lu, copy_)[index]
        models = None if models is None else list(models)
        if models is not None and (len(models) > ref.count or not all(
                m is None or (isinstance(m, int) and m >= 0) for m in models)):
            raise ValueError(f"at most {ref.count} model indices >= 0 or None")
        self._edit("placement", lambda: setattr(
            ref, "models", models if models and any(
                m is not None for m in models) else None))

    def candidates(self, key: str, index: int, picks, copy_: str = "a"):
        """Models able to take each instance of the index-th choice of a
        copy if placed as 'picks' (resolve.placement_candidates);
        None when the choice does not link or cannot be placed."""
        lu = self.entry(key)
        refs = self._refs(lu, copy_)
        link = links.link_unit(self.lib.books.get(lu.book), lu)
        if link.unit_id is None:
            return None
        lost = {id(r) for r in (link.lost if copy_ == "a" else link.lost_b)}
        if id(refs[index]) in lost:
            return None
        pos = sum(1 for r in refs[:index] if id(r) not in lost)
        valid = link.choices if copy_ == "a" else link.choices_b
        return placement_candidates(self.lib.books[lu.book], link.unit_id,
                                    [r.choice() for r in valid], pos, picks)

    # --- overrides ----------------------------------------------------------------------

    def add_override(self, key: str, ov: dict) -> None:
        """Append an override (data.overrides); one that fails on the
        current unit is refused."""
        lu = self.entry(key)
        ru = self.result().entries[key].unit
        if ru is None:
            raise ValueError("unit missing from its book")
        out = overrides.apply(ru, [ov])
        if len(out.issues) > len(ru.issues):
            raise ValueError(out.issues[-1])
        self._edit("override", lambda: lu.overrides.append(dict(ov)))

    def remove_override(self, key: str, index: int) -> None:
        lu = self.entry(key)
        lu.overrides[index]                         # IndexError if bad
        self._edit("remove override", lambda: lu.overrides.pop(index))
