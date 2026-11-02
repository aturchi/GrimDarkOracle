"""Shared path resolution for the headless test harness.

Importing this module puts the repository root on ``sys.path`` (so tests
can ``from grimdarkoracle.engine import pmf``) and resolves where Army Forge
data is read from: the synthetic book shipped in ``tests/synthetic/`` or
a real download made by ``tools/af_fetch.py``.

Both sources share af_fetch's layout, so tests never see the difference:

    <root>/books/<uid>.json
    <root>/rules/common_<gs>.json

Default is SYNTHETIC: OPR data must never be committed, so a bare checkout
has to run the whole suite. Real data is used only when requested via
``GRIMDARKORACLE_TEST_REAL=1``, ``GRIMDARKORACLE_TEST_DATA=<dir>`` or
``--real_data`` on the command line; if requested but absent, the suite
falls back to synthetic AND says so on stderr (a silent fallback would let
a run reported as real be entirely synthetic).
"""
import configparser
import json
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_TESTS_DIR)
SYNTHETIC_DIR = os.path.join(_TESTS_DIR, "synthetic")
_CONFIG_FILE = os.path.join(_TESTS_DIR, "test_config.ini")
_DEFAULT_REAL = os.path.join("data", "army_forge")
_ARGV_FLAG = "--real_data"
GAME_SYSTEM = 2

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _truthy(value):
    """Interpret an env-var string as a boolean flag."""
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _configured_real_dir():
    """Real-data root: env var, then test_config.ini [paths] data_dir,
    then data/army_forge. Relative values are taken from the repo root."""
    raw = os.environ.get("GRIMDARKORACLE_TEST_DATA")
    if not raw:
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(_CONFIG_FILE)                    # silently ignored if absent
        raw = cp.get("paths", "data_dir", fallback=_DEFAULT_REAL)
    return raw if os.path.isabs(raw) else os.path.normpath(
        os.path.join(REPO_ROOT, raw))


def _real_requested():
    """Whether real data was explicitly asked for (env or argv)."""
    return (bool(os.environ.get("GRIMDARKORACLE_TEST_DATA"))
            or _truthy(os.environ.get("GRIMDARKORACLE_TEST_REAL", ""))
            or _ARGV_FLAG in sys.argv[1:])


def _probe(root):
    """A data root is usable when it holds the core rules file."""
    return os.path.isfile(rules_path(GAME_SYSTEM, root))


def _resolve(force_real=None):
    """Return (data_dir, using_synthetic); see the module docstring."""
    want_real = _real_requested() if force_real is None else force_real
    if want_real:
        real = _configured_real_dir()
        if _probe(real):
            return real, False
        print(f"testpaths: real data requested but not found under "
              f"{real!r} - falling back to the synthetic book",
              file=sys.stderr)
    return SYNTHETIC_DIR, True


def rules_path(gs=GAME_SYSTEM, root=None):
    """Path of the core special rules of game system 'gs'."""
    return os.path.join(root or DATA_DIR, "rules", f"common_{gs}.json")


def book_path(uid, root=None):
    """Path of army book 'uid' in the active source."""
    return os.path.join(root or DATA_DIR, "books", f"{uid}.json")


def load_json(path):
    """Parse a UTF-8 JSON file."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_book(uid):
    """Load army book 'uid' from the active source."""
    return load_json(book_path(uid))


def set_source(real):
    """Re-resolve the active source at runtime (True = real data)."""
    global DATA_DIR, USING_SYNTHETIC
    DATA_DIR, USING_SYNTHETIC = _resolve(force_real=real)
    return DATA_DIR, USING_SYNTHETIC


DATA_DIR, USING_SYNTHETIC = _resolve()
