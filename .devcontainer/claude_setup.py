#!/usr/bin/env python3
"""Runs every time the codespace starts. Lets Claude Code use the course key from the Codespaces
secret ANTHROPIC_API_KEY without asking to sign in, and skips the first-start questions.
The Claude panel starts in its built-in mode, Auto: deny rules, ask rules and hooks still apply."""
import json, os
from pathlib import Path

key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
cfg_file = Path.home() / ".claude.json"
try:
    cfg = json.loads(cfg_file.read_text())
except (OSError, json.JSONDecodeError):
    cfg = {}
cfg["hasCompletedOnboarding"] = True
if key:
    resp = cfg.setdefault("customApiKeyResponses", {"approved": [], "rejected": []})
    tail = key[-20:]
    resp.setdefault("approved", [])
    resp.setdefault("rejected", [])
    if tail not in resp["approved"]:
        resp["approved"].append(tail)
    if tail in resp["rejected"]:
        resp["rejected"].remove(tail)
proj = cfg.setdefault("projects", {}).setdefault(os.getcwd(), {})
proj["hasTrustDialogAccepted"] = True
cfg_file.write_text(json.dumps(cfg, indent=2))
user = Path.home() / ".claude" / "settings.json"
user.parent.mkdir(exist_ok=True)
try:
    us = json.loads(user.read_text())
except (OSError, json.JSONDecodeError):
    us = {}
us.get("permissions", {}).pop("defaultMode", None)   # an earlier version set Manual here
user.write_text(json.dumps(us, indent=2))
print("Claude Code: course key", "ready" if key else "NOT FOUND (check the Codespaces secret ANTHROPIC_API_KEY)")
