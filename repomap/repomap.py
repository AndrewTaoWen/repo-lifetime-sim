#!/usr/bin/env python3
"""repomap: remember what the test suite runs, then ask what a change will touch without running anything.

  repomap.py record   [--package src/pkg] [--tests tests] [--python PY]
        Trace the whole suite once and save the memory to .repomap/memory.json (lines per test,
        call graph, value summaries, and the commit + file hashes it was recorded at).
  repomap.py impact   [TARGET ...] [--diff [REV]] [--json]
        TARGET is a function name (or part of one) or path.py:LINE. With --diff (or no target),
        uses your uncommitted changes against the recorded commit. Reads only the memory file.
        Prints the changed functions, their callers grouped by module, the tests that run them,
        a pytest command for those tests, and anything the memory can't vouch for.
  repomap.py refresh  [--diff [REV]]
        Re-trace only the tests that run code in the changed files (plus changed test files) and
        merge them into the memory, so the next lookup is current without a full re-record.
  repomap.py status
        What the memory covers and which package files have changed since it was recorded.
  repomap.py serve    [--port 8765] [--open] [--export FILE.html]
        Open the map in a browser at a localhost link: modules and functions coloured by how many tests
        run them, a function's callers, callees and recorded values, and the impact of your uncommitted
        changes or of any functions you pick. --export writes the same page as one self-contained file.

Run from the repo root. Needs Python 3.12+ in the interpreter that runs the tests.
"""
import argparse, ast, hashlib, json, os, re, subprocess, sys, tempfile, time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
MEM = Path(".repomap/memory.json")


# ---------- helpers ----------

def git(*a, check=True):
    return subprocess.run(["git", *a], capture_output=True, text=True, check=check).stdout


def file_hash(p):
    try:
        return hashlib.sha1(Path(p).read_bytes()).hexdigest()[:12]
    except OSError:
        return None


def functions(src):
    """[(start, end, qualname)] for every function in a source file, sorted so the innermost wins last."""
    out = []
    def walk(node, prefix):
        for n in ast.iter_child_nodes(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = f"{prefix}{n.name}"
                out.append((min([n.lineno] + [d.lineno for d in n.decorator_list]), n.end_lineno, q))
                walk(n, q + ".<locals>.")
            elif isinstance(n, ast.ClassDef):
                walk(n, f"{prefix}{n.name}.")
    try:
        walk(ast.parse(src), "")
    except SyntaxError:
        pass
    return sorted(out, key=lambda x: (x[0], -x[1]))


def func_at(fs, line):
    best = None
    for s, e, q in fs:
        if s <= line <= e:
            best = q
    return best


def module(key):
    return re.sub(r"(/__init__)?\.py$", "", key.split(":", 1)[0]).replace("/", ".")


def load():
    if not MEM.exists():
        sys.exit("No memory yet. Run: repomap.py record")
    return json.loads(MEM.read_text())


def save(m):
    MEM.parent.mkdir(exist_ok=True)
    MEM.write_text(json.dumps(m, separators=(",", ":")))


def trace(m, test_args, out):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(Path(m["package"]).parent), str(HERE),
                                                        os.environ.get("PYTHONPATH", "")]),
           "REPOMAP_ROOT": m["package"], "REPOMAP_OUT": str(out), "REPOMAP_EDGES": "1"}
    cmd = [m["python"], "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly", "-o", "addopts=",
           "-p", "repomap_trace", *test_args]
    p = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if not Path(out).exists():
        sys.exit(f"Tracing failed:\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
    return json.loads(Path(out).read_text())


def worktree_snapshot(keep=True):
    """A git tree of the working tree as it is now (tracked + untracked, minus ignored), kept alive by
    refs/repomap/memory. The memory remembers this tree, so later diffs are against exactly what was traced."""
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "GIT_INDEX_FILE": f"{td}/index"}
        run = lambda *a: subprocess.run(["git", *a], env=env, capture_output=True, text=True)  # noqa: E731
        if run("rev-parse", "--git-dir").returncode:
            return None
        run("read-tree", "HEAD")
        run("add", "-A")
        tree = run("write-tree").stdout.strip()
    head = git("rev-parse", "HEAD", check=False).strip()
    commit = subprocess.run(["git", "commit-tree", tree, *(["-p", head] if head else []), "-m", "repomap memory"],
                            capture_output=True, text=True, env={**os.environ, "GIT_AUTHOR_NAME": "repomap",
                            "GIT_AUTHOR_EMAIL": "repomap@localhost", "GIT_COMMITTER_NAME": "repomap",
                            "GIT_COMMITTER_EMAIL": "repomap@localhost"}).stdout.strip()
    if commit and keep:
        git("update-ref", "refs/repomap/memory", commit, check=False)
    return commit or None


