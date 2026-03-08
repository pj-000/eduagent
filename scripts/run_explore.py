#!/usr/bin/env python3
"""
教育创新功能探索 - 简化版
直接执行搜索并输出结果
"""
import os
import sys
import json
from datetime import datetime
from pathlib import Path

# 设置项目根目录
PROJECT_ROOT = Path("/Users/sss/directionai/eduagent")
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# 检查 API Key
api_key = os.getenv("DASHSCOPE_API_KEY")
if not api_key:
    print("错误：请设置 DASHSCOPE_API_KEY")
    sys.exit(1)

print("=" * 70)
print("教育创新功能自主探索 Agent 启动")
print("=" * 70)
print(f"API Key 已配置: {api_key[:15]}...")
print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("-" * 70)

# 导入必要的模块
from evoagentx.models import AliyunLLMConfig
from evoagentx.agents import CustomizeAgent
from evoagentx.prompts import StringTemplate
from evoagentx.tools import (
    DDGSSearchToolkit,
    GoogleFreeSearchToolkit,
    WikipediaSearchToolkit,
)

# 项目背景
PROJECT_CONTEXT = """
你所服务的项目是一个「教育 AI 平台」，目前已有以下核心能力：
1. **课程教案生成**：基于 LLM 自动生成结构化教案
2. **试卷/题目生成**：根据知识点和难度自动出题
3. **PPT 课件生成**：自动生成教学用 PPT
4. **教学评估**：对教案、试卷、PPT 进行质量评估
5. **教育数据合成**：生成训练数据用于模型微调

项目技术栈：Python + EvoAgentX 多智能体框架 + 阿里云 Qwen 大模型。
目标用户：K12 教师、教育机构、在线教育平台。
"""

# 探索方向
EXPLORE_HINT = """请广泛探索以下方向（但不限于此）：
- AI 自适应学习与个性化推荐
- 智能批改与自动反馈
- 多模态教学内容生成（视频、动画、互动课件）
- 学习分析与学情诊断
- AI 虚拟教师/助教
- 游戏化学习与激励机制
- 教育领域 RAG 与知识图谱应用
- 协作学习与社交学习
- 无障碍教育与多语言支持"""

# 创建 LLM 配置
llm_config = AliyunLLMConfig(
    model="qwen-plus",
    aliyun_api_key=api_key,
    stream=False,
    output_response=True,
)

# 初始化搜索工具
print("正在初始化搜索工具...")
ddgs_toolkit = DDGSSearchToolkit()
google_toolkit = GoogleFreeSearchToolkit()
wiki_toolkit = WikipediaSearchToolkit()
print("搜索工具初始化完成: DuckDuckGo, Google, Wikipedia")
print("-" * 70)

# 创建 Agent
template = StringTemplate(
    instruction="""你是一个教育科技领域的创新功能探索专家。

## 你的项目背景
{project_context}

## 你的任务

根据上述项目背景和已有能力，你需要**自主决定搜索方向和关键词**，在互联网上搜索教育领域的创新功能点、前沿技术和最佳实践，找到能扩展项目能力的新功能创意。

## 探索方向提示（你可以自主选择和扩展）

{explore_hint}

## 搜索策略

请你自主执行以下搜索流程：

1. **确定搜索主题**：根据项目背景和探索方向，自主规划 3-5 个搜索主题
2. **生成搜索关键词**：为每个主题生成中英文关键词，**必须在关键词中加入"2025"或"2026"或"latest"以确保搜索到最新内容**
3. **多源搜索**：
   - 使用 DuckDuckGo 搜索最新资讯和技术文章
   - 使用 DuckDuckGo 新闻搜索教育行业动态
   - 使用 Google 搜索中文教育内容
   - 使用 Wikipedia 搜索概念性知识
4. **交叉验证**：同一功能点尽量从多个来源验证
5. **筛选提炼**：过滤与项目无关的内容，聚焦可落地的创新功能

## 重要要求

- 搜索的功能点必须与项目现有能力互补或扩展（不要重复已有功能）
- 每个功能点必须有明确的应用场景和用户价值
- **优先搜索 2025-2026 年的最新技术和趋势，忽略 2024 年及更早的过时信息**
- 至少使用 3 种不同的搜索工具""",
    output_instruction="""请输出结构化的创新功能探索报告，严格按照以下格式：

## 探索概览
- 搜索主题：（列出你自主选择的搜索主题）
- 搜索关键词：（列出实际使用的中英文搜索关键词）
- 使用工具：（列出实际调用的搜索工具及次数）

## 创新功能点清单

对每个功能点按以下格式输出：

### 功能 N：[功能名称]
- **功能描述**：一句话概述
- **应用场景**：这个功能解决什么问题
- **目标用户**：谁会使用
- **与项目的关联**：如何与现有能力结合或扩展
- **技术可行性**：实现难度评估（高/中/低）
- **参考来源**：信息来源链接

## 优先级建议
（根据用户价值和技术可行性，给出功能优先级排序建议）

## 参考来源汇总
（列出所有参考链接）""",
)

print("正在创建探索 Agent...")
agent = CustomizeAgent(
    name="EduExploreAgent",
    description="教育创新功能自主探索 Agent",
    prompt_template=template,
    inputs=[
        {
            "name": "project_context",
            "type": "str",
            "description": "项目背景描述",
        },
        {
            "name": "explore_hint",
            "type": "str",
            "description": "探索方向提示",
        },
    ],
    outputs=[
        {
            "name": "explore_report",
            "type": "str",
            "description": "创新功能探索报告",
        },
    ],
    llm_config=llm_config,
    tools=[ddgs_toolkit, google_toolkit, wiki_toolkit],
)

print("Agent 创建完成")
print("-" * 70)
print("开始执行自主探索（预计需要 1-3 分钟）...")
print("=" * 70)
print()

# 执行探索
message = agent(
    inputs={
        "project_context": PROJECT_CONTEXT.strip(),
        "explore_hint": EXPLORE_HINT,
    }
)

result = message.content.explore_report
print(result)

# 保存结果
save_dir = PROJECT_ROOT / "data" / "search_results"
save_dir.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# JSON 格式
json_path = save_dir / f"explore_{timestamp}.json"
save_data = {
    "mode": "autonomous_explore",
    "explore_hint": EXPLORE_HINT[:100],
    "timestamp": datetime.now().isoformat(),
    "result": result,
}
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(save_data, f, ensure_ascii=False, indent=2)

# Markdown 格式
md_path = save_dir / f"explore_{timestamp}.md"
md_content = f"""# 教育创新功能探索报告

> 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 探索方向：全方位自主探索

---

{result}
"""
with open(md_path, "w", encoding="utf-8") as f:
    f.write(md_content)

print()
print("=" * 70)
print("探索完成！")
print(f"JSON 结果：{json_path}")
print(f"Markdown 报告：{md_path}")
print("=" * 70)