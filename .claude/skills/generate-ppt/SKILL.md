---
name: generate-ppt
description: Use when the user asks to generate PPT slides,课件,幻灯片, or similar presentation content in this repository. Gather required fields, then run the migrated local PPT entrypoint.
---

# Generate PPT

Use this skill for requests like:
- "帮我生成PPT"
- "帮我生成课件"
- "根据知识点生成幻灯片"

Do not use this skill for lesson-plan requests such as "帮我生成教案" or exam requests such as "帮我生成试卷".
If the user explicitly asks for PPT / 课件 / 幻灯片, this skill should take priority over `generate-lesson-plan`.
The planner is the only default decision layer. This skill should gather PPT parameters, then forward the task to `run_planner.py`.
Do not call the PPT MCP tool or `run_capability.py` directly unless the user explicitly asks for MCP or direct capability execution.

## Required fields

Before running anything, make sure you have:
- `course`
- at least one of `units`, `lessons`, or `knowledge_points`

If required fields are missing, ask one short follow-up and collect them together.

## Defaults

If the user does not specify them, use:
- `constraint=""`
- `page_limit=null`
- `use_rag=false`
- `model_type=QWen`
- `output_mode=ppt`

## Default path

Run:

```bash
python scripts/run_planner.py --task "<user task>" --capability ppt --planner-mode hybrid --planner-model QWen --json --set course="<course>" --set units="<units>" --set lessons="<lessons>" --set knowledge_points="<knowledge_points>"
```

Add flags only when explicit:
- custom constraints: `--set constraint="<text>"`
- page limit: `--set page_limit=<number>`
- use local knowledge base: `--set use_rag=true`
- switch model: `--set model_type=QWen|DeepSeek`
- markdown only: `--set output_mode=md`

## Expectations

- Do not manually route PPT-generation requests to `scripts/run_agent.py` or split them into search/workflow phases unless the user explicitly asks to bypass the planner.
- If the user says "先联网查资料再生成PPT", keep that full intent in the planner task text and let the planner choose the route.
- Always report:
  - planner analysis and selected route
  - markdown path in `results/ppt_md/`
  - pptx path in `results/pptx/` when `output_mode=ppt`
  - metadata path in `data/ppt_runs/`
  - the key parameters used for this generation
  - any `missing_fields` returned by the standardized JSON response when validation fails
