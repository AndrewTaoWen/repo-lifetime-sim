#!/usr/bin/env python3
"""Replay upstream's real post-snapshot history onto each hardening run, as a maintainability cost.

usage: replay.py --screen DIR --patches DIR [--out FILE] [--tests] run-name ...

For each run (e.g. werkzeug-r3) the agent's patch is committed on top of the snapshot in the clone
(objects and a refs/replay/<run> ref only; no checkout). Then, for every first-parent upstream commit
C after the snapshot, it does a 3-way merge of the agent commit with C (base = snapshot) and counts
conflict hunks, split into package code and everything else (tests, docs, changelog).
  collisions  upstream commits that add conflict hunks over the previous commit: the real changes a
              maintainer would have had to hand-merge with the agent's edits
  final_*     conflicts merging all of upstream's history at once
With --tests, the final merge is also resolved in upstream's favour (-X theirs) and HEAD's tests run on
the merged package code. broken = tests that pass on upstream HEAD but fail on the merge: semantic
interference that a clean textual merge hides.
"""
import argparse, json, os, re, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blind import run_future  # noqa: E402
from screen import sh  # noqa: E402


def g(repo, *args, env=None, check=True, input=None):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                       env={**os.environ, **(env or {})}, input=input)
    if check and p.returncode not in (0, 1):
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr}")
    return p


def agent_commit(repo, snap, patch, run):
    with tempfile.TemporaryDirectory() as td:
        env = {"GIT_INDEX_FILE": f"{td}/index", "GIT_AUTHOR_NAME": "agent", "GIT_AUTHOR_EMAIL": "a@a",
               "GIT_COMMITTER_NAME": "agent", "GIT_COMMITTER_EMAIL": "a@a"}
        g(repo, "read-tree", snap, env=env)
        p = g(repo, "apply", "--cached", "--whitespace=nowarn", str(patch), env=env, check=False)
        if p.returncode:
            raise RuntimeError(f"{run}: patch does not apply: {p.stderr[:300]}")
        tree = g(repo, "write-tree", env=env).stdout.strip()
        sha = g(repo, "commit-tree", tree, "-p", snap, "-m", f"agent {run}", env=env).stdout.strip()
    g(repo, "update-ref", f"refs/replay/{run}", sha)
    return sha


def conflicts(repo, snap, ours, theirs, packages):
    """Conflict hunks of a 3-way merge, split into package code and other files."""
    p = g(repo, "merge-tree", "--write-tree", "--name-only", f"--merge-base={snap}", ours, theirs)
    lines = p.stdout.splitlines()
    tree, files = lines[0], [l for l in lines[1:] if l and not l.startswith(("Auto-merging", "CONFLICT"))]
    out = {"package": 0, "other": 0, "files": {}}
    for f in dict.fromkeys(files):
        blob = g(repo, "cat-file", "-p", f"{tree}:{f}", check=False).stdout
        n = max(len(re.findall(r"^<<<<<<< ", blob, re.M)), 1)  # modify/delete etc. count as one hunk
        out["package" if f.startswith(tuple(packages)) else "other"] += n
        out["files"][f] = n
    return out


def replay(run, screen, patches, tests):
    name = run.rsplit("-r", 1)[0]
    scr = json.loads((screen / f"{name}.json").read_text())
    repo = screen.parent / "screen" / scr["repo"].replace("/", "_")
    snap, head, pk = scr["snapshot"], scr["head"], scr["packages"]
    agent = agent_commit(repo, snap, patches / f"{run}.patch", run)
    ups = g(repo, "rev-list", "--first-parent", "--reverse", f"{snap}..{head}").stdout.split()
    prev, collisions = {}, []
    for c in ups:
        k = conflicts(repo, snap, agent, c, pk)["files"]
        grew = {f: n - prev.get(f, 0) for f, n in k.items() if n > prev.get(f, 0)}
        if grew:
            collisions.append(dict(commit=c[:10], subject=g(repo, "log", "-1", "--format=%s", c).stdout.strip(),
                                   new_hunks=sum(grew.values()), files=sorted(grew)))
        prev = k
    final = conflicts(repo, snap, agent, head, pk)
    res = dict(upstream_commits=len(ups), collisions=len(collisions),
               collision_package=sum(1 for x in collisions if any(f.startswith(tuple(pk)) for f in x["files"])),
               final_package_hunks=final["package"], final_other_hunks=final["other"],
               final_files=sorted(final["files"]), collision_detail=collisions,
               diff=g(repo, "diff", "--shortstat", snap, agent).stdout.strip())
    if tests:
        tree = g(repo, "merge-tree", "--write-tree", "-X", "theirs", f"--merge-base={snap}", agent, head).stdout.split()[0]
        work, py = screen / "work" / name, screen / "venvs" / name / "bin" / "python"
        place = lambda dst, p: sh(f"git -C {repo} archive {tree} {p} | tar -x -C {work}")  # noqa: E731
        merged = run_future(work, repo, scr, py, place)
        upstream = run_future(work, repo, scr, py, lambda dst, p: sh(f"git -C {repo} archive {head} {p} | tar -x -C {work}"))
        res["broken"] = sorted(t for t, s in merged.items() if s == "fail" and upstream.get(t) == "pass")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen", type=Path, required=True)
    ap.add_argument("--patches", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--tests", action="store_true")
    ap.add_argument("runs", nargs="+")
    a = ap.parse_args()
    out = json.loads(a.out.read_text()) if a.out and a.out.exists() else {}
    for run in a.runs:
        r = out[run] = replay(run, a.screen, a.patches, a.tests)
        print(f"{run}: {r['collisions']}/{r['upstream_commits']} upstream commits collide "
              f"({r['collision_package']} in package code); final conflicts {r['final_package_hunks']} package, "
              f"{r['final_other_hunks']} other" + (f"; broken {len(r['broken'])}" if "broken" in r else ""), flush=True)
        if a.out:
            a.out.write_text(json.dumps(out, indent=1))
