"""Tests for evaluation: rule_checker and evaluator."""
from __future__ import annotations

import pytest
from pathlib import Path

from eduagent.evaluation.evaluator import Evaluator
from eduagent.evaluation.rule_checker import RuleChecker
from eduagent.models.artifacts import ExecutableToolSpec, PromptSkillSpec
from eduagent.models.evaluation import EvaluationCard
from eduagent.runtime.sandbox import Sandbox


@pytest.fixture
def rule_checker():
    return RuleChecker(sandbox=Sandbox())


@pytest.fixture
def evaluator(rule_checker):
    return Evaluator(rule_checker=rule_checker)


class TestRuleChecker:
    def test_valid_executable_tool(self, rule_checker, tmp_path):
        code = "def run(x=1):\n    return x * 2"
        code_path = tmp_path / "tool.py"
        code_path.write_text(code)

        tool = ExecutableToolSpec(
            artifact_id="t1",
            name="doubler",
            description="Doubles a number",
            created_by="builder",
            entrypoint="run",
            code_path=str(code_path),
        )
        result = rule_checker.check(tool)
        assert result.passed
        assert result.issues == []

    def test_empty_name_fails(self, rule_checker):
        tool = ExecutableToolSpec(
            artifact_id="t1",
            name="",
            description="test",
            created_by="builder",
        )
        result = rule_checker.check(tool)
        assert not result.passed
        assert any("name" in i.lower() for i in result.issues)

    def test_empty_description_fails(self, rule_checker):
        tool = ExecutableToolSpec(
            artifact_id="t1",
            name="test",
            description="",
            created_by="builder",
        )
        result = rule_checker.check(tool)
        assert not result.passed

    def test_forbidden_import_fails(self, rule_checker, tmp_path):
        code = "import os\ndef run():\n    return os.getcwd()"
        code_path = tmp_path / "tool.py"
        code_path.write_text(code)

        tool = ExecutableToolSpec(
            artifact_id="t1",
            name="bad_tool",
            description="Uses os",
            created_by="builder",
            entrypoint="run",
            code_path=str(code_path),
        )
        result = rule_checker.check(tool)
        assert not result.passed
        assert any("os" in i for i in result.issues)

    def test_missing_entrypoint_fails(self, rule_checker, tmp_path):
        code = "def helper():\n    return 1"
        code_path = tmp_path / "tool.py"
        code_path.write_text(code)

        tool = ExecutableToolSpec(
            artifact_id="t1",
            name="no_entry",
            description="Missing entrypoint",
            created_by="builder",
            entrypoint="run",
            code_path=str(code_path),
        )
        result = rule_checker.check(tool)
        assert not result.passed
        assert any("entrypoint" in i.lower() for i in result.issues)

    def test_smoke_test_failure(self, rule_checker, tmp_path):
        code = "def run():\n    raise ValueError('boom')"
        code_path = tmp_path / "tool.py"
        code_path.write_text(code)

        tool = ExecutableToolSpec(
            artifact_id="t1",
            name="boom_tool",
            description="Raises error",
            created_by="builder",
            entrypoint="run",
            code_path=str(code_path),
        )
        result = rule_checker.check(tool)
        assert not result.passed
        assert any("smoke" in i.lower() for i in result.issues)

    def test_valid_prompt_skill(self, rule_checker):
        skill = PromptSkillSpec(
            artifact_id="s1",
            name="simplifier",
            description="Simplifies text",
            created_by="builder",
            trigger_guidance="simplify text reading",
            prompt_fragment="Please simplify the following text",
        )
        result = rule_checker.check(skill)
        assert result.passed

    def test_empty_prompt_fragment_fails(self, rule_checker):
        skill = PromptSkillSpec(
            artifact_id="s1",
            name="bad_skill",
            description="Bad skill",
            created_by="builder",
            trigger_guidance="test",
            prompt_fragment="",
        )
        result = rule_checker.check(skill)
        assert not result.passed

    def test_empty_trigger_guidance_fails(self, rule_checker):
        skill = PromptSkillSpec(
            artifact_id="s1",
            name="bad_skill",
            description="Bad skill",
            created_by="builder",
            trigger_guidance="",
            prompt_fragment="do something",
        )
        result = rule_checker.check(skill)
        assert not result.passed


