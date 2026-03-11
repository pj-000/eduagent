"""Dual-layer reviewer for direct EduAgent capabilities."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .llm_planner import PlannerLLMError, build_planner_llm


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REVIEW_RUNS_DIR = PROJECT_ROOT / "data" / "review_runs"

CANONICAL_METRICS = {
    "1.1 指令遵循与任务完成": "1.1 指令遵循与任务完成",
    "1.3 内容相关性与范围控制": "1.3 内容相关性与范围控制",
    "2.1 基础事实准确性": "2.1 基础事实准确性",
    "2.2 领域知识专业性": "2.2 领域知识专业性",
    "2.5 题目整体布局与知识点覆盖": "2.5 题目整体布局与知识点覆盖",
    "3.1 清晰易懂与表达启发": "3.1 清晰易懂与表达启发",
}

METRIC_ALIASES = {
    "1指令遵循与任务完成": "1.1 指令遵循与任务完成",
    "1.1指令遵循与任务完成": "1.1 指令遵循与任务完成",
}
METRIC_ALIASES.update(
    {
        "1.3内容相关性与范围控制": "1.3 内容相关性与范围控制",
        "3内容相关性与范围控制": "1.3 内容相关性与范围控制",
        "5基础事实准确性": "2.1 基础事实准确性",
        "2.1基础事实准确性": "2.1 基础事实准确性",
        "6领域知识专业性": "2.2 领域知识专业性",
        "2.2领域知识专业性": "2.2 领域知识专业性",
        "9题目整体布局与知识点覆盖": "2.5 题目整体布局与知识点覆盖",
        "2.5题目整体布局与知识点覆盖": "2.5 题目整体布局与知识点覆盖",
        "10清晰易懂与表达启发": "3.1 清晰易懂与表达启发",
        "3.1清晰易懂与表达启发": "3.1 清晰易懂与表达启发",
    }
)

DEFAULT_REVIEW_METRICS = {
    "lesson_plan": [
        "1.1 指令遵循与任务完成",
        "1.3 内容相关性与范围控制",
        "2.1 基础事实准确性",
        "2.2 领域知识专业性",
        "3.1 清晰易懂与表达启发",
    ],
    "ppt": [
        "1.1 指令遵循与任务完成",
        "1.3 内容相关性与范围控制",
        "2.1 基础事实准确性",
        "2.2 领域知识专业性",
        "3.1 清晰易懂与表达启发",
    ],
    "exam": [
        "1.1 指令遵循与任务完成",
        "1.3 内容相关性与范围控制",
        "2.1 基础事实准确性",
        "2.2 领域知识专业性",
        "2.5 题目整体布局与知识点覆盖",
        "3.1 清晰易懂与表达启发",
    ],
}

LESSON_PLAN_GOAL_KEYWORDS = ("教学目标", "学习目标", "目标")
LESSON_PLAN_PROCESS_KEYWORDS = ("教学过程", "教学活动", "过程")

EXAM_COUNT_FIELDS = (
    "single_choice_num",
    "multiple_choice_num",
    "true_false_num",
    "fill_blank_num",
    "short_answer_num",
    "programming_num",
)


def normalize_metric_name(name: str) -> str:
    text = str(name or "").strip()
    key = re.sub(r"\s+", "", text)
    if key in METRIC_ALIASES:
        return METRIC_ALIASES[key]
    if text in CANONICAL_METRICS:
        return text
    return text


def normalize_metric_names(metrics: list[str] | tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    for metric in metrics:
        canonical = normalize_metric_name(str(metric))
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized


def get_default_review_metrics(capability: str) -> list[str]:
    return list(DEFAULT_REVIEW_METRICS.get(capability, []))


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
    raise PlannerLLMError("LLM reviewer 输出中未找到合法 JSON 对象。")


def _read_text(path_value: str | None) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _read_json(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        return data
    return {}


def _heading_count(markdown: str) -> int:
    return len(re.findall(r"(?m)^#\s+", markdown))


def _title_count(markdown: str) -> int:
    return len(re.findall(r"(?m)^#{1,6}\s+", markdown))


def _score_from_findings(blocking_issues: list[str], advisories: list[str]) -> int:
    return max(0, 100 - len(blocking_issues) * 20 - len(advisories) * 5)


def _build_rule_result(
    *,
    status: str,
    blocking_issues: list[str],
    advisories: list[str],
    signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "score": _score_from_findings(blocking_issues, advisories),
        "blocking_issues": blocking_issues,
        "advisories": advisories,
        "signals": dict(signals or {}),
    }


def _review_lesson_plan_rules(request_payload: dict[str, Any], capability_result: dict[str, Any]) -> dict[str, Any]:
    artifacts = capability_result.get("artifacts", {})
    content = _read_text(artifacts.get("lesson_plan_path"))
    blocking_issues: list[str] = []
    advisories: list[str] = []
    signals = {
        "char_count": len(content),
        "heading_count": _title_count(content),
    }

    if not artifacts.get("lesson_plan_path") or not Path(str(artifacts.get("lesson_plan_path"))).exists():
        blocking_issues.append("lesson_plan_artifact_missing")
    if not content.strip():
        blocking_issues.append("lesson_plan_empty")
    if len(content) < 400:
        blocking_issues.append("lesson_plan_too_short")
    if _title_count(content) < 3:
        blocking_issues.append("lesson_plan_heading_count_too_low")
    if not any(keyword in content for keyword in LESSON_PLAN_GOAL_KEYWORDS):
        blocking_issues.append("lesson_plan_goal_section_missing")
    if not any(keyword in content for keyword in LESSON_PLAN_PROCESS_KEYWORDS):
        blocking_issues.append("lesson_plan_process_section_missing")
    if request_payload.get("word_limit") and len(content) < int(request_payload["word_limit"]) * 0.3:
        advisories.append("lesson_plan_may_be_short_for_requested_word_limit")

    return _build_rule_result(
        status="fail" if blocking_issues else "pass",
        blocking_issues=blocking_issues,
        advisories=advisories,
        signals=signals,
    )


def _expected_exam_question_count(request_payload: dict[str, Any]) -> int:
    total = 0
    for field_name in EXAM_COUNT_FIELDS:
        try:
            total += int(request_payload.get(field_name, 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _question_has_correct_answer(question: dict[str, Any]) -> bool:
    for option in question.get("options", []):
        if int(option.get("is_answer", 0) or 0) == 1:
            return True
    return False


def _review_exam_rules(request_payload: dict[str, Any], capability_result: dict[str, Any]) -> dict[str, Any]:
    artifacts = capability_result.get("artifacts", {})
    payload = _read_json(artifacts.get("result_json_path"))
    questions = payload.get("questions", []) if isinstance(payload.get("questions"), list) else []
    blocking_issues: list[str] = []
    advisories: list[str] = []
    expected_count = _expected_exam_question_count(request_payload)
    signals = {
        "expected_question_count": expected_count,
        "actual_question_count": len(questions),
    }

    result_json_path = artifacts.get("result_json_path")
    if not result_json_path or not Path(str(result_json_path)).exists():
        blocking_issues.append("exam_result_json_missing")
    if not questions:
        blocking_issues.append("exam_questions_missing")
    if expected_count and questions and len(questions) != expected_count:
        blocking_issues.append("exam_question_count_mismatch")

    for index, question in enumerate(questions):
        if not str(question.get("name", "")).strip():
            blocking_issues.append(f"question_{index}_missing_name")
        if question.get("type") in (None, ""):
            blocking_issues.append(f"question_{index}_missing_type")
        if not str(question.get("analysis", "")).strip():
            blocking_issues.append(f"question_{index}_missing_analysis")

        options = question.get("options", [])
        if isinstance(options, list) and options:
            if len(options) < 2:
                blocking_issues.append(f"question_{index}_insufficient_options")
            if not _question_has_correct_answer(question):
                blocking_issues.append(f"question_{index}_missing_correct_answer")

    if questions and len(questions) < 3:
        advisories.append("exam_question_count_is_small")

    return _build_rule_result(
        status="fail" if blocking_issues else "pass",
        blocking_issues=blocking_issues,
        advisories=advisories,
        signals=signals,
    )


def _review_ppt_rules(request_payload: dict[str, Any], capability_result: dict[str, Any]) -> dict[str, Any]:
    artifacts = capability_result.get("artifacts", {})
    content = _read_text(artifacts.get("markdown_path"))
    heading_count = _heading_count(content)
    second_level_count = len(re.findall(r"(?m)^##\s+", content))
    expected_pages = max(6, int(request_payload.get("page_limit") or 0)) if request_payload.get("page_limit") else 6
    blocking_issues: list[str] = []
    advisories: list[str] = []
    signals = {
        "heading_count": heading_count,
        "second_level_heading_count": second_level_count,
        "expected_page_hint": expected_pages,
    }

    markdown_path = artifacts.get("markdown_path")
    if not markdown_path or not Path(str(markdown_path)).exists():
        blocking_issues.append("ppt_markdown_missing")
    if not content.strip():
        blocking_issues.append("ppt_markdown_empty")

    if request_payload.get("output_mode", "ppt") == "ppt":
        pptx_path = artifacts.get("pptx_path")
        if not pptx_path or not Path(str(pptx_path)).exists():
            blocking_issues.append("ppt_output_file_missing")

    soft_threshold = max(3, math.ceil(expected_pages / 2))
    if heading_count < soft_threshold:
        advisories.append("ppt_page_count_looks_low_for_requested_scope")

    return _build_rule_result(
        status="fail" if blocking_issues else "pass",
        blocking_issues=blocking_issues,
        advisories=advisories,
        signals=signals,
    )


def rule_review_capability_result(
    capability: str,
    request_payload: dict[str, Any],
    capability_result: dict[str, Any],
) -> dict[str, Any]:
    if capability == "lesson_plan":
        return _review_lesson_plan_rules(request_payload, capability_result)
    if capability == "exam":
        return _review_exam_rules(request_payload, capability_result)
    if capability == "ppt":
        return _review_ppt_rules(request_payload, capability_result)
    return _build_rule_result(
        status="fail",
        blocking_issues=[f"unsupported_capability:{capability}"],
        advisories=[],
        signals={},
    )


def _build_llm_review_prompt(
    *,
    capability: str,
    request_payload: dict[str, Any],
    capability_result: dict[str, Any],
    metrics: list[str],
    rule_review: dict[str, Any],
) -> str:
    artifacts = capability_result.get("artifacts", {})
    if capability == "lesson_plan":
        content = _read_text(artifacts.get("lesson_plan_path"))
        content_label = "教案内容"
    elif capability == "ppt":
        content = _read_text(artifacts.get("markdown_path"))
        content_label = "PPT Markdown 内容"
    else:
        content = json.dumps(_read_json(artifacts.get("result_json_path")), ensure_ascii=False, indent=2)
        content_label = "试卷 JSON 内容"

    metrics_text = json.dumps(metrics, ensure_ascii=False)
    request_text = json.dumps(request_payload, ensure_ascii=False, indent=2)
    rule_review_text = json.dumps(rule_review, ensure_ascii=False, indent=2)
    return f"""你是 EduAgent 的教育内容质量评审器。请对生成结果进行严格评审，并输出 JSON。

