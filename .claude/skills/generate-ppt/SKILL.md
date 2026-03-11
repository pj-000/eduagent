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
python scripts/run_ppt.py --course "<course>" --units "<units>" --lessons "<lessons>" --knowledge-points "<knowledge_points>"
```

Add flags only when explicit:
- custom constraints: `--constraint "<text>"`
- page limit: `--page-limit <number>`
- use local knowledge base: `--use-rag`
- switch model: `--model-type QWen|DeepSeek`
- markdown only: `--output-mode md`

## Expectations

- Do not route PPT-generation requests to `scripts/run_agent.py` unless the user explicitly asks for the search/workflow pipeline.
- If the user says "先联网查资料再生成PPT", run the search path first, then generate the PPT.
- Always report:
  - markdown path in `results/ppt_md/`
  - pptx path in `results/pptx/` when `output_mode=ppt`
  - metadata path in `data/ppt_runs/`
  - the key parameters used for this generation
