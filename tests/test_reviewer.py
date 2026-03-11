from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eduagent_core.reviewer import (
    llm_review_capability_result,
    normalize_metric_name,
    review_capability_result,
    rule_review_capability_result,
)


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content

    def generate(self, prompt: str):
        self.prompt = prompt
        return self._content


class ReviewerTests(unittest.TestCase):
    def test_normalize_metric_name_maps_legacy_names(self) -> None:
        self.assertEqual(normalize_metric_name("1 指令遵循与任务完成"), "1.1 指令遵循与任务完成")
        self.assertEqual(normalize_metric_name("9 题目整体布局与知识点覆盖"), "2.5 题目整体布局与知识点覆盖")
        self.assertEqual(normalize_metric_name("3.1 清晰易懂与表达启发"), "3.1 清晰易懂与表达启发")

    def test_rule_review_lesson_plan_passes_with_required_sections(self) -> None:
        markdown = "# 标题\n\n## 教学目标\n- 目标\n\n## 教学过程\n- 过程\n\n## 总结\n" + ("内容" * 220)
        with tempfile.TemporaryDirectory() as tmpdir:
            lesson_path = Path(tmpdir) / "lesson.md"
            lesson_path.write_text(markdown, encoding="utf-8")
            result = rule_review_capability_result(
                "lesson_plan",
                {"word_limit": 1200},
                {"artifacts": {"lesson_plan_path": str(lesson_path)}},
            )
        self.assertEqual(result["status"], "pass")

    def test_rule_review_lesson_plan_fails_without_goal_or_process(self) -> None:
        markdown = "# 标题\n\n## 内容\n" + ("内容" * 220)
        with tempfile.TemporaryDirectory() as tmpdir:
            lesson_path = Path(tmpdir) / "lesson.md"
            lesson_path.write_text(markdown, encoding="utf-8")
            result = rule_review_capability_result(
                "lesson_plan",
                {},
                {"artifacts": {"lesson_plan_path": str(lesson_path)}},
            )
        self.assertEqual(result["status"], "fail")
        self.assertIn("lesson_plan_goal_section_missing", result["blocking_issues"])

    def test_rule_review_exam_detects_question_count_mismatch(self) -> None:
        payload = {"questions": [{"name": "Q1", "type": 1, "analysis": "A", "options": [{"answer": "x", "is_answer": 1}, {"answer": "y", "is_answer": 0}]}]}
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "exam.json"
            json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = rule_review_capability_result(
                "exam",
                {"single_choice_num": 2},
                {"artifacts": {"result_json_path": str(json_path)}},
            )
        self.assertEqual(result["status"], "fail")
        self.assertIn("exam_question_count_mismatch", result["blocking_issues"])

    def test_rule_review_ppt_requires_pptx_when_output_mode_is_ppt(self) -> None:
        markdown = "# 封面\n\n# 目录\n\n## 内容\n- 要点\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "slides.md"
            md_path.write_text(markdown, encoding="utf-8")
            result = rule_review_capability_result(
                "ppt",
                {"output_mode": "ppt"},
                {"artifacts": {"markdown_path": str(md_path), "pptx_path": str(Path(tmpdir) / "slides.pptx")}},
            )
        self.assertEqual(result["status"], "fail")
        self.assertIn("ppt_output_file_missing", result["blocking_issues"])

    def test_rule_review_ppt_low_page_count_is_only_advisory(self) -> None:
        markdown = "# 封面\n\n# 目录\n\n## 内容\n- 要点\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "slides.md"
            pptx_path = Path(tmpdir) / "slides.pptx"
            md_path.write_text(markdown, encoding="utf-8")
            pptx_path.write_text("fake", encoding="utf-8")
            result = rule_review_capability_result(
                "ppt",
                {"output_mode": "ppt", "page_limit": 12},
                {"artifacts": {"markdown_path": str(md_path), "pptx_path": str(pptx_path)}},
            )
        self.assertEqual(result["status"], "pass")
        self.assertIn("ppt_page_count_looks_low_for_requested_scope", result["advisories"])

    @patch("eduagent_core.reviewer.build_planner_llm")
    def test_llm_review_uses_qwen_and_normalizes_metrics(self, build_llm_mock) -> None:
        build_llm_mock.return_value = _FakeLLM(
            json.dumps(
                {
                    "dimension_scores": [
                        {
                            "dimension": "1 指令遵循与任务完成",
                            "score": 8,
                            "reason": "完成较好",
                            "optimization_suggestion": "补充细节",
                        },
                        {
                            "dimension": "3 内容相关性与范围控制",
                            "score": 7,
                            "reason": "相关性较强",
                            "optimization_suggestion": "减少冗余",
                        },
                        {
                            "dimension": "5 基础事实准确性",
                            "score": 9,
                            "reason": "事实准确",
                            "optimization_suggestion": "保持一致",
                        },
                        {
                            "dimension": "6 领域知识专业性",
                            "score": 8,
                            "reason": "专业性较好",
                            "optimization_suggestion": "增加深度",
                        },
                        {
                            "dimension": "10 清晰易懂与表达启发",
                            "score": 7,
                            "reason": "较易理解",
                            "optimization_suggestion": "增强启发性",
                        },
                    ],
                    "overall_score": 8,
                    "overall_status": "pass",
                    "summary": "整体较好",
                    "blocking_issues": [],
                    "advisories": ["增加案例"],
                    "retry_hint": "补充案例并增强教学引导。",
                },
                ensure_ascii=False,
            )
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            lesson_path = Path(tmpdir) / "lesson.md"
            lesson_path.write_text("# 标题\n\n## 教学目标\n" + ("内容" * 220) + "\n## 教学过程\n- 过程\n", encoding="utf-8")
            review = llm_review_capability_result(
                "lesson_plan",
                {"course": "高中数学", "lessons": "分数加减法"},
                {"artifacts": {"lesson_plan_path": str(lesson_path)}},
                {"status": "pass", "blocking_issues": [], "advisories": [], "signals": {}},
            )
        build_llm_mock.assert_called_once_with(model_type="QWen")
        self.assertEqual(review["status"], "pass")
        self.assertEqual(review["overall_score"], 80)
        self.assertEqual(review["dimension_scores"][0]["dimension"], "1.1 指令遵循与任务完成")

    @patch("eduagent_core.reviewer.build_planner_llm")
    def test_llm_review_fails_on_invalid_json(self, build_llm_mock) -> None:
        build_llm_mock.return_value = _FakeLLM("not json")
        review = llm_review_capability_result(
            "ppt",
            {"course": "高中数学"},
            {"artifacts": {}},
            {"status": "pass", "blocking_issues": [], "advisories": [], "signals": {}},
        )
        self.assertEqual(review["status"], "fail")
        self.assertTrue(review["blocking_issues"])

    @patch("eduagent_core.reviewer.build_planner_llm")
    def test_review_capability_result_writes_review_artifact(self, build_llm_mock) -> None:
        build_llm_mock.return_value = _FakeLLM(
            json.dumps(
                {
                    "dimension_scores": [
                        {
                            "dimension": "1.1 指令遵循与任务完成",
                            "score": 8,
                            "reason": "完成较好",
                            "optimization_suggestion": "补充细节",
                        },
                        {
                            "dimension": "1.3 内容相关性与范围控制",
                            "score": 8,
                            "reason": "相关性较强",
                            "optimization_suggestion": "减少冗余",
                        },
                        {
                            "dimension": "2.1 基础事实准确性",
                            "score": 9,
                            "reason": "事实准确",
                            "optimization_suggestion": "保持一致",
                        },
                        {
                            "dimension": "2.2 领域知识专业性",
                            "score": 8,
                            "reason": "专业性较好",
                            "optimization_suggestion": "增加深度",
                        },
                        {
                            "dimension": "3.1 清晰易懂与表达启发",
                            "score": 8,
                            "reason": "较易理解",
                            "optimization_suggestion": "增强启发性",
                        },
                    ],
                    "overall_score": 85,
                    "overall_status": "pass",
                    "summary": "整体较好",
                    "blocking_issues": [],
                    "advisories": [],
                    "retry_hint": "done",
                },
                ensure_ascii=False,
            )
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            review_dir = Path(tmpdir) / "reviews"
            md_path = Path(tmpdir) / "lesson.md"
            md_path.write_text("# 标题\n\n## 教学目标\n" + ("内容" * 220) + "\n## 教学过程\n- 过程\n", encoding="utf-8")
            with patch("eduagent_core.reviewer.REVIEW_RUNS_DIR", review_dir):
                result = review_capability_result(
                    "lesson_plan",
                    {"course": "高中数学", "lessons": "分数加减法"},
                    {"artifacts": {"lesson_plan_path": str(md_path)}},
                )
                artifact_path = Path(result["review_artifact_path"])
                self.assertTrue(artifact_path.exists())
                saved = json.loads(artifact_path.read_text(encoding="utf-8"))
                self.assertEqual(saved["review_status"], "pass")


if __name__ == "__main__":
    unittest.main()
