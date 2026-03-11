from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eduagent_ppt.service import PPTGenerationInputError, build_request, generate_ppt_artifacts


class PPTServiceTests(unittest.TestCase):
    def test_build_request_requires_course(self) -> None:
        with self.assertRaises(PPTGenerationInputError) as ctx:
            build_request({"lessons": "分数加减法"})
        self.assertEqual(ctx.exception.missing_fields, ["course"])

    def test_build_request_requires_content_scope(self) -> None:
        with self.assertRaises(PPTGenerationInputError) as ctx:
            build_request({"course": "高中数学"})
        self.assertEqual(ctx.exception.missing_fields, ["units_or_lessons_or_knowledge_points"])

    def test_generate_ppt_artifacts_saves_md_outputs(self) -> None:
        request = build_request({"course": "高中数学", "lessons": "分数加减法", "output_mode": "md"})
        fake_markdown = "# 高中数学\n\n## 目录\n\n- 分数加减法\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch("eduagent_ppt.service.MD_RESULTS_DIR", tmp_path / "md"), patch(
                "eduagent_ppt.service.PPTX_RESULTS_DIR", tmp_path / "pptx"
            ), patch(
                "eduagent_ppt.service.RUNS_DIR", tmp_path / "runs"
            ), patch(
                "eduagent_ppt.service.execute_ppt_workflow",
                return_value=fake_markdown,
            ):
                result = generate_ppt_artifacts(request)
                md_path = Path(result["markdown_path"])
                metadata_path = Path(result["metadata_path"])
                self.assertTrue(md_path.exists())
                self.assertTrue(metadata_path.exists())
                self.assertIsNone(result["pptx_path"])
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                self.assertEqual(metadata["request"]["course"], "高中数学")


if __name__ == "__main__":
    unittest.main()