def package_files(m):
    return sorted(str(p) for p in Path(m["package"]).rglob("*.py"))


# ---------- record ----------

def record(a):
    m = dict(package=a.package.rstrip("/"), tests=a.tests, python=a.python, commit=worktree_snapshot())
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        raw = trace(m, [a.tests], Path(td) / "map.json")
    m.update(prefix=str(Path(m["package"]).parent) + "/", tests_map=raw["tests"], functions=raw["functions"],
             edges=raw["edges"], hashes={f: file_hash(f) for f in package_files(m)}, recorded=time.time())
    save(m)
    print(f"Recorded {len(raw['tests'])} tests, {len(raw['functions'])} functions, {len(raw['edges'])} call edges "
          f"in {time.time() - t0:.0f}s -> {MEM}")


# ---------- working out what changed ----------

def old_source(m, path):
    """The file as it was when the memory was last recorded or refreshed, or the current file if unknown."""
    if m.get("commit"):
        src = subprocess.run(["git", "show", f"{m['commit']}:{path}"], capture_output=True, text=True)
        if src.returncode == 0:
            return src.stdout
    return Path(path).read_text() if Path(path).exists() else ""


def changed_targets(m, rev):
    """{key "rel/file.py:Qual"} touched by the diff between the memory's snapshot (or REV) and the working tree,
    plus changed test files. Uses the recorded version of each file to find the functions."""
    base = rev or m.get("commit") or "HEAD"
    now = worktree_snapshot(keep=False) or "HEAD"  # includes untracked files, like the memory's snapshot
    diff = git("diff", "-U0", "--no-renames", base, now, "--", m["package"], m["tests"])
    keys, test_files, cur = set(), set(), None
    fs_cache = {}
    for l in diff.splitlines():
        if l.startswith("--- "):
            cur = None if l == "--- /dev/null" else l[6:]
        elif l.startswith("+++ ") and cur is None:
            cur = l[6:]
        elif l.startswith("@@") and cur:
            if cur.startswith(m["tests"]):
                test_files.add(cur)
                continue
            if not cur.endswith(".py") or not cur.startswith(m["package"]):
                continue
            mm = re.match(r"@@ -(\d+)(?:,(\d+))?", l)
            start, n = int(mm[1]), int(mm[2] or 1)
            fs = fs_cache.setdefault(cur, functions(old_source(m, cur)))
            rel = cur[len(m["prefix"]):]
            hit = False
            for ln in (range(start, start + n) if n else range(start, start + 2)):
                q = func_at(fs, ln)
                if q:
                    keys.add(f"{rel}:{q}")
                    hit = True
            if not hit:
                keys.add(f"{rel}:<module level>")
    return keys, test_files


def resolve(m, targets):
    """Function names, partial names or path.py:LINE -> memory keys."""
    keys = set()
    for t in targets:
        mm = re.match(r"(.+\.py):(\d+)$", t)
        if mm:
            path = mm[1] if mm[1].startswith(m["prefix"]) else m["prefix"] + mm[1]
            q = func_at(functions(old_source(m, path)), int(mm[2]))
            keys.add(f"{path[len(m['prefix']):]}:{q or '<module level>'}")
            continue
        found = [k for k in m["functions"] if k.endswith(":" + t) or k.endswith("." + t)] or \
                [k for k in m["functions"] if t in k]
        if not found:
            print(f"  (nothing in memory matches {t!r})")
        keys.update(found)
    return keys


# ---------- impact ----------

