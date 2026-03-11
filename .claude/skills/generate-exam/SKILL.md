---
name: generate-exam
description: Use when the user asks to generate a test paper,试卷,题目,考题, or similar exam content in this repository. Gather the required fields, then run the migrated local exam entrypoint.
---

# Generate Exam

Use this skill for requests like:
- "帮我生成试卷"
- "根据知识点出题"
- "生成一份考试题"

Do not use this skill for PPT / 课件 / 幻灯片 requests.
The planner is the only default decision layer. This skill should gather exam parameters, then forward the task to `run_planner.py`.
Do not call the exam MCP tool or `run_capability.py` directly unless the user explicitly asks for MCP or direct capability execution.

## Required fields

Before running anything, make sure you have:
- `subject`
- `knowledge_bases`

If either is missing, ask one short follow-up and collect them together.

## Defaults

If the user does not specify them, use:
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

## Default path

Run:

```bash
python scripts/run_planner.py --task "<user task>" --capability exam --planner-mode hybrid --planner-model QWen --json --set subject="<subject>" --set knowledge_bases="<knowledge_bases>"
```

Add flags only when explicit:
- custom constraints: `--set constraint="<text>"`
- custom language: `--set language="<text>"`
- custom counts: `--set single_choice_num=N` etc.
- custom difficulty ratios: `--set easy_percentage=N --set medium_percentage=N --set hard_percentage=N`
- use local knowledge base: `--set use_rag=true`
- switch model: `--set model_type=QWen|DeepSeek`

## Expectations

- Do not manually route exam-generation requests to `scripts/run_agent.py` or split them into search/workflow phases unless the user explicitly asks to bypass the planner.
- If the user says "先联网查资料再生成试卷", keep that full intent in the planner task text and let the planner choose the route.
- Always report:
  - planner analysis and selected route
  - result JSON path in `results/exams/`
  - result Markdown path in `results/exams/`
  - metadata path in `data/exam_runs/`
  - the key parameters used for this generation
  - any `missing_fields` returned by the standardized JSON response when validation fails
