#!/usr/bin/env python3
"""One-shot runner for the GrimDarkOracle test suite in tests/.

Runs every ``test_*.py`` in this directory, each in its own subprocess
(the suite mixes ``unittest`` modules, which call ``sys.exit``, and plain
``assert`` scripts), judges each by its exit code and prints one report:
a PASS / FAIL table, timings, a summary and the output of the failures.

Data: tests read Army Forge data through ``testpaths``, which defaults to
the synthetic book in ``tests/synthetic/``; ``--real_data`` switches the
whole suite to the real download in ``data/army_forge`` (af_fetch).

Usage:
    python3 tests/run_all.py                # synthetic data
    python3 tests/run_all.py --real_data    # real Army Forge data
    python3 tests/run_all.py -v             # also stream each test's output
    python3 tests/run_all.py -k pmf         # only tests whose name has 'pmf'

Exit code: the number of FAIL/ERROR tests (0 when all pass).
"""
import argparse
import os
import subprocess
import sys
import time

import testpaths                       # noqa: F401  (sets sys.path)

# Test files deliberately left out of the suite.
_EXCLUDED = set()

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

# ANSI colours, disabled when the output is not a TTY (e.g. piped to a file).
_TTY = sys.stdout.isatty()


def _c(code, text):
    """Wrap text in an ANSI colour code when writing to a terminal."""
    return f"\033[{code}m{text}\033[0m" if _TTY else text


_STATUS_STYLE = {
    "PASS": ("32", "PASS"),      # green
    "FAIL": ("31", "FAIL"),      # red
    "ERROR": ("31", "ERROR"),    # red
}


def discover():
    """Return the ordered list of test filenames to run.

    All ``test_*.py`` in this directory (minus _EXCLUDED), sorted."""
    names = sorted(f for f in os.listdir(_TESTS_DIR)
                   if f.startswith("test_") and f.endswith(".py")
                   and f not in _EXCLUDED)
    return names


def run_one(fname, extra_args=None, env=None):
    """Run a single test file as a subprocess.

    Returns a dict with keys: name, status, seconds, output. 'status' is
    one of PASS / FAIL / ERROR. 'extra_args' are appended to the child's
    argv; 'env' is the child environment (used to select real data
    suite-wide)."""
    path = os.path.join(_TESTS_DIR, fname)
    cmd = [sys.executable, path] + list(extra_args or [])

    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd, cwd=_TESTS_DIR, env=env, capture_output=True, text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired as exc:
        return {"name": fname, "status": "ERROR",
                "seconds": time.perf_counter() - start,
                "output": f"TIMEOUT after {exc.timeout}s\n"
                          f"{exc.stdout or ''}{exc.stderr or ''}"}

    seconds = time.perf_counter() - start
    output = (proc.stdout or "") + (proc.stderr or "")
    # Exit code 0 == the test's own asserts/unittest all passed.
    status = "PASS" if proc.returncode == 0 else "FAIL"
    return {"name": fname, "status": status, "seconds": seconds,
            "output": output.strip()}


def _print_report(results, verbose):
    """Print the per-test table, failing-test output, and the summary."""
    width = max(len(r["name"]) for r in results)

    print()
    print(_c("1", "GrimDarkOracle test suite"))
    print("=" * (width + 26))
    for r in results:
        colour, label = _STATUS_STYLE[r["status"]]
        line = (f"  {r['name']:<{width}}  "
                f"{_c(colour, f'{label:<5}')}  {r['seconds']:6.2f}s")
        print(line)
        if verbose and r["output"]:
            for ln in r["output"].splitlines():
                print(f"      {ln}")
    print("=" * (width + 26))

    # Detailed output for anything that did not pass or skip.
    problems = [r for r in results if r["status"] in ("FAIL", "ERROR")]
    if problems:
        print()
        print(_c("1", "Output of failing tests"))
        for r in problems:
            colour, label = _STATUS_STYLE[r["status"]]
            print("-" * (width + 26))
            print(f"{_c(colour, label)}  {r['name']}")
            print("-" * (width + 26))
            print(r["output"] or "(no output captured)")

    # Summary line.
    n = len(results)
    passed = sum(r["status"] == "PASS" for r in results)
    failed = sum(r["status"] in ("FAIL", "ERROR") for r in results)
    total_s = sum(r["seconds"] for r in results)
    print()
    parts = [_c("32", f"{passed} passed")]
    if failed:
        parts.append(_c("31", f"{failed} failed"))
    print(f"{', '.join(parts)}  of {n} tests in {total_s:.2f}s")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Run the GrimDarkOracle test suite and report.")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="also print each test's own captured output")
    ap.add_argument("-k", metavar="SUBSTR", default=None,
                    help="only run tests whose filename contains SUBSTR")
    ap.add_argument("--real_data", action="store_true",
                    help="run the whole suite against the real Army Forge "
                         "data instead of the synthetic book")
    args = ap.parse_args(argv)

    tests = discover()
    if args.k:
        tests = [t for t in tests if args.k in t]
        if not tests:
            print(f"No tests match -k {args.k!r}")
            return 0

    # --real_data selects the real source for every test via the env flag.
    child_env = dict(os.environ)
    if args.real_data:
        child_env["GRIMDARKORACLE_TEST_REAL"] = "1"

    results = []
    for fname in tests:
        r = run_one(fname, env=child_env)
        results.append(r)
        # Live one-line progress so a long run isn't silent.
        colour, label = _STATUS_STYLE[r["status"]]
        print(f"{_c(colour, label):<5}  {r['name']}  ({r['seconds']:.2f}s)")

    _print_report(results, args.verbose)

    # Exit code = number of failing tests (0 when all pass).
    return sum(r["status"] in ("FAIL", "ERROR") for r in results)


if __name__ == "__main__":
    sys.exit(main())
