---
name: generate-edu-workflow
description: Use when the user wants an EvoAgentX workflow generated from a task, topic, or saved education search result. Run the workflow generator and save both JSON and Markdown artifacts.
---

# Generate Education Workflow

Use this skill for requests like:
- "根据这个任务生成 workflow"
- "为这个教学主题设计多智能体工作流"
- "把搜索结果转成可执行 workflow"

## Default path

Run one of:

```bash
python scripts/generate_workflow.py --goal "<task or topic>"
python scripts/generate_workflow.py --input data/search_results/<file>.md
python scripts/generate_workflow.py --mode sequential --goal "<task>"
```

## Expectations

- Prefer `--goal` for direct user tasks.
- Prefer `--input` when the user explicitly references a saved search artifact.
- Report the saved files in `workflows/`.
