"""
内容元素提取
从Markdown内容中提取要点、代码块、表格等元素
"""

import re
from config import *


def extract_content_elements_enhanced(content_lines):
    """
    增强版内容元素提取，支持内容长度统计和保持原始格式
    """
    elements = {
        'bullets': [],
        'numbered_lists': [],
        'tables': [],
        'code_blocks': [],
        'quotes': [],
        'plain_text': [],
        'total_length': 0,  # 总文本长度
        'ordered': []  # 按出现顺序记录所有元素类型
    }
    
    in_code_block = False
    in_table = False
    current_code = []
    current_table = []
    
    for line_index, original_line in enumerate(content_lines):
        # 保留原始行（包括前导空格）
        if not original_line.strip():
            continue
            
        # 统计文本长度
        elements['total_length'] += len(original_line)
        
        # 代码块处理（保持原始缩进）- 支持三个和四个反引号
        code_marker_match = re.match(r'^```+', original_line.strip())
        if code_marker_match:
            if in_code_block:
                # 结束代码块，保存代码内容（保持原始缩进）
                code_content = '\n'.join(current_code)
                elements['code_blocks'].append(code_content)
                elements['total_length'] += len(code_content)
                # 记录到顺序数组
                elements['ordered'].append(('code_blocks', len(elements['code_blocks']) - 1, code_content))
                current_code = []
                in_code_block = False
            else:
                in_code_block = True
            continue
            
        if in_code_block:
            # 保存原始行，包括缩进，并还原#注释
            restored_line = original_line.replace('§CODE_COMMENT§', '#')
            current_code.append(restored_line)
            continue
            
        # 处理非代码行（去除前导空格用于其他处理）
        line = original_line.strip()
        
        # 表格（至少2个"|"且以"|"开头或含列分隔" | "）
        if line.count('|') >= 2 and (line.strip().startswith('|') or ' | ' in line) and not in_table:
            in_table = True
            current_table = [line]
            continue
        elif in_table and (line.strip().startswith('|') or ' | ' in line):
            current_table.append(line)
            continue
        elif in_table and line.count('|') == 0:
            table_content = '\n'.join(current_table)
            elements['tables'].append(table_content)
            elements['total_length'] += len(table_content)
            # 记录到顺序数组
            elements['ordered'].append(('tables', len(elements['tables']) - 1, table_content))
            current_table = []
            in_table = False
            
        # 引用
        if line.startswith('>'):
            quote_text = line[1:].strip()
            elements['quotes'].append(quote_text)
            # 记录到顺序数组
            elements['ordered'].append(('quotes', len(elements['quotes']) - 1, quote_text))
            continue
            
        # 列表项 - 增强处理：支持嵌套列表和缩进内容
        bullet_match = re.match(r'^(\s*)[-*•]\s+(.+)', line)
        if bullet_match and bullet_match.group(2).strip():  # 确保有内容
            indentation = bullet_match.group(1)  # 保存缩进
            bullet_text = bullet_match.group(2)
            
            # 保留粗体标记但不删除，用于后续处理
            bullet_text_clean = re.sub(r'\*\*(.*?)\*\*', r'\1', bullet_text)
            bullet_text_clean = re.sub(r'\*(.*?)\*', r'\1', bullet_text_clean)
            
            # 检查是否有后续的嵌套内容（包括子列表项和数字列表）
            combined_bullet = bullet_text  # 保留原始格式，包括**粗体**
            nested_content = []
            
            # 向前查看后续行，收集嵌套内容
            for next_idx in range(line_index + 1, len(content_lines)):
                if next_idx >= len(content_lines):
                    break
                    
                next_line = content_lines[next_idx]
                if not next_line.strip():
                    continue
                
                # 检查是否是更深层次的缩进内容
                next_indentation = len(next_line) - len(next_line.lstrip())
                current_indentation = len(indentation)
                
                # 如果缩进更深，说明是子内容
                if next_indentation > current_indentation:
                    # 子列表项
                    sub_bullet_match = re.match(r'^(\s+)[-*•]\s+(.+)', next_line)
                    if sub_bullet_match:
                        sub_text = sub_bullet_match.group(2)
                        nested_content.append(f"  - {sub_text}")
                        # 标记已处理
                        if not hasattr(elements, '_processed_indices'):
                            elements['_processed_indices'] = set()
                        elements['_processed_indices'].add(next_idx)
                        continue
                    
                    # 数字列表项
                    numbered_match = re.match(r'^(\s+)\d+[\.、]\s+(.+)', next_line)
                    if numbered_match:
                        numbered_text = numbered_match.group(2)
                        nested_content.append(f"  {len(nested_content)+1}. {numbered_text}")
                        # 标记已处理
                        if not hasattr(elements, '_processed_indices'):
                            elements['_processed_indices'] = set()
                        elements['_processed_indices'].add(next_idx)
                        continue
                        
                    # 其他缩进内容
                    if next_line.strip() and not next_line.strip().startswith('#'):
                        nested_content.append(f"  {next_line.strip()}")
                        # 标记已处理
                        if not hasattr(elements, '_processed_indices'):
                            elements['_processed_indices'] = set()
                        elements['_processed_indices'].add(next_idx)
                        continue
                else:
                    # 缩进相同或更少，停止查找嵌套内容
                    break
            
            # 合并嵌套内容
            if nested_content:
                combined_bullet += "\n" + "\n".join(nested_content)
            
            elements['bullets'].append(combined_bullet)
            # 记录到顺序数组
            elements['ordered'].append(('bullets', len(elements['bullets']) - 1, combined_bullet))
            continue
            
        # 检查是否已经被处理过了
        if hasattr(elements, '_processed_indices') and line_index in elements['_processed_indices']:
            continue
            
        # 数字列表 - 增强处理：支持嵌套和缩进
        numbered_match = re.match(r'^(\s*)\d+[\.、]\s+(.+)', line)
        if numbered_match:
            indentation = numbered_match.group(1)
            numbered_text = numbered_match.group(2)
            
            # 保留原始格式，包括粗体标记
            elements['numbered_lists'].append(numbered_text)
            # 记录到顺序数组
            elements['ordered'].append(('numbered_lists', len(elements['numbered_lists']) - 1, numbered_text))
            continue
            
        # 普通文本 - 保留粗体标记信息，但过滤掉单独的"-"或空白行
        if line and not line.startswith('#') and line.strip() != '-':  # 排除标题行和单独的"-"
            elements['plain_text'].append(line)  # 保留原始格式，包括**粗体**标记
            # 记录到顺序数组
            elements['ordered'].append(('plain_text', len(elements['plain_text']) - 1, line))
    
    # 处理最后的表格
    if current_table:
        table_content = '\n'.join(current_table)
        elements['tables'].append(table_content)
        elements['total_length'] += len(table_content)
        # 记录到顺序数组
        elements['ordered'].append(('tables', len(elements['tables']) - 1, table_content))
    
    return elements


