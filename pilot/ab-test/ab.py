"""Bug-only recall per run for the prompt A/B test.

usage: ab.py DIR OUT.json [SCORES.json]   (DIR holds labels-heldout.json)
"""
import json, re, sys, collections
S = sys.argv[1]
lab = json.load(open(f"{S}/labels-heldout.json"))
ov = json.load(open(__import__("os").path.join(__import__("os").path.dirname(__file__), "..", "scale-up", "label-overrides.json")))
sc = json.load(open(sys.argv[3] if len(sys.argv) > 3 else "/srv/blind4/scores.json"))
def final(repo, r):
    o = ov.get(repo, {})
    func = re.sub(r"\[.*", "", r["test"].split("::")[-1])
    if not r["commit"] and "test:" + func in o: return o["test:" + func]
    if not r["commit"] and "test:*" in o: return o["test:*"]
    for k, v in o.items():
        if r["commit"] and not k.startswith(("test:", "*", "_")) and r["commit"].startswith(k): return v
    return o.get("*", r["label"])
# adding commits found by hand (git log -S on the parameter text) for tests label.py couldn't place
FOUND = {"python-dotenv": [("#", "f5485a6"), ("\\\\", "f7b18d9")],
         "werkzeug": [("test_get_host_invalid", "658bf5ed"), ("test_plain_int", "b9761b5b"),
                      ("test_if_range_parsing", "5b0dc6d6"), ("test_range_parsing", "0c419f95"),
                      ("test_csp_header", "63a800ca")]}
def commit(repo, r):
    if r["commit"]: return r["commit"]
    for pat, c in FOUND.get(repo, []):
        if pat in r["test"]: return c
    return r["test"]
out = {}
for repo in ["python-dotenv", "cattrs", "werkzeug", "pydantic-settings"]:
    rows = {r["test"]: dict(r, final=final(repo, r)) for r in lab[repo]}
    bugs = {t for t, r in rows.items() if r["final"] == "bug"}
    bugc = {commit(repo, rows[t]) for t in bugs}
    c = collections.Counter(r["final"] for r in rows.values())
    print(f"\n{repo}: {dict(c)}; bug tests {len(bugs)}, distinct bug commits {len(bugc)}")
    for k in range(1, 5):
        run = f"{repo}-r{k}"; s = sc[run]
        ft = {t.split("::", 1)[0].split("/")[-1] + "::" + t.split("::", 1)[1] if False else t for t in s["fixed_tests"]}
        fb = [t for t in s["fixed_tests"] if t in bugs]
        miss = [t for t in s["fixed_tests"] if t not in rows]
        fc = {commit(repo, rows[t]) for t in fb}
        nonbug = [ (t, rows[t]["final"]) for t in s["fixed_tests"] if t in rows and t not in bugs]
        arm = "base" if k <= 2 else "impr"
        print(f"  r{k} {arm}: all {s['fixed']}/{s['target']}, bug tests {len(fb)}/{len(bugs)}, bug commits {len(fc)}/{len(bugc)}, regr {s['regressions']}, nonbug {nonbug}, unlabeled {len(miss)}")
        out[run] = dict(arm=arm, fixed=s["fixed"], target=s["target"], bug_tests=len(fb), n_bug_tests=len(bugs), bug_commits=sorted(fc), n_bug_commits=len(bugc), regressions=s["regressions"])
old = json.load(open(sys.argv[2])) if len(sys.argv) > 2 and __import__("os").path.exists(sys.argv[2]) else {}
for k in out: out[k]["verified_new_tests"] = old.get(k, {}).get("verified_new_tests")
json.dump(out, open(sys.argv[2], "w"), indent=1)
