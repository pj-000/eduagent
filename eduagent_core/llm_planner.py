"""Optional LLM-assisted routing for the EduAgent planner."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any


try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency for local env loading
    def load_dotenv(*_args, **_kwargs):
        return False


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
logging.getLogger("dashscope").setLevel(logging.CRITICAL)
logging.getLogger("LiteLLM").setLevel(logging.ERROR)

QWEN_MODEL_NAME = "QWen"
DEEPSEEK_MODEL_NAME = "DeepSeek"
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"


class PlannerLLMError(RuntimeError):
    """Raised when the optional planner LLM cannot be used safely."""


def _extract_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise PlannerLLMError("Planner LLM 输出中未找到合法 JSON 对象。")


def build_planner_llm(model_type: str = QWEN_MODEL_NAME):
    """Build the planner LLM lazily so rule-based planner use remains dependency-free."""

    try:
        from evoagentx.models import AliyunLLM, AliyunLLMConfig, LiteLLM, LiteLLMConfig
    except ImportError as exc:  # pragma: no cover - depends on optional runtime package
        raise PlannerLLMError("EvoAgentX 未安装，无法启用 LLM planner。") from exc

    if model_type == DEEPSEEK_MODEL_NAME:
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise PlannerLLMError("未配置 DEEPSEEK_API_KEY，无法启用 DeepSeek planner。")
        return LiteLLM(
            config=LiteLLMConfig(
                model="deepseek/deepseek-chat",
                deepseek_key=api_key,
                base_url=os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL),
                stream=False,
            )
        )

    if model_type != QWEN_MODEL_NAME:
        raise PlannerLLMError(f"不支持的 planner 模型类型：{model_type}")

    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise PlannerLLMError("未配置 DASHSCOPE_API_KEY，无法启用 QWen planner。")
    return AliyunLLM(
        config=AliyunLLMConfig(
            model="qwen-plus",
            aliyun_api_key=api_key,
            base_url=os.getenv("DASHSCOPE_BASE_URL", QWEN_BASE_URL),
            stream=False,
            output_response=True,
        )
    )


def analyze_task_with_llm(
    *,
    task: str,
    payload: dict[str, Any],
    capability_summaries: list[dict[str, Any]],
    model_type: str = QWEN_MODEL_NAME,
) -> dict[str, Any]:
    """Ask the planner model to classify the task and recommend a route."""

    llm = build_planner_llm(model_type=model_type)
    prompt = f"""你是 EduAgent 的任务规划器。你要根据用户任务，判断应该直接调用专用生成能力，还是进入 workflow 主链。

可选 task_family:
- generation
- mixed
- research
- evaluation

可选 complexity:
- single_step
- multi_step

可选 recommended_route:
- capability
- workflow

可选 direct_capability:
- lesson_plan
- exam
- ppt
- null

判断原则：
1. 仅当任务是清晰的单步生成时，才推荐 capability。
2. 如果任务包含 “先查资料 / 调研 / 探索 / workflow / 评估 / 落地方案 / 多步骤”，优先推荐 workflow。
3. 如果用户提供的字段不足以支持 direct capability，也优先推荐 workflow 或保持 capability 但说明缺参风险。
4. 输出必须是 JSON，不要输出解释性文字。

当前任务：
{task}

当前 payload(JSON)：
{json.dumps(payload, ensure_ascii=False)}

可用 direct capabilities(JSON)：
{json.dumps(capability_summaries, ensure_ascii=False)}

请输出如下 JSON 结构：
{{
  "task_family": "generation|mixed|research|evaluation",
  "complexity": "single_step|multi_step",
  "recommended_route": "capability|workflow",
  "direct_capability": "lesson_plan|exam|ppt|null",
  "requires_research": true,
  "requires_workflow": false,
  "reason": "简洁中文原因"
}}
"""
    try:
        response = llm.generate(prompt=prompt)
    except Exception as exc:  # pragma: no cover - depends on remote model/network/runtime
        raise PlannerLLMError(f"LLM planner 调用失败：{exc}") from exc
    if hasattr(response, "content"):
        content = response.content
    elif isinstance(response, str):
        content = response
    else:
        content = str(response)
    return _extract_json_object(content)