任务要求：
1. 只根据用户请求、规则 reviewer 结果、以及产物内容评审。
2. 必须对每个评估维度给出 1-10 分整数、理由、优化建议。
3. 如存在明显偏题、事实错误、专业性明显不足、任务未完成、内容缺失等问题，overall_status 必须为 fail。
4. blocking_issues 只写真正阻断交付的问题；advisories 写一般性优化建议。
5. retry_hint 必须是可直接追加到 constraint 的中文改写建议。
6. dimension_scores 中的 dimension 字段必须严格使用以下名称，且顺序一致：
{metrics_text}
7. 输出必须是 JSON 对象，不要输出解释性文字。

用户请求(JSON)：
{request_text}

规则 reviewer 结果(JSON)：
{rule_review_text}

产物类型：{capability}
{content_label}：
{content}

请输出以下 JSON 结构：
{{
  "dimension_scores": [
    {{
      "dimension": "维度名",
      "score": 8,
      "reason": "详细理由",
      "optimization_suggestion": "具体优化建议"
    }}
  ],
  "overall_score": 78,
  "overall_status": "pass|fail",
  "summary": "整体评价摘要",
  "blocking_issues": ["问题1"],
  "advisories": ["建议1"],
  "retry_hint": "用于下一轮自动纠偏的简洁中文指令"
}}
"""


def _coerce_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _normalize_dimension_scores(values: Any, metrics: list[str]) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    normalized: list[dict[str, Any]] = []
    used_dimensions: set[str] = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            continue
        metric_name = normalize_metric_name(str(item.get("dimension", "")).strip())
        if metric_name not in metrics:
            if index < len(metrics):
                metric_name = metrics[index]
            else:
                continue
        used_dimensions.add(metric_name)
        raw_score = item.get("score", 0)
        try:
            score = int(raw_score)
        except (TypeError, ValueError):
            score = 0
        score = min(10, max(0, score))
        normalized.append(
            {
                "dimension": metric_name,
                "score": score,
                "reason": str(item.get("reason", "")).strip(),
                "optimization_suggestion": str(item.get("optimization_suggestion", "")).strip(),
            }
        )

    for metric in metrics:
        if metric in used_dimensions:
            continue
        normalized.append(
            {
                "dimension": metric,
                "score": 0,
                "reason": "LLM reviewer 未返回该维度结果。",
                "optimization_suggestion": "补充该维度的针对性分析。",
            }
        )
    return normalized


def llm_review_capability_result(
    capability: str,
    request_payload: dict[str, Any],
    capability_result: dict[str, Any],
    rule_review: dict[str, Any],
) -> dict[str, Any]:
    metrics = get_default_review_metrics(capability)
    try:
        llm = build_planner_llm(model_type="QWen")
        prompt = _build_llm_review_prompt(
            capability=capability,
            request_payload=request_payload,
            capability_result=capability_result,
            metrics=metrics,
            rule_review=rule_review,
        )
        response = llm.generate(prompt=prompt)
        if hasattr(response, "content"):
            raw_report = str(response.content)
        elif isinstance(response, str):
            raw_report = response
        else:
            raw_report = str(response)

        parsed = _extract_json_object(raw_report)
        overall_score = parsed.get("overall_score", 0)
        try:
            normalized_score = int(overall_score)
        except (TypeError, ValueError):
            normalized_score = 0
        if 0 < normalized_score <= 10:
            normalized_score *= 10
        normalized_score = min(100, max(0, normalized_score))

        normalized_dimensions = _normalize_dimension_scores(parsed.get("dimension_scores"), metrics)
        blocking_issues = _coerce_string_list(parsed.get("blocking_issues"))
        advisories = _coerce_string_list(parsed.get("advisories"))
        overall_status = str(parsed.get("overall_status", "")).strip().lower()
        if overall_status not in {"pass", "fail"}:
            overall_status = "fail" if blocking_issues else "pass"
        retry_hint = str(parsed.get("retry_hint", "")).strip()
        if not retry_hint:
            retry_hint = "请根据评审问题补足缺失内容，修正事实或结构问题，并提升整体可读性与专业性。"

        return {
            "status": overall_status,
            "overall_score": normalized_score,
            "dimension_scores": normalized_dimensions,
            "summary": str(parsed.get("summary", "")).strip(),
            "blocking_issues": blocking_issues,
            "advisories": advisories,
            "retry_hint": retry_hint,
            "raw_report": raw_report,
            "metrics": metrics,
        }
    except Exception as exc:
        return {
            "status": "fail",
            "overall_score": 0,
            "dimension_scores": [],
            "summary": "LLM reviewer 不可用。",
            "blocking_issues": [f"llm_reviewer_unavailable: {exc}"],
            "advisories": [],
            "retry_hint": "请补充内容完整性、事实准确性和专业性后重新生成。",
            "raw_report": "",
            "metrics": metrics,
        }


def _compose_retry_hint(rule_review: dict[str, Any], llm_review: dict[str, Any]) -> str:
    retry_hint = str(llm_review.get("retry_hint", "")).strip()
    if retry_hint:
        return retry_hint
    issues = _coerce_string_list(rule_review.get("blocking_issues")) + _coerce_string_list(rule_review.get("advisories"))
    if issues:
        return "请重点修复以下问题：" + "；".join(issues[:5])
    return "请修复结构与内容问题，并提升结果质量。"


def _save_review_artifact(payload: dict[str, Any], capability: str) -> str:
    REVIEW_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REVIEW_RUNS_DIR / f"review_{timestamp}_{capability}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def review_capability_result(
    capability: str,
    request_payload: dict[str, Any],
    capability_result: dict[str, Any],
) -> dict[str, Any]:
    normalized_request = dict(request_payload or {})
    rule_review = rule_review_capability_result(capability, normalized_request, capability_result)
    llm_review = llm_review_capability_result(capability, normalized_request, capability_result, rule_review)
    review_status = "pass" if rule_review["status"] == "pass" and llm_review["status"] == "pass" else "fail"
    review_payload = {
        "capability": capability,
        "generated_at": datetime.now().isoformat(),
        "request": normalized_request,
        "artifacts": capability_result.get("artifacts", {}),
        "default_metrics": get_default_review_metrics(capability),
        "rule_review": rule_review,
        "llm_review": llm_review,
        "review_status": review_status,
        "retry_hint": _compose_retry_hint(rule_review, llm_review),
    }
    artifact_path = _save_review_artifact(review_payload, capability)
    review_payload["review_artifact_path"] = artifact_path
    return review_payload
