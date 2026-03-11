"""Migrated PPT generation service used by CLI and MCP entrypoints."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency for local env loading
    def load_dotenv(*_args, **_kwargs):
        return False
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent
WORKFLOW_PATH = PACKAGE_DIR / "workflows" / "ppt_generation_workflow.json"
MAKE_PPT_DIR = PACKAGE_DIR / "make_ppt"
DEFAULT_TEMPLATE = MAKE_PPT_DIR / "ppt_template" / "template2.pptx"
DB_PATH = PROJECT_ROOT / "data" / "faiss_db.sqlite"
MD_RESULTS_DIR = PROJECT_ROOT / "results" / "ppt_md"
PPTX_RESULTS_DIR = PROJECT_ROOT / "results" / "pptx"
RUNS_DIR = PROJECT_ROOT / "data" / "ppt_runs"

QWEN_MODEL_NAME = "QWen"
DEEPSEEK_MODEL_NAME = "DeepSeek"
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
PPT_NODE_SEQUENCE = ["outline_generation", "title_extraction"]

load_dotenv(PROJECT_ROOT / ".env")

_RAG_TOOLKIT = None


class PPTGenerationError(RuntimeError):
    """Base error for PPT generation."""

    error_type = "runtime_error"

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": "error",
            "error_type": self.error_type,
            "message": str(self),
        }


class PPTGenerationInputError(PPTGenerationError):
    """Raised when request inputs are incomplete or invalid."""

    error_type = "validation_error"

    def __init__(self, message: str, missing_fields: list[str] | None = None) -> None:
        super().__init__(message)
        self.missing_fields = missing_fields or []

    def to_payload(self) -> dict[str, Any]:
        payload = super().to_payload()
        payload["missing_fields"] = self.missing_fields
        return payload


class PPTGenerationRequest(BaseModel):
    """Normalized input for migrated PPT generation."""

    course: str = Field(..., description="课程名称")
    units: list[str] = Field(default_factory=list, description="单元列表")
    lessons: list[str] = Field(default_factory=list, description="课时列表")
    knowledge_points: list[str] = Field(default_factory=list, description="知识点列表")
    constraint: str = Field("", description="附加要求")
    page_limit: Optional[int] = Field(None, ge=6, description="页面数量限制")
    model_type: str = Field(QWEN_MODEL_NAME, description="模型类型: QWen / DeepSeek")
    use_rag: bool = Field(False, description="是否开启 RAG")
    output_mode: str = Field("ppt", description="输出模式: md / ppt")

    @field_validator("course", "constraint", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("units", "lessons", "knowledge_points", mode="before")
    @classmethod
    def _normalize_list_fields(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        if not text:
            return []
        parts = re.split(r"[，,、\n]+", text)
        return [part.strip() for part in parts if part.strip()]

    @field_validator("model_type")
    @classmethod
    def _validate_model_type(cls, value: str) -> str:
        if value not in {QWEN_MODEL_NAME, DEEPSEEK_MODEL_NAME}:
            raise ValueError("model_type 仅支持 QWen 或 DeepSeek")
        return value

    @field_validator("output_mode")
    @classmethod
    def _validate_output_mode(cls, value: str) -> str:
        if value not in {"md", "ppt"}:
            raise ValueError("output_mode 仅支持 md 或 ppt")
        return value

    @model_validator(mode="after")
    def _validate_content_scope(self) -> "PPTGenerationRequest":
        if not (self.units or self.lessons or self.knowledge_points):
            raise ValueError("至少需要提供 units、lessons、knowledge_points 其中之一。")
        return self


def _extract_validation_fields(exc: ValidationError) -> list[str]:
    fields: list[str] = []
    for error in exc.errors():
        loc = error.get("loc", ())
        if loc:
            fields.append(str(loc[0]))
    return sorted(set(fields))


def build_request(payload: dict[str, Any] | None) -> PPTGenerationRequest:
    """Validate a raw payload and return a normalized request object."""

    payload = dict(payload or {})
    course = str(payload.get("course", "") or "").strip()
    units = payload.get("units")
    lessons = payload.get("lessons")
    knowledge_points = payload.get("knowledge_points")

    def _has_values(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, (list, tuple)):
            return any(str(item).strip() for item in value)
        return bool(str(value).strip())

    missing_fields: list[str] = []
    if not course:
        missing_fields.append("course")
    if not (_has_values(units) or _has_values(lessons) or _has_values(knowledge_points)):
        missing_fields.append("units_or_lessons_or_knowledge_points")
    if missing_fields:
        raise PPTGenerationInputError(
            "缺少必填字段：需要提供 course，并且至少提供 units、lessons、knowledge_points 之一。",
            missing_fields=missing_fields,
        )

    try:
        return PPTGenerationRequest(**payload)
    except ValidationError as exc:
        raise PPTGenerationInputError(
            "输入字段格式不合法。",
            missing_fields=_extract_validation_fields(exc),
        ) from exc


def _require_env_var(name: str, model_type: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise PPTGenerationError(f"{model_type} 模型缺少环境变量 {name}。")
    return value


def init_llm(model_type: str):
    """Initialize the configured non-thinking LLM."""

    try:
        from evoagentx.models import AliyunLLM, AliyunLLMConfig, LiteLLM, LiteLLMConfig
    except ImportError as exc:
        raise PPTGenerationError("EvoAgentX 未安装，请先执行 pip install -r requirements.txt。") from exc

    if model_type == DEEPSEEK_MODEL_NAME:
        api_key = _require_env_var("DEEPSEEK_API_KEY", model_type)
        return LiteLLM(
            config=LiteLLMConfig(
                model="deepseek/deepseek-chat",
                deepseek_key=api_key,
                base_url=os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL),
                stream=False,
            )
        )

    api_key = _require_env_var("DASHSCOPE_API_KEY", model_type)
    return AliyunLLM(
        config=AliyunLLMConfig(
            model="qwen-plus",
            aliyun_api_key=api_key,
            base_url=os.getenv("DASHSCOPE_BASE_URL", QWEN_BASE_URL),
            stream=False,
        )
    )


def get_rag_toolkit():
    """Lazily initialize the migrated RAG toolkit."""

    global _RAG_TOOLKIT

    if not DB_PATH.exists():
        raise PPTGenerationError(
            f"已开启 RAG，但本地知识库不存在：{DB_PATH}。请先准备知识库后再启用 use_rag。"
        )

    if _RAG_TOOLKIT is None:
        try:
            from eduagent_lesson_plan.faiss_toolkit import FaissToolkit
        except ImportError as exc:
            raise PPTGenerationError(
                "RAG 工具箱导入失败。请确认可选依赖已安装，例如 sentence-transformers。"
            ) from exc

        try:
            logger.info("正在初始化 PPT RAG 工具箱...")
            _RAG_TOOLKIT = FaissToolkit(db_path=str(DB_PATH))
        except ModuleNotFoundError as exc:
            raise PPTGenerationError(
                f"RAG 依赖缺失：{exc.name}。若暂不需要知识库增强，请关闭 use_rag。"
            ) from exc
        except Exception as exc:
            raise PPTGenerationError(f"RAG 工具箱初始化失败：{exc}") from exc

    return _RAG_TOOLKIT


def build_rag_queries(
    course: str,
    units: list[str],
    lessons: list[str],
    knowledge_points: list[str],
    constraint: str,
) -> list[dict[str, str]]:
    queries: list[dict[str, str]] = []
    if course:
        queries.append({"field": "课程名称", "query": f"课程是{course}"})
    if units:
        queries.append({"field": "单元", "query": f"单元是{', '.join(units)}"})
    if lessons:
        queries.append({"field": "课时", "query": f"课时内容关于{', '.join(lessons)}"})
    if knowledge_points:
        queries.append({"field": "知识点", "query": f"知识点包括{', '.join(knowledge_points)}"})
    if constraint:
        queries.append({"field": "附加要求", "query": f"要求：{constraint}"})
    if not queries:
        queries.append({"field": "通用", "query": "通用教学参考资料"})
    return queries


def retrieve_rag_context(req: PPTGenerationRequest) -> str:
    """Execute RAG retrieval and merge the result into one text block."""

    if not req.use_rag:
        logger.info(">>> 用户未开启 RAG，跳过检索步骤")
        return ""

    toolkit = get_rag_toolkit()
    query_tool = toolkit.get_tool("faiss_query")
    if query_tool is None:
        raise PPTGenerationError("RAG 工具箱缺少 faiss_query 能力。")

    sections: list[str] = []
    for item in build_rag_queries(req.course, req.units, req.lessons, req.knowledge_points, req.constraint):
        logger.info("RAG 查询词(%s): [%s]", item["field"], item["query"])
        search_results = query_tool(query=item["query"], top_k=3)
        if search_results.get("success"):
            results = search_results.get("data", {}).get("results", [])
            if results:
                docs = [f"资料{index}: {res.get('content', '')}" for index, res in enumerate(results, 1)]
                sections.append(f"【{item['field']}】\n" + "\n".join(docs))
    return "\n\n".join(sections)


def compute_page_params(page_limit: Optional[int]) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Estimate title count and page detail density based on the page limit."""

    if page_limit is None:
        return None, None, None

    available_pages = page_limit - 2
    if available_pages <= 18:
        title_count = 4
    elif available_pages <= 28:
        title_count = 6
    elif available_pages <= 48:
        title_count = min(9, max(6, int(available_pages * 0.18)))
    else:
        title_count = 9

    avg_sections_per_title = min(4, max(1, int(available_pages / (title_count * 1.2))))
    avg_word_limit = max(325, min(400, int(2500 / (title_count * avg_sections_per_title))))

    total_sections = title_count * avg_sections_per_title
    if total_sections > available_pages:
        avg_sections_per_title = max(2, int(available_pages / title_count) - 1)
        total_sections = title_count * avg_sections_per_title
        avg_word_limit = max(300, min(600, int(2500 / total_sections)))

    return title_count, avg_sections_per_title, avg_word_limit


