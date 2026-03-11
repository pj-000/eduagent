---
description: Generate a lesson plan with the migrated local lesson-plan capability
---

Handle this lesson-plan request:

`$ARGUMENTS`

Steps:
1. Treat this as a lesson-plan / teaching-design request, not the generic search -> workflow -> execute pipeline.
2. Ensure the request includes `course` and at least one of `units` or `lessons`.
3. If those fields are missing, ask one concise follow-up question before running anything.
4. Use defaults unless the user overrides them:
   - `constraint=""`
   - `word_limit=2000`
   - `use_rag=false`
   - `model_type=QWen`
5. Run `python scripts/run_lesson_plan.py ...` with the collected fields.
6. Return:
   - lesson plan markdown path in `results/lesson_plans/`
   - metadata path in `data/lesson_plan_runs/`
   - the key parameters used