def split_content_by_length(elements):
    """
    根据内容长度和要点数量分割内容
    修复：确保每个代码块都能被正确处理
    """
    chunks = []
    current_chunk = {
        'bullets': [],
        'numbered_lists': [],
        'tables': [],
        'code_blocks': [],
        'quotes': [],
        'plain_text': [],
        'total_length': 0
    }
    
    # 优先处理特殊内容（表格、代码、引用）
    # 修复：每个代码块都单独创建一页，避免多个代码块被合并
    for special_type in ['tables', 'code_blocks', 'quotes']:
        for item in elements[special_type]:
            if special_type == 'code_blocks' or len(item) > MAX_TEXT_LENGTH * 0.8:  # 代码块总是独立成页
                if current_chunk['total_length'] > 0:
                    chunks.append(current_chunk.copy())
                    current_chunk = {k: [] for k in current_chunk.keys()}
                    current_chunk['total_length'] = 0
                
                chunks.append({
                    **{k: [] for k in current_chunk.keys()},
                    special_type: [item],
                    'total_length': len(item)
                })
            else:
                current_chunk[special_type].append(item)
                current_chunk['total_length'] += len(item)
    
    # 处理要点和文本
    all_points = []
    for bullet in elements['bullets']:
        all_points.append(('bullet', bullet))
    for numbered in elements['numbered_lists']:
        all_points.append(('numbered', numbered))
    for text in elements['plain_text']:
        all_points.append(('text', text))
    
    for point_type, content in all_points:
        # 检查是否需要分页
        if (current_chunk['total_length'] + len(content) > MAX_TEXT_LENGTH or
            len(current_chunk['bullets']) + len(current_chunk['numbered_lists']) >= MAX_BULLETS_PER_SLIDE):
            
            if current_chunk['total_length'] > 0:
                chunks.append(current_chunk.copy())
                current_chunk = {k: [] for k in current_chunk.keys()}
                current_chunk['total_length'] = 0
        
        # 添加内容
        if point_type == 'bullet':
            current_chunk['bullets'].append(content)
        elif point_type == 'numbered':
            current_chunk['numbered_lists'].append(content)
        else:
            current_chunk['plain_text'].append(content)
        
        current_chunk['total_length'] += len(content)
    
    # 添加最后一块
    if current_chunk['total_length'] > 0:
        chunks.append(current_chunk)
    
    return chunks if chunks else [current_chunk]


