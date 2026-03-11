---
name: search-edu-info
description: Use when the user wants education innovation research, trend exploration, or feature discovery. Run the education search agent and save the search artifacts.
---

# Search Education Info

Use this skill for requests like:
- "搜索教育领域创新点"
- "调研 AI 在课堂中的新应用"
- "找几个可落地的教育功能方向"

## Default path

Run one of:

```bash
python scripts/search_edu.py
python scripts/search_edu.py --focus adaptive
python scripts/search_edu.py --focus free --hint "<task or direction>"
python scripts/search_edu.py --theme "<theme 1>" --theme "<theme 2>"
python scripts/search_edu.py --hint "<custom hint>"
```

## Expectations

- If the user gives explicit themes, prefer repeated `--theme`.
- If the user asks for open-ended exploration, prefer `--focus free`.
- Otherwise use `--hint` or a suitable preset `--focus`.
- Prefer broad-source evidence: news, open web pages, blogs, communities, GitHub, product pages, and papers.
- Always return the saved artifact paths under `data/search_results/`.
- Keep source attribution from the generated report.
