#!/usr/bin/env python3
"""
教育功能工作流执行器
基于 EvoAgentX WorkFlow 引擎执行功能二生成的工作流。

功能：加载已生成的 WorkFlowGraph JSON，注册所有 Agent，逐步执行工作流并输出结果。
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# 加载项目根目录的 .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from evoagentx.models import AliyunLLMConfig, AliyunLLM
from evoagentx.workflow import WorkFlowGraph, WorkFlow
from evoagentx.agents import AgentManager


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


def build_llm(config: AliyunLLMConfig) -> AliyunLLM:
    """构建阿里云 LLM 实例"""
    return AliyunLLM(config)


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


def _fix_graph_agent_prompts(graph) -> None:
    """
    修复 WorkFlowGraph 中所有 node 的 agent prompt，
    确保 prompt 包含其 node 所有 input 参数的 {name} 占位符。
    """
    for node in graph.nodes:
        if not node.inputs or not node.agents:
            continue
        for agent in node.agents:
            # agent 可能是 dict 或 Pydantic 对象
            if isinstance(agent, dict):
                prompt = agent.get("prompt", "")
                for inp in node.inputs:
                    inp_name = inp.name if hasattr(inp, "name") else inp.get("name", "")
                    inp_desc = inp.description if hasattr(inp, "description") else inp.get("description", inp_name)
                    if inp_name and f"{{{inp_name}}}" not in prompt:
                        prompt += f"\n\n{inp_desc}：\n{{{inp_name}}}"
                agent["prompt"] = prompt
            else:
                prompt = getattr(agent, "prompt", "")
                for inp in node.inputs:
                    inp_name = inp.name if hasattr(inp, "name") else inp.get("name", "")
                    inp_desc = inp.description if hasattr(inp, "description") else inp.get("description", inp_name)
                    if inp_name and f"{{{inp_name}}}" not in prompt:
                        prompt += f"\n\n{inp_desc}：\n{{{inp_name}}}"
                if hasattr(agent, "prompt"):
                    agent.prompt = prompt


def load_workflow(path: str) -> WorkFlowGraph:
    """
    加载工作流 JSON 文件，构建 WorkFlowGraph。
    支持两种格式：
    1. get_config() 输出的格式（含 class_name 等完整字段）
    2. 手动构建的简化格式
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # 移除 _metadata（我们自己添加的，不属于 WorkFlowGraph schema）
    data.pop("_metadata", None)

    try:
        # 在 from_dict 之前，先修复 tasks/nodes 中的 prompt 占位符
        # 以避免 CustomizeAgent 初始化时验证失败
        if "tasks" in data:
            for task in data["tasks"]:
                _fix_prompt_placeholders(task)
        elif "nodes" in data:
            for node_data in data["nodes"]:
                agents = node_data.get("agents", [])
                inputs = node_data.get("inputs", [])
                if agents and inputs:
                    for agent in agents:
                        if isinstance(agent, dict):
                            prompt = agent.get("prompt", "")
                            for inp in inputs:
                                inp_name = inp.get("name", "")
                                inp_desc = inp.get("description", inp_name)
                                if inp_name and f"{{{inp_name}}}" not in prompt:
                                    prompt += f"\n\n{inp_desc}：\n{{{inp_name}}}"
                            agent["prompt"] = prompt

        # 根据 class_name 判断应该用哪个类来加载
        class_name = data.get("class_name", "")
        if class_name == "SequentialWorkFlowGraph":
            from evoagentx.workflow.workflow_graph import SequentialWorkFlowGraph
            graph = SequentialWorkFlowGraph.from_dict(data)
        else:
            graph = WorkFlowGraph.from_dict(data)
    except Exception as e:
        print(f"⚠ from_dict 失败 ({e})，尝试手动构建...")
        # 回退：手动构建
        from evoagentx.workflow.workflow_graph import SequentialWorkFlowGraph
        goal = data.get("goal", "")

        # 支持 tasks 和 nodes 两种格式
        tasks_data = data.get("tasks", data.get("nodes", []))

        # 把数据转换为 tasks 格式（SequentialWorkFlowGraph 接受的格式）
        tasks = []
        for item in tasks_data:
            # 如果是 node 格式（有 agents），提取 prompt
            agents = item.get("agents", [])
            prompt = item.get("prompt", "")
            if not prompt and agents and isinstance(agents[0], dict):
                prompt = agents[0].get("prompt", "")

            task = {
                "name": item.get("name", ""),
                "description": item.get("description", ""),
                "prompt": prompt or item.get("description", "请完成此任务"),
                "inputs": item.get("inputs", []),
                "outputs": item.get("outputs", []),
            }
            # 清理 inputs/outputs 中可能的 class_name 字段
            for io_list in [task["inputs"], task["outputs"]]:
                for io_item in io_list:
                    io_item.pop("class_name", None)
            # 修复 prompt 中缺失的输入参数占位符
            _fix_prompt_placeholders(task)
            tasks.append(task)

        graph = SequentialWorkFlowGraph(goal=goal, tasks=tasks)

    # 后处理：修复 agents 中 prompt 缺少输入参数占位符的问题
    # CustomizeAgent.validate_data() 要求 prompt 中包含所有 inputs 的 {name}
    _fix_graph_agent_prompts(graph)

    return graph


