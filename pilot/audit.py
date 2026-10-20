#!/usr/bin/env python3
"""Audit blind-hardening agent transcripts for leakage.

usage: audit.py TRANSCRIPT_DIR [--root BLIND_ROOT]

For every subagent transcript whose prompt names a blind workspace (<root>/<repo>-r<k>), lists each
tool call that reaches outside that workspace or can reach the network:
  web       WebFetch / WebSearch tool calls
  network   pip/uv installs, curl, wget, git clone/fetch/pull, urllib/requests/http in inline code
  outside   Read/Grep/Glob/Edit/Write paths, or absolute paths in shell commands, outside the workspace
  sensitive any reference to future-data locations (clones, screen output, shared project folder,
            results repo, other runs' workspaces, session transcripts)
Writes a JSON report to stdout: {run: {agent, calls, flags: [[kind, detail]]}}.
"""
import argparse, json, re
from pathlib import Path

NET = re.compile(r"\b(pip3?\s+(install|download)|uv\s+(pip\s+install|add|sync|run\s+--with)|curl|wget|"
                 r"git\s+(clone|fetch|pull|ls-remote|submodule)|urllib|requests\.|http\.client|socket\.|"
                 r"pypi\.org|github\.com|files\.pythonhosted)")
SENSITIVE = re.compile(r"((?:scr-out|/screen/|screen\b.*_|project-files|repo-lifetime-sim|\.claude/projects|"
                       r"labels.*\.json|scores\.json|/blind\b|blind2?/(?!{run})))")
SAFE_PREFIX = ("/usr/", "/bin/", "/lib", "/etc/", "/dev/null", "/proc/", "/opt/node", "/root/.cache/uv",
               "/root/.local/share/uv", "/tmp/pytest", "/sys/")
ABS_PATH = re.compile(r"(?<![\w.~:/-])(/(?:tmp|root|home|mnt|srv|var|workspace|opt)(?:/[\w.@+-]+)*/?)")


def calls(path):
    for line in path.open():
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if m.get("type") != "assistant":
            continue
        for c in m.get("message", {}).get("content", []):
            if isinstance(c, dict) and c.get("type") == "tool_use":
                yield c["name"], c.get("input", {})


def prompt(path):
    for line in path.open():
        m = json.loads(line)
        if m.get("type") == "user":
            c = m["message"]["content"]
            return c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return ""


def audit(path, root):
    m = re.search(re.escape(str(root)) + r"/([\w.-]+-r\d+)", prompt(path))
    if not m:
        return None
    run = m.group(1)
    ws = f"{root}/{run}"
    sens = re.compile(SENSITIVE.pattern.replace("{run}", re.escape(run)))
    flags, n = [], 0
    for name, inp in calls(path):
        n += 1
        if name in ("WebFetch", "WebSearch"):
            flags.append(["web", json.dumps(inp)[:200]])
            continue
        text = inp.get("command") or inp.get("file_path") or inp.get("path") or inp.get("pattern") or ""
        if name == "Bash" and NET.search(text):
            flags.append(["network", text[:300]])
        if sens.search(text) and "/tool-results/" not in text:
            flags.append(["sensitive", f"{name}: {text[:300]}"])
        paths = [inp[k] for k in ("file_path", "path", "notebook_path") if isinstance(inp.get(k), str)]
        if name == "Bash":
            paths += ABS_PATH.findall(text)
        for p in paths:
            if p.startswith("/") and not p.startswith(ws) and not p.startswith(SAFE_PREFIX) and p != "/":
                own_spill = "/tool-results/" in p  # the agent's own long tool output, saved by the harness
                flags.append(["own-output" if own_spill else "outside", f"{name}: {p}"])
    return run, dict(agent=path.stem, calls=n, flags=flags)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("transcripts", type=Path)
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    report = {}
    for p in sorted(a.transcripts.glob("agent-*.jsonl")):
        r = audit(p, a.root)
        if r:
            run, d = r
            if run in report:  # a run resumed in a second transcript
                report[run]["calls"] += d["calls"]; report[run]["flags"] += d["flags"]
                report[run]["agent"] += "," + d["agent"]
            else:
                report[run] = d
    print(json.dumps(report, indent=1))
