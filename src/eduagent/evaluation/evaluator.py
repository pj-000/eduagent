"""Evaluator: coordinates the three-stage evaluation pipeline."""
from __future__ import annotations

from ..models.artifacts import (
    ArtifactKind,
    CapabilityArtifact,
    ExecutableToolSpec,
)
from ..models.evaluation import EvaluationCard
from .rule_checker import RuleChecker


class Evaluator:
    """Coordinates rule_checker results with agent reviews to decide activation."""

    def __init__(self, rule_checker: RuleChecker | None = None):
        self.rule_checker = rule_checker or RuleChecker()

    def run_rule_check(self, artifact: CapabilityArtifact) -> dict:
        result = self.rule_checker.check(artifact)
        return {"passed": result.passed, "issues": result.issues}

    def can_activate(
        self,
        artifact: CapabilityArtifact,
        rule_check: dict,
        reviews: list[EvaluationCard],
    ) -> tuple[bool, str]:
        """Determine if artifact meets activation criteria."""
        if not rule_check.get("passed"):
            return False, f"Rule check failed: {'; '.join(rule_check.get('issues', []))}"

        if not reviews:
            return False, "No reviews submitted"

        # Only consider the latest approval from each evaluator
        latest_by_evaluator: dict[str, EvaluationCard] = {}
        for review in reviews:
            latest_by_evaluator[review.evaluator_id] = review

        approved_reviews = [r for r in latest_by_evaluator.values() if r.approve]
        rejected_reviews = [r for r in latest_by_evaluator.values() if not r.approve]

        if rejected_reviews:
            r = rejected_reviews[0]
            revisions = "; ".join(r.required_revisions) if r.required_revisions else "none specified"
            return False, f"Reviewer {r.evaluator_id} rejected. Revisions: {revisions}"

        if not approved_reviews:
            return False, "No approvals submitted"

        # Check score thresholds — only on reviews that actually contain these scores
        # (reviewer checks correctness/safety; user_simulator checks usability etc.)
        for review in approved_reviews:
            if "correctness" in review.scores:
                correctness = review.scores["correctness"]
                if correctness < 0.7:
                    return False, f"Correctness score {correctness} below threshold 0.7"

            if isinstance(artifact, ExecutableToolSpec) and "safety" in review.scores:
                safety = review.scores["safety"]
                if safety < 0.8:
                    return False, f"Safety score {safety} below threshold 0.8"

        return True, "All checks passed"
