---
name: run-eduagent
description: Use when the user gives a natural-language education task and wants EduAgent to handle it end-to-end. Run the unified pipeline that performs official EvoAgentX framework research, education innovation search, workflow generation, and workflow execution.
---

# Run EduAgent

Use this skill for end-to-end tasks such as:
- "帮我设计一个数学教学工作流并执行"
- "探索 AI 助教方案并给出落地 workflow"
- "用这个项目完成一个教育任务"

Do not use this skill for direct lesson-plan requests like "帮我生成教案" or "帮我备课".
Those should go to `generate-lesson-plan` instead.
Do not use this skill for direct exam-generation requests like "帮我生成试卷" or "根据知识点出题".
Those should go to `generate-exam` instead.
Do not use this skill for direct PPT-generation requests like "帮我生成PPT" or "帮我生成课件".
Those should go to `generate-ppt` instead.

## Default path

1. Work inside the `eduagent/` project root.
2. If the request is specifically about lesson plans / teaching design, switch to:

```bash
python scripts/run_lesson_plan.py --course "<course>" --units "<units>" --lessons "<lessons>"
```

3. If the request is specifically about exam generation / question generation, switch to:

```bash
python scripts/run_exam.py --subject "<subject>" --knowledge-bases "<knowledge_bases>"
```

4. If the request is specifically about PPT / slide generation, switch to:

```bash
python scripts/run_ppt.py --course "<course>" --units "<units>" --lessons "<lessons>" --knowledge-points "<knowledge_points>"
```

5. Otherwise prefer the unified pipeline:

```bash
python scripts/run_agent.py --task "<user task>"
```

6. Map optional user intent to flags only when explicit:
- focus domain: `--focus free|adaptive|assessment|content|interaction`
- explicit search themes: repeated `--theme "<theme>"`
- skip framework docs lookup: `--skip-framework-research`
- skip education search: `--skip-search`
- fast linear workflow: `--mode sequential`

## After execution

Always report:
- framework notes path in `data/framework_notes/`
- task state path in `data/task_runs/`
- workflow path in `workflows/`
- final result path in `results/`

If execution fails, inspect the latest `task_state_*.json` and identify the failed stage before responding.