def generate_title_slide(class_name: str) -> str:
    return f"# {class_name}\n\n---\n\n"


def generate_toc_slide(outlines: list[str]) -> str:
    chinese_nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九"]
    toc = "# 目录\n\n"
    for index, outline in enumerate(outlines):
        if outline.strip():
            clean_title = re.sub(r"^\d+[、.]?\s*", "", outline.strip())
            if clean_title and index < len(chinese_nums):
                toc += f"- {chinese_nums[index]}、{clean_title}\n"
    return toc + "\n"


def build_slide_prompt(
    title: str,
    index: int,
    outline: str,
    prev_titles: list[str],
    avg_word_limit: Optional[int],
    avg_sections_per_title: Optional[int],
) -> str:
    prompt = f"""你是一个专业的PPT生成器，请根据幻灯片标题{{{title}}}和详细的教学内容大纲生成幻灯片{index + 1}
教学大纲如下：
{{{outline}}}
给定前面的幻灯片的标题：
"""
    for prev_index, prev in enumerate(prev_titles):
        prompt += f"幻灯片{prev_index + 1}：\n{{\n{prev}\n}}"

    if avg_word_limit is not None and avg_sections_per_title is not None:
        bullets_per_section = (
            f"要点数量要求：第{index+1}个一级标题下的各个二级标题必须有不同数量的要点，"
            f"分别按照 {min(4, max(1, int(avg_word_limit/120)))} 个、"
            f"{min(4, max(2, int(avg_word_limit/100)))} 个、"
            f"{min(4, max(1, int(avg_word_limit/150)))} 个、"
            f"{min(4, max(3, int(avg_word_limit/80)))} 个要点的顺序分配"
            f"（如果二级标题少于4个，则按顺序取前几个数量）"
        )

        if avg_word_limit <= 250:
            content_detail = "内容应该详细充实，每个要点包含核心概念的详细解释、工作原理、主要特点、典型应用场景和具体实例"
        elif avg_word_limit <= 350:
            content_detail = "内容应该非常详细，每个要点包含概念解释、技术原理、实现方法、典型应用、案例分析和优缺点分析"
        else:
            content_detail = "内容应该极其详细全面，每个要点包含理论基础、技术实现细节、实际应用、案例分析、发展趋势和行业标准"

        prompt += f"幻灯片内容的字数大约控制在{avg_word_limit}字左右。{content_detail}。"
        prompt += f"每个一级标题下应该包含{avg_sections_per_title}个二级标题（## 格式），{bullets_per_section}，确保内容分布均衡且内容充实。"
        prompt += f"重要：本幻灯片必须包含{avg_sections_per_title}个二级标题（## 格式），不能多也不能少。"
        prompt += f"要点内容要求：每个要点应包含100-170字的详细解释，不同二级标题下的要点数量必须不同，严格按照指定的要点数量分配，确保每个要点内容要充实且有深度。"

    prompt += """

生成时需要确保：
1、幻灯片的内容与给定的幻灯片标题高度相关且全面深入
2、确保本幻灯片不重复前面幻灯片的任何内容
3、整体演示文稿的逻辑连贯性很好
4、幻灯片标题使用一级标题格式（#），序号必须使用中文数字（如一、二、三），格式为：# 一、标题
5、子标题（二级标题）使用## 格式，不使用序号，例如：## 什么是AI大模型
6、内容使用要点符号（-）
7、严格禁止使用三级标题（###）和更深层次的标题
8、严格禁止要点符号下面再有子要点或缩进内容
9、严格禁止数字列表下面再有子列表或缩进内容
10、所有内容必须保持平级结构，不允许任何形式的嵌套
11、每个要点（-）必须是独立的，不能包含子项目
12、重要格式要求：每个要点必须写成完整的一行，不允许在要点内容中间换行
13、要点内容格式：要点内容应该是连续的文本，避免在句子中间换行
14、如果有相关内容，请作为独立的要点分别列出，而不是嵌套在其他要点下
15、合理分配内容：每个二级标题下的要点数量必须严格按照指定要求分配
16、优先保证内容的全面性和深度，确保知识点覆盖充分
17、代码使用标准markdown代码块格式，代码块必须完整在一个二级标题下
18、公式表示规范：使用Unicode数学符号和美观的文本格式表示公式
19、严格禁止LaTeX格式：不允许使用$...$、$$...$$等LaTeX语法
20、每个要点内容应该详细充实，包含核心概念定义、工作原理、实现方法、典型应用场景和具体实例
21、避免空洞描述，每个要点都要有实质性的、有深度的专业知识内容
22、严格禁止要点内容中出现人为换行：要点内容必须保持为连续的单行文本

输出为markdown，格式为：
{{标题}}
{{内容}}
"""
    return prompt


