---
description: Run the full EduAgent pipeline for a natural-language education task
---

Run EduAgent end-to-end for the following natural-language task:

`$ARGUMENTS`

Workflow:
1. Work in the `eduagent/` project root.
2. `run_planner.py` is the only default decision layer. Call `python scripts/run_planner.py --task "$ARGUMENTS" --planner-mode hybrid --planner-model QWen --json`.
3. Do not use any external/system Plan agent as a substitute for the project planner.
4. Do not manually split the task into search / framework / generation sub-steps unless the user explicitly asks for manual control.
5. Do not call `run_capability.py`, `run_agent.py`, or repo-local MCP generation tools unless the user explicitly asks to bypass the planner.
6. Summarize the generated artifact paths:
   - official framework notes
   - search results
   - task state
   - workflow files
   - final execution result or direct generation artifacts
7. For planner runs, parse `analysis`, `selected_route`, `attempts`, `review` (when present), and final `result`.
8. If the user explicitly asks to bypass the planner, say so briefly and then use the requested lower-level entrypoint.
9. If the pipeline fails, inspect the latest `data/task_runs/task_state_*.json` and report the failing stage before answering.
10. Workflow runs do not use the new reviewer yet.
