"""Unified capability schema, routing, and dispatch helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from eduagent_exam import ExamGenerationError, ExamGenerationInputError, build_request as build_exam_request, generate_exam_artifacts
from eduagent_lesson_plan import (
    LessonPlanError,
    LessonPlanInputError,
    build_request as build_lesson_plan_request,
    generate_lesson_plan_artifacts,
)
from eduagent_ppt import PPTGenerationError, PPTGenerationInputError, build_request as build_ppt_request, generate_ppt_artifacts


@dataclass(frozen=True)
class FieldSpec:
    """Metadata describing one normalized input field."""

    name: str
    label: str
    field_type: str
    description: str
    required: bool = False
    default: Any = None
    aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "type": self.field_type,
            "description": self.description,
            "required": self.required,
            "default": self.default,
            "aliases": list(self.aliases),
        }


@dataclass(frozen=True)
class RequiredGroupSpec:
    """A set of fields where at least one must be provided."""

    name: str
    label: str
    fields: tuple[str, ...]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "fields": list(self.fields),
            "description": self.description,
        }


@dataclass(frozen=True)
class CapabilitySpec:
    """Normalized capability definition for routing and dispatch."""

    key: str
    label: str
    description: str
    keywords: tuple[str, ...]
    field_specs: tuple[FieldSpec, ...]
    required_groups: tuple[RequiredGroupSpec, ...] = ()
    defaults: dict[str, Any] = field(default_factory=dict)
    artifact_keys: tuple[str, ...] = ()
    metric_keys: tuple[str, ...] = ()
    preview_key: str | None = None
    build_request: Callable[[dict[str, Any] | None], Any] | None = None
    execute: Callable[[Any], dict[str, Any]] | None = None
    input_error_cls: type[Exception] = Exception
    runtime_error_cls: type[Exception] = Exception

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.key,
            "label": self.label,
            "description": self.description,
            "fields": [item.to_dict() for item in self.field_specs],
            "required_groups": [item.to_dict() for item in self.required_groups],
            "defaults": dict(self.defaults),
            "artifact_keys": list(self.artifact_keys),
            "metric_keys": list(self.metric_keys),
            "preview_key": self.preview_key,
        }


class CapabilityResolutionError(ValueError):
    """Raised when a request cannot be mapped to a known capability."""


class CapabilityDispatchError(RuntimeError):
    """Raised when a capability cannot be executed."""


LESSON_PLAN_SPEC = CapabilitySpec(
    key="lesson_plan",
    label="教案生成",
    description="生成课程教案与配套 metadata。",
    keywords=("教案", "教学设计", "lesson plan", "教学方案"),
    field_specs=(
        FieldSpec("course", "课程名称", "string", "课程或学科名称。", required=True),
        FieldSpec("units", "单元名称", "string", "课程所属单元。"),
        FieldSpec("lessons", "课时名称", "string", "具体课时。"),
        FieldSpec("constraint", "附加要求", "string", "风格、难度或教学约束。", default=""),
        FieldSpec("word_limit", "字数要求", "integer", "教案期望字数。", default=2000),
        FieldSpec("model_type", "模型类型", "string", "可选 QWen 或 DeepSeek。", default="QWen"),
        FieldSpec("use_rag", "启用 RAG", "boolean", "是否启用本地知识库增强。", default=False),
    ),
    required_groups=(
        RequiredGroupSpec(
            name="teaching_scope",
            label="教学范围",
            fields=("units", "lessons"),
            description="至少提供单元或课时之一。",
        ),
    ),
    defaults={"word_limit": 2000, "model_type": "QWen", "use_rag": False},
    artifact_keys=("lesson_plan_path", "metadata_path"),
    preview_key="lesson_plan_preview",
    build_request=lambda payload: build_lesson_plan_request(payload),
    execute=lambda request: generate_lesson_plan_artifacts(request),
    input_error_cls=LessonPlanInputError,
    runtime_error_cls=LessonPlanError,
)

EXAM_SPEC = CapabilitySpec(
    key="exam",
    label="试卷生成",
    description="生成试卷 JSON、Markdown 和 metadata。",
    keywords=("试卷", "考试", "出题", "题库", "测验", "练习题"),
    field_specs=(
        FieldSpec("subject", "学科名称", "string", "学科、课程或考试名称。", required=True),
        FieldSpec("knowledge_bases", "考查知识点", "string", "知识点或章节范围。", required=True),
        FieldSpec("constraint", "附加要求", "string", "题型风格或考试约束。", default=""),
        FieldSpec("language", "出题语言", "string", "默认 Chinese。", default="Chinese"),
        FieldSpec("single_choice_num", "单选题数量", "integer", "单选题数量。", default=3),
        FieldSpec("multiple_choice_num", "多选题数量", "integer", "多选题数量。", default=3),
        FieldSpec("true_false_num", "判断题数量", "integer", "判断题数量。", default=3),
        FieldSpec("fill_blank_num", "填空题数量", "integer", "填空题数量。", default=2),
        FieldSpec("short_answer_num", "简答题数量", "integer", "简答题数量。", default=2),
        FieldSpec("programming_num", "编程题数量", "integer", "编程题数量。", default=1),
        FieldSpec("easy_percentage", "简单题比例", "integer", "百分比，默认 30。", default=30),
        FieldSpec("medium_percentage", "中等题比例", "integer", "百分比，默认 50。", default=50),
        FieldSpec("hard_percentage", "困难题比例", "integer", "百分比，默认 20。", default=20),
        FieldSpec("model_type", "模型类型", "string", "可选 QWen 或 DeepSeek。", default="QWen"),
        FieldSpec("use_rag", "启用 RAG", "boolean", "是否启用本地知识库增强。", default=False),
    ),
    defaults={
        "language": "Chinese",
        "single_choice_num": 3,
        "multiple_choice_num": 3,
        "true_false_num": 3,
        "fill_blank_num": 2,
        "short_answer_num": 2,
        "programming_num": 1,
        "easy_percentage": 30,
        "medium_percentage": 50,
        "hard_percentage": 20,
        "model_type": "QWen",
        "use_rag": False,
    },
    artifact_keys=("result_json_path", "result_md_path", "metadata_path"),
    metric_keys=("question_count",),
    preview_key="preview",
    build_request=lambda payload: build_exam_request(payload),
    execute=lambda request: generate_exam_artifacts(request),
    input_error_cls=ExamGenerationInputError,
    runtime_error_cls=ExamGenerationError,
)

PPT_SPEC = CapabilitySpec(
    key="ppt",
    label="PPT 生成",
    description="生成教学 PPT Markdown 或 PPTX 产物。",
    keywords=("ppt", "课件", "幻灯片", "slides", "演示文稿"),
    field_specs=(
        FieldSpec("course", "课程名称", "string", "课程或学科名称。", required=True),
        FieldSpec("units", "单元列表", "list[string]", "一个或多个单元。"),
        FieldSpec("lessons", "课时列表", "list[string]", "一个或多个课时。"),
        FieldSpec("knowledge_points", "知识点", "list[string]", "PPT 覆盖的知识点。"),
        FieldSpec("constraint", "附加要求", "string", "展示风格或限制条件。", default=""),
        FieldSpec("page_limit", "页数限制", "integer", "不少于 6 页。"),
        FieldSpec("model_type", "模型类型", "string", "可选 QWen 或 DeepSeek。", default="QWen"),
        FieldSpec("use_rag", "启用 RAG", "boolean", "是否启用本地知识库增强。", default=False),
        FieldSpec("output_mode", "输出模式", "string", "可选 md 或 ppt。", default="ppt"),
    ),
    required_groups=(
        RequiredGroupSpec(
            name="content_scope",
            label="内容范围",
            fields=("units", "lessons", "knowledge_points"),
            description="至少提供单元、课时、知识点之一。",
        ),
    ),
    defaults={"model_type": "QWen", "use_rag": False, "output_mode": "ppt"},
    artifact_keys=("markdown_path", "pptx_path", "metadata_path"),
    preview_key="preview",
    build_request=lambda payload: build_ppt_request(payload),
    execute=lambda request: generate_ppt_artifacts(request),
    input_error_cls=PPTGenerationInputError,
    runtime_error_cls=PPTGenerationError,
)

CAPABILITY_SPECS: dict[str, CapabilitySpec] = {
    LESSON_PLAN_SPEC.key: LESSON_PLAN_SPEC,
    EXAM_SPEC.key: EXAM_SPEC,
    PPT_SPEC.key: PPT_SPEC,
}

TASK_KEYWORD_PRIORITY = ("ppt", "exam", "lesson_plan")
PAYLOAD_HINTS: tuple[tuple[str, str], ...] = (
    ("knowledge_points", "ppt"),
    ("page_limit", "ppt"),
    ("output_mode", "ppt"),
    ("subject", "exam"),
    ("knowledge_bases", "exam"),
    ("single_choice_num", "exam"),
    ("multiple_choice_num", "exam"),
    ("true_false_num", "exam"),
    ("fill_blank_num", "exam"),
    ("short_answer_num", "exam"),
    ("programming_num", "exam"),
)


def describe_capabilities(capability: str | None = None) -> dict[str, Any]:
    """Return one capability schema or all schemas."""

    if capability:
        spec = CAPABILITY_SPECS.get(capability)
        if spec is None:
            raise CapabilityResolutionError(f"未知能力：{capability}")
        return spec.to_dict()
    return {"capabilities": [spec.to_dict() for spec in CAPABILITY_SPECS.values()]}


def resolve_capability(
    task: str | None = None,
    payload: dict[str, Any] | None = None,
    capability: str | None = None,
) -> str:
    """Resolve capability from an explicit choice, payload hints, or task text."""

    if capability:
        if capability not in CAPABILITY_SPECS:
            raise CapabilityResolutionError(f"未知能力：{capability}")
        return capability

    payload = dict(payload or {})
    for field_name, matched_capability in PAYLOAD_HINTS:
        value = payload.get(field_name)
        if value not in (None, "", [], ()):
            return matched_capability

    if payload.get("course") not in (None, ""):
        if payload.get("knowledge_points") not in (None, "", [], ()):
            return "ppt"
        if payload.get("output_mode") not in (None, ""):
            return "ppt"
        return "lesson_plan"

    task_text = str(task or "").strip().lower()
    if task_text:
        for capability_key in TASK_KEYWORD_PRIORITY:
            spec = CAPABILITY_SPECS[capability_key]
            if any(keyword.lower() in task_text for keyword in spec.keywords):
                return capability_key

    raise CapabilityResolutionError(
        "无法识别任务能力，请显式传入 capability，或提供更明确的任务描述/字段。"
    )


def _extract_artifacts(result: dict[str, Any], artifact_keys: tuple[str, ...]) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for key in artifact_keys:
        if key in result:
            artifacts[key] = result[key]
    return artifacts


def _extract_metrics(result: dict[str, Any], metric_keys: tuple[str, ...]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for key in metric_keys:
        if key in result:
            metrics[key] = result[key]
    return metrics


def dispatch_capability(
    *,
    task: str | None = None,
    payload: dict[str, Any] | None = None,
    capability: str | None = None,
) -> dict[str, Any]:
    """Validate inputs, execute the capability, and normalize the response."""

    resolved_capability = resolve_capability(task=task, payload=payload, capability=capability)
    spec = CAPABILITY_SPECS[resolved_capability]
    raw_payload = dict(payload or {})

    try:
        if spec.build_request is None or spec.execute is None:
            raise CapabilityDispatchError(f"能力 {resolved_capability} 尚未绑定执行器。")
        request = spec.build_request(raw_payload)
        result = spec.execute(request)
    except spec.input_error_cls as exc:
        return {
            "status": "error",
            "capability": resolved_capability,
            "error_type": "validation_error",
            "message": str(exc),
            "missing_fields": list(getattr(exc, "missing_fields", [])),
            "schema": spec.to_dict(),
        }
    except spec.runtime_error_cls as exc:
        return {
            "status": "error",
            "capability": resolved_capability,
            "error_type": "runtime_error",
            "message": str(exc),
            "schema": spec.to_dict(),
        }

    request_payload = request.model_dump() if hasattr(request, "model_dump") else dict(request)
    return {
        "status": "success",
        "capability": resolved_capability,
        "request": request_payload,
        "artifacts": _extract_artifacts(result, spec.artifact_keys),
        "metrics": _extract_metrics(result, spec.metric_keys),
        "preview": result.get(spec.preview_key) if spec.preview_key else None,
        "result": result,
    }