def extract_section_content(raw_output: str | dict[str, Any], section_key: str) -> str:
    """Extract a marked markdown section from workflow output."""

    known_sections = ["teaching_outline", "title_sequence", "Thought"]
    if isinstance(raw_output, dict):
        content = str(raw_output.get(section_key, raw_output))
    else:
        content = str(raw_output).strip()

    content = re.sub(r"##\s*Thought\b.*?(?=\n##\s+[^\s]|\Z)", "", content, flags=re.DOTALL)
    other_sections = [section for section in known_sections if section != section_key]
    stop_pattern = "|".join(rf"##\s*{re.escape(section)}" for section in other_sections)
    header_pattern = rf"##\s*{re.escape(section_key)}\s*\n(.*?)(?={stop_pattern}|\Z)"
    header_match = re.search(header_pattern, content, re.DOTALL)
    if header_match:
        content = header_match.group(1)
    return content.strip()


def build_goal_text(req: PPTGenerationRequest, title_count: Optional[int]) -> str:
    goal = f"课程名称：{req.course}\n"
    if req.units and req.lessons:
        goal += "教学内容：\n"
        for unit, lesson in zip(req.units, req.lessons):
            goal += f"  - {unit!r} 单元的 {lesson!r} 部分\n"
    elif req.units:
        goal += f"单元内容：{', '.join(repr(unit) for unit in req.units)}\n"
    elif req.lessons:
        goal += f"课时内容：{', '.join(repr(lesson) for lesson in req.lessons)}\n"
    if req.knowledge_points:
        goal += f"知识点：{', '.join(repr(point) for point in req.knowledge_points)}\n"
    if req.constraint:
        goal += f"附加要求：{req.constraint}\n"
    if title_count is not None:
        goal += f"\n标题数量限制：请提取恰好 {title_count} 个标题。\n"
    else:
        goal += "\n请根据大纲内容提取适量标题。\n"
    return goal


