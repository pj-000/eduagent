from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eduagent_lesson_plan.service import (
    LessonPlanInputError,
    build_request,
    generate_lesson_plan_artifacts,
)


class LessonPlanServiceTests(unittest.TestCase):
    def test_build_request_requires_course(self) -> None:
        with self.assertRaises(LessonPlanInputError) as ctx:
            build_request({"lessons": "分数加减法"})
        self.assertEqual(ctx.exception.missing_fields, ["course"])

    def test_build_request_requires_units_or_lessons(self) -> None:
        with self.assertRaises(LessonPlanInputError) as ctx:
            build_request({"course": "高中数学"})
        self.assertEqual(ctx.exception.missing_fields, ["units_or_lessons"])

    def test_generate_lesson_plan_artifacts_saves_markdown_and_metadata(self) -> None:
        request = build_request({"course": "高中数学", "lessons": "分数加减法"})
        fake_markdown = "# 《高中数学》教学教案\n\n## 理论部分\n\n内容"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch("eduagent_lesson_plan.service.RESULTS_DIR", tmp_path / "results"), patch(
                "eduagent_lesson_plan.service.RUNS_DIR", tmp_path / "runs"
            ), patch(
                "eduagent_lesson_plan.service.UPLOAD_DIR", tmp_path / "upload"
            ), patch(
                "eduagent_lesson_plan.service.execute_workflow_logic",
                return_value=fake_markdown,
            ):
                result = generate_lesson_plan_artifacts(request)
                lesson_plan_path = Path(result["lesson_plan_path"])
                metadata_path = Path(result["metadata_path"])
                self.assertTrue(lesson_plan_path.exists())
                self.assertTrue(metadata_path.exists())
                self.assertEqual(lesson_plan_path.read_text(encoding="utf-8"), fake_markdown)

                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                self.assertEqual(metadata["request"]["course"], "高中数学")
                self.assertNotIn("thinking_steps", metadata)
                self.assertNotIn("thinking_steps", result)


if __name__ == "__main__":
    unittest.main()
