#!/usr/bin/env python3
"""Label each target future test as a latent bug or a new feature.

usage: label.py --screen DIR --clones DIR --out FILE repo-name ...

Two signals per target test:
  why it fails on the snapshot code: an API that doesn't exist yet (AttributeError, ImportError,
    unexpected keyword, ...) points to a feature; a wrong result or a missing exception points to a bug.
  the commit that added the test (first commit after the snapshot whose diff mentions the test name):
    "fix"/"bug"/"crash"/"regression" in its subject points to a bug; "add"/"support"/"feat"/"new" to a feature.
The failure type wins when it says the API is missing; otherwise the commit subject decides;
otherwise the test is "bug" when it fails by assertion and "unclear" when it errors some other way.
"""
import argparse, json, re, subprocess, sys
import defusedxml.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from screen import sh, git, archive_tree  # noqa: E402

MISSING_API = re.compile(
    r"has no attribute|cannot import name|No module named|is not defined|unexpected keyword argument|"
    r"got an unexpected|takes \d+ positional|missing \d+ required positional|fixture '.*' not found|"
    r"object is not callable|not subscriptable|is not iterable|DID NOT RAISE <class '.*Deprecat")
BUG_WORDS = re.compile(r"\b(fix|fixes|fixed|bug|crash|regression|incorrect|wrong|broken|handle|reject|prevent|avoid|error)", re.I)
FEATURE_WORDS = re.compile(r"\b(add|adds|added|support|feat|feature|new|introduce|implement|allow|expose|deprecat)", re.I)


def failures(work, py, tests, ids):
    junit = work / "junit-label.xml"
    sh([str(py), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
        "--continue-on-collection-errors", f"--junitxml={junit}", tests], cwd=work, timeout=2400)
    out = {}
    for tc in ET.parse(junit).getroot().iter("testcase"):
        nid = f"{tc.get('classname')}::{tc.get('name')}"
        if nid in ids:
            for c in tc:
                if c.tag in ("failure", "error"):
                    out[nid] = (c.get("message") or "") + "\n" + (c.text or "")[-1500:]
    return out


def adding_commit(repo, snap, head, name, tests):
    log = git(repo, "log", "--reverse", "--format=%h%x09%s", f"-S{name}", f"{snap}..{head}", "--", tests)
    return log.splitlines()[0].split("\t", 1) if log.strip() else ["", ""]


def label(name, screen, clones):
    scr = json.loads((screen / f"{name}.json").read_text())
    repo = clones / scr["repo"].replace("/", "_")
    work, py = screen / "work" / name, screen / "venvs" / name / "bin" / "python"
    for p in list(work.iterdir()):  # future tree with snapshot package code, as in blind.py's control run
        subprocess.run(["rm", "-rf", str(p)])
    archive_tree(repo, scr["head"], work)
    for p in scr["packages"]:
        subprocess.run(["rm", "-rf", str(work / p)])
        archive_tree(repo, scr["snapshot"], work, p)
    ids = set(scr["future_tests_failing_on_snapshot"])
    fails = failures(work, py, scr["tests"], ids)
    rows, commits = [], {}
    for t in sorted(ids):
        func = re.sub(r"\[.*", "", t.split("::")[-1])
        if func not in commits:
            commits[func] = adding_commit(repo, scr["snapshot"], scr["head"], func, scr["tests"])
        sha, subj = commits[func]
        msg = fails.get(t, "")
        first = next((l for l in msg.splitlines() if l.strip()), "")[:200]
        if MISSING_API.search(msg):
            lab, why = "feature", "API missing on snapshot"
        elif sha and BUG_WORDS.search(subj) and not re.match(r"(?i)\s*(add|feat|support)", subj):
            lab, why = "bug", "added in a fix commit"
        elif sha and FEATURE_WORDS.search(subj):
            lab, why = "feature", "added in a feature commit"
        elif "AssertionError" in msg or "assert " in msg or "DID NOT RAISE" in msg:
            lab, why = "bug", "wrong behaviour on snapshot"
        else:
            lab, why = "unclear", ""
        rows.append(dict(test=t, label=lab, why=why, commit=sha, subject=subj, failure=first))
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen", type=Path, required=True)
    ap.add_argument("--clones", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("repos", nargs="+")
    a = ap.parse_args()
    labels = json.loads(a.out.read_text()) if a.out.exists() else {}
    for name in a.repos:
        labels[name] = label(name, a.screen, a.clones)
        c = {k: sum(r["label"] == k for r in labels[name]) for k in ("bug", "feature", "unclear")}
        print(name, c, flush=True)
        a.out.write_text(json.dumps(labels, indent=1))
