---
name: execute-edu-workflow
description: Use when the user wants to run a generated EvoAgentX workflow, inspect execution state, or troubleshoot a failed run. Run the workflow executor and report saved results.
---

# Execute Education Workflow

Use this skill for requests like:
- "执行最新 workflow"
- "跑一下这个 workflow"
- "帮我看 workflow 为什么失败"

## Default path

Run one of:

```bash
python scripts/execute_workflow.py
python scripts/execute_workflow.py --workflow workflows/<file>.json
python scripts/execute_workflow.py --workflow workflows/<file>.json --inputs <inputs>.json
```

## Expectations

- If the workflow fails, inspect the latest task state or traceback and identify the failing stage or node.
- Always report the result artifact in `results/`.
- If the user wants end-to-end handling, switch to the `run-eduagent` skill instead of manually chaining multiple scripts.