def lines_index(m):
    """key -> tests that run it, built from per-test lines and the recorded function ranges."""
    by_file = defaultdict(list)  # rel file -> [(test, line)]
    for t, v in m["tests_map"].items():
        for l in v["lines"]:
            f, n = l.rsplit(":", 1)
            by_file[f].append((t, int(n)))
    return by_file


def tests_for(m, keys, by_file):
    out = defaultdict(set)
    cache = {}
    for k in keys:
        rel, q = k.split(":", 1)
        path = m["prefix"] + rel
        fs = cache.setdefault(rel, functions(old_source(m, path)))
        if q in ("<module level>", "<new file>"):
            out[k] = {t for t, _ in by_file.get(rel, [])}  # anything that runs code in the file
            continue
        span = [(s, e) for s, e, qq in fs if qq == q]
        out[k] = {t for t, n in by_file.get(rel, []) if any(s <= n <= e for s, e in span)}
    return out


def callers_of(m, keys, depth=2):
    up = defaultdict(set)
    for caller, callee in m["edges"]:
        if caller != "<test>" and caller != callee:
            up[callee].add(caller)
    seen, frontier, layers = set(keys), set(keys), []
    for _ in range(depth):
        nxt = {c for k in frontier for c in up.get(k, ())} - seen
        if not nxt:
            break
        layers.append(nxt)
        seen |= nxt
        frontier = nxt
    return layers


def compute_impact(m, targets=(), diff=None, use_diff=True, depth=2):
    """The impact of named targets, or of the working-tree diff against the memory's snapshot (or REV)."""
    t0 = time.time()
    if targets:
        keys, test_files = resolve(m, targets), set()
        source = "named targets"
    else:
        keys, test_files = changed_targets(m, diff)
        source = f"changes since {(diff or m.get('commit') or 'HEAD')[:10]}"
    by_file = lines_index(m)
    per_key = tests_for(m, keys, by_file)
    tests = set().union(*per_key.values()) if per_key else set()
    for tf in test_files:
        tests |= {t for t in m["tests_map"] if t.startswith(tf)} or {tf}
    layers = callers_of(m, {k for k in keys if not k.endswith(">")}, depth)
    unknown = sorted(k for k in keys if not per_key.get(k) and not k.endswith(">"))
    stale = sorted(f for f, h in m["hashes"].items() if file_hash(f) != h)
    return dict(source=source, changed=sorted(keys), changed_tests={k: len(v) for k, v in per_key.items()},
                test_files=sorted(test_files), callers=[sorted(l) for l in layers], tests=sorted(tests),
                untested=unknown, files_changed_since_record=stale, seconds=round(time.time() - t0, 2))


def impact(a):
    m = load()
    res = compute_impact(m, a.targets if not a.diff_given else (), a.diff, depth=a.depth)
    keys, test_files, tests, unknown, stale = (set(res["changed"]), res["test_files"], set(res["tests"]),
                                               res["untested"], res["files_changed_since_record"])
    layers, source = [set(l) for l in res["callers"]], res["source"]
    per_key = {k: range(n) for k, n in res["changed_tests"].items()}
    if a.json:
        print(json.dumps(res, indent=1))
        return
    print(f"Impact of {source}  ({len(m['tests_map'])} tests in memory, looked up in {res['seconds']}s)\n")
    if not keys and not test_files:
        print("No changes to library or test code.")
        return
    print("Changed:")
    for k in sorted(keys):
        print(f"  {k}  ({len(per_key.get(k, ()))} tests)")
    for tf in sorted(test_files):
        print(f"  {tf}  (test file)")
    if layers:
        print("\nCallers (pieces that depend on it):")
        for i, l in enumerate(layers, 1):
            by_mod = defaultdict(list)
            for k in l:
                by_mod[module(k)].append(k.split(":", 1)[1])
            for mod in sorted(by_mod):
                names = sorted(by_mod[mod])
                more = f" … +{len(names) - 6}" if len(names) > 6 else ""
                print(f"  {'  ' * (i - 1)}{'direct' if i == 1 else f'level {i}'}  {mod}: {', '.join(names[:6])}{more}")
    by_tf = defaultdict(int)
    for t in tests:
        by_tf[t.split("::", 1)[0]] += 1
    print(f"\nTests that run it: {len(tests)} of {len(m['tests_map'])}")
    for tf, n in sorted(by_tf.items(), key=lambda x: -x[1])[:15]:
        print(f"  {n:4d}  {tf}")
    if len(by_tf) > 15:
        print(f"        … {len(by_tf) - 15} more files")
    if unknown:
        print("\nNo test in memory runs these, so the memory can't say what depends on them:")
        for k in unknown:
            print(f"  {k}")
    if stale:
        print(f"\n{len(stale)} library files changed since recording; run `repomap.py refresh` to update.")
    if tests:
        sel = sorted({t.split('[')[0] for t in tests}) if len(tests) < 40 else sorted(by_tf)
        print(f"\nRun them:\n  {m['python']} -m pytest -q " + " ".join(sel[:40]) + (" …" if len(sel) > 40 else ""))


