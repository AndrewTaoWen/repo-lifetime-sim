#!/usr/bin/env python3
"""Mutation benchmark for repomap's impact lookups, independent of the tracer.

usage: (from the repo root, with a recorded .repomap/memory.json)
  mutbench.py --n 150 --seed 1 --out mutbench.json      inject faults and record which tests each one breaks
  mutbench.py --score mutbench.json [MEMORY.json ...]   score a memory's lookups against those results

For N functions that the memory says some test runs, inject one small fault (flip a comparison,
swap and/or, nudge an int constant, negate an if, or make a return give None), run the whole suite,
and compare the tests that start failing with the tests `repomap.py impact <function>` selects.
  safety     share of the failing tests that the lookup selected (1.0 = nothing missed)
  detected   whether at least one selected test fails (the lookup would have caught the fault)
  selected   how much of the suite the lookup asks you to run
Mutants no test notices ("survivors") say nothing about the lookup and are counted separately.
The broken tests are stored in full, so any later memory (a re-record, a changed tracer) can be scored
against the same faults without re-running the suite.
"""
import argparse, ast, json, random, signal, statistics, subprocess, sys, tempfile, time, xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repomap as rm  # noqa: E402

FLIP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt,
        ast.Is: ast.IsNot, ast.IsNot: ast.Is, ast.In: ast.NotIn, ast.NotIn: ast.In}


def candidates(fn_node):
    """(node, replacement source) pairs for single-line nodes inside one function body."""
    out = []
    for n in ast.walk(fn_node):
        if getattr(n, "lineno", None) != getattr(n, "end_lineno", -1):
            continue
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in FLIP:
            m = ast.Compare(left=n.left, ops=[FLIP[type(n.ops[0])]()], comparators=n.comparators)
            out.append((n, ast.unparse(m), "flip comparison"))
        elif isinstance(n, ast.BoolOp):
            m = ast.BoolOp(op=ast.Or() if isinstance(n.op, ast.And) else ast.And(), values=n.values)
            out.append((n, ast.unparse(m), "swap and/or"))
        elif isinstance(n, ast.Constant) and type(n.value) is int:
            out.append((n, str(n.value + 1), "int + 1"))
        elif isinstance(n, ast.Return) and n.value is not None and not (
                isinstance(n.value, ast.Constant) and n.value.value is None):
            out.append((n.value, "None", "return None"))
    for n in ast.walk(fn_node):
        if isinstance(n, ast.If) and n.test.lineno == n.test.end_lineno:
            out.append((n.test, f"not ({ast.unparse(n.test)})", "negate if"))
    return out


def splice(src, node, text):
    lines = src.splitlines(keepends=True)
    i = node.lineno - 1
    b = lines[i].encode()
    lines[i] = (b[:node.col_offset] + text.encode() + b[node.end_col_offset:]).decode()
    return "".join(lines)


def failing(m, junit):
    p = subprocess.run([m["python"], "-m", "pytest", "-q", "-x" if False else "-q", "-p", "no:cacheprovider",
                        "-p", "no:randomly", "-o", "addopts=", f"--junitxml={junit}", m["tests"]],
                       capture_output=True, text=True, env={**__import__("os").environ,
                       "PYTHONPATH": str(Path(m["package"]).parent)}, timeout=900)
    try:
        root = ET.parse(junit).getroot()
    except Exception:
        return None
    out = set()
    for tc in root.iter("testcase"):
        if any(c.tag in ("failure", "error") for c in tc):
            out.add(f"{tc.get('classname')}::{tc.get('name')}")  # "::tests.mod" = the module failed to import
    return out


def norm(nodeid):
    """pytest node id -> junit classname::name form, to compare the two. Parameters may contain "::"."""
    path, _, rest = nodeid.partition("::")
    base, br, params = rest.partition("[")
    parts = base.split("::")
    cls = path[:-3].replace("/", ".") + ("." + ".".join(parts[:-1]) if len(parts) > 1 else "")
    return f"{cls}::{parts[-1]}{br}{params}"


