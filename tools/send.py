#!/usr/bin/env python3
"""Sends a briefing by e-mail. In this course nothing really leaves the computer:
the message is written to outbox/ as it would have been sent."""
import argparse, datetime, pathlib, sys
ap = argparse.ArgumentParser()
ap.add_argument("--to", required=True, help="comma-separated addresses")
ap.add_argument("file")
a = ap.parse_args()
body = pathlib.Path(a.file).read_text(encoding="utf-8")
rcpt = [x.strip() for x in a.to.split(",") if x.strip()]
out = pathlib.Path("outbox"); out.mkdir(exist_ok=True)
stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
(out / f"{stamp}.eml").write_text("To: " + ", ".join(rcpt) + "\nSubject: Cocoa supply briefing 2026-W45\n\n" + body, encoding="utf-8")
print(f"Sent to {len(rcpt)} recipient(s): " + ", ".join(rcpt))
