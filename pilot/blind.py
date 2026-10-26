#!/usr/bin/env python3
"""Prepare blind hardening workspaces and score them against future tests.

prep:  blind.py prep  --root DIR --clones DIR --cutoff 2026-06-01 --runs 3 owner/repo ...
       Creates DIR/<name>-r<k>/ (snapshot tree as its own git repo) with a private venv,
       and checks the snapshot's own tests pass. Writes DIR/<name>-r<k>/.blind.json.
score: blind.py score --root DIR --screen DIR  [run-dir-names...]
       For each run, swaps the run's package code into the future tree from the screen
       step (screen.py) and runs the future tests. Writes DIR/scores.json.
"""
import argparse, json, os, shutil, subprocess, sys
import defusedxml.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from screen import sh, git, package_dirs, tests_dir, generated_files, archive_tree  # noqa: E402

ENV_EXTRA = {"SETUPTOOLS_SCM_PRETEND_VERSION": os.environ.get("SETUPTOOLS_SCM_PRETEND_VERSION", "0.0.0")}


def junit_results(path):
    res = {}
    for tc in ET.parse(path).getroot().iter("testcase"):
        kids = {c.tag for c in tc}
        res[f"{tc.get('classname')}::{tc.get('name')}"] = (
            "fail" if kids & {"failure", "error"} else "skip" if "skipped" in kids else "pass")
    return res


def prep(a):
    for spec in a.repos:
        owner, name = spec.split("/")
        repo = a.clones / f"{owner}_{name}"
        snap = git(repo, "rev-list", "-1", f"--before={a.cutoff}", "HEAD").strip()
        for k in range(1, a.runs + 1):
            d = a.root / f"{name}-r{k}"
            shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True)
            archive_tree(repo, snap, d)
            venv = d / ".venv"
            env = {**os.environ, **ENV_EXTRA, "VIRTUAL_ENV": str(venv)}
            sh(["uv", "venv", "-q", "-p", "3.13", str(venv)])
            sh(["uv", "pip", "install", "-q", "pytest", *a.dep], env=env)
            for group in ("test", "tests", "dev", "testing"):
                if sh(["uv", "pip", "install", "-q", "-e", ".", "--group", group], cwd=d, env=env)[0] == 0:
                    break
            else:
                sh(["uv", "pip", "install", "-q", "-e", "."], cwd=d, env=env)
            tdir = tests_dir(d)
            cmd = f".venv/bin/python -m pytest -q -p no:cacheprovider -o addopts= {tdir}"
            code, out = sh(cmd, cwd=d, timeout=1800)
            (d / ".gitignore").write_text(".venv/\n__pycache__/\n*.egg-info/\njunit.xml\n")
            sh(["git", "init", "-q"], cwd=d)
            sh(["git", "add", "-A"], cwd=d)
            sh(["git", "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-qm", "snapshot"], cwd=d)
            meta = dict(repo=spec, snapshot=snap, test_cmd=cmd, baseline=out.strip().splitlines()[-1][:200])
            (d / ".blind.json").write_text(json.dumps(meta, indent=1))
            print(f"{d.name}: {meta['baseline']}", flush=True)


def run_future(work, repo, scr, py, place):
    """Rebuild the future tree in `work`, put package code there with place(dst, p), run the tests."""
    gen = {p: generated_files(repo, scr["head"], work, p) for p in scr["packages"]} if work.exists() else {}
    for p in list(work.iterdir()):
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    archive_tree(repo, scr["head"], work)
    for p in scr["packages"]:
        target = work / p
        keep = gen.get(p, {})
        shutil.rmtree(target, ignore_errors=True) if target.is_dir() else target.unlink(missing_ok=True)
        place(target, p)
        for rel, data in keep.items():  # install-time generated files (e.g. version.py) missing from archives
            if not (work / rel).exists():
                (work / rel).parent.mkdir(parents=True, exist_ok=True)
                (work / rel).write_bytes(data)
    junit = work / "junit.xml"
    sh([str(py), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly", "-o", "addopts=",
        "--continue-on-collection-errors", f"--junitxml={junit}", scr["tests"]], cwd=work, timeout=2400)
    return junit_results(junit) if junit.exists() else {}


def score(a):
    scores_path = a.root / "scores.json"
    scores = json.loads(scores_path.read_text()) if scores_path.exists() else {}
    controls = {}
    runs = a.runs or sorted(p.name for p in a.root.iterdir() if (p / ".blind.json").exists())
    for run in runs:
        d = a.root / run
        meta = json.loads((d / ".blind.json").read_text())
        name = meta["repo"].split("/")[1]
        scr = json.loads((a.screen / f"{name}.json").read_text())
        work = a.screen / "work" / name
        clones = a.screen.parent / "screen"
        repo = clones / meta["repo"].replace("/", "_")
        py = a.screen / "venvs" / name / "bin" / "python"
        if name not in controls:  # future tests on the untouched snapshot code, for regressions
            controls[name] = run_future(work, repo, scr, py, lambda dst, p: archive_tree(repo, meta["snapshot"], work, p))
        control = controls[name]

        def copy_from_run(dst, p):
            src = d / p
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
        res = run_future(work, repo, scr, py, copy_from_run)
        target = set(scr["future_tests_failing_on_snapshot"])
        fixed = sorted(t for t in target if res.get(t) == "pass")
        # regressions: future tests that pass on the untouched snapshot but fail after hardening
        regress = sorted(t for t, st in res.items() if st == "fail" and control.get(t) == "pass")
        commits = int(git(d, "rev-list", "--count", "HEAD").strip() or 0) - 1
        stat = git(d, "diff", "--shortstat", git(d, "rev-list", "--max-parents=0", "HEAD").splitlines()[0]).strip()
        scores[run] = dict(repo=meta["repo"], target=len(target), fixed=len(fixed), regressions=len(regress),
                           fixed_tests=fixed, regressed_tests=regress[:50], agent_commits=commits, diff=stat)
        print(f"{run}: fixed {len(fixed)}/{len(target)}, regressions {len(regress)}, {stat}", flush=True)
        scores_path.write_text(json.dumps(scores, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--clones", type=Path, required=True)
    p.add_argument("--cutoff", default="2026-06-01")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--dep", action="append", default=[])
    p.add_argument("repos", nargs="+")
    s = sub.add_parser("score")
    s.add_argument("--root", type=Path, required=True)
    s.add_argument("--screen", type=Path, required=True)
    s.add_argument("runs", nargs="*")
    a = ap.parse_args()
    prep(a) if a.cmd == "prep" else score(a)
