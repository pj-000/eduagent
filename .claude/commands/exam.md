---
description: Generate exam questions with the migrated local exam-generation capability
---

Handle this exam-generation request:

`$ARGUMENTS`

Steps:
1. Treat this as an exam / question-generation request, but keep the planner as the only default decision layer.
2. Ensure the request includes `subject` and `knowledge_bases`.
3. If those fields are missing, ask one concise follow-up question before running anything.
4. Use defaults unless the user overrides them:
   - `constraint=""`
   - `language="Chinese"`
   - `single_choice_num=3`
   - `multiple_choice_num=3`
   - `true_false_num=3`
   - `fill_blank_num=2`
   - `short_answer_num=2`
   - `programming_num=1`
   - `easy_percentage=30`
   - `medium_percentage=50`
   - `hard_percentage=20`
   - `use_rag=false`
   - `model_type=QWen`
5. Run `python scripts/run_planner.py --task "$ARGUMENTS" --capability exam --planner-mode hybrid --planner-model QWen --json ...` with the collected fields.
6. Return:
   - planner analysis and selected route
   - result JSON path in `results/exams/`
   - result Markdown path in `results/exams/`
   - metadata path in `data/exam_runs/`
   - the key parameters used
7. Prefer `--set subject=... --set knowledge_bases=...` style flags so the call shape stays consistent.
8. Only bypass the planner if the user explicitly asks for MCP or direct capability execution.
