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
python scripts/run_lesson_plan.py --course "<course>" --units "<units>" --lessons "<lessons>"
```

Add flags only when explicit:
- custom constraints: `--constraint "<text>"`
- custom length: `--word-limit <number>`
- use local knowledge base: `--use-rag`
- switch model: `--model-type QWen|DeepSeek`

## Expectations

- Do not route lesson-plan requests to `scripts/run_agent.py` unless the user explicitly asks for the search/workflow pipeline.
- If the user says "先联网查资料再生成教案", run the search path first, then generate the lesson plan.
- Always report:
  - lesson plan markdown path in `results/lesson_plans/`
  - metadata path in `data/lesson_plan_runs/`
  - the key parameters used for this generation
