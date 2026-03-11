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
python scripts/run_exam.py --subject "<subject>" --knowledge-bases "<knowledge_bases>"
```

Add flags only when explicit:
- custom constraints: `--constraint "<text>"`
- custom language: `--language "<text>"`
- custom counts: `--single-choice-num N` etc.
- custom difficulty ratios: `--easy-percentage N --medium-percentage N --hard-percentage N`
- use local knowledge base: `--use-rag`
- switch model: `--model-type QWen|DeepSeek`

## Expectations

- Do not route exam-generation requests to `scripts/run_agent.py` unless the user explicitly asks for the search/workflow pipeline.
- If the user says "先联网查资料再生成试卷", run the search path first, then generate the exam.
- Always report:
  - result JSON path in `results/exams/`
  - result Markdown path in `results/exams/`
  - metadata path in `data/exam_runs/`
  - the key parameters used for this generation
