from __future__ import annotations

import unittest
from unittest.mock import patch

from eduagent_core.llm_planner import PlannerLLMError
from eduagent_core.planner import analyze_task, execute_plan


class PlannerTests(unittest.TestCase):
    def test_analyze_direct_generation_task(self) -> None:
        analysis = analyze_task(task="帮我生成一份高中数学教案", payload={"course": "高中数学", "lessons": "分数加减法"})
        self.assertEqual(analysis.analysis_source, "rule")
        self.assertEqual(analysis.task_family, "generation")
        self.assertEqual(analysis.recommended_route, "capability")
        self.assertEqual(analysis.direct_capability, "lesson_plan")

    def test_analyze_mixed_task_prefers_workflow(self) -> None:
        analysis = analyze_task(
            task="先查资料再生成一份强化学习教案",
            payload={"course": "大模型", "units": "强化学习基础"},
            planner_mode="rule",
        )
        self.assertEqual(analysis.task_family, "mixed")
        self.assertEqual(analysis.recommended_route, "workflow")
        self.assertTrue(analysis.fallback_attempts)

    @patch("eduagent_core.planner.analyze_task_with_llm")
    def test_hybrid_analysis_uses_llm_for_mixed_task(self, llm_mock) -> None:
        llm_mock.return_value = {
            "task_family": "mixed",
            "complexity": "multi_step",
            "recommended_route": "workflow",
            "direct_capability": "lesson_plan",
            "requires_research": True,
            "requires_workflow": True,
            "reason": "需要先调研再生成",
        }
        analysis = analyze_task(
            task="先查资料再生成一份强化学习教案",
            payload={"course": "大模型", "units": "强化学习基础"},
            planner_mode="hybrid",
        )
        self.assertEqual(analysis.analysis_source, "llm")
        self.assertEqual(analysis.recommended_route, "workflow")
        llm_mock.assert_called_once()

    @patch("eduagent_core.planner.analyze_task_with_llm")
    def test_hybrid_analysis_falls_back_to_rules_when_llm_unavailable(self, llm_mock) -> None:
        llm_mock.side_effect = PlannerLLMError("missing api key")
        analysis = analyze_task(
            task="探索 AI 助教并给出 workflow",
            payload={},
            planner_mode="hybrid",
        )
        self.assertEqual(analysis.analysis_source, "rule_fallback")
        self.assertEqual(analysis.recommended_route, "workflow")

    @patch("eduagent_core.planner.analyze_task_with_llm")
    def test_llm_analysis_is_validated_by_local_constraints(self, llm_mock) -> None:
        llm_mock.return_value = {
            "task_family": "generation",
            "complexity": "single_step",
            "recommended_route": "capability",
            "direct_capability": "lesson_plan",
            "requires_research": False,
            "requires_workflow": False,
            "reason": "模型认为是教案",
        }
        analysis = analyze_task(
            task="帮我生成教案",
            payload={},
            planner_mode="llm",
        )
        self.assertEqual(analysis.analysis_source, "llm")
        self.assertEqual(analysis.recommended_route, "workflow")

    @patch("eduagent_core.planner.review_capability_result")
    @patch("eduagent_core.planner.dispatch_capability")
    def test_execute_plan_uses_direct_capability_for_generation(self, dispatch_mock, review_mock) -> None:
        dispatch_mock.return_value = {
            "status": "success",
            "capability": "lesson_plan",
            "request": {"course": "高中数学", "lessons": "分数加减法"},
            "artifacts": {"lesson_plan_path": "/tmp/lesson.md"},
            "preview": "preview",
        }
        review_mock.return_value = {
            "review_status": "pass",
            "review_artifact_path": "/tmp/review.json",
            "rule_review": {"score": 95},
            "llm_review": {"overall_score": 88},
        }

        result = execute_plan(
            task="帮我生成一份高中数学教案",
            payload={"course": "高中数学", "lessons": "分数加减法"},
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["selected_route"], "capability")
        dispatch_mock.assert_called_once()
        self.assertEqual(result["review"]["review_status"], "pass")

    @patch("eduagent_core.planner.run_workflow_pipeline")
    def test_execute_plan_falls_back_to_sequential_workflow(self, workflow_mock) -> None:
        workflow_mock.side_effect = [
            {"status": "error", "route": "workflow", "error_type": "runtime_error", "message": "auto failed"},
            {"status": "success", "route": "workflow", "artifacts": {"result_path": "/tmp/result.md"}},
        ]

        result = execute_plan(task="探索 AI 助教并给出 workflow", payload={}, planner_mode="rule")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["selected_route"], "workflow")
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(workflow_mock.call_args_list[1].kwargs["mode"], "sequential")

    @patch("eduagent_core.planner.run_workflow_pipeline")
    def test_execute_plan_passes_search_mode_to_workflow(self, workflow_mock) -> None:
        workflow_mock.return_value = {
            "status": "success",
            "route": "workflow",
            "artifacts": {"result_path": "/tmp/result.md"},
        }

        execute_plan(
            task="先查资料再生成一份强化学习教案",
            payload={"course": "大模型", "units": "强化学习基础", "search_mode": "research"},
            planner_mode="rule",
        )

        self.assertEqual(workflow_mock.call_args.kwargs["search_mode"], "research")

    @patch("eduagent_core.planner.dispatch_capability")
    def test_execute_plan_stops_on_validation_error(self, dispatch_mock) -> None:
        dispatch_mock.return_value = {
            "status": "error",
            "route": "capability",
            "error_type": "validation_error",
            "message": "missing fields",
        }

        result = execute_plan(task="帮我生成教案", payload={})

        self.assertEqual(result["status"], "error")
        self.assertEqual(len(result["attempts"]), 1)

    @patch("eduagent_core.planner.review_capability_result")
    @patch("eduagent_core.planner.dispatch_capability")
    def test_execute_plan_retries_once_when_review_fails(self, dispatch_mock, review_mock) -> None:
        dispatch_mock.side_effect = [
            {
                "status": "success",
                "capability": "lesson_plan",
                "request": {"course": "高中数学", "lessons": "分数加减法", "model_type": "QWen"},
                "artifacts": {"lesson_plan_path": "/tmp/lesson.md"},
            },
            {
                "status": "success",
                "capability": "lesson_plan",
                "request": {"course": "高中数学", "lessons": "分数加减法", "model_type": "DeepSeek"},
                "artifacts": {"lesson_plan_path": "/tmp/lesson_v2.md"},
            },
        ]
        review_mock.side_effect = [
            {
                "review_status": "fail",
                "retry_hint": "请补充教学目标与教学过程，并提升表达清晰度。",
                "review_artifact_path": "/tmp/review_1.json",
                "rule_review": {"score": 40},
                "llm_review": {"overall_score": 55},
            },
            {
                "review_status": "pass",
                "retry_hint": "done",
                "review_artifact_path": "/tmp/review_2.json",
                "rule_review": {"score": 90},
                "llm_review": {"overall_score": 86},
            },
        ]

        result = execute_plan(
            task="帮我生成一份高中数学教案",
            payload={"course": "高中数学", "lessons": "分数加减法"},
            planner_mode="rule",
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(result["attempts"][0]["review_status"], "fail")
        second_payload = dispatch_mock.call_args_list[1].kwargs["payload"]
        self.assertEqual(second_payload["model_type"], "DeepSeek")
        self.assertIn("教学目标", second_payload["constraint"])

    @patch("eduagent_core.planner.review_capability_result")
    @patch("eduagent_core.planner.dispatch_capability")
    def test_execute_plan_preserves_explicit_model_type_on_review_retry(self, dispatch_mock, review_mock) -> None:
        dispatch_mock.side_effect = [
            {
                "status": "success",
                "capability": "lesson_plan",
                "request": {"course": "高中数学", "lessons": "分数加减法", "model_type": "QWen"},
                "artifacts": {"lesson_plan_path": "/tmp/lesson.md"},
            },
            {
                "status": "success",
                "capability": "lesson_plan",
                "request": {"course": "高中数学", "lessons": "分数加减法", "model_type": "QWen"},
                "artifacts": {"lesson_plan_path": "/tmp/lesson_v2.md"},
            },
        ]
        review_mock.side_effect = [
            {
                "review_status": "fail",
                "retry_hint": "请补充教学目标与教学过程，并提升表达清晰度。",
                "review_artifact_path": "/tmp/review_1.json",
                "rule_review": {"score": 40},
                "llm_review": {"overall_score": 55},
            },
            {
                "review_status": "pass",
                "retry_hint": "done",
                "review_artifact_path": "/tmp/review_2.json",
                "rule_review": {"score": 90},
                "llm_review": {"overall_score": 86},
            },
        ]

        execute_plan(
            task="帮我生成一份高中数学教案",
            payload={"course": "高中数学", "lessons": "分数加减法", "model_type": "QWen"},
            planner_mode="rule",
        )

        second_payload = dispatch_mock.call_args_list[1].kwargs["payload"]
        self.assertEqual(second_payload["model_type"], "QWen")

    @patch("eduagent_core.planner.review_capability_result")
    @patch("eduagent_core.planner.run_workflow_pipeline")
    def test_execute_plan_workflow_route_does_not_trigger_review(self, workflow_mock, review_mock) -> None:
        workflow_mock.return_value = {
            "status": "success",
            "route": "workflow",
            "artifacts": {"result_path": "/tmp/result.md"},
        }

        result = execute_plan(task="探索 AI 助教并给出 workflow", payload={}, planner_mode="rule")

        self.assertEqual(result["status"], "success")
        review_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
