#!/usr/bin/env python3
"""Writes every step of the agent to .trace/agent_trace.md, so you can read afterwards
which folders it looked at and which commands it ran. Called by Claude Code (see settings.json):
SessionStart starts a new section, PostToolUse adds one line per tool call."""
import datetime, json, os, sys
from pathlib import Path

d = json.load(sys.stdin)
root = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
log = root / ".trace" / "agent_trace.md"
log.parent.mkdir(exist_ok=True)
now = datetime.datetime.now().strftime("%H:%M:%S")

if d.get("hook_event_name") == "SessionStart":   # the header is written by govern.py when a run starts
    sys.exit(0)

tool = d.get("tool_name", "?")
if tool.startswith("mcp__ccd_"):  # the app's own bookkeeping (plan, recap), not work on your files
    sys.exit(0)
i = d.get("tool_input", {}) or {}
what = {
    "Bash": lambda: "ran: " + i.get("command", ""),
    "Read": lambda: "read: " + i.get("file_path", ""),
    "Write": lambda: "wrote: " + i.get("file_path", ""),
    "Edit": lambda: "changed: " + i.get("file_path", ""),
    "Glob": lambda: "searched file names: " + i.get("pattern", ""),
    "Grep": lambda: "searched inside files for: " + i.get("pattern", ""),
    "Agent": lambda: "asked the helper " + i.get("subagent_type", "") + ": " + i.get("description", ""),
}.get(tool, lambda: json.dumps(i)[:200])()
# shorten the repository's own path, in Windows and in Unix spelling
for r in {str(root), root.as_posix(), str(root).replace("\\", "/")}:
    for q in ('"', "'", ""):
        what = what.replace(f"cd {q}{r}{q} && ", "").replace(f"cd {q}{r}{q}; ", "")
    what = what.replace(r + "/", "").replace(r + "\\", "")
what = what.replace("\n", " ⏎ ").replace("|", "\\|")
if len(what) > 300:
    what = what[:300] + " …"
with open(log, "a", encoding="utf-8") as f:
    f.write(f"| {now} | {tool} | `{what}` |\n")
