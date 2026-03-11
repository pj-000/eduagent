"""Minimal planner layer that chooses between direct capabilities and workflow execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .capability_registry import CAPABILITY_SPECS, dispatch_capability, resolve_capability
from .llm_planner import PlannerLLMError, analyze_task_with_llm
from .reviewer import review_capability_result
from .workflow_runner import run_workflow_pipeline


SEARCH_KEYWORDS = ("搜索", "查资料", "调研", "探索", "research", "search", "检索")
WORKFLOW_KEYWORDS = ("workflow", "工作流", "方案", "落地", "执行链", "pipeline")
EVALUATION_KEYWORDS = ("评估", "评价", "review", "rubric", "评分")
GENERATION_KEYWORDS = ("生成", "制作", "产出", "写", "教案", "试卷", "ppt", "课件", "幻灯片")
WORKFLOW_CONTROL_FIELDS = {
    "focus",
    "themes",
    "search_mode",
    "hint",
    "feature",
    "mode",
    "skip_search",
    "inputs",
    "max_steps",
    "no_save_state",
    "skip_framework_research",
}


@dataclass(frozen=True)
class PlannerAttempt:
    route: str
    reason: str
    capability: str | None = None
    mode: str | None = None
    payload_overrides: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["payload_overrides"] = dict(self.payload_overrides or {})
        return data


@dataclass(frozen=True)
class TaskAnalysis:
    analysis_source: str
    task_family: str
    complexity: str
    direct_capability: str | None
    recommended_route: str
    requires_research: bool
    requires_workflow: bool
    fallback_attempts: tuple[PlannerAttempt, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_source": self.analysis_source,
            "task_family": self.task_family,
            "complexity": self.complexity,
            "direct_capability": self.direct_capability,
            "recommended_route": self.recommended_route,
            "requires_research": self.requires_research,
            "requires_workflow": self.requires_workflow,
            "reason": self.reason,
            "fallback_attempts": [item.to_dict() for item in self.fallback_attempts],
        }


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _normalize_task_family(value: Any, fallback: str) -> str:
    candidate = str(value or "").strip()
    if candidate in {"generation", "mixed", "research", "evaluation"}:
        return candidate
    return fallback


def _normalize_complexity(value: Any, fallback: str) -> str:
    candidate = str(value or "").strip()
    if candidate in {"single_step", "multi_step"}:
        return candidate
    return fallback


def _normalize_route(value: Any, fallback: str) -> str:
    candidate = str(value or "").strip()
    if candidate in {"capability", "workflow"}:
        return candidate
    return fallback


def _normalize_direct_capability(value: Any, fallback: str | None) -> str | None:
    if value in (None, "", "null"):
        return None
    candidate = str(value).strip()
    if candidate in CAPABILITY_SPECS:
        return candidate
    return fallback


def _has_minimum_payload(capability: str, payload: dict[str, Any]) -> bool:
    if capability == "lesson_plan":
        return bool(payload.get("course")) and bool(payload.get("units") or payload.get("lessons"))
    if capability == "exam":
        return bool(payload.get("subject")) and bool(payload.get("knowledge_bases"))
    if capability == "ppt":
        return bool(payload.get("course")) and bool(
            payload.get("units") or payload.get("lessons") or payload.get("knowledge_points")
        )
    return False


def _build_workflow_fallbacks(
    direct_capability: str | None,
    payload: dict[str, Any],
    mode: str,
) -> tuple[PlannerAttempt, ...]:
    fallbacks: list[PlannerAttempt] = []
    if mode == "auto":
        fallbacks.append(
            PlannerAttempt(
                route="workflow",
                mode="sequential",
                reason="workflow_auto_failed_then_degrade_to_sequential",
            )
        )
    if direct_capability and _has_minimum_payload(direct_capability, payload):
        fallbacks.append(
            PlannerAttempt(
                route="capability",
                capability=direct_capability,
                reason="workflow_failed_then_fallback_to_direct_capability",
            )
        )
    return tuple(fallbacks)


def _build_capability_fallbacks(capability: str, payload: dict[str, Any]) -> tuple[PlannerAttempt, ...]:
    if capability not in CAPABILITY_SPECS:
        return ()
    if "model_type" in payload:
        return ()
    return (
        PlannerAttempt(
            route="capability",
            capability=capability,
            payload_overrides={"model_type": "DeepSeek"},
            reason="default_model_failed_then_switch_to_deepseek",
        ),
    )


def _analyze_task_rule_based(
    *,
    task: str | None = None,
    payload: dict[str, Any] | None = None,
    capability: str | None = None,
) -> TaskAnalysis:
    """Analyze task type and recommend a route."""

    raw_payload = dict(payload or {})
    task_text = str(task or "").strip()
    direct_capability: str | None = None
    try:
        direct_capability = resolve_capability(task=task_text, payload=raw_payload, capability=capability)
    except Exception:
        direct_capability = None

    has_search = _contains_any(task_text, SEARCH_KEYWORDS) or any(key in raw_payload for key in ("focus", "themes", "hint"))
    has_workflow = _contains_any(task_text, WORKFLOW_KEYWORDS) or capability == "workflow"
    has_evaluation = _contains_any(task_text, EVALUATION_KEYWORDS)
    has_generation = direct_capability is not None or _contains_any(task_text, GENERATION_KEYWORDS)

    if has_generation and not (has_search or has_workflow or has_evaluation) and direct_capability:
        return TaskAnalysis(
            analysis_source="rule",
            task_family="generation",
            complexity="single_step",
            direct_capability=direct_capability,
            recommended_route="capability",
            requires_research=False,
            requires_workflow=False,
            fallback_attempts=_build_capability_fallbacks(direct_capability, raw_payload),
            reason="direct_generation_request_with_known_capability",
        )

    if has_generation and (has_search or has_workflow or has_evaluation):
        mode = str(raw_payload.get("mode", "auto"))
        return TaskAnalysis(
            analysis_source="rule",
            task_family="mixed",
            complexity="multi_step",
            direct_capability=direct_capability,
            recommended_route="workflow",
            requires_research=has_search,
            requires_workflow=True,
            fallback_attempts=_build_workflow_fallbacks(direct_capability, raw_payload, mode),
            reason="mixed_request_requires_research_or_workflow_before_generation",
        )

    if has_search or has_workflow or has_evaluation or direct_capability is None:
        mode = str(raw_payload.get("mode", "auto"))
        family = "evaluation" if has_evaluation and not (has_search or has_workflow) else "research"
        return TaskAnalysis(
            analysis_source="rule",
            task_family=family,
            complexity="multi_step",
            direct_capability=direct_capability,
            recommended_route="workflow",
            requires_research=has_search or family == "research",
            requires_workflow=True,
            fallback_attempts=_build_workflow_fallbacks(direct_capability, raw_payload, mode),
            reason="task_requires_planning_or_cannot_be_safely_mapped_to_single_capability",
        )

    return TaskAnalysis(
        analysis_source="rule",
        task_family="generation",
        complexity="single_step",
        direct_capability=direct_capability,
        recommended_route="capability" if direct_capability else "workflow",
        requires_research=False,
        requires_workflow=direct_capability is None,
        fallback_attempts=(),
        reason="default_route_selection",
    )


def _should_call_llm(rule_analysis: TaskAnalysis, task: str, payload: dict[str, Any], planner_mode: str) -> bool:
    if planner_mode == "llm":
        return True
    if planner_mode != "hybrid":
        return False
    if rule_analysis.task_family in {"mixed", "research", "evaluation"}:
        return True
    if any(field in payload for field in WORKFLOW_CONTROL_FIELDS):
        return True
    return _contains_any(task, SEARCH_KEYWORDS + WORKFLOW_KEYWORDS + EVALUATION_KEYWORDS)


def _build_capability_summaries() -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for spec in CAPABILITY_SPECS.values():
        summaries.append(
            {
                "capability": spec.key,
                "description": spec.description,
                "required_fields": [field.name for field in spec.field_specs if field.required],
                "required_groups": [group.to_dict() for group in spec.required_groups],
                "defaults": spec.defaults,
            }
        )
    return summaries


def _merge_llm_analysis(
    rule_analysis: TaskAnalysis,
    llm_output: dict[str, Any],
    payload: dict[str, Any],
) -> TaskAnalysis:
    direct_capability = _normalize_direct_capability(llm_output.get("direct_capability"), rule_analysis.direct_capability)
    recommended_route = _normalize_route(llm_output.get("recommended_route"), rule_analysis.recommended_route)
    if recommended_route == "capability" and direct_capability is None:
        recommended_route = rule_analysis.recommended_route
    if recommended_route == "capability" and direct_capability and not _has_minimum_payload(direct_capability, payload):
        # The model may recognize intent correctly but direct execution would still fail.
        recommended_route = "workflow"

    merged = TaskAnalysis(
        analysis_source="llm",
        task_family=_normalize_task_family(llm_output.get("task_family"), rule_analysis.task_family),
        complexity=_normalize_complexity(llm_output.get("complexity"), rule_analysis.complexity),
        direct_capability=direct_capability,
        recommended_route=recommended_route,
        requires_research=bool(llm_output.get("requires_research", rule_analysis.requires_research)),
        requires_workflow=bool(llm_output.get("requires_workflow", rule_analysis.requires_workflow or recommended_route == "workflow")),
        fallback_attempts=(),
        reason=str(llm_output.get("reason") or rule_analysis.reason),
    )
    if merged.recommended_route == "workflow":
        fallback_attempts = _build_workflow_fallbacks(merged.direct_capability, payload, str(payload.get("mode", "auto")))
    else:
        fallback_attempts = _build_capability_fallbacks(merged.direct_capability or "", payload)
    return TaskAnalysis(
        analysis_source=merged.analysis_source,
        task_family=merged.task_family,
        complexity=merged.complexity,
        direct_capability=merged.direct_capability,
        recommended_route=merged.recommended_route,
        requires_research=merged.requires_research,
        requires_workflow=merged.requires_workflow,
        fallback_attempts=fallback_attempts,
        reason=merged.reason,
    )


def analyze_task(
    *,
    task: str | None = None,
    payload: dict[str, Any] | None = None,
    capability: str | None = None,
    planner_mode: str = "hybrid",
    planner_model: str = "QWen",
) -> TaskAnalysis:
    """Analyze task type and recommend a route."""

    raw_payload = dict(payload or {})
    task_text = str(task or "").strip()
    rule_analysis = _analyze_task_rule_based(task=task_text, payload=raw_payload, capability=capability)
    if not _should_call_llm(rule_analysis, task_text, raw_payload, planner_mode):
        return rule_analysis

    try:
        llm_output = analyze_task_with_llm(
            task=task_text,
            payload=raw_payload,
            capability_summaries=_build_capability_summaries(),
            model_type=planner_model,
        )
    except Exception as exc:
        return TaskAnalysis(
            analysis_source="rule_fallback",
            task_family=rule_analysis.task_family,
            complexity=rule_analysis.complexity,
            direct_capability=rule_analysis.direct_capability,
            recommended_route=rule_analysis.recommended_route,
            requires_research=rule_analysis.requires_research,
            requires_workflow=rule_analysis.requires_workflow,
            fallback_attempts=rule_analysis.fallback_attempts,
            reason=f"{rule_analysis.reason}; llm_planner_unavailable: {exc}",
        )

    return _merge_llm_analysis(rule_analysis, llm_output, raw_payload)


def _extract_workflow_kwargs(task: str, payload: dict[str, Any], mode: str | None = None) -> dict[str, Any]:
    kwargs = {
        "task": task,
        "focus": payload.get("focus", "all"),
        "themes": list(payload.get("themes", [])),
        "search_mode": payload.get("search_mode", "research"),
        "hint": payload.get("hint"),
        "feature": payload.get("feature"),
        "mode": mode or payload.get("mode", "auto"),
        "skip_search": bool(payload.get("skip_search", False)),
        "inputs": payload.get("inputs"),
        "max_steps": int(payload.get("max_steps", 5)),
        "no_save_state": bool(payload.get("no_save_state", False)),
        "skip_framework_research": bool(payload.get("skip_framework_research", False)),
    }
    return kwargs


def _run_attempt(task: str, payload: dict[str, Any], attempt: PlannerAttempt) -> dict[str, Any]:
    if attempt.route == "workflow":
        workflow_result = run_workflow_pipeline(**_extract_workflow_kwargs(task, payload, mode=attempt.mode))
        workflow_result["attempt"] = attempt.to_dict()
        return workflow_result

    merged_payload = dict(payload)
    merged_payload.update(attempt.payload_overrides or {})
    capability_result = dispatch_capability(task=task, payload=merged_payload, capability=attempt.capability)
    capability_result["attempt"] = attempt.to_dict()
    capability_result["route"] = "capability"
    return capability_result


def _build_history_entry(
    *,
    index: int,
    attempt: PlannerAttempt,
    result: dict[str, Any],
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = {
        "index": index,
        "route": result.get("route", attempt.route),
        "status": result.get("status"),
        "reason": attempt.reason,
        "capability": attempt.capability,
        "mode": attempt.mode,
        "error_type": result.get("error_type"),
        "message": result.get("message"),
        "review_status": None,
        "review_artifact_path": None,
        "rule_review_score": None,
        "llm_review_score": None,
    }
    if review:
        entry["review_status"] = review.get("review_status")
        entry["review_artifact_path"] = review.get("review_artifact_path")
        entry["rule_review_score"] = review.get("rule_review", {}).get("score")
        entry["llm_review_score"] = review.get("llm_review", {}).get("overall_score")
        if review.get("review_status") == "fail":
            entry["status"] = "review_failed"
            entry["message"] = review.get("retry_hint")
    return entry


def _should_switch_model_for_review_retry(raw_payload: dict[str, Any], attempt: PlannerAttempt) -> bool:
    if "model_type" in raw_payload:
        return False
    return "model_type" not in (attempt.payload_overrides or {})


def _build_quality_retry_attempt(
    attempt: PlannerAttempt,
    payload: dict[str, Any],
    review: dict[str, Any],
) -> PlannerAttempt:
    merged_constraint_parts: list[str] = []
    existing_constraint = str(payload.get("constraint", "") or "").strip()
    if existing_constraint:
        merged_constraint_parts.append(existing_constraint)
    retry_hint = str(review.get("retry_hint", "") or "").strip()
    if retry_hint:
        merged_constraint_parts.append(retry_hint)

    payload_overrides = dict(attempt.payload_overrides or {})
    payload_overrides["constraint"] = "\n".join(merged_constraint_parts).strip()
    if _should_switch_model_for_review_retry(payload, attempt):
        payload_overrides["model_type"] = "DeepSeek"

    return PlannerAttempt(
        route="capability",
        capability=attempt.capability,
        reason="review_failed_then_retry_capability_with_refined_constraint",
        payload_overrides=payload_overrides,
    )


def execute_plan(
    *,
    task: str,
    payload: dict[str, Any] | None = None,
    capability: str | None = None,
    allow_fallback: bool = True,
    planner_mode: str = "hybrid",
    planner_model: str = "QWen",
) -> dict[str, Any]:
    """Analyze a task, execute the selected route, and apply simple fallbacks."""

    raw_payload = dict(payload or {})
    analysis = analyze_task(
        task=task,
        payload=raw_payload,
        capability=capability,
        planner_mode=planner_mode,
        planner_model=planner_model,
    )

    attempts: list[PlannerAttempt] = []
    if analysis.recommended_route == "capability":
        attempts.append(
            PlannerAttempt(
                route="capability",
                capability=analysis.direct_capability or capability,
                reason="primary_direct_capability_route",
            )
        )
    else:
        attempts.append(
            PlannerAttempt(
                route="workflow",
                mode=str(raw_payload.get("mode", "auto")),
                reason="primary_workflow_route",
            )
        )
    if allow_fallback:
        attempts.extend(list(analysis.fallback_attempts))

    history: list[dict[str, Any]] = []
    for index, attempt in enumerate(attempts):
        result = _run_attempt(task, raw_payload, attempt)
        review: dict[str, Any] | None = None
        if result.get("status") == "success":
            if result.get("route") == "capability":
                review = review_capability_result(
                    result.get("capability") or attempt.capability or "",
                    result.get("request") or raw_payload,
                    result,
                )
                history.append(_build_history_entry(index=index, attempt=attempt, result=result, review=review))
                if review.get("review_status") == "pass":
                    return {
                        "status": "success",
                        "analysis": analysis.to_dict(),
                        "selected_route": result.get("route", attempt.route),
                        "result": result,
                        "review": review,
                        "attempts": history,
                    }

                retry_attempt = _build_quality_retry_attempt(attempt, raw_payload, review)
                retry_result = _run_attempt(task, raw_payload, retry_attempt)
                retry_review: dict[str, Any] | None = None
                if retry_result.get("status") == "success":
                    retry_review = review_capability_result(
                        retry_result.get("capability") or retry_attempt.capability or "",
                        retry_result.get("request") or raw_payload,
                        retry_result,
                    )
                history.append(
                    _build_history_entry(
                        index=index + 1,
                        attempt=retry_attempt,
                        result=retry_result,
                        review=retry_review,
                    )
                )
                if retry_result.get("status") == "success" and retry_review and retry_review.get("review_status") == "pass":
                    return {
                        "status": "success",
                        "analysis": analysis.to_dict(),
                        "selected_route": retry_result.get("route", retry_attempt.route),
                        "result": retry_result,
                        "review": retry_review,
                        "attempts": history,
                    }
                failure_message = (
                    retry_review.get("retry_hint")
                    if retry_review
                    else retry_result.get("message") or review.get("retry_hint")
                )
                return {
                    "status": "error",
                    "analysis": analysis.to_dict(),
                    "selected_route": attempt.route,
                    "attempts": history,
                    "message": failure_message or "planner_quality_review_failed",
                    "review": retry_review or review,
                }

            history.append(_build_history_entry(index=index, attempt=attempt, result=result))
            return {
                "status": "success",
                "analysis": analysis.to_dict(),
                "selected_route": result.get("route", attempt.route),
                "result": result,
                "attempts": history,
            }
        history.append(_build_history_entry(index=index, attempt=attempt, result=result))
        if result.get("error_type") == "validation_error":
            break

    return {
        "status": "error",
        "analysis": analysis.to_dict(),
        "selected_route": attempts[0].route if attempts else analysis.recommended_route,
        "attempts": history,
        "message": history[-1]["message"] if history else "planner_execution_failed",
    }
