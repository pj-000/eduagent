from pathlib import Path
from pptx.dml.color import RGBColor

"""
配置参数和常量
集中管理所有可配置参数，便于统一修改
"""

# 路径配置
MD_FILE   = Path('slides_qwen_3000.md')
TMPL_FILE = Path('ppt_template/template2.pptx')
OUT_FILE  = Path('output_template2.pptx')
# TMPL_FILE = Path('ppt_template/template.pptx')
# OUT_FILE  = Path('output_template.pptx')

# 内容分页配置
MAX_BULLETS_PER_SLIDE = 4
MAX_TEXT_LENGTH = 1000  # 减少每页最大长度，避免过长内容
MERGE_SUBSECTIONS = False
CREATE_TITLE_SLIDES = True
CREATE_TOC_SLIDE = True

# 目录页字体配置
TOC_TITLE_FONT_SIZE = 60
TOC_ITEMS_FONT_SIZE = 24

# 代码块长度阈值
CODE_LINES_THRESHOLD = 20

# Python关键字
PYTHON_KEYWORDS = {
    'def', 'class', 'import', 'from', 'if', 'else', 'elif', 'for', 'while',
    'try', 'except', 'finally', 'return', 'yield', 'with', 'as', 'pass',
    'break', 'continue', 'and', 'or', 'not', 'in', 'is', 'lambda', 'True', 'False', 'None'
}

# 颜色配置
KEYWORD_COLOR = RGBColor(0, 100, 200)  # 蓝色
STRING_COLOR = RGBColor(0, 128, 0)     # 绿色

COMMENT_COLOR = RGBColor(128, 128, 128) # 灰色