def find_latest_workflow() -> Path | None:
    """查找最新的工作流 JSON 文件"""
    workflow_dir = PROJECT_ROOT / "workflows"
    if not workflow_dir.exists():
        return None
    json_files = sorted(workflow_dir.glob("workflow_*.json"), reverse=True)
    return json_files[0] if json_files else None


def build_default_inputs(graph: WorkFlowGraph, task_text: str) -> dict[str, str]:
    """
    为统一入口自动构造初始输入，避免每次都走交互式输入。
    默认将自然语言任务填入首节点所需字段；若存在 goal 字段则优先写入 goal。
    """
    if not graph.nodes:
        return {}

    first_node = graph.nodes[0]
    if not first_node.inputs:
        return {}

    auto_inputs = {}
    for param in first_node.inputs:
        param_name = param.name if hasattr(param, "name") else param.get("name", "unknown")
        auto_inputs[param_name] = task_text
    return auto_inputs


def collect_inputs_interactive(graph: WorkFlowGraph) -> dict:
    """
    交互式收集工作流第一个节点的输入参数。
    如果用户不提供，则使用默认占位文本。
    """
    if not graph.nodes:
        return {}

    first_node = graph.nodes[0]
    if not first_node.inputs:
        return {}

    print("\n📝 请为工作流提供初始输入参数：")
    print(f"   (第一个子任务：{first_node.name} — {first_node.description})\n")

    inputs = {}
    for param in first_node.inputs:
        param_name = param.name if hasattr(param, "name") else param.get("name", "unknown")
        param_desc = param.description if hasattr(param, "description") else param.get("description", "")
        param_required = param.required if hasattr(param, "required") else param.get("required", True)

        hint = f"  {param_name}"
        if param_desc:
            hint += f" ({param_desc})"
        if not param_required:
            hint += " [可选，按回车跳过]"
        hint += "："

        value = input(hint).strip()
        if value:
            inputs[param_name] = value
        elif param_required:
            # 使用有意义的默认文本
            inputs[param_name] = f"[请补充 {param_name} 的具体内容]"
            print(f"    → 使用占位文本")

    return inputs


def collect_inputs_from_file(file_path: str) -> dict:
    """从 JSON 文件加载输入参数"""
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


def save_result(output: str, workflow_path: str) -> Path:
    """保存执行结果"""
    results_dir = PROJECT_ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = results_dir / f"result_{timestamp}.md"

    workflow_name = Path(workflow_path).stem

    content = f"""# 工作流执行结果

> 执行时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 工作流文件：{workflow_name}

## 执行输出

{output}
"""
    with open(result_path, "w", encoding="utf-8") as f:
        f.write(content)

    return result_path


