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
2. `run_planner.py` is the only default decision layer. Use this top-level entrypoint first:

```bash
python scripts/run_planner.py --task "<user task>" --planner-mode hybrid --planner-model QWen --json
```

3. Do not use any external/system Plan agent as a substitute for the project planner.
4. If structured parameters are already known, pass them as `--set key=value` flags to `run_planner.py` so the planner can still make the route decision.
5. Only bypass the planner when the user explicitly asks for MCP, direct capability execution, or workflow-only execution.

## After execution

Always report:
- planner analysis and selected route when you used `run_planner.py`
- framework notes path in `data/framework_notes/`
- task state path in `data/task_runs/`
- workflow path in `workflows/`
- final result path in `results/`

If execution fails, inspect the latest `task_state_*.json` and identify the failed stage before responding.
