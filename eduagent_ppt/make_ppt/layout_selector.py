"""
幻灯片布局选择器
根据内容类型智能选择最佳幻灯片布局
"""

import random
from config import *
from pptx import Presentation

prs = Presentation(TMPL_FILE)
layout_map = {ly.name: ly for ly in prs.slide_layouts}

def choose_layout_enhanced(elements, is_toc=False, is_title_page=False):
    """
    增强版版式选择，支持随机选择相似版式，添加封面页支持
    """
    available_layouts = list(layout_map.keys())
    
    # 封面页优先
    if is_title_page:
        return layout_map.get('Title page', layout_map.get('TitleOnly', list(layout_map.values())[0]))
    
    # 目录页优先
    if is_toc:
        return layout_map.get('TOC', layout_map.get('TitleOnly', list(layout_map.values())[0]))    # 特殊类型优先 - 智能代码块版式选择
    if elements['code_blocks']:
        # 检查是否同时包含其他重要内容（要点、文本等）
        has_bullets = len(elements['bullets']) > 0
        has_text = len(elements['plain_text']) > 0
        has_numbered = len(elements['numbered_lists']) > 0
        
        # 如果同时包含要点或其他文本内容，优先考虑混合版式
        if has_bullets or has_text or has_numbered:
            total_other_content = len(elements['bullets']) + len(elements['plain_text']) + len(elements['numbered_lists'])
            code_content = elements['code_blocks'][0]
            code_lines = code_content.split('\n')
            code_line_count = len(code_lines)
            
            print(f"  混合内容检测: {total_other_content} 个非代码项, {code_line_count} 行代码")
            
            # 如果其他内容较多，或代码较短，优先使用普通版式
            if total_other_content >= 3 or code_line_count <= 10:
                print(f"  选择混合版式: 优先显示要点内容，代码作为补充")
                # 继续执行后续的版式选择逻辑，而不是直接返回代码版式
            else:
                # 代码内容占主导，使用代码版式
                if code_line_count > CODE_LINES_THRESHOLD:
                    chosen_layout = layout_map.get('CodeSlide2', layout_map.get('CodeSlide', list(layout_map.values())[0]))
                    print(f"  选择代码版式: CodeSlide2 (代码行数 > {CODE_LINES_THRESHOLD})")
                else:
                    chosen_layout = layout_map.get('CodeSlide1', layout_map.get('CodeSlide', list(layout_map.values())[0]))
                    print(f"  选择代码版式: CodeSlide1 (代码行数 <= {CODE_LINES_THRESHOLD})")
                return chosen_layout
        else:
            # 纯代码内容，使用代码版式
            code_content = elements['code_blocks'][0]
            code_lines = code_content.split('\n')
            line_count = len(code_lines)
            print(f"  纯代码块行数: {line_count}")
            
            if line_count > CODE_LINES_THRESHOLD:
                chosen_layout = layout_map.get('CodeSlide2', layout_map.get('CodeSlide', list(layout_map.values())[0]))
                print(f"  选择代码版式: CodeSlide2 (代码行数 > {CODE_LINES_THRESHOLD})")
            else:
                chosen_layout = layout_map.get('CodeSlide1', layout_map.get('CodeSlide', list(layout_map.values())[0]))
                print(f"  选择代码版式: CodeSlide1 (代码行数 <= {CODE_LINES_THRESHOLD})")
            return chosen_layout
    
    if elements['tables']:
        return layout_map.get('TableSlide', list(layout_map.values())[0])
    
    if elements['quotes']:
        return layout_map.get('QuoteSlide', list(layout_map.values())[0])
    
    # 检查图片建议
    has_image_suggestion = any('配图建议' in text or '图' in text for text in elements['plain_text'])
    if has_image_suggestion:
        return layout_map.get('ImageLeftTextRight', list(layout_map.values())[0])
      # 根据要点数量选择
    total_points = len(elements['bullets']) + len(elements['numbered_lists'])
    
    # 智能调整：如果数字列表项较多但要点较少，可能是嵌套结构
    # 在这种情况下，偏向选择较少要点的版式
    if len(elements['numbered_lists']) >= 3 and len(elements['bullets']) <= 3:
        # 优先按要点数量选择版式，而不是总数
        effective_points = len(elements['bullets'])
        print(f"  检测到嵌套结构: {len(elements['bullets'])} 个要点, {len(elements['numbered_lists'])} 个数字列表")
        print(f"  使用有效要点数: {effective_points} 而不是总数: {total_points}")
        total_points = effective_points
    
    if total_points == 0 and not elements['plain_text']:
        return layout_map.get('TitleOnly', list(layout_map.values())[0])
    
    elif total_points == 1:
        # 随机选择OneBullet版式
        one_bullet_layouts = []
        if 'OneBullet1' in layout_map:
            one_bullet_layouts.append('OneBullet1')
        if 'OneBullet2' in layout_map:
            one_bullet_layouts.append('OneBullet2')
        if 'OneBullet3' in layout_map:
            one_bullet_layouts.append('OneBullet3')
        if 'OneBullet' in layout_map:
            one_bullet_layouts.append('OneBullet')
        if one_bullet_layouts:
            chosen_layout = random.choice(one_bullet_layouts)
            print(f"  随机选择版式: {chosen_layout} (可选: {one_bullet_layouts})")
            return layout_map[chosen_layout]
        else:
            return list(layout_map.values())[0]
    elif total_points == 2:
        # 随机选择TwoBullets版式
        two_bullet_layouts = []
        if 'TwoBullets1' in layout_map:
            two_bullet_layouts.append('TwoBullets1')
        if 'TwoBullets2' in layout_map:
            two_bullet_layouts.append('TwoBullets2')
        if 'TwoBullets3' in layout_map:
            two_bullet_layouts.append('TwoBullets3')
        if 'TwoBullets' in layout_map:
            two_bullet_layouts.append('TwoBullets')
        
        if two_bullet_layouts:
            chosen_layout = random.choice(two_bullet_layouts)
            print(f"  随机选择版式: {chosen_layout} (可选: {two_bullet_layouts})")
            return layout_map[chosen_layout]
        else:
            return list(layout_map.values())[0]
    elif total_points == 3:
        # 随机选择ThreeBullets版式
        three_bullet_layouts = []
        if 'ThreeBullets1' in layout_map:
            three_bullet_layouts.append('ThreeBullets1')
        if 'ThreeBullets2' in layout_map:
            three_bullet_layouts.append('ThreeBullets2')
        if 'ThreeBullets3' in layout_map:
            three_bullet_layouts.append('ThreeBullets3')
        if 'ThreeBullets' in layout_map:
            three_bullet_layouts.append('ThreeBullets')
        
        if three_bullet_layouts:
            chosen_layout = random.choice(three_bullet_layouts)
            print(f"  随机选择版式: {chosen_layout} (可选: {three_bullet_layouts})")
            return layout_map[chosen_layout]
        else:
            return list(layout_map.values())[0]
    elif total_points >= 4:
        # 随机选择FourBullets版式
        four_bullet_layouts = []
        if 'FourBullets1' in layout_map:
            four_bullet_layouts.append('FourBullets1')
        if 'FourBullets2' in layout_map:
            four_bullet_layouts.append('FourBullets2')
        if 'FourBullets3' in layout_map:
            four_bullet_layouts.append('FourBullets3')
        if 'FourBullets' in layout_map:
            four_bullet_layouts.append('FourBullets')
        
        if four_bullet_layouts:
            chosen_layout = random.choice(four_bullet_layouts)
            print(f"  随机选择版式: {chosen_layout} (可选: {four_bullet_layouts})")
            return layout_map[chosen_layout]
        else:
            return list(layout_map.values())[0]
    
    return list(layout_map.values())[0]