def run_workflow_execution(
    workflow_path: str | Path | None = None,
    inputs: dict[str, Any] | None = None,
    inputs_path: str | None = None,
    max_steps: int = 5,
    save: bool = True,
    verbose: bool = True,
) -> dict[str, Any]:
    """以编程方式执行工作流，供统一入口复用。"""
    if workflow_path:
        resolved_workflow_path = Path(workflow_path)
        if not resolved_workflow_path.is_absolute():
            resolved_workflow_path = PROJECT_ROOT / resolved_workflow_path
    else:
        resolved_workflow_path = find_latest_workflow()
        if resolved_workflow_path is None:
            raise FileNotFoundError("未找到工作流文件，请先生成工作流。")

    if not resolved_workflow_path.exists():
        raise FileNotFoundError(f"工作流文件不存在: {resolved_workflow_path}")

    if verbose:
        print("🔧 教育功能工作流执行器启动")
        print(f"📄 工作流文件：{resolved_workflow_path.name}")
        print("-" * 60)
        print("📊 加载工作流...")

    graph = load_workflow(str(resolved_workflow_path))

    if verbose:
        print(f"  目标：{graph.goal[:100]}")
        print(f"  子任务数：{len(graph.nodes)}")
        for i, node in enumerate(graph.nodes, 1):
            desc = node.description[:60] if node.description else "(无描述)"
            print(f"  {i}. {node.name} — {desc}")

    if inputs_path:
        resolved_inputs_path = Path(inputs_path)
        if not resolved_inputs_path.is_absolute():
            resolved_inputs_path = PROJECT_ROOT / resolved_inputs_path
        execution_inputs = collect_inputs_from_file(str(resolved_inputs_path))
        if verbose:
            print(f"\n📥 从文件加载了 {len(execution_inputs)} 个输入参数")
    else:
        execution_inputs = inputs or {}

    if execution_inputs and verbose:
        print("\n📥 输入参数：")
        for key, value in execution_inputs.items():
            display_val = str(value)
            if len(display_val) > 80:
                display_val = display_val[:80] + "..."
            print(f"  {key}: {display_val}")

    if verbose:
        print("\n⚙️  初始化执行引擎...")
    llm_config = build_llm_config()
    llm = build_llm(llm_config)

    agent_manager = AgentManager()
    agent_manager.add_agents_from_workflow(graph, llm_config=llm_config)
    if verbose:
        print(f"  已注册 {len(agent_manager.agents)} 个 Agent")
        print("\n" + "=" * 60)
        print("🚀 开始执行工作流")
        print("=" * 60 + "\n")

    workflow = WorkFlow(
        graph=graph,
        llm=llm,
        agent_manager=agent_manager,
        max_execution_steps=max_steps,
    )
    output = workflow.execute(inputs=execution_inputs)

    result_path = save_result(output, str(resolved_workflow_path)) if save else None
    return {
        "workflow_path": resolved_workflow_path,
        "graph": graph,
        "inputs": execution_inputs,
        "output": output,
        "result_path": result_path,
    }


def main():
    parser = argparse.ArgumentParser(
        description="教育功能工作流执行器 — 基于 EvoAgentX WorkFlow 引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 执行最新生成的工作流（交互式输入参数）
  python scripts/execute_workflow.py

  # 指定工作流文件
  python scripts/execute_workflow.py --workflow workflows/workflow_20260305_183041.json

  # 从 JSON 文件提供输入参数
  python scripts/execute_workflow.py --inputs inputs.json

  # 调整最大执行步数
  python scripts/execute_workflow.py --max-steps 10

  # 不保存结果
  python scripts/execute_workflow.py --no-save
        """,
    )
    parser.add_argument(
        "--workflow", "-w", default=None,
        help="指定工作流 JSON 文件路径（默认使用最新的）",
    )
    parser.add_argument(
        "--inputs", "-i", default=None,
        help="从 JSON 文件加载输入参数（默认交互式输入）",
    )
    parser.add_argument(
        "--max-steps", "-m", type=int, default=5,
        help="每个子任务的最大执行步数（默认 5）",
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="不保存执行结果",
    )
    args = parser.parse_args()

    # 仍保留原交互式模式
    workflow_path = args.workflow
    if workflow_path is None:
        latest_workflow = find_latest_workflow()
        if latest_workflow is None:
            print("错误：未找到工作流文件")
            print("请先运行功能二（python scripts/generate_workflow.py）生成工作流")
            sys.exit(1)
        workflow_path = str(latest_workflow)

    graph = load_workflow(str(Path(workflow_path) if Path(workflow_path).is_absolute() else PROJECT_ROOT / workflow_path))
    if args.inputs:
        inputs = collect_inputs_from_file(args.inputs)
    else:
        inputs = collect_inputs_interactive(graph)

    try:
        result_bundle = run_workflow_execution(
            workflow_path=workflow_path,
            inputs=inputs,
            max_steps=args.max_steps,
            save=not args.no_save,
            verbose=True,
        )
    except Exception as e:
        print(f"\n❌ 工作流执行失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✅ 工作流执行完成！")
    print("=" * 60)
    print(f"\n{result_bundle['output']}")

    if not args.no_save:
        print(f"\n📄 结果已保存：{result_bundle['result_path']}")


if __name__ == "__main__":
    main()
