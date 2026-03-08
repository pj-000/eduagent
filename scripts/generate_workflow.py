#!/usr/bin/env python3
"""
教育功能工作流生成器
基于 EvoAgentX 官方 API 实现（参考 GitHub quickstart 文档）。

主路径：WorkFlowGenerator.generate_workflow(goal)  — 官方推荐方式
回退路径：LLM 直接生成 + SequentialWorkFlowGraph  — 当 WorkFlowGenerator 失败时

参考文档：
  https://github.com/EvoAgentX/EvoAgentX/blob/main/docs/zh/quickstart.md
  https://github.com/EvoAgentX/EvoAgentX/blob/main/examples/sequential_workflow.py
"""

import os
import re
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# 加载项目根目录的 .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from evoagentx.models import AliyunLLMConfig, AliyunLLM
from evoagentx.workflow import WorkFlowGenerator, WorkFlowGraph
from evoagentx.workflow.workflow_graph import SequentialWorkFlowGraph

# ────────────────────────────────────────────────
# Monkey-patch: 修复 EvoAgentX _parse_json_content
# 原始实现只取第一个 JSON 块，当 qwen-plus 输出多个 JSON 块时
# （如 ## Thought 中的 JSON 和 ## Selected or Generated Agents 中的 JSON），
# 会取到错误的 JSON 导致 AgentGenerationOutput 验证失败。
# 修复后：在所有 JSON 块中搜索包含目标类所有必需字段的 JSON。
# ────────────────────────────────────────────────
import yaml
from evoagentx.models.base_model import LLMOutputParser
from evoagentx.core.module_utils import parse_json_from_text

_original_parse_json_content = LLMOutputParser._parse_json_content

@classmethod
def _patched_parse_json_content(cls, content: str, **kwargs) -> dict:
    """
    修复版 _parse_json_content：在多个 JSON 块中优先选择
    包含当前类所有必需字段的 JSON（而非仅取第一个）。
    """
    extracted_json_list = parse_json_from_text(content)
    if not extracted_json_list:
        raise ValueError(f"Generated text does not contain JSON:\n{content[:500]}")

    # 获取当前解析目标类的所有必需字段名
    required_fields = set(cls.get_attrs())

    # 优先搜索：包含所有必需字段的 JSON
    for json_str in extracted_json_list:
        try:
            data = yaml.safe_load(json_str)
            if isinstance(data, dict) and required_fields.issubset(data.keys()):
                return data
        except Exception:
            continue

    # 次优搜索：包含至少一个必需字段的 JSON（部分匹配）
    for json_str in extracted_json_list:
        try:
            data = yaml.safe_load(json_str)
            if isinstance(data, dict) and required_fields.intersection(data.keys()):
                return data
        except Exception:
            continue

    # 回退：使用原始逻辑（取第一个 JSON）
    return _original_parse_json_content.__func__(cls, content=content, **kwargs)

LLMOutputParser._parse_json_content = _patched_parse_json_content
# ────────────────────────────────────────────────


def build_llm_config() -> AliyunLLMConfig:
    """构建阿里云 LLM 配置"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("错误：请在 .env 文件中设置 DASHSCOPE_API_KEY")
        sys.exit(1)

    return AliyunLLMConfig(
        model="qwen-plus",
        aliyun_api_key=api_key,
        stream=False,
        output_response=True,
    )


def build_llm(config: AliyunLLMConfig = None) -> AliyunLLM:
    """构建阿里云 LLM 实例"""
    if config is None:
        config = build_llm_config()
    return AliyunLLM(config)


def extract_json_from_text(text: str) -> dict | None:
    """
    从 LLM 输出文本中稳健地提取 JSON 对象。
    策略：
    1. 优先提取 ```json ... ``` 代码块
    2. 如果有多个代码块，找包含 "tasks" 键的那个
    3. 最后回退到正则匹配最外层 { ... }
    """
    # 提取所有 ```json ... ``` 代码块
    fenced_blocks = re.findall(r'```(?:json)?\s*\n(.*?)\n\s*```', text, re.DOTALL)

    # 在所有代码块中找包含 tasks 键的 JSON
    for block in fenced_blocks:
        try:
            data = json.loads(block.strip())
            if isinstance(data, dict) and "tasks" in data:
                return data
        except json.JSONDecodeError:
            continue

    # 如果代码块中没找到，尝试找所有匹配的 JSON（回退）
    for block in fenced_blocks:
        try:
            data = json.loads(block.strip())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue

    # 最后回退：用正则匹配最外层大括号
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


WORKFLOW_GENERATION_PROMPT = """你是一位资深教育 AI 系统架构师。请根据以下目标和参考资料，设计一个教育功能实施工作流。

