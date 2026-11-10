#!/usr/bin/env python3
"""Pass/fail check for your piece. Run: python checks/check.py
It checks shape and internal consistency, not whether your judgement is right.
Exit code 0 = pass, 1 = fail (with the reasons)."""
import csv, datetime, json, math, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIECE = (ROOT / ".govern" / "piece").read_text().strip() if (ROOT / ".govern" / "piece").exists() else "1"
problems = []


def load(rel):
    p = ROOT / rel
    if not p.exists():
        problems.append(f"{rel} does not exist")
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        problems.append(f"{rel} is not valid JSON: {e}")
        return None


def week_plus(week, n):
    y, w = map(int, week.split("-W"))
    d = datetime.date.fromisocalendar(y, w, 1) + datetime.timedelta(weeks=n)
    y2, w2, _ = d.isocalendar()
    return f"{y2}-W{w2:02d}"


def week_key(week):
    y, w = map(int, week.split("-W"))
    return (y, w)


def check1():
    s = load("work/suppliers.json")
    if s is None:
        return
    sup = s.get("suppliers", [])
    ids = sorted(x.get("id") for x in sup)
    if ids != [f"S{i}" for i in range(1, 7)]:
        problems.append(f"suppliers must be S1 to S6 exactly, found {ids}")
    used = set()
    for x in sup:
        for k in ["id", "name", "country", "share_pct", "status", "expected_delay_weeks", "at_sea_t", "blocked_t", "sources"]:
            if k not in x:
                problems.append(f"{x.get('id')}: field '{k}' missing")
        if x.get("status") not in ("normal", "delayed", "suspended"):
            problems.append(f"{x.get('id')}: status must be normal, delayed or suspended")
        for f in x.get("sources", []):
            if not (ROOT / f).exists():
                problems.append(f"{x.get('id')}: source {f} does not exist")
            used.add(f)
    for i in s.get("ignored", []):
        used.add(i.get("file"))
    for folder in ["data/reports", "data/notices", "data/inbox"]:
        for f in sorted((ROOT / folder).glob("*")):
            rel = f"{folder}/{f.name}"
            if rel not in used:
                problems.append(f"{rel} is neither in any 'sources' nor in 'ignored'")


def check2():
    e = load("work/exposure.json")
    if e is None:
        return
    for k in ["stock_on_hand_t", "inbound_counted_t", "weekly_use_t", "weeks_of_cover", "run_out_week", "cover_estimates_seen", "critical_suppliers", "orders_at_risk", "conflicts"]:
        if k not in e:
            problems.append(f"field '{k}' missing")
    if problems:
        return
    try:
        calc = (e["stock_on_hand_t"] + e["inbound_counted_t"]) / e["weekly_use_t"]
    except (TypeError, ZeroDivisionError):
        problems.append("stock_on_hand_t, inbound_counted_t and weekly_use_t must be numbers")
        return
    if abs(calc - e["weeks_of_cover"]) > 0.06:
        problems.append(f"weeks_of_cover is {e['weeks_of_cover']}, but your own figures give {calc:.2f}")
    expect_week = week_plus("2026-W45", math.floor(e["weeks_of_cover"]))
    if e["run_out_week"] != expect_week:
        problems.append(f"run_out_week is {e['run_out_week']}, but 2026-W45 plus {math.floor(e['weeks_of_cover'])} whole weeks is {expect_week}")
    orders = list(csv.DictReader(open(ROOT / "data/orders/customer_orders.csv", encoding="utf-8")))
    late = {o["order_id"] for o in orders if week_key(o["delivery_week"]) > week_key(e["run_out_week"])}
    listed = {o.get("order_id") for o in e["orders_at_risk"]}
    if late - listed:
        problems.append(f"orders delivered after your run-out week but not listed: {sorted(late - listed)}")
    if listed - late:
        problems.append(f"orders listed as at risk but delivered before your run-out week: {sorted(listed - late)}")
    if not e["cover_estimates_seen"]:
        problems.append("cover_estimates_seen is empty")
    far = [c for c in e["cover_estimates_seen"] if isinstance(c.get("weeks"), (int, float)) and abs(c["weeks"] - e["weeks_of_cover"]) > 0.2]
    if far and not e["conflicts"]:
        problems.append("some cover estimates differ from yours, but conflicts is empty")


def check3():
    b = ROOT / "out/briefing.md"
    if not b.exists():
        problems.append("out/briefing.md does not exist")
        return
    text = b.read_text(encoding="utf-8")
    low = text.lower()
    for sec in ["exposed suppliers", "weeks of cover", "customer orders at risk", "what we can do", "open questions"]:
        if not re.search(r"^#+\s*" + re.escape(sec), low, re.M):
            problems.append(f"section '{sec}' missing")
    e = load("work/exposure.json") or {}
    s = load("work/suppliers.json") or {}
    names = {x["id"]: x["name"] for x in s.get("suppliers", [])}
    for c in e.get("critical_suppliers", []):
        if c["id"] not in text and names.get(c["id"], "@@").lower() not in low:
            problems.append(f"critical supplier {c['id']} is not named")
    for o in e.get("orders_at_risk", []):
        if o["order_id"] not in text:
            problems.append(f"order at risk {o['order_id']} is not named")
    if "weeks_of_cover" in e and str(e["weeks_of_cover"]) not in text:
        problems.append(f"the weeks of cover ({e['weeks_of_cover']}) do not appear")
    if not list((ROOT / "outbox").glob("*.eml")):
        problems.append("nothing was sent (outbox/ is empty)")


{"1": check1, "2": check2, "3": check3}[PIECE]()
if problems:
    print(f"CHECK FAILED · piece {PIECE}")
    for p in problems:
        print(" - " + p)
    sys.exit(1)
print(f"CHECK PASSED · piece {PIECE}")
