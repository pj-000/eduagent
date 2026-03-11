---
description: Run the full EduAgent pipeline for a natural-language education task
---

Run EduAgent end-to-end for the following natural-language task:

`$ARGUMENTS`

Workflow:
1. Work in the `eduagent/` project root.
2. If the request is about 教案 / 备课 / 教学设计, do not use `scripts/run_agent.py`.
3. For lesson-plan requests, ensure `course` and at least one of `units` or `lessons` are present, then run `python scripts/run_lesson_plan.py ...`.
4. If the request is about 试卷 / 出题 / 题目生成, do not use `scripts/run_agent.py`.
5. For exam-generation requests, ensure `subject` and `knowledge_bases` are present, then run `python scripts/run_exam.py ...`.
6. If the request is about PPT / 课件 / 幻灯片, do not use `scripts/run_agent.py`.
7. For PPT-generation requests, ensure `course` and at least one of `units`, `lessons`, or `knowledge_points` are present, then run `python scripts/run_ppt.py ...`.
8. Otherwise run `python scripts/run_agent.py --task "$ARGUMENTS"`.
9. If the task asks for open-ended idea generation, prefer `--focus free`.
10. If the task clearly matches `adaptive`, `assessment`, `content`, or `interaction`, add `--focus` accordingly.
11. If the request names specific themes, add repeated `--theme "<theme>"`.
12. Summarize the generated artifact paths:
   - official framework notes
   - search results
   - task state
   - workflow files
   - final execution result or direct generation artifacts
13. If the pipeline fails, inspect the latest `data/task_runs/task_state_*.json` and report the failing stage before answering.
