"""
主程序入口
协调整个PPT生成流程
"""


from pathlib import Path
from pptx import Presentation
from markdown_parser import parse_markdown_optimized
from content_extractor import extract_content_elements_enhanced, split_content_by_length
from slide_creator import add_content_to_slide_enhanced, create_slides_optimized, prs as slide_prs, layout_map
from config import *



# ---------- 1. 读取 Markdown ----------
md_text = MD_FILE.read_text(encoding='utf-8')

# ---------- 2. 打开模板 ----------
# 使用 slide_creator 中的共享 Presentation，无需重新创建
prs = Presentation(TMPL_FILE)
layout_map = {ly.name: ly for ly in prs.slide_layouts}

# ---------- 3. 主程序执行 ----------
print("🚀 开始解析Markdown文件...")
print(f"配置参数:")
print(f"  - 最大要点数/页: {MAX_BULLETS_PER_SLIDE}")
print(f"  - 最大文本长度/页: {MAX_TEXT_LENGTH}")
print(f"  - 合并三级标题: {MERGE_SUBSECTIONS}")
print(f"  - 创建一级标题页: {CREATE_TITLE_SLIDES}")

slides_data = parse_markdown_optimized(md_text)
print(f"找到 {len(slides_data)} 个主章节")

print(f"\n📊 可用版式: {list(layout_map.keys())}")

# 生成幻灯片
total_slides = create_slides_optimized(slides_data)

# 保存文件
slide_prs.save(OUT_FILE)
print(f'\n✅ 已生成 {OUT_FILE.resolve()}')
print(f"📈 总共创建了 {total_slides} 张幻灯片")
print(f"🎯 平均每个主章节 {total_slides/len(slides_data):.1f} 张幻灯片")