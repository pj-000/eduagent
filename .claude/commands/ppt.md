---
description: Generate PPT markdown or PPTX with the migrated local PPT-generation capability
---

Handle this PPT-generation request:

`$ARGUMENTS`

Steps:
1. Treat this as a PPT / slide-generation request, not the generic search -> workflow -> execute pipeline.
2. Ensure the request includes `course` and at least one of `units`, `lessons`, or `knowledge_points`.
3. If those fields are missing, ask one concise follow-up question before running anything.
4. Use defaults unless the user overrides them:
   - `constraint=""`
   - `page_limit=null`
   - `use_rag=false`
   - `model_type=QWen`
   - `output_mode=ppt`
5. Run `python scripts/run_ppt.py ...` with the collected fields.
6. Return:
   - markdown path in `results/ppt_md/`
   - pptx path in `results/pptx/` when generated
   - metadata path in `data/ppt_runs/`
   - the key parameters used