def split_content_by_order(elements):
    """
    按照内容的原始顺序分割内容，保持MD文件中的顺序
    """
    if 'ordered' not in elements or not elements['ordered']:
        # 如果没有顺序信息，回退到原来的分割方式
        return split_content_by_length(elements)
    
    def make_empty_chunk():
        return {
            'bullets': [],
            'numbered_lists': [],
            'tables': [],
            'code_blocks': [],
            'quotes': [],
            'plain_text': [],
            'total_length': 0,
            'ordered': []
        }

    def chunk_has_content(chunk):
        return (
            chunk['total_length'] > 0 or
            any(len(chunk[key]) > 0 for key in ['bullets', 'numbered_lists', 'tables', 'code_blocks', 'quotes', 'plain_text'])
        )

    def append_chunk_if_needed(chunk):
        if chunk_has_content(chunk):
            chunk_copy = {
                'bullets': chunk['bullets'][:],
                'numbered_lists': chunk['numbered_lists'][:],
                'tables': chunk['tables'][:],
                'code_blocks': chunk['code_blocks'][:],
                'quotes': chunk['quotes'][:],
                'plain_text': chunk['plain_text'][:],
                'ordered': chunk['ordered'][:],
                'total_length': chunk['total_length']
            }
            chunks.append(chunk_copy)

    chunks = []
    current_chunk = make_empty_chunk()
    
    for content_type, index, content in elements['ordered']:
        # 检查是否需要分页（基于长度或要点数量）
        content_length = len(content)
        current_bullets_count = len(current_chunk['bullets']) + len(current_chunk['numbered_lists'])
        has_existing_content = chunk_has_content(current_chunk)

        # 代码块始终独立成页，避免与其他内容混排
        if content_type == 'code_blocks':
            append_chunk_if_needed(current_chunk)
            current_chunk = make_empty_chunk()

            code_chunk = make_empty_chunk()
            code_chunk['code_blocks'].append(content)
            code_chunk['total_length'] = content_length
            code_chunk['ordered'].append((content_type, 0, content))
            chunks.append(code_chunk)
            continue
        
        # 对于非代码块内容，按原来的逻辑判断是否需要分页
        needs_new_page = False
        if ((current_chunk['total_length'] + content_length > MAX_TEXT_LENGTH) or
            (current_bullets_count >= MAX_BULLETS_PER_SLIDE)) and current_chunk['total_length'] > 0:
            needs_new_page = True
        
        if needs_new_page and has_existing_content:
            # 保存当前chunk并开始新的
            append_chunk_if_needed(current_chunk)
            current_chunk = make_empty_chunk()
        
        # 添加内容到当前chunk
        current_chunk[content_type].append(content)
        current_chunk['total_length'] += content_length
        current_chunk['ordered'].append((content_type, len(current_chunk[content_type]) - 1, content))
    
    # 添加最后一个chunk（如果有内容）
    append_chunk_if_needed(current_chunk)

    if not chunks:
        return [make_empty_chunk()]
    
    return chunks
