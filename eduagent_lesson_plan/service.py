"""Migrated lesson-plan generation service used by CLI and MCP entrypoints."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency for local env loading
    def load_dotenv(*_args, **_kwargs):
        return False
from pydantic import BaseModel, Field, ValidationError, field_validator


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent
WORKFLOW_PATH = PACKAGE_DIR / "workflows" / "lessonplan_generation_workflow.json"
DB_PATH = PROJECT_ROOT / "data" / "faiss_db.sqlite"
RESULTS_DIR = PROJECT_ROOT / "results" / "lesson_plans"
RUNS_DIR = PROJECT_ROOT / "data" / "lesson_plan_runs"
UPLOAD_DIR = PROJECT_ROOT / "data" / "upload_knowledge"
LESSON_PLAN_NODE_SEQUENCE = [
    "course_outline_design",
    "content_generation_theory",
    "content_generation_practice",
]

QWEN_MODEL_NAME = "QWen"
DEEPSEEK_MODEL_NAME = "DeepSeek"
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

load_dotenv(PROJECT_ROOT / ".env")

_RAG_TOOLKIT = None


class LessonPlanError(RuntimeError):
    """Base error for lesson-plan generation."""

    error_type = "runtime_error"

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": "error",
            "error_type": self.error_type,
            "message": str(self),
        }


class LessonPlanInputError(LessonPlanError):
    """Raised when request inputs are incomplete or invalid."""

    error_type = "validation_error"

    def __init__(self, message: str, missing_fields: list[str] | None = None) -> None:
        super().__init__(message)
        self.missing_fields = missing_fields or []

    def to_payload(self) -> dict[str, Any]:
        payload = super().to_payload()
        payload["missing_fields"] = self.missing_fields
        return payload


class LessonPlanRequest(BaseModel):
    """Normalized input for migrated lesson-plan generation."""

    course: str = Field(..., description="课程名称")
    units: str = Field("", description="单元名称")
    lessons: str = Field("", description="课时名称")
    constraint: str = Field("", description="附加要求")
    word_limit: int = Field(2000, gt=0, description="字数要求")
    model_type: str = Field(QWEN_MODEL_NAME, description="模型类型: QWen / DeepSeek")
    use_rag: bool = Field(False, description="是否开启 RAG")

    @field_validator("course", "units", "lessons", "constraint", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("model_type")
    @classmethod
    def _validate_model_type(cls, value: str) -> str:
        if value not in {QWEN_MODEL_NAME, DEEPSEEK_MODEL_NAME}:
            raise ValueError("model_type 仅支持 QWen 或 DeepSeek")
        return value


def _slugify_course_name(course: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", course.lower()).strip("-")
    if slug:
        return slug[:48]
    digest = hashlib.sha1(course.encode("utf-8")).hexdigest()[:10]
    return f"lesson-plan-{digest}"


def _build_preview(markdown: str, max_chars: int = 220) -> str:
    preview = re.sub(r"\s+", " ", markdown).strip()
    return preview[:max_chars]


def _extract_validation_fields(exc: ValidationError) -> list[str]:
    fields: list[str] = []
    for error in exc.errors():
        loc = error.get("loc", ())
        if loc:
            fields.append(str(loc[0]))
    return sorted(set(fields))


def build_request(payload: dict[str, Any] | None) -> LessonPlanRequest:
    """Validate a raw payload and return a normalized request object."""

    payload = dict(payload or {})
    course = str(payload.get("course", "") or "").strip()
    units = str(payload.get("units", "") or "").strip()
    lessons = str(payload.get("lessons", "") or "").strip()

    missing_fields: list[str] = []
    if not course:
        missing_fields.append("course")
    if not units and not lessons:
        missing_fields.append("units_or_lessons")
    if missing_fields:
        raise LessonPlanInputError(
            "缺少必填字段：需要提供 course，并且至少提供 units 或 lessons 之一。",
            missing_fields=missing_fields,
        )

    try:
        return LessonPlanRequest(**payload)
    except ValidationError as exc:
        raise LessonPlanInputError(
            "输入字段格式不合法。",
            missing_fields=_extract_validation_fields(exc),
        ) from exc


def _require_env_var(name: str, model_type: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise LessonPlanError(f"{model_type} 模型缺少环境变量 {name}。")
    return value


def build_rag_queries(course: str, units: str, lessons: str, constraint: str) -> list[dict[str, str]]:
    queries: list[dict[str, str]] = []
    if course:
        queries.append({"field": "课程名称", "query": f"课程是{course}"})
    if units:
        queries.append({"field": "单元", "query": f"单元是{units}"})
    if lessons:
        queries.append({"field": "课时", "query": f"课时内容关于{lessons}"})
    if constraint:
        queries.append({"field": "附加要求", "query": f"要求：{constraint}"})
    if not queries:
        queries.append({"field": "通用", "query": "通用教案参考资料"})
    return queries


def get_rag_toolkit():
    """Lazily initialize the migrated RAG toolkit."""

    global _RAG_TOOLKIT

    if not DB_PATH.exists():
        raise LessonPlanError(
            f"已开启 RAG，但本地知识库不存在：{DB_PATH}。请先准备知识库后再启用 use_rag。"
        )

    if _RAG_TOOLKIT is None:
        try:
            from .faiss_toolkit import FaissToolkit
        except ImportError as exc:
            raise LessonPlanError(
                "RAG 工具箱导入失败。请确认可选依赖已安装，例如 sentence-transformers。"
            ) from exc

        try:
            logger.info("正在初始化 RAG 工具箱...")
            _RAG_TOOLKIT = FaissToolkit(db_path=str(DB_PATH))
            logger.info("RAG 工具箱初始化成功")
        except ModuleNotFoundError as exc:
            raise LessonPlanError(
                f"RAG 依赖缺失：{exc.name}。若暂不需要知识库增强，请关闭 use_rag。"
            ) from exc
        except Exception as exc:
            raise LessonPlanError(f"RAG 工具箱初始化失败：{exc}") from exc

    return _RAG_TOOLKIT


def build_rag_context(req: LessonPlanRequest) -> str:
    """Query the optional FAISS knowledge base and return a merged context string."""

    if not req.use_rag:
        logger.info(">>> 用户未开启 RAG，跳过检索步骤")
        return ""

    logger.info(">>> 用户开启了 RAG，开始检索...")
    toolkit = get_rag_toolkit()
    query_tool = toolkit.get_tool("faiss_query")
    if query_tool is None:
        raise LessonPlanError("RAG 工具箱缺少 faiss_query 能力。")

    all_sections: list[str] = []
    total_hits = 0
    for item in build_rag_queries(req.course, req.units, req.lessons, req.constraint):
        field = item["field"]
        search_query = item["query"]
        logger.info("RAG 查询词(%s): [%s]", field, search_query)
        search_results = query_tool(query=search_query, top_k=3)
        if search_results.get("success"):
            results_list = search_results.get("data", {}).get("results", [])
            if results_list:
                section_docs = [
                    f"资料{idx}: {res.get('content', '')}"
                    for idx, res in enumerate(results_list, 1)
                ]
                all_sections.append(f"【{field}】\n" + "\n".join(section_docs))
                total_hits += len(results_list)
            else:
                all_sections.append(f"【{field}】\n未检索到相关资料。")
        else:
            all_sections.append(f"【{field}】\n检索失败：{search_results.get('error')}")

    logger.info("RAG 完成: 合计 %s 条资料", total_hits)
    return "\n\n".join(all_sections)


def init_llm(model_type: str):
    """Initialize the configured non-thinking LLM."""

    try:
        from evoagentx.models import AliyunLLM, AliyunLLMConfig, LiteLLM, LiteLLMConfig
    except ImportError as exc:
        raise LessonPlanError("EvoAgentX 未安装，请先执行 pip install -r requirements.txt。") from exc

    if model_type == DEEPSEEK_MODEL_NAME:
        api_key = _require_env_var("DEEPSEEK_API_KEY", model_type)
        model_id = "deepseek/deepseek-chat"
        return LiteLLM(
            config=LiteLLMConfig(
                model=model_id,
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
            result_format="message",
        )
    )


def extract_section_content(raw_output: str | dict[str, Any], section_key: str) -> str:
    """Extract a marked markdown section from workflow output."""

    content = ""
    known_sections = ["theory_content", "practice_content", "outline_structure", "Thought"]

    if isinstance(raw_output, dict):
        if section_key in raw_output:
            content = str(raw_output[section_key])
        else:
            for value in raw_output.values():
                value_text = str(value)
                if f"## {section_key}" in value_text:
                    content = value_text
                    break
            if not content:
                content = str(raw_output)
    else:
        content = str(raw_output).strip()

    json_match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if section_key in data:
                content = data[section_key]
        except Exception:
            pass

    content = re.sub(r"##\s*Thought\b.*?(?=\n##\s+[^\s]|\Z)", "", content, flags=re.DOTALL)

    other_sections = [section for section in known_sections if section != section_key]
    stop_pattern = "|".join(rf"##\s*{re.escape(section)}" for section in other_sections)
    header_pattern = rf"##\s*{re.escape(section_key)}\s*\n(.*?)(?={stop_pattern}|\Z)"
    header_match = re.search(header_pattern, content, re.DOTALL)
    if header_match:
        content = header_match.group(1)

    title_match = re.search(r"(?m)^\s*#{1,6}\s+.*", content)
    if title_match:
        content = content[title_match.start() :]

    return content.strip()


def _deduplicate_content(theory: str, practice: str) -> tuple[str, str]:
    if not theory or not practice:
        return theory, practice

    if theory.strip() == practice.strip():
        combined = theory.strip()
        practice_markers = [
            r"(?m)^#{1,4}\s*.*实践操作",
            r"(?m)^#{1,4}\s*.*教学过程设计",
            r"(?m)^#{1,4}\s*.*课堂活动",
            r"(?m)^#{1,4}\s*.*实验环境",
        ]
        for marker in practice_markers:
            split_match = re.search(marker, combined)
            if split_match:
                return combined[: split_match.start()].strip(), combined[split_match.start() :].strip()
        return combined, ""

    shorter, longer = (theory, practice) if len(theory) <= len(practice) else (practice, theory)
    if len(shorter) > 200 and shorter[:200] in longer:
        cleaned = longer.replace(shorter, "").strip()
        if len(cleaned) > 100:
            return (theory, cleaned) if len(theory) <= len(practice) else (cleaned, practice)

    return theory, practice


def assemble_lesson_plan(req: LessonPlanRequest, theory_content: str, practice_content: str) -> str:
    """Merge the theory and practice sections into one markdown lesson plan."""

    theory_content, practice_content = _deduplicate_content(theory_content, practice_content)
    final_plan = f"# 《{req.course}》教学教案\n\n{theory_content}\n\n---\n\n"
    if practice_content:
        final_plan += practice_content
    return final_plan.strip()


def _sanitize_extracted_content(content: str) -> str:
    if not content:
        return ""
    content = re.sub(r"##\s*Thought\b.*?(?=\n##\s+[^\s]|\Z)", "", content, flags=re.DOTALL).strip()
    title_match = re.search(r"(?m)^\s*#{1,6}\s+.*", content)
    if title_match:
        content = content[title_match.start() :]
    return content.strip()


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


def _ensure_not_failed_output(content: str, workflow=None) -> None:
    normalized = (content or "").strip()
    if normalized == "Workflow Execution Failed":
        detail = _extract_failed_step_error(workflow)
        if detail:
            raise LessonPlanError(f"教案工作流执行失败：{detail}")
        raise LessonPlanError("教案工作流执行失败。")


def _build_goal_text(req: LessonPlanRequest, rag_context: str) -> str:
    theory_word_limit = int(req.word_limit * 0.60)
    practice_word_limit = int(req.word_limit * 0.40)
    goal = f"""
