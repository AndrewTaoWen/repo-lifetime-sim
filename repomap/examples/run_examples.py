#!/usr/bin/env python3
"""Small, readable demonstrations of repomap's change impact on the toy repo in shopkit/.

usage: run_examples.py --python PY [--work DIR] [--out DIR]
  PY is an interpreter with pytest installed (Python 3.12+).

For each example it makes one edit, asks `repomap.py impact` what the edit affects (without running
anything), then runs the whole suite to see which tests really break, and puts the edit back.
Writes examples.json, impact-*.txt (the CLI output for each edit) and shopkit-map.html (the `serve`
page with every example built in).
"""
import argparse, json, os, shutil, subprocess, sys, tempfile, xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOMAP = HERE.parent / "repomap.py"
sys.path.insert(0, str(HERE.parent))
import repomap as rm  # noqa: E402

EXAMPLES = [
    dict(slug="format", title="Print prices differently",
         blurb="A leaf function with one caller. Only the code that prints a price is affected.",
         file="src/shopkit/money.py", old='{"USD": "$",', new='{"USD": "US$",'),
    dict(slug="bulk", title="Move the bulk-discount threshold",
         blurb="Some tests run the changed function without depending on the detail that changed. "
               "They are selected but still pass.",
         file="src/shopkit/discounts.py", old="item_count >= 10", new="item_count > 10"),
    dict(slug="rounding", title="Change how cents are rounded",
         blurb="A shared helper. The change ripples up through tax and checkout to the receipt.",
         file="src/shopkit/money.py", old="rounding=ROUND_HALF_UP", new='rounding="ROUND_DOWN"'),
    dict(slug="taxrate", title="Raise California's tax rate",
         blurb="A data change outside any function. Every test that runs code in tax.py is selected.",
         file="src/shopkit/tax.py", old='"CA": 0.0725', new='"CA": 0.08'),
    dict(slug="setup", title="Normalise product codes on add",
         blurb="TestCart builds its catalog once in setup_class, before its tests run. All three "
               "tests depend on Catalog.add even though none of them calls it.",
         file="src/shopkit/catalog.py", old="self._prices[sku] = price", new="self._prices[sku.upper()] = price"),
    dict(slug="untested", title="Edit the CSV export",
         blurb="No test runs this function, so the memory can't say what depends on it. "
               "repomap says so instead of reporting zero impact.",
         file="src/shopkit/export.py", old='rows = ["sku,qty,price"]', new='rows = ["sku,quantity,price"]'),
]


def run(*a, **kw):
    return subprocess.run(a, capture_output=True, text=True, **kw)


def failing(py, junit):
    run(py, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}", "tests",
        env={**os.environ, "PYTHONPATH": "src"})
    out = set()
    for tc in ET.parse(junit).getroot().iter("testcase"):
        if any(c.tag in ("failure", "error") for c in tc):
            cls = tc.get("classname").split(".")
            mod = [p for p in cls if p.startswith("test_")][0]
            rest = cls[cls.index(mod) + 1:]
            out.add("::".join([f"tests/{mod}.py", *rest, tc.get("name")]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", required=True)
    ap.add_argument("--work", default=None)
    ap.add_argument("--out", default=str(HERE))
    a = ap.parse_args()
    out = Path(a.out).resolve()
    work = Path(a.work or tempfile.mkdtemp()) / "shopkit"
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(HERE / "shopkit", work, ignore=shutil.ignore_patterns("__pycache__", ".repomap"))
    os.chdir(work)
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "-c", "user.name=demo", "-c", "user.email=demo@localhost", "commit", "-qm", "shopkit"]):
        run(*cmd)
    print(run(sys.executable, REPOMAP, "record", "--package", "src/shopkit", "--python", a.python).stdout.strip())
    m = rm.load()
    results = []
    for ex in EXAMPLES:
        path = Path(ex["file"])
        src = path.read_text()
        assert ex["old"] in src, ex["slug"]
        new = src.replace(ex["old"], ex["new"])
        for o, n in ex.get("also", ()):
            new = new.replace(o, n)
        try:
            path.write_text(new)
            diff = run("git", "diff", "--", ex["file"]).stdout
            text = run(sys.executable, REPOMAP, "impact").stdout.replace(a.python, "python")
            res = rm.compute_impact(m)
            with tempfile.TemporaryDirectory() as td:
                broke = failing(a.python, f"{td}/j.xml")
        finally:
            path.write_text(src)
        selected = set(res["tests"])
        r = dict(slug=ex["slug"], title=ex["title"], blurb=ex["blurb"], file=ex["file"], diff=diff,
                 changed=res["changed"], callers=res["callers"], untested=res["untested"],
                 selected=sorted(selected), broke=sorted(broke), missed=sorted(broke - selected),
                 suite=len(m["tests_map"]))
        results.append(r)
        (out / f"impact-{ex['slug']}.txt").write_text(f"$ git diff\n{diff}\n$ repomap.py impact\n{text}")
        print(f"{ex['slug']:9s} selected {len(selected):2d}/{r['suite']}  broke {len(broke):2d}  missed {len(r['missed'])}")
    (out / "examples.json").write_text(json.dumps(results, indent=1))
    page = rm.page_with(rm.ui_data(m), None).replace(
        '<script id="examples" type="application/json"></script>',
        f'<script id="examples" type="application/json">{json.dumps(results).replace("</", "<" + chr(92) + "/")}</script>')
    (out / "shopkit-map.html").write_text(page)
    print(f"wrote {out}/examples.json and shopkit-map.html")


if __name__ == "__main__":
    main()