class TestEvaluator:
    def test_can_activate_all_pass(self, evaluator, tmp_path):
        code = "def run():\n    return {'ok': True}"
        code_path = tmp_path / "tool.py"
        code_path.write_text(code)

        tool = ExecutableToolSpec(
            artifact_id="t1",
            name="good_tool",
            description="Good tool",
            created_by="builder",
            entrypoint="run",
            code_path=str(code_path),
        )

        rule_check = {"passed": True, "issues": []}
        reviews = [
            EvaluationCard(
                artifact_id="t1",
                evaluator_id="reviewer",
                scores={"correctness": 0.9, "safety": 1.0},
                approve=True,
                rationale="Good",
            ),
            EvaluationCard(
                artifact_id="t1",
                evaluator_id="user_simulator",
                scores={"correctness": 0.8, "safety": 0.9},
                approve=True,
                rationale="Useful",
            ),
        ]

        can, reason = evaluator.can_activate(tool, rule_check, reviews)
        assert can
        assert "passed" in reason.lower()

    def test_cannot_activate_rule_fail(self, evaluator):
        tool = ExecutableToolSpec(
            artifact_id="t1", name="t", description="d", created_by="b"
        )
        rule_check = {"passed": False, "issues": ["bad code"]}
        can, reason = evaluator.can_activate(tool, rule_check, [])
        assert not can
        assert "rule" in reason.lower()

    def test_cannot_activate_no_reviews(self, evaluator):
        tool = ExecutableToolSpec(
            artifact_id="t1", name="t", description="d", created_by="b"
        )
        rule_check = {"passed": True, "issues": []}
        can, reason = evaluator.can_activate(tool, rule_check, [])
        assert not can
        assert "review" in reason.lower()

    def test_cannot_activate_reviewer_rejects(self, evaluator):
        tool = ExecutableToolSpec(
            artifact_id="t1", name="t", description="d", created_by="b"
        )
        rule_check = {"passed": True, "issues": []}
        reviews = [
            EvaluationCard(
                artifact_id="t1",
                evaluator_id="reviewer",
                scores={"correctness": 0.9, "safety": 1.0},
                approve=False,
                rationale="Not good enough",
                required_revisions=["fix X"],
            ),
        ]
        can, reason = evaluator.can_activate(tool, rule_check, reviews)
        assert not can
        assert "rejected" in reason.lower()

    def test_cannot_activate_low_correctness(self, evaluator):
        tool = ExecutableToolSpec(
            artifact_id="t1", name="t", description="d", created_by="b"
        )
        rule_check = {"passed": True, "issues": []}
        reviews = [
            EvaluationCard(
                artifact_id="t1",
                evaluator_id="reviewer",
                scores={"correctness": 0.5, "safety": 1.0},
                approve=True,
                rationale="Approved but low score",
            ),
        ]
        can, reason = evaluator.can_activate(tool, rule_check, reviews)
        assert not can
        assert "correctness" in reason.lower()

    def test_cannot_activate_low_safety(self, evaluator):
        tool = ExecutableToolSpec(
            artifact_id="t1", name="t", description="d", created_by="b"
        )
        rule_check = {"passed": True, "issues": []}
        reviews = [
            EvaluationCard(
                artifact_id="t1",
                evaluator_id="reviewer",
                scores={"correctness": 0.9, "safety": 0.5},
                approve=True,
                rationale="Approved but unsafe",
            ),
        ]
        can, reason = evaluator.can_activate(tool, rule_check, reviews)
        assert not can
        assert "safety" in reason.lower()

    def test_prompt_skill_no_safety_check(self, evaluator):
        skill = PromptSkillSpec(
            artifact_id="s1",
            name="skill",
            description="d",
            created_by="b",
            trigger_guidance="t",
            prompt_fragment="p",
        )
        rule_check = {"passed": True, "issues": []}
        reviews = [
            EvaluationCard(
                artifact_id="s1",
                evaluator_id="reviewer",
                scores={"correctness": 0.8},
                approve=True,
                rationale="Good",
            ),
        ]
        can, reason = evaluator.can_activate(skill, rule_check, reviews)
        assert can

    def test_user_simulator_scores_dont_block_activation(self, evaluator):
        """user_simulator uses usability/educational_value, not correctness/safety."""
        tool = ExecutableToolSpec(
            artifact_id="t1", name="t", description="d", created_by="b"
        )
        rule_check = {"passed": True, "issues": []}
        reviews = [
            EvaluationCard(
                artifact_id="t1",
                evaluator_id="reviewer",
                scores={"correctness": 0.9, "safety": 1.0},
                approve=True,
                rationale="Good",
            ),
            EvaluationCard(
                artifact_id="t1",
                evaluator_id="user_simulator",
                scores={"usability": 0.9, "educational_value": 0.85, "age_appropriateness": 0.9},
                approve=True,
                rationale="Useful",
            ),
        ]
        can, reason = evaluator.can_activate(tool, rule_check, reviews)
        assert can

    def test_latest_review_per_evaluator_wins(self, evaluator):
        """If reviewer submitted two cards, only the latest counts."""
        tool = ExecutableToolSpec(
            artifact_id="t1", name="t", description="d", created_by="b"
        )
        rule_check = {"passed": True, "issues": []}
        reviews = [
            # First review: reject with low scores
            EvaluationCard(
                artifact_id="t1",
                evaluator_id="reviewer",
                scores={"correctness": 0.0, "safety": 0.0},
                approve=False,
                rationale="First pass — missing code",
            ),
            # Second review: approve with good scores
            EvaluationCard(
                artifact_id="t1",
                evaluator_id="reviewer",
                scores={"correctness": 0.9, "safety": 1.0},
                approve=True,
                rationale="Revised — looks good",
            ),
        ]
        can, reason = evaluator.can_activate(tool, rule_check, reviews)
        assert can
