"""Migrated exam-generation service used by CLI and MCP entrypoints."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
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
WORKFLOW_PATH = PACKAGE_DIR / "workflows" / "examination_generation_workflow.json"
DB_PATH = PROJECT_ROOT / "data" / "faiss_db.sqlite"
RESULTS_DIR = PROJECT_ROOT / "results" / "exams"
RUNS_DIR = PROJECT_ROOT / "data" / "exam_runs"

QWEN_MODEL_NAME = "QWen"
DEEPSEEK_MODEL_NAME = "DeepSeek"
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
QUESTION_TYPE_LABELS = {
    "single_choice_questions": "单选题",
    "multiple_choice_questions": "多选题",
    "true_false_questions": "判断题",
    "fill_blank_questions": "填空题",
    "short_answer_questions": "简答题",
    "programming_questions": "编程题",
}
QUESTION_COUNT_FIELDS = [
    "single_choice_num",
    "multiple_choice_num",
    "true_false_num",
    "fill_blank_num",
    "short_answer_num",
    "programming_num",
]
QUESTION_RESULT_KEYS = [
    "single_choice_questions",
    "multiple_choice_questions",
    "true_false_questions",
    "fill_blank_questions",
    "short_answer_questions",
    "programming_questions",
]

load_dotenv(PROJECT_ROOT / ".env")

_THREAD_POOL = ThreadPoolExecutor(max_workers=8)
_RAG_TOOLKIT = None


class ExamGenerationError(RuntimeError):
    """Base error for exam generation."""

    error_type = "runtime_error"

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": "error",
            "error_type": self.error_type,
            "message": str(self),
        }


class ExamGenerationInputError(ExamGenerationError):
    """Raised when request inputs are incomplete or invalid."""

    error_type = "validation_error"

    def __init__(self, message: str, missing_fields: list[str] | None = None) -> None:
        super().__init__(message)
        self.missing_fields = missing_fields or []

    def to_payload(self) -> dict[str, Any]:
        payload = super().to_payload()
        payload["missing_fields"] = self.missing_fields
        return payload


class ExamRequest(BaseModel):
    """Normalized input for migrated exam generation."""

    subject: str = Field(..., description="学科或课程名称")
    knowledge_bases: str = Field(..., description="考查知识点")
    constraint: str = Field("", description="附加要求")
    language: str = Field("Chinese", description="生成语言")
    single_choice_num: int = Field(3, ge=0, description="单选题数量")
    multiple_choice_num: int = Field(3, ge=0, description="多选题数量")
    true_false_num: int = Field(3, ge=0, description="判断题数量")
    fill_blank_num: int = Field(2, ge=0, description="填空题数量")
    short_answer_num: int = Field(2, ge=0, description="简答题数量")
    programming_num: int = Field(1, ge=0, description="编程题数量")
    easy_percentage: int = Field(30, ge=0, le=100, description="简单题比例")
    medium_percentage: int = Field(50, ge=0, le=100, description="中等题比例")
    hard_percentage: int = Field(20, ge=0, le=100, description="困难题比例")
    use_rag: bool = Field(False, description="是否开启 RAG")
    model_type: str = Field(QWEN_MODEL_NAME, description="模型类型: QWen / DeepSeek")

    @field_validator("subject", "constraint", "language", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("knowledge_bases", mode="before")
    @classmethod
    def _normalize_knowledge_bases(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return "，".join(str(item).strip() for item in value if str(item).strip())
        return str(value).strip()

    @field_validator("model_type")
    @classmethod
    def _validate_model_type(cls, value: str) -> str:
        if value not in {QWEN_MODEL_NAME, DEEPSEEK_MODEL_NAME}:
            raise ValueError("model_type 仅支持 QWen 或 DeepSeek")
        return value

    @model_validator(mode="after")
    def _validate_counts_and_percentages(self) -> "ExamRequest":
        total_questions = sum(getattr(self, field) for field in QUESTION_COUNT_FIELDS)
        if total_questions <= 0:
            raise ValueError("至少需要生成一种题型，且数量大于 0。")

        ratio_sum = self.easy_percentage + self.medium_percentage + self.hard_percentage
        if ratio_sum != 100:
            raise ValueError("难度比例之和必须等于 100。")

        return self


class ParallelWorkFlow:  # Thin adapter over EvoAgentX WorkFlow
    """Parallel workflow runner for exam generation."""

    def __init__(self, thread_pool: ThreadPoolExecutor, node_callback=None, **kwargs):
        from evoagentx.workflow import WorkFlow

        self._workflow = WorkFlow(**kwargs)
        self.graph = self._workflow.graph
        self.environment = self._workflow.environment
        self.agent_manager = self._workflow.agent_manager
        self.llm = self._workflow.llm
        self.thread_pool = thread_pool
        self.node_callback = node_callback

    def init_module(self) -> None:
        self._workflow.init_module()

    def _run_node_sync(self, task) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._workflow.execute_task(task))
        finally:
            loop.close()

    def _extract_questions_directly(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        exec_data = self.environment.get_all_execution_data()
        for key in QUESTION_RESULT_KEYS:
            value = exec_data.get(key, [])
            if isinstance(value, str):
                value = self._parse_questions_from_text(value, key)
            result[key] = value if isinstance(value, list) else []
        return result

    @staticmethod
    def _try_parse_json_array(text: str) -> Optional[list[dict[str, Any]]]:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "[":
                continue
            try:
                parsed, _ = decoder.raw_decode(text[index:])
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                continue
        return None

    def _parse_questions_from_text(self, text: str, key: str) -> list[dict[str, Any]]:
        if not text:
            return []
        section_pattern = rf"##\s*{re.escape(key)}\s*(\[[\s\S]*?\])"
        section_match = re.search(section_pattern, text)
        if section_match:
            parsed = self._try_parse_json_array(section_match.group(1))
            if parsed is not None:
                return parsed
        fallback = self._try_parse_json_array(text)
        return fallback if fallback is not None else []

    async def async_execute(self, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        from evoagentx.core.message import Message, MessageType
        from evoagentx.workflow.environment import TrajectoryState
        from evoagentx.workflow.workflow_graph import WorkFlowNodeState

        goal = self.graph.goal
        prepared_inputs = self._workflow._prepare_inputs(inputs or {})
        self._workflow._validate_workflow_structure(inputs=prepared_inputs)
        self.environment.update(
            message=Message(content=prepared_inputs, msg_type=MessageType.INPUT, wf_goal=goal),
            state=TrajectoryState.COMPLETED,
        )

        failed = False
        while not self.graph.is_complete and not failed:
            candidate_node_names = self.graph.get_next_candidate_nodes()
            if not candidate_node_names:
                if not self.graph.is_complete:
                    break
                break

            tasks = []
            for node_name in candidate_node_names:
                node = self.graph.get_node(node_name)
                self.graph.set_node_status(node, WorkFlowNodeState.RUNNING)
                if self.node_callback:
                    self.node_callback("node_start", node_name)
                loop = asyncio.get_running_loop()
                task_future = loop.run_in_executor(self.thread_pool, self._run_node_sync, node)
                tasks.append((node_name, task_future))

            if tasks:
                results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)
                for (node_name, _), result in zip(tasks, results):
                    if isinstance(result, Exception):
                        failed = True
                        self.environment.update(
                            message=Message(content=str(result), msg_type=MessageType.ERROR, wf_goal=goal),
                            state=TrajectoryState.FAILED,
                            error=str(result),
                        )
                        if self.node_callback:
                            self.node_callback("node_error", node_name)
                    else:
                        if self.node_callback:
                            self.node_callback("node_end", node_name)

        if failed:
            return {"status": "failed", "error": _extract_failed_step_error(self._workflow) or "Workflow Execution Failed"}

        return {"output": self._extract_questions_directly()}


def _extract_validation_fields(exc: ValidationError) -> list[str]:
    fields: list[str] = []
    for error in exc.errors():
        loc = error.get("loc", ())
        if loc:
            fields.append(str(loc[0]))
    return sorted(set(fields))


def build_request(payload: dict[str, Any] | None) -> ExamRequest:
    """Validate a raw payload and return a normalized request object."""

    payload = dict(payload or {})
    subject = str(payload.get("subject", "") or "").strip()
    knowledge_bases = payload.get("knowledge_bases", "")
    normalized_knowledge = ""
    if isinstance(knowledge_bases, (list, tuple)):
        normalized_knowledge = "，".join(str(item).strip() for item in knowledge_bases if str(item).strip())
    else:
        normalized_knowledge = str(knowledge_bases or "").strip()

    missing_fields: list[str] = []
    if not subject:
        missing_fields.append("subject")
    if not normalized_knowledge:
        missing_fields.append("knowledge_bases")
    if missing_fields:
        raise ExamGenerationInputError(
            "缺少必填字段：需要提供 subject 和 knowledge_bases。",
            missing_fields=missing_fields,
        )

    try:
        return ExamRequest(**payload)
    except ValidationError as exc:
        raise ExamGenerationInputError(
            "输入字段格式不合法。",
            missing_fields=_extract_validation_fields(exc),
        ) from exc


def _require_env_var(name: str, model_type: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ExamGenerationError(f"{model_type} 模型缺少环境变量 {name}。")
    return value


def init_llm(model_type: str):
    """Initialize the configured non-thinking LLM."""

    try:
        from evoagentx.models import AliyunLLM, AliyunLLMConfig, LiteLLM, LiteLLMConfig
    except ImportError as exc:
        raise ExamGenerationError("EvoAgentX 未安装，请先执行 pip install -r requirements.txt。") from exc

    if model_type == DEEPSEEK_MODEL_NAME:
        api_key = _require_env_var("DEEPSEEK_API_KEY", model_type)
        return LiteLLM(
            config=LiteLLMConfig(
                model="deepseek/deepseek-chat",
                deepseek_key=api_key,
                base_url=os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL),
                stream=False,
                max_tokens=8000,
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


def get_rag_toolkit():
    """Lazily initialize the migrated RAG toolkit."""

    global _RAG_TOOLKIT

    if not DB_PATH.exists():
        raise ExamGenerationError(
            f"已开启 RAG，但本地知识库不存在：{DB_PATH}。请先准备知识库后再启用 use_rag。"
        )

    if _RAG_TOOLKIT is None:
        try:
            from eduagent_lesson_plan.faiss_toolkit import FaissToolkit
        except ImportError as exc:
            raise ExamGenerationError(
                "RAG 工具箱导入失败。请确认可选依赖已安装，例如 sentence-transformers。"
            ) from exc

        try:
            logger.info("正在初始化试卷 RAG 工具箱...")
            _RAG_TOOLKIT = FaissToolkit(db_path=str(DB_PATH))
        except ModuleNotFoundError as exc:
            raise ExamGenerationError(
                f"RAG 依赖缺失：{exc.name}。若暂不需要知识库增强，请关闭 use_rag。"
            ) from exc
        except Exception as exc:
            raise ExamGenerationError(f"RAG 工具箱初始化失败：{exc}") from exc

    return _RAG_TOOLKIT


def build_rag_queries(subject: str, knowledge: str, constraint: str) -> list[dict[str, str]]:
    queries: list[dict[str, str]] = []
    if subject:
        queries.append({"field": "学科背景", "query": f"关于{subject}的核心概念和基础知识"})
    if knowledge:
        queries.append({"field": "考查知识点", "query": f"详细解释以下知识点：{knowledge}"})
    if constraint:
        queries.append({"field": "出题约束", "query": f"关于{constraint}的相关要求和背景"})
    if not queries:
        queries.append({"field": "综合检索", "query": f"{subject} {knowledge}".strip()})
    return queries


def build_rag_context(req: ExamRequest) -> str:
    """Query the optional FAISS knowledge base and return a merged context string."""

    if not req.use_rag:
        logger.info(">>> 用户未开启 RAG，跳过检索步骤")
        return ""

    toolkit = get_rag_toolkit()
    query_tool = toolkit.get_tool("faiss_query")
    if query_tool is None:
        raise ExamGenerationError("RAG 工具箱缺少 faiss_query 能力。")

    sections: list[str] = []
    for item in build_rag_queries(req.subject, req.knowledge_bases, req.constraint):
        logger.info("RAG 查询词(%s): [%s]", item["field"], item["query"])
        search_results = query_tool(query=item["query"], top_k=3)
        if search_results.get("success"):
            results = search_results.get("data", {}).get("results", [])
            if results:
                docs = [f"资料{index}: {res.get('content', '').strip()}" for index, res in enumerate(results, 1)]
                sections.append(f"【{item['field']}参考资料】\n" + "\n".join(docs))
    return "\n\n".join(sections)


def merge_results(
    raw_output: dict[str, list[dict[str, Any]]],
    allowed_keys: Optional[list[str]] = None,
    limits: Optional[dict[str, int]] = None,
) -> list[dict[str, Any]]:
    final_list: list[dict[str, Any]] = []
    for key, value in raw_output.items():
        if allowed_keys is not None and key not in allowed_keys:
            continue
        if isinstance(value, list):
            if limits and key in limits:
                final_list.extend(value[: max(limits[key], 0)])
            else:
                final_list.extend(value)
    return final_list


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


def _build_result_key_limits(req: ExamRequest) -> tuple[list[str], dict[str, int]]:
    key_map = [
        ("single_choice_questions", req.single_choice_num),
        ("multiple_choice_questions", req.multiple_choice_num),
        ("true_false_questions", req.true_false_num),
        ("fill_blank_questions", req.fill_blank_num),
        ("short_answer_questions", req.short_answer_num),
        ("programming_questions", req.programming_num),
    ]
    allowed_keys: list[str] = []
    limits: dict[str, int] = {}
    for key, count in key_map:
        if count and count > 0:
            allowed_keys.append(key)
            limits[key] = count
    return allowed_keys, limits


async def generate_exam_questions(req: ExamRequest) -> dict[str, Any]:
    """Run the migrated exam workflow and return structured question data."""

    try:
        from evoagentx.agents import AgentManager
        from evoagentx.workflow import WorkFlowGraph
    except ImportError as exc:
        raise ExamGenerationError("EvoAgentX 未安装，请先执行 pip install -r requirements.txt。") from exc

    if not WORKFLOW_PATH.exists():
        raise ExamGenerationError(f"找不到工作流文件：{WORKFLOW_PATH}")

    llm = init_llm(req.model_type)
    rag_context = build_rag_context(req)
    workflow_graph = WorkFlowGraph.from_file(str(WORKFLOW_PATH))
    agent_manager = AgentManager()
    agent_manager.add_agents_from_workflow(workflow_graph, llm_config=llm.config)

    workflow = ParallelWorkFlow(graph=workflow_graph, agent_manager=agent_manager, llm=llm, thread_pool=_THREAD_POOL)
    workflow.init_module()

    input_data = {key: str(value) for key, value in req.model_dump().items()}
    input_data["rag_context"] = rag_context
    input_data["goal"] = f"Generate exam for {req.subject}"

    try:
        result = await workflow.async_execute(input_data)
    except Exception as exc:
        detail = _extract_failed_step_error(workflow._workflow) or str(exc)
        raise ExamGenerationError(f"试卷工作流执行失败：{detail}") from exc

    if not isinstance(result, dict):
        raise ExamGenerationError(f"试卷工作流返回了非字典结果：{type(result).__name__}")

    if result.get("status") == "failed":
        raise ExamGenerationError(f"试卷工作流执行失败：{result.get('error') or 'Workflow Execution Failed'}")

    output = result.get("output", {})
    if not isinstance(output, dict):
        raise ExamGenerationError("试卷工作流没有返回结构化题目结果。")

    allowed_keys, limits = _build_result_key_limits(req)
    questions = merge_results(output, allowed_keys=allowed_keys, limits=limits)
    if not questions:
        raise ExamGenerationError("试卷工作流执行完成，但未提取到任何题目。")

    return {
        "questions": questions,
        "raw_output": output,
    }


def _slugify_subject(subject: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")
    return slug[:48] if slug else "exam"


def _build_exam_preview(questions: list[dict[str, Any]]) -> str:
    counts: dict[int, int] = {}
    for question in questions:
        question_type = int(question.get("type", 0) or 0)
        counts[question_type] = counts.get(question_type, 0) + 1
    parts = []
    if counts.get(1):
        parts.append(f"单选{counts[1]}题")
    if counts.get(2):
        parts.append(f"多选{counts[2]}题")
    if counts.get(3):
        parts.append(f"判断{counts[3]}题")
    if counts.get(4):
        parts.append(f"填空{counts[4]}题")
    if counts.get(5):
        parts.append(f"简答{counts[5]}题")
    if counts.get(6):
        parts.append(f"编程{counts[6]}题")
    summary = "，".join(parts) if parts else "未统计到题型"
    return f"共 {len(questions)} 道题：{summary}"


def _render_question_markdown(subject: str, questions: list[dict[str, Any]]) -> str:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for question in questions:
        qtype = int(question.get("type", 0) or 0)
        grouped.setdefault(qtype, []).append(question)

    lines = [f"# 《{subject}》试卷", ""]
    label_by_type = {1: "单选题", 2: "多选题", 3: "判断题", 4: "填空题", 5: "简答题", 6: "编程题"}
    for qtype in sorted(grouped):
        lines.extend([f"## {label_by_type.get(qtype, f'题型{qtype}')}", ""])
        for index, question in enumerate(grouped[qtype], 1):
            lines.append(f"{index}. {question.get('name', '')}")
            options = question.get("options", [])
            if isinstance(options, list):
                for option_index, option in enumerate(options):
                    option_text = option.get("answer", "") if isinstance(option, dict) else str(option)
                    if option_text:
                        prefix = chr(ord("A") + option_index) if qtype in {1, 2} else "-"
                        lines.append(f"   {prefix}. {option_text}")
            analysis = question.get("analysis", "")
            if analysis:
                lines.append(f"   解析：{analysis}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def generate_exam_artifacts(req: ExamRequest) -> dict[str, Any]:
    """Generate exam questions and save JSON, markdown, and metadata artifacts."""

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    exam_bundle = asyncio.run(generate_exam_questions(req))
    questions = exam_bundle["questions"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify_subject(req.subject)
    json_path = RESULTS_DIR / f"{timestamp}_{slug}.json"
    md_path = RESULTS_DIR / f"{timestamp}_{slug}.md"
    metadata_path = RUNS_DIR / f"exam_run_{timestamp}_{slug}.json"

    json_path.write_text(json.dumps({"questions": questions}, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_question_markdown(req.subject, questions), encoding="utf-8")

    preview = _build_exam_preview(questions)
    metadata = {
        "status": "success",
        "generated_at": datetime.now().isoformat(),
        "request": req.model_dump(),
        "workflow_path": str(WORKFLOW_PATH),
        "result_json_path": str(json_path),
        "result_md_path": str(md_path),
        "metadata_path": str(metadata_path),
        "question_count": len(questions),
        "preview": preview,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "success",
        "result_json_path": str(json_path),
        "result_md_path": str(md_path),
        "metadata_path": str(metadata_path),
        "question_count": len(questions),
        "preview": preview,
        "request": req.model_dump(),
    }
