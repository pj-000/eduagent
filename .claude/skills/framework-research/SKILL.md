---
name: framework-research
description: Use when the task depends on EvoAgentX capabilities, APIs, workflow patterns, tools, memory, or HITL. Fetch and summarize only official EvoAgentX GitHub and documentation sources.
---

# Framework Research

Use this skill when the user asks about:
- EvoAgentX APIs
- workflow patterns
- tools, memory, or HITL support
- whether a feature is supported officially

## Default path

Run:

```bash
python scripts/framework_research.py --task "<current task>"
```

## Expectations

- Use only official EvoAgentX sources gathered by the script.
- Prefer these artifacts in your response:
  - `data/framework_notes/framework_notes_*.md`
  - `data/framework_notes/framework_notes_*.json`
- If the user later asks to build or change the project, reuse the latest framework notes instead of re-explaining from memory.