## 设计目标

{goal}

## 输出要求

请输出一个 JSON 对象，包含以下字段：
- "goal": 字符串，工作流的整体目标概述（一句话）
- "tasks": 数组，包含 3-6 个按执行顺序排列的子任务

每个子任务是一个 JSON 对象，必须包含：
- "name": 英文蛇形命名（如 "analyze_requirements"），不可重复
- "description": 中文描述（一句话说明这步做什么）
- "inputs": 输入参数数组，每个元素是 {{"name": "参数名", "type": "string", "required": true, "description": "描述"}}
- "outputs": 输出参数数组，格式同 inputs
- "prompt": 中文 Prompt，指导 Agent 执行该步骤。必须包含输入参数的占位符 {{参数名}}。Prompt 中描述角色定位、任务要求、输出格式。

## 重要约束

1. 相邻任务的输出参数名必须与下一个任务的输入参数名匹配（数据流传递）
2. 第一个任务的输入是用户提供的外部数据
3. 最后一个任务的输出应是最终交付物
4. prompt 中用 {{参数名}} 引用输入参数
5. 不要输出其他内容，只输出一个 JSON 代码块

## 输出示例

```json
{{
  "goal": "基于教学大纲自动生成分层练习题",
  "tasks": [
    {{
      "name": "parse_syllabus",
      "description": "解析教学大纲，提取知识点和难度层级",
      "inputs": [{{"name": "syllabus_text", "type": "string", "required": true, "description": "教学大纲原文"}}],
      "outputs": [{{"name": "knowledge_map", "type": "string", "required": true, "description": "结构化知识点及难度标注"}}],
      "prompt": "你是课程分析专家。请解析以下教学大纲，提取所有知识点并标注难度层级。\\n\\n教学大纲：\\n{{syllabus_text}}\\n\\n请输出结构化的知识点列表。"
    }},
    {{
      "name": "generate_exercises",
      "description": "根据知识点生成分层练习题",
      "inputs": [{{"name": "knowledge_map", "type": "string", "required": true, "description": "结构化知识点"}}],
      "outputs": [{{"name": "exercise_set", "type": "string", "required": true, "description": "分层练习题集合"}}],
      "prompt": "你是资深出题专家。根据以下知识点，为每个知识点生成基础、提高、挑战三个难度的练习题。\\n\\n知识点：\\n{{knowledge_map}}\\n\\n请输出按难度分层的练习题。"
    }}
  ]
}}
```

请严格按照上述格式输出，只输出一个 JSON 代码块。"""


def load_latest_search_result() -> tuple[str, Path]:
    """加载最新的搜索结果 Markdown 文件"""
    search_dir = PROJECT_ROOT / "data" / "search_results"
    if not search_dir.exists():
        print("错误：未找到搜索结果目录 data/search_results/")
        print("请先运行功能一（python scripts/search_edu.py）进行搜索")
        sys.exit(1)

    md_files = sorted(search_dir.glob("explore_*.md"), reverse=True)
    if not md_files:
        print("错误：未找到搜索结果文件")
        print("请先运行功能一（python scripts/search_edu.py）进行搜索")
        sys.exit(1)

    latest = md_files[0]
    content = latest.read_text(encoding="utf-8")
    return content, latest


def load_search_result_by_path(path: str) -> str:
    """加载指定路径的搜索结果"""
    p = Path(path)
    if not p.exists():
        print(f"错误：文件不存在 {path}")
        sys.exit(1)

    if p.suffix == ".json":
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("result", "")
    else:
        return p.read_text(encoding="utf-8")


def summarize_search_result(llm: AliyunLLM, search_result: str) -> str:
    """
    用 LLM 将长搜索结果摘要为简洁的功能点列表。
    WorkFlowGenerator 的 goal 需要保持简洁（<500字），否则内部 JSON 解析容易出错。
    """
    MAX_INPUT_CHARS = 4000
    if len(search_result) > MAX_INPUT_CHARS:
        search_result = search_result[:MAX_INPUT_CHARS]

    prompt = f"""请将以下教育领域创新功能探索报告精炼为一段 200 字以内的功能摘要。
