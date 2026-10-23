#!/usr/bin/env python3
"""Ask a traced map what the test suite actually did, for an agent or a person.

usage:
  query.py MAP fn NAME          value summary for functions whose key contains NAME
  query.py MAP callers NAME     who calls it (needs a map traced with REPOMAP_EDGES=1)
  query.py MAP tests FILE:LINE  which tests run that line
  query.py MAP gaps [MODULE]    arguments never exercised with empty / zero / negative / None values

The gaps view is the one meant for hardening agents: an argument that takes strings but was never
given an empty one, or numbers but never zero or a negative, is untested territory.
"""
import json, sys

PROBES = {  # type seen -> flags worth having seen at least once
    "str": ("empty",), "bytes": ("empty",), "list": ("empty",), "tuple": ("empty",), "dict": ("empty",),
    "int": ("zero", "negative"), "float": ("zero", "negative"),
}


def fmt_summary(s):
    types = ", ".join(f"{t}×{n}" for t, n in sorted(s["types"].items(), key=lambda x: -x[1]))
    flags = ", ".join(f"{f}×{n}" for f, n in sorted(s["flags"].items()))
    return f"{types or 'never seen'}" + (f"  [{flags}]" if flags else "")


def gaps_of(s, optional=False):
    missing = []
    for t in s["types"]:
        for f in PROBES.get(t, ()):
            if not s["flags"].get(f) and f not in missing:
                missing.append(f)
    return missing


def main():
    m = json.load(open(sys.argv[1]))
    cmd, arg = sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "")
    F = m["functions"]
    if cmd == "fn":
        for k in sorted(x for x in F if arg in x):
            f = F[k]
            print(f"{k}  (line {f['first']}, {f['calls']} calls)")
            for a, s in f["args"].items():
                g = gaps_of(s)
                print(f"  {a}: {fmt_summary(s)}" + (f"  never: {', '.join(g)}" if g else ""))
            print(f"  -> {fmt_summary(f['returns'])}")
            if f["raises"]:
                print(f"  raises: {dict(f['raises'])}")
    elif cmd == "callers":
        for caller, callee in m.get("edges", []):
            if arg in callee:
                print(f"{caller} -> {callee}")
    elif cmd == "tests":
        for t, v in m["tests"].items():
            if arg in v["lines"]:
                print(t)
    elif cmd == "gaps":
        for k in sorted(F):
            if arg and arg not in k:
                continue
            out = [f"{a} never {'/'.join(g)}" for a, s in F[k]["args"].items() if (g := gaps_of(s))]
            if out:
                print(f"{k}: " + "; ".join(out))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
