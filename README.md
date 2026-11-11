# The big task · cocoa supply briefing

All companies, people and places in this repository are invented.

You work only in the editor and in the Claude panel. No terminal needed.

## Once, at the start
Open `governance.yaml`, set `piece:` to the piece you were given (1, 2 or 3), leave all switches `off`, and save (Ctrl+S).

## Each run
1. In the Claude panel (the ✳ icon), start a **new session**. Claude prepares `TASK.md` and `work/` for your piece and turns your switches on.
2. Ask: `Do the task in TASK.md.`
3. When Claude stops, the panel shows "Saved as run_NN · cost so far $…". Look at the result in `work/` or `out/`, and at `.trace/agent_trace.md`. Write it in the run log of your worksheet.
4. For the next run, change **one** switch in `governance.yaml`, save, and start a new session. The switches are read when a session starts.

Every run is saved in `runs/` by itself. There is nothing to hand in.

## The rule of the game
First run: all switches off. Then turn on one at a time.
Your question: **what is the least governance that gives a correct result?**
