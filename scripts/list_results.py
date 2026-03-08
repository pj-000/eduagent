#!/usr/bin/env python3
"""列出搜索结果目录内容"""
import os
from pathlib import Path

save_dir = Path("/Users/sss/directionai/eduagent/data/search_results")
save_dir.mkdir(parents=True, exist_ok=True)

print(f"搜索结果目录: {save_dir}")
print(f"目录内容:")
for f in sorted(save_dir.iterdir(), key=lambda x: x.name, reverse=True):
    print(f"  - {f.name}")