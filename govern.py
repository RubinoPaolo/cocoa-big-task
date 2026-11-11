#!/usr/bin/env python3
"""Course machinery for the big task. Students never run this file: Claude Code runs it through
the hooks in .claude/settings.json.

  Every new session  (SessionStart)  reads governance.yaml, prepares TASK.md and work/, turns the switches on
  Every tool call    (PreToolUse)    applies the switches that act on tools: hard_rules, human_gate, budget
  Every stop         (Stop)          runs the check if it is on, then saves this run to runs/ (and to the class board)

Course team only:
  python govern.py            show the piece and the switches
  python govern.py pack       put all saved runs in one zip file (fallback if the class board is not reachable)"""
import base64, datetime, json, os, re, shutil, subprocess, sys, urllib.request, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
G = ROOT / ".govern"
STATE = ROOT / ".claude" / "state"
SWITCHES = ["context", "spec", "check", "hard_rules", "human_gate", "reviewer", "budget"]
BUDGET = 25
CHECK_MAX = 3
# US dollars per million tokens: input, output, cache read, cache write 5 min, cache write 1 h
PRICES = {"opus": (4, 20, 0.2, 5, 8), "sonnet": (2, 10, 0.1, 2.5, 4), "haiku": (1, 5, 0.05, 1.25, 2)}


# ───────────── reading the switches
def pack():
    return json.loads(zlib.decompress(base64.b64decode((G / "pack.b64").read_text())))


def read_yaml():
    piece, sw = None, {k: False for k in SWITCHES}
    for line in (ROOT / "governance.yaml").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*piece\s*:\s*([123])\b", line)
        if m:
            piece = m.group(1)
        m = re.match(r"^\s*([a-z_]+)\s*:\s*(on|off|true|false|yes|no)\b", line, re.I)
        if m and m.group(1) in sw:
            sw[m.group(1)] = m.group(2).lower() in ("on", "true", "yes")
    return piece, sw


