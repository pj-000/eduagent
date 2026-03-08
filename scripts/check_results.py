#!/usr/bin/env python3
"""检查搜索结果目录"""
import os
import json
from pathlib import Path
from datetime import datetime

save_dir = Path("/Users/sss/directionai/eduagent/data/search_results")
save_dir.mkdir(parents=True, exist_ok=True)

print("=" * 70)
print("教育创新功能探索 - 目录检查")
print("=" * 70)
print(f"搜索结果目录: {save_dir}")
print(f"绝对路径: {save_dir.absolute()}")
print(f"目录存在: {save_dir.exists()}")
print("-" * 70)

files = list(save_dir.glob("explore_*.md"))
print(f"找到 {len(files)} 个搜索结果文件:")
for f in sorted(files, key=lambda x: x.name, reverse=True)[:5]:
    print(f"  - {f.name}")
    # 尝试读取文件大小
    try:
        size = f.stat().st_size
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        print(f"    大小: {size} bytes, 修改时间: {mtime}")
    except:
        pass