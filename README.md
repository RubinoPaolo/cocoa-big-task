# The big task · cocoa supply briefing

All companies, people and places in this repository are invented.

## Once, at the start
In the terminal (bottom of the screen), choose the piece you were given:
```
python govern.py piece 1
```
(or 2, or 3). Then read `TASK.md`: it says what you build and what file you hand on.

## Each run
1. Open `governance.yaml` in the editor, set each switch to `on` or `off`, and save (Ctrl+S).
2. In the terminal: `python govern.py apply`
3. Start Claude: `claude`, then paste exactly: `Do the task in TASK.md.`
4. When it stops, look at the result in `work/` or `out/`, and at `.trace/agent_trace.md`. Type `/cost` and note the cost. Then `/exit`.
5. Save the run: `python govern.py log "what you changed, what you saw, cost $0.xx"`
   This saves the run in `runs/` and clears the output for the next run.

## At the end
`python govern.py pack` makes one zip file with all your runs. Download it and hand it in.

## The rule of the game
First run: all switches off. Then turn on one at a time.
Your question: **what is the least governance that gives a correct result?**
