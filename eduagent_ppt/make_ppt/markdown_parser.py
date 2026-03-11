"""
Markdown文件解析
将Markdown内容转换为结构化数据
"""


import re
from config import *


def parse_markdown_optimized(text):
    """
    优化版Markdown解析：支持内容合并和层级控制，特别处理代码块，添加封面页支持
    增强：防止代码块中的#注释被误认为标题
    """
    slides = []
    
    # 预处理：标记代码块，避免代码块中的#被误认为标题
    lines = text.split('\n')
    processed_lines = []
    in_code_block = False
    
    for line in lines:
        # 检测代码块开始/结束
        if re.match(r'^```+', line.strip()):
            in_code_block = not in_code_block
            processed_lines.append(line)
        elif in_code_block:
            # 在代码块内，将#替换为特殊标记，避免被误认为标题
            if line.strip().startswith('#'):
                processed_lines.append(line.replace('#', '§CODE_COMMENT§', 1))
            else:
                processed_lines.append(line)
        else:
            processed_lines.append(line)
    
    processed_text = '\n'.join(processed_lines)
    
    # 按一级标题分割
    slide_blocks = re.split(r'(?m)^(#\s+.+)$', processed_text)
    
    for i in range(1, len(slide_blocks), 2):
        title_line = slide_blocks[i]
        content_block = slide_blocks[i+1] if i+1 < len(slide_blocks) else ""
        
        # 提取一级标题
        title_match = re.match(r'^#\s+(.+)', title_line.strip())
        if not title_match:
            continue
            
        main_title = title_match.group(1)
        
        # 检查是否是封面页 - 判断是否是第一个标题且包含课程名称特征，同时排除“目录”页
        if i == 1 and main_title not in ["目录", "contents", "Contents", "目录页"] and (len(content_block.strip()) < 100 or "课程标题页" in content_block or "---" in content_block):
            # 创建封面页数据结构
            slides.append({
                'main_title': main_title,
                'content': content_block.strip().split('\n'),
                'sections': [],
                'is_title_page': True  # 标记为封面页
            })
            continue
        
        # 检查是否是目录页
        if main_title == "目录" or main_title.lower() == "contents" or "目录" in main_title:
            # 解析目录内容
            toc_items = []
            lines = content_block.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line and (line.startswith('-') or line.startswith('*') or re.match(r'^\d+\.', line)):
                    # 提取目录项，保留原有的编号格式（如"一、"、"二、"等）
                    toc_item = re.sub(r'^[-*]\s*', '', line).strip()  # 只移除列表符号，保留原有编号
                    if toc_item:
                        toc_items.append(toc_item)
            
            # 创建目录页数据结构
            slides.append({
                'main_title': main_title,
                'content': [],
                'sections': [],
                'is_toc': True,
                'toc_items': toc_items
            })
            continue
        
        # 解析内容结构
        content_lines = []
        sections = []
        current_section = None
        
        lines = content_block.strip().split('\n')
        in_code_block = False
        code_buffer = []
        code_block_just_closed = False  # 标识刚结束代码块
        for line in lines:
            # 处理代码块标记 - 支持三个和四个反引号
            code_marker_match = re.match(r'^```+', line.strip())
            if code_marker_match:
                if in_code_block:
                    # 结束代码块
                    if current_section:
                        current_section['content'].extend(code_buffer)
                        current_section['content'].append(line)
                    else:
                        content_lines.extend(code_buffer)
                        content_lines.append(line)
                    code_buffer = []
                    in_code_block = False
                    code_block_just_closed = True  # 记录代码块刚结束
                else:
                    # 开始代码块
                    if current_section:
                        current_section['content'].append(line)
                    else:
                        content_lines.append(line)
                    in_code_block = True
                continue
              # 如果在代码块内，直接添加到缓冲区并还原#注释
            if in_code_block:
                # 还原代码块中的#注释
                restored_line = line.replace('§CODE_COMMENT§', '#')
                code_buffer.append(restored_line)
                continue
            
            # 空行处理
            if not line.strip():
                # 遇到空行时重置刚结束代码块标志，避免跨段落误触发
                code_block_just_closed = False
                if current_section:
                    current_section['content'].append(line)
                else:
                    content_lines.append(line)
                continue
                
            # 二级标题
            if line.strip().startswith('## '):
                # 遇到标题时也重置代码块结束标志
                code_block_just_closed = False
                # 保存之前的section
                if current_section:
                    sections.append(current_section)
                
                current_section = {
                    'title': line.strip()[3:].strip(),
                    'level': 2,
                    'content': [],
                    'subsections': []
                }
                continue
            
            # 三级标题处理（如果启用合并，则合并到二级标题中）
            # 遇到三级标题同样重置标志

            elif line.strip().startswith('### '):
                if MERGE_SUBSECTIONS and current_section:
                    # 合并到二级标题中
                    subsection_title = line.strip()[4:].strip()
                    current_section['content'].append(f"**{subsection_title}**")
                else:
                    # 三级标题独立处理
                    if current_section:
                        sections.append(current_section)
                    
                    current_section = {
                        'title': line.strip()[4:].strip(),
                        'level': 3,
                        'content': [],
                        'subsections': []
                    }
                continue
            
            # 内容行
            else:
                # 检测代码块结束后紧跟要点的情况，自动拆分为新的二级标题块
                if code_block_just_closed and line.lstrip().startswith('-') and current_section:
                    # 结束当前 section 并创建一个新的 section，标题与当前保持一致
                    sections.append(current_section)
                    current_section = {
                        'title': current_section['title'],
                        'level': current_section['level'],
                        'content': [],
                        'subsections': []
                    }
                    code_block_just_closed = False  # 已处理
                # 常规内容处理
                if current_section:
                    current_section['content'].append(line)
                else:
                    content_lines.append(line)
        
        # 保存最后的section
        if current_section:
            sections.append(current_section)
        
        # 创建幻灯片数据结构
        slides.append({
            'main_title': main_title,
            'content': content_lines,
            'sections': sections
        })
    

    return slides
