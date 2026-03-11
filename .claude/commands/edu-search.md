---
description: Search for education innovation opportunities related to a task or direction
---

Search for education innovation directions for this request:

`$ARGUMENTS`

Steps:
1. If the request contains explicit themes, run `python scripts/search_edu.py --theme "<theme>" ...` and preserve all requested themes.
2. If the request asks for open-ended exploration, run `python scripts/search_edu.py --focus free --hint "$ARGUMENTS"`.
3. Otherwise, if the request includes a clear direction, run `python scripts/search_edu.py --hint "$ARGUMENTS"`.
4. If the request is still broad, choose an appropriate `--focus` and run `python scripts/search_edu.py --focus <focus>`.
5. Return the saved artifact paths under `data/search_results/`.
6. Prefer evidence from multiple source types: news, blogs, communities, GitHub, product pages, and papers.
7. Summarize the most actionable ideas for this repository.
