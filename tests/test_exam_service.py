from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eduagent_exam.service import ExamGenerationInputError, build_request, generate_exam_artifacts


class ExamServiceTests(unittest.TestCase):
    def test_build_request_requires_subject_and_knowledge(self) -> None:
        with self.assertRaises(ExamGenerationInputError) as ctx:
            build_request({"subject": ""})
        self.assertEqual(ctx.exception.missing_fields, ["subject", "knowledge_bases"])

    def test_build_request_requires_positive_question_count(self) -> None:
        with self.assertRaises(ExamGenerationInputError) as ctx:
            build_request(
                {
                    "subject": "大模型",
                    "knowledge_bases": "强化学习",
                    "single_choice_num": 0,
                    "multiple_choice_num": 0,
                    "true_false_num": 0,
                    "fill_blank_num": 0,
                    "short_answer_num": 0,
                    "programming_num": 0,
                }
            )
        self.assertEqual(ctx.exception.missing_fields, [])

    def test_generate_exam_artifacts_saves_outputs(self) -> None:
        request = build_request({"subject": "大模型", "knowledge_bases": "强化学习"})
        fake_questions = [
            {
                "name": "强化学习中的 agent 指什么？",
                "type": 1,
                "analysis": "考查基础概念",
                "options": [{"answer": "智能体", "is_answer": 1}],
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch("eduagent_exam.service.RESULTS_DIR", tmp_path / "results"), patch(
                "eduagent_exam.service.RUNS_DIR", tmp_path / "runs"
            ), patch(
                "eduagent_exam.service.generate_exam_questions",
                return_value={"questions": fake_questions, "raw_output": {}},
            ):
                result = generate_exam_artifacts(request)
                json_path = Path(result["result_json_path"])
                md_path = Path(result["result_md_path"])
                metadata_path = Path(result["metadata_path"])
                self.assertTrue(json_path.exists())
                self.assertTrue(md_path.exists())
                self.assertTrue(metadata_path.exists())

                data = json.loads(json_path.read_text(encoding="utf-8"))
                self.assertEqual(len(data["questions"]), 1)
                self.assertEqual(result["question_count"], 1)


if __name__ == "__main__":
    unittest.main()
