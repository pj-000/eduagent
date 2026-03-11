---
description: Execute the latest or specified EduAgent workflow and summarize the result
---

Execute the latest or specified workflow for this request:

`$ARGUMENTS`

Steps:
1. If the request names a workflow file, use it with `python scripts/execute_workflow.py --workflow <file>`.
2. Otherwise run `python scripts/execute_workflow.py` to execute the latest workflow.
3. Summarize the final output and the saved result file in `results/`.
4. If execution fails, inspect the latest task state or traceback and identify the failing phase.
