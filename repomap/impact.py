#!/usr/bin/env python3
"""Score change-impact predictions from a traced test map against a repo's real later commits.

usage: impact.py --clone DIR --python PY --snapshot SHA --head SHA --package src/werkzeug
                 --tests tests --work DIR --out FILE

For every first-parent commit C after the snapshot that touches package code (parent P):
  1. trace P's tests on P's code (the map), and P's tests on C's code;
  2. ground truth: tests whose outcome changes, that run changed code (old lines in P or new lines in C),
     or whose path through unchanged package lines differs after aligning P's line numbers to C's;
  3. predictions from the map of P:
       line      tests that ran a changed line (insertions anchor on the neighbouring old lines)
       function  tests that ran any function whose body the change touches; a module-level change
                 falls back to every test that ran code in that file
       file      tests that ran any code in a changed file
       stale     the function predictor, but using the map traced once at the snapshot
     plus the share of the suite each one selects.
Tests whose function sets differ between two traces of the same code are flaky and excluded.
"""
import argparse, ast, json, os, re, shutil, subprocess, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout


def archive_tree(repo, rev, dst, package=None):
    """Extract a git tree without interpreting paths or refs as shell syntax."""
    import tempfile
    commit = git(repo, "rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}").strip()
    command = ["git", "-C", str(repo), "archive", commit]
    if package is not None:
        command += ["--", str(package)]
    with tempfile.TemporaryFile() as stream:
        subprocess.run(command, stdout=stream, check=True)
        stream.seek(0)
        subprocess.run(["tar", "-x", "-C", str(dst)], stdin=stream, check=True)


def tree(repo, rev, dst, src_rev=None, package=None):
    shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True)
    archive_tree(repo, rev, dst)
    if src_rev:
        shutil.rmtree(dst / package)
        archive_tree(repo, src_rev, dst, package)


def trace(a, d, out):
    env = {**os.environ, "PYTHONPATH": f"{d / Path(a.package).parent}:{HERE}", "REPOMAP_ROOT": a.package,
           "REPOMAP_OUT": str(out), "REPOMAP_SAMPLES": "0"}
    subprocess.run([a.python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly", "-o", "addopts=",
                    "-p", "repomap_trace", a.tests], cwd=d, env=env, capture_output=True, timeout=3600)
    return json.loads(out.read_text())


