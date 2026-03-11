---
description: Generate a lesson plan with the migrated local lesson-plan capability
---

Handle this lesson-plan request:

`$ARGUMENTS`

Steps:
1. Treat this as a lesson-plan / teaching-design request, but keep the planner as the only default decision layer.
2. Ensure the request includes `course` and at least one of `units` or `lessons`.
3. If those fields are missing, ask one concise follow-up question before running anything.
4. Use defaults unless the user overrides them:
   - `constraint=""`
   - `word_limit=2000`
   - `use_rag=false`
   - `model_type=QWen`
5. Run `python scripts/run_planner.py --task "$ARGUMENTS" --capability lesson_plan --planner-mode hybrid --planner-model QWen --json ...` with the collected fields.
6. Return:
   - planner analysis and selected route
   - lesson plan markdown path in `results/lesson_plans/`
   - metadata path in `data/lesson_plan_runs/`
   - the key parameters used
7. Prefer `--set course=... --set units=... --set lessons=...` style flags so the call shape stays consistent.
8. Only bypass the planner if the user explicitly asks for MCP or direct capability execution.