def current():
    try:
        return json.loads((G / "current.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def out(obj):
    print(json.dumps(obj))
    sys.exit(0)


# ───────────── SessionStart: a new run
def prepare(piece, sw, P):
    for d in ["out", "outbox", "work"]:
        shutil.rmtree(ROOT / d, ignore_errors=True)
        (ROOT / d).mkdir()
    for key, text in P.items():
        if key.startswith(f"fixtures/piece{piece}/"):
            (ROOT / "work" / key.split("/")[-1]).write_text(text, encoding="utf-8")
    (ROOT / "TASK.md").write_text(P[f"tasks/piece{piece}.md"], encoding="utf-8")
    shutil.rmtree(ROOT / "specs", ignore_errors=True)
    if sw["spec"]:
        (ROOT / "specs").mkdir()
        (ROOT / "specs" / "SPEC.md").write_text(P[f"specs/piece{piece}.md"], encoding="utf-8")
    shutil.rmtree(ROOT / "checks", ignore_errors=True)
    if sw["check"]:
        (ROOT / "checks").mkdir()
        (ROOT / "checks" / "check.py").write_text(P["checks/check.py"], encoding="utf-8")
    agent = ROOT / ".claude" / "agents" / "piece-reviewer.md"
    agent.unlink(missing_ok=True)
    if sw["reviewer"]:
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_text(P["reviewer.md"], encoding="utf-8")
    shutil.rmtree(STATE, ignore_errors=True)
    (ROOT / ".trace").mkdir(exist_ok=True)
    (ROOT / ".trace" / "agent_trace.md").write_text(
        f"## Run started {datetime.datetime.now():%Y-%m-%d %H:%M}\n\n| Time | Step | What exactly |\n|---|---|---|\n", encoding="utf-8")


def on_session(d):
    source = d.get("source", "startup")
    cur = current()
    if source in ("resume", "compact") and cur.get("session_id") == d.get("session_id"):
        piece, sw = cur.get("piece"), cur.get("switches", {})   # same run continues: keep everything
    else:
        final = finalize(cur)
        piece, sw = read_yaml()
        if not piece:
            (ROOT / "TASK.md").write_text("# Choose your piece first\n\nOpen `governance.yaml`, set `piece:` to 1, 2 or 3, save, then start a new session.\n", encoding="utf-8")
            out({"systemMessage": "No piece chosen yet. Open governance.yaml, set piece: 1, 2 or 3, save, then start a new session.",
                 "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "The student has not chosen a piece yet. If asked to do the task, say that they must set piece: 1, 2 or 3 in governance.yaml, save, and start a new session. Do nothing else."}})
        prepare(piece, sw, pack())
        G.mkdir(exist_ok=True)
        (G / "current.json").write_text(json.dumps({"session_id": d.get("session_id"), "piece": piece, "switches": sw,
                                                     "started": datetime.datetime.now().isoformat(timespec="seconds"),
                                                     "transcript": d.get("transcript_path")}, indent=2))
    P = pack()
    ctx = ""
    if sw.get("context"):
        ctx += P["context.md"]
    if sw.get("spec"):
        ctx += P["spec_line.md"]
    if sw.get("reviewer"):
        ctx += P["reviewer_line.md"]
    on = [k for k in SWITCHES if sw.get(k)]
    msg = f"Big task · piece {piece} · switches on: {', '.join(on) if on else 'none'}. New run ready: ask Claude to do the task in TASK.md."
    if source not in ("resume", "compact") and final:
        msg = final + " " + msg
    res = {"systemMessage": msg}
    if ctx:
        res["hookSpecificOutput"] = {"hookEventName": "SessionStart", "additionalContext": ctx}
    out(res)


# ───────────── PreToolUse: the switches that act on tools
def contract_prices():
    known = set()
    for c in (ROOT / "data" / "contracts").glob("*.md"):
        for p in re.finditer(r"CHF\s?([\d,'’]+)\s?/\s?t", c.read_text(encoding="utf-8")):
            digits = re.sub(r"\D", "", p.group(1))
            if len(digits) >= 4:
                known.add(digits)
    return known


def guard_send(cmd, cwd):
    """hard_rules: no recipient outside @alpstein-choc.ch, no contract price in what is sent."""
    known = contract_prices()

    def prices_in(text):
        found = [p.group(0) for p in re.finditer(r"CHF\s?[\d'’,.]{3,}\s?(/\s?t\b|per\s+t)", text, re.I)]
        found += [n.group(0) for n in re.finditer(r"\d[\d,'’]{2,}\d", text) if re.sub(r"\D", "", n.group(0)) in known]
        return found

    problems = []
    send_part = cmd[cmd.rfind("send.py"):]
    for grp in re.findall(r"--to[=\s]+[\"']?([^\"'\s]+)", send_part):
        for a in grp.split(","):
            a = a.strip()
            if a and not a.lower().endswith("@alpstein-choc.ch"):
                problems.append(f"recipient outside the company: {a}")
    texts = {"the command": cmd}
    bases = [ROOT, Path(cwd or ROOT)]
    m = re.search(r"\bcd\s+([^\s;&|]+)", cmd)
    if m:
        bases.append(Path(m.group(1).strip("'\"")))
    for f in re.findall(r"(\S+\.md)\b", send_part):
        f = f.strip("'\"")
        for b in bases:
            p = Path(f) if Path(f).is_absolute() else b / f
            if p.exists():
                texts[f] = p.read_text(encoding="utf-8")
                break
    for where, text in texts.items():
        for hit in sorted(set(prices_in(text))):
            problems.append(f"{where} contains a contract price: '{hit}'")
    return problems


def decide(decision, reason):
    out({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": reason}})


def on_pre(d):
    sw = current().get("switches", {})
    tool, inp = d.get("tool_name", ""), d.get("tool_input", {}) or {}
    cmd = inp.get("command", "") if tool == "Bash" else ""
    if sw.get("budget"):
        STATE.mkdir(parents=True, exist_ok=True)
        c = STATE / f"budget_{d.get('session_id', 'x')}.txt"
        n = int(c.read_text()) + 1 if c.exists() else 1
        c.write_text(str(n))
        if n > BUDGET:
            decide("deny", f"Budget reached: {BUDGET} tool calls. Stop working. Write down what you have done and what is missing.")
    if sw.get("hard_rules") and cmd:
        if re.search(r"(^|[;&|]\s*)(rm|curl|wget|mail|sendmail)\b", cmd):
            decide("deny", "Blocked by a hard rule: this command is not allowed in this repository.")
        if "send.py" in cmd:
            problems = guard_send(cmd, d.get("cwd"))
            if problems:
                decide("deny", "Blocked by a hard rule: " + "; ".join(problems))
    if sw.get("human_gate") and "send.py" in cmd:
        decide("ask", "Human approval is on. Open out/briefing.md and read it before you say yes.")
    sys.exit(0)


# ───────────── Stop: the check, then save the run
def cost_of(transcript):
    """Same figure as /cost: from the session's own record, or from its token counts."""
    total, seen, tools, ts = None, set(), 0, []
    usage = 0.0
    try:
        lines = open(transcript, encoding="utf-8").read().splitlines()
    except (OSError, TypeError):
        return None, None, None
    for line in lines:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("timestamp"):
            ts.append(d["timestamp"])
        if d.get("type") == "cost-state":
            total = d.get("totalCostUSD")
        if d.get("type") != "assistant":
            continue
        msg = d.get("message", {})
        tools += sum(1 for c in msg.get("content", []) if isinstance(c, dict) and c.get("type") == "tool_use")
        key = (msg.get("id"), d.get("requestId"))
        if key in seen:
            continue
        seen.add(key)
        u = msg.get("usage", {}) or {}
        model = msg.get("model", "")
        p = next((v for k, v in PRICES.items() if k in model), PRICES["opus"])
        cc = u.get("cache_creation", {}) or {}
        w5 = cc.get("ephemeral_5m_input_tokens", 0) or 0
        w1 = cc.get("ephemeral_1h_input_tokens", 0) or 0
        if not (w5 or w1):
            w5 = u.get("cache_creation_input_tokens", 0) or 0
        usage += (u.get("input_tokens", 0) * p[0] + u.get("output_tokens", 0) * p[1] + u.get("cache_read_input_tokens", 0) * p[2]
                  + w5 * p[3] + w1 * p[4]) / 1e6
    sub = Path(str(transcript)[:-6]) / "subagents" if str(transcript).endswith(".jsonl") else None
    for f in (sorted(sub.glob("*.jsonl")) if sub and sub.exists() else []):   # helpers (reviewer) cost too
        for line in open(f, encoding="utf-8"):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = d.get("message", {}) if d.get("type") == "assistant" else None
            if not msg or (msg.get("id"), d.get("requestId")) in seen:
                continue
            seen.add((msg.get("id"), d.get("requestId")))
            u = msg.get("usage", {}) or {}
            p = next((v for k, v in PRICES.items() if k in msg.get("model", "")), PRICES["opus"])
            cc = u.get("cache_creation", {}) or {}
            w5, w1 = cc.get("ephemeral_5m_input_tokens", 0) or 0, cc.get("ephemeral_1h_input_tokens", 0) or 0
            if not (w5 or w1):
                w5 = u.get("cache_creation_input_tokens", 0) or 0
            usage += (u.get("input_tokens", 0) * p[0] + u.get("output_tokens", 0) * p[1] + u.get("cache_read_input_tokens", 0) * p[2]
                      + w5 * p[3] + w1 * p[4]) / 1e6
    mins = None
    if len(ts) > 1:
        f = lambda s: datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        mins = round((f(ts[-1]) - f(ts[0])).total_seconds() / 60, 1)
    return round(total if total is not None else usage, 2), tools, mins


def save_run(d):
    cur = current()
    if not cur.get("piece"):
        return None
    runs = ROOT / "runs"; runs.mkdir(exist_ok=True)
    index_f = G / "runs.json"
    index = json.loads(index_f.read_text()) if index_f.exists() else {}
    sid = d.get("session_id") or cur.get("session_id")
    if sid not in index:
        index[sid] = f"run_{len(index) + 1:02d}"
        index_f.write_text(json.dumps(index, indent=2))
    dst = runs / index[sid]
    shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir()
    for name in ["work", "out", "outbox"]:
        if (ROOT / name).exists():
            shutil.copytree(ROOT / name, dst / name)
    if (ROOT / ".trace").exists():
        shutil.copytree(ROOT / ".trace", dst / "trace")
    cost, tools, mins = cost_of(d.get("transcript_path") or cur.get("transcript"))
    meta = {"run": index[sid], "piece": cur["piece"], "switches": cur["switches"], "started": cur.get("started"),
            "saved": datetime.datetime.now().isoformat(timespec="seconds"), "cost_usd": cost, "tool_calls": tools, "minutes": mins,
            "who": os.environ.get("GITHUB_USER") or os.environ.get("USER", "")}
    (dst / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    send_to_board(meta, dst)
    return meta


def send_to_board(meta, dst):
    """If the course team has set a class-board address in .govern/board_url, send the run there too."""
    url_f = G / "board_url"
    if not url_f.exists() or not url_f.read_text().strip():
        return
    files = {}
    for f in dst.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".md", ".eml", ".txt") and f.stat().st_size < 200_000:
            files[str(f.relative_to(dst))] = f.read_text(encoding="utf-8", errors="replace")
    body = json.dumps({**meta, "repo": os.environ.get("GITHUB_REPOSITORY", ""), "files": files}).encode()
    try:
        req = urllib.request.Request(url_f.read_text().strip(), data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass   # the run is saved in runs/ anyway


def finalize(cur):
    """The previous run's transcript is complete now: store its final cost (the same figure as /cost)."""
    try:
        index = json.loads((G / "runs.json").read_text())
        run = ROOT / "runs" / index[cur["session_id"]] / "run.json"
        meta = json.loads(run.read_text())
    except (OSError, KeyError, json.JSONDecodeError, TypeError):
        return ""
    cost, tools, mins = cost_of(cur.get("transcript"))
    if cost is None:
        return ""
    meta.update({"cost_usd": cost, "tool_calls": tools, "minutes": mins, "final": True})
    run.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    send_to_board(meta, run.parent)
    return f"Your previous run ({meta['run']}) cost ${cost:.2f} in total."


def on_stop(d):
    cur = current()
    sw = cur.get("switches", {})
    if sw.get("check") and (ROOT / "checks" / "check.py").exists():
        r = subprocess.run([sys.executable, "checks/check.py"], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            STATE.mkdir(parents=True, exist_ok=True)
            c = STATE / f"check_blocks_{d.get('session_id', 'x')}.txt"
            n = int(c.read_text()) + 1 if c.exists() else 1
            c.write_text(str(n))
            if n <= CHECK_MAX:
                out({"decision": "block", "reason": "The check for your piece fails. Fix this before you finish:\n" + r.stdout[-2000:]})
    meta = save_run(d)
    if meta:
        cost = f"${meta['cost_usd']:.2f}" if meta.get("cost_usd") is not None else "unknown"
        out({"systemMessage": f"Saved as {meta['run']} · cost so far {cost}. For your next run: change governance.yaml, save, start a new session."})
    sys.exit(0)


# ───────────── course team
def pack_runs():
    import zipfile
    runs = ROOT / "runs"
    if not runs.exists():
        sys.exit("No runs saved yet.")
    name = ROOT / f"runs_piece{current().get('piece', 'x')}_{datetime.datetime.now():%Y%m%d-%H%M}.zip"
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
        for f in runs.rglob("*"):
            z.write(f, f.relative_to(ROOT))
    print(f"Created {name.name}.")


if __name__ == "__main__":
    cmd = sys.argv[1:] or ["show"]
    if cmd[0] == "hook":
        data = json.load(sys.stdin) if not sys.stdin.isatty() else {}
        {"session": on_session, "pre": on_pre, "stop": on_stop}[cmd[1]](data)
    elif cmd[0] == "pack":
        pack_runs()
    else:
        final = finalize(cur)
        piece, sw = read_yaml()
        print(f"Piece {piece or 'not chosen'}")
        for k in SWITCHES:
            print(f"  {k:<11} {'on' if sw[k] else 'off'}")
