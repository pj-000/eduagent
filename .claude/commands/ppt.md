---
description: Generate PPT markdown or PPTX with the migrated local PPT-generation capability
---

Handle this PPT-generation request:

`$ARGUMENTS`

Steps:
1. Treat this as a PPT / slide-generation request, but keep the planner as the only default decision layer.
2. Ensure the request includes `course` and at least one of `units`, `lessons`, or `knowledge_points`.
3. If those fields are missing, ask one concise follow-up question before running anything.
4. Use defaults unless the user overrides them:
   - `constraint=""`
   - `page_limit=null`
   - `use_rag=false`
   - `model_type=QWen`
   - `output_mode=ppt`
5. Run `python scripts/run_planner.py --task "$ARGUMENTS" --capability ppt --planner-mode hybrid --planner-model QWen --json ...` with the collected fields.
6. Return:
   - planner analysis and selected route
   - markdown path in `results/ppt_md/`
   - pptx path in `results/pptx/` when generated
   - metadata path in `data/ppt_runs/`
   - the key parameters used
7. Prefer `--set course=... --set units=... --set lessons=... --set knowledge_points=...` style flags so the call shape stays consistent.
8. Only bypass the planner if the user explicitly asks for MCP or direct capability execution.