# ---------- refresh ----------

def refresh(a):
    t0 = time.time()
    m = load()
    keys, test_files = changed_targets(m, a.diff)
    files = {k.split(":", 1)[0] for k in keys}
    by_file = lines_index(m)
    rerun = {t for f in files for t, _ in by_file.get(f, [])}
    targets = sorted({t.split("::", 1)[0] for t in rerun} | test_files) if a.by_file else sorted(rerun | test_files)
    if not targets:
        print("Nothing to refresh.")
        return
    with tempfile.TemporaryDirectory() as td:
        args = targets
        if len(" ".join(args)) > 100_000:  # very long node-id lists: fall back to whole test files
            args = sorted({t.split("::", 1)[0] for t in targets})
        raw = trace(m, args, Path(td) / "map.json")
    # line numbers in changed files are only valid for re-traced tests; drop everyone else's lines there
    # (by construction nobody else ran those files), then merge
    for t in list(m["tests_map"]):
        if t in raw["tests"] or any(t.startswith(tf) for tf in test_files):
            m["tests_map"].pop(t, None)
    m["tests_map"].update(raw["tests"])
    touched = {m["prefix"] + f for f in files}
    m["edges"] = [e for e in m["edges"] if not any(x.split(":", 1)[0] in files for x in e)]
    m["edges"] = sorted({tuple(e) for e in m["edges"]} | {tuple(e) for e in raw["edges"]})
    for k, v in raw["functions"].items():
        m["functions"][k] = v
    m["hashes"].update({f: file_hash(f) for f in package_files(m)})
    m["commit"] = worktree_snapshot() or m.get("commit")
    save(m)
    print(f"Re-traced {len(raw['tests'])} tests (of {len(m['tests_map'])}) touching {len(touched)} changed files "
          f"in {time.time() - t0:.0f}s; memory updated.")


def status(a):
    m = load()
    stale = sorted(f for f, h in m["hashes"].items() if file_hash(f) != h)
    print(f"Memory: {len(m['tests_map'])} tests, {len(m['functions'])} functions, recorded at "
          f"snapshot {(m.get('commit') or '?')[:10]} (refs/repomap/memory)")
    print(f"Library files changed since: {len(stale)}" + ("".join(f"\n  {f}" for f in stale)))


# ---------- serve ----------

def ui_data(m):
    """Everything the map page needs, indexed so the browser can work out impact by itself
    (same rules as `impact`: a function's tests are those that ran any line of it)."""
    tests = sorted(m["tests_map"])
    tix = {t: i for i, t in enumerate(tests)}
    by_file = lines_index(m)
    fns, fidx = [], {}
    for path in sorted(m["hashes"]):
        rel = path[len(m["prefix"]):]
        src = old_source(m, path)
        at_line = defaultdict(list)
        fidx[f"{rel}:<module level>"] = len(fns)
        fns.append([f"{rel}:<module level>", 0, 0, set()])
        for s_, e, q in functions(src):
            fidx[f"{rel}:{q}"] = len(fns)
            for n in range(s_, e + 1):
                at_line[n].append(len(fns))
            fns.append([f"{rel}:{q}", s_, e, set()])
        for t, n in by_file.get(rel, []):
            fns[fidx[f"{rel}:<module level>"]][3].add(tix[t])
            for i in at_line.get(n, ()):
                fns[i][3].add(tix[t])
    vals = {}
    for k, f in m["functions"].items():
        if k in fidx:
            vals[fidx[k]] = {"calls": f["calls"], "args": f["args"], "returns": f["returns"], "raises": f["raises"]}
    edges = sorted({(fidx[a], fidx[b]) for a, b in m["edges"] if a in fidx and b in fidx and a != b})
    stale = sorted(f for f, h in m["hashes"].items() if file_hash(f) != h)
    return dict(name=Path.cwd().name, package=m["package"], tests_dir=m["tests"], python=m["python"],
                commit=(m.get("commit") or "")[:10], recorded=m.get("recorded"),
                tests=[[t, m["tests_map"][t]["outcome"]] for t in tests],
                fns=[[k, s_, e, sorted(t)] for k, s_, e, t in fns], vals=vals, edges=edges, stale=stale)


