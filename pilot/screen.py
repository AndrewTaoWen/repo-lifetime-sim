#!/usr/bin/env python3
"""Screen repos for "future tests": tests at a later ref that fail on the code as of a cutoff.

For each repo: build the later tree, install it in its own venv, run its tests (sanity),
then swap in the package code from the cutoff snapshot and run the same tests again.
Writes <out>/<name>.json with pass/fail sets for both runs.

usage: screen.py --out DIR --clones DIR --cutoff 2026-06-01 owner/repo [owner/repo ...]
"""
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path


def sh(cmd, cwd=None, timeout=900, env=None):
    r = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True,
                       text=True, timeout=timeout, env=env)
    return r.returncode, r.stdout + r.stderr


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def package_dirs(tree: Path):
    """Top-level importable code: src/<pkg>, or <pkg>/ with __init__.py, or single-module .py files."""
    if (tree / "src").is_dir():
        return [Path("src")]
    skip = {"tests", "test", "docs", "doc", "examples", "scripts", "benchmarks", "bench", "tools", "ci"}
    out = [Path(p.name) for p in tree.iterdir()
           if p.is_dir() and p.name not in skip and not p.name.startswith(".") and (p / "__init__.py").exists()]
    out += [Path(p.name) for p in tree.glob("*.py") if p.name not in {"setup.py", "conftest.py", "noxfile.py"}]
    return out


def tests_dir(tree: Path):
    for d in ("tests", "test", "testing"):
        if (tree / d).is_dir():
            return d
    return "."


def run_pytest(d: Path, py: Path, tests: str, extra):
    junit = d / "junit.xml"
    code, out = sh([str(py), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                    "--continue-on-collection-errors", f"--junitxml={junit}", *extra, tests], cwd=d, timeout=1200)
    results = {}
    if junit.exists():
        import xml.etree.ElementTree as ET
        for tc in ET.parse(junit).getroot().iter("testcase"):
            nid = f"{tc.get('classname')}::{tc.get('name')}"
            kids = {c.tag for c in tc}
            results[nid] = ("fail" if kids & {"failure", "error"} else
                            "skip" if "skipped" in kids else "pass")
    summary = re.findall(r"^=*\s*(\d+ (?:passed|failed).*?)\s*=*$", out, re.M)
    return results, (summary[-1] if summary else out[-500:])


def screen(spec, clones: Path, out: Path, cutoff: str, extra, extra_deps=()):
    owner, name = spec.split("/")
    repo = clones / f"{owner}_{name}"
    if not repo.exists():
        sh(["git", "clone", "-q", "--filter=blob:none", f"https://github.com/{spec}", str(repo)])
    snap = git(repo, "rev-list", "-1", f"--before={cutoff}", "HEAD").strip()
    head = git(repo, "rev-parse", "HEAD").strip()
    work = out / "work" / name
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    sh(f"git -C {repo} archive {head} | tar -x -C {work}")
    venv = out / "venvs" / name
    if not venv.exists():
        sh(["uv", "venv", "-q", "-p", "3.13", str(venv)])
    py = venv / "bin" / "python"
    env = {**os.environ, "VIRTUAL_ENV": str(venv),
           # git archive has no .git, so tell setuptools-scm / hatch-vcs what version to use
           "SETUPTOOLS_SCM_PRETEND_VERSION": "0.0.0"}
    sh(["uv", "pip", "install", "-q", "pytest"], env=env)
    # install the package (with deps) plus any test dependency group / requirements we can find
    for group in ("test", "tests", "dev", "testing"):
        if sh(["uv", "pip", "install", "-q", "-e", ".", "--group", group], cwd=work, env=env)[0] == 0:
            break
    else:
        sh(["uv", "pip", "install", "-q", "-e", "."], cwd=work, env=env)
    for req in list(work.glob("requirements*test*.txt")) + list(work.glob("*/requirements*test*.txt")) \
            + list(work.glob("requirements/test*.txt")):
        sh(["uv", "pip", "install", "-q", "-r", str(req)], env=env)
    if extra_deps:
        sh(["uv", "pip", "install", "-q", *extra_deps], env=env)
    tdir = tests_dir(work)
    fut, fut_sum = run_pytest(work, py, tdir, extra)
    pkgs = package_dirs(work)
    for p in pkgs:
        target = work / p
        shutil.rmtree(target, ignore_errors=True) if target.is_dir() else target.unlink(missing_ok=True)
        sh(f"git -C {repo} archive {snap} {p} | tar -x -C {work}")
    old, old_sum = run_pytest(work, py, tdir, extra)
    newly_failing = sorted(t for t, s in old.items() if s == "fail" and fut.get(t) == "pass")
    res = dict(repo=spec, snapshot=snap, snapshot_date=git(repo, "log", "-1", "--format=%cs", snap).strip(),
               head=head, head_date=git(repo, "log", "-1", "--format=%cs", head).strip(),
               packages=[str(p) for p in pkgs], tests=tdir,
               future_on_future=fut_sum, future_on_snapshot=old_sum,
               n_future_pass=sum(s == "pass" for s in fut.values()), future_tests_failing_on_snapshot=newly_failing)
    (out / f"{name}.json").write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--clones", required=True, type=Path)
    ap.add_argument("--cutoff", default="2026-06-01")
    ap.add_argument("--pytest-arg", action="append", default=[])
    ap.add_argument("--dep", action="append", default=[], help="extra test dependency to install")
    ap.add_argument("repos", nargs="+")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for spec in a.repos:
        try:
            r = screen(spec, a.clones, a.out, a.cutoff, a.pytest_arg, a.dep)
            print(f"{spec}: future={r['future_on_future']} | snapshot={r['future_on_snapshot']} "
                  f"| newly failing={len(r['future_tests_failing_on_snapshot'])}", flush=True)
        except Exception as e:  # keep screening the rest
            print(f"{spec}: ERROR {e!r}"[:300], flush=True)