只保留核心功能点名称和一句话描述，去掉所有细节。

报告内容：
{search_result}

请直接输出摘要文本，不要加标题或格式。"""

    response = llm.generate(prompt=prompt)
    if hasattr(response, "content"):
        return response.content
    elif isinstance(response, str):
        return response
    return str(response)


def _fix_prompt_placeholders(task: dict) -> None:
    """
    确保 task 的 prompt 中包含所有 inputs 的 {name} 占位符。
    CustomizeAgent.validate_data() 会校验这一点，缺失会 raise KeyError。
    """
    prompt = task.get("prompt", "")
    inputs = task.get("inputs", [])
    for inp in inputs:
        name = inp.get("name", "")
        if name and f"{{{name}}}" not in prompt:
            desc = inp.get("description", name)
            prompt += f"\n\n{desc}：\n{{{name}}}"
    task["prompt"] = prompt


def build_goal(search_result: str, feature_index: int | None = None, summary: str = None) -> str:
    """
    基于搜索摘要构建简洁的工作流目标描述。
    目标保持 500 字以内，以确保 WorkFlowGenerator 内部 JSON 解析正确。
    """
    context = summary or search_result[:500]

    if feature_index is not None:
        goal = (
            f"Design a complete implementation workflow for feature #{feature_index} "
            f"from the following education innovation research. "
            f"The workflow should include: requirements analysis, technical research, "
            f"solution design, and prototype development. "
            f"It must integrate with existing EdTech platform capabilities "
            f"(lesson plan generation, exam generation, PPT generation, evaluation). "
            f"\n\nFeature context: {context}"
        )
    else:
        goal = (
            f"Design a comprehensive evaluation and prioritization workflow "
            f"for education innovation features. The workflow should include: "
            f"feasibility analysis, technical complexity assessment, user value scoring, "
            f"priority ranking, and roadmap generation. "
            f"Consider integration with existing platform capabilities "
            f"(lesson plan generation, exam generation, PPT generation, evaluation). "
            f"\n\nFeatures to evaluate: {context}"
        )

    return goal


def generate_workflow_official(llm: AliyunLLM, goal: str, retry: int = 3) -> WorkFlowGraph:
    """
    官方推荐方式：使用 WorkFlowGenerator.generate_workflow(goal)
    参考：https://github.com/EvoAgentX/EvoAgentX/blob/main/docs/zh/quickstart.md
    """
    wf_generator = WorkFlowGenerator(llm=llm)
    workflow_graph = wf_generator.generate_workflow(goal=goal, retry=retry)
    return workflow_graph


def generate_workflow_fallback(llm: AliyunLLM, goal: str, retry: int = 3) -> SequentialWorkFlowGraph:
    """
    回退方式：LLM 直接生成任务列表 JSON + SequentialWorkFlowGraph
    参考：https://github.com/EvoAgentX/EvoAgentX/blob/main/examples/sequential_workflow.py

    当 WorkFlowGenerator 内部的 AgentGenerator JSON 解析失败时使用。
    """
    prompt = WORKFLOW_GENERATION_PROMPT.format(goal=goal)

    for attempt in range(1, retry + 1):
        print(f"  尝试 {attempt}/{retry} ...")
        try:
            response = llm.generate(prompt=prompt)

            # 从 response 中提取文本
            if hasattr(response, "content"):
                text = response.content
            elif hasattr(response, "text"):
                text = response.text
            elif isinstance(response, str):
                text = response
            else:
                text = str(response)

            # 提取 JSON
            data = extract_json_from_text(text)
            if data is None:
                print(f"  ⚠ 第 {attempt} 次尝试：未能从 LLM 输出中提取 JSON")
                if attempt == retry:
                    print("  LLM 原始输出片段：")
                    print(text[:500])
                continue

            # 验证必要字段
            workflow_goal = data.get("goal", goal)
            tasks = data.get("tasks", [])

            if not tasks:
                print(f"  ⚠ 第 {attempt} 次尝试：tasks 为空")
                continue

            # 验证每个 task 的必要字段
            valid = True
            for i, task in enumerate(tasks):
                missing = [k for k in ("name", "description", "prompt") if k not in task]
                if missing:
                    print(f"  ⚠ 任务 {i+1} 缺少字段：{missing}")
                    valid = False
                    break
                # 确保有 inputs 和 outputs（可以为空列表）
                task.setdefault("inputs", [])
                task.setdefault("outputs", [])
                # 修复 prompt 中缺失的输入参数占位符
                # CustomizeAgent.validate_data() 要求 prompt 中包含所有 inputs 的 {name}
                _fix_prompt_placeholders(task)
            if not valid:
                continue

            # 构建 SequentialWorkFlowGraph
            workflow_graph = SequentialWorkFlowGraph(goal=workflow_goal, tasks=tasks)
            print(f"  ✓ 第 {attempt} 次尝试成功，生成 {len(tasks)} 个子任务")
            return workflow_graph

        except Exception as e:
            print(f"  ⚠ 第 {attempt} 次尝试出错：{e}")
            if attempt == retry:
                raise

    raise RuntimeError(f"工作流生成失败，已重试 {retry} 次")


def save_workflow(workflow_graph, goal: str, source_file: str) -> tuple[Path, Path]:
    """保存生成的工作流"""
    save_dir = PROJECT_ROOT / "workflows"
    save_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"workflow_{timestamp}.json"
    save_path = save_dir / filename

    # 序列化 WorkFlowGraph (使用 get_config 避免 MultiDiGraph 不可序列化)
    try:
        workflow_data = workflow_graph.get_config()
    except Exception:
        # 回退：手动构建可序列化的 dict
        workflow_data = {
            "class_name": "WorkFlowGraph",
            "goal": workflow_graph.goal,
            "nodes": [],
            "edges": [],
        }
        for node in workflow_graph.nodes:
            node_dict = {
                "name": node.name,
                "description": node.description,
                "inputs": [{"name": p.name, "type": p.type, "description": p.description, "required": p.required} for p in (node.inputs or [])],
                "outputs": [{"name": p.name, "type": p.type, "description": p.description, "required": p.required} for p in (node.outputs or [])],
                "agents": [],
            }
            for agent in (node.agents or []):
                node_dict["agents"].append({
                    "name": agent.name,
                    "description": agent.description,
                    "prompt": agent.prompt if hasattr(agent, "prompt") else "",
                })
            workflow_data["nodes"].append(node_dict)
        for edge in workflow_graph.edges:
            workflow_data["edges"].append({
                "source": edge.source,
                "target": edge.target,
            })
    workflow_data["_metadata"] = {
        "generated_at": datetime.now().isoformat(),
        "source_search_result": source_file,
        "goal_summary": goal[:200],
    }

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(workflow_data, f, ensure_ascii=False, indent=2)

    # 同时保存可读的 Markdown 描述
    md_path = save_path.with_suffix(".md")
    md_lines = [
        f"# 工作流设计报告\n",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 数据来源：{source_file}\n",
        f"## 工作流目标\n",
        f"{workflow_graph.goal}\n",
        f"## 子任务列表\n",
    ]
    for i, node in enumerate(workflow_graph.nodes, 1):
        md_lines.append(f"### {i}. {node.name}\n")
        md_lines.append(f"**描述**：{node.description}\n")
        if node.inputs:
            md_lines.append("**输入**：")
            for inp in node.inputs:
                md_lines.append(f"- `{inp.name}` ({inp.type}): {inp.description}")
            md_lines.append("")
        if node.outputs:
            md_lines.append("**输出**：")
            for out in node.outputs:
                md_lines.append(f"- `{out.name}` ({out.type}): {out.description}")
            md_lines.append("")
        if node.agents:
            agent = node.agents[0]
            # agent 可能是 dict 或 Pydantic 对象
            prompt_text = agent.get("prompt", "") if isinstance(agent, dict) else getattr(agent, "prompt", "")
            if prompt_text:
                md_lines.append(f"**Agent Prompt**：\n")
                md_lines.append(f"```\n{prompt_text[:300]}{'...' if len(prompt_text) > 300 else ''}\n```\n")
        md_lines.append("---\n")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    return save_path, md_path


def main():
    parser = argparse.ArgumentParser(
        description="教育功能工作流生成器 — 基于 EvoAgentX 官方 API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 基于最新搜索结果生成综合评估工作流（默认）
  python scripts/generate_workflow.py

  # 针对搜索结果中的第 1 个功能点生成实施工作流
  python scripts/generate_workflow.py --feature 1

  # 指定搜索结果文件
  python scripts/generate_workflow.py --input data/search_results/explore_20260305_141113.md

  # 自定义工作流目标
  python scripts/generate_workflow.py --goal "设计一个 AI 自适应学习系统的完整开发工作流"

  # 强制使用 SequentialWorkFlowGraph（跳过 WorkFlowGenerator）
  python scripts/generate_workflow.py --mode sequential --goal "..."
        """,
    )
    parser.add_argument(
        "--input", "-i", default=None,
        help="指定搜索结果文件路径（默认使用最新的搜索结果）",
    )
    parser.add_argument(
        "--feature", "-f", type=int, default=None,
        help="针对搜索结果中的第 N 个功能点生成工作流（如 --feature 1）",
    )
    parser.add_argument(
        "--goal", "-g", default=None,
        help="自定义工作流目标（覆盖基于搜索结果的自动生成）",
    )
    parser.add_argument(
        "--retry", "-r", type=int, default=3,
        help="LLM 生成重试次数（默认 3）",
    )
    parser.add_argument(
        "--mode", "-m", choices=["auto", "sequential"],
        default="auto",
        help="生成模式：auto=WorkFlowGenerator+回退（默认）, sequential=直接用 SequentialWorkFlowGraph",
    )
    args = parser.parse_args()

    # 构建 LLM
    llm_config = build_llm_config()
    llm = build_llm(llm_config)

    # 加载搜索结果并构建 goal
    if args.goal:
        search_result = ""
        source_file = "custom_goal"
        goal = args.goal
    elif args.input:
        search_result = load_search_result_by_path(args.input)
        source_file = args.input
        print("📝 正在摘要搜索结果...")
        summary = summarize_search_result(llm, search_result)
        goal = build_goal(search_result, args.feature, summary=summary)
    else:
        search_result, source_path = load_latest_search_result()
        source_file = str(source_path.name)
        print("📝 正在摘要搜索结果...")
        summary = summarize_search_result(llm, search_result)
        goal = build_goal(search_result, args.feature, summary=summary)

    # 生成工作流
    print("🔧 教育功能工作流生成器启动")
    print(f"📄 数据来源：{source_file}")
    if args.feature:
        print(f"🎯 聚焦功能点：第 {args.feature} 个")
    print(f"📐 生成模式：{args.mode}")
    print("-" * 60)

    workflow_graph = None

    if args.mode == "auto":
        # 主路径：官方 WorkFlowGenerator（retry=1 快速失败，避免长时间等待）
        print("⏳ [主路径] 使用 WorkFlowGenerator 生成工作流...")
        try:
            workflow_graph = generate_workflow_official(llm, goal, retry=1)
            print(f"  ✓ WorkFlowGenerator 成功，生成 {len(workflow_graph.nodes)} 个子任务")
        except Exception as e:
            print(f"  ⚠ WorkFlowGenerator 失败：{type(e).__name__}: {str(e)[:200]}")
            print("  → 切换到回退路径 (SequentialWorkFlowGraph)...")

    if workflow_graph is None:
        # 回退路径：SequentialWorkFlowGraph
        print("⏳ [回退路径] 使用 SequentialWorkFlowGraph 生成工作流...")
        workflow_graph = generate_workflow_fallback(llm, goal, retry=args.retry)

    # 保存工作流
    json_path, md_path = save_workflow(workflow_graph, goal, source_file)

    print("\n✅ 工作流生成完成！")
    print(f"📋 JSON 工作流：{json_path}")
    print(f"📄 Markdown 描述：{md_path}")

    # 输出工作流概览
    print("\n" + "=" * 60)
    print("工作流概览")
    print("=" * 60)
    print(f"目标：{workflow_graph.goal[:200]}")
    print(f"子任务数：{len(workflow_graph.nodes)}")
    print(f"依赖边数：{len(workflow_graph.edges)}")
    print("\n子任务列表：")
    for i, node in enumerate(workflow_graph.nodes, 1):
        desc = node.description[:80] if node.description else "(无描述)"
        print(f"  {i}. {node.name} — {desc}")


if __name__ == "__main__":
    main()
