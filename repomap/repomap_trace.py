"""pytest plugin: record what each test executes in one package, plus value summaries.

Load with:  REPOMAP_ROOT=src/werkzeug REPOMAP_OUT=map.json python -m pytest -p repomap_trace ...
(the directory holding this file must be on PYTHONPATH).

Uses sys.monitoring (Python 3.12+). For each test it records the package lines executed. Each line
event is disabled after its first hit and re-armed at the next test, so the cost is one callback per
distinct line per test. For every package function it keeps a bounded summary of argument and return
values: types seen and whether empty / zero / negative / None / bool values ever appeared.

Output JSON:
  tests:     {nodeid: {"outcome": pass|fail|skip, "lines": ["rel/file.py:123", ...]}}
  edges:     [[caller, callee], ...] with REPOMAP_EDGES=1; caller "<test>" for calls from test code
  functions: {"rel/file.py:Qual.name": {"first": line, "calls": n, "args": {name: summary},
              "returns": summary, "raises": {exc type: n}}}
"""
import json, os, sys
from collections import defaultdict

mon = sys.monitoring
TOOL = 4  # free tool id: leaves debugger, coverage and profiler slots to the code under test
E = mon.events
ROOT = os.path.abspath(os.environ.get("REPOMAP_ROOT", "src"))
BASE = os.path.dirname(ROOT)
OUT = os.environ.get("REPOMAP_OUT", "repomap.json")
EDGES = os.environ.get("REPOMAP_EDGES") == "1"  # also record caller -> callee edges (slower)
SAMPLES = int(os.environ.get("REPOMAP_SAMPLES", "30"))  # calls per function per test that get value summaries


def summary():
    return {"types": defaultdict(int), "flags": defaultdict(int)}


def note(s, v):
    t = type(v)
    s["types"][t.__qualname__ if t.__module__ == "builtins" else f"{t.__module__}.{t.__qualname__}"] += 1
    f = s["flags"]
    try:
        if v is None:
            f["none"] += 1
        elif isinstance(v, bool):
            f["true" if v else "false"] += 1
        elif isinstance(v, (int, float)):
            f["zero" if v == 0 else "negative" if v < 0 else "positive"] += 1
            if isinstance(v, float) and v != v:
                f["nan"] += 1
        elif isinstance(v, (str, bytes, list, tuple, dict, set, frozenset)):
            f["empty" if len(v) == 0 else "nonempty"] += 1
            if isinstance(v, (str, bytes)) and v and (v.strip() != v):
                f["edge_whitespace"] += 1
            if isinstance(v, str) and not v.isascii():
                f["non_ascii"] += 1
    except Exception:
        f["unsummarisable"] += 1


class Recorder:
    def __init__(self):
        self.tests = {}
        self.funcs = {}
        self.lines = None
        self.calls = defaultdict(int)
        self.mine = {}
        self.edges = set()

    def is_mine(self, code):
        r = self.mine.get(code)
        if r is None:
            r = self.mine[code] = code.co_filename.startswith(ROOT)
        return r

    def key(self, code):
        return f"{os.path.relpath(code.co_filename, BASE)}:{code.co_qualname}"

    def func(self, code):
        k = self.key(code)
        f = self.funcs.get(k)
        if f is None:
            f = self.funcs[k] = {"first": code.co_firstlineno, "calls": 0, "args": {}, "returns": summary(),
                                 "raises": defaultdict(int)}
        return f

    def on_line(self, code, line):
        if not self.is_mine(code):
            return mon.DISABLE
        if self.lines is not None:
            self.lines.add(f"{os.path.relpath(code.co_filename, BASE)}:{line}")
        return mon.DISABLE

    def on_start(self, code, offset):
        if not self.is_mine(code):
            return mon.DISABLE
        f = self.func(code)
        f["calls"] += 1
        self.calls[code] += 1
        if EDGES:
            back = sys._getframe(1).f_back
            if back is not None:
                cc = back.f_code
                caller = self.key(cc) if self.is_mine(cc) else (
                    "<test>" if os.sep + "tests" + os.sep in cc.co_filename else None)
                if caller:
                    self.edges.add((caller, self.key(code)))
        if self.calls[code] > SAMPLES:
            return
        frame = sys._getframe(1)
        names = code.co_varnames[:code.co_argcount + code.co_kwonlyargcount
                                  + bool(code.co_flags & 4) + bool(code.co_flags & 8)]
        for n in names:
            if n in ("self", "cls"):
                continue
            note(f["args"].setdefault(n, summary()), frame.f_locals.get(n))

    def on_return(self, code, offset, value):
        if not self.is_mine(code):
            return mon.DISABLE
        if self.calls[code] <= SAMPLES:
            note(self.func(code)["returns"], value)

    def on_raise(self, code, offset, exc):
        if self.is_mine(code) and self.calls[code] <= SAMPLES:
            self.func(code)["raises"][type(exc).__name__] += 1

    def start(self):
        mon.use_tool_id(TOOL, "repomap")
        mon.register_callback(TOOL, E.LINE, self.on_line)
        mon.register_callback(TOOL, E.PY_START, self.on_start)
        mon.register_callback(TOOL, E.PY_RETURN, self.on_return)
        mon.register_callback(TOOL, E.RAISE, self.on_raise)
        mon.set_events(TOOL, E.LINE | E.PY_START | E.PY_RETURN | E.RAISE)

    def begin_test(self):
        self.lines = set()
        self.calls.clear()
        mon.restart_events()

    def end_test(self, nodeid, outcome):
        t = self.tests.setdefault(nodeid, {"outcome": "pass", "lines": set()})
        t["lines"] |= self.lines or set()
        if outcome != "pass" and t["outcome"] == "pass":  # setup/teardown failures count too
            t["outcome"] = outcome
        self.lines = None

    def dump(self):
        mon.set_events(TOOL, 0)
        mon.free_tool_id(TOOL)
        out = {"root": os.path.relpath(ROOT, BASE),
               "tests": {k: {"outcome": v["outcome"], "lines": sorted(v["lines"])} for k, v in self.tests.items()},
               "functions": self.funcs, "edges": sorted(self.edges)}
        with open(OUT, "w") as fh:
            json.dump(out, fh, default=dict)


REC = Recorder()


def pytest_configure(config):
    REC.start()


def pytest_runtest_setup(item):
    REC.begin_test()


def pytest_runtest_logreport(report):
    outcome = "fail" if report.failed else "skip" if report.skipped and report.when == "setup" else "pass"
    if report.when == "teardown" or report.failed:
        REC.end_test(report.nodeid, outcome)
        REC.lines = set() if report.when != "teardown" else None
    elif report.when == "setup" and report.skipped:
        REC.end_test(report.nodeid, "skip")


def pytest_unconfigure(config):
    REC.dump()
