"""
make_ppt 命令行入口 —— 接受外部参数将 MD 文件转为 PPTX

用法:
    python convert_ppt.py <md_file> <output_pptx> [--template <template.pptx>]
"""

import sys
import argparse
from pathlib import Path

def convert(md_file: str, output_file: str, template_file: str = None):
    """将 Markdown 文件转换为 PPTX"""
    import config as cfg

    # 动态覆盖 config 中的路径
    cfg.MD_FILE = Path(md_file)
    cfg.OUT_FILE = Path(output_file)
    if template_file:
        cfg.TMPL_FILE = Path(template_file)

    from pptx import Presentation
    from markdown_parser import parse_markdown_optimized
    from content_extractor import extract_content_elements_enhanced, split_content_by_length
    import slide_creator

    # 重新初始化 Presentation（使用可能被覆盖的模板路径）
    prs = Presentation(cfg.TMPL_FILE)
    layout_map = {ly.name: ly for ly in prs.slide_layouts}

    # 更新 slide_creator 中的全局对象
    slide_creator.prs = prs
    slide_creator.layout_map = layout_map

    import layout_selector as _layout_selector
    _layout_selector.layout_map = layout_map
    _layout_selector.prs = prs

    # 读取 MD 文件
    md_text = cfg.MD_FILE.read_text(encoding='utf-8')

    # 解析 + 生成
    slides_data = parse_markdown_optimized(md_text)
    print(f"找到 {len(slides_data)} 个主章节")

    total_slides = slide_creator.create_slides_optimized(slides_data)

    # 保存
    slide_creator.prs.save(cfg.OUT_FILE)
    print(f"✅ 已生成 {cfg.OUT_FILE.resolve()}")
    print(f"📈 总共创建了 {total_slides} 张幻灯片")

    return str(cfg.OUT_FILE.resolve())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='将 Markdown 转换为 PPT')
    parser.add_argument('md_file', help='输入的 Markdown 文件路径')
    parser.add_argument('output_file', help='输出的 PPTX 文件路径')
    parser.add_argument('--template', default=None, help='PPT 模板文件路径')
    args = parser.parse_args()

    convert(args.md_file, args.output_file, args.template)
