#!/usr/bin/env python3
"""Course switchboard.

  python govern.py piece 2    choose your piece (1, 2 or 3): writes TASK.md and prepares work/
  python govern.py            show your piece and your switches
  python govern.py apply      turn the switches in governance.yaml into real Claude Code files
  python govern.py log "..."  save this run (switches, output, trace, cost) to runs/, then reset
  python govern.py reset      clear work/, out/ and outbox/ for a new run
  python govern.py pack       put all your runs in one zip file to hand in

Edit governance.yaml (on / off), run apply, start Claude Code, paste: Do the task in TASK.md."""
import base64, datetime, json, os, re, shutil, sys, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
G = ROOT / ".govern"
SWITCHES = ["context", "spec", "check", "hard_rules", "human_gate", "reviewer", "budget"]


def pack():
    return json.loads(zlib.decompress(base64.b64decode((G / "pack.b64").read_text())))


def piece():
    f = G / "piece"
    if not f.exists():
        sys.exit("Choose your piece first: python govern.py piece 1   (or 2, or 3)")
    return f.read_text().strip()


def choose(n):
    if n not in ("1", "2", "3"):
        sys.exit("The piece must be 1, 2 or 3.")
    (G / "piece").write_text(n)
    (ROOT / "TASK.md").write_text(pack()[f"tasks/piece{n}.md"], encoding="utf-8")
    reset()
    apply()
    print(f"You build piece {n}. Read TASK.md, then start your first run with all switches off.")


def read_switches():
    sw = {k: False for k in SWITCHES}
    for line in (ROOT / "governance.yaml").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([a-z_]+)\s*:\s*(on|off|true|false|yes|no)\b", line, re.I)
        if m and m.group(1) in sw:
            sw[m.group(1)] = m.group(2).lower() in ("on", "true", "yes")
    return sw