def build_goal_text_with_rag(req: PPTGenerationRequest, title_count: Optional[int], rag_context: str) -> str:
    goal = build_goal_text(req, title_count)
    if rag_context:
        goal += f"\n### 📚 本地知识库参考资料（请优先参考以下内容）：\n{rag_context}\n"
    return goal


def _extract_failed_step_error(workflow) -> str | None:
    trajectory = getattr(workflow.environment, "trajectory", [])
    for step in reversed(trajectory):
        if getattr(step, "error", None):
            return step.error
        message = getattr(step, "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str) and "An Error occurs when executing the workflow:" in content:
            return content
    return None


def execute_ppt_workflow(req: PPTGenerationRequest) -> str:
    """Generate PPT markdown content via fixed two-step workflow plus slide synthesis."""

    try:
        from evoagentx.agents import AgentManager
        from evoagentx.core.message import Message, MessageType
        from evoagentx.workflow import WorkFlow, WorkFlowGraph
        from evoagentx.workflow.environment import TrajectoryState
    except ImportError as exc:
        raise PPTGenerationError("EvoAgentX 未安装，请先执行 pip install -r requirements.txt。") from exc

    if not WORKFLOW_PATH.exists():
        raise PPTGenerationError(f"找不到工作流文件：{WORKFLOW_PATH}")

    title_count, avg_sections_per_title, avg_word_limit = compute_page_params(req.page_limit)
    rag_context = retrieve_rag_context(req)
    llm = init_llm(req.model_type)

    goal_text = build_goal_text_with_rag(req, title_count, rag_context)
    workflow_graph = WorkFlowGraph.from_file(str(WORKFLOW_PATH))
    agent_manager = AgentManager()
    agent_manager.add_agents_from_workflow(workflow_graph, llm_config=llm.config)
    workflow = WorkFlow(graph=workflow_graph, agent_manager=agent_manager, llm=llm)

    inputs = {"goal": goal_text}

    async def _run_sequential_workflow() -> None:
        prepared_inputs = workflow._prepare_inputs(dict(inputs))
        workflow._validate_workflow_structure(inputs=prepared_inputs)
        workflow.environment.update(
            message=Message(content=prepared_inputs, msg_type=MessageType.INPUT, wf_goal=workflow.graph.goal),
            state=TrajectoryState.COMPLETED,
        )
        for node_name in PPT_NODE_SEQUENCE:
            node = workflow.graph.get_node(node_name)
            logger.info("执行 PPT 节点: %s", node.name)
            await workflow.execute_task(node)

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run_sequential_workflow())
    except Exception as exc:
        detail = _extract_failed_step_error(workflow) or str(exc)
        raise PPTGenerationError(f"PPT 工作流执行失败：{detail}") from exc
    finally:
        loop.close()

    all_exec_data = workflow.environment.get_all_execution_data()
    outline = str(all_exec_data.get("teaching_outline", "")).strip()
    title_sequence = str(all_exec_data.get("title_sequence", "")).strip()
    outline = re.sub(r"##\s*Thought\b.*?(?=\n##\s+[^\s]|\Z)", "", outline, flags=re.DOTALL).strip()
    title_sequence = re.sub(r"##\s*Thought\b.*?(?=\n##\s+[^\s]|\Z)", "", title_sequence, flags=re.DOTALL).strip()

    if not outline or not title_sequence:
        task_messages = workflow.environment.get_task_messages(tasks=PPT_NODE_SEQUENCE, n=None, include_inputs=False)
        combined_output = "\n\n".join(str(message) for message in task_messages)
        if not outline:
            outline = extract_section_content(combined_output, "teaching_outline")
        if not title_sequence:
            title_sequence = extract_section_content(combined_output, "title_sequence")

    outlines = [line for line in title_sequence.strip().split("\n") if line.strip()]
    if not outlines:
        raise PPTGenerationError("未能从工作流输出中提取到标题序列。")

    slides = [generate_title_slide(req.course), generate_toc_slide(outlines)]
    system_prompt = "你是一个专业的PPT生成器，请根据幻灯片标题和详细的教学内容大纲生成幻灯片，确保每个二级标题下有1-4个要点，每个要点内容详细充实且有深度。"
    for index, title in enumerate(outlines):
        prompt = build_slide_prompt(
            title=title,
            index=index,
            outline=outline,
            prev_titles=outlines[:index],
            avg_word_limit=avg_word_limit,
            avg_sections_per_title=avg_sections_per_title,
        )
        result = llm.generate(prompt=prompt, system_message=system_prompt, parse_mode="str")
        slide_content = result.content if hasattr(result, "content") else str(result)
        slide_content = slide_content.replace("{#", "#").replace("}", "")
        slides.append(f"{slide_content}\n\n")

    final_md = "".join(slides)
    if "Workflow Execution Failed" in final_md:
        raise PPTGenerationError("PPT 内容生成失败。")
    return final_md


