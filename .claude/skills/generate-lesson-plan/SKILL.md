---
name: generate-lesson-plan
description: Use when the user asks to generate a lesson plan,备课内容,教学设计, or similar teaching material in this repository. Gather required fields, then run the migrated local lesson-plan entrypoint.
---

# Generate Lesson Plan

Use this skill for requests like:
- "帮我生成教案"
- "帮我备一节课"
- "根据这个知识点做教学设计"

Do not use this skill for PPT / 课件 / 幻灯片 requests.
The planner is the only default decision layer. This skill should gather lesson-plan parameters, then forward the task to `run_planner.py`.
Do not call the lesson-plan MCP tool or `run_capability.py` directly unless the user explicitly asks for MCP or direct capability execution.

## Required fields

Before running anything, make sure you have:
- `course`
- at least one of `units` or `lessons`

If either is missing, ask a short follow-up and collect them in one turn.

## Defaults

If the user does not specify them, use:
- `constraint=""`
- `word_limit=2000`
- `use_rag=false`
- `model_type=QWen`

## Default path

Run:

```bash
python scripts/run_planner.py --task "<user task>" --capability lesson_plan --planner-mode hybrid --planner-model QWen --json --set course="<course>" --set units="<units>" --set lessons="<lessons>"
```

Add flags only when explicit:
- custom constraints: `--set constraint="<text>"`
- custom length: `--set word_limit=<number>`
- use local knowledge base: `--set use_rag=true`
- switch model: `--set model_type=QWen|DeepSeek`

## Expectations

- Do not manually route lesson-plan requests to `scripts/run_agent.py` or split them into search/workflow phases unless the user explicitly asks to bypass the planner.
- If the user says "先联网查资料再生成教案", keep that full intent in the planner task text and let the planner choose the route.
- Always report:
  - planner analysis and selected route
  - lesson plan markdown path in `results/lesson_plans/`
  - metadata path in `data/lesson_plan_runs/`
  - the key parameters used for this generation
  - any `missing_fields` returned by the standardized JSON response when validation fails