def score(results, mem_path):
    """Selection from one memory against the recorded broken tests of every mutant."""
    rm.MEM = Path(mem_path)
    m = rm.load()
    by_file = rm.lines_index(m)
    rows = []
    for r in results:
        killed = set(r["killed_tests"])
        sel = rm.tests_for(m, {r["function"]}, by_file)[r["function"]]
        seln = {norm(t) for t in sel}
        broken_mods = {k[2:] for k in killed if k.startswith("::")}  # import errors break every test in the module
        caught = {k for k in killed if k in seln} | {t for t in seln if t.split("::")[0] in broken_mods}
        per_test = {k for k in killed if not k.startswith("::")}
        rows.append(dict(function=r["function"], kind=r["kind"], selected=len(sel), suite=len(m["tests_map"]),
                         killed=len(killed), import_error=bool(broken_mods), caught=len(caught),
                         missed=sorted(per_test - seln), detected=bool(caught)))
    live = [x for x in rows if x["killed"]]
    tests_level = [x for x in live if not x["import_error"]]
    tot_k = sum(x["killed"] for x in tests_level)
    tot_m = sum(len(x["missed"]) for x in tests_level)
    return dict(memory=str(mem_path), mutants=len(rows), survivors=len(rows) - len(live),
                import_errors=sum(x["import_error"] for x in live),
                detected=sum(x["detected"] for x in live), detectable=len(live),
                broken_tests=tot_k, broken_tests_selected=tot_k - tot_m,
                mutants_missing_any=sum(bool(x["missed"]) for x in tests_level),
                selected_share_median=statistics.median(x["selected"] / x["suite"] for x in live) if live else None,
                selected_share_mean=statistics.mean(x["selected"] / x["suite"] for x in live) if live else None,
                misses=[x for x in tests_level if x["missed"]])


def report(results, mems):
    for mp in mems:
        s = score(results, mp)
        print(f"\n{s['memory']}: {s['mutants']} mutants, {s['survivors']} survived (no test noticed), "
              f"{s['import_errors']} broke an import")
        print(f"  detected (a selected test fails): {s['detected']} of {s['detectable']}")
        print(f"  broken tests selected: {s['broken_tests_selected']} of {s['broken_tests']} "
              f"({100 * s['broken_tests_selected'] / max(1, s['broken_tests']):.1f}%); "
              f"mutants with any broken test missed: {s['mutants_missing_any']}")
        print(f"  share of suite selected: median {100 * s['selected_share_median']:.1f}%, "
              f"mean {100 * s['selected_share_mean']:.1f}%")
        for x in s["misses"]:
            print(f"    missed {len(x['missed'])} of {x['killed']}: {x['function']} ({x['kind']})  e.g. {x['missed'][0]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="mutbench.json")
    ap.add_argument("--score", nargs="+", metavar=("RESULTS", "MEMORY"))
    a = ap.parse_args()
    if a.score:
        report(json.loads(Path(a.score[0]).read_text()), a.score[1:] or [str(rm.MEM)])
        return
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))  # restore the file on kill
    m = rm.load()
    by_file = rm.lines_index(m)
    rng = random.Random(a.seed)
    with tempfile.TemporaryDirectory() as td:
        base = failing(m, f"{td}/base.xml")
    print(f"baseline: {len(base)} failing tests", flush=True)

    keys = [k for k in m["functions"] if "<" not in k.split(":", 1)[1]]
    rng.shuffle(keys)
    results = json.loads(Path(a.out).read_text()) if Path(a.out).exists() else []
    done = {r["function"] for r in results}
    for k in keys:
        if len(results) >= a.n:
            break
        if k in done:
            continue
        rel, q = k.split(":", 1)
        path = Path(m["prefix"] + rel)
        src = path.read_text()
        tree = ast.parse(src)
        node = None
        for s, e, qq in rm.functions(src):
            if qq == q:
                node = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and n.lineno <= e and (n.end_lineno or 0) >= s and n.name == q.split(".")[-1])
        selected = rm.tests_for(m, {k}, by_file)[k]
        if node is None or not selected:
            continue
        cands = candidates(node)
        if not cands:
            continue
        target, text, kind = rng.choice(cands)
        original = src.splitlines()[target.lineno - 1]
        t0 = time.time()
        try:
            path.write_text(splice(src, target, text))
            with tempfile.TemporaryDirectory() as td:
                fails = failing(m, f"{td}/m.xml")
        finally:
            path.write_text(src)
        if fails is None:
            continue
        killed = fails - base
        sel = {norm(t) for t in selected}
        hit = killed & sel
        r = dict(function=k, kind=kind, line=target.lineno, original=original.strip(),
                 mutant=splice(src, target, text).splitlines()[target.lineno - 1].strip(), selected=len(selected),
                 suite=len(m["tests_map"]), killed=len(killed), caught=len(hit), killed_tests=sorted(killed),
                 seconds=round(time.time() - t0, 1))
        results.append(r)
        Path(a.out).write_text(json.dumps(results, indent=1))
        print(f"{len(results):3d} {k[:60]:60s} {kind:15s} killed {len(killed):3d} caught {len(hit):3d} "
              f"selected {len(selected):3d}", flush=True)
    report(results, [str(rm.MEM)])


if __name__ == "__main__":
    main()