def functions(src):
    """[(start, end, qualname)] for every function in a source file, innermost last."""
    out = []
    def walk(node, prefix):
        for n in ast.iter_child_nodes(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = f"{prefix}{n.name}"
                start = min([n.lineno] + [x.lineno for x in n.decorator_list])
                out.append((start, n.end_lineno, q))
                walk(n, q + ".<locals>.")
            elif isinstance(n, ast.ClassDef):
                walk(n, f"{prefix}{n.name}.")
    try:
        walk(ast.parse(src), "")
    except SyntaxError:
        pass
    return sorted(out, key=lambda x: (x[0], -x[1]))


class Index:
    """Maps "rel/file.py:line" to the innermost enclosing function, for one source tree."""
    def __init__(self, root):
        self.root, self.cache = root, {}

    def funcs(self, rel):
        if rel not in self.cache:
            p = self.root / rel
            self.cache[rel] = functions(p.read_text()) if p.exists() else []
        return self.cache[rel]

    def func_of(self, rel, line):
        best = None
        for s, e, q in self.funcs(rel):
            if s <= line <= e:
                best = q  # sorted by start, so the last match is innermost
        return best


def func_sets(m, idx):
    out = {}
    for t, v in m["tests"].items():
        fs = set()
        for l in v["lines"]:
            rel, line = l.rsplit(":", 1)
            q = idx.func_of(rel, int(line))
            if q:  # module and class-body lines run once at import, whichever test imports first
                fs.add(f"{rel}:{q}")
        out[t] = fs
    return out


def hunks(repo, p, c, package):
    """{rel file: [(old_start, old_len)]} for package .py files, rel to the package's parent dir."""
    diff = git(repo, "diff", "-U0", p, c, "--", package)
    base = str(Path(package).parent) + "/"
    out, cur = defaultdict(list), None
    for l in diff.splitlines():
        if l.startswith("--- "):
            cur = l[6:] if l.startswith("--- a/") else None
        elif l.startswith("+++ ") and cur is None and l.startswith("+++ b/"):
            cur = l[6:]  # new file: no old lines
        elif l.startswith("@@") and cur and cur.endswith(".py"):
            m = re.match(r"@@ -(\d+)(?:,(\d+))?", l)
            out[cur[len(base):] if cur.startswith(base) else cur].append((int(m.group(1)), int(m.group(2) or 1)))
    return out


def alignment(repo, p, c, package):
    """Per file: (changed old lines, changed new lines, old->new offset table) from a -U0 diff."""
    diff = git(repo, "diff", "-U0", "--no-renames", p, c, "--", package)
    base = str(Path(package).parent) + "/"
    rel = lambda f: f[len(base):] if f.startswith(base) else f  # noqa: E731
    out, old, new = {}, None, None
    for l in diff.splitlines():
        if l.startswith("--- "):
            old = None if l == "--- /dev/null" else l[6:]
        elif l.startswith("+++ "):
            new = None if l == "+++ /dev/null" else l[6:]
            f = rel(new or old)
            out[f] = dict(old=set(), new=set(), shifts=[], added=old is None, deleted=new is None)
        elif l.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))?", l)
            os_, on, ns, nn = int(m[1]), int(m[2] or 1), int(m[3]), int(m[4] or 1)
            d = out[rel(new or old)]
            d["old"].update(range(os_, os_ + on))
            d["new"].update(range(ns, ns + nn))
            d["shifts"].append((os_ + on if on else os_ + 1, (ns + nn if nn else ns + 1) - (os_ + on if on else os_ + 1)))
    return out


def affected(mp, mc, al):
    """Per test, how it is affected between P and C: {"outcome", "old_code", "new_code", "path"} subsets.
    old_code: ran a changed or deleted line in P; new_code: ran a changed or added line in C;
    path: its lines through unchanged code differ once P's line numbers are aligned to C's."""
    def split(l):
        f, n = l.rsplit(":", 1)
        return f, int(n)
    def to_new(f, n):
        d = al.get(f)
        if not d:
            return n
        if n in d["old"] or d["deleted"]:
            return None
        off = 0
        for start, delta in d["shifts"]:
            if n >= start:
                off = delta
        return n + off
    res = {}
    for t, v in mp["tests"].items():
        w = mc["tests"].get(t)
        if w is None:
            continue
        why = set()
        if v["outcome"] != w["outcome"]:
            why.add("outcome")
        pl = [split(l) for l in v["lines"]]
        cl = [split(l) for l in w["lines"]]
        if any(f in al and (n in al[f]["old"] or al[f]["deleted"]) for f, n in pl):
            why.add("old_code")
        if any(f in al and (n in al[f]["new"] or al[f]["added"]) for f, n in cl):
            why.add("new_code")
        mapped = {(f, m) for f, n in pl if (m := to_new(f, n)) is not None}
        unchanged_c = {(f, n) for f, n in cl if not (f in al and (n in al[f]["new"] or al[f]["added"]))}
        if mapped != unchanged_c:
            why.add("path")
        if why:
            res[t] = why
    return res