def page_with(data, changes):
    page = (HERE / "repomap_ui.html").read_text()
    blob = json.dumps({"data": data, "changes": changes}, separators=(",", ":")).replace("</", "<\\/")
    return page.replace('<script id="embedded" type="application/json"></script>',
                        f'<script id="embedded" type="application/json">{blob}</script>')


def serve(a):
    if a.export:
        m = load()
        res = compute_impact(m)
        Path(a.export).write_text(page_with(ui_data(m), res if res["changed"] or res["test_files"] else None))
        print(f"Wrote {a.export} ({Path(a.export).stat().st_size // 1024} KB)")
        return
    cache = {}

    def current():
        mt = MEM.stat().st_mtime  # a refresh in another terminal shows up on the next reload
        if cache.get("mt") != mt:
            m = load()
            cache.update(mt=mt, m=m, data=json.dumps(ui_data(m), separators=(",", ":")).encode())
        return cache

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlparse(self.path).path
            try:
                if path == "/":
                    body, kind = (HERE / "repomap_ui.html").read_bytes(), "text/html; charset=utf-8"
                elif path == "/api/data":
                    body, kind = current()["data"], "application/json"
                elif path == "/api/changes":
                    body, kind = json.dumps(compute_impact(current()["m"])).encode(), "application/json"
                else:
                    self.send_error(404)
                    return
            except Exception as e:  # keep serving; show the error in the page
                body, kind = json.dumps({"error": str(e)}).encode(), "application/json"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    load()
    for port in range(a.port, a.port + 20):
        try:
            srv = ThreadingHTTPServer((a.host, port), Handler)
            break
        except OSError:
            continue
    else:
        sys.exit(f"No free port from {a.port} to {a.port + 19}.")
    url = f"http://localhost:{port}"
    print(f"repomap map of {Path.cwd().name}: {url}   (Ctrl-C to stop)", flush=True)
    if a.open:
        import webbrowser
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--package", default=None)
    r.add_argument("--tests", default="tests")
    r.add_argument("--python", default=sys.executable)
    i = sub.add_parser("impact")
    i.add_argument("targets", nargs="*")
    i.add_argument("--diff", nargs="?", const=None, default=False)
    i.add_argument("--depth", type=int, default=2)
    i.add_argument("--json", action="store_true")
    f = sub.add_parser("refresh")
    f.add_argument("--diff", nargs="?", const=None, default=None)
    f.add_argument("--by-file", action="store_true", help="re-run whole test files instead of single tests")
    sub.add_parser("status")
    v = sub.add_parser("serve")
    v.add_argument("--port", type=int, default=8765)
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--open", action="store_true", help="open the link in your browser")
    v.add_argument("--export", metavar="FILE", help="write a self-contained HTML file instead of serving")
    a = ap.parse_args()
    if a.cmd == "record":
        if not a.package:
            cands = [p for p in Path("src").glob("*/__init__.py")] or [p for p in Path(".").glob("*/__init__.py")
                                                                     if p.parent.name not in ("tests", "docs")]
            if len(cands) != 1:
                sys.exit("Pass --package (e.g. src/mypkg).")
            a.package = str(cands[0].parent)
        record(a)
    elif a.cmd == "impact":
        a.diff_given = a.diff is not False
        a.diff = a.diff or None
        impact(a)
    elif a.cmd == "refresh":
        refresh(a)
    elif a.cmd == "serve":
        serve(a)
    else:
        status(a)


if __name__ == "__main__":
    main()
