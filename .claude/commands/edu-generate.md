---
description: Generate an EvoAgentX workflow for a natural-language education task
---

Generate an EvoAgentX workflow for this task:

`$ARGUMENTS`

Steps:
1. Work in the `eduagent/` project root.
2. Run `python scripts/generate_workflow.py --goal "$ARGUMENTS"`.
3. Report:
   - workflow goal
   - node count
   - saved JSON path
   - saved Markdown path
4. If generation fails, inspect the traceback and explain whether the issue came from goal construction, JSON parsing, or workflow generation.