def predict(m, idx, fsets, hk):
    lines_by_test = {t: set(v["lines"]) for t, v in m["tests"].items()}
    line_p, func_p, file_p = set(), set(), set()
    for rel, hs in hk.items():
        changed_lines, changed_funcs, module_level = set(), set(), False
        for start, n in hs:
            span = range(start, start + n) if n else range(start, start + 2)  # insertion after line `start`
            for ln in span:
                changed_lines.add(f"{rel}:{ln}")
                q = idx.func_of(rel, ln)
                if q:
                    changed_funcs.add(f"{rel}:{q}")
                elif n:
                    module_level = True
        for t, ls in lines_by_test.items():
            in_file = any(x.startswith(rel + ":") for x in ls)
            if in_file:
                file_p.add(t)
            if ls & changed_lines:
                line_p.add(t)
            if fsets[t] & changed_funcs or (module_level and in_file):
                func_p.add(t)
    return line_p, func_p, file_p


def stale_predict(snap_fsets, idx_p, hk):
    changed = set()
    for rel, hs in hk.items():
        for start, n in hs:
            for ln in (range(start, start + n) if n else range(start, start + 2)):
                q = idx_p.func_of(rel, ln)
                if q:
                    changed.add(f"{rel}:{q}")
    return {t for t, fs in snap_fsets.items() if fs & changed}


def main():
    ap = argparse.ArgumentParser()
    for k in ("clone", "python", "snapshot", "head", "package", "tests", "work", "out"):
        ap.add_argument(f"--{k}", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    repo, work = Path(a.clone), Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    out = json.loads(Path(a.out).read_text()) if Path(a.out).exists() else {}

    # flaky tests: function sets that differ between two traces of the snapshot
    snapdir = work / "snap"
    tree(repo, a.snapshot, snapdir)
    m1, m2 = trace(a, snapdir, work / "s1.json"), trace(a, snapdir, work / "s2.json")
    sidx = Index(snapdir / Path(a.package).parent)
    f1, f2 = func_sets(m1, sidx), func_sets(m2, sidx)
    flaky = set(affected(m1, m2, {}))
    out["_flaky"] = sorted(flaky)
    snap_fsets = f1

    commits = git(repo, "rev-list", "--first-parent", "--reverse", f"{a.snapshot}..{a.head}").split()
    done = 0
    for c in commits:
        if c in out:
            continue
        p = git(repo, "rev-parse", f"{c}^1").strip()
        hk = hunks(repo, p, c, a.package)
        if not hk:
            continue
        pd, cd = work / "p", work / "c"
        tree(repo, p, pd)
        tree(repo, p, cd, src_rev=c, package=a.package)
        mp, mc = trace(a, pd, work / "p.json"), trace(a, cd, work / "c.json")
        ip, ic = Index(pd / Path(a.package).parent), Index(cd / Path(a.package).parent)
        fp, fc = func_sets(mp, ip), func_sets(mc, ic)
        why = {t: w for t, w in affected(mp, mc, alignment(repo, p, c, a.package)).items() if t not in flaky}
        truth = set(why)  # any effect
        behaviour = {t for t, w in why.items() if w & {"outcome", "path"}}
        pool = {t for t in mp["tests"] if t not in flaky}
        lp, fnp, flp = predict(mp, ip, fp, hk)
        sp = stale_predict(snap_fsets, ip, hk)
        res = dict(subject=git(repo, "log", "-1", "--format=%s", c).strip(), files=sorted(hk), suite=len(pool),
                   truth={t: sorted(w) for t, w in sorted(why.items())})
        for name, pr in (("line", lp), ("function", fnp), ("file", flp), ("stale", sp)):
            pr = pr & pool
            res[name] = dict(selected=len(pr), hit=len(pr & truth), hit_behaviour=len(pr & behaviour),
                             missed=sorted(truth - pr), tests=sorted(pr))
        out[c] = res
        Path(a.out).write_text(json.dumps(out, indent=1))
        print(f"{c[:8]} truth {len(truth):4d} behaviour {len(behaviour):4d} | " + " | ".join(
            f"{n} {res[n]['hit']}/{len(truth)} b{res[n]['hit_behaviour']} sel {res[n]['selected']}"
            for n in ("line", "function", "file", "stale")),
            res["subject"][:50], flush=True)
        done += 1
        if a.limit and done >= a.limit:
            break


if __name__ == "__main__":
    main()