def apply():
    P, n, sw = pack(), piece(), read_switches()
    claude = P["claude_base.md"]
    if sw["context"]:
        claude += P["context.md"]
    spec_dir = ROOT / "specs"
    shutil.rmtree(spec_dir, ignore_errors=True)
    if sw["spec"]:
        spec_dir.mkdir()
        (spec_dir / "SPEC.md").write_text(P[f"specs/piece{n}.md"], encoding="utf-8")
        claude += P["spec_line.md"]
    if sw["reviewer"]:
        claude += P["reviewer_line.md"]
    (ROOT / "CLAUDE.md").write_text(claude, encoding="utf-8")

    cdir = ROOT / ".claude"
    for sub in ["hooks", "agents"]:
        shutil.rmtree(cdir / sub, ignore_errors=True)
    (cdir / "hooks").mkdir(parents=True)
    settings = {
        "permissions": {
            "allow": ["Bash(python:*)", "Bash(python3:*)", "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(wc:*)"],
            "deny": ["Read(./.govern/**)", "Read(./runs/**)", "Read(./govern.py)", "Edit(./data/**)", "Write(./data/**)", "WebFetch", "WebSearch"],
            "ask": [],
        },
        "hooks": {},
    }
    pre = []
    # always on (course machinery, not a switch): every step of the agent goes to .trace/agent_trace.md
    py = '"$(command -v python || command -v python3)" '
    (cdir / "hooks" / "trace.py").write_text(P["hooks/trace.py"], encoding="utf-8")
    trace = {"hooks": [{"type": "command", "command": py + '"$CLAUDE_PROJECT_DIR/.claude/hooks/trace.py"'}]}
    settings["hooks"]["SessionStart"] = [trace]
    settings["hooks"]["PostToolUse"] = [trace]
    if sw["hard_rules"]:
        settings["permissions"]["deny"] += ["Bash(rm:*)", "Bash(curl:*)", "Bash(wget:*)", "Bash(mail:*)"]
        (cdir / "hooks" / "guard_send.py").write_text(P["hooks/guard_send.py"], encoding="utf-8")
        pre.append({"matcher": "Bash", "hooks": [{"type": "command", "command": '"$(command -v python || command -v python3)" "$CLAUDE_PROJECT_DIR/.claude/hooks/guard_send.py"'}]})
    if sw["budget"]:
        (cdir / "hooks" / "budget.py").write_text(P["hooks/budget.py"], encoding="utf-8")
        pre.append({"hooks": [{"type": "command", "command": '"$(command -v python || command -v python3)" "$CLAUDE_PROJECT_DIR/.claude/hooks/budget.py"'}]})
    if pre:
        settings["hooks"]["PreToolUse"] = pre
    shutil.rmtree(ROOT / "checks", ignore_errors=True)
    if sw["check"]:
        (ROOT / "checks").mkdir()
        (ROOT / "checks" / "check.py").write_text(P["checks/check.py"], encoding="utf-8")
        (cdir / "hooks" / "stop_check.py").write_text(P["hooks/stop_check.py"], encoding="utf-8")
        settings["hooks"]["Stop"] = [{"hooks": [{"type": "command", "command": '"$(command -v python || command -v python3)" "$CLAUDE_PROJECT_DIR/.claude/hooks/stop_check.py"', "timeout": 60}]}]
    if sw["human_gate"]:
        settings["permissions"]["ask"] += ["Bash(python tools/send.py:*)", "Bash(python3 tools/send.py:*)"]
    if sw["reviewer"]:
        (cdir / "agents").mkdir()
        (cdir / "agents" / "piece-reviewer.md").write_text(P["reviewer.md"], encoding="utf-8")
    (cdir / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    on = [k for k in SWITCHES if sw[k]]
    print(f"Piece {n}. Switches on: {', '.join(on) if on else 'none'}. Applied.")


def reset():
    n = piece()
    for d in ["out", "outbox"]:
        shutil.rmtree(ROOT / d, ignore_errors=True)
        (ROOT / d).mkdir()
    shutil.rmtree(ROOT / "work", ignore_errors=True)
    (ROOT / "work").mkdir()
    for key, text in pack().items():
        if key.startswith(f"fixtures/piece{n}/"):
            (ROOT / "work" / key.split("/")[-1]).write_text(text, encoding="utf-8")
    shutil.rmtree(ROOT / ".claude" / "state", ignore_errors=True)
    shutil.rmtree(ROOT / ".trace", ignore_errors=True)
    print(f"Piece {n}: work/, out/ and outbox/ are ready for a new run.")


def same_folder(a, b):
    norm = lambda x: os.path.normcase(os.path.normpath(str(x)))
    return norm(a) == norm(b)


def last_session():
    """Newest Claude Code transcript of a task run in this repository: a session started in this
    folder whose prompt asked for the task. Sessions that only ran govern.py are skipped."""
    best = None
    for p in (Path.home() / ".claude" / "projects").glob("*/*.jsonl"):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "TASK.md" not in text or "Do the task" not in text:
            continue
        cwd = None
        for line in text.splitlines()[:50]:
            try:
                cwd = json.loads(line).get("cwd")
            except (json.JSONDecodeError, AttributeError):
                continue
            if cwd:
                break
        if cwd and same_folder(cwd, ROOT):
            if best is None or p.stat().st_mtime > best.stat().st_mtime:
                best = p
    if not best:
        return {}
    tools, tin, tout, ts = 0, 0, 0, []
    for line in open(best, encoding="utf-8"):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("timestamp"):
            ts.append(d["timestamp"])
        if d.get("type") == "assistant":
            u = d["message"].get("usage", {})
            tin += u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            tout += u.get("output_tokens", 0)
            tools += sum(1 for c in d["message"].get("content", []) if isinstance(c, dict) and c.get("type") == "tool_use")
    mins = None
    if len(ts) > 1:
        f = lambda s: datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        mins = round((f(ts[-1]) - f(ts[0])).total_seconds() / 60, 1)
    return {"transcript": str(best), "tool_calls": tools, "tokens_in": tin, "tokens_out": tout, "minutes": mins}


def log(note):
    runs = ROOT / "runs"; runs.mkdir(exist_ok=True)
    k = len([p for p in runs.iterdir() if p.is_dir()]) + 1
    dst = runs / f"run_{k:02d}"
    dst.mkdir()
    for d in ["work", "out", "outbox"]:
        if (ROOT / d).exists():
            shutil.copytree(ROOT / d, dst / d)
    if (ROOT / ".trace").exists():
        shutil.copytree(ROOT / ".trace", dst / "trace")
    meta = {"piece": piece(), "switches": read_switches(), "note": note, "time": datetime.datetime.now().isoformat(timespec="seconds")}
    meta.update(last_session())
    m = re.search(r"\$\s?(\d+(?:[.,]\d+)?)", note)
    if m:
        meta["cost_usd"] = float(m.group(1).replace(",", "."))
    (dst / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Saved as runs/run_{k:02d}. Tool calls: {meta.get('tool_calls')}, minutes: {meta.get('minutes')}, cost: {meta.get('cost_usd', 'not in your note')}.")
    reset()


def pack_runs():
    import zipfile
    runs = ROOT / "runs"
    if not runs.exists():
        sys.exit("No runs saved yet.")
    name = ROOT / f"runs_piece{piece()}_{datetime.datetime.now():%Y%m%d-%H%M}.zip"
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
        for f in runs.rglob("*"):
            z.write(f, f.relative_to(ROOT))
    print(f"Created {name.name}. Download it (right-click in the file list, Download) and hand it in.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "piece":
        choose(sys.argv[2] if len(sys.argv) > 2 else "")
    elif cmd == "pack":
        pack_runs()
    elif cmd == "apply":
        apply()
    elif cmd == "reset":
        reset()
    elif cmd == "log":
        log(" ".join(sys.argv[2:]))
    else:
        sw = read_switches()
        print(f"Piece {piece()}")
        for k in SWITCHES:
            print(f"  {k:<11} {'on' if sw[k] else 'off'}")