请为《{req.course}》课程生成教学教案的相关内容。

课程信息：
- 课程名称：{req.course}
- 单元：{req.units}
- 课时：{req.lessons}
- 附加要求：{req.constraint}
- 教案总字数要求：{req.word_limit}字
- 理论部分字数上限：{theory_word_limit}字
- 实践部分字数上限：{practice_word_limit}字

⚠️ 严格控制字数，不得超出上限。
""".strip()
    if rag_context:
        goal += f"\n\n### 📚 本地知识库参考资料\n{rag_context}\n"
    return goal


def execute_workflow_logic(req: LessonPlanRequest) -> str:
    """Run the migrated EvoAgentX workflow and return lesson-plan markdown."""

    try:
        from evoagentx.agents import AgentManager
        from evoagentx.workflow import WorkFlow, WorkFlowGraph
    except ImportError as exc:
        raise LessonPlanError("EvoAgentX 未安装，请先执行 pip install -r requirements.txt。") from exc

    if not WORKFLOW_PATH.exists():
        raise LessonPlanError(f"找不到工作流文件：{WORKFLOW_PATH}")

    rag_context = build_rag_context(req)

    theory_word_limit = int(req.word_limit * 0.60)
    practice_word_limit = int(req.word_limit * 0.40)
    workflow_graph = WorkFlowGraph.from_file(str(WORKFLOW_PATH))
    llm = init_llm(req.model_type)

    agent_manager = AgentManager()
    agent_manager.add_agents_from_workflow(workflow_graph, llm_config=llm.config)

    workflow = WorkFlow(graph=workflow_graph, agent_manager=agent_manager, llm=llm)
    inputs = {
        "goal": _build_goal_text(req, rag_context),
        "word_limit": str(req.word_limit),
        "theory_word_limit": str(theory_word_limit),
        "practice_word_limit": str(practice_word_limit),
    }

    async def _run_sequential_workflow() -> None:
        from evoagentx.core.message import Message, MessageType
        from evoagentx.workflow.environment import TrajectoryState

        prepared_inputs = workflow._prepare_inputs(dict(inputs))
        workflow._validate_workflow_structure(inputs=prepared_inputs)
        workflow.environment.update(
            message=Message(content=prepared_inputs, msg_type=MessageType.INPUT, wf_goal=workflow.graph.goal),
            state=TrajectoryState.COMPLETED,
        )
        for node_name in LESSON_PLAN_NODE_SEQUENCE:
            node = workflow.graph.get_node(node_name)
            logger.info("执行教案节点: %s", node.name)
            await workflow.execute_task(node)

    logger.info("开始执行教案工作流（固定串行：大纲 -> 理论 -> 实践）...")
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run_sequential_workflow())
    except Exception as exc:
        detail = _extract_failed_step_error(workflow) or str(exc)
        raise LessonPlanError(f"教案工作流执行失败：{detail}") from exc
    finally:
        loop.close()

    theory = ""
    practice = ""
    try:
        all_exec_data = workflow.environment.get_all_execution_data()
        theory = str(all_exec_data.get("theory_content", "")).strip()
        practice = str(all_exec_data.get("practice_content", "")).strip()
    except Exception as exc:
        logger.warning("从 execution_data 获取节点产物失败：%s", exc)

    theory = _sanitize_extracted_content(theory)
    practice = _sanitize_extracted_content(practice)

    if not theory or not practice:
        all_task_messages = workflow.environment.get_task_messages(
            tasks=["content_generation_theory", "content_generation_practice"],
            n=None,
            include_inputs=False,
        )
        combined_output = "\n\n".join(str(msg) for msg in all_task_messages)
        if not theory:
            theory = extract_section_content(combined_output, "theory_content")
        if not practice:
            practice = extract_section_content(combined_output, "practice_content")

    if not theory and not practice:
        raise LessonPlanError("教案工作流执行完成，但未提取到 theory_content / practice_content。")
    else:
        final_markdown = assemble_lesson_plan(req, theory, practice)

    _ensure_not_failed_output(final_markdown, workflow=workflow)

    return final_markdown


def generate_lesson_plan_artifacts(
    req: LessonPlanRequest,
    *,
    include_content: bool = False,
) -> dict[str, Any]:
    """Generate a lesson plan and save markdown plus metadata artifacts."""

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    lesson_plan = execute_workflow_logic(req)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify_course_name(req.course)
    lesson_plan_path = RESULTS_DIR / f"{timestamp}_{slug}.md"
    metadata_path = RUNS_DIR / f"lesson_plan_run_{timestamp}_{slug}.json"
    lesson_plan_path.write_text(lesson_plan, encoding="utf-8")

    preview = _build_preview(lesson_plan)
    metadata = {
        "status": "success",
        "generated_at": datetime.now().isoformat(),
        "request": req.model_dump(),
        "workflow_path": str(WORKFLOW_PATH),
        "lesson_plan_path": str(lesson_plan_path),
        "metadata_path": str(metadata_path),
        "lesson_plan_preview": preview,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    result = {
        "status": "success",
        "lesson_plan_path": str(lesson_plan_path),
        "metadata_path": str(metadata_path),
        "lesson_plan_preview": preview,
        "request": req.model_dump(),
    }
    if include_content:
        result["lesson_plan"] = lesson_plan
    return result
