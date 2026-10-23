#!/usr/bin/env python3
"""Bundle impact.py results and the snapshot call graph into one JSON for the impact viewer page.

usage: build_ui.py --clone DIR --package src/werkzeug --impact impact.json --map snap-map.json --out data.json
"""
import argparse, json, re, subprocess, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from impact import functions, git, hunks  # noqa: E402


def module(key):
    f = key.split(":", 1)[0]
    return re.sub(r"(/__init__)?\.py$", "", f).replace("/", ".")


def changed_functions(repo, p, c, package):
    out, base = [], str(Path(package).parent) + "/"
    for rel, hs in hunks(repo, p, c, package).items():
        try:
            src = git(repo, "show", f"{p}:{base}{rel}")
        except subprocess.CalledProcessError:
            src = ""
        fs = functions(src)
        for start, n in hs:
            hit = None
            for ln in (range(start, start + n) if n else range(start, start + 2)):
                for s, e, q in fs:
                    if s <= ln <= e:
                        hit = q
            out.append(f"{rel}:{hit}" if hit else f"{rel}:<module level>")
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser()
    for k in ("clone", "package", "impact", "map", "out"):
        ap.add_argument(f"--{k}", required=True)
    a = ap.parse_args()
    repo = Path(a.clone)
    imp = json.loads(Path(a.impact).read_text())
    snap = json.loads(Path(a.map).read_text())
    callers = defaultdict(set)
    for caller, callee in snap["edges"]:
        if caller != "<test>" and caller != callee:
            callers[callee].add(caller)
    public = {callee for caller, callee in snap["edges"] if caller == "<test>"}

    commits = []
    for c, r in imp.items():
        if c.startswith("_"):
            continue
        p = git(repo, "rev-parse", f"{c}^1").strip()
        changed = changed_functions(repo, p, c, a.package)
        # callers up to 3 levels, from the snapshot call graph
        seen, frontier, layers = set(changed), set(changed), []
        for _ in range(3):
            nxt = {x for f in frontier for x in callers.get(f, ())} - seen
            if not nxt:
                break
            layers.append(sorted(nxt))
            seen |= nxt
            frontier = nxt
        affected_fns = set(changed) | {x for l in layers for x in l}
        pieces = defaultdict(lambda: {"changed": [], "callers": [], "entry": 0})
        for f in changed:
            pieces[module(f)]["changed"].append(f.split(":", 1)[1])
        for l in layers:
            for f in l:
                pieces[module(f)]["callers"].append(f.split(":", 1)[1])
        for f in affected_fns:
            if f in public:
                pieces[module(f)]["entry"] += 1
        truth = r["truth"]
        pred = set(r["function"]["tests"])
        by_file = defaultdict(lambda: {"predicted": 0, "affected": 0, "missed": 0})
        for t in pred | set(truth):
            tf = t.split("::", 1)[0]
            if t in pred:
                by_file[tf]["predicted"] += 1
            if t in truth:
                by_file[tf]["affected"] += 1
                if t not in pred:
                    by_file[tf]["missed"] += 1
        reasons = defaultdict(int)
        for w in truth.values():
            reasons["behaviour changed" if set(w) & {"outcome", "path"} else
                    "reaches new code only" if w == ["new_code"] else "runs changed code"] += 1
        commits.append(dict(
            sha=c[:10], subject=r["subject"], date=git(repo, "log", "-1", "--format=%cs", c).strip(),
            files=r["files"], suite=r["suite"], changed=changed,
            pieces=sorted(({"name": k, **v} for k, v in pieces.items()),
                          key=lambda x: (-len(x["changed"]), -len(x["callers"]), x["name"])),
            tests=sorted(({"file": k, **v} for k, v in by_file.items()), key=lambda x: (-x["affected"], -x["predicted"])),
            truth=len(truth), reasons=dict(reasons),
            outcome_changed=sorted(t for t, w in truth.items() if "outcome" in w),
            missed=sorted(set(truth) - pred),
            pred={k: dict(selected=r[k]["selected"], hit=r[k]["hit"]) for k in ("line", "function", "file", "stale")}))
    Path(a.out).write_text(json.dumps(dict(repo="werkzeug", suite=commits[0]["suite"] if commits else 0,
                                           commits=commits), separators=(",", ":")))
    print(len(commits), "commits")


if __name__ == "__main__":
    main()
