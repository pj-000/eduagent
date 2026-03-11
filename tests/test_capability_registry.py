from __future__ import annotations

import unittest
from unittest.mock import patch

from eduagent_core.capability_registry import (
    describe_capabilities,
    dispatch_capability,
    resolve_capability,
)


class CapabilityRegistryTests(unittest.TestCase):
    def test_resolve_capability_from_task_keywords(self) -> None:
        self.assertEqual(resolve_capability(task="请帮我生成一份高中数学教案"), "lesson_plan")
        self.assertEqual(resolve_capability(task="做一套强化学习试卷"), "exam")
        self.assertEqual(resolve_capability(task="输出一份强化学习 PPT"), "ppt")

    def test_resolve_capability_from_payload(self) -> None:
        self.assertEqual(resolve_capability(payload={"subject": "大模型", "knowledge_bases": "强化学习"}), "exam")
        self.assertEqual(resolve_capability(payload={"course": "高中数学", "knowledge_points": ["分数"]}), "ppt")
        self.assertEqual(resolve_capability(payload={"course": "高中数学", "lessons": "分数加减法"}), "lesson_plan")

    def test_describe_capabilities_includes_required_groups(self) -> None:
        schema = describe_capabilities("ppt")
        self.assertEqual(schema["capability"], "ppt")
        self.assertEqual(schema["required_groups"][0]["fields"], ["units", "lessons", "knowledge_points"])

    def test_dispatch_returns_standardized_success_payload(self) -> None:
        fake_result = {
            "lesson_plan_path": "/tmp/lesson.md",
            "metadata_path": "/tmp/lesson.json",
            "lesson_plan_preview": "preview",
        }

        with patch("eduagent_core.capability_registry.generate_lesson_plan_artifacts", return_value=fake_result):
            payload = dispatch_capability(
                capability="lesson_plan",
                payload={"course": "高中数学", "lessons": "分数加减法"},
            )

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["capability"], "lesson_plan")
        self.assertEqual(payload["artifacts"]["lesson_plan_path"], "/tmp/lesson.md")
        self.assertEqual(payload["preview"], "preview")

    def test_dispatch_returns_standardized_validation_error(self) -> None:
        payload = dispatch_capability(capability="exam", payload={"subject": "大模型"})

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["capability"], "exam")
        self.assertEqual(payload["error_type"], "validation_error")
        self.assertEqual(payload["missing_fields"], ["knowledge_bases"])


if __name__ == "__main__":
    unittest.main()