def convert_md_to_pptx(md_file_path: str, output_pptx_path: str, template_path: str | None = None) -> str:
    """Convert markdown slides into a PPTX file via the migrated make_ppt script."""

    convert_script = MAKE_PPT_DIR / "convert_ppt.py"
    if not convert_script.exists():
        raise PPTGenerationError(f"找不到转换脚本：{convert_script}")

    template = template_path or str(DEFAULT_TEMPLATE)
    if not Path(template).exists():
        raise PPTGenerationError(f"找不到 PPT 模板：{template}")

    cmd = [
        sys.executable,
        str(convert_script),
        str(md_file_path),
        str(output_pptx_path),
        "--template",
        str(template),
    ]
    result = subprocess.run(
        cmd,
        cwd=str(MAKE_PPT_DIR),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise PPTGenerationError(f"MD→PPTX 转换失败：{result.stderr or result.stdout}")
    return output_pptx_path


def _build_filename_prefix(req: PPTGenerationRequest) -> str:
    parts = [req.course, *req.units, *req.lessons]
    if not req.units and not req.lessons and req.knowledge_points:
        parts.extend(req.knowledge_points[:3])
    normalized = [re.sub(r"[^\w\u4e00-\u9fff-]+", "_", part).strip("_") for part in parts if part]
    return "_".join(filter(None, normalized)) or "ppt"


def _build_md_preview(markdown_content: str, max_chars: int = 220) -> str:
    return re.sub(r"\s+", " ", markdown_content).strip()[:max_chars]


def generate_ppt_artifacts(req: PPTGenerationRequest) -> dict[str, Any]:
    """Generate markdown slides and optionally convert them to PPTX."""

    MD_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PPTX_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    markdown_content = execute_ppt_workflow(req)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = _build_filename_prefix(req)
    md_path = MD_RESULTS_DIR / f"{timestamp}_{prefix}_slides.md"
    md_path.write_text(markdown_content, encoding="utf-8")

    pptx_path: str | None = None
    if req.output_mode == "ppt":
        pptx_output_path = PPTX_RESULTS_DIR / f"{timestamp}_{prefix}_slides.pptx"
        pptx_path = convert_md_to_pptx(str(md_path), str(pptx_output_path))

    preview = _build_md_preview(markdown_content)
    metadata_path = RUNS_DIR / f"ppt_run_{timestamp}_{prefix}.json"
    metadata = {
        "status": "success",
        "generated_at": datetime.now().isoformat(),
        "request": req.model_dump(),
        "workflow_path": str(WORKFLOW_PATH),
        "markdown_path": str(md_path),
        "pptx_path": pptx_path,
        "metadata_path": str(metadata_path),
        "preview": preview,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "success",
        "markdown_path": str(md_path),
        "pptx_path": pptx_path,
        "metadata_path": str(metadata_path),
        "preview": preview,
        "request": req.model_dump(),
    }
